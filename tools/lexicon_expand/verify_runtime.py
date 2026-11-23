"""Exercise the expansion through isolated source-built Rime/Lua sessions."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import uuid

from tools.lexicon import pipeline as lex
from tools.lexicon_expand.common import CACHE, ROOT, digest, read_json, read_jsonl, write_json
from tools.lexicon_expand.finalize import FINAL, PREVIEW, SNAPSHOT, SNAPSHOT_PREVIEW, build_preview
from tools.lexicon_expand.catalog import input_reading
from tools.packaging.engine_client import EngineProbe
from tools.packaging.package import chinese_data, source_lock
from tools.packaging.verify_double_pinyin import SCHEMAS, encode_syllable


def verify(legacy=False, snapshot=False, *, packaged=None, report_path=None):
    if packaged:
        from pathlib import Path
        packaged = Path(packaged).resolve()
    data = lex.validate()
    if legacy:
        dictionary = None
        lua = lex.build_files(data, 'preview')['lexicon.lua']
        rows = [{**r, 'pinyin': data.sources[r['source_entry_sha256']]['pinyin'].lower().replace('u:', 'v')}
                for r in data.entries]
        expected = {r['chinese']: r['commit_english'] for r in rows}
    else:
        if packaged:
            reviewed = packaged / 'data/lexicon-expansion'
            dictionary = (packaged / 'data/shared/cedict_study.dict.yaml').read_bytes()
            lua = (packaged / 'data/user-template/lua/lexicon.lua').read_bytes()
        else:
            build_preview(snapshot=snapshot)
            preview = SNAPSHOT_PREVIEW if snapshot else PREVIEW
            reviewed = SNAPSHOT if snapshot else FINAL
            dictionary = (preview / 'cedict_study.dict.yaml').read_bytes()
            lua = (preview / 'lua/lexicon.lua').read_bytes()
        model = read_json(reviewed / 'runtime-model.json')
        expected = {zh: next(s['commit_english'] for s in e['senses'] if s['id'] == e['primary_sense_id'])
                    for zh, e in model['entries'].items()}
        rows = read_jsonl(reviewed / 'accepted-senses.jsonl')
        covered = {r['chinese'] for r in rows}
        rows += [{**r, 'pinyin': data.sources[r['source_entry_sha256']]['pinyin'].lower().replace('u:', 'v')}
                 for r in data.entries if r['chinese'] not in covered]
    unique = {}
    for row in rows:
        code = input_reading(row['chinese'], row['pinyin'])
        unique.setdefault((row['chinese'], code), row)
    allowed = {zh: {value} for zh, value in expected.items()}
    if not legacy:
        for zh, entry in model['entries'].items():
            if entry['requires_reading']:
                allowed[zh] = {s['commit_english'] for s in entry['senses']
                               if s['id'] in entry['primary_by_reading'].values()}
    work = CACHE / 'runtime-checks' / (('legacy-' if legacy else 'final-') + uuid.uuid4().hex)
    shared, user = work / 'shared', work / 'user'
    if packaged:
        for source, destination in ((packaged / 'data/shared', shared), (packaged / 'data/user-template', user)):
            for path in source.rglob('*'):
                if path.is_file():
                    lex.atomic_write(destination / path.relative_to(source), path.read_bytes())
    else:
        files, _ = chinese_data(source_lock())
        for name, raw in files.items():
            if name.startswith('data/shared/'):
                lex.atomic_write(shared / name[len('data/shared/'):], raw)
    if dictionary:
        lex.atomic_write(shared / 'cedict_study.dict.yaml', dictionary)
    for name in ('study.schema.yaml', 'study_double_pinyin.schema.yaml', 'study_flypy.schema.yaml'):
        if not packaged:
            lex.atomic_write(shared / name, (ROOT / 'packaging/data' / name).read_bytes())
    for name in ('default.custom.yaml', 'rime.lua'):
        if not packaged:
            lex.atomic_write(user / name, (ROOT / 'packaging/data' / name).read_bytes())
    lex.atomic_write(user / 'lua/lexicon.lua', lua)
    core = ((packaged / 'data/user-template/lua/study_core.lua') if packaged else
            (ROOT / 'src/study/lua/study_core.lua')).read_bytes()
    lex.atomic_write(user / 'lua/study_core.lua', core)
    executable = ROOT / '.cache/packaging/build/bin/StudyIME.EngineProbe.exe'
    dll = packaged / 'bin/rime.dll' if packaged else ROOT / '.cache/rime-build/dist/lib/rime.dll'
    probe = None
    checks, failure, startup = [], None, None
    try:
        probe = EngineProbe(executable, dll, shared, user)
        startup = probe.receive(timeout=60)
        for schema in SCHEMAS:
            probe.command('schema ' + schema)
            for count, ((zh, code), row) in enumerate(unique.items(), 1):
                expected_value = expected[zh]
                if not legacy:
                    entry = model['entries'][zh]
                    if entry['requires_reading']:
                        sid = entry['primary_by_reading'][code]
                        expected_value = next(s['commit_english'] for s in entry['senses'] if s['id'] == sid)
                query = code.replace(' ', '') if schema == 'study' else ''.join(
                    encode_syllable(s, schema) for s in row['pinyin'].split())
                item = {'schema': schema, 'chinese': zh, 'pinyin': row['pinyin'], 'input': query,
                        'expected_english': expected_value, 'passed': False}
                try:
                    page, index = probe.find(query, zh, pages=60)
                    item['page'] = page['page']
                    item['annotations_match'] = page['load'] == 'ready' and all(
                        c['comment'] in allowed.get(c['text'], {''}) for c in page['candidates'])
                    item['selected_annotation_matches'] = page['candidates'][index]['comment'] == expected_value
                    probe.command('highlight ' + str(index))
                    result = probe.command('key 65293 5')
                    item['english_commit_matches'] = (result['commit'] == expected_value and result['input'] == ''
                                                        and result['action'] == 'english-committed')
                    _, index = probe.find(query, zh, pages=60)
                    chinese = probe.command('choose ' + str(index))
                    item['chinese_commit_matches'] = chinese['commit'] == zh and chinese['input'] == ''
                    item['passed'] = all(item[k] for k in ('annotations_match', 'selected_annotation_matches', 'english_commit_matches', 'chinese_commit_matches'))
                    if not item['passed']:
                        item.update(actual_english=result['commit'], actual_chinese=chinese['commit'])
                except ValueError as error:
                    item['error'] = str(error)
                checks.append(item)
                if not item['passed'] or count % 100 == 0:
                    print(json.dumps({'schema': schema, 'checked': count, 'total': len(unique),
                                      'failures': sum(not r['passed'] for r in checks)}, ensure_ascii=False), flush=True)
    except Exception as error:
        failure = str(error)
    finally:
        if probe:
            try:
                probe.close()
            except Exception as error:
                failure = failure or str(error)
    report = {'schema_version': 1, 'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'passed': failure is None and len(checks) == len(unique) * len(SCHEMAS) and all(c['passed'] for c in checks),
              'error': failure, 'startup': startup, 'legacy_flat_schema': legacy, 'partial_review_snapshot': snapshot,
              'unique_trigger_readings': len(unique), 'checks': checks,
              'packaged_runtime': str(packaged) if packaged else None,
              'runtime_core_sha256': digest(core), 'lexicon_lua_sha256': digest(lua),
              'dictionary_sha256': digest((shared / 'cedict_study.dict.yaml').read_bytes()),
              'engine_probe_sha256': digest(executable.read_bytes()), 'rime_dll_sha256': digest(dll.read_bytes()),
              'work_directory': work.relative_to(ROOT).as_posix(),
              'scope': 'Isolated actual x64 Rime/Lua C API; synthetic inputs; full pinyin and both double-pinyin schemes.',
              'limits': ['Does not test installed TSF, physical input, desktop candidate rendering, or other applications.',
                         'Checks the explicitly selected common sense; other accepted senses are preserved in the data.']}
    name = 'legacy-runtime-compatibility' if legacy else 'snapshot-runtime' if snapshot else 'final-runtime'
    target = report_path or ROOT / 'experiments/lexicon-expansion/results' / (name + '-20261109.json')
    write_json(target, report)
    print(json.dumps({'passed': report['passed'], 'checks': len(checks), 'failures': sum(not c['passed'] for c in checks),
                      'error': failure, 'report': str(target)}, ensure_ascii=False), flush=True)
    if not report['passed']:
        raise SystemExit(1)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy', action='store_true')
    parser.add_argument('--snapshot', action='store_true')
    args = parser.parse_args()
    verify(args.legacy, args.snapshot)
