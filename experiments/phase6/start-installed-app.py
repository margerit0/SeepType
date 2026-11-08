"""Launch a real application against an installed TIP with isolated StudyIME data.

Only the installer registers the TIP. This helper does not select an input
profile or synthesize input; all desktop interaction uses Computer Use.
"""
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import winreg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.packaging.common import file_hash, json_bytes, product


def chrome_path():
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                path = Path(winreg.QueryValueEx(key, "")[0])
                if path.is_file():
                    return path
        except FileNotFoundError:
            pass
    raise FileNotFoundError("Chrome executable was not registered in App Paths")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", choices=["notepad", "chrome", "vscode", "stop-service"])
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    installed = Path(os.environ["ProgramFiles"]) / "StudyIME" / product()["version"]
    receipt = json.loads((installed / "install-receipt.json").read_text(encoding="utf-8-sig"))
    if receipt["status"] != "installed" or not receipt["registered"]:
        raise ValueError("A successful, registered installation is required")
    manifest = json.loads((installed / "package-manifest.json").read_bytes())
    if receipt["manifest_sha256"] != file_hash(installed / "package-manifest.json"):
        raise ValueError("Installed manifest and receipt differ")
    hashes = {}
    for entry in manifest["files"]:
        if entry["path"].startswith(("bin/", "data/")) or entry["path"] == "product.json":
            hashes[entry["path"]] = file_hash(installed / entry["path"])
            if hashes[entry["path"]] != entry["sha256"]:
                raise ValueError("Installed input changed: " + entry["path"])
    if args.record.exists():
        record = json.loads(args.record.read_bytes())
        if record["installed_input_hashes"] != hashes:
            raise ValueError("Installed inputs changed during this application session")
    else:
        session = uuid.uuid4().hex
        work = ROOT / ".cache/packaging/installed-apps" / session
        work.mkdir(parents=True)
        record = {"started_at": datetime.now(timezone.utc).isoformat(), "session": session,
                  "work": str(work), "data_root": str(work / "user"), "installed_root": str(installed),
                  "installed_input_hashes": hashes, "launches": []}
    work = Path(record["work"])
    env = {**os.environ, "STUDYIME_DEV_SESSION": record["session"], "STUDYIME_DEV_DATA_ROOT": record["data_root"]}
    service = installed / "bin/StudyIME.Service.exe"
    if args.app == "stop-service":
        subprocess.run([str(service), "--stop"], env=env, cwd=installed, check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=20)
        record["service_stopped_at"] = datetime.now(timezone.utc).isoformat()
    else:
        if not record.get("data_prepared"):
            subprocess.run([str(service), "--prepare-data"], env=env, cwd=installed, check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=90)
            record["data_prepared"] = True
        if args.app == "chrome":
            page = work / "browser-input.html"
            page.write_bytes((ROOT / "experiments/phase6/browser-input.html").read_bytes())
            command = [chrome_path(), "--user-data-dir=" + str(work / "chrome-profile"),
                       "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--new-window", page.as_uri()]
        else:
            document = work / ("StudyIME-" + args.app + "-acceptance.txt")
            if not document.exists():
                document.write_text("", encoding="utf-8")
            if args.app == "notepad":
                command = [Path(os.environ["SystemRoot"]) / "System32/notepad.exe", document]
            else:
                code_cli = shutil.which("code.cmd")
                if not code_cli:
                    raise FileNotFoundError("VS Code command was not found")
                command = [Path(code_cli).resolve().parents[1] / "Code.exe", "--new-window", "--disable-extensions",
                           "--user-data-dir", work / "vscode-profile", "--extensions-dir", work / "vscode-extensions",
                           "--skip-welcome", "--skip-release-notes", document]
        command = [str(arg) for arg in command]
        process = subprocess.Popen(command, env=env, cwd=work, creationflags=subprocess.CREATE_NO_WINDOW)
        record["launches"].append({"app": args.app, "pid": process.pid, "command": command,
                                   "at": datetime.now(timezone.utc).isoformat()})
    args.record.parent.mkdir(parents=True, exist_ok=True)
    args.record.write_bytes(json_bytes(record))
    print(json.dumps({"record": str(args.record), "work": str(work), "app": args.app,
                      "launch": record["launches"][-1] if args.app != "stop-service" else None}, ensure_ascii=False))


if __name__ == "__main__":
    main()
