"""Consume the pinned, reviewed development snapshot without generating new entries."""
import gzip
import hashlib
import json
from pathlib import Path

SNAPSHOT = "data/lexicon-expansion/reviews/adopted-expansion-all-20261114"
SUMMARY_SHA256 = "31a9e9122a89f5ddd76e5898e30d426094636d86ac9d9b516fc04a63aaf47f4e"
CORE_SHA256 = "962de7cbc9b086c8da755c48057273dd7704ff004a954bda8cdbd090a4da443c"


def checked(root):
    directory = Path(root) / SNAPSHOT
    raw = (directory / "summary.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SUMMARY_SHA256:
        raise ValueError("Expansion snapshot summary differs from the reviewed pin")
    summary = json.loads(raw)
    for name, expected in summary["artifacts"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Expansion snapshot artifact differs: " + name)
    report = json.loads((directory / "validation/runtime-report.json").read_bytes())
    if report.get("passed") is not True or report["snapshot_artifacts"] != summary["artifacts"]:
        raise ValueError("Expansion lacks matching upstream native verification")
    core = (Path(root) / "src/study/lua/study_core.lua").read_bytes()
    if hashlib.sha256(core).hexdigest() != CORE_SHA256:
        raise ValueError("Expansion requires the verified schema-2 Lua reader")
    records = [json.loads(line) for line in (directory / "accepted-senses.jsonl").read_bytes().splitlines() if line]
    if len(records) != summary["accepted_records"] or any(row["verdict"] != "accepted" for row in records):
        raise ValueError("Expansion contains unaccepted or missing records")
    return directory, summary


def apply(root, payload, base_dictionary):
    directory, summary = checked(root)
    if hashlib.sha256(base_dictionary).hexdigest() != summary["base_rime_dictionary_sha256"]:
        raise ValueError("Expansion Chinese base differs from Android's verified base")
    payload["rime/lua/lexicon.lua"] = (directory / "runtime-preview/lua/lexicon.lua").read_bytes()
    payload["rime/cedict_study.dict.yaml"] = (directory / "runtime-preview/cedict_study.dict.yaml").read_bytes()
    payload["notices/README.txt"] = payload["notices/README.txt"].replace(b"0.1.0-preview.1", b"0.1.0-preview.2")
    # Compressed original source/review records travel with the preview. They
    # are not runtime tables and are never inflated by startup verification.
    for name in ("accepted-senses.jsonl", "adoption-provenance.json", "source-bindings.json"):
        # AGP expands .gz assets and strips that extension; preserve these
        # opaque bytes using .gzip so runtime file hashes keep their meaning.
        payload["notices/english/expansion/" + name + ".gzip"] = gzip.compress((directory / name).read_bytes(), mtime=0)
    payload["notices/english/expansion/summary.json"] = (directory / "summary.json").read_bytes()
    payload["notices/english/expansion/README.txt"] = (
        "Reviewed development snapshot, 2026-11-14. Not approved for distribution.\n"
        "3401 accepted expansion records; 3194 runtime Chinese entries / 3195 readings, including retained legacy previews.\n"
        "Source/review originals are gzip-compressed in this directory. Original hashes are in summary.json.\n"
        "Older English notice files describe the retained 200-entry base only.\n"
    ).encode()
    return {"englishEntries": summary["accepted_records"], "humanApproved": 0,
            "chineseEntriesAdded": summary["total_supplemental_readings"],
            "englishRuntimeChineseEntries": summary["runtime_chinese_entries"],
            "englishRuntimeReadings": summary["runtime_trigger_readings"],
            "englishSnapshot": "adopted-expansion-all-20261114",
            "englishSnapshotSha256": SUMMARY_SHA256}


def smoke_cases(root):
    from tools.packaging.verify_double_pinyin import SCHEMAS, encode_syllable
    directory = Path(root) / SNAPSHOT
    model = json.loads((directory / "runtime-model.json").read_bytes())["entries"]
    readings = [json.loads(line) for line in (directory / "all-trigger-readings.jsonl").read_bytes().splitlines()]
    selected = {}
    for row in readings:
        if model[row["chinese"]]["requires_reading"] or row["chinese"] in ("公园", "存储器", "五月", "求职信"):
            selected[(row["chinese"], row["code"])] = row
    new_ids = {json.loads(line)["id"] for line in (directory / "new-accepted-senses.jsonl").read_bytes().splitlines()}
    for row in [r for r in readings if any(sid in new_ids for sid in r["sense_ids"])][:8]:
        selected[(row["chinese"], row["code"])] = row
    cases = []
    for row in selected.values():
        entry = model[row["chinese"]]
        sid = entry["primary_by_reading"].get(row["code"], entry["primary_sense_id"]) if entry["requires_reading"] else entry["primary_sense_id"]
        english = next(s["commit_english"] for s in entry["senses"] if s["id"] == sid)
        for schema in SCHEMAS:
            keys = "'".join(row["code"].split()) if schema == "study" else "".join(encode_syllable(s, schema) for s in row["code"].split())
            cases.append({"schema": schema, "input": keys, "chinese": row["chinese"], "english": english})
    return cases


def full_cases(root):
    """Every exposed reading/primary value in all schemes, including aliases."""
    from tools.packaging.verify_double_pinyin import SCHEMAS, encode_syllable
    directory, summary = checked(root)
    entries = json.loads((directory / "runtime-model.json").read_bytes())["entries"]
    readings = [json.loads(line) for line in (directory / "all-trigger-readings.jsonl").read_bytes().splitlines()]
    if len(readings) != summary["runtime_trigger_readings"]:
        raise ValueError("Incomplete runtime reading matrix")
    cases = []
    for row in readings:
        entry = entries[row["chinese"]]
        sid = entry["primary_by_reading"][row["code"]] if entry["requires_reading"] else entry["primary_sense_id"]
        sense = next(s for s in entry["senses"] if s["id"] == sid)
        for schema in SCHEMAS:
            keys = "'".join(row["code"].split()) if schema == "study" else "".join(encode_syllable(s, schema) for s in row["code"].split())
            cases.append({"schema": schema, "input": keys, "reading": row["code"], "chinese": row["chinese"],
                          "english": sense["commit_english"], "senseId": sid})
    return cases


def prepare_cases(root):
    """Regenerate test assets without changing the product resources."""
    from tools.android.common import json_write, digest
    root = Path(root)
    checked(root)
    output = root / "android/app/src/androidTest/assets/generated"
    legacy = output / "engine-cases.json"
    if legacy.exists():
        json_write(legacy, current_legacy_expectations(root, json.loads(legacy.read_bytes())))
    for name, cases in (("reviewed-smoke.json", smoke_cases(root)), ("reviewed-full.json", full_cases(root))):
        json_write(output / name, cases)
    json_write(output / "reviewed-cases-manifest.json", {"snapshot": SNAPSHOT, "summarySha256": SUMMARY_SHA256,
               "files": {name: {"sha256": digest(output / name), "cases": len(json.loads((output / name).read_bytes()))}
                         for name in ("reviewed-smoke.json", "reviewed-full.json")}})


def current_legacy_expectations(root, cases):
    """Keep the original inputs; assert against the pinned current primary sense."""
    directory, _ = checked(root)
    entries = json.loads((directory / "runtime-model.json").read_bytes())["entries"]
    result = []
    for case in cases:
        entry = entries[case["chinese"]]
        if entry["requires_reading"]:
            raise ValueError("Legacy matrix needs an explicit reading oracle: " + case["chinese"])
        english = next(s["commit_english"] for s in entry["senses"] if s["id"] == entry["primary_sense_id"])
        result.append({**case, "english": english})
    return result


if __name__ == "__main__":
    import sys
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    prepare_cases(root)
    print("Generated checked smoke and complete three-scheme lexicon matrices")
