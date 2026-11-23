"""Build inspectable, capped API requests without accessing an API key or endpoint."""
from __future__ import annotations

from pathlib import Path

from tools.lexicon_expand.catalog import load_prepared
from tools.lexicon_expand.common import (
    CACHE, ROOT, canonical, digest, generated_directory, read_json, read_jsonl,
    require, write_json, write_jsonl,
)

PROMPT = Path(__file__).with_name("prompt.txt")
PROMPTS = {1: PROMPT, 2: Path(__file__).with_name('prompts') / 'v2.txt',
           3: Path(__file__).with_name('prompts') / 'v3.txt',
           4: Path(__file__).with_name('prompts') / 'v4.txt'}


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


def make_job(task, targets, system_prompt, scenario=None, *, response_version=2, quality_policy=None):
    require(response_version in (2, 3), 'Unknown response schema version')
    payload = {"task": task, "targets": targets}
    if response_version == 3:
        from tools.lexicon_expand.quality import policy
        payload.update(response_schema_version=3, quality_policy=policy() if quality_policy is None else quality_policy)
    if scenario is not None:
        payload["scenario"] = scenario
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": canonical(payload).decode("utf-8")}]
    identity = digest(canonical(messages))
    return {"id": "request-" + identity[:24], "request_sha256": identity,
            "task": task, "units": len(targets), "payload": payload, "messages": messages}


def make_plan(prepared=CACHE / "prepared", output=None, *, word_count=200,
              scene_count=100, batch_size=10, pack="ielts", prompt_version=2):
    require(type(word_count) is int and type(scene_count) is int and word_count >= 0 and scene_count >= 0,
            "Counts must be nonnegative integers")
    require(0 < word_count + scene_count <= 100000, "Empty or oversized generation plan")
    require(1 <= batch_size <= 20, "Batch size must be between 1 and 20")
    require(prompt_version in PROMPTS, 'Unknown prompt version')
    targets, summary, manifest = load_prepared(prepared)
    output = (CACHE / (f'pilot-v{prompt_version}' if prompt_version >= 2 else 'pilot')) if output is None else output
    output = generated_directory(output)
    require(output != Path(prepared).resolve(), "Do not overwrite the prepared catalog")
    prompt = PROMPTS[prompt_version].read_text(encoding="utf-8")
    version = 3 if prompt_version >= 2 else 2
    from tools.lexicon_expand.quality import policy
    selected_policy = policy(2 if prompt_version >= 3 else 1) if version == 3 else None
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
        jobs.append(make_job("map_targets", group, prompt, response_version=version, quality_policy=selected_policy))
    scenarios = summary["scenarios"]
    require(bool(scenarios) or scene_count == 0, "No scene configuration available")
    for index, scenario in enumerate(scenarios):
        quota = scene_count // len(scenarios) + (index < scene_count % len(scenarios))
        for start in range(0, quota, batch_size):
            slots = [{"target_id": f"scene-{scenario['id']}-{slot:05d}",
                      "english": None, "packs": ["scene:" + scenario["id"]],
                      "source_refs": [], "dictionary_references": [], "existing_entries": []}
                     for slot in range(start + 1, min(start + batch_size, quota) + 1)]
            jobs.append(make_job("scene_terms", slots, prompt, scenario, response_version=version, quality_policy=selected_policy))
    units = sum(job["units"] for job in jobs)
    require(units == word_count + scene_count, "Generation budget accounting mismatch")
    plan = {"schema_version": version, "status": "offline-plan-not-executed", "word_pack": pack,
            "word_targets": word_count, "scene_slots": scene_count, "maximum_items": units,
            "maximum_senses_per_item": 3, "request_count": len(jobs), "batch_size": batch_size,
            "prompt_sha256": digest(PROMPT.read_bytes()) if prompt_version == 1 else digest(prompt.encode('utf-8')),
            "catalog_manifest_sha256": digest(canonical(manifest)),
            "prepared_directory": str(Path(prepared).resolve())}
    if version == 3:
        from tools.lexicon_expand.quality import policy
        plan.update(prompt_version=prompt_version, response_schema_version=3, quality_policy=selected_policy)
    return save_plan(output, plan, jobs, selected, prompt)


def save_plan(output, plan, jobs, selected, prompt):
    artifacts = {'requests.jsonl': b''.join(canonical(j) + b'\n' for j in jobs),
                 'selected-targets.jsonl': b''.join(canonical(t) + b'\n' for t in selected)}
    if plan['schema_version'] == 3:
        artifacts['prompt.txt'] = prompt.encode('utf-8')
    plan = {**plan, 'files': {name: digest(raw) for name, raw in artifacts.items()}}
    if (output / 'plan.json').exists():
        require(read_json(output / 'plan.json') == plan,
                'Output already contains a different plan; choose a new directory')
    else:
        require(not output.exists() or not any(output.iterdir()),
                'Plan output must be empty; choose a new directory')
    from tools.lexicon.pipeline import atomic_write
    for name, raw in artifacts.items():
        atomic_write(output / name, raw)
    write_json(output / 'plan.json', plan)
    return plan


def make_repair_plan(review_batch, output=CACHE / 'repair-v2', *, prepared=CACHE / 'prepared', batch_size=5):
    from tools.lexicon_expand.review_pilot import source_inputs
    from tools.lexicon_expand.quality import policy
    require(type(batch_size) is int and 1 <= batch_size <= 20, 'Invalid repair batch size')
    batch = Path(review_batch).resolve()
    records, decisions, _ = source_inputs(batch)
    catalog, _, manifest = load_prepared(prepared)
    by_id = {t['id']: t for t in catalog}
    selected = []
    for record, decision in zip(records, decisions):
        for sense, code in zip(record['senses'], decision['decisions']):
            if code != 'R':
                continue
            original = by_id.get(record['id'], record)
            selected.append({'target_id': 'repair-' + digest(canonical([record['id'], sense['id']]))[:24],
                'english': record['english'], 'source_forms': original.get('source_forms', []),
                'packs': record['packs'], 'source_refs': record['source_refs'],
                'dictionary_references': original['dictionary_references'],
                'original_target_id': record['id'], 'original_sense': sense,
                'source_record_sha256': digest(canonical(record)), 'review_reason': decision['note']})
    require(bool(selected), 'No senses need revision')
    output = generated_directory(output)
    require(output != Path(prepared).resolve(), 'Do not overwrite the prepared catalog')
    prompt = PROMPTS[2].read_text(encoding='utf-8')
    jobs = [make_job('repair_senses', selected[start:start + batch_size], prompt, response_version=3)
            for start in range(0, len(selected), batch_size)]
    plan = {'schema_version': 3, 'status': 'offline-plan-not-executed', 'task': 'repair_senses',
            'maximum_items': len(selected), 'maximum_senses_per_item': 1,
            'request_count': len(jobs), 'batch_size': batch_size,
            'prompt_version': 2, 'response_schema_version': 3,
            'prompt_sha256': digest(prompt.encode('utf-8')), 'quality_policy': policy(),
            'prepared_directory': str(Path(prepared).resolve()),
            'catalog_manifest_sha256': digest(canonical(manifest)),
            'review_sources': {p.relative_to(ROOT).as_posix(): digest(p.read_bytes())
                               for p in (batch / 'source-drafts.jsonl', batch / 'decisions.tsv')},
            'preserved_accepted_senses': sum(d['decisions'].count('P') for d in decisions),
            'excluded_rejected_senses': sum(d['decisions'].count('X') for d in decisions),
            'automatic_adoption': False}
    return save_plan(output, plan, jobs, selected, prompt)


def load_plan(directory=CACHE / "pilot"):
    directory = generated_directory(directory)
    plan = read_json(directory / "plan.json")
    version = plan['schema_version']
    require(version in (2, 3), "Unknown request plan version")
    prompt_path = PROMPT if version == 2 else directory / 'prompt.txt'
    require(digest(prompt_path.read_bytes()) == plan["prompt_sha256"], "Prompt changed; rebuild the plan")
    if version == 3:
        from tools.lexicon_expand.quality import policy
        require(plan.get('prompt_version') in (2, 3, 4) and plan.get('response_schema_version') == 3,
                'Unknown prompt/response version')
        require(plan['quality_policy'] == policy(plan['quality_policy'].get('version')), 'Quality policy changed')
        for name, sha in plan.get('review_sources', {}).items():
            path = (ROOT / name).resolve()
            require(path.is_relative_to(ROOT) and digest(path.read_bytes()) == sha,
                    'Repair review source changed')
    _, _, catalog_manifest = load_prepared(plan["prepared_directory"])
    require(digest(canonical(catalog_manifest)) == plan["catalog_manifest_sha256"],
            "Catalog changed; rebuild the plan")
    files = {"requests.jsonl", "selected-targets.jsonl"}
    if version == 3:
        files.add('prompt.txt')
    require(set(plan["files"]) == files,
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
                                     prompt_path.read_text(encoding="utf-8"), job["payload"].get("scenario"),
                                     response_version=version, quality_policy=plan.get('quality_policy'))
        require(job == expected_messages, "Request payload and messages disagree")
        for target in job["payload"]["targets"]:
            require(target["target_id"] not in targets, "Duplicate target ID in plan")
            targets.add(target["target_id"])
    require(sum(job["units"] for job in jobs) == plan["maximum_items"] == len(targets),
            "Request item budget mismatch")
    return plan, jobs
