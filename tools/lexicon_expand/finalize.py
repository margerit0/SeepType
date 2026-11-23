"""Validate authored repair decisions, preserve originals, and build a preview."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json

from tools.lexicon import pipeline as legacy
from tools.lexicon_expand.common import CACHE, ROOT, canonical, digest, read_json, read_jsonl, require, write_json, write_jsonl
from tools.lexicon_expand.continue_repairs import REVIEW40, archive
from tools.lexicon_expand.repair_trial import REVIEW
from tools.lexicon_expand.review_pilot import BATCH, dictionary_readings, verify_protected
from tools.lexicon_expand.runtime import choices_from_tsv, compile_model, lua_bytes, supplement_dictionary, trigger_additions

FINAL = ROOT / 'data/lexicon-expansion/reviews/final-300-20261109'
PREVIEW = CACHE / 'runtime-preview-20261109'
SNAPSHOT = ROOT / 'data/lexicon-expansion/reviews/reviewed-snapshot-20261109'
SNAPSHOT_PREVIEW = CACHE / 'runtime-reviewed-snapshot-20261109'


def repair_inputs(require_complete=True):
    archive()
    trial = read_jsonl(REVIEW / 'revisions.jsonl')
    forty = read_jsonl(REVIEW40 / 'external/results/drafts.jsonl')
    original = {r['id']: r for r in read_jsonl(BATCH / 'revision-requests.jsonl')}
    generated = {}
    for row in trial:
        generated[row['original_sense_id']] = {
            'candidate': row['candidate'], 'generation': row['generation'],
            'unresolved_reason': row['unresolved_reason']}
    for row in forty:
        sid = row['repair_of']['sense_id']
        require(sid not in generated, 'Repeated repair ancestry')
        require(row['review']['status'] == 'pending' and not row['release_ready'], 'Generator granted approval')
        require(len(row['senses']) <= 1, 'Multiple repair candidates')
        generated[sid] = {'candidate': row['senses'][0] if row['senses'] else None,
                          'generation': row['generation'], 'unresolved_reason': row['unresolved_reason']}
    require(len(original) == 50 and set(generated) <= set(original), 'Unknown repair ancestry')
    if require_complete:
        require(len(generated) == 50 and set(generated) == set(original),
                'All fifty repairs must have verified external results')
    from tools.lexicon_expand.followups import apply_followups
    generated = apply_followups(original, generated, FINAL / 'followup-plans.json')
    return original, generated


def finalize(snapshot=False):
    original, generated = repair_inputs(require_complete=not snapshot)
    output = SNAPSHOT if snapshot else FINAL
    meta = read_json(FINAL / 'provenance.json')
    require(meta['method'] == 'user-delegated-agent-semantic-review' and meta['reviewer'] == 'Codex',
            'Explicit delegated reviewer required')
    require(meta['authorization'] == '用户：委托你复审并继续后续任务', 'Review authorization changed')
    verify_protected(read_json(REVIEW40 / 'provenance.json'))
    with (FINAL / 'repair-decisions.tsv').open(encoding='utf-8', newline='') as stream:
        decisions = list(csv.DictReader(stream, delimiter='\t'))
    require(len(decisions) == len(generated) and len({r['original_sense_id'] for r in decisions}) == len(generated),
            'Expected an authored decision for each returned repair')
    require({r['original_sense_id'] for r in decisions} == set(generated), 'Decision coverage differs')
    baseline = read_jsonl(BATCH / 'accepted-senses.jsonl')
    require(len(baseline) == 504, 'Original accepted list changed')
    accepted = list(baseline)
    reviewed = []
    for d in decisions:
        require(set(d) == {'original_sense_id', 'candidate_sha256', 'decision', 'reason'} and d['reason'].strip(),
                'Invalid authored decision')
        sid = d['original_sense_id']
        source, result = original[sid], generated[sid]
        candidate = result['candidate']
        require(d['candidate_sha256'] == digest(canonical(candidate)), 'Stale repair decision')
        require(d['decision'] in {'accepted', 'duplicate', 'rejected', 'deferred'}, 'Unknown decision')
        duplicate_ids = []
        if d['decision'] in {'accepted', 'duplicate'}:
            require(candidate is not None, 'Cannot adopt an unresolved external result')
            duplicate_ids = [r['id'] for r in accepted if all(r[k] == candidate[k] for k in
                             ('chinese', 'pinyin', 'commit_english'))]
        if d['decision'] == 'accepted':
            require(candidate['quality']['disposition'] != 'blocked', 'Blocked pronunciation cannot be accepted')
            require(not duplicate_ids, 'Repeated accepted entry must be archived as duplicate')
            accepted.append({**source, **candidate, 'verdict': 'accepted',
                'reason': d['reason'], 'selected_as_primary': False,
                'base_reading_present': candidate['quality']['base_reading_present'],
                'base_numbered_reading_present': candidate['quality']['numbered_reading_present'],
                'requires_trigger_addition': not candidate['quality']['base_reading_present'],
                'original_sense_id': sid, 'generation': result['generation'],
                'review': {'status': 'accepted', 'reviewer': meta['reviewer'],
                           'reviewed_at': meta['reviewed_at'], 'method': meta['method'],
                           'candidate_sha256': d['candidate_sha256'], 'human_approved': False}})
        elif d['decision'] == 'duplicate':
            require(duplicate_ids, 'Duplicate decision requires an existing accepted entry')
        reviewed.append({**d, 'row': source['row'], 'sense_number': source['sense_number'],
                         'original': source, **result, 'duplicate_of_sense_ids': duplicate_ids,
                         'reviewer': meta['reviewer'], 'method': meta['method'],
                         'reviewed_at': meta['reviewed_at'], 'human_approved': False})
    require(len({r['id'] for r in accepted}) == len(accepted), 'Accepted sense IDs collide')
    readings, _, _, dictionary_sha = dictionary_readings()
    additions = trigger_additions(accepted, readings)
    model = compile_model(accepted, choices_from_tsv(FINAL / 'primary-choices.tsv'), legacy.validate().entries)
    write_jsonl(output / 'accepted-senses.jsonl', accepted)
    write_jsonl(output / 'reviewed-repairs.jsonl', reviewed)
    write_jsonl(output / 'original-exclusions.jsonl', [r for r in read_jsonl(BATCH / 'issues.jsonl') if r['verdict'] == 'rejected'])
    write_jsonl(output / 'trigger-additions.jsonl', additions)
    write_json(output / 'runtime-model.json', model)
    write_json(output / 'summary.json', {
        'schema_version': 1, 'method': meta['method'], 'reviewer': meta['reviewer'],
        'status': 'partial-reviewed-snapshot' if snapshot else 'all-repairs-reviewed',
        'repair_review_complete': len(generated) == 50,
        'repair_senses_reviewed': len(generated), 'repair_senses_awaiting_generation': 50 - len(generated),
        'authorization': meta['authorization'], 'reviewed_at': meta['reviewed_at'],
        'original_accepted_senses_preserved': 504, 'original_excluded_senses': 31,
        'repair_decisions': dict(Counter(d['decision'] for d in decisions)),
        'accepted_senses': len(accepted), 'unique_expansion_triggers': len({r['chinese'] for r in accepted}),
        'missing_trigger_readings': len(additions), 'dictionary_sha256': dictionary_sha,
        'runtime_chinese_entries_with_legacy_preview': len(model['entries']),
        'human_approved': False, 'release_ready': False,
        'files': {name: digest((output / name).read_bytes()) for name in (
            'accepted-senses.jsonl', 'reviewed-repairs.jsonl', 'original-exclusions.jsonl',
            'trigger-additions.jsonl', 'runtime-model.json')},
        'authored_inputs': {name: digest((FINAL / name).read_bytes()) for name in (
            'provenance.json', 'repair-decisions.tsv', 'primary-choices.tsv', 'followup-plans.json')
                           if (FINAL / name).exists()},
        'limits': ['Delegated semantic review is not distribution approval.',
                   'Existing candidate UI uses the explicit common sense; other accepted senses remain in the data.',
                   'Original 200-entry human-review preview remains unchanged.']})
    labels = {'accepted': '通过', 'duplicate': '重复归档', 'rejected': '不通过', 'deferred': '暂缓或需返修'}
    lines = ['# 用户委托复审结果', '',
             f"审核者：{meta['reviewer']}；时间：{meta['reviewed_at']}；方式：明确受托的代理语义审核。", '',
             f"已复审 {len(generated)}/50 个返修义项；其余 {50-len(generated)} 个尚未返回。",
             f"本阶段保留原504个通过义项，并纳入{len(accepted)-504}个通过修订，共{len(accepted)}个义项。",
             f"需补录 {len(additions)} 个中文读音入口。原31个剔除义项不进入新版。", '',
             '本报告保留所有审核理由和生成来源，不代表人工签名或正式发布批准。', '',
             '| 原位置 | 原英文／中文 | 外部修订 | 结论 | 复审理由 |',
             '| --- | --- | --- | --- | --- |']
    from tools.lexicon_expand.review_pilot import cell
    for row in sorted(reviewed, key=lambda r: (r['row'], r['sense_number'])):
        source, candidate = row['original'], row['candidate']
        after = (f"{candidate['chinese']} → {candidate['commit_english']}；{candidate['pinyin']}；{candidate['meaning_zh']}"
                 if candidate else '无可靠候选：' + row['unresolved_reason'])
        lines.append('| ' + ' | '.join(cell(v) for v in (
            f"{row['row']}.{row['sense_number']}", f"{source['english']}／{source['chinese']}",
            after, labels[row['decision']], row['reason'])) + ' |')
    legacy.atomic_write(output / 'review.md', ('\n'.join(lines) + '\n').encode('utf-8'))
    return read_json(output / 'summary.json')


def build_preview(snapshot=False):
    summary = finalize(snapshot=snapshot)
    output = SNAPSHOT if snapshot else FINAL
    preview = SNAPSHOT_PREVIEW if snapshot else PREVIEW
    from tools.dictionary.cedict import files
    dictionary = files()['cedict_study.dict.yaml']
    model = read_json(output / 'runtime-model.json')
    additions = read_jsonl(output / 'trigger-additions.jsonl')
    legacy.atomic_write(preview / 'lua/lexicon.lua', lua_bytes(model))
    legacy.atomic_write(preview / 'cedict_study.dict.yaml', supplement_dictionary(dictionary, additions))
    manifest = {'schema_version': 1, 'status': 'delegated-reviewed-development-preview',
                'accepted_senses': summary['accepted_senses'], 'supplemented_readings': len(additions),
                'review_complete': summary['repair_review_complete'],
                'base_dictionary_sha256': digest(dictionary), 'review_summary_sha256': digest((output / 'summary.json').read_bytes()),
                'files': {p.relative_to(preview).as_posix(): digest(p.read_bytes())
                          for p in sorted(preview.rglob('*')) if p.is_file() and p.name != 'manifest.json'},
                'release_ready': False}
    write_json(preview / 'manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['finalize', 'build-preview'])
    parser.add_argument('--snapshot', action='store_true', help='Build a labeled partial snapshot; never claim full repair completion')
    args = parser.parse_args()
    print(json.dumps(finalize(args.snapshot) if args.command == 'finalize' else build_preview(args.snapshot), ensure_ascii=False, indent=2))
