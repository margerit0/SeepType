"""Interactive desktop acceptance host; never overwrites automated evidence."""
from pathlib import Path
import json
import os
import subprocess
import uuid
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--service-x64', action='store_true')
parser.add_argument('--host', type=Path, help='Use a separately built acceptance host')
args = parser.parse_args()

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILD = HERE / 'build'
RUNTIME = HERE / 'runtime'
env = os.environ.copy()
env['STUDY_IPC_TEST_NAME'] = uuid.uuid4().hex
env['STUDY_SETTINGS_PATH'] = str(RUNTIME / 'interactive-settings.ini')
RUNTIME.mkdir(parents=True, exist_ok=True)
with (RUNTIME / 'interactive-server.log').open('wb') as server_log, (RUNTIME / 'interactive-host.log').open('wb') as host_log:
    service = subprocess.Popen([str(BUILD / ('study_service_x64.exe' if args.service_x64 else 'study_service.exe'))], cwd=ROOT, env=env,
        stdout=server_log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        host = subprocess.Popen([str(args.host.resolve() if args.host else BUILD / 'tsf_text_host_x64.exe'),
            str(RUNTIME / 'interactive-state.json'), str(BUILD / 'tsf-x64/study_weasel_x64.dll'), '--interactive'],
            cwd=ROOT, env=env, stdout=host_log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        (RUNTIME / 'interactive-processes.json').write_text(json.dumps({'host':host.pid, 'service':service.pid,
            'pipe':env['STUDY_IPC_TEST_NAME']}), encoding='utf-8')
        print(f'Interactive host PID {host.pid}; isolated service PID {service.pid}', flush=True)
        result = host.wait()
        if result:
            raise RuntimeError(f'Interactive host exited {result}; see interactive-host.log')
    finally:
        if service.poll() is None:
            service.terminate()
            service.wait(timeout=5)
