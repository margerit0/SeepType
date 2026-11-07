"""Probe shipped dev.2 activation without registration; fail closed if unsupported.

The first dev.2 run failed Activate with E_FAIL in this unregistered host.
This is a diagnostic entry point, not a completed desktop acceptance route.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.packaging.common import CACHE, file_hash, json_bytes, product
from tools.packaging.verify import registry_state


def main():
    package = CACHE / 'stage' / ('StudyIME-' + product()['version'])
    host_path = CACHE / 'desktop-host/StudyIME.DesktopHost.exe'
    build = json.loads((host_path.parent / 'build.json').read_bytes())
    if file_hash(host_path) != build['executable_sha256']:
        raise ValueError('Desktop host does not match its build record')
    manifest = json.loads((package / 'package-manifest.json').read_bytes())
    # Bind this observation to the existing release payload, without rebuilding.
    hashes = {}
    for entry in manifest['files']:
        name = entry['path']
        if name.startswith(('bin/', 'data/shared/', 'data/user-template/')) or name == 'product.json':
            actual = file_hash(package / name)
            if actual != entry['sha256']:
                raise ValueError('Changed product input: ' + name)
            hashes[name] = actual
    session = uuid.uuid4().hex
    work = CACHE / 'desktop-runs' / session
    work.mkdir(parents=True)
    env = {**os.environ, 'STUDYIME_DEV_SESSION': session,
           'STUDYIME_DEV_DATA_ROOT': str(work / 'user')}
    service = package / 'bin/StudyIME.Service.exe'
    normal = Path(os.environ['LOCALAPPDATA']) / 'StudyIME'
    record = {'started_at': datetime.now(timezone.utc).isoformat(),
              'package': str(package), 'runtime_input_hashes': hashes,
              'host_build': build, 'session': session, 'data_root': env['STUDYIME_DEV_DATA_ROOT'],
              'registry_before': registry_state(), 'normal_data_existed_before': normal.exists(),
              'system_install_executed': False, 'tsf_registration_executed': False,
              'scope': 'Shipped DLL loaded in an unregistered two-document TSF host; host forwards physical key messages. No installed routing or external application acceptance.'}
    def save():
        (work / 'session.json').write_bytes(json_bytes(record))
    def run(args):
        subprocess.run([str(arg) for arg in args], cwd=package, env=env, check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=90)
    save()
    print(str(work), flush=True)
    try:
        run([service, '--prepare-data'])
        run([service, '--ensure-running'])
        with (work / 'host.log').open('wb') as log:
            host = subprocess.Popen([str(host_path), str(work / 'state.json'),
                str(package / 'bin/StudyIME.TSF.x64.dll'), '--interactive'], cwd=package,
                env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
            record['host_pid'] = host.pid
            save()
            record['host_exit_code'] = host.wait()
        record['host_log'] = (work / 'host.log').read_text(encoding='utf-8', errors='replace')
        record['activation_succeeded'] = 'Interactive text host ready;' in record['host_log']
    finally:
        try:
            run([service, '--stop'])
            record['service_stopped'] = True
        finally:
            record['registry_after'] = registry_state()
            record['normal_data_existed_after'] = normal.exists()
            record['finished_at'] = datetime.now(timezone.utc).isoformat()
            save()
    if record['host_exit_code']:
        raise RuntimeError('Host failed; see ' + str(work / 'host.log'))


if __name__ == '__main__':
    main()
