"""Verify or restore the original, pinned TTF fonts bundled with the skins.

Normal APK builds use the checked-in files without network access. Restoration:
  python -X utf8 tools/android/prepare_skin_fonts.py --restore
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def prepare(restore=False):
    fonts = ROOT / "android/app/src/main/res/font"
    notices = ROOT / "android/app/src/main/assets/fonts"
    records = json.loads((notices / "manifest.json").read_text(encoding="utf-8"))
    for record in records:
        for target, url, expected in [
            (fonts / record["file"], record["source"], record["sha256"]),
            (notices / record["licenseFile"], record["licenseSource"], record["licenseSha256"]),
        ]:
            if restore:
                data = urllib.request.urlopen(url, timeout=30).read()
                if hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError("Upstream font/license digest mismatch: " + target.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise ValueError("Bundled font/license digest mismatch: " + target.name)
        data = (fonts / record["file"]).read_bytes()
        assert data[:4] == b"\x00\x01\x00\x00" and len(data) == record["bytes"]
    print(json.dumps({"verifiedFonts": len(records), "bytes": sum(record["bytes"] for record in records)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", action="store_true")
    prepare(parser.parse_args().restore)
