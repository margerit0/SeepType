"""Two-provider pilot runner; one owner per request and a shared attempt budget."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from pathlib import Path
import json
from threading import Event, Lock

from tools.lexicon_expand.common import CACHE, Invalid, canonical, digest, read_json, require
from tools.lexicon_expand.storage import write_json, write_jsonl
from tools.lexicon_expand.generation import GenerationFailure, generate, now, read_attempts, run_lock
from tools.lexicon_expand.planning import load_plan
from tools.lexicon_expand.provider import load_config
from tools.lexicon_expand.retry import MAX_RETRY_DELAY_SECONDS, retry_request


def run(*, execute=False, retry_failed=False, max_retries=None):
    require(max_retries is None or (type(max_retries) is int and 0 <= max_retries <= 15),
            'max_retries must be between 0 and 15')
    plan_dir = CACHE / 'pilot'
    plan, jobs = load_plan(plan_dir)
    providers = [(CACHE / 'api.local.json', CACHE / 'pilot-results-v1'),
                 (CACHE / 'api.grok.local.json', CACHE / 'pilot-results-grok')]
    output = CACHE / 'pilot-results-combined'
    with run_lock(output):
        require(not (output / 'gemini-takeover.json').exists(),
                'Pilot now uses Gemini takeover; resume with tools.lexicon_expand.gemini_takeover')
        policy_path = output / 'retry-policy.json'
        policy = read_json(policy_path) if policy_path.exists() else None
        if max_retries is None:
            max_retries = policy['max_retries'] if policy else 0
        if policy:
            require(max_retries == policy['max_retries'], 'Retry policy is fixed; resume with the same max_retries')
        configs = [load_config(path) for path, _ in providers]
        identities = [digest(canonical({'plan': plan, 'provider': config})) for config in configs]
        def receipts(*, include_recoveries=True):
            rows = []
            for index, (_, directory) in enumerate(providers):
                if (directory / 'run.json').exists():
                    require(read_json(directory / 'run.json')['identity'] == identities[index], 'Provider configuration changed')
                rows.extend((index, row) for row in read_attempts(directory, jobs, identities[index],
                                                                include_recoveries=include_recoveries))
            return rows
        rows = receipts()
        owners = {}
        for index, row in rows:
            require(row['request_id'] not in owners or owners[row['request_id']] == index, 'Request sent to two providers')
            owners[row['request_id']] = index
        allocation_path = output / 'allocation.json'
        if allocation_path.exists():
            allocation = read_json(allocation_path)
            require(allocation['identities'] == identities, 'Allocation configuration changed')
            allocation = allocation['owners']
            require(set(allocation) == {j['id'] for j in jobs}, 'Allocation plan changed')
            require(all(allocation[k] == v for k, v in owners.items()), 'Allocation contradicts receipts')
        else:
            allocation = dict(owners)
            for job in jobs:
                if job['id'] not in allocation:
                    counts = Counter(allocation.values())
                    allocation[job['id']] = min(range(2), key=lambda i: counts[i])
            write_json(allocation_path, {'identities': identities, 'owners': allocation})

        # The original /gemini Chat Completions and native probes are outside
        # these receipt directories, but still count toward the pilot budget.
        legacy_attempts, legacy_tokens = 2, 8192
        def summarize():
            current = receipts()
            completed = [r for _, r in current if r['status'] == 'completed']
            require(len({r['request_id'] for r in completed}) == len(completed), 'Duplicate completed request')
            records = sorted([record for row in completed for record in row['records']], key=lambda r: r['id'])
            require(len({r['id'] for r in records}) == len(records), 'Duplicate draft target')
            done_ids = {r['request_id'] for r in completed}
            latest = {}
            for index, row in current:
                latest[row['request_id']] = (index, row)
            issues = []
            for request_id, (index, row) in latest.items():
                if request_id not in done_ids and row['status'] == 'failed':
                    failures = [r for i, r in current if i == index and r['request_id'] == request_id
                                and r['status'] == 'failed' and (not policy or r['sequence'] > policy['baseline_counts'][index])]
                    scope = row.get('failure_scope', 'request' if row.get('retryable') else 'provider')
                    issues.append({'request_id': request_id, 'model': configs[index]['model'],
                                   'sequence': row['sequence'], 'failure_scope': scope,
                                   'failure_category': row.get('failure_category', 'legacy'),
                                   'error': row.get('failure_message'), 'validation_error': row.get('validation_error'),
                                   'failed_attempts_under_policy': len(failures),
                                   'state': 'provider-stopped' if scope == 'provider' else
                                            ('retry-limit' if policy and len(failures) > max_retries else
                                             ('retry-pending' if policy else 'retry-disabled'))})
            write_jsonl(output / 'issues.jsonl', issues)
            summary = {'status': 'pending-language-review' if len(completed) == len(jobs) else 'generation-incomplete',
                       'planned_items': plan['maximum_items'], 'planned_requests': len(jobs),
                       'completed_requests': len(completed), 'returned_items': len(records),
                       'resolved_draft_items': sum(bool(r['senses']) for r in records),
                       'unresolved_items': sum(not r['senses'] for r in records),
                       'attempts_including_legacy': len(current) + legacy_attempts,
                       'reserved_output_tokens': sum(r['reserved_output_tokens'] for _, r in current) + legacy_tokens,
                       'failed_attempts_including_legacy': sum(r.get('original_status', r['status']) == 'failed' for _, r in current) + legacy_attempts,
                       'recovered_requests': sum('recovered_at' in r for _, r in current),
                       'requests_with_issues': len(issues),
                       'uncertain_attempts': sum(r['status'] == 'started' for _, r in current),
                       'provider_reported_usage': {k: sum(r.get('usage', {}).get(k, 0) for _, r in current)
                                                   for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')},
                       'attempts_with_reported_usage': sum(bool(r.get('usage')) for _, r in current),
                       'items_by_model': dict(Counter(r['generation']['requested_model'] for r in records)),
                       'human_approved_items': 0, 'release_ready': False, 'currency_cost': None}
            if policy:
                summary['retry_policy'] = policy
            write_jsonl(output / 'drafts.jsonl', records)
            write_json(output / 'summary.json', summary)
            return current, summary
        rows, summary = summarize()
        done = {r['request_id'] for _, r in rows if r['status'] == 'completed'}
        failed = {r['request_id'] for _, r in rows if r['status'] == 'failed'} - done
        require(not summary['uncertain_attempts'], 'Inspect uncertain requests before continuing')
        pending = [j for j in jobs if j['id'] not in done and (retry_failed or j['id'] not in failed)]
        if max_retries and policy is None:
            original_rows = receipts(include_recoveries=False)
            baseline = [[r for i, r in original_rows if i == index] for index in range(2)]
            eligible = [j['id'] for j in pending]
            budgets = [{'attempt_cap': len(baseline[index]) + sum(allocation[k] == index for k in eligible) * (1 + max_retries),
                        'output_token_cap': sum(r['reserved_output_tokens'] for r in baseline[index]) +
                        sum(allocation[k] == index for k in eligible) * (1 + max_retries) * configs[index]['max_output_tokens']}
                       for index in range(2)]
            policy = {'schema_version': 1, 'created_at': now(), 'max_retries': max_retries,
                      'base_delay_seconds': 3, 'max_delay_seconds': MAX_RETRY_DELAY_SECONDS,
                      'identities': identities, 'eligible_requests': eligible,
                      'baseline_counts': [len(b) for b in baseline],
                      'baseline_sha256': [digest(canonical(b)) for b in baseline],
                      'provider_budgets': budgets,
                      'shared_attempt_cap': max(60, legacy_attempts + sum(b['attempt_cap'] for b in budgets)),
                      'shared_output_token_cap': max(245760, legacy_tokens + sum(b['output_token_cap'] for b in budgets))}
            if execute:
                write_json(policy_path, policy)
        if policy:
            require(policy['identities'] == identities, 'Retry policy configuration changed')
            require({j['id'] for j in pending}.issubset(policy['eligible_requests']), 'Request is outside the retry policy')
            for index in range(2):
                baseline = [r for i, r in receipts(include_recoveries=False) if i == index][:policy['baseline_counts'][index]]
                require(digest(canonical(baseline)) == policy['baseline_sha256'][index], 'Retry baseline changed')
            # Apply the approved wait cap to old runs without renewing their retry budget.
            if policy.get('max_delay_seconds') != MAX_RETRY_DELAY_SECONDS:
                policy['max_delay_seconds'] = MAX_RETRY_DELAY_SECONDS
                if execute:
                    write_json(policy_path, policy)
            attempt_cap, token_cap = policy['shared_attempt_cap'], policy['shared_output_token_cap']
        else:
            attempt_cap, token_cap = 60, 245760
        require(summary['attempts_including_legacy'] + len(pending) <= attempt_cap, 'Shared attempt cap exceeded')
        require(summary['reserved_output_tokens'] + sum(configs[allocation[j['id']]]['max_output_tokens'] for j in pending) <= token_cap,
                'Shared output reservation cap exceeded')
        if not execute:
            return {**summary, 'pending_requests_this_pass': len(pending), 'execute': False,
                    'retry_policy': policy}
        stop_path = output / 'stop.json'
        stop_path.unlink(missing_ok=True)
        stopped = Event()
        state_lock = Lock()
        states = {}
        def cancelled():
            return stopped.is_set() or stop_path.exists()
        def emit(index, request_id, event):
            data = {'model': configs[index]['model'], 'request_id': request_id, **event}
            with state_lock:
                states[str(index)] = {**data, 'updated_at': now()}
                write_json(output / 'retry-state.json', states)
            print(json.dumps(data, ensure_ascii=False), flush=True)
        def worker(index):
            selected = [j['id'] for j in pending if allocation[j['id']] == index]
            for request_id in selected:
                if cancelled():
                    break
                def send():
                    kwargs = policy['provider_budgets'][index] if policy else {}
                    try:
                        return generate(plan_dir, providers[index][0], providers[index][1], execute=True,
                                        request_ids=[request_id], retry_failed=retry_failed or bool(max_retries),
                                        max_requests=kwargs.get('attempt_cap', 60),
                                        max_output_budget=kwargs.get('output_token_cap', 245760),
                                        progress=lambda event: emit(index, request_id, event))
                    finally:
                        with state_lock:
                            summarize()
                def history():
                    return [r for r in read_attempts(providers[index][1], jobs, identities[index])
                            if r['sequence'] > policy['baseline_counts'][index] and r['request_id'] == request_id]
                try:
                    if policy:
                        if not retry_request(send, history, max_retries=max_retries,
                                             emit=lambda event: emit(index, request_id, event), cancelled=cancelled):
                            last = history()[-1]
                            scope = last.get('failure_scope', 'request' if last.get('retryable') else 'provider')
                            emit(index, request_id, {'event': 'provider_stopped' if scope == 'provider' else 'request_queued',
                                                     'failure_scope': scope, 'error': last.get('failure_message'),
                                                     'validation_error': last.get('validation_error')})
                            if scope == 'provider':
                                break
                            continue
                    else:
                        send()
                except GenerationFailure as error:
                    if error.retryable:
                        # With retries disabled, isolate content errors; transport keeps its old stop behavior.
                        last = read_attempts(providers[index][1], jobs, identities[index])[-1]
                        if last.get('failure_category') == 'content':
                            emit(index, request_id, {'event': 'request_queued', 'failure_scope': 'request',
                                                     'error': last.get('failure_message'),
                                                     'validation_error': last.get('validation_error')})
                            continue
                    emit(index, request_id, {'event': 'provider_stopped', 'error': str(error)})
                    break
                except Invalid as error:
                    emit(index, request_id, {'event': 'provider_stopped', 'error': str(error)})
                    break
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, index) for index in range(2)]
            try:
                for future in as_completed(futures):
                    future.result()
            except BaseException:
                stopped.set()
                raise
        return summarize()[1]


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--retry-failed', action='store_true')
    parser.add_argument('--max-retries', type=int, default=None, help='Retries per request, 0 to 15; persisted across restarts')
    parser.add_argument('--stop', action='store_true', help='Stop waiting workers after in-flight requests finish')
    args = parser.parse_args()
    if args.stop:
        write_json(CACHE / 'pilot-results-combined/stop.json', {'requested_at': now()})
        print('Stop requested; in-flight requests will finish before workers exit.')
    else:
        print(json.dumps(run(execute=args.execute, retry_failed=args.retry_failed, max_retries=args.max_retries),
                         ensure_ascii=False, indent=2))
