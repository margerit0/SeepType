"""New real Windows TSF edit-session evidence; never replaces older reports."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILD = HERE / 'build'
RUNTIME = HERE / 'runtime'
exe = BUILD / 'tsf_text_host_x64.exe'
dll = BUILD / 'tsf-x64/study_weasel_x64.dll'
service_exe = BUILD / 'study_service.exe'
env = os.environ.copy()
env['STUDY_IPC_TEST_NAME'] = uuid.uuid4().hex
if '--preview' in sys.argv:
    env['STUDY_TSF_PREVIEW'] = '1'
checks = RUNTIME / 'text-host-checks.json'
checks.unlink(missing_ok=True)
error = None
with (RUNTIME / 'text-host-server.log').open('wb') as output:
    service = subprocess.Popen([str(service_exe)], cwd=ROOT, env=env,
        stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        run = subprocess.run([str(exe), str(checks), str(dll)], cwd=ROOT, env=env,
            capture_output=True, timeout=140 if '--preview' in sys.argv else 45, creationflags=subprocess.CREATE_NO_WINDOW)
        (RUNTIME / 'text-host-client.log').write_bytes(run.stdout + run.stderr)
        print((run.stdout + run.stderr).decode('utf-8', errors='replace'))
        if run.returncode:
            raise RuntimeError(f'Text host exited {run.returncode}')
        if service.wait(timeout=5):
            raise RuntimeError('Isolated service exit failed')
    except Exception as failure:
        error = str(failure)
    finally:
        if service.poll() is None:
            service.terminate()
            service.wait(timeout=5)
items = json.loads(checks.read_text(encoding='utf-8'))['checks'] if checks.exists() else []
sources = [HERE / name for name in ['tsf_text_host.cpp', 'text_store.h', 'prepare-tsf.py',
    'build-service.py', 'verify-text-host.py', 'patches/weasel-study-ipc.patch']]
sources += [ROOT / 'src/study/windows/TsfStudy.inc']
report = {
    'date': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
    'scope': 'Unregistered DLL factory activation; real Windows thread/document/context/range and edit sessions backed by a visible plain-text ITextStoreACP host. Host forwards key/focus callbacks to production sinks; actual Rime IPC and native candidate/menu windows.',
    'passed': not error and len(items) == 16 and all(c['passed'] for c in items),
    'checks': items, 'error': error,
    'binaries': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [exe, dll, service_exe]},
    'sources': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    'limits': ['Programmatic key/focus callbacks; not Windows routing of an installed TIP or physical keyboard/mouse observations',
        'Native menu open/cancel/focus/disconnect tested; physical selection of its English command remains unverified',
        'No registration, installation, profile activation or input settings changes',
        'Not Notepad/browser/VS Code compatibility evidence',
        'x86 isolated service, test-only lexicon; v0.5 full UI and x64 service/package still pending'],
    'unchanged_evidence': ['tsf-frontend.json', 'desktop-menu.json', 'service-ipc.json', 'service-dispatch.json'],
}
(HERE / 'results/tsf-text-host.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
if not report['passed']:
    raise SystemExit(error or 'Incomplete text-host checks')
print(f'{len(items)}/{len(items)} real TSF text-host checks passed.')
