"""Restore a fixed portable CMake under the project cache; offline by default."""
from pathlib import Path
import argparse
import json
import sys
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, file_hash, package_path, write_changed


def cmake(*, fetch=False):
    lock = json.loads((ROOT / "licensing/build-tools.lock.json").read_bytes())
    item = next(item for item in lock["tools"] if item["id"] == "cmake")
    archive = ROOT / item["archive"]
    if not archive.exists():
        if not fetch:
            raise ValueError("Missing fixed CMake archive; restore source materials or run build_tools.py --fetch")
        archive.parent.mkdir(parents=True, exist_ok=True)
        temporary = archive.with_suffix(".download")
        with urllib.request.urlopen(item["url"], timeout=40) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if file_hash(temporary) != item["archive_sha256"]:
            raise ValueError("Downloaded CMake differs from the official fixed checksum")
        temporary.replace(archive)
    if file_hash(archive) != item["archive_sha256"]:
        raise ValueError("Fixed CMake archive digest mismatch")
    destination = ROOT / ".cache/build-tools"
    expected = destination / item["directory"]
    if destination.is_symlink() or destination.is_junction() or expected.is_symlink() or expected.is_junction():
        raise ValueError("Reparse point in portable build-tool destination")
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            name = info.filename.rstrip("/")
            package_path(name)
            if name != item["directory"] and not name.startswith(item["directory"] + "/"):
                raise ValueError("Unexpected CMake archive root")
            path = destination / name
            if not path.resolve().is_relative_to(expected.resolve()) or path.is_symlink() or path.is_junction():
                raise ValueError("Unsafe CMake extraction path")
            if info.external_attr >> 16 & 0o170000 == 0o120000:
                raise ValueError("CMake archive contains a symbolic link")
            if not info.is_dir():
                write_changed(path, bundle.read(info))
    return expected / "bin/cmake.exe"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    print(cmake(fetch=args.fetch))
