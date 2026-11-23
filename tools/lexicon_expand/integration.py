"""Integrate explicitly selected reviews into a separate, reproducible snapshot.

No generation, packaging, installation, or historical-review mutations occur.
An authored plan, routes, and default choices are required; spelling equality
alone never authorizes merging meanings.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import io
from pathlib import Path

from tools.lexicon import pipeline as legacy
from tools.lexicon_expand.adoption import identity
from tools.lexicon_expand.catalog import input_reading
from tools.lexicon_expand.common import (
    ROOT, canonical, digest, read_json, read_jsonl, require, write_json, write_jsonl,
)
from tools.lexicon_expand.quality_v3 import require_pronunciation_review
from tools.lexicon_expand.review_pilot import dictionary_readings
from tools.lexicon_expand.runtime import (
    choices_from_tsv, compile_model, lua_bytes, supplement_dictionary, trigger_additions,
)


class EvidenceIndex:
    """Resolve original records, decisions and response bytes against a freeze."""

    def __init__(self, manifest):
        self.files = manifest['files']
        self.used = {}
        self._raw_cache = {}
        self.records = defaultdict(list)
        self.packets = defaultdict(list)
        self.decisions = defaultdict(list)
        self.by_sha = defaultdict(list)
        for name, info in self.files.items():
            self.by_sha[info['sha256']].append(name)
            if '/history/' in name or '/handoffs/' in name:
                continue
            path = Path(name)
            if path.name.endswith('drafts.jsonl'):
                for line, row in enumerate(self.jsonl(name), 1):
                    if 'senses' in row:
                        self.records[digest(canonical(row))].append((name, line, row))
            if path.name.endswith(('review-packet.json', 'evaluation-decisions.json')):
                document = self.json(name)
                rows = document.get('items', []) if isinstance(document, dict) else []
                if not isinstance(rows, list):
                    continue
                index = self.packets if path.name.endswith('review-packet.json') else self.decisions
                for number, row in enumerate(rows):
                    if 'packet_id' in row:
                        index[row['packet_id']].append((name, number, row))
            if path.name == 'devote-adjudication.json':
                document = self.json(name)
                row = document['current_decision']
                self.decisions[row['packet_id']].append((name, 'current_decision', row))

    def raw(self, name):
        name = Path(name).as_posix()
        require(name in self.files, 'Unfrozen evidence file: ' + name)
        if name in self._raw_cache:
            return self._raw_cache[name]
        raw = (ROOT / name).read_bytes()
        sha = digest(raw)
        require(sha == self.files[name]['sha256'], 'Frozen evidence changed: ' + name)
        self.used[name] = sha
        self._raw_cache[name] = raw
        return raw

    def json(self, name):
        import json
        return json.loads(self.raw(name).decode('utf-8-sig'), object_pairs_hook=legacy.unique_keys)

    def jsonl(self, name):
        import json
        return [json.loads(line, object_pairs_hook=legacy.unique_keys)
                for line in self.raw(name).decode('utf-8-sig').splitlines() if line.strip()]

    def binding(self, name, **locator):
        self.raw(name)
        return {'path': name, 'sha256': self.files[name]['sha256'], **locator}

    @staticmethod
    def preferred(locations):
        # Prefer the original per-batch archive over a combined/current index.
        return sorted(locations, key=lambda x: ('combined-' in x[0], '/history/' in x[0], len(x[0]), x[0]))[0]

    def bind_candidate(self, source, index_path, line):
        sense, decision, pid = source['candidate'], source['decision'], source['packet_id']
        sha = digest(canonical(sense))
        require(sha == source['candidate_sha256'] == decision['candidate_sha256'],
                'Candidate/review hash mismatch: ' + pid)
        require(decision['decision'] == 'accepted' and bool(decision['reason'].strip()),
                'Nonaccepted or unexplained source: ' + pid)
        require_pronunciation_review(sense, decision)
        records = self.records[source['source_record_sha256']]
        require(records, 'Original source record absent: ' + pid)
        record_path, record_line, record = self.preferred(records)
        require(sense in record['senses'] and record['id'] == source['target_id'],
                'Source candidate/target differs from archived draft: ' + pid)
        require(record['generation'] == source['generation'], 'Generation provenance differs: ' + pid)
        packets = [p for p in self.packets[pid]
                   if p[2].get('candidate') == sense and p[2].get('candidate_sha256') == sha]
        decisions = [d for d in self.decisions[pid] if d[2] == decision]
        require(packets and decisions, 'Original review or current adjudication absent: ' + pid)
        packet_path, packet_number, _ = self.preferred(packets)
        decision_path, decision_number, _ = self.preferred(decisions)
        generation = source['generation']
        response_sha = generation.get('response_sha256', generation.get('raw_response_sha256'))
        responses = self.by_sha[response_sha]
        require(responses, 'Original response bytes absent: ' + pid)
        response_path = sorted(responses, key=lambda x: ('/history/' in x, '/inbox/' in x, len(x), x))[0]
        links = {
            'selected_index': self.binding(index_path, line=line, row_sha256=digest(canonical(source))),
            'original_draft': self.binding(record_path, line=record_line,
                                           record_sha256=source['source_record_sha256']),
            'review_packet': self.binding(packet_path, item_index=packet_number, packet_id=pid),
            'semantic_decision': self.binding(decision_path, item_index=decision_number,
                                              decision_sha256=digest(canonical(decision))),
            'original_response': self.binding(response_path),
        }
        # Explicitly link prior drafts/packets named by repair/followup ancestry.
        previous_records, previous_packets = set(), set()

        def inspect(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == 'source_record_sha256' and isinstance(child, str) and child in self.records:
                        previous_records.add(child)
                    if key.endswith('packet_id') and isinstance(child, str) and child in self.packets:
                        previous_packets.add(child)
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)

        for field in ('repair_of', 'repair_context', 'source_binding', 'followup_context', 'supersedes_in_current_view'):
            inspect(source.get(field))
        ancestry = []
        for previous in sorted(previous_records):
            path, number, _ = self.preferred(self.records[previous])
            ancestry.append(self.binding(path, line=number, record_sha256=previous))
        for previous in sorted(previous_packets):
            path, number, row = self.preferred(self.packets[previous])
            ancestry.append(self.binding(path, item_index=number, packet_id=previous,
                                          candidate_sha256=row.get('candidate_sha256')))
        return {**source, '_integration': {'bindings': links, 'ancestry': ancestry,
                                          'packs': source.get('packs', record.get('packs', []))}}


def retained_legacy(baseline, baseline_model, validation):
    """Keep precisely the legacy fallbacks present before this integration."""
    words = {zh for zh, entry in baseline_model['entries'].items()
             if any(s['id'].startswith('legacy-') for s in entry['senses'])}
    rows = []
    for row in validation.entries:
        if row['chinese'] in words and row['review']['status'] != 'rejected':
            pinyin = validation.sources[row['source_entry_sha256']]['pinyin'].lower().replace('u:', 'v')
            rows.append({**row, 'pinyin': pinyin})
    require({r['chinese'] for r in rows} == words, 'Missing preexisting runtime fallback')
    return rows


def load_sources(output):
    output = Path(output)
    plan = read_json(output / 'integration-plan.json')
    evidence = EvidenceIndex(read_json(output / 'history/initial-input-manifest.json'))
    sources, inventory, seen = [], [], {}
    for spec in plan['sources']:
        rows = evidence.jsonl(spec['path'])
        require(len(rows) == spec['expected_records'], 'Selected source count changed: ' + spec['path'])
        added = 0
        for line, source in enumerate(rows, 1):
            bound = evidence.bind_candidate(source, spec['path'], line)
            pid = source['packet_id']
            if pid in seen:
                require(source['candidate'] == seen[pid]['candidate'] and source['decision'] == seen[pid]['decision'],
                        'Conflicting repeated source identity: ' + pid)
                continue
            seen[pid] = bound
            sources.append(bound)
            added += 1
        inventory.append({**spec, 'sha256': evidence.files[spec['path']]['sha256'],
                          'unique_source_candidates': added, 'index_references_only': len(rows) - added})
    for name in plan.get('context_files', []):
        evidence.raw(name)
    require(len(sources) == plan['expected_unique_source_candidates'], 'Incomplete selected-source inventory')
    return sources, inventory, evidence


def resolve_routes(baseline, sources, routes):
    by_source = {s['packet_id']: s for s in sources}
    by_baseline = {s['id']: s for s in baseline}
    require(len(by_source) == len(sources) and len(by_baseline) == len(baseline), 'Repeated source/baseline ID')
    authored = {r['packet_id']: r for r in routes}
    require(len(authored) == len(routes) == len(sources) and set(authored) == set(by_source),
            'Every selected candidate needs exactly one adoption route')
    selected, provenance = {}, defaultdict(list)
    for pid, route in authored.items():
        source = by_source[pid]
        sense = source['candidate']
        require(source['decision']['decision'] == 'accepted', 'Nonaccepted source reached adoption')
        require(route['candidate_sha256'] == source['candidate_sha256'] ==
                source['decision']['candidate_sha256'] == digest(canonical(sense)),
                'Stale adoption candidate: ' + pid)
        require(route['reason'].strip(), 'Unexplained adoption route')
        action, destination = route['action'], route['destination']
        require(action in {'adopt', 'adopt-search-alias', 'merge-reviewed-version', 'already-in-baseline'},
                'Unknown adoption route')
        if action == 'already-in-baseline':
            require(destination in by_baseline and identity(sense) == identity(by_baseline[destination]),
                    'Baseline merge changes an input, English spelling, or part of speech')
        elif action == 'merge-reviewed-version':
            require(destination != pid and destination in by_source and
                    identity(sense) == identity(by_source[destination]['candidate']),
                    'Version merge changes an input, English spelling, or part of speech')
            require(route.get('semantic_adjudication'), 'Version merge needs an explicit meaning adjudication')
        else:
            require(destination == pid, 'Adoption must preserve its own candidate content')
            require(sense.get('id', 'sense-' + pid) not in by_baseline, 'New sense ID collides with baseline')
            selected[pid] = source
        provenance[destination].append({'route': route, 'source': source})
    for pid, route in authored.items():
        if route['action'] == 'merge-reviewed-version':
            require(route['destination'] in selected, 'Version merge destination is not adopted')
        if route['action'] == 'adopt-search-alias':
            anchor = route['semantic_anchor']
            require(anchor in by_baseline or anchor in selected, 'Alias anchor is not retained')
            target = by_baseline[anchor] if anchor in by_baseline else selected[anchor]['candidate']
            source = by_source[pid]['candidate']
            require((source['commit_english'], source['pos']) == (target['commit_english'], target['pos']),
                    'Chinese alias must keep the same complete English and part of speech')
            require(source['chinese'] != target['chinese'], 'Alias must provide another Chinese entry')
    new = []
    # Source-order output is stable and keeps the independently scoped followup IDs.
    for source in sources:
        pid = source['packet_id']
        if pid not in selected:
            continue
        route = authored[pid]
        new.append({**source['candidate'], 'id': source['candidate'].get('id', 'sense-' + pid),
                    'verdict': 'accepted',
                    'english': source['english'], 'target_id': source['target_id'],
                    'original_target_id': source.get('original_target_id', source['target_id']),
                    'packs': source.get('_integration', {}).get('packs', source.get('packs', [])),
                    'reason': source['decision']['reason'], 'reviewer': 'Codex',
                    'method': 'user-delegated-agent-semantic-review',
                    'adoption_packet_id': pid, 'adoption': route,
                    'provenance': provenance[pid], 'human_approved': False, 'release_ready': False})
    require(len({s['id'] for s in new}) == len(new), 'Adopted sense IDs collide')
    return baseline + new, dict(provenance)


def reading_rows(accepted, legacy_rows, dictionary_keys):
    groups = {}
    for source, rows in (('reviewed-expansion', accepted), ('retained-legacy-preview', legacy_rows)):
        for row in rows:
            code = input_reading(row['chinese'], row['pinyin'])
            require(code is not None, 'Invalid complete reading')
            key = row['chinese'], code
            group = groups.setdefault(key, {'chinese': key[0], 'code': key[1], 'numbered_readings': [],
                                            'sense_ids': [], 'sources': [],
                                            'in_pinned_dictionary': key in dictionary_keys})
            if row['pinyin'] not in group['numbered_readings']:
                group['numbered_readings'].append(row['pinyin'])
            sid = row['id'] if source == 'reviewed-expansion' else 'legacy-' + str(row['id'])
            group['sense_ids'].append(sid)
            group['sources'].append({'sense_id': sid, 'kind': source,
                                     'adoption_packet_id': row.get('adoption_packet_id')})
    return [groups[key] for key in sorted(groups)]


def default_value(entry, code=None):
    sid = entry['primary_by_reading'].get(code, entry['primary_sense_id']) if code is not None else entry['primary_sense_id']
    return next(s['commit_english'] for s in entry['senses'] if s['id'] == sid)


def build(output, *, source_loader=load_sources):
    output = Path(output).resolve()
    plan = read_json(output / 'integration-plan.json')
    baseline_dir = ROOT / plan['baseline_directory']
    require(output != baseline_dir.resolve(), 'A separate snapshot directory is required')
    baseline_raw = (baseline_dir / 'accepted-senses.jsonl').read_bytes()
    require(digest(baseline_raw) == plan['baseline_sha256'], 'Baseline bytes changed')
    require(baseline_raw.endswith(b'\n'), 'Baseline must end with a record delimiter')
    baseline = read_jsonl(baseline_dir / 'accepted-senses.jsonl')
    require(len(baseline) == plan['baseline_records'], 'Baseline count changed')
    old_raw = (ROOT / plan['older_baseline_path']).read_bytes()
    require(baseline_raw.startswith(old_raw), 'Older baseline byte prefix changed')
    sources, inventory, evidence = source_loader(output)
    routes_document = read_json(output / 'adoption-decisions.json')
    accepted, provenance = resolve_routes(baseline, sources, routes_document['items'])
    validation = legacy.validate()
    old_model = read_json(baseline_dir / 'runtime-model.json')
    fallbacks = retained_legacy(baseline, old_model, validation)
    choices = choices_from_tsv(output / 'primary-choices.tsv')
    enriched_legacy = [{**r, 'pinyin': validation.sources[r['source_entry_sha256']]['pinyin'].lower().replace('u:', 'v')}
                       for r in validation.entries]
    model = compile_model(accepted, choices, enriched_legacy,
                          retain_legacy_words={r['chinese'] for r in fallbacks})
    dictionary_keys, _, _, dictionary_sha = dictionary_readings()
    additions = trigger_additions(accepted, dictionary_keys)
    old_additions = read_jsonl(baseline_dir / 'trigger-additions.jsonl')
    old_keys = {(r['chinese'], r['code']) for r in old_additions}
    require(old_keys <= {(r['chinese'], r['code']) for r in additions}, 'Lost a baseline supplemental reading')
    readings = reading_rows(accepted, fallbacks, dictionary_keys)
    baseline_readings = reading_rows(baseline, fallbacks, dictionary_keys)
    compatibility = []
    for row in baseline_readings:
        zh, code = row['chinese'], row['code']
        before, after = old_model['entries'][zh], model['entries'][zh]
        compatibility.append({'chinese': zh, 'code': code,
                              'before': default_value(before, code), 'after': default_value(after, code),
                              'old_values_preserved': {s['commit_english'] for s in before['senses']} <=
                                                     {s['commit_english'] for s in after['senses']}})
    require(all(r['before'] == r['after'] and r['old_values_preserved'] for r in compatibility),
            'A preexisting runtime default or option was lost')
    new = accepted[len(baseline):]
    legacy.atomic_write(output / 'accepted-senses.jsonl', baseline_raw + b''.join(canonical(s) + b'\n' for s in new))
    write_jsonl(output / 'new-accepted-senses.jsonl', new)
    write_jsonl(output / 'accepted-source-candidates.jsonl', sources)
    write_json(output / 'source-inventory.json', {'items': inventory, 'unique_candidates': len(sources)})
    write_json(output / 'adoption-provenance.json', provenance)
    write_jsonl(output / 'trigger-additions.jsonl', additions)
    write_jsonl(output / 'new-trigger-additions.jsonl',
                [r for r in additions if (r['chinese'], r['code']) not in old_keys])
    write_jsonl(output / 'all-trigger-readings.jsonl', readings)
    write_jsonl(output / 'retained-legacy-runtime.jsonl', fallbacks)
    write_json(output / 'baseline-compatibility.json', {
        'all_defaults_preserved': True, 'all_old_runtime_options_preserved': True,
        'retained_legacy_preview_entries': len(fallbacks), 'checks': compatibility})
    write_json(output / 'runtime-model.json', model)
    from tools.dictionary.cedict import files as dictionary_files
    dictionary = dictionary_files()['cedict_study.dict.yaml']
    preview = output / 'runtime-preview'
    legacy.atomic_write(preview / 'lua/lexicon.lua', lua_bytes(model))
    legacy.atomic_write(preview / 'cedict_study.dict.yaml', supplement_dictionary(dictionary, additions))
    write_json(output / 'source-bindings.json', {
        'schema_version': 1, 'verified_source_candidates': len(sources),
        'frozen_consumed_inputs': evidence.used,
        'review_decisions_and_original_response_bytes_verified': True,
        'generation_calls': 0})
    old_choices = choices_from_tsv(baseline_dir / 'primary-choices.tsv')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=['chinese', 'english', 'reason'], delimiter='\t', lineterminator='\n')
    writer.writeheader()
    writer.writerows(v for k, v in choices.items() if k not in old_choices)
    legacy.atomic_write(output / 'new-primary-choices.tsv', stream.getvalue().encode('utf-8'))
    outputs = ['accepted-senses.jsonl', 'new-accepted-senses.jsonl', 'accepted-source-candidates.jsonl',
               'source-inventory.json', 'adoption-provenance.json', 'trigger-additions.jsonl',
               'new-trigger-additions.jsonl', 'all-trigger-readings.jsonl', 'retained-legacy-runtime.jsonl',
               'baseline-compatibility.json', 'runtime-model.json', 'source-bindings.json',
               'primary-choices.tsv', 'new-primary-choices.tsv', 'adoption-decisions.json',
               'semantic-relations.json', 'default-decisions.json', 'integration-plan.json',
               'runtime-preview/lua/lexicon.lua', 'runtime-preview/cedict_study.dict.yaml']
    summary = {
        'schema_version': 1, 'client_date': plan['client_date'],
        'status': 'reviewed-development-data-snapshot', 'baseline_records': len(baseline),
        'source_candidates': len(sources), 'adoption_routes': dict(Counter(r['action'] for r in routes_document['items'])),
        'new_adopted_records': len(new), 'accepted_records': len(accepted),
        'chinese_search_alias_records_added': sum(r['action'] == 'adopt-search-alias' for r in routes_document['items']),
        'unique_expansion_chinese_entries': len({r['chinese'] for r in accepted}),
        'runtime_chinese_entries': len(model['entries']), 'runtime_trigger_readings': len(readings),
        'total_supplemental_readings': len(additions), 'new_supplemental_readings': len(additions) - len(old_keys),
        'explicit_default_choices': len(choices), 'new_explicit_default_choices': len(choices) - len(old_choices),
        'baseline_byte_prefix_preserved': True, 'older_baseline_byte_prefix_preserved': True,
        'baseline_runtime_defaults_preserved': True, 'runtime_data_compiles': True,
        'distinct_english_meaning_count_claimed': False,
        'native_validation_report': 'validation/runtime-report.json',
        'dictionary_source_sha256': dictionary_sha, 'base_rime_dictionary_sha256': digest(dictionary),
        'generation_calls': 0, 'packaging_deferred': True, 'human_approved': False, 'release_ready': False,
        'build_tools': {name: digest((ROOT / name).read_bytes()) for name in
                        ['tools/lexicon_expand/integration.py', 'tools/lexicon_expand/runtime.py',
                         'tools/lexicon_expand/catalog.py', 'tools/lexicon_expand/common.py']},
        'authored_decisions_script_sha256': digest((output / 'author-integration.local.py').read_bytes()),
        'artifacts': {name: digest((output / name).read_bytes()) for name in outputs},
    }
    write_json(output / 'summary.json', summary)
    return summary


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.snapshot), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
