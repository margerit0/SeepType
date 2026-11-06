"""Verify final source-package docs edits did not change the tested build inputs."""
from pathlib import Path
import json
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, file_hash, json_bytes, product, sha256, write_changed
from tools.packaging.package import source_materials
from tools.packaging.common import deterministic_zip


def main():
    report = json.loads((ROOT / "experiments/phase6/results/source-materials.json").read_text(encoding="utf-8"))
    if not report["fresh_cache_native_build_passed"]: raise ValueError("The source build did not pass")
    project = Path(report["workspace"])
    old_archive = project.parents[1] / "source-second-export.zip"
    if file_hash(old_archive) != report["source_archive_sha256"]: raise ValueError("The tested source archive changed")
    current = CACHE / "dist" / f"StudyIME-{product()['version']}-source-materials.zip"
    final_repeat = CACHE / "verification/final-source-repeat.zip"
    deterministic_zip(final_repeat, source_materials())
    if file_hash(final_repeat) != file_hash(current): raise ValueError("Final source ZIP differs on a second export")
    build = json.loads((project / ".cache/packaging/build/native-build.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(old_archive) as previous, zipfile.ZipFile(current) as archive:
        expected = {info.filename: sha256(previous.read(info)) for info in previous.infolist()}
        actual = {info.filename: sha256(archive.read(info)) for info in archive.infolist()}
        changed = sorted(name for name in expected.keys() | actual.keys() if expected.get(name) != actual.get(name))
        if any(not (name.startswith("project/docs/") or name == "project/README.md") for name in changed):
            raise ValueError("Non-document source material changed after verification: " + ", ".join(changed))
        for name, digest in build["inputs"].items():
            if actual["project/" + name] != digest: raise ValueError("A native build input differs: " + name)
    result = {"current_source_archive_sha256": file_hash(current), "tested_source_archive_sha256": report["source_archive_sha256"],
              "second_export_identical": True, "unchanged_native_build_inputs": len(build["inputs"]),
              "documentation_changes": changed, "source_build_rerun": False,
              "scope": "Only documentation differs from the already restored and compiled source archive; every other member and native build input is unchanged."}
    write_changed(ROOT / "experiments/phase6/results/source-evidence-binding.json", json_bytes(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
