"""Import a verified development lexicon for Windows and Android from a local Git commit."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import ROOT, safe
from tools.android.word_details import pack_details, snapshot_rows
from tools.lexicon.pipeline import atomic_write
from tools.lexicon_expand.generation import run_lock
from tools.lexicon_expand.runtime import lua_bytes

SOURCE = "data/lexicon-expansion"
OUTPUT = ROOT / SOURCE / "android-runtime"
WINDOWS_OUTPUT = ROOT / SOURCE / "windows-runtime"
EXAMPLES = "word-detail-examples.json"
SCHEMAS = ("study", "study_double_pinyin", "study_flypy")
CORE = "src/study/lua/study_core.lua"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def records(data):
    return [json.loads(line) for line in data.splitlines()]


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def merge_examples(existing, incoming):
    examples = json.loads(existing)
    by_id = {example["id"]: example for example in examples}
    require(len(by_id) == len(examples), "Duplicate example ID in the current Android examples")
    for example in incoming:
        sense_id = example["id"]
        require(by_id.setdefault(sense_id, example) == example, f"Conflicting example for {sense_id}")
    return json_bytes(list(by_id.values())) if len(by_id) > len(examples) else existing


def import_snapshot(ref, source_repo=ROOT):
    git_dir = source_repo / ".git"
    if not git_dir.exists():
        git_dir = source_repo

    def git(*args):
        return subprocess.check_output(["git", "--git-dir", str(git_dir), *args])

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
    model_bytes = artifact("runtime-model.json")
    model = json.loads(model_bytes)
    require(lua_bytes(model) == lexicon, "Windows runtime model does not reproduce the verified Lua lexicon")
    core = blob(CORE, report["runtime_inputs"]["user-template/lua/study_core.lua"])
    examples = json.loads(blob(f"{source}/{EXAMPLES}", evidence[EXAMPLES])) if EXAMPLES in evidence else []
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
        selected.update(dict.fromkeys(sample, group))
    cases = [{"schema": row["schema"], "input": row["input"], "chinese": row["chinese"],
              "english": row["expected_english"], "coverage": selected[key(row)]}
             for row in defaults if key(row) in selected]
    require(cases and Counter(row["schema"] for row in cases) == dict.fromkeys(SCHEMAS, len(selected)),
            "Sample must cover the same triggers in all three schemes")
    dictionary_rows = dictionary.split(b"\n...\n", 1)[1].splitlines()
    payload = {"cedict_study.dict.yaml": dictionary, "lexicon.lua": lexicon,
               "engine-cases.json": json_bytes(cases),
               "word-details.jsonl": snapshot_rows(model, triggers, records(artifact("accepted-senses.jsonl")))}
    shared_lock = json_bytes({
        "schemaVersion": 1, "windowsCommit": commit, "windowsSnapshot": source,
        "verificationSha256": current["verification_sha256"], "windowsEngineChecks": len(checks),
        "acceptedRecords": current["accepted_records"], "englishTriggerReadings": len(triggers),
        "supplementalReadings": summary["total_supplemental_readings"],
        "chineseDictionaryRows": sum(not row.startswith(b"#") and bool(row) for row in dictionary_rows),
        "baseDictionarySha256": summary["base_rime_dictionary_sha256"],
        "studyCoreSha256": sha(core), "humanApproved": 0, "releaseReady": False,
        "files": {name: sha(data) for name, data in payload.items()},
    })
    windows_lock = json_bytes({
        "schema_version": 1,
        "runtime_model_sha256": sha(model_bytes),
        "shared_snapshot_sha256": sha(shared_lock),
    })

    with run_lock(ROOT / ".cache/lexicon-expansion/import-snapshot"):
        examples_path = OUTPUT / EXAMPLES
        existing_examples = examples_path.read_bytes() if examples_path.is_file() else b"[]\n"
        merged_examples = merge_examples(existing_examples, examples)
        pack_details(payload["word-details.jsonl"], merged_examples)

        updates = {OUTPUT / name: data for name, data in payload.items()}
        updates.update({
            ROOT / CORE: core,
            examples_path: merged_examples,
            WINDOWS_OUTPUT / "runtime-model.json": model_bytes,
            OUTPUT / "snapshot.json": shared_lock,
            WINDOWS_OUTPUT / "snapshot.json": windows_lock,
        })
        for path, data in updates.items():
            if not path.is_file() or path.read_bytes() != data:
                atomic_write(safe(path), data)

    print(f"Imported {current['accepted_records']} records, {len(cases)} engine cases, "
          f"and {len(json.loads(merged_examples))} total Android examples from {commit}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ref", help="Windows branch or exact source commit")
    parser.add_argument("--source-repo", type=Path, default=ROOT,
                        help="Local source repository or worktree (defaults to this repository)")
    args = parser.parse_args()
    try:
        import_snapshot(args.ref, args.source_repo)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Import failed: {error}\n")
