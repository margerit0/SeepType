"""Focused ordinary-selection response and learning-state IPC regression."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import subprocess
import uuid
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--service-x64', action='store_true')
args = parser.parse_args()

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RUNTIME = HERE / 'runtime'
exe = HERE / 'build/selection_test_x64.exe'
service_exe = HERE / ('build/study_service_x64.exe' if args.service_x64 else 'build/study_service.exe')
rime_dll = ROOT / ('.cache/rime-1.13.1/dist/lib/rime.dll' if args.service_x64 else '.cache/weasel-0.17.4/rime.dll')
checks = RUNTIME / 'selection-checks.json'
checks.unlink(missing_ok=True)
env = {**os.environ, 'STUDY_IPC_TEST_NAME': uuid.uuid4().hex}
with (RUNTIME / 'selection-server.log').open('wb') as log:
    service = subprocess.Popen([str(service_exe)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    error = None
    try:
        run = subprocess.run([str(exe), str(checks)], cwd=ROOT, env=env, capture_output=True, timeout=35, creationflags=subprocess.CREATE_NO_WINDOW)
        (RUNTIME / 'selection-client.log').write_bytes(run.stdout + run.stderr)
        print((run.stdout + run.stderr).decode('utf-8', errors='replace').replace('\r\n', '\n'))
        if run.returncode:
            raise RuntimeError(f'Selection client exited {run.returncode}')
        if service.wait(timeout=5):
            raise RuntimeError('Service shutdown failed')
    except Exception as failure:
        error = str(failure)
    finally:
        if service.poll() is None:
            service.terminate()
            service.wait(timeout=5)
items = json.loads(checks.read_text(encoding='utf-8'))['checks'] if checks.exists() else []
sources = [HERE / name for name in ['selection_test.cpp', 'verify-selection.py', 'prepare-weasel.py', 'patches/weasel-study-ipc.patch', 'service_rime.cpp', 'build-service.py']]
sources += [ROOT / 'src/study' / name for name in ['RimeSession.cpp', 'RimeSession.h', 'StudyService.cpp']]
report = {
    'date': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
    'scope': 'x64 production Weasel client and parser against the isolated ' + ('x64' if args.service_x64 else 'x86') + ' Rime service; ordinary selection response, pending commit protection and learning page preservation.',
    'passed': not error and len(items) == 7 and all(item['passed'] for item in items),
    'checks': items, 'error': error,
    'binaries': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in [exe, service_exe, rime_dll]},
    'sources': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
    'limits': ['No desktop input, TSF activation, registration or installed-application compatibility observations'],
}
(HERE / ('results/selection-ipc-x64.json' if args.service_x64 else 'results/selection-ipc.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
if not report['passed']:
    raise SystemExit(error or 'Incomplete selection checks')
print('7/7 ordinary selection IPC checks passed.')
