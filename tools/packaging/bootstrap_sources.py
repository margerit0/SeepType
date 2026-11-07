"""Restore the supplied source/build materials into a fresh local project cache.

No network access, compiler installation, registry operation or input setting
change. All inputs must match the source-materials manifest before extraction.
"""
from pathlib import Path
import argparse
import gzip
import json
import shutil
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, file_hash, package_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("materials", type=Path)
    args = parser.parse_args()
    materials = args.materials.resolve()
    manifest = json.loads((materials / "source-materials.json").read_text(encoding="utf-8"))
    planned = []
    for item in manifest["materials"]:
        package_path(item["path"])
        package_path(item["restore"])
        source = materials / item["path"]
        destination = ROOT / item["restore"]
        if not destination.resolve().is_relative_to((ROOT / ".cache").resolve()): raise ValueError("Restore path escapes cache")
        if file_hash(source) != item["sha256"]: raise ValueError("Source material digest mismatch")
        if destination.exists() and file_hash(destination) != item["sha256"]: raise ValueError("Existing cache differs; inspect it manually")
        planned.append((source, destination))
    for source, destination in planned:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists(): shutil.copyfile(source, destination)
    weasel = ROOT / ".cache/src/weasel"
    if not weasel.exists():
        subprocess.run(["git", "clone", str(ROOT / ".cache/packaging/sources/weasel-9cc96e20.bundle"), str(weasel)], check=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=weasel, text=True).strip()
    if commit != "9cc96e20dc71b80876b12f689bb5863c76c2a7ed": raise ValueError("Unexpected Weasel source revision")
    boost = ROOT / ".cache/src/boost_1_84_0"
    if not (boost / ".study-headers-complete").exists():
        with tarfile.open(ROOT / ".cache/downloads/boost_1_84_0.tar.bz2", "r|bz2") as archive:
            for member in archive:
                if (member.name.startswith("boost_1_84_0/boost/") or member.name == "boost_1_84_0/LICENSE_1_0.txt") and (member.isfile() or member.isdir()):
                    archive.extract(member, ROOT / ".cache/src", filter="data")
        (boost / ".study-headers-complete").write_text("Restored from supplied fixed source archive\n", encoding="ascii")
    # build.cmd builds Rime and the API headers from the supplied archives.
    # The product workflow no longer restores or links an official Rime DLL.
    cedict = json.loads((ROOT / "data/lexicon/source.lock.json").read_bytes())["artifact"]
    archive = ROOT / ".cache/dictionaries/cc-cedict" / (cedict["archive_sha256"] + ".txt.gz")
    text = gzip.decompress(archive.read_bytes())
    from tools.packaging.common import sha256, write_changed
    if sha256(text) != cedict["text_sha256"]: raise ValueError("Restored CC-CEDICT text digest mismatch")
    write_changed(archive.with_suffix(""), text)
    print("Local source cache restored. Run tools\\packaging\\build.cmd; no installation or registration was performed.")


if __name__ == "__main__": main()
