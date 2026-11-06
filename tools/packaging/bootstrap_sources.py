"""Restore the supplied source/build materials into a fresh local project cache.

No network access, compiler installation, registry operation or input setting
change. All inputs must match the source-materials manifest before extraction.
"""
from pathlib import Path
import argparse
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
    rime = ROOT / ".cache/rime-1.13.1"
    if not (rime / "dist/lib/rime.dll").exists():
        archive = ROOT / ".cache/downloads/rime-1c23358-Windows-msvc-x64.7z"
        members = subprocess.check_output(["tar.exe", "-tf", str(archive)], text=True).splitlines()
        for name in members: package_path(name.rstrip("/"))
        rime.mkdir(parents=True, exist_ok=True)
        subprocess.run(["tar.exe", "-xf", str(archive), "-C", str(rime)], check=True)
    if file_hash(rime / "dist/lib/rime.dll") != "2d8f1bc3737635a11d9fb1bfca4dc9e70533633930a8a0142a81ca879c39c45b":
        raise ValueError("Restored Rime DLL digest mismatch")
    print("Local source cache restored. Run tools\\packaging\\build.cmd; no installation or registration was performed.")


if __name__ == "__main__": main()
