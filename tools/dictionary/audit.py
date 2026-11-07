"""Check every exported Chinese headword/reading against its original source rows."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.dictionary.cedict import files
from tools.lexicon import pipeline as lex
from tools.packaging.common import ROOT, file_hash, json_bytes, sha256, write_changed


def audit():
    generated = files()
    repeated = files()
    if generated != repeated: raise ValueError("Chinese export is not byte reproducible")
    metadata = json.loads(generated["provenance.json"])
    mapping = json.loads(generated["source-mapping.json"])
    lock = json.loads((ROOT / "data/lexicon/source.lock.json").read_bytes())
    path = ROOT / ".cache/dictionaries/cc-cedict" / (lock["artifact"]["archive_sha256"] + ".txt")
    raw = path.read_bytes()
    if sha256(raw) != lock["artifact"]["text_sha256"]: raise ValueError("CC-CEDICT source digest mismatch")
    source_rows = {sha256(line.encode("utf-8")): lex.parse_source(line) for line in raw.decode("utf-8-sig").splitlines() if line and not line.startswith("#")}
    body = generated["cedict_study.dict.yaml"].decode("utf-8").split("\n...\n", 1)[1]
    seen, source_references = set(), 0
    for line in body.splitlines():
        word, code, weight = line.split("\t")
        key = word + "\t" + code
        if key in seen or int(weight) < 1: raise ValueError("Duplicate or invalid Chinese dictionary row")
        seen.add(key)
        if not mapping[key]: raise ValueError("Dictionary row has no source witness")
        for digest in mapping[key]:
            original = source_rows[digest]
            tokens = original["pinyin"].lower().replace("u:", "v").split()
            if word != original["chinese"] or code.split() != [re.sub("[1-5]$", "", token) for token in tokens]:
                raise ValueError("Dictionary row differs from its original Chinese headword or reading")
            source_references += 1
    if seen != set(mapping) or len(seen) != metadata["dictionary_entries"] or source_references != metadata["accepted_source_entries"]:
        raise ValueError("Dictionary/source mapping coverage mismatch")
    data = lex.validate()
    report = {"recorded_at": datetime.now(timezone.utc).isoformat(), "passed": True,
              "dictionary_entries": len(seen), "verified_source_references": source_references,
              "identical_second_export": True, "source_text_sha256": sha256(raw),
              "dictionary_sha256": metadata["dictionary_sha256"], "source_mapping_sha256": metadata["source_mapping_sha256"],
              "review_counts": data.counts, "english_review_entries_sha256": file_hash(ROOT / "data/lexicon/entries.json"),
              "scope": "Exact Chinese source correspondence and deterministic export, not human English review or typing-quality acceptance"}
    write_changed(ROOT / "experiments/phase6/results/chinese-source-validation.json", json_bytes(report))
    print(f"Verified {len(seen)} Chinese dictionary rows against {source_references} source references; identical second export.")


if __name__ == "__main__": audit()
