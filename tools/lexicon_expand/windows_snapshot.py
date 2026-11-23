"""Check the shared development lexicon, optionally in a fresh Windows Rime session."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
import tempfile

from tools.lexicon_expand.common import DATA, ROOT, digest, generated_directory, require, write_json
from tools.lexicon_expand.runtime import lua_bytes
from tools.lexicon_expand.verify_integration import allowed_annotations
from tools.packaging.common import CACHE as PACKAGE_CACHE
from tools.packaging.engine_client import EngineProbe
from tools.packaging.package import chinese_data, source_lock
from tools.packaging.verify_double_pinyin import SCHEMAS

EXPANSION = DATA.relative_to(ROOT)
RUNTIME = EXPANSION / 'windows-runtime'
SHARED = EXPANSION / 'android-runtime'
CORE = Path('src/study/lua/study_core.lua')
SUPPLEMENT = b'# Reviewed expansion Chinese triggers; provenance in expansion manifest.\n'


@dataclass(frozen=True)
class Snapshot:
    metadata: dict
    model: dict
    dictionary: bytes
    lua: bytes
    core: bytes
    cases: list[dict]


def locked_bytes(path, expected):
    data = path.read_bytes()
    require(digest(data) == expected, f'Development snapshot hash mismatch: {path.name}')
    return data


def load_snapshot(root=ROOT):
    lock = json.loads((root / RUNTIME / 'snapshot.json').read_bytes())
    require(lock['schema_version'] == 1, 'Unexpected Windows snapshot schema')
    metadata = json.loads(locked_bytes(root / SHARED / 'snapshot.json', lock['shared_snapshot_sha256']))
    require(metadata['schemaVersion'] == 1 and metadata['humanApproved'] == 0 and not metadata['releaseReady'],
            'Expected a development-only snapshot')
    model = json.loads(locked_bytes(root / RUNTIME / 'runtime-model.json', lock['runtime_model_sha256']))

    def shared(name):
        return locked_bytes(root / SHARED / name, metadata['files'][name])

    dictionary, lua = shared('cedict_study.dict.yaml'), shared('lexicon.lua')
    core = locked_bytes(root / CORE, metadata['studyCoreSha256'])
    require(lua_bytes(model) == lua, 'Windows runtime model does not reproduce the shared Lua lexicon')
    base, marker, supplemental = dictionary.partition(SUPPLEMENT)
    require(marker and digest(base) == metadata['baseDictionarySha256'], 'Chinese base dictionary changed')
    rows = dictionary.split(b'\n...\n', 1)[1].splitlines()
    require(len(supplemental.splitlines()) == metadata['supplementalReadings'] and
            sum(bool(row) and not row.startswith(b'#') for row in rows) == metadata['chineseDictionaryRows'],
            'Chinese dictionary coverage changed')

    cases = json.loads(shared('engine-cases.json'))
    allowed = allowed_annotations(model)
    require(all(re.fullmatch("[a-z']+", case['input']) and case['english'] in allowed.get(case['chinese'], ())
                for case in cases), 'Invalid Windows engine case input or expected value')
    signatures = {schema: Counter((case['chinese'], case['english'], case['coverage']) for case in cases
                                 if case['schema'] == schema) for schema in SCHEMAS}
    require(set(c['schema'] for c in cases) == set(SCHEMAS) and
            all(signatures[schema] == signatures['study'] for schema in SCHEMAS),
            'Windows engine cases must cover matching entries in all three schemes')
    return Snapshot(metadata, model, dictionary, lua, core, cases)


def verify_engine(snapshot, executable, dll):
    executable, dll = executable.resolve(strict=True), dll.resolve(strict=True)
    sources, _ = chinese_data(source_lock())
    dictionary_path = 'data/shared/cedict_study.dict.yaml'
    require(digest(sources[dictionary_path]) == snapshot.metadata['baseDictionarySha256'],
            'Pinned Windows source data does not reproduce the shared base dictionary')
    sources[dictionary_path] = snapshot.dictionary
    for schema in SCHEMAS:
        name = schema + '.schema.yaml'
        sources['data/shared/' + name] = (ROOT / 'packaging/data' / name).read_bytes()
    for name in ('default.custom.yaml', 'rime.lua'):
        sources['data/user-template/' + name] = (ROOT / 'packaging/data' / name).read_bytes()
    sources['data/user-template/lua/lexicon.lua'] = snapshot.lua
    sources['data/user-template/lua/study_core.lua'] = snapshot.core
    cache = generated_directory(ROOT / '.cache/lexicon-expansion/windows-snapshot')
    cache.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='run-', dir=cache))
    shared, user = run / 'data/shared', run / 'data/user-template'
    inputs = {}
    for name, raw in sources.items():
        if name.startswith(('data/shared/', 'data/user-template/')):
            path = run / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            inputs[name] = digest(raw)
    print(f'Isolated Windows Rime workspace: {run}', flush=True)
    checked = Counter()
    allowed = allowed_annotations(snapshot.model)
    probe = EngineProbe(executable, dll, shared, user)
    try:
        probe.receive(timeout=90)
        for schema in SCHEMAS:
            probe.command('schema ' + schema)
            for case in snapshot.cases:
                if case['schema'] != schema:
                    continue
                code, word, english = case['input'], case['chinese'], case['english']
                label = f'{schema}/{code}/{word}'
                page, index = probe.find(code, word, pages=80)
                require(page['load'] == 'ready' and page['candidates'][index]['comment'] == english and
                        all(c['comment'] in allowed.get(c['text'], {''}) for c in page['candidates']),
                        'Unexpected candidate annotation: ' + label)
                require(probe.command('highlight ' + str(index))['selected'] == index,
                        'Candidate selection did not follow the highlight: ' + label)
                committed = probe.command('key 65293 5')
                require(committed['commit'] == english and committed['input'] == '' and
                        committed['action'] == 'english-committed', 'Unexpected English commit: ' + label)
                _, index = probe.find(code, word, pages=80)
                committed = probe.command('choose ' + str(index))
                require(committed['commit'] == word and committed['input'] == '',
                        'Unexpected Chinese commit: ' + label)
                checked[schema] += 1
    finally:
        probe.close()
    require(sum(checked.values()) == len(snapshot.cases), 'Incomplete Windows engine coverage')
    report = {'passed': True, 'checked': dict(checked), 'runtime_inputs': inputs,
              'engine_probe_sha256': digest(executable.read_bytes()), 'rime_sha256': digest(dll.read_bytes())}
    write_json(run / 'report.json', report)
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='store_true', help='Run the real Windows engine; do not install anything')
    parser.add_argument('--probe', type=Path, default=PACKAGE_CACHE / 'build/bin/StudyIME.EngineProbe.exe')
    parser.add_argument('--rime', type=Path, default=ROOT / '.cache/rime-build/dist/lib/rime.dll')
    args = parser.parse_args()
    try:
        snapshot = load_snapshot()
        result = {'source_commit': snapshot.metadata['windowsCommit'], 'snapshot_passed': True,
                  'engine_cases': len(snapshot.cases)}
        if args.engine:
            result['windows_engine_checks'] = dict(verify_engine(snapshot, args.probe, args.rime))
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f'{error}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
