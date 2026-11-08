"""Verify and publish the script-only uninstall fix over frozen source materials.

Never includes the concurrent lexicon working tree, compiles native code, or
installs a TIP. The previous archives and all historical reports are preserved.
"""
from datetime import datetime, timezone
import argparse
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
from tools.packaging.package import payload, stage

DIST = ROOT / ".cache/packaging/dist"
RESULTS = ROOT / "experiments/phase6/results/source-uninstall-update-20261108"
SOURCE_NAME = "StudyIME-0.5.0-dev.2-source-materials.zip"
RUNTIME_NAME = "StudyIME-0.5.0-dev.2-windows-x64-preview.zip"
BASE_SOURCE = "8541dd9a6b9441796219578f04e1eb8b52192fe3e0a6b931e9a1e6de89478322"
BASE_RUNTIME = "c1c429adee39465f0740bf7ac6111dad799d097a83e39019a5975d02acf3648e"
PATCH_FILES = (
    "packaging/windows/Common.ps1", "packaging/windows/Uninstall.ps1",
    "tools/packaging/verify-uninstall-registry.ps1", "docs/packaging.md",
    "tools/packaging/verify.py",
)


def read_zip(path):
    with zipfile.ZipFile(path) as archive:
        files = {}
        for item in archive.infolist():
            package_path(item.filename)
            if item.filename in files:
                raise ValueError("Duplicate archive member: " + item.filename)
            files[item.filename] = archive.read(item)
        return files


def changed(before, after):
    return sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-validation", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    previous = json.loads((ROOT / "experiments/phase6/results/source-receipt-update-20261108/summary.json").read_bytes())
    if not previous["reproduced_runtime_identical"] or previous["source_archive_sha256"] != BASE_SOURCE:
        raise ValueError("Verified receipt source baseline is missing")
    workspace = Path(previous["independent_workspace"]).resolve()
    allowed = (ROOT / ".cache/packaging/source-check").resolve()
    if workspace == allowed or not workspace.is_relative_to(allowed):
        raise ValueError("Unexpected independent workspace")
    backup = DIST / "before-uninstall-fix-20261108"
    backup.mkdir(exist_ok=True)
    for name, expected in ((SOURCE_NAME, BASE_SOURCE), (RUNTIME_NAME, BASE_RUNTIME)):
        destination = backup / name
        if not destination.exists():
            if file_hash(DIST / name) != expected:
                raise ValueError("Current archive is not the expected baseline: " + name)
            shutil.copyfile(DIST / name, destination)
        if file_hash(destination) != expected:
            raise ValueError("Preserved baseline archive changed: " + name)
    for name in ("package-report.json", "SHA256SUMS.txt"):
        if not (backup / name).exists():
            shutil.copyfile(DIST / name, backup / name)

    old_source = read_zip(backup / SOURCE_NAME)
    files = dict(old_source)
    patch = {name: (ROOT / name).read_bytes() for name in PATCH_FILES}
    files.update({"project/" + name: content for name, content in patch.items()})
    files["SOURCE-UPDATE.txt"] += (
        "\nUninstall update, 2026-11-08\n"
        f"Prior source ZIP SHA256: {BASE_SOURCE}\n"
        f"Prior runtime ZIP SHA256: {BASE_RUNTIME}\n"
        "The uninstall script removes only the observed, empty, owned TIP\n"
        "containers after successful native unregistration. Nonempty and\n"
        "unfamiliar branches are preserved. The production function is tested\n"
        "under Windows PowerShell 5.1 in isolated HKCU registry fixtures.\n"
        "Native inputs and upstream materials remain unchanged.\n"
        "Updated docs/packaging.md supersedes historical installation status\n"
        "in other bundled notes. Browser acceptance was skipped by the user.\n"
        "The current machine still needs a Windows restart and a final retry\n"
        "to release the mapped TSF DLL; complete uninstall is not claimed.\n"
        "No concurrent lexicon-expansion drafts are included.\n"
    ).encode("utf-8")
    build = json.loads((workspace / ".cache/packaging/build/native-build.json").read_bytes())
    engine = json.loads((workspace / ".cache/rime-build/rime-build.json").read_bytes())
    for inputs in (build["inputs"], engine["project_inputs"]):
        for name, digest in inputs.items():
            if sha256(files["project/" + name]) != digest or file_hash(workspace / name) != digest:
                raise ValueError("Native build input changed: " + name)
    for name, content in old_source.items():
        if not name.startswith("project/"):
            continue
        destination = workspace / name[8:]
        if file_hash(destination) not in {sha256(content), sha256(files[name])}:
            raise ValueError("Independent source file changed: " + name)
    for name, item in build["binaries"].items():
        if file_hash(workspace / ".cache/packaging/build/bin" / name) != item["sha256"]:
            raise ValueError("Independent native binary changed: " + name)
    if file_hash(workspace / engine["binary"]["path"]) != engine["binary"]["sha256"]:
        raise ValueError("Independent Rime binary changed")
    materials = json.loads(files["source-materials.json"])["materials"]
    for item in materials:
        if sha256(files[item["path"]]) != item["sha256"] or file_hash(workspace / item["restore"]) != item["sha256"]:
            raise ValueError("Upstream material changed: " + item["path"])
    for name, content in patch.items():
        destination = (workspace / name).resolve()
        if not destination.is_relative_to(workspace):
            raise ValueError("Source patch escapes the independent workspace")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

    candidate_runtime = ROOT / ".cache/packaging/verification/uninstall-runtime-candidate.zip"
    if args.resume_validation:
        runtime_files = read_zip(candidate_runtime)
        if runtime_files["scripts/Common.ps1"] != patch["packaging/windows/Common.ps1"] or runtime_files["Uninstall.ps1"] != patch["packaging/windows/Uninstall.ps1"]:
            raise ValueError("Cannot reuse validation after production scripts change")
    else:
        runtime_files, _ = payload()
    runtime_changes = changed(read_zip(backup / RUNTIME_NAME), runtime_files)
    if runtime_changes != ["Uninstall.ps1", "package-manifest.json", "scripts/Common.ps1"]:
        raise ValueError("Unexpected runtime payload changes: " + repr(runtime_changes))
    # Large archives stay in the ignored cache, not in tracked evidence.
    deterministic_zip(candidate_runtime, runtime_files)
    candidate_source = ROOT / ".cache/packaging/verification/uninstall-source-candidate.zip"
    repeated_source = ROOT / ".cache/packaging/verification/uninstall-source-repeat.zip"
    deterministic_zip(candidate_source, files)
    deterministic_zip(repeated_source, files)
    if file_hash(candidate_source) != file_hash(repeated_source):
        raise ValueError("Repeated source export differs")

    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    if args.resume_validation:
        for name, total in (("registry-from-source.json", 8), ("receipt-from-source.json", 4)):
            prior = json.loads((RESULTS / name).read_bytes())
            if prior["passed"] != total or prior["common_sha256"] != sha256(patch["packaging/windows/Common.ps1"]):
                raise ValueError("Cannot reuse incompatible script validation: " + name)
        archive_report = json.loads((workspace / "experiments/phase6/results/package-validation.json").read_bytes())
        if archive_report["passed"] != 15 or archive_report["package_sha256"] != file_hash(candidate_runtime):
            raise ValueError("Cannot reuse incompatible archive validation")
        if file_hash(workspace / ".cache/packaging/dist" / RUNTIME_NAME) != file_hash(candidate_runtime):
            raise ValueError("Cannot reuse a different independent runtime export")
        if not (RESULTS / "initial-installer-assumption-failure.log").exists():
            shutil.copyfile(RESULTS / "validation.log", RESULTS / "initial-installer-assumption-failure.log")
            shutil.copyfile(workspace / "experiments/phase6/results/installer-plans.json", RESULTS / "installer-plans-initial.json")
    with (RESULTS / "validation.log").open("ab" if args.resume_validation else "wb") as log:
        commands = [
            ([sys.executable, "tools/packaging/package.py", "--mode", "preview"], 240),
            ([str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
              str(workspace / "tools/packaging/verify-uninstall-registry.ps1"), "-Output", str(RESULTS / "registry-from-source.json")], 60),
            ([str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
              str(workspace / "tools/packaging/verify-receipt.ps1"), "-Output", str(RESULTS / "receipt-from-source.json")], 60),
            ([sys.executable, "tools/packaging/verify.py", "--section", "archive"], 120),
            ([sys.executable, "tools/packaging/verify.py", "--section", "installer"], 120),
        ]
        if args.resume_validation:
            # Only the verification harness changed. Preserve its original
            # failed report and rerun the affected installer checks.
            commands = commands[-1:]
        for command, timeout in commands:
            subprocess.run(command, cwd=workspace, stdout=log, stderr=subprocess.STDOUT,
                           creationflags=subprocess.CREATE_NO_WINDOW, check=True, timeout=timeout)
    reproduced = workspace / ".cache/packaging/dist" / RUNTIME_NAME
    if file_hash(reproduced) != file_hash(candidate_runtime):
        raise ValueError("Independent source does not reproduce the new runtime ZIP")
    registry = json.loads((RESULTS / "registry-from-source.json").read_bytes())
    receipt = json.loads((RESULTS / "receipt-from-source.json").read_bytes())
    if registry["passed"] != 8 or receipt["passed"] != 4:
        raise ValueError("Changed PowerShell script validation failed")
    for name in ("package-validation.json", "installer-plans.json"):
        shutil.copyfile(workspace / "experiments/phase6/results" / name, RESULTS / name)

    stage_root = (ROOT / ".cache/packaging/stage/StudyIME-0.5.0-dev.2").resolve()
    if not stage_root.is_relative_to((ROOT / ".cache/packaging/stage").resolve()):
        raise ValueError("Unsafe output stage")
    stage(runtime_files, stage_root)
    shutil.copyfile(candidate_runtime, DIST / RUNTIME_NAME)
    shutil.copyfile(candidate_source, DIST / SOURCE_NAME)
    report = json.loads((workspace / ".cache/packaging/dist/package-report.json").read_bytes())
    report["stage"] = str(stage_root)
    report["archives"] = {name: {"sha256": file_hash(DIST / name), "bytes": (DIST / name).stat().st_size}
                          for name in (SOURCE_NAME, RUNTIME_NAME)}
    (DIST / "package-report.json").write_bytes(json_bytes(report))
    (DIST / "SHA256SUMS.txt").write_text("".join(f"{item['sha256']}  {name}\n" for name, item in sorted(report["archives"].items())), encoding="utf-8")
    summary = {
        "recorded_at": datetime.now(timezone.utc).isoformat(), "status": "passed",
        "baseline_source_archive_sha256": BASE_SOURCE, "baseline_runtime_archive_sha256": BASE_RUNTIME,
        "source_archive_sha256": file_hash(DIST / SOURCE_NAME), "runtime_archive_sha256": file_hash(DIST / RUNTIME_NAME),
        "runtime_manifest_sha256": sha256(runtime_files["package-manifest.json"]),
        "source_changes": changed(old_source, files), "runtime_changes": runtime_changes,
        "patch_file_hashes": {name: sha256(content) for name, content in patch.items()},
        "registry_checks_passed": registry["passed"], "receipt_checks_passed": receipt["passed"],
        "powershell": registry["powershell"], "verified_upstream_materials": len(materials),
        "unchanged_native_inputs": len(build["inputs"]), "unchanged_rime_inputs": len(engine["project_inputs"]),
        "source_export_repeated_identically": True, "reproduced_runtime_identical": True,
        "validation_resumed": args.resume_validation,
        "runtime_export_reused": args.resume_validation,
        "independent_workspace": str(workspace), "native_recompiled": False, "fresh_empty_cache_build": False,
        "network_used": False, "system_install_executed": False, "tsf_registration_executed": False,
        "scope": "Script-only source update over verified native artifacts; targeted source and package checks. Physical UI evidence is reused only for identical binaries/data. Final installed DLL deletion still awaits Windows restart."
    }
    (RESULTS / "summary.json").write_bytes(json_bytes(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
