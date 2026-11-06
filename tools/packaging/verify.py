"""Targeted package/installer-plan/runtime verification; never installs a TIP.

No -Apply path, registry write, physical input or Computer Use is invoked.
Test files and Rime deployment output stay under .cache/packaging/verification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import winreg
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, deterministic_zip, file_hash, json_bytes, package_path, product, sha256, write_changed
from tools.packaging.package import native_build, payload, stage

HERE = ROOT / "experiments/phase6/results"
POWERSHELL = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"


def run(args, *, env=None, timeout=60, ok=True):
    result = subprocess.run([str(arg) for arg in args], cwd=CACHE, env=env, timeout=timeout,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    if ok and result.returncode:
        raise RuntimeError(f"{Path(str(args[0])).name} exited {result.returncode}: " + result.stderr.decode("utf-8", errors="replace")[-3500:])
    return result


def powershell(script, *, ok=True):
    import base64
    script = "[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false); " + script
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return run([POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], ok=ok)


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def registry_state():
    result = {}
    for name, hive, path in [
        ("tip_class", winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Classes\CLSID\{FEB10355-3C08-5342-B75C-5873F1CA04DF}"),
        ("app_entry", winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{D89859C5-5A51-53E6-8199-DF3407D2908B}"),
        ("user_product", winreg.HKEY_CURRENT_USER, r"Software\StudyIME"),
        ("keyboard_preload", winreg.HKEY_CURRENT_USER, r"Keyboard Layout\Preload"),
    ]:
        try:
            with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                info = winreg.QueryInfoKey(key)
                values = [winreg.EnumValue(key, index) for index in range(info[1])]
                result[name] = {"exists": True, "values_sha256": sha256(json_bytes(values)), "subkeys": info[0], "last_write": info[2]}
        except FileNotFoundError: result[name] = {"exists": False}
    return result


class Checks:
    def __init__(self, name, package_hash):
        self.path = HERE / (name + ".json")
        self.data = {"recorded_at": datetime.now(timezone.utc).isoformat(), "package_sha256": package_hash,
                     "checks": [], "system_install_executed": False, "tsf_registration_executed": False,
                     "computer_use_executed": False}

    def check(self, name, condition, detail=None):
        self.data["checks"].append({"name": name, "passed": bool(condition), **({"detail": detail} if detail else {})})
        write_changed(self.path, json_bytes(self.data))
        print(("PASS " if condition else "FAIL ") + name, flush=True)
        if not condition: raise AssertionError(name)

    def finish(self):
        self.data["passed"] = sum(item["passed"] for item in self.data["checks"])
        self.data["total"] = len(self.data["checks"])
        write_changed(self.path, json_bytes(self.data))


def verify_archive(files, archive, work):
    report = Checks("package-validation", file_hash(archive))
    rebuilt = work / "second-export.zip"
    deterministic_zip(rebuilt, dict(reversed(list(files.items()))))
    report.check("package archive is byte-identical with reversed input order and another output directory", file_hash(rebuilt) == file_hash(archive))
    with zipfile.ZipFile(archive) as bundle:
        info = bundle.infolist()
        report.check("archive paths timestamps permissions and compression are canonical",
            [item.filename for item in info] == sorted(files) and all(item.date_time == (1980, 1, 1, 0, 0, 0)
            and item.compress_type == zipfile.ZIP_STORED and item.external_attr >> 16 == 0o100644 for item in info))
        report.check("all archive entries match their declared payload bytes", all(bundle.read(name) == content for name, content in files.items()))
    bad = ["../escape", "a/../b", "/absolute", "a\\b", "C:/data", "a//b", "CON.txt", "a ", "x.", "x:stream"]
    rejected = []
    for name in bad:
        try: package_path(name)
        except ValueError: rejected.append(name)
    report.check("Windows path traversal aliases devices and alternate streams are rejected", rejected == bad)
    try:
        deterministic_zip(work / "case-collision.zip", {"a": b"1", "A": b"2"})
        collision = False
    except ValueError: collision = True
    report.check("case-insensitive archive collisions are rejected", collision)
    try:
        payload("release")
        blocked = ""
    except ValueError as error: blocked = str(error)
    report.check("release packaging refuses pending human review and unresolved licenses", "human-lexicon-review" in blocked and "wtl-gpl-compatibility" in blocked)
    manifest = json.loads(files["package-manifest.json"])
    report.check("review preview is explicit and retains zero human approvals", manifest["mode"] == "preview" and not manifest["release_ready"] and manifest["lexicon_review"] == {"approved-for-distribution": 0, "pending": 200, "rejected": 0})
    report.check("runtime payload excludes historical fixtures and unrelated installer tools",
        "21 条测试".encode() not in files["data/user-template/lua/lexicon.lua"] and not any(
            any(word in name.lower() for word in ["cangjie", "bopomofo", "terra_pinyin", "stroke.", "7z.exe", "ui_probe", "packageprobe", "weaseldeployer"])
            for name in files))
    record = json.loads(files["source-provenance/native-build.json"])
    report.check("all four product binaries are recorded x64 images", len(record["binaries"]) == 4 and all(item["architecture"] == "x64" for item in record["binaries"].values()))
    roots = [str(ROOT), ROOT.as_posix()]
    encoded_roots = [path.encode(encoding) for path in roots for encoding in ["utf-8", "utf-16le"]]
    report.check("product PE images contain no checkout-specific absolute path",
        all(not any(path in files["bin/" + name] for path in encoded_roots) for name in record["binaries"]))
    # The previous build trusted timestamps and ignored a legacy class header.
    # Change its bytes without changing mtime and require the package gate to fail.
    header = CACHE / "weasel/include/WeaselUI.h"
    original_header, original_stat = header.read_bytes(), header.stat()
    try:
        header.write_bytes(original_header + b"\n// altered cached header\n")
        os.utime(header, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        try:
            native_build()
            rejected_header = False
        except ValueError as error:
            rejected_header = "input tree changed" in str(error)
        report.check("changed generated headers are rejected even when mtime is preserved", rejected_header)
    finally:
        header.write_bytes(original_header)
        os.utime(header, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    dependencies = set()
    for item in record["binaries"].values(): dependencies.update(name.lower() for name in item["imports"] + item["delay_imports"])
    runtime = json.loads(files["source-provenance/runtime-dependencies.json"])["rime.dll"]
    dependencies.update(name.lower() for name in runtime["imports"] + runtime["delay_imports"])
    system = {"kernel32.dll", "user32.dll", "gdi32.dll", "ole32.dll", "oleaut32.dll", "oleacc.dll", "advapi32.dll",
              "shell32.dll", "shlwapi.dll", "imm32.dll", "comctl32.dll", "uuid.dll", "usp10.dll", "d2d1.dll", "dwrite.dll",
              "dwmapi.dll", "uxtheme.dll", "msimg32.dll", "gdiplus.dll", "windowscodecs.dll", "bcrypt.dll", "dbghelp.dll",
              "version.dll", "rpcrt4.dll", "msvcrt.dll", "api-ms-win-shcore-scaling-l1-1-1.dll"}
    report.check("all static and delayed DLL imports are Windows system libraries", dependencies <= system, sorted(dependencies))
    report.finish()


def verify_installer(files, root, work, archive):
    report = Checks("installer-plans", file_hash(archive))
    before = registry_state()
    common = quote(root / "scripts/Common.ps1")
    # Tests run the actual default entry points; no -Apply argument is present.
    plans = {}
    for name in ["Install", "Uninstall"]:
        raw = powershell("& " + quote(root / (name + ".ps1")))
        plan = json.loads(raw.stdout.decode("utf-8-sig"))
        plans[name.lower()] = plan
        report.check(name.lower() + " defaults to a reviewable plan with no apply", plan["apply_requested"] is False)
    report.check("plan records the independent CLSID and keeps default input selection", plans["install"]["registry_class"].endswith("{FEB10355-3C08-5342-B75C-5873F1CA04DF}") and plans["install"]["default_input_method_changed"] is False)
    target = Path(plans["install"]["target"])
    report.check("dry-run leaves the installation target absent", not target.exists())
    report.check("uninstall plan preserves user data modified files and applications", plans["uninstall"]["preserve_user_data"] and plans["uninstall"]["preserve_unlisted_or_modified_files"] and not plans["uninstall"]["terminate_other_applications"])
    bad = ["../escape", "folder/../escape", "a\\b", "a//b", "C:/data", "NUL.txt", "x:stream", "space "]
    script = "$ErrorActionPreference='Stop'; . " + common + "; $rejected=0; foreach($value in @(" + ",".join(quote(n) for n in bad) + ")) { try { $null=Resolve-StudyChild " + quote(root) + " $value } catch { $rejected++ } }; Write-Output $rejected"
    rejected = int(powershell(script).stdout.strip())
    report.check("installer independently rejects unsafe manifest paths", rejected == len(bad))
    check_command = "$ErrorActionPreference='Stop'; . " + common + "; $null=Get-StudyPackage " + quote(root)
    readme = root / "README.txt"
    original = readme.read_bytes()
    try:
        readme.write_bytes(original + b"tamper")
        result = powershell(check_command, ok=False)
        report.check("installer refuses a modified payload before any apply step", result.returncode != 0)
    finally: readme.write_bytes(original)
    extra = root / "unexpected.txt"
    try:
        extra.write_text("not in manifest", encoding="ascii")
        result = powershell(check_command, ok=False)
        report.check("installer refuses unlisted payload files", result.returncode != 0)
    finally:
        if extra.resolve().is_relative_to(work.resolve()): extra.unlink()
    manifest_path = root / "package-manifest.json"
    original = manifest_path.read_bytes()
    try:
        value = json.loads(original)
        value["files"].append({**value["files"][0], "path": value["files"][0]["path"].upper()})
        manifest_path.write_bytes(json_bytes(value))
        report.check("installer rejects manifest case collisions", powershell(check_command, ok=False).returncode != 0)
    finally: manifest_path.write_bytes(original)
    script = "$ErrorActionPreference='Stop'; . " + common + "; $p=Get-StudyPackage " + quote(root) + "; $null=Get-StudyReceipt $p"
    report.check("uninstaller cannot apply to an extracted package without its install receipt", powershell(script, ok=False).returncode != 0)
    # Metadata must be branded on the actual files, including the TSF DLL.
    script = "$r=@(); foreach($p in Get-ChildItem -LiteralPath " + quote(root / "bin") + " -Filter 'StudyIME.*') { $r += @{name=$p.Name;product=$p.VersionInfo.ProductName;version=$p.VersionInfo.FileVersion;company=$p.VersionInfo.CompanyName} }; ConvertTo-Json -InputObject $r"
    metadata = json.loads(powershell(script).stdout.decode("utf-8-sig"))
    report.check("all four PE resources carry StudyIME product version and contributor identity", len(metadata) == 4 and all(item["product"] == product()["name"] + " (StudyIME)" and item["version"] == product()["version"] and item["company"] == "StudyIME contributors" for item in metadata))
    after = registry_state()
    report.check("product registration and keyboard settings are unchanged", before == after)
    report.data["plans"] = plans
    report.data["registry_before"] = before
    report.data["registry_after"] = after
    report.data["scope_limit"] = "Real PowerShell default plans, validation and PE metadata. Apply/rollback/locked-file cleanup and TSF registration are not executed."
    report.finish()


def verify_runtime(root, work, archive):
    report = Checks("product-runtime-x64", file_hash(archive))
    report.data["runtime_file_hashes"] = {file.relative_to(root).as_posix(): file_hash(file)
        for folder in [root / "bin", root / "data/shared", root / "data/user-template"]
        for file in sorted(folder.rglob("*")) if file.is_file()}
    report.data["runtime_file_hashes"]["product.json"] = file_hash(root / "product.json")
    before = registry_state()
    normal_data = Path(os.environ["LOCALAPPDATA"]) / "StudyIME"
    normal_existed = normal_data.exists()
    env = {**os.environ, "STUDYIME_DEV_SESSION": uuid.uuid4().hex,
           "STUDYIME_DEV_DATA_ROOT": str((work / "isolated user data 中文").resolve())}
    service = root / "bin/StudyIME.Service.exe"
    registrar = root / "bin/StudyIME.Registrar.exe"
    for name in ["StudyIME.Service.exe", "StudyIME.Settings.exe"]:
        result = json.loads(run([root / "bin" / name, "--identity"], env=env).stdout)
        report.check(name + " identity matches the shipped manifest", result == product())
    result = json.loads(run([registrar, "--inspect"], env=env).stdout)
    report.check("unregistered TSF DLL has the product GUID and rejects another class GUID", result["identity_matches"] and result["factory_guid_isolated"] and not result["registration_executed"])
    started = time.monotonic()
    deployed = run([service, "--prepare-data"], env=env, timeout=60)
    report.check("packaged text dictionaries deploy into the isolated user directory", (Path(env["STUDYIME_DEV_DATA_ROOT"]) / "rime/build/study.schema.yaml").exists(), {"seconds": round(time.monotonic() - started, 3)})
    try:
        run([service, "--ensure-running"], env=env, timeout=10)
        report.check("service starts on demand from the relocated package", True)
        probe_report = work / "runtime-probe.json"
        result = run([CACHE / "build/bin/StudyIME.PackageProbe.exe", probe_report], env=env, timeout=30, ok=False)
        checks = json.loads(probe_report.read_text(encoding="utf-8")) if probe_report.exists() else {"checks": []}
        report.check("five samples traverse the packaged Chinese data Lua and commit paths", result.returncode == 0 and len(checks["checks"]) == 22 and all(item["passed"] for item in checks["checks"]), checks)
    finally:
        stopped = run([service, "--stop"], env=env, timeout=15, ok=False)
        report.check("the dedicated stop operation joins its own service", stopped.returncode == 0)
    report.check("runtime checks leave system registration and real user data untouched", before == registry_state() and normal_data.exists() == normal_existed)
    report.data["relocated_package"] = str(root)
    report.data["user_data"] = env["STUDYIME_DEV_DATA_ROOT"]
    report.data["scope_limit"] = "Packaged binaries, independent pipe, exact DLL class identity and real Rime IPC; no registered TSF activation or physical keyboard/mouse."
    report.finish()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--section", choices=["archive", "installer", "runtime", "all"], default="all")
    args = parser.parse_args()
    files, manifest = payload()
    archive = CACHE / "dist" / f"StudyIME-{product()['version']}-windows-x64-preview.zip"
    work = CACHE / "verification" / uuid.uuid4().hex[:12]
    work.mkdir(parents=True)
    root = work / "relocated 中文 path"
    stage(files, root)
    if args.section in ["archive", "all"]: verify_archive(files, archive, work)
    if args.section in ["installer", "all"]: verify_installer(files, root, work, archive)
    if args.section in ["runtime", "all"]: verify_runtime(root, work, archive)
    print("Targeted packaging verification complete; no system installation or TSF registration.")


if __name__ == "__main__": main()
