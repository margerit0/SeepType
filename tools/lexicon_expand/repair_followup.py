"""Prepare the explicitly routed follow-up repairs without calling a provider."""
import json
from datetime import datetime, timedelta, timezone
from tools.lexicon_expand.catalog import load_prepared
from tools.lexicon_expand.common import (
    CACHE, ROOT, canonical, digest, read_json, read_jsonl, require, write_json,
)
from tools.lexicon_expand.generation import generate
from tools.lexicon_expand.planning import load_plan
from tools.lexicon_expand.provider import load_config
from tools.lexicon_expand.quality_v3 import save_profile, target_fields
from tools.lexicon_expand.repair_trial import unchanged_file

NAME = 'repair-13-20261110'
WORK = CACHE / NAME
REVIEW = ROOT / 'data/lexicon-expansion/reviews' / NAME
SOURCE = ROOT / 'data/lexicon-expansion/reviews/expansion-104-20261110'
BASELINE = ROOT / 'data/lexicon-expansion/reviews/adopted-expansion-20261110/accepted-senses.jsonl'
QUEUE = 'after-expansion-100-20261110-b'


def select_repairs(records, queue, routes, source_targets, accepted, *, batch=NAME):
    originals = {r['id']: r for r in records}
    held = {r['packet_id']: r for r in queue}
    require(len(held) == len(queue) == len(routes) and
            {r['packet_id'] for r in routes} == set(held), 'Every queued candidate requires one route')
    accepted_ids = {r['id'] for r in accepted}
    selected, deferred = [], []
    for route in routes:
        item = held[route['packet_id']]
        record = originals[item['target_id']]
        sense = item['candidate']
        require(item['decision']['decision'] in ('rejected', 'deferred'), 'Accepted content reached repair')
        require(sense in record['senses'] and sense['id'] not in accepted_ids and
                route['candidate_sha256'] == item['candidate_sha256'] ==
                item['decision']['candidate_sha256'] == digest(canonical(sense)), 'Stale repair source')
        require(item['source_record_sha256'] == digest(canonical(record)), 'Original repair record changed')
        require(route['reason'].strip(), 'Explicit repair route reason required')
        if route['action'] == 'hold-for-evidence':
            deferred.append(route)
            continue
        require(route['action'] == 'repair' and route['focus'].strip(), 'Invalid repair route')
        source = source_targets[item['target_id']]
        target = {**target_fields({**source, 'id': record['id']}),
                  'target_id': 'repair-' + digest(canonical([record['id'], sense['id'], batch]))[:24],
                  'original_target_id': record['id'], 'original_sense': sense,
                  'source_record_sha256': digest(canonical(record)),
                  'review_reason': item['decision']['reason'],
                  'repair_category': route['category'], 'repair_focus': route['focus'],
                  'repair_evidence': route.get('evidence', [])}
        selected.append(target)
    require(len({r['target_id'] for r in selected}) == len(selected), 'Repeated repair identity')
    return selected, deferred


def prepare():
    routing = read_json(REVIEW / 'repair-routing.json')
    frozen_paths = [SOURCE / n for n in ('repair-queue.json', 'evaluation-decisions.json',
                                        'external/results/drafts.jsonl', 'external/plan/selected-targets.jsonl')]
    frozen_paths += [BASELINE, REVIEW / 'repair-routing.json', REVIEW / 'evidence-check.json']
    sources = {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in frozen_paths}
    source_targets = {r['target_id']: r for r in read_jsonl(SOURCE / 'external/plan/selected-targets.jsonl')}
    selected, deferred = select_repairs(read_jsonl(SOURCE / 'external/results/drafts.jsonl'),
        read_json(SOURCE / 'repair-queue.json')['items'], routing['items'], source_targets, read_jsonl(BASELINE))
    require(len(selected) == 13 and len(deferred) == 1, 'Expected 12 clear repairs, Congress, and one held pronunciation')
    _, _, manifest = load_prepared()
    plan = save_profile(WORK / 'plan', selected, 3, manifest, task='repair_senses', sources=sources)
    config = load_config(CACHE / 'api.local.json')
    caps = dict(max_items=len(selected), max_requests=plan['request_count'] * 30,
                max_output_budget=plan['request_count'] * 30 * config['max_output_tokens'])
    metadata = {'schema_version': 1, 'batch': NAME, 'status': 'planned-not-started',
                'authorization': '用户：执行；12项明确返修与2项补证据，当前100词结束后接续跑小批返修。',
                'targets': len(selected), 'request_count': plan['request_count'],
                'prompt_version': 3, 'quality_policy_version': 2, 'automatic_adoption': False,
                'max_attempts_per_request': 30, 'max_retries': 29, 'max_wait_seconds': 30,
                'generation_caps': caps, 'plan_sha256': digest(canonical(plan)),
                'provider_sha256': digest(canonical(config)), 'preserved_development_senses': 819,
                'held_for_evidence': deferred, 'review_sources': sources,
                'start_after': 'expansion-100-20261110-b', 'packaging_deferred': True}
    raw = json.dumps(metadata, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    for folder in (WORK, REVIEW):
        unchanged_file(folder / 'batch-plan.json', raw)
    for path in (WORK / 'plan').iterdir():
        if path.is_file():
            unchanged_file(REVIEW / 'external/plan' / path.name, path.read_bytes())
    loaded, _ = load_plan(WORK / 'plan')
    preview = generate(WORK / 'plan', CACHE / 'api.local.json', WORK / 'results', execute=False, **caps)
    report = {'schema_version': 1, 'batch': NAME, 'planned_repairs': len(selected),
              'request_count': loaded['request_count'], 'held_candidates': len(deferred),
              'baseline_accepted_senses_preserved': 819, 'frozen_review_inputs': len(sources),
              'source_words': [r['english'] for r in selected], 'generation_caps': caps,
              'api_key_read': preview['api_key_read'], 'model_requests': preview['model_requests'],
              'automatic_adoption': False, 'packaging_deferred': True}
    write_json(REVIEW / 'preparation-verification.json', report)
    return report


def prepare_queue():
    """Freeze exactly one successor; reruns never extend its six-hour deadline."""
    from tools.lexicon_expand.followup_run import validate_queue
    work = CACHE / QUEUE
    review = ROOT / 'data/lexicon-expansion/reviews' / QUEUE
    if (work / 'queue.json').exists():
        return validate_queue(QUEUE)
    created = datetime.now(timezone.utc)
    predecessor = 'expansion-100-20261110-b'
    frozen = {}
    for name in (predecessor, NAME):
        for folder in (CACHE / name, ROOT / 'data/lexicon-expansion/reviews' / name):
            for suffix in ('batch-plan.json', 'plan/plan.json' if folder.is_relative_to(CACHE) else 'external/plan/plan.json'):
                path = folder / suffix
                frozen[path.relative_to(ROOT).as_posix()] = digest(path.read_bytes())
    config = {'schema_version': 1, 'queue': QUEUE,
              'authorization': '用户：执行；让当前100词完成后接续小批返修。',
              'predecessor': predecessor, 'successor': NAME,
              'created_at': created.isoformat(timespec='seconds'),
              'expires_at': (created + timedelta(hours=6)).isoformat(timespec='seconds'),
              'poll_seconds': 15, 'maximum_successor_batches': 1,
              'frozen_inputs': frozen, 'automatic_adoption': False, 'packaging_deferred': True,
              'start_condition': '原批进程锁释放，20组/100目标的原响应与收据完整校验，无未知结果或停止标记。',
              'failure_behavior': '前批未完整结束、结果未知、摘要变动或六小时到期时不发返修；凭据只在条件成立后准备。'}
    raw = json.dumps(config, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    for folder in (work, review):
        unchanged_file(folder / 'queue.json', raw)
    return validate_queue(QUEUE)


if __name__ == '__main__':
    import json
    print(json.dumps(prepare(), ensure_ascii=False, indent=2))
