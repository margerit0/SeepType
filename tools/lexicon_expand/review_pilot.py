"""Validate and render the explicitly authored, user-delegated pilot review.

This command never makes semantic decisions, calls a provider, edits generation
receipts, imports runtime entries, or writes human/distribution approval.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from pathlib import Path

from tools.lexicon import pipeline as legacy
from tools.lexicon_expand.catalog import input_reading
from tools.lexicon_expand.common import (
    ROOT, canonical, digest, read_json, read_jsonl, require, write_json,
)


BATCH = ROOT / "data/lexicon-expansion/reviews/pilot-300-20261109"
SOURCE_SHA256 = "1f92e95a1179e8fa8bf8bca780d4a511de34645db6740a1886cff9a2b3d2a43c"
VERDICTS = {"P": "accepted", "R": "needs-revision", "X": "rejected"}
LABELS = {"accepted": "通过", "needs-revision": "返修", "rejected": "剔除",
          "partial": "部分通过"}


def validate_decisions(records, decisions):
    require(len(records) == len(decisions) == 300, "Expected all 300 review decisions")
    require(len({r['id'] for r in records}) == 300, "Repeated target ID")
    seen_senses = set()
    for number, (record, decision) in enumerate(zip(records, decisions), 1):
        require(decision['row'] == str(number) and decision['english'] == record['english'],
                f"Review row identity mismatch: {number}")
        codes = decision['decisions']
        require(len(codes) == len(record['senses']) and set(codes) <= set(VERDICTS),
                f"Incomplete or invalid sense verdicts: {number}")
        require(bool(decision['note'].strip()), f"Missing authored reason: {number}")
        try:
            primary = int(decision['primary'])
        except ValueError:
            raise ValueError(f"Invalid primary index: {number}") from None
        require(0 <= primary <= len(codes), f"Primary outside sense list: {number}")
        require((primary > 0 and codes[primary - 1] == 'P') or
                (primary == 0 and 'P' not in codes), f"Unaccepted primary selection: {number}")
        require(record['review']['status'] == 'pending' and record['selected_sense_id'] is None
                and record['release_ready'] is False, "Expected original pending API draft")
        for sense in record['senses']:
            require(sense['id'] not in seen_senses, "Repeated sense ID")
            require(sense['display_english'] == sense['commit_english'] == record['english'],
                    "Original English display/commit mismatch")
            seen_senses.add(sense['id'])
    require(len(seen_senses) == 585, "Expected all 585 sense decisions")


def source_inputs(batch=BATCH):
    raw = (batch / 'source-drafts.jsonl').read_bytes()
    require(digest(raw) == SOURCE_SHA256, "Frozen source draft hash mismatch")
    meta = read_json(batch / 'provenance.json')
    require(meta['drafts_sha256'] == SOURCE_SHA256, "Provenance hash mismatch")
    require(meta['method'] == 'user-delegated-agent-semantic-review', "Invalid review method")
    records = read_jsonl(batch / 'source-drafts.jsonl')
    with (batch / 'decisions.tsv').open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        require(reader.fieldnames == ['row', 'english', 'decisions', 'primary', 'note'],
                "Unexpected decision columns")
        decisions = list(reader)
    validate_decisions(records, decisions)
    return records, decisions, meta


def verify_protected(meta):
    for entry in meta['protected_inputs']:
        path = (ROOT / entry['path']).resolve()
        require(path.is_relative_to(ROOT), "Protected path escapes repository")
        require(path.is_file() and digest(path.read_bytes()) == entry['sha256'],
                f"Protected original changed: {entry['path']}")
    return len(meta['protected_inputs'])


def dictionary_readings():
    lock = read_json(ROOT / 'data/lexicon/source.lock.json')
    artifact = lock['artifact']
    path = ROOT / '.cache/dictionaries/cc-cedict' / (artifact['archive_sha256'] + '.txt')
    raw = path.read_bytes()
    require(digest(raw) == artifact['text_sha256'], "Pinned dictionary hash mismatch")
    readings, words, characters = set(), defaultdict(set), defaultdict(set)
    for line in raw.decode('utf-8-sig').splitlines():
        if not line or line.startswith('#'):
            continue
        entry = legacy.parse_source(line)
        word = entry['chinese']
        pinyin = entry['pinyin'].lower().replace('u:', 'v')
        code = input_reading(word, pinyin)
        if code is not None:
            readings.add((word, code))
        syllables = pinyin.split()
        if len(word) == len(syllables):
            words[word].add(' '.join(syllables))
            for char, syllable in zip(word, syllables):
                characters[char].add(syllable)
    return readings, words, characters, artifact['text_sha256']


def write_jsonl(path, rows):
    legacy.atomic_write(path, b''.join(canonical(r) + b'\n' for r in rows))


def cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def render(batch=BATCH):
    records, decisions, meta = source_inputs(batch)
    protected = verify_protected(meta)
    readings, words, characters, dictionary_sha = dictionary_readings()
    english_targets, trigger_english = defaultdict(set), defaultdict(set)
    evidence = read_json(batch / 'evidence.json')
    for record in records:
        english_targets[record['english'].casefold()].add(record['id'])
        for sense in record['senses']:
            trigger_english[sense['chinese']].add(record['english'])
    reviewed, accepted, issues, pinyin_findings = [], [], [], []
    for record, decision in zip(records, decisions):
        number = int(decision['row'])
        codes = decision['decisions']
        primary = int(decision['primary'])
        verdict = 'accepted' if set(codes) == {'P'} else 'partial' if 'P' in codes else 'needs-revision'
        item = {
            'schema_version': 1, 'row': number, 'target_id': record['id'],
            'english': record['english'], 'packs': record['packs'],
            'source_record_sha256': digest(canonical(record)),
            'source_drafts_sha256': SOURCE_SHA256, 'reviewer': meta['reviewer'],
            'method': meta['method'], 'reviewed_at': meta['reviewed_at'],
            'verdict': verdict, 'note': decision['note'],
            'selected_sense_id': record['senses'][primary - 1]['id'] if primary else None,
            'evidence_ids': [r['id'] for r in evidence['references'] if number in r['rows']],
            'human_approved': False, 'release_ready': False, 'senses': [],
        }
        for sense_number, (sense, code) in enumerate(zip(record['senses'], codes), 1):
            reading = input_reading(sense['chinese'], sense['pinyin'])
            present = (sense['chinese'], reading) in readings
            checked = {**sense, 'verdict': VERDICTS[code],
                       'selected_as_primary': sense_number == primary,
                       'base_reading_present': present,
                       'base_numbered_reading_present': sense['pinyin'] in words[sense['chinese']],
                       'requires_trigger_addition': code == 'P' and not present,
                       'reason': decision['note']}
            item['senses'].append(checked)
            row = {'row': number, 'target_id': record['id'], 'english': record['english'],
                   'packs': record['packs'], 'sense_number': sense_number, **checked}
            if code == 'P':
                accepted.append(row)
            else:
                issues.append(row)
            conflicts = [
                {'character': char, 'given': syllable,
                 'dictionary_readings': sorted(characters[char])}
                for char, syllable in zip(sense['chinese'], sense['pinyin'].split())
                if syllable not in characters[char]
            ]
            if conflicts:
                require(code != 'P', f"Unchecked pronunciation conflict: {number}")
                pinyin_findings.append({'row': number, 'sense_id': sense['id'],
                                       'chinese': sense['chinese'], 'pinyin': sense['pinyin'],
                                       'conflicts': conflicts, 'review_verdict': VERDICTS[code]})
        reviewed.append(item)
    require({r['row'] for r in pinyin_findings} == set(evidence['local_evidence']['incorrect_pinyin_rows']),
            'Pronunciation evidence no longer matches review')
    counts = Counter(s['verdict'] for r in reviewed for s in r['senses'])
    item_counts = Counter(r['verdict'] for r in reviewed)
    require(sum(counts.values()) == 585 and sum(item_counts.values()) == 300,
            'Review totals do not reconcile')
    primary_senses = [s for r in reviewed for s in r['senses'] if s['selected_as_primary']]
    summary = {
        'schema_version': 1, 'batch_id': meta['batch_id'], 'reviewed_at': meta['reviewed_at'],
        'reviewer': meta['reviewer'], 'method': meta['method'],
        'authorization': meta['authorization'], 'source_drafts_sha256': SOURCE_SHA256,
        'decisions_sha256': digest((batch / 'decisions.tsv').read_bytes()),
        'dictionary_sha256': dictionary_sha,
        'items_reviewed': len(reviewed), 'senses_reviewed': sum(counts.values()),
        'item_verdicts': dict(item_counts), 'sense_verdicts': dict(counts),
        'items_with_accepted_sense': len(primary_senses),
        'selected_primary_senses': len(primary_senses),
        'accepted_senses_base_reading_present': sum(s['base_reading_present'] for s in accepted),
        'accepted_senses_needing_trigger_addition': sum(s['requires_trigger_addition'] for s in accepted),
        'accepted_unique_missing_triggers': len({(s['chinese'], s['pinyin']) for s in accepted
                                                if s['requires_trigger_addition']}),
        'selected_primary_base_reading_present': sum(s['base_reading_present'] for s in primary_senses),
        'selected_primary_needing_trigger_addition': sum(s['requires_trigger_addition'] for s in primary_senses),
        'confirmed_bad_pinyin_senses': len(pinyin_findings),
        'same_english_multiple_targets': {k: sorted(v) for k, v in english_targets.items() if len(v) > 1},
        'shared_chinese_triggers': {k: sorted(v) for k, v in trigger_english.items() if len(v) > 1},
        'protected_original_files_verified': protected,
        'coverage_complete': True, 'new_generation_api_calls': 0,
        'human_approved_items': 0, 'runtime_imported_items': 0, 'release_ready': False,
        'limitations': [
            'User-delegated agent semantic review; not represented as a human signature.',
            'Accepted means language review passed for that original sense and its recorded scope.',
            'Original drafts, provider responses, receipts, budgets and old 200-item corpus are unchanged.',
            'Missing Chinese triggers need integration; native candidate/commit acceptance was not performed.',
            'Correction notes are review requests, not generated replacement translations.',
            'Distribution/license and runtime schema work remain separate from this language review.',
        ],
    }
    write_jsonl(batch / 'reviewed-items.jsonl', reviewed)
    write_jsonl(batch / 'accepted-senses.jsonl', accepted)
    write_jsonl(batch / 'issues.jsonl', issues)
    write_jsonl(batch / 'revision-requests.jsonl', [r for r in issues if r['verdict'] == 'needs-revision'])
    write_json(batch / 'pinyin-findings.json', pinyin_findings)
    write_json(batch / 'summary.json', summary)
    lines = [
        '# 首批300项：受托逐项审核', '',
        f"审核者：Codex；时间：{meta['reviewed_at']}；方式：用户明确委托的代理语义审核。", '',
        f"**{len(reviewed)}/300项、{sum(counts.values())}/585义项已审核。"
        f"{item_counts['accepted']}项全部通过，{item_counts['partial']}项部分通过，"
        f"{item_counts['needs-revision']}项本轮无可用义项。**", '',
        f"**义项：{counts['accepted']}个通过、{counts['needs-revision']}个返修、"
        f"{counts['rejected']}个剔除。** {len(primary_senses)}项已选出一个通过的主义项。", '',
        f"通过义项中，{summary['accepted_senses_base_reading_present']}个中文和无调拼音命中固定基础库，"
        f"{summary['accepted_senses_needing_trigger_addition']}个需要补触发词；"
        f"{len(primary_senses)}个主义项中{summary['selected_primary_needing_trigger_addition']}个需要补触发词。", '',
        '通过表示现有义项在所记语境中可保留；部分通过表示仅保留通过的义项。返修和剔除义项均不进入通过清单。', '',
        '已逐项检查中文与英文对应、英文词性、完整提交词形、普通话拼音、大小写、使用范围和场景。'
        '拼音采用词典本调，不强制改一、不的连读变调；同义中文可以保留为触发别名，名词/动词同形保留元数据。', '',
        '同英文跨场景的 transfer 和 reservation 均为有效复用；原目标身份保留。'
        '同中文对多个英文需展示可区分候选，不能用覆盖方式导入。', '',
        '本审核独立于生成草稿，未冒充人工签名。原始API草稿、收据、用量与旧200条数据保持原样。'
        '本轮未请求新释义、未导入运行时、未安装或发布。', '',
        '复现：在仓库根目录运行 `python -B -X utf8 -m tools.lexicon_expand.review_pilot`。'
        '它只校验并整理显式决策，不会按基础词库命中自动判定通过。', '',
        '## 文件', '',
        '- `decisions.tsv`：全部300项的显式决策；P＝通过，R＝返修，X＝剔除，顺序与原义项一致。',
        '- `reviewed-items.jsonl`：完整逐项审核、主义项与来源内容摘要。',
        f"- `accepted-senses.jsonl`：{counts['accepted']}个通过的原义项；仍携带中文触发词接入状态。",
        f"- `issues.jsonl` / `revision-requests.jsonl`：{len(issues)}个不放行义项／其中{counts['needs-revision']}个返修请求。",
        f"- `source-drafts.jsonl` / `provenance.json`：原始草稿逐字节快照及{protected}个受保护输入摘要。",
        f"- `evidence.json` / `pinyin-findings.json`：公开辞典核对入口及{len(pinyin_findings)}个带调拼音错误。", '',
        f"## {len(pinyin_findings)}个拼音错误", '',
        '| 项目 | 中文 | 原拼音 | 结论 |', '| --- | --- | --- | --- |',
    ]
    for row in pinyin_findings:
        lines.append(f"| {row['row']} | {row['chinese']} | {row['pinyin']} | 返修，详见逐项说明 |")
    lines += ['', '原静态审核只比对去声调拼音，账单的声调错误因此不会被它标出。'
              '词形缺失时也不能仅凭无匹配判断读音，行李提取的 xing2 li5 是正确读法。', '',
              '## 300项结论', '',
              '| 序号 | 英文 | 结论 | 主义项 | 逐义项结论 | 理由 |',
              '| --- | --- | --- | --- | --- | --- |']
    for r in reviewed:
        primary = next((s['chinese'] for s in r['senses'] if s['selected_as_primary']), '—')
        verdicts = '；'.join(f"{i}.{s['chinese']}：{LABELS[s['verdict']]}" for i, s in enumerate(r['senses'], 1))
        lines.append('| ' + ' | '.join(cell(x) for x in (
            r['row'], r['english'], LABELS[r['verdict']], primary, verdicts, r['note'])) + ' |')
    lines += ['', '## 585个义项明细', '',
              '| 序号 | 英文 | 中文 | 拼音 | 英文词性 | 原义项说明 | 结论 | 基础词库读音命中 |',
              '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in reviewed:
        for i, s in enumerate(r['senses'], 1):
            lines.append('| ' + ' | '.join(cell(x) for x in (
                f"{r['row']}.{i}", r['english'], s['chinese'], s['pinyin'], s['pos'],
                s['meaning_zh'], LABELS[s['verdict']], '是' if s['base_reading_present'] else '否')) + ' |')
    legacy.atomic_write(batch / 'review.md', ('\n'.join(lines) + '\n').encode('utf-8'))
    require(verify_protected(meta) == protected, 'Protected source verification failed after render')
    return summary


if __name__ == '__main__':
    import json
    print(json.dumps(render(), ensure_ascii=False, indent=2))
