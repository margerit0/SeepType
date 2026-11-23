"""Compile reviewed senses and explicit common-sense choices for offline Rime."""
from __future__ import annotations

from collections import defaultdict
import csv
import json

from tools.lexicon_expand.catalog import input_reading
from tools.lexicon_expand.common import canonical, digest, english, require


def choices_from_tsv(path):
    with path.open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    result = {}
    for row in rows:
        require(set(row) == {'chinese', 'english', 'reason'} and row['reason'].strip(),
                'Invalid common-sense choice')
        require(row['chinese'] not in result, 'Duplicate common-sense choice')
        result[row['chinese']] = row
    return result


def compile_model(accepted, choices, legacy_entries=(), *, retain_legacy_words=()):
    groups = defaultdict(list)
    seen = set()
    for row in accepted:
        require(row['id'] not in seen, 'Repeated accepted sense ID')
        seen.add(row['id'])
        require(row['verdict'] == 'accepted', 'Unaccepted sense reached runtime compiler')
        require(row['display_english'] == row['commit_english'], 'Display/commit mismatch')
        english(row['commit_english'])
        require(input_reading(row['chinese'], row['pinyin']) is not None, 'Invalid trigger reading')
        groups[row['chinese']].append(row)
    expansion_words = set(groups)
    retain_legacy_words = set(retain_legacy_words)
    for row in legacy_entries:
        # A later expansion may share a Chinese trigger with an older runtime
        # fallback. Explicit retention keeps that old option/default available
        # without reclassifying the legacy preview as a newly approved sense.
        if (row['chinese'] not in expansion_words or row['chinese'] in retain_legacy_words) and row['review']['status'] != 'rejected':
            groups[row['chinese']].append({**row, 'id': 'legacy-' + str(row['id'])})
    entries = {}
    used_choices = set()
    for zh, senses in sorted(groups.items()):
        values = {s['commit_english'] for s in senses}
        by_reading = defaultdict(list)
        for sense in senses:
            code = input_reading(zh, sense['pinyin']) if 'pinyin' in sense else ''
            by_reading[code].append(sense)
        ambiguous = any(len({s['commit_english'] for s in group}) > 1 for group in by_reading.values())
        if ambiguous:
            require(zh in choices, f'Explicit common-sense choice required: {zh}')
            chosen = choices[zh]['english']
            require(chosen in values, f'Chosen English is not accepted: {zh}')
            used_choices.add(zh)
            reason = choices[zh]['reason']
        else:
            chosen = senses[0]['commit_english']
            reason = ('该中文全部保留义项的英文提交值一致。' if len(values) == 1 else
                      '不同读音各自对应已通过的英文，按真实候选读音选择。')
        primary_by_reading = {}
        selected_values = set()
        for code, group in by_reading.items():
            group_values = {s['commit_english'] for s in group}
            value = chosen if len(group_values) > 1 else group[0]['commit_english']
            require(value in group_values, f'Common-sense choice does not cover this reading: {zh}/{code}')
            primary_by_reading[code] = next(s['id'] for s in group if s['commit_english'] == value)
            selected_values.add(value)
        primary = next(s['id'] for s in senses if s['commit_english'] == chosen)
        entries[zh] = {'primary_sense_id': primary, 'selection_reason': reason,
                       'primary_by_reading': primary_by_reading,
                       'requires_reading': len(selected_values) > 1,
                       'senses': [{k: s[k] for k in ('id', 'display_english', 'commit_english')}
                                  for s in senses]}
    require(set(choices) == used_choices, 'Stale or unnecessary common-sense choice')
    return {'schema_version': 2, 'interaction': 'one-explicit-common-sense-per-Chinese-candidate',
            'entries': entries}


def lua_bytes(model):
    quote = lambda v: json.dumps(v, ensure_ascii=False)
    lines = ['-- Development preview; delegated semantic review is not distribution approval.',
             '-- Full sense/source/review records accompany this file.',
             'return {schema_version = 2, entries = {']
    for zh, entry in model['entries'].items():
        options = f'primary_sense_id = {quote(entry["primary_sense_id"])}'
        if entry['requires_reading']:
            mapping = ', '.join(f'[{quote(code)}] = {quote(sid)}' for code, sid in entry['primary_by_reading'].items())
            options += f', requires_reading = true, primary_by_reading = {{{mapping}}}'
        lines.append(f'  [{quote(zh)}] = {{{options}, senses = {{')
        for sense in entry['senses']:
            lines.append('    {' + ', '.join(f'{key} = {quote(value)}' for key, value in sense.items()) + '},')
        lines.append('  }},')
    lines.append('}}')
    return ('\n'.join(lines) + '\n').encode('utf-8')


def trigger_additions(accepted, readings):
    missing = {}
    for row in accepted:
        key = row['chinese'], input_reading(row['chinese'], row['pinyin'])
        require(key[1] is not None, 'Invalid accepted trigger reading')
        if key not in readings:
            entry = missing.setdefault(key, {'chinese': key[0], 'code': key[1],
                                           'pinyin': row['pinyin'], 'sense_ids': []})
            entry['sense_ids'].append(row['id'])
    return [missing[key] for key in sorted(missing)]


def supplement_dictionary(base, additions):
    require(base.endswith(b'\n'), 'Dictionary must end with newline')
    rows = ''.join(f"{r['chinese']}\t{r['code']}\t100\n" for r in additions).encode('utf-8')
    return base + b'# Reviewed expansion Chinese triggers; provenance in expansion manifest.\n' + rows
