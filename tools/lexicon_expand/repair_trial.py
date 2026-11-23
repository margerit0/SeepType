"""Prepare a ten-sense external repair trial and render it for user review."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from tools.lexicon_expand.common import (
    CACHE, ROOT, canonical, digest, generated_directory, read_json, read_jsonl,
    require, write_json, write_jsonl,
)
from tools.lexicon_expand.generation import read_attempts
from tools.lexicon_expand.planning import load_plan, make_job, save_plan
from tools.lexicon_expand.review_pilot import BATCH, cell, verify_protected
from tools.lexicon_expand.storage import atomic_write


PLAN = CACHE / 'repair-trial-10-20261109'
RESULTS = CACHE / 'repair-trial-10-results-20261109'
REVIEW = ROOT / 'data/lexicon-expansion/reviews/repair-trial-10-20261109'
# Explicit sense slots in the reviewed 300-item batch; not whole target words.
SELECTION = (
    (226, 1, '拼音'), (228, 1, '拼音'), (274, 1, '拼音'),
    (191, 1, '大小写'), (91, 1, '大小写'), (140, 1, '大小写'),
    (209, 1, '词义'), (180, 1, '词义'),
    (71, 2, '搭配'), (160, 2, '搭配'),
)


def select_trial(targets, revisions):
    by_slot = {(r['row'], r['sense_number']): r for r in revisions}
    require(len(revisions) == len(by_slot) == 50, 'Expected 50 unique revision slots')
    by_sense = {t['original_sense']['id']: t for t in targets}
    selected, slots = [], []
    for number, (row, sense_number, category) in enumerate(SELECTION, 1):
        require((row, sense_number) in by_slot, 'Trial slot is not a revision')
        revision = by_slot[(row, sense_number)]
        require(revision['verdict'] == 'needs-revision', 'Trial slot is not held for revision')
        target = by_sense.get(revision['id'])
        require(target is not None and target['original_target_id'] == revision['target_id'],
                'Trial target differs from reviewed sense')
        selected.append(target)
        slots.append({'number': number, 'category': category, 'row': row,
                      'sense_number': sense_number, 'repair_id': target['target_id'],
                      'original_sense_id': revision['id'], 'reason': revision['reason']})
    require(len({t['target_id'] for t in selected}) == 10, 'Repeated trial target')
    return selected, slots


def unchanged_file(path, raw):
    if path.exists():
        require(path.read_bytes() == raw, 'Existing trial artifact differs; use a new trial directory')
    else:
        atomic_write(path, raw)


def prepare_trial(plan_directory=PLAN, review_directory=REVIEW):
    full_directory = CACHE / 'repair-v2'
    plan, _ = load_plan(full_directory)
    targets = read_jsonl(full_directory / 'selected-targets.jsonl')
    revisions = read_jsonl(BATCH / 'revision-requests.jsonl')
    selected, slots = select_trial(targets, revisions)
    accepted = read_jsonl(BATCH / 'accepted-senses.jsonl')
    rejected = [r for r in read_jsonl(BATCH / 'issues.jsonl') if r['verdict'] == 'rejected']
    require(len(accepted) == 504 and len(rejected) == 31, 'Review baseline counts changed')
    require(not {t['original_sense']['id'] for t in selected} &
            {r['id'] for r in accepted + rejected}, 'Trial includes accepted or rejected senses')
    meta = read_json(BATCH / 'provenance.json')
    verify_protected(meta)
    protected = {e['path']: e['sha256'] for e in meta['protected_inputs']}
    for directory in (BATCH, full_directory):
        for p in directory.iterdir():
            if p.is_file():
                protected[p.relative_to(ROOT).as_posix()] = digest(p.read_bytes())
    provenance = {'schema_version': 1, 'status': 'awaiting-external-generation-and-user-review',
                  'selection': slots, 'baseline_accepted_senses': 504,
                  'excluded_rejected_senses': 31, 'remaining_revision_senses': 40,
                  'protected_inputs': [{'path': p, 'sha256': sha} for p, sha in sorted(protected.items())],
                  'automatic_adoption': False}
    unchanged_file(Path(review_directory) / 'provenance.json',
                   (json.dumps(provenance, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    prompt = (full_directory / 'prompt.txt').read_text(encoding='utf-8')
    jobs = [make_job('repair_senses', selected[i:i + 5], prompt, response_version=3,
                     quality_policy=plan['quality_policy']) for i in range(0, 10, 5)]
    trial_plan = {k: v for k, v in plan.items() if k != 'files'}
    trial_plan.update(maximum_items=10, request_count=2, trial_requires_user_review=True,
                      trial_selection=slots)
    output = generated_directory(plan_directory)
    save_plan(output, trial_plan, jobs, selected, prompt)
    held_ids = {t['original_sense']['id'] for t in selected}
    remaining = [r for r in revisions if r['id'] not in held_ids]
    unchanged_file(Path(review_directory) / 'remaining-revision-requests.jsonl',
                   b''.join(canonical(r) + b'\n' for r in remaining))
    return {'planned_senses': 10, 'requests': 2, 'remaining_senses': 40,
            'protected_files': len(protected), 'model_requests': 0}


def validate_pending(records, targets):
    by_id = {r['id']: r for r in records}
    require(len(records) == len(by_id) == len(targets) == 10, 'Expected all ten unique trial records')
    require(set(by_id) == {t['target_id'] for t in targets}, 'Returned trial identities differ')
    for target in targets:
        record = by_id[target['target_id']]
        require(record['repair_of'] == {
            'target_id': target['original_target_id'], 'sense_id': target['original_sense']['id'],
            'source_record_sha256': target['source_record_sha256']}, 'Repair ancestry changed')
        require(record['review']['status'] == 'pending' and record['selected_sense_id'] is None
                and record['release_ready'] is False, 'Trial cannot grant approval')
        require(len(record['senses']) <= 1, 'More than one sense returned for repair')
        require(record['generation']['kind'] == 'external-api', 'Expected external model provenance')
    return by_id


def render_trial(plan_directory=PLAN, results_directory=RESULTS, review_directory=REVIEW):
    plan, jobs = load_plan(plan_directory)
    targets = read_jsonl(Path(plan_directory) / 'selected-targets.jsonl')
    review_directory = Path(review_directory)
    provenance = read_json(review_directory / 'provenance.json')
    protected_count = verify_protected(provenance)
    run = read_json(Path(results_directory) / 'run.json')
    require(run['identity'] == digest(canonical({'plan': plan, 'provider': run['provider']})),
            'Trial run identity changed')
    attempts = read_attempts(Path(results_directory), jobs, run['identity'])
    completed = [a for a in attempts if a['status'] == 'completed']
    require(len(completed) == len({a['request_id'] for a in completed}) == 2,
            'Both trial requests must complete exactly once')
    records = [r for a in completed for r in a['records']]
    by_id = validate_pending(records, targets)
    require(read_jsonl(Path(results_directory) / 'drafts.jsonl') == sorted(records, key=lambda r: r['id']),
            'Drafts differ from verified external responses')
    # Keep exact external evidence outside the disposable cache, without credentials.
    evidence_paths = [(Path(plan_directory) / name, Path('external/plan') / name)
                      for name in ('plan.json', 'requests.jsonl', 'selected-targets.jsonl', 'prompt.txt')]
    evidence_paths += [(Path(results_directory) / name, Path('external/results') / name)
                       for name in ('run.json', 'summary.json', 'drafts.jsonl')]
    for folder in ('attempts', 'responses'):
        evidence_paths += [(p, Path('external/results') / folder / p.name)
                           for p in sorted((Path(results_directory) / folder).glob('*.json'))]
    for source, destination in evidence_paths:
        unchanged_file(review_directory / destination, source.read_bytes())
    by_target = {t['target_id']: t for t in targets}
    rows = []
    lines = ['# 10个代表性义项：外部模型试修，待用户复审', '',
             '原504个通过义项保留；31个剔除义项排除；本批不自动纳入新版数据。',
             '所有候选均来自独立外部API响应。拼音和大小写检查不构成语义通过。',
             '复审可逐项回复“通过／继续返修／剔除”；未解决项可确认暂缓。', '',
             '| 编号 | 类别 | 原条目 | 外部修订 | 修订说明／未解决原因 | 检查 |',
             '| --- | --- | --- | --- | --- | --- |']
    for slot in provenance['selection']:
        target, record = by_target[slot['repair_id']], by_id[slot['repair_id']]
        original = target['original_sense']
        candidate = record['senses'][0] if record['senses'] else None
        row = {**slot, 'original_target_id': target['original_target_id'],
               'original_sense': original, 'candidate': candidate,
               'unresolved_reason': record['unresolved_reason'], 'generation': record['generation'],
               'candidate_sha256': digest(canonical(candidate)), 'review': {'status': 'pending-user-review'},
               'adopted': False}
        rows.append(row)
        before = f"{original['chinese']} → {original['commit_english']}；{original['pinyin']}"
        after = (f"{candidate['chinese']} → {candidate['commit_english']}；{candidate['pinyin']}"
                 if candidate else '未解决（无修订候选）')
        note = candidate['meaning_zh'] if candidate else record['unresolved_reason']
        checks = candidate['quality']['disposition'] if candidate else '无候选'
        lines.append('| ' + ' | '.join(cell(v) for v in
                     (slot['number'], slot['category'], before, after, note, checks)) + ' |')
    lines += ['', '## 逐项原文与追溯', '']
    for row in rows:
        original, candidate = row['original_sense'], row['candidate']
        lines += [f"### {row['number']}. {original['commit_english']} / {original['chinese']}", '',
                  f"- 原位置：{row['row']}.{row['sense_number']}；原义项：`{row['original_sense_id']}`。",
                  f"- 返修理由：{row['reason']}",
                  f"- 原文：{original['chinese']} / {original['pinyin']} / {original['pos']} / {original['meaning_zh']}"]
        if candidate:
            lines += [f"- 修订：{candidate['chinese']} / {candidate['pinyin']} / {candidate['pos']} / {candidate['meaning_zh']}",
                      f"- 显示与提交：`{candidate['display_english']}` / `{candidate['commit_english']}`。",
                      f"- 质量标记：`{json.dumps(candidate['quality']['findings'], ensure_ascii=False)}`。"]
        else:
            lines += [f"- 未解决：{row['unresolved_reason']}"]
        lines += [f"- 请求：`{row['generation']['request_id']}`；原始响应SHA256：`{row['generation']['response_sha256']}`。", '']
    write_jsonl(review_directory / 'revisions.jsonl', rows)
    template = {'schema_version': 1, 'revisions_sha256': digest((review_directory / 'revisions.jsonl').read_bytes()),
                'reviewer': None, 'reviewed_at': None,
                'decisions': [{'number': r['number'], 'original_sense_id': r['original_sense_id'],
                               'candidate_sha256': r['candidate_sha256'], 'decision': 'pending',
                               'note': ''} for r in rows]}
    unchanged_file(review_directory / 'decisions.template.json',
                   (json.dumps(template, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    atomic_write(review_directory / 'review.md', ('\n'.join(lines) + '\n').encode('utf-8'))
    dispositions = Counter(r['candidate']['quality']['disposition'] for r in rows if r['candidate'])
    summary = {'schema_version': 1, 'status': 'pending-user-review', 'trial_senses': 10,
               'returned_candidates': sum(r['candidate'] is not None for r in rows),
               'unresolved_senses': sum(r['candidate'] is None for r in rows),
               'quality_dispositions': dict(dispositions), 'user_approved_senses': 0,
               'newly_adopted_senses': 0, 'preserved_accepted_senses': 504,
               'excluded_rejected_senses': 31, 'remaining_unattempted_revision_senses': 40,
               'baseline_missing_triggers': 53, 'final_missing_triggers': None,
               'runtime_imported_senses': 0, 'attempts': len(attempts),
               'provider': run['provider'],
               'reserved_output_tokens': sum(a['reserved_output_tokens'] for a in attempts),
               'provider_reported_usage': {key: sum(a.get('usage', {}).get(key, 0) for a in attempts)
                                           for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')},
               'protected_original_files_verified': verify_protected(provenance),
               'prior_protected_original_files_verified': verify_protected(read_json(BATCH / 'provenance.json')),
               'artifacts_sha256': {name: digest((review_directory / name).read_bytes()) for name in
                                     ('revisions.jsonl', 'review.md', 'decisions.template.json', 'provenance.json',
                                      'remaining-revision-requests.jsonl')}}
    summary['external_evidence_sha256'] = {
        destination.as_posix(): digest((review_directory / destination).read_bytes())
        for _, destination in evidence_paths}
    require(summary['protected_original_files_verified'] == protected_count, 'Protection count changed')
    write_json(review_directory / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'report'])
    args = parser.parse_args()
    result = prepare_trial() if args.command == 'plan' else render_trial()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
