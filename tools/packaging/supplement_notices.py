"""Pin missing canonical/vendored license notices; explicit network opt-in."""
from pathlib import Path
import argparse
import json
import re
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, json_bytes, sha256, write_changed
from tools.packaging.collect_licenses import source_files

NOTICES = [
    ("licensing/third-party/wtl/MS-PL.txt", "https://raw.githubusercontent.com/spdx/license-list-data/v3.26.0/text/MS-PL.txt"),
    ("licensing/third-party/rapidjson/license.txt", "https://raw.githubusercontent.com/Tencent/rapidjson/v1.1.0/license.txt"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--extend-lock", action="store_true")
    args = parser.parse_args()
    lock_path = ROOT / "licensing/notices.lock.json"
    old = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.exists() else None
    entries = []
    for relative, url in NOTICES:
        file = ROOT / relative
        if not file.exists():
            if not args.fetch: raise FileNotFoundError(f"Explicit --fetch required for {relative}")
            with urllib.request.urlopen(url, timeout=30) as response: raw = response.read()
            write_changed(file, raw)
        entries.append({"path": relative, "url": url, "sha256": sha256(file.read_bytes())})
    upstream = ROOT / ".cache/src/weasel/include/wtl/atlapp.h"
    raw = upstream.read_bytes()
    header = raw[:raw.index(b"#ifndef")]
    relative = "licensing/third-party/wtl/UPSTREAM-NOTICE.txt"
    write_changed(ROOT / relative, header)
    entries.append({"path": relative, "source": "Weasel 9cc96e20dc71b80876b12f689bb5863c76c2a7ed:include/wtl/atlapp.h (header)", "sha256": sha256(header)})
    sources = json.loads((ROOT / "licensing/sources.lock.json").read_text(encoding="utf-8"))
    lua = next(item for item in sources["sources"] if item["id"] == "lua-thirdparty")
    files = dict(source_files(ROOT / lua["archive"]))
    # The complete Lua grant appears in lua.h itself in this vendor branch.
    source = "lua5.4/lua.h"
    if not all(re.search(rb'#define LUA_VERSION_' + name + rb'\s+"' + value + rb'"', files[source])
               for name, value in [(b"MAJOR", b"5"), (b"MINOR", b"4"), (b"RELEASE", b"7")]):
        raise ValueError("Unexpected vendored Lua header")
    relative = "licensing/third-party/lua/lua.h"
    write_changed(ROOT / relative, files[source])
    entries.append({"path": relative, "source": f"{lua['commit']}:{source}", "sha256": sha256(files[source])})
    for component, filename, origin in [
        ("weasel", "LICENSE.txt", "Weasel 9cc96e20dc71b80876b12f689bb5863c76c2a7ed:LICENSE.txt"),
        ("boost", "LICENSE_1_0.txt", "Boost 1.84.0 archive cc4b893acf645c9d4b698e9a0f08ca8846aa5d6c68275c14c3e7949c24109454:LICENSE_1_0.txt"),
    ]:
        relative = f"licensing/third-party/{component}/{filename}"
        entries.append({"path": relative, "source": origin, "sha256": sha256((ROOT / relative).read_bytes())})
    result = {"schema_version": 1, "notices": entries}
    if old and result != old and (not args.extend_lock or any(entry not in entries for entry in old["notices"])):
        raise ValueError("Supplemental notices differ from their lock")
    write_changed(lock_path, json_bytes(result))
    print(f"Verified {len(entries)} supplemental notices.")


if __name__ == "__main__": main()
