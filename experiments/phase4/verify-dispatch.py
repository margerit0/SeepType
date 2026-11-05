"""Only the changed scheduling/lifetime paths; retain the earlier IPC evidence."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import os
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
RUNTIME = HERE / "runtime"
RESULTS = HERE / "results"
environment = os.environ.copy()
environment["STUDY_IPC_TEST_NAME"] = uuid.uuid4().hex
checks = []
error = None
executables = {}
for name in ["dispatch_test", "study_service", "service_client_test"]:
    with (BUILD / (name + ".exe")).open("rb") as stream:
        executables[name + ".exe"] = hashlib.file_digest(stream, "sha256").hexdigest()


def run(name, args):
    path = RUNTIME / (name + "-checks.json")
    if path.exists():
        path.unlink()
    log = RUNTIME / (name + ".log")
    try:
        with log.open("wb") as output:
            result = subprocess.run([str(BUILD / (args[0] + ".exe")), str(path), *args[1:]],
                                    cwd=ROOT, env=environment, stdout=output,
                                    stderr=subprocess.STDOUT, timeout=30,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        print(log.read_text(encoding="utf-8", errors="replace"), end="")
        if path.exists():
            checks.extend(json.loads(path.read_text(encoding="utf-8"))["checks"])
    if result.returncode:
        raise RuntimeError(f"{name} exited with {result.returncode}")


try:
    run("dispatch", ["dispatch_test"])
    with (RUNTIME / "dispatch-rime-server.log").open("wb") as output:
        server = subprocess.Popen([str(BUILD / "study_service.exe")], cwd=ROOT,
                                  env=environment, stdout=output, stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            run("dispatch-rime", ["service_client_test", "--dispatch"])
            if server.wait(timeout=5) != 0:
                raise RuntimeError("Rime service did not exit cleanly")
        finally:
            if server.poll() is None:
                server.terminate()
                server.wait(timeout=5)
except Exception as failure:
    error = str(failure)

report = {
    "date": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
    "scope": "Window-owner dispatch and joined transport lifetime using actual Win32 message queues, patched Weasel pipes, and a targeted real Rime smoke run. No visible candidate window or installed TSF.",
    "passed": not error and len(checks) == 14 and all(item["passed"] for item in checks),
    "checks": checks,
    "error": error,
    "executables": executables,
    "upstream_patch": "../patches/weasel-study-ipc.patch",
    "unchanged_evidence": ["service-ipc.json", "desktop-menu.json", "session-actions.json", "phase3 results"],
    "limits": ["x86 isolated test processes", "No visible candidate or TSF edit-session validation", "No real application compatibility validation", "Test-only lexicon"],
}
(RESULTS / "service-dispatch.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if not report["passed"]:
    raise SystemExit(error or "Dispatch checks failed or incomplete")
print(f"{len(checks)}/{len(checks)} targeted dispatch checks passed; older evidence retained.")
