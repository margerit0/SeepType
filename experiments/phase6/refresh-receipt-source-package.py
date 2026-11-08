"""Bind the installer fix to the previously reproduced dev.2 source package.

Uses a frozen committed patch, never the concurrent lexicon working tree.
Reuses and verifies the independent native build, reruns the changed receipt
script under Windows PowerShell 5.1, and reproduces the corrected runtime ZIP.
This is an incremental source-package check, not a new empty-cache build.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.packaging.common import deterministic_zip, file_hash, json_bytes, package_path, sha256

DIST = ROOT / ".cache/packaging/dist"
RESULTS = ROOT / "experiments/phase6/results/source-receipt-update-20261108"
SOURCE_NAME = "StudyIME-0.5.0-dev.2-source-materials.zip"
RUNTIME_NAME = "StudyIME-0.5.0-dev.2-windows-x64-preview.zip"
BASELINE_HASH = "926e8ce52f14b50f4e94471806502f0fcb3fef7f547b7e24ef6e3230a221bb25"
RUNTIME_HASH = "c1c429adee39465f0740bf7ac6111dad799d097a83e39019a5975d02acf3648e"
REVISION = "b913b55d198c9aafbe95f31adc2c58a69e767193"
PATCH_FILES = (
    "docs/packaging.md",
    "experiments/phase4/start-text-host.py",
    "experiments/phase4/tsf_text_host.cpp",
    "packaging/windows/Common.ps1",
    "tools/packaging/verify-receipt.ps1",
)


def read_zip(path):
    with zipfile.ZipFile(path) as archive:
        result = {}
        for item in archive.infolist():
            package_path(item.filename)
            if item.filename in result:
                raise ValueError("Duplicate source member: " + item.filename)
            result[item.filename] = archive.read(item)
        return result


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    previous = json.loads((ROOT / "experiments/phase6/results/source-materials.json").read_bytes())
    workspace = Path(previous["workspace"]).resolve()
    cache = (ROOT / ".cache/packaging/source-check").resolve()
    if not workspace.is_relative_to(cache) or workspace == cache:
        raise ValueError("Independent workspace is outside the named source-check cache")
    if not previous["fresh_cache_native_build_passed"] or not previous["all_native_binaries_identical"]:
        raise ValueError("No successful native source-build baseline")
    tested_archive = workspace.parents[1] / "source-second-export.zip"
    if file_hash(tested_archive) != previous["source_archive_sha256"]:
        raise ValueError("Previously tested source archive changed")
    baseline = DIST / "before-receipt-fix-20261108" / SOURCE_NAME
    if file_hash(baseline) != BASELINE_HASH:
        raise ValueError("Distributed baseline source archive changed")
    if file_hash(DIST / RUNTIME_NAME) != RUNTIME_HASH:
        raise ValueError("Corrected runtime archive changed")
    original = read_zip(baseline)
    files = dict(original)
    for name in PATCH_FILES:
        files["project/" + name] = subprocess.check_output(["git", "show", REVISION + ":" + name], cwd=ROOT)
    # Keep historical packaging notes intact and state the new source boundary
    # in a separate shipped note rather than rewriting past build evidence.
    files["SOURCE-UPDATE.txt"] = (
        "StudyIME dev.2 incremental source update, 2026-11-08\n"
        f"Baseline source ZIP SHA256: {BASELINE_HASH}\n"
        f"Selected committed updates: {REVISION}\n"
        + "\n".join(PATCH_FILES) + "\n\n"
        "The Windows PowerShell 5.1 receipt fix is included. Historical notes\n"
        "about an out-of-date source ZIP are superseded by this file.\n"
        "Native/Rime inputs and upstream materials retain the verified baseline.\n"
        "The changed receipt script is checked in the independent source tree;\n"
        "that tree reproduces the corrected runtime ZIP without recompilation.\n"
        "This is not a new empty-cache or cross-machine native build.\n"
        "Concurrent lexicon-expansion drafts are not part of this package.\n"
    ).encode("utf-8")
    tested = read_zip(tested_archive)
    build = json.loads((workspace / ".cache/packaging/build/native-build.json").read_bytes())
    engine = json.loads((workspace / ".cache/rime-build/rime-build.json").read_bytes())
    for inputs in (build["inputs"], engine["project_inputs"]):
        for name, digest in inputs.items():
            if sha256(files["project/" + name]) != digest or file_hash(workspace / name) != digest:
                raise ValueError("Native input changed: " + name)
    for name, item in build["binaries"].items():
        if file_hash(workspace / ".cache/packaging/build/bin" / name) != item["sha256"]:
            raise ValueError("Independent native binary changed: " + name)
    if file_hash(workspace / engine["binary"]["path"]) != engine["binary"]["sha256"]:
        raise ValueError("Independent Rime binary changed")
    materials = json.loads(files["source-materials.json"])["materials"]
    for item in materials:
        if sha256(files[item["path"]]) != item["sha256"] or file_hash(workspace / item["restore"]) != item["sha256"]:
            raise ValueError("Supplied/restored material changed: " + item["path"])
    for name, content in tested.items():
        if name.startswith("project/"):
            path = workspace / name[8:]
            allowed = {sha256(content), sha256(files[name])}
            if file_hash(path) not in allowed:
                raise ValueError("Independent project file changed: " + name)
    candidate = ROOT / ".cache/packaging/verification/receipt-source-update.zip"
    deterministic_zip(candidate, files)
    second = ROOT / ".cache/packaging/verification/receipt-source-repeat.zip"
    deterministic_zip(second, files)
    if file_hash(candidate) != file_hash(second):
        raise ValueError("Frozen source export is not deterministic")
    # Apply only source members to the already verified independent workspace.
    for name, content in files.items():
        if not name.startswith("project/"):
            continue
        destination = (workspace / name[8:]).resolve()
        if not destination.is_relative_to(workspace):
            raise ValueError("Project member escapes independent workspace")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or destination.read_bytes() != content:
            destination.write_bytes(content)
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    receipt_output = RESULTS / "receipt-from-source.json"
    with (RESULTS / "source-validation.log").open("wb") as output:
        subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        str(workspace / "tools/packaging/verify-receipt.ps1"), "-Output", str(receipt_output)],
                       cwd=workspace, stdout=output, stderr=subprocess.STDOUT,
                       creationflags=subprocess.CREATE_NO_WINDOW, check=True, timeout=60)
        subprocess.run([sys.executable, "tools/packaging/package.py", "--mode", "preview"],
                       cwd=workspace, stdout=output, stderr=subprocess.STDOUT,
                       creationflags=subprocess.CREATE_NO_WINDOW, check=True, timeout=180)
    reproduced = workspace / ".cache/packaging/dist" / RUNTIME_NAME
    if file_hash(reproduced) != RUNTIME_HASH:
        raise ValueError("Independent source tree did not reproduce the corrected runtime ZIP")
    receipt = json.loads(receipt_output.read_bytes())
    if receipt["passed"] != 4 or not receipt["powershell"].startswith("5.1."):
        raise ValueError("Windows PowerShell 5.1 receipt validation did not pass")
    current = DIST / SOURCE_NAME
    shutil.copyfile(candidate, current)
    report_path = DIST / "package-report.json"
    package_report = json.loads(report_path.read_bytes())
    package_report["archives"][SOURCE_NAME] = {"sha256": file_hash(current), "bytes": current.stat().st_size}
    package_report["archives"][RUNTIME_NAME] = {"sha256": RUNTIME_HASH, "bytes": (DIST / RUNTIME_NAME).stat().st_size}
    report_path.write_bytes(json_bytes(package_report))
    (DIST / "SHA256SUMS.txt").write_text("".join(f"{item['sha256']}  {name}\n" for name, item in sorted(package_report["archives"].items())), encoding="utf-8")
    result = {
        "recorded_at": datetime.now(timezone.utc).isoformat(), "status": "passed",
        "baseline_source_archive_sha256": BASELINE_HASH, "patch_revision": REVISION,
        "source_archive_sha256": file_hash(current), "runtime_archive_sha256": RUNTIME_HASH,
        "source_files_updated": list(PATCH_FILES), "project_file_count": sum(n.startswith("project/") for n in files),
        "source_export_repeated_identically": True, "verified_upstream_materials": len(materials),
        "unchanged_native_inputs": len(build["inputs"]), "unchanged_rime_inputs": len(engine["project_inputs"]),
        "receipt_checks_passed": receipt["passed"], "powershell": receipt["powershell"],
        "independent_workspace": str(workspace), "reproduced_runtime_identical": True,
        "native_recompiled": False, "fresh_empty_cache_build": False,
        "system_install_executed": False, "tsf_registration_executed": False, "network_used": False,
        "scope": "Incremental script/source update over the preserved successful native rebuild; no concurrent lexicon edits included.",
    }
    (RESULTS / "summary.json").write_bytes(json_bytes(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
