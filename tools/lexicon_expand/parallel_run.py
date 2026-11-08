"""Two-provider pilot runner; one owner per request and a shared attempt budget."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path
import json

from tools.lexicon_expand.common import CACHE, Invalid, canonical, digest, read_json, require, write_json, write_jsonl
from tools.lexicon_expand.generation import generate, read_attempts, run_lock
from tools.lexicon_expand.planning import load_plan
from tools.lexicon_expand.provider import load_config


def run(*, execute=False, retry_failed=False):
    plan_dir = CACHE / 'pilot'
    plan, jobs = load_plan(plan_dir)
    providers = [(CACHE / 'api.local.json', CACHE / 'pilot-results-v1'),
                 (CACHE / 'api.grok.local.json', CACHE / 'pilot-results-grok')]
    output = CACHE / 'pilot-results-combined'
    with run_lock(output):
        configs = [load_config(path) for path, _ in providers]
        identities = [digest(canonical({'plan': plan, 'provider': config})) for config in configs]
        def receipts():
            rows = []
            for index, (_, directory) in enumerate(providers):
                if (directory / 'run.json').exists():
                    require(read_json(directory / 'run.json')['identity'] == identities[index], 'Provider configuration changed')
                rows.extend((index, row) for row in read_attempts(directory, jobs, identities[index]))
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
            summary = {'status': 'pending-language-review' if len(completed) == len(jobs) else 'generation-incomplete',
                       'planned_items': plan['maximum_items'], 'planned_requests': len(jobs),
                       'completed_requests': len(completed), 'returned_items': len(records),
                       'resolved_draft_items': sum(bool(r['senses']) for r in records),
                       'unresolved_items': sum(not r['senses'] for r in records),
                       'attempts_including_legacy': len(current) + legacy_attempts,
                       'reserved_output_tokens': sum(r['reserved_output_tokens'] for _, r in current) + legacy_tokens,
                       'failed_attempts_including_legacy': sum(r['status'] == 'failed' for _, r in current) + legacy_attempts,
                       'uncertain_attempts': sum(r['status'] == 'started' for _, r in current),
                       'provider_reported_usage': {k: sum(r.get('usage', {}).get(k, 0) for _, r in current)
                                                   for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')},
                       'attempts_with_reported_usage': sum(bool(r.get('usage')) for _, r in current),
                       'items_by_model': dict(Counter(r['generation']['requested_model'] for r in records)),
                       'human_approved_items': 0, 'release_ready': False, 'currency_cost': None}
            write_jsonl(output / 'drafts.jsonl', records)
            write_json(output / 'summary.json', summary)
            return current, summary
        rows, summary = summarize()
        done = {r['request_id'] for _, r in rows if r['status'] == 'completed'}
        failed = {r['request_id'] for _, r in rows if r['status'] == 'failed'} - done
        require(not summary['uncertain_attempts'], 'Inspect uncertain requests before continuing')
        pending = [j for j in jobs if j['id'] not in done and (retry_failed or j['id'] not in failed)]
        require(summary['attempts_including_legacy'] + len(pending) <= 60, 'Shared attempt cap exceeded')
        require(summary['reserved_output_tokens'] + sum(configs[allocation[j['id']]]['max_output_tokens'] for j in pending) <= 245760,
                'Shared output reservation cap exceeded')
        if not execute:
            return {**summary, 'pending_requests_this_pass': len(pending), 'execute': False}
        def worker(index):
            selected = [j['id'] for j in pending if allocation[j['id']] == index]
            for request_id in selected:
                try:
                    generate(plan_dir, providers[index][0], providers[index][1], execute=True,
                             request_ids=[request_id], retry_failed=retry_failed,
                             progress=lambda event: print(json.dumps({'model': configs[index]['model'], **event}), flush=True))
                except Invalid as error:
                    print(json.dumps({'model': configs[index]['model'], 'request_id': request_id, 'error': str(error)}), flush=True)
                    # Stop this provider after a failure; leave the remainder
                    # unsent for an explicit later resume instead of cascading.
                    break
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, index) for index in range(2)]
            for future in futures:
                future.result()
        return summarize()[1]


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--retry-failed', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(execute=args.execute, retry_failed=args.retry_failed), ensure_ascii=False, indent=2))
