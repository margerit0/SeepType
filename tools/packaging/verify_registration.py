"""Verify shared registration rollback using memory operations, never Windows registration."""
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, file_hash, json_bytes, write_changed
from tools.packaging.verify import registry_state


def main():
    before = registry_state()
    executable = CACHE / "registration-test/flow.exe"
    result = subprocess.run([str(executable)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
    report = json.loads(result.stdout)
    report.update({"recorded_at": datetime.now(timezone.utc).isoformat(),
        "test_executable_sha256": file_hash(executable),
        "inputs": {name: file_hash(ROOT / name) for name in [
            "src/study/windows/ProductRegistrationFlow.h", "tools/packaging/registration_flow_test.cpp"]},
        "registry_unchanged": before == registry_state(), "system_install_executed": False,
        "tsf_registration_executed": False, "scope_limit":
            "The production registration flow runs against an in-memory operation adapter. Windows registry/TSF API behavior and actual installation still require authorized acceptance."})
    write_changed(ROOT / "experiments/phase6/results/registration-recovery.json", json_bytes(report))
    print(f"Registration recovery memory checks: {report['passed']}/{report['total']}; no system registration.")
    if result.returncode or report["passed"] != report["total"] or not report["registry_unchanged"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
