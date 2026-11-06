"""New real Windows TSF edit-session evidence; never replaces older reports."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import subprocess
import sys
import uuid
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--preview', action='store_true')
parser.add_argument('--v05', action='store_true')
parser.add_argument('--service-x64', action='store_true')
parser.add_argument('--report', type=Path)
args = parser.parse_args()

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILD = HERE / 'build'
RUNTIME = HERE / 'runtime'
exe = BUILD / 'tsf_text_host_x64.exe'
dll = BUILD / 'tsf-x64/study_weasel_x64.dll'
service_exe = BUILD / ('study_service_x64.exe' if args.service_x64 else 'study_service.exe')
rime_dll = ROOT / ('.cache/rime-1.13.1/dist/lib/rime.dll' if args.service_x64 else '.cache/weasel-0.17.4/rime.dll')
env = os.environ.copy()
env['STUDY_IPC_TEST_NAME'] = uuid.uuid4().hex
if args.preview:
    env['STUDY_TSF_PREVIEW'] = '1'
settings = RUNTIME / ('native-v05-tsf-settings.ini' if args.v05 else 'text-host-settings.ini')
settings.write_text('version=1\nlearning=1\nlarge_text=0\ntheme=light\nshortcut=ctrl_shift_enter\nreduce_motion=0\n', encoding='utf-8')
env['STUDY_SETTINGS_PATH'] = str(settings)
checks = RUNTIME / 'text-host-checks.json'
checks.unlink(missing_ok=True)
error = None
with (RUNTIME / 'text-host-server.log').open('wb') as output:
    service = subprocess.Popen([str(service_exe)], cwd=ROOT, env=env,
        stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        run = subprocess.run([str(exe), str(checks), str(dll)] + (['--v05'] if args.v05 else []), cwd=ROOT, env=env,
            capture_output=True, timeout=140 if args.preview else 55, creationflags=subprocess.CREATE_NO_WINDOW)
        (RUNTIME / 'text-host-client.log').write_bytes(run.stdout + run.stderr)
        print((run.stdout + run.stderr).decode('utf-8', errors='replace').replace('\r\n', '\n'))
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
sources += [ROOT / 'src/study' / name for name in ['RimeSession.cpp', 'RimeSession.h', 'StudyService.cpp']]
sources += [HERE / name for name in ['prepare-weasel.py', 'service_rime.cpp', 'service_host.cpp']]
sources += list((ROOT / 'src/study/windows').glob('Candidate*.cpp')) + list((ROOT / 'src/study/windows').glob('Candidate*.h'))
sources += [ROOT / 'src/study/windows' / name for name in ['StudyLayout.cpp', 'StudyLayout.h', 'StudyMotion.cpp', 'StudyMotion.h', 'UiPreferences.cpp', 'UiPreferences.h', 'EnglishMenu.cpp', 'EnglishMenu.h']]
report = {
    'date': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
    'scope': 'Unregistered DLL factory activation; real Windows thread/document/context/range and edit sessions backed by a visible plain-text ITextStoreACP host. Host forwards key/focus callbacks to production sinks; actual Rime IPC and native candidate/menu windows.',
    'passed': not error and len(items) == (27 if args.v05 else 16) and all(c['passed'] for c in items),
    'checks': items, 'error': error,
    'binaries': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [exe, dll, service_exe, rime_dll]},
    'sources': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    'limits': ['Programmatic key/focus callbacks; not Windows routing of an installed TIP or physical keyboard/mouse observations',
        'Native menu open/cancel/focus/disconnect tested; physical selection of its English command remains unverified',
        'No registration, installation, profile activation or input settings changes',
        'Not Notepad/browser/VS Code compatibility evidence',
        ('x64' if args.service_x64 else 'x86') + ' isolated service; test-only lexicon; no complete installable product package'],
    'unchanged_evidence': ['tsf-frontend.json', 'desktop-menu.json', 'service-ipc.json', 'service-dispatch.json'],
}
destination = args.report or HERE / ('results/native-v05-tsf-x64.json' if args.v05 and args.service_x64 else 'results/native-v05-tsf.json' if args.v05 else 'results/tsf-text-host.json')
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
if not report['passed']:
    raise SystemExit(error or 'Incomplete text-host checks')
print(f'{len(items)}/{len(items)} real TSF text-host checks passed.')
