"""Collect pinned upstream source/licensing materials; never install software.

`--fetch --initialize` is a maintainer-only first collection. Subsequent runs
verify the lock and local archive hashes; --fetch restores missing archives
from their exact locked URLs. No branch head or latest release is followed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, file_hash, json_bytes, package_path, sha256, write_changed

SPECS = [
    ("librime", "rime/librime", "1c23358157934bd6e6d6981f0c0164f05393b497", "BSD-3-Clause"),
    ("librime-lua", "hchunhui/librime-lua", "e3912a4b3ac2c202d89face3fef3d41eb1d7fcd6", "BSD-3-Clause"),
    ("lua-thirdparty", "hchunhui/librime-lua", "115e000c878d1170337f7ca934d7a84f68986e39", "MIT"),
    ("librime-octagram", "lotem/librime-octagram", "dfcc15115788c828d9dd7b4bff68067d3ce2ffb8", "GPLv3 (upstream notice)"),
    ("librime-predict", "rime/librime-predict", "920bd41ebf6f9bf6855d14fbe80212e54e749791", "BSD-3-Clause"),
    ("glog", "google/glog", "7b134a5c82c0c0b5698bb6bf7a835b230c5638e4", "BSD-3-Clause"),
    ("leveldb", "google/leveldb", "99b3c03b3284f5886f9ef9a4ef703d57373e61be", "BSD-3-Clause"),
    ("marisa-trie", "rime/marisa-trie", "0d4e8ab58eec355facf8f65ff11ef811b330e373", "BSD-2-Clause OR LGPL-2.1-or-later"),
    ("opencc", "BYVoid/OpenCC", "e5d6c5f1b78e28a5797e7ad3ede3513314e544b7", "Apache-2.0"),
    ("yaml-cpp", "jbeder/yaml-cpp", "f7320141120f720aecc4c32be25586e7da9eb978", "MIT"),
    ("googletest", "google/googletest", "f8d7d77c06936315286eb55f8de22cd23c188571", "BSD-3-Clause"),
    ("rime-luna-pinyin", "rime/rime-luna-pinyin", "9593090080294a7dfc3c864c087e4070459c0168", "LGPL-3.0"),
    ("rime-prelude", "rime/rime-prelude", "3c602fdb0dcca7825103e281efc50ef7580f99ec", "LGPL-3.0"),
    ("rime-essay", "rime/rime-essay", "573bbeb53e53d4331fff5fae151b814c67b8d0cd", "LGPL-3.0"),
]
LOCK = ROOT / "licensing/sources.lock.json"


def fetch(url: str, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "StudyIME-source-license-audit"})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read(80 * 1024 * 1024 + 1)
    if len(raw) > 80 * 1024 * 1024:
        raise ValueError("Source archive exceeded collection limit")
    write_changed(path, raw)


def source_files(path: Path):
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir(): continue
                package_path(member.filename)
                yield member.filename, archive.read(member)
        return
    with tarfile.open(path, "r:*") as archive:
        for member in archive:
            if not member.isfile():
                continue
            parts = member.name.split("/", 1)
            if len(parts) != 2:
                continue
            yield parts[1], archive.extractfile(member).read()


def collect_one(spec, allow_fetch, locked=None):
    name, repository, commit, license_id = spec
    url = f"https://codeload.github.com/{repository}/tar.gz/{commit}"
    archive = CACHE / "sources" / f"{name}-{commit}.tar.gz"
    if not archive.exists():
        if not allow_fetch:
            raise FileNotFoundError(f"Missing pinned source {archive}; explicit --fetch is required")
        fetch(url, archive)
    digest = file_hash(archive)
    if locked and (digest != locked["archive_sha256"] or url != locked["url"]):
        raise ValueError(f"Locked source differs: {name}")
    record = {"id": name, "repository": f"https://github.com/{repository}", "commit": commit,
              "license_hint": license_id, "url": url, "archive": archive.relative_to(ROOT).as_posix(),
              "archive_sha256": digest, "notices": []}
    for relative, raw in source_files(archive):
        if re.search(r"(?i)^(license|licence|copying|notice|copyright)([._-]|$)", Path(relative).name):
            target = ROOT / "licensing/third-party" / name / relative
            write_changed(target, raw)
            record["notices"].append({"source_path": relative,
                                      "path": target.relative_to(ROOT).as_posix(), "sha256": sha256(raw)})
    record["notices"].sort(key=lambda item: item["source_path"])
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--extend-lock", action="store_true", help="Add new pinned components; existing entries must remain byte-identical")
    args = parser.parse_args()
    if args.initialize and LOCK.exists():
        raise SystemExit("Refusing to replace an existing source lock")
    previous = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.exists() else None
    if not previous and not args.initialize:
        raise SystemExit("First collection requires --initialize; lock creation is explicit")
    indexed = {entry["id"]: entry for entry in previous["sources"]} if previous else {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(collect_one, spec, args.fetch, indexed.get(spec[0])) for spec in SPECS]
        records = [job.result() for job in jobs]
    for name, source, target in [
        ("weasel", ".cache/src/weasel/LICENSE.txt", "licensing/third-party/weasel/LICENSE.txt"),
        ("boost", ".cache/src/boost_1_84_0/LICENSE_1_0.txt", "licensing/third-party/boost/LICENSE_1_0.txt"),
    ]:
        raw = (ROOT / source).read_bytes()
        write_changed(ROOT / target, raw)
    write_changed(ROOT / "LICENSE", (ROOT / ".cache/src/weasel/LICENSE.txt").read_bytes())
    result = {"schema_version": 1, "collection_date": "2026-11-07", "sources": records,
              "basis": "Rime version-info.txt, librime pinned gitlinks, and pre-release data repository commits; per-file matching is recorded separately."}
    if previous:
        if result != previous:
            if not args.extend_lock or any(entry not in result["sources"] for entry in previous["sources"]):
                raise SystemExit("Collection changed; inspect differences instead of silently updating the lock")
            write_changed(LOCK, json_bytes(result))
    else:
        write_changed(LOCK, json_bytes(result))
    print(json.dumps({"source_archives": len(records), "notice_files": sum(len(x["notices"]) for x in records),
                      "lock": str(LOCK)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
