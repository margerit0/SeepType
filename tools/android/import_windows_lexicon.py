"""Import a verified Windows development lexicon from a local Git ref, not a running worktree."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import ROOT, json_write, write
from tools.android.word_details import snapshot_rows

SOURCE = "data/lexicon-expansion"
OUTPUT = ROOT / SOURCE / "android-runtime"
SCHEMAS = ("study", "study_double_pinyin", "study_flypy")
CORE = "src/study/lua/study_core.lua"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def records(data):
    return [json.loads(line) for line in data.splitlines()]


def import_snapshot(ref):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT)

    commit = git("rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()

    def blob(name, expected=None):
        data = git("cat-file", "blob", f"{commit}:{name}")
        require(expected is None or sha(data) == expected, f"Windows snapshot hash mismatch: {name}")
        return data

    current = json.loads(blob(f"{SOURCE}/current-development.json"))
    verification = json.loads(blob(current["verification_path"], current["verification_sha256"]))
    source = current["snapshot_directory"]
    require(verification["passed"] and verification["final_runtime_artifacts_match_snapshot"],
            "Windows snapshot is not engine validated")
    evidence = verification["evidence"]
    summary = json.loads(blob(f"{source}/summary.json", evidence["summary.json"]))
    report_path = verification["final_runtime_report"]
    report = json.loads(blob(f"{source}/{report_path}", evidence[report_path]))
    require(report["passed"] and report["completed_checks"] == current["runtime_checks_passed"],
            "Windows engine checks are incomplete")
    artifacts = summary["artifacts"]

    def artifact(name):
        return blob(f"{source}/{name}", artifacts[name])

    dictionary = artifact("runtime-preview/cedict_study.dict.yaml")
    lexicon = artifact("runtime-preview/lua/lexicon.lua")
    core = blob(CORE, report["runtime_inputs"]["user-template/lua/study_core.lua"])
    checks = records(blob(f"{source}/{report['checks_file']}", report["checks_sha256"]))
    legacy = {row["chinese"] for row in records(artifact("retained-legacy-runtime.jsonl"))}
    added = {(row["chinese"], row["code"]) for row in records(artifact("new-trigger-additions.jsonl"))}
    triggers = records(artifact("all-trigger-readings.jsonl"))
    multiple = {word for word, count in Counter(row["chinese"] for row in triggers).items() if count > 1}
    defaults = [row for row in checks if row["layer"] == "delivered-defaults"]
    require(len(checks) == report["completed_checks"] and all(row["passed"] for row in checks)
            and Counter(row["schema"] for row in defaults) == dict.fromkeys(SCHEMAS, len(triggers)),
            "Unexpected Windows validation case coverage")
    require(summary["accepted_records"] == current["accepted_records"] == report["accepted_records"]
            and len(triggers) == summary["runtime_trigger_readings"], "Inconsistent Windows snapshot counts")

    # Keep the approved runtime defaults for the retained old preview entries,
    # every pronunciation-sensitive entry, and deterministic new-entry samples.
    def key(row):
        return row["chinese"], row["code"]

    selected = {}
    for row in defaults:
        if row["chinese"] in multiple:
            selected[key(row)] = "reading-sensitive"
        elif row["chinese"] in legacy:
            selected[key(row)] = "legacy-preview"
    for group, eligible in (
        ("supplemental", (key(row) for row in defaults if key(row) in added)),
        ("expansion", (key(row) for row in defaults if not row["baseline_trigger"] and key(row) not in added)),
    ):
        sample = sorted(set(eligible) - selected.keys(), key=lambda item: (sha("\t".join(item).encode()), item))[:24]
        require(len(sample) == 24, f"Not enough Windows cases for {group}")
        selected.update(dict.fromkeys(sample, group))
    cases = [{"schema": row["schema"], "input": row["input"], "chinese": row["chinese"],
              "english": row["expected_english"], "coverage": selected[key(row)]}
             for row in defaults if key(row) in selected]
    require(Counter(row["schema"] for row in cases) == dict.fromkeys(SCHEMAS, len(selected)),
            "Sample must cover the same triggers in all three schemes")
    dictionary_rows = dictionary.split(b"\n...\n", 1)[1].splitlines()
    payload = {"cedict_study.dict.yaml": dictionary, "lexicon.lua": lexicon,
               "engine-cases.json": (json.dumps(cases, ensure_ascii=False, indent=2) + "\n").encode(),
               "word-details.jsonl": snapshot_rows(json.loads(artifact("runtime-model.json")), triggers,
                                                 records(artifact("accepted-senses.jsonl")))}
    for name, data in payload.items():
        write(OUTPUT / name, data)
    write(ROOT / CORE, core)
    json_write(OUTPUT / "snapshot.json", {
        "schemaVersion": 1, "windowsCommit": commit, "windowsSnapshot": source,
        "verificationSha256": current["verification_sha256"], "windowsEngineChecks": len(checks),
        "acceptedRecords": current["accepted_records"], "englishTriggerReadings": len(triggers),
        "supplementalReadings": summary["total_supplemental_readings"],
        "chineseDictionaryRows": sum(not row.startswith(b"#") and bool(row) for row in dictionary_rows),
        "baseDictionarySha256": summary["base_rime_dictionary_sha256"],
        "studyCoreSha256": sha(core), "humanApproved": 0, "releaseReady": False,
        "files": {name: sha(data) for name, data in payload.items()},
    })
    print(f"Imported {current['accepted_records']} records and {len(cases)} Android test cases from {commit}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ref", help="Windows branch or exact source commit")
    import_snapshot(parser.parse_args().ref)
