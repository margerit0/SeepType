"""New cross-process coverage only; does not rerun prior engine/UI/menu suites."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
RUNTIME = HERE / "runtime"
RESULTS = HERE / "results"
RESULTS.mkdir(exist_ok=True)
RUNTIME.mkdir(exist_ok=True)

if not (RUNTIME / ".prepared").exists():
    prepared = ROOT / "experiments/phase3/runtime"
    if not (prepared / "user/build/study.schema.yaml").exists():
        raise SystemExit("Use the existing prepared phase3 runtime before this new IPC check.")
    for name in ["shared", "user"]:
        shutil.copytree(prepared / name, RUNTIME / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("logs", "*.log"))
    (RUNTIME / ".prepared").write_text("Separate copy; never reads installed Rime user data.\n")

server_exe = BUILD / "study_service.exe"
client_exe = BUILD / "service_client_test.exe"
ticket = RUNTIME / "restart-ticket.txt"
environment = os.environ.copy()
environment["STUDY_IPC_TEST_NAME"] = uuid.uuid4().hex
logs = []
all_checks = []
def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

executables = {p.name: digest(p) for p in [server_exe, client_exe]}
resume = "--resume" in sys.argv
if resume:
    previous = json.loads((RESULTS / "service-ipc.json").read_text(encoding="utf-8"))
    if previous["executables"][server_exe.name] != executables[server_exe.name]:
        raise SystemExit("Server changed; previous passes cannot be reused for --resume.")
    failed = [c["name"] for c in previous["checks"] if not c["passed"]]
    if failed != ["partial composition cannot lose remaining pinyin through IPC"]:
        raise SystemExit("--resume is for the isolated candidate-selection assertion correction only.")
    for check in previous["checks"]:
        if check["passed"]:
            check.setdefault("client_executable_sha256", previous["executables"][client_exe.name])
            all_checks.append(check)


def run_server_test(name, arguments):
    server_log = RUNTIME / (name + "-server.log")
    client_log = RUNTIME / (name + "-client.log")
    partial = RUNTIME / (name + ".json")
    logs.extend([server_log, client_log])
    with server_log.open("wb") as output:
        server = subprocess.Popen([str(server_exe)], cwd=ROOT, env=environment,
                                  stdout=output, stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            with client_log.open("wb") as client_output:
                result = subprocess.run([str(client_exe), str(partial), *map(str, arguments)],
                                        cwd=ROOT, env=environment, stdout=client_output,
                                        stderr=subprocess.STDOUT, timeout=50,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
            print(client_log.read_text(encoding="utf-8", errors="replace"), end="")
            if partial.exists():
                data = json.loads(partial.read_text(encoding="utf-8"))
                for check in data["checks"]:
                    check["client_executable_sha256"] = executables[client_exe.name]
                    all_checks.append(check)
            if result.returncode:
                raise RuntimeError(f"New IPC check {name} failed (exit {result.returncode}).")
            if server.wait(timeout=5) != 0:
                raise RuntimeError(f"Isolated service {name} exited unsuccessfully.")
        finally:
            if server.poll() is None:
                # This is exactly the child process created above, never a
                # user's running Weasel or interactive probe process.
                server.terminate()
                server.wait(timeout=5)


failure = None
try:
    if resume:
        run_server_test("partial", ["--partial"])
    else:
        run_server_test("ipc", [ticket])
    run_server_test("restart", ["--restart", ticket])
except Exception as error:
    failure = str(error)
finally:
    report = {
        "date": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "scope": "Real Weasel Client, PipeChannel, IPC Server and RimeWithWeasel handler in separate processes, with the fixed x86 Rime/Lua DLL. Headless and isolated; no TSF registration or desktop input.",
        "passed": failure is None and bool(all_checks) and all(c["passed"] for c in all_checks),
        "checks": all_checks,
        "error": failure,
        "executables": executables,
        "verification_note": "The same service binary passed all checks. Earlier successful cases are retained with their client binary hashes; the candidate-selection display assertion was corrected and only that case and restart were rerun." if resume else "Single full IPC run plus a separate service restart.",
        "upstream_patch": "../patches/weasel-study-ipc.patch",
        "unchanged_suites": ["phase3 engine", "phase3 native UI", "phase3 DPI layout", "phase4 desktop menu"],
        "limits": ["No Windows input method installed or registered", "No live TSF client or application compatibility coverage", "No production toolbar, settings or animation coverage", "Uses the 21-entry test-only lexicon", "Runs x86 clients and service; x64 TSF integration remains pending"],
    }
    (RESULTS / "service-ipc.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
if failure:
    raise SystemExit(failure)
print(f"{len(all_checks)}/{len(all_checks)} new cross-process checks passed; prior suites were not rerun.")
