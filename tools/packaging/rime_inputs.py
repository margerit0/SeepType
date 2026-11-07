"""Validate the compiled product engine against its saved source/build record."""
from pathlib import Path
import json

from tools.packaging.common import ROOT, file_hash

WORK = ROOT / ".cache/rime-build"


def validate():
    record = json.loads((WORK / "rime-build.json").read_bytes())
    if record["plugins"] != ["lua"] or record["binary"]["architecture"] != "x64":
        raise ValueError("Unexpected product Rime configuration")
    for name, digest in record["project_inputs"].items():
        if file_hash(ROOT / name) != digest:
            raise ValueError("Rime build inputs changed; rebuild before packaging: " + name)
    for key, file in [("source_tree_sha256", "source-tree.json"), ("include_trace_sha256", "include-trace.json"),
                      ("compile_commands_sha256", "compile-commands.json")]:
        if file_hash(WORK / file) != record[key]:
            raise ValueError("Rime provenance record changed: " + file)
    for source in record["source_archives"].values():
        if file_hash(ROOT / source["archive"]) != source["archive_sha256"]:
            raise ValueError("Rime source archive changed")
    checked = {}
    for file in ["source-tree.json", "include-trace.json"]:
        for name, digest in json.loads((WORK / file).read_bytes()).items():
            if name not in checked:
                checked[name] = file_hash(ROOT / name)
            if checked[name] != digest:
                raise ValueError("Actual Rime compiler input changed; rebuild: " + name)
    for name, item in json.loads((WORK / "compile-commands.json").read_bytes()).items():
        if checked.get(name, None) != item["sha256"] and file_hash(ROOT / name) != item["sha256"]:
            raise ValueError("Compiled Rime source changed; rebuild: " + name)
    for name, digest in record["static_libraries"].items():
        if file_hash(ROOT / name) != digest:
            raise ValueError("Rime static library changed; rebuild: " + name)
    if file_hash(ROOT / record["binary"]["path"]) != record["binary"]["sha256"]:
        raise ValueError("Rime binary changed after its source build")
    return record
