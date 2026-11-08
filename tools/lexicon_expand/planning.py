"""Build inspectable, capped API requests without accessing an API key or endpoint."""
from __future__ import annotations

from pathlib import Path

from tools.lexicon_expand.catalog import load_prepared
from tools.lexicon_expand.common import (
    CACHE, canonical, digest, generated_directory, read_json, read_jsonl,
    require, write_json, write_jsonl,
)

PROMPT = Path(__file__).with_name("prompt.txt")


def select_targets(targets, count, pack="ielts"):
    pool = [t for t in targets if pack in t["packs"] and t["api_eligible"] and not any(
        e["review_status"] == "approved-for-distribution" and e["input_dictionary_reachable"]
        for e in t["existing_entries"])]
    key = lambda t: (any(e["review_status"] == "pending" for e in t["existing_entries"]),
                     t["frequency_rank"] or 10**9, t["english"])
    # Include missing references as well as source-backed words in a pilot.
    without = sorted([t for t in pool if not t["dictionary_reference_count"]], key=key)
    selected = without[:count // 4]
    chosen = {t["id"] for t in selected}
    selected += sorted([t for t in pool if t["id"] not in chosen], key=key)[:count - len(selected)]
    return selected


def make_job(task, targets, system_prompt, scenario=None):
    payload = {"task": task, "targets": targets}
    if scenario is not None:
        payload["scenario"] = scenario
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": canonical(payload).decode("utf-8")}]
    identity = digest(canonical(messages))
    return {"id": "request-" + identity[:24], "request_sha256": identity,
            "task": task, "units": len(targets), "payload": payload, "messages": messages}


def make_plan(prepared=CACHE / "prepared", output=CACHE / "pilot", *, word_count=200,
              scene_count=100, batch_size=10, pack="ielts"):
    require(type(word_count) is int and type(scene_count) is int and word_count >= 0 and scene_count >= 0,
            "Counts must be nonnegative integers")
    require(0 < word_count + scene_count <= 100000, "Empty or oversized generation plan")
    require(1 <= batch_size <= 20, "Batch size must be between 1 and 20")
    targets, summary, manifest = load_prepared(prepared)
    output = generated_directory(output)
    require(output != Path(prepared).resolve(), "Do not overwrite the prepared catalog")
    prompt = PROMPT.read_text(encoding="utf-8")
    selected = select_targets(targets, word_count, pack)
    require(len(selected) == word_count, "Requested more eligible targets than the selected pack contains")
    jobs = []
    for start in range(0, len(selected), batch_size):
        group = []
        for target in selected[start:start + batch_size]:
            group.append({"target_id": target["id"], "english": target["english"],
                          "source_forms": target["source_forms"], "packs": target["packs"],
                          "parts_of_speech": target["parts_of_speech"],
                          "cefr_levels": target["cefr_levels"], "source_refs": target["source_refs"],
                          "dictionary_references": target["dictionary_references"],
                          "existing_entries": target["existing_entries"]})
        jobs.append(make_job("map_targets", group, prompt))
    scenarios = summary["scenarios"]
    require(bool(scenarios) or scene_count == 0, "No scene configuration available")
    for index, scenario in enumerate(scenarios):
        quota = scene_count // len(scenarios) + (index < scene_count % len(scenarios))
        for start in range(0, quota, batch_size):
            slots = [{"target_id": f"scene-{scenario['id']}-{slot:05d}",
                      "english": None, "packs": ["scene:" + scenario["id"]],
                      "source_refs": [], "dictionary_references": [], "existing_entries": []}
                     for slot in range(start + 1, min(start + batch_size, quota) + 1)]
            jobs.append(make_job("scene_terms", slots, prompt, scenario))
    units = sum(job["units"] for job in jobs)
    require(units == word_count + scene_count, "Generation budget accounting mismatch")
    write_jsonl(output / "requests.jsonl", jobs)
    write_jsonl(output / "selected-targets.jsonl", selected)
    plan = {"schema_version": 2, "status": "offline-plan-not-executed", "word_pack": pack,
            "word_targets": word_count, "scene_slots": scene_count, "maximum_items": units,
            "maximum_senses_per_item": 3, "request_count": len(jobs), "batch_size": batch_size,
            "prompt_sha256": digest(PROMPT.read_bytes()),
            "catalog_manifest_sha256": digest(canonical(manifest)),
            "prepared_directory": str(Path(prepared).resolve()),
            "files": {name: digest((output / name).read_bytes())
                      for name in ("requests.jsonl", "selected-targets.jsonl")}}
    write_json(output / "plan.json", plan)
    return plan


def load_plan(directory=CACHE / "pilot"):
    directory = generated_directory(directory)
    plan = read_json(directory / "plan.json")
    require(plan["schema_version"] == 2, "Unknown request plan version")
    require(digest(PROMPT.read_bytes()) == plan["prompt_sha256"], "Prompt changed; rebuild the plan")
    _, _, catalog_manifest = load_prepared(plan["prepared_directory"])
    require(digest(canonical(catalog_manifest)) == plan["catalog_manifest_sha256"],
            "Catalog changed; rebuild the plan")
    require(set(plan["files"]) == {"requests.jsonl", "selected-targets.jsonl"},
            "Unexpected plan artifacts")
    for name, expected in plan["files"].items():
        require(digest((directory / name).read_bytes()) == expected, "Request plan checksum mismatch")
    jobs = read_jsonl(directory / "requests.jsonl")
    require(len(jobs) == plan["request_count"], "Request count mismatch")
    ids, targets = set(), set()
    for job in jobs:
        require(job["id"] not in ids, "Duplicate request ID")
        ids.add(job["id"])
        require(digest(canonical(job["messages"])) == job["request_sha256"], "Request digest mismatch")
        expected_messages = make_job(job["task"], job["payload"]["targets"],
                                     PROMPT.read_text(encoding="utf-8"), job["payload"].get("scenario"))
        require(job == expected_messages, "Request payload and messages disagree")
        for target in job["payload"]["targets"]:
            require(target["target_id"] not in targets, "Duplicate target ID in plan")
            targets.add(target["target_id"])
    require(sum(job["units"] for job in jobs) == plan["maximum_items"] == len(targets),
            "Request item budget mismatch")
    return plan, jobs
