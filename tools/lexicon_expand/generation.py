"""Bounded external generation, atomic receipts, resume and a separate draft file."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path

from tools.lexicon_expand import provider
from tools.lexicon_expand.common import (
    CACHE, Invalid, canonical, digest, generated_directory, read_json, require,
)
from tools.lexicon_expand.storage import atomic_write, write_json, write_jsonl
from tools.lexicon_expand.planning import load_plan
from tools.lexicon_expand.interruptions import effective_interruption
from tools.lexicon_expand.normalization import ResponseValidationError, parse_reply


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class GenerationFailure(Invalid):
    def __init__(self, message, *, retryable):
        super().__init__(message)
        self.retryable = retryable


@contextmanager
def run_lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".run.lock").open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Invalid("Another process is using this generation directory") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def read_attempts(output, jobs, identity, *, include_recoveries=True):
    expected = {job["id"]: job for job in jobs}
    attempts = []
    for path in sorted((output / "attempts").glob("*.json")):
        attempt = read_json(path)
        require(attempt["identity"] == identity and attempt["request_id"] in expected,
                "Attempt belongs to a different model or request plan")
        require(attempt["sequence"] == len(attempts) + 1, "Missing or duplicated attempt sequence")
        require(attempt["status"] in ("started", "failed", "completed"), "Unknown attempt state")
        if include_recoveries:
            attempt = effective_interruption(output, path, attempt)
        if (include_recoveries and attempt['status'] == 'failed' and 'response_sha256' in attempt
                and 'failure_category' not in attempt):
            # Reclassify old content failures in the effective view only. Raw receipts
            # remain the authority for policy baselines and historical accounting.
            raw = (output / 'responses' / path.name).read_bytes()
            require(digest(raw) == attempt['response_sha256'], 'Saved provider response changed')
            attempt = {**attempt, 'retryable': True, 'failure_scope': 'request', 'failure_category': 'content'}
            try:
                content, _, _ = provider.decode_response(raw)
                parse_reply(content, expected[attempt['request_id']], {})
            except (ValueError, TypeError, KeyError) as error:
                attempt['validation_error'] = error.detail if isinstance(error, ResponseValidationError) else {
                    'code': 'provider-envelope', 'path': '$', 'message': 'Invalid or incomplete provider response envelope'}
        recovery_path = output / 'recoveries' / path.name
        if include_recoveries and recovery_path.exists():
            recovery = read_json(recovery_path)
            require(attempt['status'] == 'failed' and recovery['receipt_sha256'] == digest(path.read_bytes()),
                    'Recovery does not match the original failure receipt')
            require(recovery['identity'] == identity and recovery['request_id'] == attempt['request_id'],
                    'Recovery belongs to another model or request')
            attempt = {**attempt, 'original_status': 'failed', 'status': 'completed',
                       'records': recovery['records'], 'generation': recovery['generation'],
                       'recovered_at': recovery['recovered_at']}
        if attempt["status"] == "completed":
            raw_path = output / "responses" / f"{attempt['sequence']:05d}.json"
            raw = raw_path.read_bytes()
            require(digest(raw) == attempt["response_sha256"], "Saved provider response changed")
            content, _, _ = provider.decode_response(raw)
            records, checked_generation = parse_reply(content, expected[attempt["request_id"]], attempt["generation"])
            require(checked_generation == attempt['generation'], 'Saved normalization metadata changed')
            require(records == attempt["records"], "Saved drafts do not match the provider response")
        attempts.append(attempt)
    return attempts


def write_summary(output, plan, attempts):
    completed = {}
    for attempt in attempts:
        if attempt["status"] == "completed":
            require(attempt["request_id"] not in completed, "A request completed more than once")
            completed[attempt["request_id"]] = attempt
    records = [record for attempt in completed.values() for record in attempt["records"]]
    records.sort(key=lambda record: record["id"])
    require(len({record["id"] for record in records}) == len(records), "Duplicate generated target ID")
    summary = {
        "schema_version": 2,
        "status": "pending-language-review" if len(completed) == plan["request_count"] else "generation-incomplete",
        "planned_items": plan["maximum_items"],
        "planned_requests": plan["request_count"], "attempts": len(attempts),
        "completed_requests": len(completed),
        "failed_attempts": sum(a.get('original_status', a['status']) == "failed" for a in attempts),
        "recovered_requests": sum('recovered_at' in a for a in attempts),
        "uncertain_attempts": sum(a["status"] == "started" for a in attempts),
        "unconfirmed_provider_outcomes": sum(bool(a.get('outcome_unknown')) for a in attempts),
        "returned_items": len(records), "resolved_draft_items": sum(bool(r["senses"]) for r in records),
        "unresolved_items": sum(not r["senses"] for r in records), "human_approved_items": 0,
        "reserved_output_tokens": sum(a["reserved_output_tokens"] for a in attempts),
        "provider_reported_usage": {field: sum(a.get("usage", {}).get(field, 0) for a in attempts)
                                    for field in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "attempts_with_reported_usage": sum(bool(a.get("usage")) for a in attempts),
        "currency_cost": None, "release_ready": False,
    }
    if plan['schema_version'] == 3:
        senses = [s for record in records for s in record['senses']]
        summary.update(schema_version=3, quality_policy=plan['quality_policy'],
                       blocked_senses=sum(s['quality']['disposition'] == 'blocked' for s in senses),
                       pronunciation_or_case_review_senses=sum(
                           s['quality']['disposition'] == 'review-required' for s in senses),
                       senses_needing_trigger_addition=sum(not s['quality']['base_reading_present'] for s in senses),
                       semantic_approved_senses=0)
        write_jsonl(output / 'quality-issues.jsonl', [
            {'target_id': record['id'], 'sense_id': s['id'], 'quality': s['quality']}
            for record in records for s in record['senses'] if s['quality']['findings']])
    write_jsonl(output / "drafts.jsonl", records)
    write_json(output / "summary.json", summary)
    return summary


def generate(plan_directory, config_path, output=CACHE / "pilot-results", *, execute=False,
             max_items=300, max_requests=60, max_output_budget=245760,
             retry_failed=False, retry_uncertain=False, progress=None, request_ids=None):
    plan, jobs = load_plan(plan_directory)
    config = provider.load_config(config_path)
    selected = {job['id'] for job in jobs} if request_ids is None else set(request_ids)
    require(selected.issubset({job['id'] for job in jobs}), 'Unknown selected request ID')
    require(type(max_items) is int and max_items > 0 and plan["maximum_items"] <= max_items,
            "Plan exceeds --max-items; inspect the plan before raising the cap")
    require(type(max_requests) is int and max_requests > 0, "Invalid request cap")
    require(type(max_output_budget) is int and max_output_budget > 0, "Invalid output token cap")
    preview = {"execute": False, "endpoint": config["endpoint"], "model": config["model"],
               "planned_items": plan["maximum_items"], "planned_requests": len(jobs),
               "initial_output_token_ceiling": len(jobs) * config["max_output_tokens"],
               "request_cap": max_requests, "output_token_cap": max_output_budget,
               "api_key_read": False, "model_requests": 0}
    if not execute:
        return preview
    output = generated_directory(output)
    require(output not in (Path(plan_directory).resolve(), Path(plan["prepared_directory"]).resolve()),
            "Use a separate generation output directory")
    identity = digest(canonical({"plan": plan, "provider": config}))
    with run_lock(output):
        run_path = output / "run.json"
        if run_path.exists():
            require(read_json(run_path)["identity"] == identity,
                    "Output is bound to another plan/configuration; choose a new directory")
        else:
            require(not list((output / "attempts").glob("*.json")), "Orphaned attempt receipts")
            write_json(run_path, {"schema_version": 2, "identity": identity,
                                  "plan_sha256": digest(canonical(plan)), "provider": config,
                                  "started_at": now()})
        attempts = read_attempts(output, jobs, identity)
        completed = {a["request_id"] for a in attempts if a["status"] == "completed"}
        pending = [job for job in jobs if job["id"] in selected and job["id"] not in completed]
        summary = write_summary(output, plan, attempts)
        if not pending:
            return summary
        for job in pending:
            previous = [a for a in attempts if a["request_id"] == job["id"]]
            if any(a["status"] == "started" for a in previous):
                require(retry_uncertain, "An earlier request has an uncertain outcome; inspect receipts before --retry-uncertain")
            elif any(a["status"] == "failed" for a in previous):
                require(retry_failed, "An earlier request failed; inspect receipts before --retry-failed")
        require(len(attempts) + len(pending) <= max_requests, "Remaining requests exceed the total attempt cap")
        reserved = sum(a["reserved_output_tokens"] for a in attempts)
        require(reserved + len(pending) * config["max_output_tokens"] <= max_output_budget,
                "Remaining requests exceed the total reserved output token cap")
        key = provider.read_key(config["api_key_env"])
        for job in pending:
            sequence = len(attempts) + 1
            path = output / "attempts" / f"{sequence:05d}.json"
            attempt = {"sequence": sequence, "identity": identity, "request_id": job["id"],
                       "request_sha256": job["request_sha256"], "status": "started", "started_at": now(),
                       "reserved_output_tokens": config["max_output_tokens"]}
            write_json(path, attempt)
            attempts.append(attempt)
            if progress:
                progress({"event": "request_started", "sequence": sequence, "items": job["units"]})
            raw_saved = False
            try:
                raw = provider.complete(config, key, job)
                require(key.encode("utf-8") not in raw, "Provider echoed credential data; response withheld")
                raw_path = output / "responses" / f"{sequence:05d}.json"
                atomic_write(raw_path, raw)
                raw_saved = True
                attempt["response_sha256"] = digest(raw)
                # Even truncated/invalid content may have consumed billable tokens.
                attempt["usage"] = provider.token_usage(raw)
                content, usage, reported_model = provider.decode_response(raw)
                attempt["usage"] = usage
                generation = {"kind": "external-api", "endpoint": config["endpoint"],
                              "requested_model": config["model"], "reported_model": reported_model,
                              "request_id": job["id"], "request_sha256": job["request_sha256"],
                              "prompt_sha256": plan["prompt_sha256"], "response_sha256": digest(raw),
                              "received_at": now()}
                records, generation = parse_reply(content, job, generation)
                attempt.update(status="completed", records=records, generation=generation)
            except (provider.ProviderFailure, ValueError, TypeError, KeyError) as error:
                # Parser exceptions can contain model-controlled text; log only a fixed category.
                retryable = error.retryable if isinstance(error, provider.ProviderFailure) else raw_saved
                attempt.update(status="failed", failure_kind=type(error).__name__,
                               retryable=retryable,
                               failure_scope='request' if retryable else 'provider',
                               failure_category='transport' if isinstance(error, provider.ProviderFailure) else
                                                ('content' if raw_saved else 'credential-echo'),
                               failure_message=str(error) if isinstance(error, provider.ProviderFailure)
                               else "Provider response did not pass structural validation")
                if raw_saved:
                    attempt['validation_error'] = error.detail if isinstance(error, ResponseValidationError) else {
                        'code': 'provider-envelope', 'path': '$', 'message': 'Invalid or incomplete provider response envelope'}
                attempt["finished_at"] = now()
                write_json(path, attempt)
                write_summary(output, plan, attempts)
                raise GenerationFailure(attempt["failure_message"] + "; inspect the local receipt and response before retrying",
                                        retryable=attempt["retryable"]) from None
            attempt["finished_at"] = now()
            write_json(path, attempt)
            summary = write_summary(output, plan, attempts)
            if progress:
                progress({"event": "request_completed", "sequence": sequence,
                          "completed_requests": summary["completed_requests"],
                          "resolved_draft_items": summary["resolved_draft_items"]})
        return summary
