"""Resume missing and unresolved pilot items on Gemini with separate receipts."""
from collections import Counter
import json

from tools.lexicon_expand.common import CACHE, Invalid, canonical, digest, read_json, require
from tools.lexicon_expand.generation import generate, now, read_attempts, run_lock
from tools.lexicon_expand.interruptions import inspect_interrupted
from tools.lexicon_expand.planning import load_plan
from tools.lexicon_expand.provider import load_config
from tools.lexicon_expand.retry import MAX_RETRY_DELAY_SECONDS, retry_request
from tools.lexicon_expand.storage import write_json, write_jsonl


def merge_records(original, replacement):
    """Keep every original item that already has senses, including provenance."""
    merged = {r['id']: r for r in original}
    require(len(merged) == len(original), 'Duplicate original target')
    require(len({r['id'] for r in replacement}) == len(replacement), 'Duplicate takeover target')
    for record in replacement:
        if record['id'] not in merged or not merged[record['id']]['senses']:
            merged[record['id']] = record
    return sorted(merged.values(), key=lambda r: r['id'])


def run(*, execute=False, resume_interrupted=False, rerun_issues=False):
    output = CACHE / 'pilot-results-combined'
    phase = 'gemini-rerun-issues' if rerun_issues else 'gemini-takeover'
    destination = CACHE / ('pilot-results-' + phase)
    with run_lock(output):
        require(rerun_issues or not (output / 'gemini-rerun-issues.json').exists(),
                'Pilot now uses Gemini issue rerun; continue with --rerun-issues')
        plan, jobs = load_plan(CACHE / 'pilot')
        config = load_config(CACHE / 'api.local.json')
        identity = digest(canonical({'plan': plan, 'provider': config}))
        allocation = read_json(output / 'allocation.json')
        require(identity == allocation['identities'][0], 'Gemini configuration changed')
        policy = read_json(output / 'retry-policy.json')
        original, original_records = [], []
        source_files = [output / 'allocation.json', output / 'retry-policy.json']
        sources = [('pilot-results-v1', 0), ('pilot-results-grok', 1)]
        if rerun_issues:
            sources.append(('pilot-results-gemini-takeover', 0))
        for name, index in sources:
            if name == 'pilot-results-gemini-takeover':
                previous_manifest = read_json(output / 'gemini-takeover.json')
                require(previous_manifest['identity'] == identity and previous_manifest['source_hashes'] == {
                    p.relative_to(CACHE).as_posix(): digest(p.read_bytes()) for p in source_files},
                    'Original takeover sources or configuration changed')
                source_files.append(output / 'gemini-takeover.json')
            directory = CACHE / name
            source_rows = read_attempts(directory, jobs, allocation['identities'][index])
            original.extend(source_rows)
            original_records = merge_records(original_records, [record for row in source_rows
                                              if row['status'] == 'completed' for record in row['records']])
            source_files.append(directory / 'run.json')
            for child in ('attempts', 'responses', 'recoveries', 'interruptions'):
                source_files.extend(sorted((directory / child).glob('*.json')))
        require(not any(r['status'] == 'started' for r in original),
                'Wait for original in-flight requests to finish before takeover')
        resolved = {r['id'] for r in original_records if r['senses']}
        selected = [j['id'] for j in jobs if any(t['target_id'] not in resolved for t in j['payload']['targets'])]
        hashes = {p.relative_to(CACHE).as_posix(): digest(p.read_bytes()) for p in source_files}
        manifest_path = output / (phase + '.json')
        if manifest_path.exists():
            manifest = read_json(manifest_path)
            require(manifest['identity'] == identity and manifest['selected_requests'] == selected,
                    'Takeover configuration or source selection changed')
            require(manifest['source_hashes'] == hashes, 'Original pilot receipts or policy changed')
        else:
            manifest = {'schema_version': 1, 'created_at': now(), 'identity': identity,
                        'reason': ('User explicitly requested rerunning the outstanding items; previous phase retries remain frozen'
                                   if rerun_issues else 'User requested Gemini instead of repeatedly failing Grok'),
                        'generation_phase': phase,
                        'selected_requests': selected, 'source_hashes': hashes,
                        'source_summary': read_json(output / 'summary.json'),
                        'max_retries': policy['max_retries'],
                        'shared_attempt_cap': policy['shared_attempt_cap'],
                        'shared_output_token_cap': policy['shared_output_token_cap']}
        # Historical requests keep their original provider and retry receipts. The
        # new provider phase can use only what remains of the original shared cap.
        attempt_cap = manifest['shared_attempt_cap'] - len(original) - 2
        token_cap = manifest['shared_output_token_cap'] - sum(r['reserved_output_tokens'] for r in original) - 8192

        def history():
            rows = read_attempts(destination, jobs, identity)
            require(all(r['request_id'] in selected for r in rows), 'Unexpected takeover request')
            return rows

        if resume_interrupted:
            require(execute, 'Interruption inspection requires --execute')
            with run_lock(destination):
                inspect_interrupted(destination, read_json(output / 'background-state.json'),
                                    config['timeout_seconds'])
        rows = history()
        require(not any(r['status'] == 'started' for r in rows), 'Inspect uncertain takeover requests before continuing')
        done = {r['request_id'] for r in rows if r['status'] == 'completed'}
        pending = [j for j in jobs if j['id'] in selected and j['id'] not in done]
        if not execute:
            return {'execute': False, 'model': config['model'], 'pending_requests': len(pending),
                    'targets_in_selected_requests': sum(j['units'] for j in pending),
                    'preserved_resolved_items': len(resolved), 'source_files': len(hashes),
                    'attempt_cap_for_takeover': attempt_cap, 'output_token_cap_for_takeover': token_cap,
                    'max_retries': manifest['max_retries'], 'max_delay_seconds': MAX_RETRY_DELAY_SECONDS}
        require(not pending or (attempt_cap > len(rows) and
                token_cap >= sum(r['reserved_output_tokens'] for r in rows) + config['max_output_tokens']),
                'Original shared budget has no remaining request capacity')
        write_json(manifest_path, manifest)
        stop_path = output / 'stop.json'
        stop_path.unlink(missing_ok=True)

        def cancelled():
            return stop_path.exists()

        def emit(request_id, event):
            data = {'model': config['model'], 'request_id': request_id, **event}
            write_json(output / 'retry-state.json', {'0': {**data, 'updated_at': now()}})
            print(json.dumps(data, ensure_ascii=False), flush=True)

        def summarize():
            current = history()
            replacements = [record for row in current if row['status'] == 'completed' for record in row['records']]
            merged = merge_records(original_records, replacements)
            by_id = {r['id']: r for r in merged}
            expected = {t['target_id'] for j in jobs for t in j['payload']['targets']}
            require(set(by_id).issubset(expected), 'Takeover returned an unexpected target')
            all_rows = original + current
            latest = {r['request_id']: r for r in current}
            issues = []
            for job in jobs:
                missing = [t['target_id'] for t in job['payload']['targets'] if t['target_id'] not in by_id]
                unresolved = [t['target_id'] for t in job['payload']['targets']
                              if t['target_id'] in by_id and not by_id[t['target_id']]['senses']]
                if missing or unresolved:
                    last = latest.get(job['id'], {})
                    issues.append({'request_id': job['id'], 'model': config['model'],
                                   'missing_targets': missing, 'unresolved_targets': unresolved,
                                   'state': 'unresolved' if last.get('status') == 'completed' else
                                            ('takeover-' + last['status'] if last else 'takeover-pending'),
                                   'error': last.get('failure_message'), 'validation_error': last.get('validation_error')})
            resolved_count = sum(bool(r['senses']) for r in merged)
            summary = {'status': 'pending-language-review' if resolved_count == plan['maximum_items'] else 'generation-incomplete',
                       'generation_phase': phase, 'active_model': config['model'],
                       'planned_items': plan['maximum_items'], 'planned_requests': len(jobs),
                       'completed_requests': sum(all(t['target_id'] in by_id for t in j['payload']['targets']) for j in jobs),
                       'resolved_requests': sum(all(t['target_id'] in by_id and by_id[t['target_id']]['senses']
                                                   for t in j['payload']['targets']) for j in jobs),
                       'returned_items': len(merged), 'resolved_draft_items': resolved_count,
                       'unresolved_items': len(merged) - resolved_count, 'missing_items': plan['maximum_items'] - len(merged),
                       'attempts_including_legacy': len(all_rows) + 2,
                       'reserved_output_tokens': sum(r['reserved_output_tokens'] for r in all_rows) + 8192,
                       'failed_attempts_including_legacy': sum(r.get('original_status', r['status']) == 'failed' for r in all_rows) + 2,
                       'recovered_requests': sum('recovered_at' in r for r in all_rows),
                       'uncertain_attempts': sum(r['status'] == 'started' for r in all_rows),
                       'unconfirmed_provider_outcomes': sum(bool(r.get('outcome_unknown')) for r in all_rows),
                       'requests_with_issues': len(issues),
                       'provider_reported_usage': {k: sum(r.get('usage', {}).get(k, 0) for r in all_rows)
                                                   for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')},
                       'attempts_with_reported_usage': sum(bool(r.get('usage')) for r in all_rows),
                       'items_by_model': dict(Counter(r['generation']['requested_model'] for r in merged)),
                       'retry_policy': policy, 'human_approved_items': 0, 'release_ready': False, 'currency_cost': None}
            require(summary['attempts_including_legacy'] <= manifest['shared_attempt_cap'], 'Shared attempt cap exceeded')
            require(summary['reserved_output_tokens'] <= manifest['shared_output_token_cap'], 'Shared output token cap exceeded')
            write_jsonl(output / 'drafts.jsonl', merged)
            write_jsonl(output / 'issues.jsonl', issues)
            write_json(output / 'summary.json', summary)
            return summary

        summarize()
        for job in pending:
            if cancelled():
                break
            request_id = job['id']

            def send():
                try:
                    return generate(CACHE / 'pilot', CACHE / 'api.local.json', destination, execute=True,
                                    request_ids=[request_id], retry_failed=True,
                                    max_requests=attempt_cap, max_output_budget=token_cap,
                                    progress=lambda event: emit(request_id, event))
                finally:
                    summarize()

            def request_history():
                # Repeating malformed content unchanged wastes tokens. Keep the
                # raw receipt, but queue such a request after its first failure.
                return [{**r, 'retryable': False} if r.get('failure_category') == 'content' else r
                        for r in history() if r['request_id'] == request_id]

            try:
                completed = retry_request(send, request_history, max_retries=manifest['max_retries'],
                                          emit=lambda event: emit(request_id, event), cancelled=cancelled)
                if not completed:
                    last = request_history()[-1]
                    emit(request_id, {'event': 'request_queued', 'error': last.get('failure_message'),
                                      'validation_error': last.get('validation_error')})
                    if last.get('failure_scope') == 'provider':
                        break
            except Invalid as error:
                emit(request_id, {'event': 'provider_stopped', 'error': str(error)})
                break
        return summarize()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--resume-interrupted', action='store_true',
                        help='Inspect an exited background owner and retain unknown-outcome receipts before retrying')
    parser.add_argument('--rerun-issues', action='store_true',
                        help='Use the separate user-authorized rerun phase for outstanding items')
    args = parser.parse_args()
    print(json.dumps(run(execute=args.execute, resume_interrupted=args.resume_interrupted,
                         rerun_issues=args.rerun_issues), ensure_ascii=False, indent=2))
