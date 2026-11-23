"""Verify an explicitly bound development snapshot in the actual Rime/Lua engine.

All user directories, binaries and compiled dictionaries remain under a new
validation run. Alternate approved values are exercised with isolated default
overrides; those overrides never change the delivered default configuration.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time
import uuid

from tools.lexicon import pipeline as lex
from tools.lexicon_expand.common import ROOT, canonical, digest, read_json, read_jsonl, require, write_json
from tools.lexicon_expand.integration import default_value
from tools.lexicon_expand.runtime import lua_bytes
from tools.packaging.engine_client import EngineProbe
from tools.packaging.package import chinese_data, source_lock
from tools.packaging.verify_double_pinyin import SCHEMAS, encode_syllable


def alternative_layers(model, readings):
    """Select every other retained English value, only within its real reading."""
    layers = []
    for row in readings:
        entry = model['entries'][row['chinese']]
        senses = {s['id']: s for s in entry['senses']}
        values = {}
        for sid in row['sense_ids']:
            sense = senses[sid]
            if sense['commit_english'] != default_value(entry, row['code']):
                values.setdefault(sense['commit_english'], sid)
        for number, (value, sid) in enumerate(values.items()):
            while len(layers) <= number:
                layers.append({'model': copy.deepcopy(model), 'readings': [], 'overrides': []})
            layer = layers[number]
            selected = layer['model']['entries'][row['chinese']]
            selected['primary_by_reading'][row['code']] = sid
            if not selected['requires_reading']:
                selected['primary_sense_id'] = sid
            layer['readings'].append(row)
            layer['overrides'].append({'chinese': row['chinese'], 'code': row['code'],
                                       'sense_id': sid, 'english': value})
    return layers


def allowed_annotations(model):
    allowed = {}
    for zh, entry in model['entries'].items():
        allowed[zh] = ({default_value(entry, code) for code in entry['primary_by_reading']}
                       if entry['requires_reading'] else {default_value(entry)})
    return allowed


def exercise(probe, schema, row, model, allowed):
    zh, code = row['chinese'], row['code']
    syllables = code.split()
    encoded = syllables if schema == 'study' else [encode_syllable(s, schema) for s in syllables]
    query = ''.join(encoded)
    expected = default_value(model['entries'][zh], code)
    item = {'schema': schema, 'chinese': zh, 'code': code, 'numbered_readings': row['numbered_readings'],
            'input': query, 'expected_english': expected, 'passed': False,
            'checks_case': expected != expected.lower(), 'checks_full_phrase': ' ' in expected,
            'sense_ids': row['sense_ids']}
    try:
        try:
            page, index = probe.find(query, zh, pages=80)
        except ValueError as error:
            # The supported explicit syllable delimiter is recorded, never
            # silently replaced by a different Chinese word or pronunciation.
            if len(encoded) == 1:
                raise
            item['undelimited_lookup_error'] = str(error)
            query = "'".join(encoded)
            page, index = probe.find(query, zh, pages=80)
            item['input'] = query
        selected = page['candidates'][index]
        item.update(page=page['page'], candidate_index=index, candidate_page=page['candidates'],
                    selected_annotation=selected['comment'], load_state=page['load'])
        item['page_annotations_match'] = page['load'] == 'ready' and all(
            c['comment'] in allowed.get(c['text'], {''}) for c in page['candidates'])
        item['selected_annotation_matches'] = selected['comment'] == expected
        highlighted = probe.command('highlight ' + str(index))
        item['highlight_matches'] = highlighted['selected'] == index
        committed = probe.command('key 65293 5')
        item.update(actual_english_commit=committed['commit'], english_action=committed['action'],
                    input_after_english=committed['input'])
        item['english_commit_matches'] = (committed['commit'] == expected and committed['input'] == ''
                                           and committed['action'] == 'english-committed')
        _, index = probe.find(query, zh, pages=80)
        chinese = probe.command('choose ' + str(index))
        item.update(actual_chinese_commit=chinese['commit'], input_after_chinese=chinese['input'])
        item['chinese_commit_matches'] = chinese['commit'] == zh and chinese['input'] == ''
        item['passed'] = all(item[k] for k in ['page_annotations_match', 'selected_annotation_matches',
                                              'highlight_matches', 'english_commit_matches', 'chinese_commit_matches'])
    except ValueError as error:
        item['error'] = str(error)
    return item


def verify(snapshot, *, report_path=None):
    snapshot = Path(snapshot).resolve()
    summary = read_json(snapshot / 'summary.json')
    for name, expected in summary['artifacts'].items():
        require(digest((snapshot / name).read_bytes()) == expected, 'Snapshot artifact changed: ' + name)
    model = read_json(snapshot / 'runtime-model.json')
    readings = read_jsonl(snapshot / 'all-trigger-readings.jsonl')
    accepted = read_jsonl(snapshot / 'accepted-senses.jsonl')
    accepted_ids = {s['id'] for s in accepted}
    runtime_ids = {s['id'] for e in model['entries'].values() for s in e['senses']}
    require(accepted_ids <= runtime_ids, 'A retained approved option is missing from the runtime model')
    require(lua_bytes(model) == (snapshot / 'runtime-preview/lua/lexicon.lua').read_bytes(),
            'Snapshot Lua does not represent all retained model values')
    compatibility = read_json(snapshot / 'baseline-compatibility.json')
    baseline_triggers = {(r['chinese'], r['code']) for r in compatibility['checks']}
    plan = read_json(snapshot / 'integration-plan.json')
    old_model = read_json(ROOT / plan['baseline_directory'] / 'runtime-model.json')
    affected_baseline = {zh for zh, e in old_model['entries'].items()
                         if e['senses'] != model['entries'][zh]['senses']}
    layers = alternative_layers(model, readings)
    run = snapshot / 'validation/runs' / uuid.uuid4().hex
    runtime, shared, template = run / 'runtime', run / 'runtime/shared', run / 'runtime/user-template'
    executable, dll = runtime / 'bin/StudyIME.EngineProbe.exe', runtime / 'bin/rime.dll'
    files, chinese_provenance = chinese_data(source_lock())
    for name, raw in files.items():
        if name.startswith('data/shared/'):
            lex.atomic_write(shared / name[len('data/shared/'):], raw)
    lex.atomic_write(shared / 'cedict_study.dict.yaml', (snapshot / 'runtime-preview/cedict_study.dict.yaml').read_bytes())
    for schema in SCHEMAS:
        name = schema + '.schema.yaml'
        lex.atomic_write(shared / name, (ROOT / 'packaging/data' / name).read_bytes())
    for name in ('default.custom.yaml', 'rime.lua'):
        lex.atomic_write(template / name, (ROOT / 'packaging/data' / name).read_bytes())
    lex.atomic_write(template / 'lua/lexicon.lua', (snapshot / 'runtime-preview/lua/lexicon.lua').read_bytes())
    lex.atomic_write(template / 'lua/study_core.lua', (ROOT / 'src/study/lua/study_core.lua').read_bytes())
    lex.atomic_write(executable, (ROOT / '.cache/packaging/build/bin/StudyIME.EngineProbe.exe').read_bytes())
    lex.atomic_write(dll, (ROOT / '.cache/rime-build/dist/lib/rime.dll').read_bytes())
    rime_build = read_json(ROOT / '.cache/rime-build/rime-build.json')
    require(rime_build['binary']['sha256'] == digest(dll.read_bytes()), 'Rime binary differs from its source-build record')
    for name in ['.cache/rime-build/rime-build.json', '.cache/rime-build/source-tree.json',
                 'experiments/phase3/engine_probe.cpp', 'licensing/double-pinyin.lock.json',
                 'licensing/chinese-data.lock.json', 'data/lexicon/source.lock.json']:
        lex.atomic_write(runtime / 'evidence' / Path(name).name, (ROOT / name).read_bytes())
    write_json(runtime / 'evidence/chinese-provenance.json', chinese_provenance)
    initial_runtime_hashes = {p.relative_to(runtime).as_posix(): digest(p.read_bytes())
                              for p in sorted(runtime.rglob('*')) if p.is_file()}
    write_json(run / 'bound-runtime-inputs.json', initial_runtime_hashes)
    checks_path = run / 'checks.jsonl'
    checks, startups, failure = [], [], None
    started = time.monotonic()
    main_user = run / 'main-user'
    layer_specs = [{'name': 'delivered-defaults', 'model': model, 'readings': readings,
                    'overrides': [], 'user': main_user}]
    layer_specs += [{**layer, 'name': f'alternative-defaults-{i:02}', 'user': run / f'option-{i:02}-user'}
                    for i, layer in enumerate(layers, 1)]
    print(json.dumps({'status': 'starting-real-engine', 'run': str(run), 'default_triggers': len(readings),
                      'alternative_values': sum(len(s['readings']) for s in layers),
                      'expected_checks': sum(len(s['readings']) for s in layer_specs) * len(SCHEMAS)}, ensure_ascii=False), flush=True)
    with checks_path.open('wb') as record_stream:
        try:
            for spec in layer_specs:
                user = spec['user']
                shutil.copytree(template, user)
                if user != main_user and (main_user / 'build').exists():
                    shutil.copytree(main_user / 'build', user / 'build')
                lex.atomic_write(user / 'lua/lexicon.lua', lua_bytes(spec['model']))
                write_json(user / 'default-overrides.json', spec['overrides'])
                allowed = allowed_annotations(spec['model'])
                probe = None
                try:
                    probe = EngineProbe(executable, dll, shared, user)
                    startup = probe.receive(timeout=60)
                    require(startup.get('lua_module') and startup.get('pointer_bits') == 64,
                            'Expected actual x64 Rime with Lua')
                    startups.append({'layer': spec['name'], **startup,
                                     'lexicon_lua_sha256': digest((user / 'lua/lexicon.lua').read_bytes())})
                    for schema in SCHEMAS:
                        probe.command('schema ' + schema)
                        probe.command('user_learning 0')
                        probe.command('option learning_mode 1')
                        probe.command('option ascii_mode 0')
                        probe.command('option full_shape 0')
                        for number, row in enumerate(spec['readings'], 1):
                            item = exercise(probe, schema, row, spec['model'], allowed)
                            item.update(layer=spec['name'],
                                        baseline_trigger=(row['chinese'], row['code']) in baseline_triggers,
                                        affected_baseline=row['chinese'] in affected_baseline)
                            checks.append(item)
                            record_stream.write(canonical(item) + b'\n')
                            if number % 200 == 0 or not item['passed'] or number == len(spec['readings']):
                                record_stream.flush()
                                print(json.dumps({'layer': spec['name'], 'schema': schema, 'checked': number,
                                                  'total': len(spec['readings']),
                                                  'failures': sum(not c['passed'] for c in checks)}, ensure_ascii=False), flush=True)
                            require(sum(not c['passed'] for c in checks) < 20, 'Stopped after 20 failures; inspect this run')
                finally:
                    if probe:
                        probe.close()
                require(all(c['passed'] for c in checks), 'Layer failed; later overrides were not run')
        except Exception as error:
            failure = str(error)
    expected_checks = sum(len(s['readings']) for s in layer_specs) * len(SCHEMAS)
    runtime_unchanged = all(digest((runtime / name).read_bytes()) == sha for name, sha in initial_runtime_hashes.items())
    stats = {}
    for schema in SCHEMAS:
        group = [c for c in checks if c['schema'] == schema]
        defaults = [c for c in group if c['layer'] == 'delivered-defaults']
        stats[schema] = {'default_checks': len(defaults), 'alternative_checks': len(group) - len(defaults),
                         'baseline_checks': sum(c['baseline_trigger'] for c in defaults),
                         'affected_baseline_checks': sum(c['affected_baseline'] for c in defaults),
                         'case_sensitive_checks': sum(c['checks_case'] for c in group),
                         'full_phrase_checks': sum(c['checks_full_phrase'] for c in group),
                         'passed_checks': sum(c['passed'] for c in group),
                         'failed_checks': sum(not c['passed'] for c in group)}
    compiled = {p.relative_to(run).as_posix(): digest(p.read_bytes())
                for p in sorted((main_user / 'build').glob('*')) if p.is_file()}
    report = {
        'schema_version': 2, 'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'passed': failure is None and runtime_unchanged and len(checks) == expected_checks and all(c['passed'] for c in checks),
        'error': failure, 'elapsed_seconds': round(time.monotonic() - started, 2),
        'snapshot': snapshot.relative_to(ROOT).as_posix(), 'accepted_records': len(accepted),
        'snapshot_artifacts': summary['artifacts'], 'run_directory': run.relative_to(snapshot).as_posix(),
        'actual_engine_startups': startups, 'unique_default_trigger_readings': len(readings),
        'retained_nondefault_values': sum(len(s['readings']) for s in layers),
        'expected_checks': expected_checks, 'completed_checks': len(checks), 'schema_results': stats,
        'all_accepted_ids_preserved_in_model_and_Lua': accepted_ids <= runtime_ids,
        'accepted_ids_checked': len(accepted_ids), 'baseline_defaults_and_options_preserved': compatibility['all_defaults_preserved'],
        'runtime_inputs_unchanged': runtime_unchanged, 'runtime_inputs': initial_runtime_hashes,
        'compiled_dictionary_and_schemas': compiled,
        'checks_file': checks_path.relative_to(snapshot).as_posix(), 'checks_sha256': digest(checks_path.read_bytes()),
        'failures': [c for c in checks if not c['passed']],
        'explicit_delimiter_fallbacks': [dict(schema=c['schema'], layer=c['layer'], chinese=c['chinese'], input=c['input'])
                                        for c in checks if 'undelimited_lookup_error' in c],
        'scope': 'Actual source-built x64 Rime 1.13.1/Lua C API, full pinyin, natural double pinyin and Flypy; isolated synthetic input.',
        'limits': ['The delivered interaction displays/submits one explicit default per Chinese candidate/reading.',
                   'Other retained values were exercised through isolated default overrides; no new multi-sense selection UI is claimed.',
                   'No installation, TSF registration, physical keyboard, desktop UI acceptance or packaging was performed.'],
        'human_approved': False, 'release_ready': False,
    }
    write_json(run / 'runtime-report.json', report)
    target = Path(report_path) if report_path else snapshot / 'validation/runtime-report.json'
    write_json(target, report)
    print(json.dumps({'passed': report['passed'], 'checks': len(checks), 'failures': len(report['failures']),
                      'error': failure, 'report': str(target)}, ensure_ascii=False), flush=True)
    require(report['passed'], 'Real-engine verification failed; see ' + str(target))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    verify(args.snapshot, report_path=args.report)


if __name__ == '__main__':
    main()
