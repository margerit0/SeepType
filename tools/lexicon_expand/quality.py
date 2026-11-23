"""Versioned pronunciation/case checks, separate from semantic approval."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re

from tools.lexicon import pipeline as legacy
from tools.lexicon_expand.catalog import input_reading
from tools.lexicon_expand.common import (
    CACHE, ROOT, digest, generated_directory, read_json, read_jsonl, require,
    word_key, write_json, write_jsonl,
)

QUALITY_VERSION = 1
LATEST_QUALITY_VERSION = 2
CONTEXT_RULE = 'Unlisted multi-character phrases require whole-phrase pronunciation review; never rewrite tones.'


@dataclass
class ReadingIndex:
    sha256: str
    words: dict
    characters: dict

    def check(self, chinese, pinyin, *, version=1):
        require(version in (1, 2), 'Unknown pronunciation policy version')
        syllables = pinyin.split(' ')
        valid_format = len(syllables) == len(chinese) and all(
            re.fullmatch('[a-z]+[1-5]', s) for s in syllables)
        readings = self.words.get(chinese, set())
        findings = []
        if not valid_format:
            findings.append({'code': 'pinyin-format', 'severity': 'blocked'})
        else:
            for char, syllable in zip(chinese, syllables):
                known = self.characters.get(char, set())
                if known and syllable not in known:
                    findings.append({'code': 'character-reading-conflict', 'severity': 'blocked',
                                     'character': char, 'given': syllable,
                                     'known_readings': sorted(known)})
                elif not known:
                    findings.append({'code': 'character-reading-unknown', 'severity': 'review',
                                     'character': char})
            if readings and pinyin not in readings and not any(
                    f['severity'] == 'blocked' for f in findings):
                findings.append({'code': 'word-reading-unconfirmed', 'severity': 'review',
                                 'known_readings': sorted(readings)})
        # Missing a complete phrase is an integration condition, never a bad translation.
        if not readings:
            findings.append({'code': 'missing-chinese-trigger', 'severity': 'integration'})
            if version >= 2 and valid_format and len(chinese) > 1:
                findings.append({'code': 'phrase-reading-unconfirmed', 'severity': 'review',
                                 'reason': 'Character readings do not establish contextual phrase pronunciation'})
        reachable = valid_format and any(
            input_reading(chinese, pinyin) == input_reading(chinese, r) for r in readings)
        return {'numbered_reading_present': pinyin in readings,
                'base_reading_present': bool(reachable), 'word_present': bool(readings),
                'findings': findings}


@lru_cache(maxsize=2)
def _load_index(path, mtime_ns, size, expected_sha):
    raw = Path(path).read_bytes()
    require(digest(raw) == expected_sha, 'Quality dictionary snapshot changed')
    words, characters = defaultdict(set), defaultdict(set)
    for line in raw.decode('utf-8-sig').splitlines():
        if not line or line.startswith('#'):
            continue
        entry = legacy.parse_source(line)
        chinese = entry['chinese']
        pinyin = entry['pinyin'].lower().replace('u:', 'v')
        syllables = pinyin.split(' ')
        if len(chinese) != len(syllables) or not all(re.fullmatch('[a-z]+[1-5]', s) for s in syllables):
            continue
        words[chinese].add(pinyin)
        for char, syllable in zip(chinese, syllables):
            characters[char].add(syllable)
    return ReadingIndex(expected_sha, dict(words), dict(characters))


def reading_index():
    artifact = read_json(ROOT / 'data/lexicon/source.lock.json')['artifact']
    path = ROOT / '.cache/dictionaries/cc-cedict' / (artifact['archive_sha256'] + '.txt')
    stat = path.stat()
    return _load_index(str(path), stat.st_mtime_ns, stat.st_size, artifact['text_sha256'])


def policy(version=QUALITY_VERSION):
    require(type(version) is int and version in (1, 2), 'Unknown quality policy version')
    value = {'version': version, 'dictionary_sha256': reading_index().sha256}
    if version >= 2:
        value['rules_sha256'] = digest(CONTEXT_RULE.encode('utf-8'))
    return value


def check_sense(sense, target, index=None, *, version=QUALITY_VERSION):
    index = reading_index() if index is None else index
    result = index.check(sense['chinese'], sense['pinyin'], version=version)
    forms = target.get('source_forms', [])
    value = sense['commit_english']
    matching_forms = sorted({f for f in forms if word_key(f) == word_key(value)})
    if matching_forms and value not in matching_forms:
        # Source capitalization can be ambiguous (States/states): never title-case blindly.
        result['findings'].append({'code': 'source-case-unconfirmed', 'severity': 'review',
                                   'source_forms': matching_forms})
    severities = {f['severity'] for f in result['findings']}
    result.update(version=version, dictionary_sha256=index.sha256,
                  disposition='blocked' if 'blocked' in severities else
                              'review-required' if 'review' in severities else 'checks-passed',
                  semantic_review='pending')
    return result


def audit_records(records, targets, index=None, *, version=QUALITY_VERSION):
    index = reading_index() if index is None else index
    queue, additions = [], {}
    for record in records:
        target = targets.get(record['id'], targets.get(record.get('repair_of', {}).get('target_id'), {}))
        for sense in record['senses']:
            checks = check_sense(sense, target, index, version=version)
            queue.append({'target_id': record['id'], 'sense_id': sense['id'],
                          'english': sense['commit_english'], 'chinese': sense['chinese'],
                          'pinyin': sense['pinyin'], 'quality': checks})
            if not checks['base_reading_present'] and checks['disposition'] != 'blocked':
                key = (sense['chinese'], sense['pinyin'])
                addition = additions.setdefault(key, {'chinese': key[0], 'pinyin': key[1],
                    'pronunciation_review_required': not checks['numbered_reading_present'],
                    'sense_ids': [], 'status': 'proposed-not-imported'})
                addition['sense_ids'].append(sense['id'])
    counts = Counter(f['code'] for r in queue for f in r['quality']['findings'])
    summary = {'items': len(records), 'senses': len(queue),
               'dispositions': dict(Counter(r['quality']['disposition'] for r in queue)),
               'findings': dict(counts), 'quality_policy': {'version': version, 'dictionary_sha256': index.sha256},
               'proposed_trigger_additions': len(additions),
               'semantic_approvals': 0, 'runtime_imported_items': 0, 'release_ready': False}
    if version >= 2:
        summary['quality_policy']['rules_sha256'] = digest(CONTEXT_RULE.encode('utf-8'))
    return summary, queue, list(additions.values())


def audit_file(drafts, output, prepared=CACHE / 'prepared', *, version=QUALITY_VERSION):
    output = generated_directory(output)
    require(not Path(drafts).resolve().is_relative_to(output), 'Keep audit output separate from input')
    targets = {r['id']: r for r in read_jsonl(Path(prepared) / 'targets.jsonl')}
    summary, queue, additions = audit_records(read_jsonl(drafts), targets, version=version)
    write_json(output / 'quality-summary.json', summary)
    write_jsonl(output / 'quality-queue.jsonl', queue)
    write_jsonl(output / 'trigger-additions.jsonl', additions)
    return summary
