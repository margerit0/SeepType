"""Prepare the exact upstream source materials needed for the current product.

Librime's unbuilt historical preset dictionaries and Luna's mixed word list
are excluded from redistributed materials. Required code, schema text and
license notices retain their original bytes and upstream archive provenance.
"""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, deterministic_zip, file_hash, json_bytes, sha256, write_changed
from tools.packaging.collect_licenses import source_files, fetch

ACTIVE = ["librime", "librime-lua", "lua-thirdparty", "glog", "leveldb", "marisa-trie", "opencc", "yaml-cpp", "rime-luna-pinyin", "rime-prelude"]
LOCK = ROOT / "licensing/product-sources.lock.json"
LUNA_FILES = {"luna_pinyin.schema.yaml", "luna_pinyin_simp.schema.yaml", "pinyin.yaml", "LICENSE"}


def prepare(*, allow_fetch=False):
    original = json.loads((ROOT / "licensing/sources.lock.json").read_bytes())
    records = []
    for item in original["sources"]:
        if item["id"] not in ACTIVE: continue
        path = ROOT / item["archive"]
        if not path.exists() and allow_fetch: fetch(item["url"], path)
        if file_hash(path) != item["archive_sha256"]: raise ValueError("Original source archive changed")
        record = dict(item)
        if item["id"] in ["librime", "rime-luna-pinyin"]:
            source = dict(source_files(path))
            if item["id"] == "librime":
                chosen = {name: content for name, content in source.items() if not name.startswith("data/")}
            else:
                chosen = {name: source[name] for name in sorted(LUNA_FILES)}
            target = CACHE / "product-sources" / (item["id"] + "-" + item["commit"] + "-selected.zip")
            deterministic_zip(target, chosen)
            record.update({"archive": target.relative_to(ROOT).as_posix(), "archive_sha256": file_hash(target),
                "materials_kind": "selected-original-files", "upstream_archive_sha256": item["archive_sha256"],
                "upstream_archive": item["archive"], "original_file_bytes_preserved": True,
                "selection": "Exclude data/ (unbuilt historical preset dictionaries)" if item["id"] == "librime" else "Only the three schema/spelling files and original LGPL license",
                "files": {name: sha256(content) for name, content in sorted(chosen.items())}})
        records.append(record)
    result = {"schema_version": 1, "basis": "Required product source materials selected from the original fixed source lock",
              "original_source_lock_sha256": file_hash(ROOT / "licensing/sources.lock.json"), "sources": records,
              "excluded_archives": [item["id"] for item in original["sources"] if item["id"] not in ACTIVE]}
    if LOCK.exists() and json.loads(LOCK.read_bytes()) != result:
        raise ValueError("Product source selection differs from its established lock")
    write_changed(LOCK, json_bytes(result))
    return result


def locked_sources():
    value = json.loads(LOCK.read_bytes())
    if value["original_source_lock_sha256"] != file_hash(ROOT / "licensing/sources.lock.json"):
        raise ValueError("Original source lock changed after product selection")
    if {item["id"] for item in value["sources"]} != set(ACTIVE): raise ValueError("Unexpected product source set")
    for item in value["sources"]:
        path = ROOT / item["archive"]
        if file_hash(path) != item["archive_sha256"]: raise ValueError("Product source archive changed: " + item["id"])
        if item.get("files"):
            actual = {name: sha256(content) for name, content in source_files(path)}
            if actual != item["files"]: raise ValueError("Selected source file bytes changed")
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    result = prepare(allow_fetch=args.fetch) if args.prepare else locked_sources()
    print(f"Verified {len(result['sources'])} product source archives; unused mixed dictionary materials excluded.")
