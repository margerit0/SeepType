"""Restore and optionally build the supplied materials in a fresh local cache.

This is source-package validation only. It runs no historical tests, installer,
registration tool, installed TIP or Computer Use operation.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import subprocess
import sys
import time
import uuid
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, deterministic_zip, file_hash, json_bytes, package_path, product, write_changed
from tools.packaging.package import source_materials


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    archive = CACHE / "dist" / f"StudyIME-{product()['version']}-source-materials.zip"
    work = CACHE / "source-check" / ("fresh 中文 " + uuid.uuid4().hex[:12])
    work.mkdir(parents=True)
    second = work / "source-second-export.zip"
    deterministic_zip(second, source_materials())
    if file_hash(archive) != file_hash(second): raise ValueError("Source-material archive is not reproducible")
    extraction = work / "materials"
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            package_path(info.filename)
            if info.external_attr >> 16 & 0o170000 != 0o100000: raise ValueError("Unexpected source-package file type")
            destination = extraction / info.filename
            if not destination.resolve().is_relative_to(extraction.resolve()): raise ValueError("Source path escapes extraction root")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, destination.open("wb") as output:
                while chunk := source.read(1024 * 1024): output.write(chunk)
    project = extraction / "project"
    log = work / "source-workflow.log"
    started = time.monotonic()
    with log.open("wb") as output:
        result = subprocess.run([sys.executable, "tools/packaging/bootstrap_sources.py", ".."], cwd=project,
            stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW, timeout=180)
        if result.returncode: raise RuntimeError(f"Offline source restore failed; see {log}")
        if args.build:
            # CL/Ninja need a shared output code page even when launched by a
            # headless verifier. Give this build its own hidden console;
            # build.cmd selects UTF-8 without affecting the user's terminal.
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            result = subprocess.run(["cmd.exe", "/d", "/c", "tools\\packaging\\build.cmd"], cwd=project,
                stdout=output, stderr=subprocess.STDOUT, startupinfo=startup,
                creationflags=subprocess.CREATE_NEW_CONSOLE, timeout=1200)
            if result.returncode: raise RuntimeError(f"Fresh-cache native build failed; see {log}")
            result = subprocess.run([sys.executable, "tools/packaging/package.py", "--mode", "preview"], cwd=project,
                stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW, timeout=120)
            if result.returncode: raise RuntimeError(f"Fresh-cache package export failed; see {log}")
    report = {"recorded_at": datetime.now(timezone.utc).isoformat(), "source_archive_sha256": file_hash(archive),
              "second_export_identical": True, "offline_restore_passed": True, "fresh_cache_native_build_passed": args.build,
              "workspace": str(project), "log": str(log), "seconds": round(time.monotonic() - started, 3),
              "network_used": False, "system_install_executed": False, "tsf_registration_executed": False,
              "historical_tests_executed": False, "same_machine_toolchain": True}
    if args.build:
        original = json.loads((CACHE / "build/native-build.json").read_text(encoding="utf-8"))
        rebuilt = json.loads((project / ".cache/packaging/build/native-build.json").read_text(encoding="utf-8"))
        report["compiler"] = rebuilt["compiler"]
        report["identical_recorded_inputs"] = all(original[key] == rebuilt[key]
            for key in ["inputs", "generated_inputs", "dependency_inputs", "toolchain", "cache_fingerprint",
                        "include_trace_sha256", "included_header_count", "wtl_compiled"])
        report["native_binaries"] = {name: {"original_sha256": item["sha256"], "fresh_build_sha256": rebuilt["binaries"][name]["sha256"],
            "byte_identical": item["sha256"] == rebuilt["binaries"][name]["sha256"]} for name, item in original["binaries"].items()}
        report["scope_limit"] = "Buildability verified with the existing local VS2019 toolchain in a fresh project/cache. Cross-machine native binary identity is not asserted."
        report["all_native_binaries_identical"] = all(item["byte_identical"] for item in report["native_binaries"].values())
        engine = json.loads((ROOT / ".cache/rime-build/rime-build.json").read_bytes())
        fresh_engine = json.loads((project / ".cache/rime-build/rime-build.json").read_bytes())
        report["rime_engine"] = {"record_identical": engine == fresh_engine,
            "original_sha256": engine["binary"]["sha256"], "fresh_build_sha256": fresh_engine["binary"]["sha256"],
            "byte_identical": engine["binary"]["sha256"] == fresh_engine["binary"]["sha256"],
            "plugins": fresh_engine["plugins"], "official_binary_used": False}
        runtime_name = f"StudyIME-{product()['version']}-windows-x64-preview.zip"
        report["runtime_archive"] = {"original_sha256": file_hash(CACHE / "dist" / runtime_name),
            "fresh_build_sha256": file_hash(project / ".cache/packaging/dist" / runtime_name)}
        report["runtime_archive"]["byte_identical"] = report["runtime_archive"]["original_sha256"] == report["runtime_archive"]["fresh_build_sha256"]
    write_changed(ROOT / "experiments/phase6/results/source-materials.json", json_bytes(report))
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if args.build and not (report["identical_recorded_inputs"] and report["all_native_binaries_identical"] and
                          report["rime_engine"]["record_identical"] and report["rime_engine"]["byte_identical"] and report["runtime_archive"]["byte_identical"]):
        raise RuntimeError("Fresh-directory native build differs; see the saved source-materials report")


if __name__ == "__main__": main()
