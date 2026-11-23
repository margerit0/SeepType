"""Bounded next-100 expansion, with separate external drafts and authored review."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json

from tools.lexicon import pipeline as legacy
from tools.lexicon_expand.catalog import load_prepared
from tools.lexicon_expand.common import (CACHE, ROOT, canonical, digest, read_json, read_jsonl,
                                         require, word_key, write_json, write_jsonl)
from tools.lexicon_expand.generation import generate, read_attempts, run_lock
from tools.lexicon_expand.planning import PROMPTS, load_plan, make_job, save_plan, select_targets
from tools.lexicon_expand.quality import policy
from tools.lexicon_expand.repair_trial import unchanged_file
from tools.lexicon_expand.review_pilot import BATCH, verify_protected

NAME = 'next-100-20261109'
PLAN = CACHE / NAME
RESULTS = CACHE / (NAME + '-results')
REVIEW = ROOT / 'data/lexicon-expansion/reviews' / NAME
BASE = ROOT / 'data/lexicon-expansion/reviews/final-300-20261109'
PREVIEW = CACHE / (NAME + '-preview')
CAPS = dict(max_items=100, max_requests=60, max_output_budget=245760)
AUTHORIZATION = '用户：先提交，继续下一批词库扩充；先做100个新目标，完成生成、复审、触发词补录和包内回归后再扩大批量。'


def prepare():
    if (PLAN / 'plan.json').exists():
        load_plan(PLAN)
        return read_json(REVIEW / 'provenance.json')
    catalog, _, manifest = load_prepared()
    old = read_jsonl(BATCH / 'source-drafts.jsonl')
    baseline = read_jsonl(BASE / 'accepted-senses.jsonl')
    excluded = {word_key(r.get('english', r.get('commit_english'))) for r in old + baseline + legacy.validate().entries}
    selected = select_targets([r for r in catalog if word_key(r['english']) not in excluded], 100)
    require(len(selected) == len({word_key(r['english']) for r in selected}) == 100,
            'Exactly 100 different new targets required')
    prompt = PROMPTS[2].read_text(encoding='utf-8')
    fields = ('english', 'source_forms', 'packs', 'parts_of_speech', 'cefr_levels', 'source_refs',
              'dictionary_references', 'existing_entries')
    targets = [{'target_id': r['id'], **{k: r[k] for k in fields}} for r in selected]
    jobs = [make_job('map_targets', targets[i:i+5], prompt, response_version=3) for i in range(0, 100, 5)]
    protected = {}
    for folder in (ROOT / 'data/lexicon', ROOT / 'data/lexicon-expansion'):
        for path in sorted(folder.rglob('*')):
            if path.is_file() and not path.is_relative_to(REVIEW):
                protected[path.relative_to(ROOT).as_posix()] = digest(path.read_bytes())
    provenance = {'schema_version': 1, 'authorization': AUTHORIZATION,
                  'method': 'user-delegated-agent-semantic-review', 'reviewer': 'Codex',
                  'base_accepted_senses': len(baseline), 'new_targets': 100,
                  'excluded_english': sorted(excluded), 'generation_caps': CAPS,
                  'selection': '100 unseen IELTS targets; same frequency/reference stratification as pilot',
                  'deferred_phrase_assessment': 'separate; never rewrite original four sense identities',
                  'protected_inputs': [{'path': p, 'sha256': sha} for p, sha in sorted(protected.items())]}
    plan = {'schema_version': 3, 'status': 'offline-plan-not-executed', 'word_pack': 'ielts',
            'word_targets': 100, 'scene_slots': 0, 'maximum_items': 100,
            'maximum_senses_per_item': 3, 'request_count': 20, 'batch_size': 5,
            'prompt_version': 2, 'response_schema_version': 3,
            'prompt_sha256': digest(prompt.encode('utf-8')), 'quality_policy': policy(),
            'catalog_manifest_sha256': digest(canonical(manifest)),
            'prepared_directory': str((CACHE / 'prepared').resolve()),
            'automatic_adoption': False, 'review_sources': {
                (BASE / 'accepted-senses.jsonl').relative_to(ROOT).as_posix(): digest((BASE / 'accepted-senses.jsonl').read_bytes())}}
    save_plan(PLAN, plan, jobs, selected, prompt)
    write_json(REVIEW / 'provenance.json', provenance)
    return {'new_targets': 100, 'requests': 20, 'protected_inputs': len(protected), 'generation_caps': CAPS}


def verified_attempts():
    plan, jobs = load_plan(PLAN)
    run = read_json(RESULTS / 'run.json')
    require(run['identity'] == digest(canonical({'plan': plan, 'provider': run['provider']})), 'Run identity changed')
    return read_attempts(RESULTS, jobs, run['identity'])


def archive():
    attempts = verified_attempts()
    records = sorted([r for a in attempts if a['status'] == 'completed' for r in a['records']], key=lambda r: r['id'])
    require(records == read_jsonl(RESULTS / 'drafts.jsonl'), 'Drafts differ from external response evidence')
    for source, prefix in ((PLAN, 'plan'), (RESULTS, 'results')):
        for path in sorted(source.rglob('*')):
            if not path.is_file() or path.suffix not in ('.json', '.jsonl', '.txt'):
                continue
            relative = path.relative_to(source)
            if source == RESULTS and relative.parts[0] in {'attempts', 'responses'}:
                receipt = RESULTS / 'attempts' / path.name
                if receipt.exists() and read_json(receipt)['status'] == 'started':
                    continue
            destination = REVIEW / 'external' / prefix / relative
            raw = path.read_bytes()
            if destination.exists() and destination.read_bytes() != raw:
                require(path.name in {'drafts.jsonl', 'summary.json', 'quality-issues.jsonl'},
                        'Immutable external evidence changed')
                prior = destination.read_bytes()
                unchanged_file(REVIEW / 'external/history' / (digest(prior) + '-' + path.name), prior)
                legacy.atomic_write(destination, raw)
            else:
                unchanged_file(destination, raw)
    summary = read_json(RESULTS / 'summary.json')
    summary['protected_inputs_verified'] = verify_protected(read_json(REVIEW / 'provenance.json'))
    summary['historical_protected_inputs_verified'] = verify_protected(read_json(
        ROOT / 'data/lexicon-expansion/reviews/repair-remaining-40-20261109/provenance.json'))
    write_json(REVIEW / 'generation-summary.json', summary)
    runtime_report = ROOT / 'experiments/lexicon-expansion/results' / (NAME + '-runtime.json')
    write_json(ROOT / 'experiments/lexicon-expansion/results' / (NAME + '-progress.json'), {
        'recorded_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'generation': summary, 'baseline_commit': '58a7a73',
        'new_targets': 100, 'scope_expanded': False,
        'review_complete': (REVIEW / 'summary.json').exists(),
        'package_regression_complete': runtime_report.exists() and read_json(runtime_report)['passed'],
        'process_status': 'Check the live process and receipts; this is a persisted checkpoint.'})
    return summary


def attempt_limit_policy(jobs, attempts, maximum, output_per_attempt):
    """Keep all past charges and reserve only the remaining per-request slots."""
    require(type(maximum) is int and 1 <= maximum <= 30, 'Attempt limit must be between 1 and 30')
    require(not any(a['status'] == 'started' for a in attempts), 'Inspect uncertain requests before continuing')
    complete = {a['request_id'] for a in attempts if a['status'] == 'completed'}
    counts = Counter(a['request_id'] for a in attempts)
    remaining = sum(max(0, maximum - counts[j['id']]) for j in jobs if j['id'] not in complete)
    return {'max_attempts_per_request': maximum, 'max_retries': maximum - 1,
            'historical_attempts': len(attempts), 'remaining_attempt_slots': remaining,
            'generation_caps': dict(max_items=100, max_requests=len(attempts) + remaining,
                max_output_budget=sum(a['reserved_output_tokens'] for a in attempts) + remaining * output_per_attempt)}


def configure_attempt_limit(maximum, authorization):
    from tools.lexicon_expand.provider import load_config
    with run_lock(CACHE / (NAME + '-orchestrator')), run_lock(RESULTS):
        _, jobs = load_plan(PLAN)
        attempts = verified_attempts()
        policy_path = RESULTS / 'attempt-policy.json'
        if policy_path.exists():
            current = read_json(policy_path)
            require(current['max_attempts_per_request'] == maximum,
                    'Existing attempt policy differs; preserve it before changing the limit')
            return current
        config = load_config(CACHE / 'api.local.json')
        current = {'schema_version': 1, 'authorization': authorization,
                   'recorded_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                   'interpretation': 'Maximum attempts per request, including its first call and historical failures',
                   'run_identity': read_json(RESULTS / 'run.json')['identity'],
                   'retry_delay_cap_seconds': 30,
                   'previous_generation_caps': CAPS,
                   'historical_receipts': [{'path': p.name, 'sha256': digest(p.read_bytes())}
                                           for p in sorted((RESULTS / 'attempts').glob('*.json'))],
                   **attempt_limit_policy(jobs, attempts, maximum, config['max_output_tokens'])}
        unchanged_file(REVIEW / f'attempt-limit-{maximum}.json',
                       (json.dumps(current, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        write_json(policy_path, current)
        return current


def run():
    from tools.lexicon_expand.retry import retry_request
    _, jobs = load_plan(PLAN)
    emit = lambda event: print(json.dumps(event, ensure_ascii=False), flush=True)
    with run_lock(CACHE / (NAME + '-orchestrator')):
        policy_path = RESULTS / 'attempt-policy.json'
        current = read_json(policy_path) if policy_path.exists() else None
        caps, max_retries = CAPS, 15
        if current is not None:
            require(current['run_identity'] == read_json(RESULTS / 'run.json')['identity'],
                    'Attempt policy belongs to another run')
            require(current['max_retries'] == current['max_attempts_per_request'] - 1,
                    'Inconsistent per-request attempt policy')
            for receipt in current['historical_receipts']:
                require(digest((RESULTS / 'attempts' / receipt['path']).read_bytes()) == receipt['sha256'],
                        'Historical attempt receipt changed')
            caps, max_retries = current['generation_caps'], current['max_retries']
        emit({'event': 'attempt_policy', 'max_attempts_per_request': max_retries + 1,
              'generation_caps': caps, 'historical_attempts_preserved': True})
        for job in jobs:
            if (RESULTS / 'stop.json').exists():
                break
            def history():
                rows = verified_attempts() if (RESULTS / 'run.json').exists() else []
                return [{**a, 'retryable': False} if a.get('failure_category') == 'content' else a
                        for a in rows if a['request_id'] == job['id']]
            ok = retry_request(lambda: generate(PLAN, CACHE / 'api.local.json', RESULTS,
                                execute=True, **caps, retry_failed=True,
                                request_ids=[job['id']], progress=emit),
                               history, max_retries=max_retries, emit=emit,
                               cancelled=lambda: (RESULTS / 'stop.json').exists())
            emit({'event': 'request_finished', 'request_id': job['id'], 'success': ok})
            archive()
            if not ok and history()[-1].get('failure_scope') == 'provider':
                break
    return archive()


def reviewed_senses(records, decisions, baseline, reviewed_at):
    """Every decision is authored separately and bound to exact model content."""
    indexed = {(r['id'], s['id']): (r, s) for r in records for s in r['senses']}
    indexed.update({(r['id'], '-'): (r, None) for r in records if not r['senses']})
    require(len(decisions) == len(indexed) and
            {(d['target_id'], d['sense_id']) for d in decisions} == set(indexed),
            'Each returned sense or unresolved target requires exactly one authored decision')
    accepted, reviewed = [], []
    identities = {(s['chinese'], s['pinyin'], s['commit_english']) for s in baseline}
    for decision in decisions:
        require(set(decision) == {'target_id', 'sense_id', 'candidate_sha256', 'decision', 'reason'}
                and decision['reason'].strip(), 'Invalid authored review decision')
        record, sense = indexed[decision['target_id'], decision['sense_id']]
        require(decision['candidate_sha256'] == digest(canonical(sense)), 'Stale candidate review hash')
        require(decision['decision'] in {'accepted', 'duplicate', 'rejected', 'deferred'}, 'Unknown review verdict')
        row = {**decision, 'english': record['english'], 'candidate': sense,
               'source_record_sha256': digest(canonical(record)), 'generation': record['generation'],
               'reviewer': 'Codex', 'method': 'user-delegated-agent-semantic-review',
               'reviewed_at': reviewed_at, 'human_approved': False}
        if decision['decision'] in {'accepted', 'duplicate'}:
            require(sense is not None, 'Unresolved result cannot be accepted')
            identity = sense['chinese'], sense['pinyin'], sense['commit_english']
            if decision['decision'] == 'duplicate':
                require(identity in identities, 'Duplicate requires an existing accepted identity')
            else:
                require(identity not in identities, 'Duplicate accepted identity')
                require(sense['quality']['disposition'] != 'blocked', 'Blocked sense cannot be accepted')
                require(record['review']['status'] == 'pending' and record['release_ready'] is False,
                        'Expected original pending model draft')
                identities.add(identity)
                accepted.append({**sense, 'target_id': record['id'], 'english': record['english'],
                    'packs': record['packs'], 'verdict': 'accepted', 'reason': decision['reason'],
                    'generation': record['generation'], 'review': {k: row[k] for k in
                        ('reviewer', 'method', 'reviewed_at', 'candidate_sha256', 'human_approved')},
                    'requires_trigger_addition': not sense['quality']['base_reading_present']})
        reviewed.append(row)
    return accepted, reviewed


def build_preview():
    from tools.lexicon_expand.runtime import (choices_from_tsv, compile_model, lua_bytes,
                                             supplement_dictionary, trigger_additions)
    from tools.lexicon_expand.review_pilot import dictionary_readings, cell
    from tools.dictionary.cedict import files
    summary = archive()
    require(summary['returned_items'] == summary['resolved_draft_items'] + summary['unresolved_items'] == 100
            and summary['completed_requests'] == 20 and summary['uncertain_attempts'] == 0,
            'Complete all 100 targets before building this batch')
    records = read_jsonl(RESULTS / 'drafts.jsonl')
    require({r['id'] for r in records} == {t['id'] for t in read_jsonl(PLAN / 'selected-targets.jsonl')},
            'Generated targets differ from the 100 locked targets')
    baseline = read_jsonl(BASE / 'accepted-senses.jsonl')
    with (REVIEW / 'decisions.tsv').open(encoding='utf-8', newline='') as stream:
        decisions = list(csv.DictReader(stream, delimiter='\t'))
    review_meta = read_json(REVIEW / 'review-meta.json')
    require(review_meta['method'] == 'user-delegated-agent-semantic-review' and
            review_meta['reviewer'] == 'Codex', 'Explicit delegated review metadata required')
    new, reviewed = reviewed_senses(records, decisions, baseline, review_meta['reviewed_at'])
    accepted = baseline + new
    readings, _, _, _ = dictionary_readings()
    additions = trigger_additions(accepted, readings)
    choices = choices_from_tsv(BASE / 'primary-choices.tsv')
    choices.update(choices_from_tsv(REVIEW / 'primary-choices.tsv'))
    model = compile_model(accepted, choices, legacy.validate().entries)
    for name, rows in (('new-accepted-senses.jsonl', new), ('accepted-senses.jsonl', accepted),
                       ('reviewed-senses.jsonl', reviewed), ('trigger-additions.jsonl', additions)):
        write_jsonl(REVIEW / name, rows)
    write_json(REVIEW / 'runtime-model.json', model)
    old_additions = {(r['chinese'], r['code']) for r in read_jsonl(BASE / 'trigger-additions.jsonl')}
    report = {'schema_version': 1, 'batch': NAME, 'authorization': AUTHORIZATION,
              'status': 'reviewed-development-preview', 'target_count': 100,
              'generated_senses': sum(len(r['senses']) for r in records),
              'review_decisions': dict(Counter(d['decision'] for d in decisions)),
              'targets_with_accepted_senses': len({r['target_id'] for r in new}),
              'baseline_senses_preserved': len(baseline), 'new_accepted_senses': len(new),
              'accepted_senses': len(accepted), 'supplemented_readings': len(additions),
              'new_supplemented_readings': sum((r['chinese'], r['code']) not in old_additions for r in additions),
              'review': review_meta, 'human_approved': False, 'release_ready': False,
              'generation': summary,
              'authored_inputs': {n: digest((REVIEW / n).read_bytes()) for n in
                                  ('decisions.tsv', 'primary-choices.tsv', 'review-meta.json')},
              'protected_inputs_verified': verify_protected(read_json(REVIEW / 'provenance.json'))}
    write_json(REVIEW / 'summary.json', report)
    lines = ['# 第二批100个新目标复审', '',
             f"100个固定新目标；{report['generated_senses']}个返回义项；新增通过{len(new)}个义项；累计{len(accepted)}个。",
             '逐项受托代理语义复审，不是人工签名或发行批准。原始模型内容与收据保持不变。', '',
             '| 英文目标 | 中文／拼音／说明 | 决定 | 理由 |', '| --- | --- | --- | --- |']
    for r in reviewed:
        s = r['candidate']
        value = f"{s['chinese']} / {s['pinyin']} / {s['meaning_zh']}" if s else '外部模型未能提供可靠义项'
        lines.append('| ' + ' | '.join(cell(x) for x in (r['english'], value, r['decision'], r['reason'])) + ' |')
    legacy.atomic_write(REVIEW / 'review.md', ('\n'.join(lines) + '\n').encode('utf-8'))
    legacy.atomic_write(PREVIEW / 'lua/lexicon.lua', lua_bytes(model))
    legacy.atomic_write(PREVIEW / 'cedict_study.dict.yaml', supplement_dictionary(files()['cedict_study.dict.yaml'], additions))
    return report


def package_preview():
    """Build a separate complete developer ZIP; verify bytes after extraction."""
    import zipfile
    from tools.packaging.package import payload
    from tools.packaging.common import deterministic_zip, json_bytes
    summary = build_preview()
    files, manifest = payload('preview')
    files['data/shared/cedict_study.dict.yaml'] = (PREVIEW / 'cedict_study.dict.yaml').read_bytes()
    files['data/user-template/lua/lexicon.lua'] = (PREVIEW / 'lua/lexicon.lua').read_bytes()
    files['data/lexicon/legacy-preview-lexicon.lua'] = files['data/lexicon/lexicon.lua']
    files['data/lexicon/lexicon.lua'] = files['data/user-template/lua/lexicon.lua']
    for path in (ROOT / 'data/lexicon-expansion').rglob('*'):
        if path.is_file() and not path.is_relative_to(REVIEW):
            files['data/lexicon-expansion/baseline/' + path.relative_to(ROOT / 'data/lexicon-expansion').as_posix()] = path.read_bytes()
    for path in REVIEW.rglob('*'):
        if path.is_file():
            files['data/lexicon-expansion/' + path.relative_to(REVIEW).as_posix()] = path.read_bytes()
    metadata = json.loads(files['data/chinese/provenance.json'])
    metadata['base_dictionary_sha256'] = metadata['dictionary_sha256']
    metadata['dictionary_sha256'] = digest(files['data/shared/cedict_study.dict.yaml'])
    metadata['base_dictionary_entries'] = metadata['dictionary_entries']
    metadata['dictionary_entries'] += summary['supplemented_readings']
    metadata['reviewed_expansion'] = {'batch': NAME, 'additions': summary['supplemented_readings'],
                                     'provenance': 'data/lexicon-expansion/trigger-additions.jsonl'}
    files['data/chinese/provenance.json'] = json_bytes(metadata)
    files['README.txt'] += ('\nThis separate development package includes the reviewed next-100 expansion.\n'
                           'Full external receipts, review decisions, trigger additions and baseline sources are in data/lexicon-expansion.\n'
                           'Delegated review is not human distribution approval.\n').encode('utf-8')
    provenance = json.loads(files['source-provenance/chinese-data.json'])
    for row in provenance:
        if row['path'] == 'data/shared/cedict_study.dict.yaml':
            row['sha256'] = metadata['dictionary_sha256']
            row['changes'].append('Append explicitly reviewed expansion trigger readings; see expansion provenance.')
    files['source-provenance/chinese-data.json'] = json_bytes(provenance)
    manifest['lexicon_expansion'] = summary
    manifest['files'] = [{'path': name, 'sha256': digest(raw), 'bytes': len(raw)}
                         for name, raw in sorted(files.items()) if name != 'package-manifest.json']
    files['package-manifest.json'] = json_bytes(manifest)
    work = CACHE / (NAME + '-package')
    archive_path = work / (NAME + '-development.zip')
    deterministic_zip(archive_path, files)
    second = work / 'determinism-check.zip'
    deterministic_zip(second, dict(reversed(list(files.items()))))
    require(digest(archive_path.read_bytes()) == digest(second.read_bytes()), 'Package export is not deterministic')
    extracted = work / ('extracted-' + digest(archive_path.read_bytes())[:12])
    with zipfile.ZipFile(archive_path) as bundle:
        require(bundle.namelist() == sorted(files), 'Unexpected ZIP files')
        require(all(bundle.read(n) == raw for n, raw in files.items()), 'ZIP content mismatch')
        bundle.extractall(extracted)
    for row in manifest['files']:
        require(digest((extracted / row['path']).read_bytes()) == row['sha256'], 'Extracted package hash mismatch')
    report = {'archive': archive_path.relative_to(ROOT).as_posix(),
              'archive_sha256': digest(archive_path.read_bytes()), 'files_verified': len(files),
              'deterministic': True, 'extracted': extracted.relative_to(ROOT).as_posix(),
              'baseline_senses_preserved': summary['baseline_senses_preserved'],
              'accepted_senses': summary['accepted_senses'], 'release_ready': False}
    write_json(ROOT / 'experiments/lexicon-expansion/results' / (NAME + '-package.json'), report)
    return report


def regress_package():
    from tools.lexicon_expand.verify_runtime import verify
    package = package_preview()
    report_path = ROOT / 'experiments/lexicon-expansion/results' / (NAME + '-runtime.json')
    report = verify(packaged=ROOT / package['extracted'], report_path=report_path)
    package.update(runtime_passed=report['passed'], runtime_checks=len(report['checks']),
                   unique_trigger_readings=report['unique_trigger_readings'])
    write_json(ROOT / 'experiments/lexicon-expansion/results' / (NAME + '-package.json'), package)
    return package


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'generate', 'archive', 'build-preview', 'package', 'regress-package'])
    args = parser.parse_args()
    print(json.dumps({'plan': prepare, 'generate': run, 'archive': archive, 'build-preview': build_preview,
                      'package': package_preview, 'regress-package': regress_package}[args.command](),
                     ensure_ascii=False, indent=2))
