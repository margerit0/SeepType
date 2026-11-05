"""Targeted x64 frontend checks, using the previously verified x86 service."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib, json, os, subprocess, uuid
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BUILD=HERE/'build'
RUNTIME=HERE/'runtime'
exe=BUILD/'frontend_test_x64.exe'
dll=BUILD/'tsf-x64/study_weasel_x64.dll'
server_exe=BUILD/'study_service.exe'
env=os.environ.copy()
env['STUDY_IPC_TEST_NAME']=uuid.uuid4().hex
checks=RUNTIME/'frontend-checks.json'
if checks.exists(): checks.unlink()
error=None
with (RUNTIME/'frontend-server.log').open('wb') as output:
    server=subprocess.Popen([str(server_exe)],cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        run=subprocess.run([str(exe),str(checks),str(dll)],cwd=ROOT,env=env,capture_output=True,timeout=40,creationflags=subprocess.CREATE_NO_WINDOW)
        (RUNTIME/'frontend-client.log').write_bytes(run.stdout+run.stderr)
        print((run.stdout+run.stderr).decode('utf-8',errors='replace'))
        if run.returncode: raise RuntimeError(f'Frontend test exited {run.returncode}')
        if server.wait(timeout=5): raise RuntimeError('Service did not exit cleanly')
    except Exception as failure: error=str(failure)
    finally:
        if server.poll() is None:
            server.terminate();server.wait(timeout=5)
items=json.loads(checks.read_text(encoding='utf-8'))['checks'] if checks.exists() else []
report={
    'date':datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
    'scope':'Built all x64 TSF translation units and resources; loaded isolated DLL without registration; tested production response parser/state and x64-to-x86 real Rime IPC. No TSF activation or document editing.',
    'passed':not error and len(items)==16 and all(c['passed'] for c in items),
    'checks':items,'error':error,
    'binaries':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [exe,dll,server_exe]},
    'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'src/study/windows/WeaselResponse.cpp',ROOT/'src/study/windows/TsfStudy.inc',HERE/'prepare-tsf.py',HERE/'patches/weasel-study-ipc.patch']},
    'limits':['No TSF registration or input settings change','No real TSF edit-session execution, visible TSF menu, or application compatibility evidence','x64 TSF DLL with x86 isolated service; not an x64 service/package','Test-only lexicon; native v0.5 tool area, definition popup, settings and animations remain pending'],
    'unchanged_evidence':['desktop-menu.json','service-ipc.json','service-dispatch.json']
}
(HERE/'results/tsf-frontend.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if not report['passed']: raise SystemExit(error or 'Incomplete frontend checks')
print(f'{len(items)}/{len(items)} targeted frontend checks passed.')
