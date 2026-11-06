"""Bind retained runtime evidence to an updated package by exact file hashes.

Installer/docs-only edits need not repeat the already passed real engine test.
This performs hash verification only; it never labels a hash check a new run.
"""
from pathlib import Path
import json
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, file_hash, json_bytes, product, sha256, write_changed


def main():
    report_path = ROOT / "experiments/phase6/results/product-runtime-x64.json"
    runtime = json.loads(report_path.read_text(encoding="utf-8"))
    if runtime.get("passed") != runtime.get("total") or not runtime.get("total"):
        raise ValueError("The saved runtime run did not fully pass")
    hashes = runtime.get("runtime_file_hashes")
    if not hashes:
        # The first run predated the hash-subset field. Require an original
        # archive with its exact recorded digest and the retained tested files.
        matches = [path for path in (CACHE / "verification").glob("*/second-export.zip")
                   if file_hash(path) == runtime["package_sha256"]]
        if not matches: raise ValueError("The original tested archive is unavailable")
        tested = Path(runtime["relocated_package"])
        hashes = {}
        with zipfile.ZipFile(matches[0]) as archive:
            for name in archive.namelist():
                if name == "product.json" or name.startswith(("bin/", "data/shared/", "data/user-template/")):
                    digest = sha256(archive.read(name))
                    if file_hash(tested / name) != digest: raise ValueError("Retained tested files have changed")
                    hashes[name] = digest
        runtime["runtime_file_hashes"] = hashes
        runtime["hash_binding_note"] = "Added after the run from the retained tested directory and an archive matching the original reported package digest; no runtime checks were rerun."
        write_changed(report_path, json_bytes(runtime))
    current = CACHE / "dist" / f"StudyIME-{product()['version']}-windows-x64-preview.zip"
    with zipfile.ZipFile(current) as archive:
        for name, expected in hashes.items():
            if sha256(archive.read(name)) != expected:
                raise ValueError(f"Runtime input changed; a new relevant runtime check is required: {name}")
    result = {"schema_version": 1, "current_package_sha256": file_hash(current),
              "runtime_tested_package_sha256": runtime["package_sha256"],
              "runtime_report_sha256": file_hash(report_path), "identical_runtime_files": hashes,
              "runtime_rerun": False, "scope": "Exact native/runtime-data/identity hash match; installer and documentation changes are checked separately."}
    write_changed(ROOT / "experiments/phase6/results/runtime-evidence-binding.json", json_bytes(result))
    print(f"Verified {len(hashes)} runtime inputs unchanged; existing real-engine evidence remains applicable.")


if __name__ == "__main__": main()
