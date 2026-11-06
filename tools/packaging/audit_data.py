"""Record the one-time match between pinned Chinese sources and the old cache."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, file_hash, json_bytes, sha256, write_changed
from tools.packaging.collect_licenses import source_files


def main():
    from tools.packaging.package import DATA
    lock = json.loads((ROOT / "licensing/sources.lock.json").read_text(encoding="utf-8"))
    results = []
    for source in lock["sources"]:
        if source["id"] not in DATA or source["id"] == "opencc": continue
        files = dict(source_files(ROOT / source["archive"]))
        for name in DATA[source["id"]]:
            path = ROOT / ".cache/weasel-0.17.4/data" / name
            original = files[name]
            match = original.replace(b"\r\n", b"\n") == path.read_bytes().replace(b"\r\n", b"\n")
            if not match: raise ValueError("Cached Chinese input data differs: " + name)
            results.append({"path": "data/shared/" + name, "component": source["id"], "commit": source["commit"],
                            "source_sha256": sha256(original), "cached_sha256": file_hash(path), "lf_normalized_match": True})
    value = {"schema_version": 1, "basis": "Weasel 0.17.4 installer cf509534... and pinned upstream source archives",
             "files": sorted(results, key=lambda item: item["path"])}
    path = ROOT / "licensing/chinese-data.lock.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != value:
        raise ValueError("Chinese data audit differs from its lock")
    write_changed(path, json_bytes(value))
    print(f"Recorded {len(results)} fixed source/cache data matches.")


if __name__ == "__main__": main()
