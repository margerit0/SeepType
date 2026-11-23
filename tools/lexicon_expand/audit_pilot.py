"""Build a review queue from API drafts without changing any translations."""
from collections import Counter, defaultdict
from tools.lexicon import pipeline as legacy
from tools.lexicon_expand.catalog import input_reading
from tools.lexicon_expand.common import CACHE, ROOT, digest, read_jsonl, require
from tools.lexicon_expand.storage import write_json, write_jsonl


def audit():
    directory = CACHE / 'pilot-results-combined'
    records = read_jsonl(directory / 'drafts.jsonl')
    targets = {r['id']: r for r in read_jsonl(CACHE / 'prepared/targets.jsonl')}
    lexicon = legacy.validate()
    artifact = lexicon.lock['artifact']
    source = ROOT / '.cache/dictionaries/cc-cedict' / (artifact['archive_sha256'] + '.txt')
    raw = source.read_bytes()
    require(digest(raw) == artifact['text_sha256'], 'Dictionary snapshot changed')
    readings = set()
    for line in raw.decode('utf-8-sig').splitlines():
        if line and not line.startswith('#'):
            parsed = legacy.parse_source(line)
            code = input_reading(parsed['chinese'], parsed['pinyin'])
            if code is not None:
                readings.add((parsed['chinese'], code))
    headwords = {word for word, _ in readings}
    english_ids, trigger_english = defaultdict(set), defaultdict(set)
    for record in records:
        if record['english']:
            english_ids[record['english'].casefold()].add(record['id'])
        for sense in record['senses']:
            trigger_english[sense['chinese']].add(record['english'])
    queue = []
    for record in records:
        require(record['review']['status'] == 'pending' and record['selected_sense_id'] is None,
                'Audit expects untouched pending drafts')
        for sense in record['senses']:
            code = input_reading(sense['chinese'], sense['pinyin'])
            flags = []
            forms = targets.get(record['id'], {}).get('source_forms', [])
            if forms and record['english'] not in forms and any(
                    form.casefold() == record['english'].casefold() and form != form.lower() for form in forms):
                flags.append('source-capitalization-differs')
            if sense['chinese'] not in headwords:
                flags.append('missing-chinese-trigger')
            elif (sense['chinese'], code) not in readings:
                flags.append('reading-not-in-base')
            if len(trigger_english[sense['chinese']]) > 1:
                flags.append('multiple-english-for-trigger')
            if len(english_ids[record['english'].casefold()]) > 1:
                flags.append('english-in-multiple-targets')
            queue.append({'target_id': record['id'], 'sense_id': sense['id'], 'english': record['english'],
                          'chinese': sense['chinese'], 'pinyin': sense['pinyin'], 'meaning_zh': sense['meaning_zh'],
                          'pos': sense['pos'], 'packs': record['packs'], 'flags': flags,
                          'base_reading_present': (sense['chinese'], code) in readings,
                          'model': record['generation']['requested_model'], 'review_status': 'pending'})
    counts = Counter(flag for row in queue for flag in row['flags'])
    summary = {'draft_items': len(records), 'senses': len(queue), 'base_reading_present_senses': sum(r['base_reading_present'] for r in queue),
               'flagged_senses': sum(bool(r['flags']) for r in queue), 'flags': dict(counts),
               'items_with_any_base_reading': len({r['target_id'] for r in queue if r['base_reading_present']}),
               'dictionary_sha256': artifact['text_sha256'], 'drafts_sha256': digest((directory / 'drafts.jsonl').read_bytes()),
               'human_approved_items': 0, 'release_ready': False,
               'limitations': ['Static dictionary comparison only; no native candidate/commit acceptance',
                              'Flags identify review priorities, not translation correctness',
                              'Shared triggers and repeated English may be valid across senses or packs']}
    write_json(directory / 'audit.json', summary)
    write_jsonl(directory / 'review-queue.jsonl', queue)
    rows = ['# 首批 API 草稿审核清单', '',
            f"{len(records)} 项，{len(queue)} 个义项；{summary['base_reading_present_senses']} 个义项的中文及无调拼音命中固定基础词库。", '',
            '所有内容均来自外部 API，仍待人工审核。命中基础词库不代表已导入、译文正确或实际候选验收通过。', '',
            '标记：missing-chinese-trigger＝基础库缺少中文词形；reading-not-in-base＝拼音未匹配；multiple-english-for-trigger＝同中文对应多个英文；english-in-multiple-targets＝跨目标英文重复；source-capitalization-differs＝大小写与源词表不同。', '',
            '| 目标 | 英文 | 中文 | 拼音 | 词性 | 义项说明 | 模型 | 检查标记 |',
            '| --- | --- | --- | --- | --- | --- | --- | --- |']
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    for row in sorted(queue, key=lambda r: (not bool(r['flags']), r['target_id'], r['sense_id'])):
        rows.append('| ' + ' | '.join(cell(x) for x in [row['target_id'], row['english'], row['chinese'], row['pinyin'], row['pos'], row['meaning_zh'], row['model'], ', '.join(row['flags'])]) + ' |')
    (directory / 'review.md').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    return summary


if __name__ == '__main__':
    import json
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
