"""Small frozen v3/v4 trial and configurable, source-bound repair batches."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from tools.lexicon_expand.common import (
    CACHE, ROOT, canonical, digest, read_json, read_jsonl, require, word_key, write_json,
)
from tools.lexicon_expand.catalog import load_prepared
from tools.lexicon_expand.generation import generate, run_lock
from tools.lexicon_expand.planning import PROMPTS, load_plan, select_targets
from tools.lexicon_expand.provider import load_config
from tools.lexicon_expand.quality_v3 import save_profile, target_fields, receipts, archive, status, review_packet, score
from tools.lexicon_expand.recover import recover_saved
from tools.lexicon_expand.repair_followup import select_repairs
from tools.lexicon_expand.repair_trial import unchanged_file
from tools.lexicon_expand.retry import retry_request

REVIEWS = ROOT / 'data/lexicon-expansion/reviews'
BASELINE = REVIEWS / 'adopted-expansion-20261110/accepted-senses.jsonl'
AUTHORIZATION = '用户：按交接计划执行，扩词优先，先不打包，适时commit。'


def folders(name):
    require(isinstance(name, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', name),
            'Use one batch directory name')
    return CACHE / name, REVIEWS / name


def freeze_json(path, value):
    unchanged_file(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def freeze_batch(name, targets, version, *, task='map_targets', sources=None, details=None):
    work, review = folders(name)
    _, _, manifest = load_prepared()
    plan = save_profile(work / 'plan', targets, version, manifest, task=task, sources=sources)
    config = load_config(CACHE / 'api.local.json')
    count = plan['request_count']
    meta = {'schema_version': 1, 'batch': name, 'status': 'planned-not-started',
            'authorization': AUTHORIZATION, 'targets': len(targets), 'request_count': count,
            'prompt_version': version, 'quality_policy_version': 2,
            'max_attempts_per_request': 30, 'max_retries': 29, 'max_wait_seconds': 30,
            'generation_caps': dict(max_items=len(targets), max_requests=count * 30,
                                    max_output_budget=count * 30 * config['max_output_tokens']),
            'plan_sha256': digest(canonical(plan)), 'provider_sha256': digest(canonical(config)),
            'preserved_development_senses': 819, 'automatic_adoption': False,
            'packaging_deferred': True, **(details or {})}
    for folder in (work, review):
        freeze_json(folder / 'batch-plan.json', meta)
    for path in (work / 'plan').iterdir():
        if path.is_file():
            unchanged_file(review / 'external/plan' / path.name, path.read_bytes())
    generate(work / 'plan', CACHE / 'api.local.json', work / 'results', execute=False,
             **meta['generation_caps'])
    return meta


def unseen_targets(count):
    """Exclude every historical planned/generated word, baseline and prompt token."""
    from tools.lexicon import pipeline as legacy
    catalog, _, _ = load_prepared()
    excluded = {word_key(r['commit_english']) for r in legacy.validate().entries}
    sources = {}
    patterns = ('selected-targets.jsonl', 'drafts.jsonl', 'source-drafts.jsonl', 'accepted-senses.jsonl')
    for root in (REVIEWS, CACHE):
        for pattern in patterns:
            for path in sorted(root.rglob(pattern)):
                sources[path.relative_to(ROOT).as_posix()] = digest(path.read_bytes())
                for row in read_jsonl(path):
                    value = row.get('english') or row.get('commit_english')
                    if value:
                        excluded.add(word_key(value))
    for path in PROMPTS.values():
        sources[path.relative_to(ROOT).as_posix()] = digest(path.read_bytes())
        excluded.update(word_key(w) for w in re.findall(r'[A-Za-z]+(?: [A-Za-z]+)*', path.read_text(encoding='utf-8')))
        excluded.update(word_key(w) for w in re.findall(r'[A-Za-z]+', path.read_text(encoding='utf-8')))
    selected = select_targets([t for t in catalog if word_key(t['english']) not in excluded], count)
    require(len(selected) == len({word_key(t['english']) for t in selected}) == count,
            'Insufficient different unseen targets')
    return [target_fields(t) for t in selected], sources, sorted(excluded)


def prepare_trial(name):
    work, review = folders(name)
    if (work / 'experiment.json').exists():
        meta = read_json(work / 'experiment.json')
        require(meta == read_json(review / 'experiment.json'), 'Trial metadata copies differ')
        for profile, sha in meta['profiles'].items():
            require(digest(canonical(load_plan(work / profile)[0])) == sha, 'Trial plan changed')
        return meta
    selected, sources, excluded = unseen_targets(20)
    _, _, manifest = load_prepared()
    profiles = {f'holdout-v{v}': save_profile(work / f'holdout-v{v}', selected, v, manifest) for v in (3, 4)}
    schedule = []
    for i in range(4):
        for v in ((3, 4) if i % 2 == 0 else (4, 3)):
            profile = f'holdout-v{v}'
            schedule.append({'profile': profile, 'request_id': load_plan(work / profile)[1][i]['id']})
    config = load_config(CACHE / 'api.local.json')
    meta = {'schema_version': 1, 'authorization': AUTHORIZATION,
            'profiles': {n: digest(canonical(p)) for n, p in profiles.items()},
            'provider': config, 'schedule': schedule, 'holdout_targets': 20,
            'max_attempts_per_request': 30, 'max_total_attempts': 240,
            'max_reserved_output_tokens': 240 * config['max_output_tokens'],
            'selection_sources': sources, 'excluded_english': excluded,
            'automatic_adoption': False, 'packaging_deferred': True,
            'preserved_development_senses': 819,
            'evaluation_rules': ['Same targets/provider/batch-size/quality-policy; alternate arm order.',
                                 'Review every candidate and empty result; report coverage and senses separately.',
                                 'Repairs are development cases, excluded from holdout scores.',
                                 'Prefer v3 when this small sample provides no clear quality gain.']}
    for folder in (work, review):
        freeze_json(folder / 'experiment.json', meta)
    archive(work, review)
    return meta


def prepare_repairs(name, routing_path, *, version=4, baseline_path=None):
    """Routes explicitly name each source queue, candidate hash and repair intent."""
    work, review = folders(name)
    routing_path = Path(routing_path).resolve()
    require(routing_path.is_relative_to(ROOT), 'Routing must be in this workspace')
    routing = read_json(routing_path)
    require(routing['items'], 'Empty repair routing')
    baseline_path = Path(baseline_path or BASELINE).resolve()
    require(baseline_path.is_relative_to(REVIEWS), 'Repair baseline must be in reviews')
    baseline = read_jsonl(baseline_path)
    sources = {routing_path.relative_to(ROOT).as_posix(): digest(routing_path.read_bytes()),
               baseline_path.relative_to(ROOT).as_posix(): digest(baseline_path.read_bytes())}
    targets, deferred = [], []
    seen = set()
    for route in routing['items']:
        source_path = (ROOT / route['source_queue_path']).resolve()
        require(source_path.is_relative_to(REVIEWS) and source_path.name.endswith('repair-queue.json'),
                'Invalid source queue path')
        source = source_path.parent
        queue = [q for q in read_json(source_path)['items'] if q['packet_id'] == route['packet_id']]
        require(len(queue) == 1, 'Repair source candidate missing or ambiguous')
        profile = route.get('profile')
        require(profile == queue[0].get('profile'), 'Repair profile differs from source queue')
        if profile is not None:
            require(isinstance(profile, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', profile),
                    'Invalid repair source profile')
            experiment_path = source / 'experiment.json'
            require(profile in read_json(experiment_path)['profiles'], 'Unknown repair source profile')
            sources[experiment_path.relative_to(ROOT).as_posix()] = digest(experiment_path.read_bytes())
        paths = [source_path,
                 source / 'external' / (profile + '-results' if profile else 'results') / 'drafts.jsonl',
                 source / 'external' / (profile if profile else 'plan') / 'selected-targets.jsonl',
                 source / 'evaluation-decisions.json']
        sources.update({p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in paths})
        key = source_path.as_posix(), route['packet_id']
        require(key not in seen, 'Repeated repair source')
        seen.add(key)
        decisions = {d['packet_id']: d for d in read_json(source / 'evaluation-decisions.json')['items']}
        require(decisions[route['packet_id']] == queue[0]['decision'], 'Repair verdict differs from source review')
        original_targets = {r['target_id']: r for r in read_jsonl(paths[2])}
        chosen, held = select_repairs(read_jsonl(paths[1]), queue, [route], original_targets,
                                      baseline, batch=name)
        for target in chosen:
            target['repair_source'] = {'queue_path': route['source_queue_path'],
                                       'packet_id': route['packet_id'],
                                       'candidate_sha256': route['candidate_sha256']}
            if profile is not None:
                target['repair_source']['profile'] = profile
        targets.extend(chosen)
        deferred.extend(held)
    require(targets and len({t['target_id'] for t in targets}) == len(targets), 'Repeated or empty repairs')
    return freeze_batch(name, targets, version, task='repair_senses', sources=sources,
                        details={'held_for_evidence': deferred,
                                 'historical_held_items': routing.get('historical_held_items', []),
                                 'development_cases_not_holdout': True,
                                 'preserved_development_senses': len(baseline),
                                 'authorization': routing.get('authorization', AUTHORIZATION)})


def prepare_expansion(name, *, version):
    """Freeze exactly one explicitly selected 100-target expansion."""
    work, review = folders(name)
    if (work / 'batch-plan.json').exists():
        meta = read_json(work / 'batch-plan.json')
        require(meta == read_json(review / 'batch-plan.json') and meta['prompt_version'] == version,
                'Frozen expansion differs from requested version')
        load_plan(work / 'plan')
        return meta
    require(version in (3,4), 'Select an expansion prompt version explicitly')
    targets, sources, excluded = unseen_targets(100)
    selection = {'schema_version':1,'targets':100,'excluded_english':excluded,
                 'selection_time_input_sha256':sources,
                 'note':'Selection-time audit; other frozen batches may continue appending receipts.'}
    freeze_json(review / 'selection-evidence.json', selection)
    baseline = REVIEWS / 'adopted-expansion-b-20261110/accepted-senses.jsonl'
    frozen = {p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in
              (review / 'selection-evidence.json', baseline, review / 'version-selection.json')}
    return freeze_batch(name, targets, version, sources=frozen,
                        details={'preserved_development_senses':len(read_jsonl(baseline)),
                                 'selection_audit':'selection-evidence.json',
                                 'maximum_automatic_batches':1})


def run_trial(name):
    work, review = folders(name)
    meta = prepare_trial(name)
    require(load_config(CACHE / 'api.local.json') == meta['provider'], 'Trial provider changed')
    emit = lambda e: print(json.dumps(e, ensure_ascii=False), flush=True)
    cancelled = lambda: (work / 'stop.json').exists()
    state = 'running'
    with run_lock(work):
        def recover(profile):
            output = work / (profile + '-results')
            if (output / 'run.json').exists():
                recover_saved(work / profile, CACHE / 'api.local.json', output)

        def checkpoint():
            report = archive(work, review)
            write_json(review / 'trial-state.json', {'status': state, 'generation': report})
            return report

        try:
            for profile in meta['profiles']:
                recover(profile)
            require(status(work)['uncertain_attempts'] == 0, 'Inspect uncertain trial requests before resuming')
            for item in meta['schedule']:
                profile, rid = item['profile'], item['request_id']
                def history():
                    return [{**a, 'retryable': False} if a.get('failure_category') == 'content' else a
                            for a in receipts(work, profile) if a['request_id'] == rid]

                def attempt():
                    current = status(work)
                    require(current['attempts'] < meta['max_total_attempts'] and
                            current['reserved_output_tokens'] + meta['provider']['max_output_tokens'] <=
                            meta['max_reserved_output_tokens'], 'Trial cumulative budget reached')
                    try:
                        return generate(work / profile, CACHE / 'api.local.json', work / (profile + '-results'),
                            execute=True, max_items=20, max_requests=120,
                            max_output_budget=120 * meta['provider']['max_output_tokens'], retry_failed=True,
                            request_ids=[rid], progress=emit)
                    finally:
                        recover(profile)
                        checkpoint()
                ok = retry_request(attempt, history, max_retries=29, emit=emit, cancelled=cancelled)
                emit({'event': 'request_finished', **item, 'success': ok})
                if not ok and history() and history()[-1].get('failure_scope') == 'provider':
                    raise ValueError('Provider authorization or configuration failed')
            report = status(work)
            state = 'completed' if report['completed_requests'] == report['planned_requests'] else 'incomplete'
        except Exception:
            state = 'failed'
            raise
        finally:
            checkpoint()
    return {'status': state, **report}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['trial-plan', 'trial-run', 'repair-plan', 'trial-review-packet', 'trial-score', 'expansion-plan'])
    parser.add_argument('name')
    parser.add_argument('--routing', type=Path)
    parser.add_argument('--prompt-version', type=int, choices=(3,4))
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    work, review = folders(args.name)
    if args.command == 'expansion-plan':
        result = prepare_expansion(args.name, version=args.prompt_version)
    elif args.command == 'trial-review-packet':
        result = {'candidates': len(review_packet(work, review)[0])}
    elif args.command == 'trial-score':
        result = score(work, review, versions=(3,4), group_names=('holdout',), preserved_senses=943)
    else:
        result = (prepare_repairs(args.name, args.routing, version=args.prompt_version or 4,
                                  baseline_path=args.baseline) if args.command == 'repair-plan' else
                  prepare_trial(args.name) if args.command == 'trial-plan' else run_trial(args.name))
    print(json.dumps(result, ensure_ascii=False, indent=2))
