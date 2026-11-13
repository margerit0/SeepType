"""Copy only the development app's generated test evidence from its private files."""
import argparse
import io
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, safe, write
from tools.android.device import adb


def collect(directory, serial="emulator-5554"):
    if directory not in ("visual", "skins", "lifecycle", "scenarios", "performance", "recording"):
        raise ValueError("Not a generated evidence directory")
    archive = adb("exec-out", "run-as", "org.studyime.android.debug", "tar", "-C", "files", "-cf", "-", directory,
                  serial=serial, binary=True).stdout
    destination = CACHE / "evidence"
    count = 0
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        for entry in bundle:
            if not entry.isfile():
                continue
            output = safe(destination / entry.name)
            if not output.is_relative_to((destination / directory).resolve()):
                raise ValueError("Evidence escaped its generated directory")
            write(output, bundle.extractfile(entry).read())
            count += 1
    print(f"Collected {count} generated files under {destination / directory}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", choices=["visual", "skins", "lifecycle", "scenarios", "performance", "recording"])
    parser.add_argument("--serial", default="emulator-5554")
    args = parser.parse_args()
    collect(args.directory, args.serial)
