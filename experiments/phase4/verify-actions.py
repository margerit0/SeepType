"""Run the real-session action checks with only isolated synthetic input."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
executable = HERE / "build/session_actions_test.exe"
result = subprocess.run(
    [str(executable), str(ROOT)], cwd=ROOT, timeout=45,
    creationflags=subprocess.CREATE_NO_WINDOW,
)
path = HERE / "results/session-actions.json"
report = json.loads(path.read_text(encoding="utf-8"))
report["executed_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
report["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
report["lua_sha256"] = hashlib.sha256((ROOT / "src/study/lua/study_core.lua").read_bytes()).hexdigest()
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Session action checks: {sum(c['passed'] for c in report['checks'])}/{len(report['checks'])}")
raise SystemExit(result.returncode or (0 if report["passed"] else 1))
