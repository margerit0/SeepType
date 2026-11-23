"""Run a frozen single-arm expansion with persistent receipts and bounded retries."""
from datetime import datetime, timezone
import json
import re

from tools.lexicon import pipeline as legacy
from tools.lexicon_expand.common import CACHE, ROOT, canonical, digest, read_json, require, write_json
from tools.lexicon_expand.generation import generate, read_attempts, run_lock
from tools.lexicon_expand.planning import load_plan
from tools.lexicon_expand.provider import load_config
from tools.lexicon_expand.repair_trial import unchanged_file
from tools.lexicon_expand.retry import retry_request
from tools.lexicon_expand.recover import recover_saved


def run(batch, *, progress=None):
    require(isinstance(batch, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', batch) is not None,
            'Use one batch directory name')
    work = CACHE / batch
    review = ROOT / 'data/lexicon-expansion/reviews' / batch
    raw = (work / 'batch-plan.json').read_bytes()
    require(raw == (review / 'batch-plan.json').read_bytes(), 'Frozen batch metadata copies differ')
    meta = read_json(work / 'batch-plan.json')
    plan, jobs = load_plan(work / 'plan')
    config = load_config(CACHE / 'api.local.json')
    require(meta['batch'] == batch and digest(canonical(plan)) == meta['plan_sha256'], 'Batch plan changed')
    require(digest(canonical(config)) == meta['provider_sha256'], 'Provider configuration changed')
    require(meta['targets'] == plan['maximum_items'] and meta['request_count'] == len(jobs), 'Batch counts differ')
    require(meta['max_attempts_per_request'] == 30 and meta['max_retries'] == 29 and meta['max_wait_seconds'] == 30,
            'Unexpected retry allowance')
    caps = meta['generation_caps']
    require(caps == dict(max_items=plan['maximum_items'], max_requests=len(jobs) * 30,
                         max_output_budget=len(jobs) * 30 * config['max_output_tokens']), 'Cumulative budget changed')
    output = work / 'results'
    identity = digest(canonical({'plan': plan, 'provider': config}))
    state, error = 'running', None

    def emit(event):
        print(json.dumps(event, ensure_ascii=False), flush=True)

    cancelled = lambda: (work / 'stop.json').exists() or (output / 'stop.json').exists()

    def receipts():
        if not (output / 'run.json').exists():
            return []
        require(read_json(output / 'run.json')['identity'] == identity, 'Run identity changed')
        return read_attempts(output, jobs, identity)

    def archive():
        rows = receipts()
        for path in sorted(output.rglob('*')):
            if not path.is_file() or path.suffix not in ('.json', '.jsonl', '.txt'):
                continue
            if path.parent.name in ('attempts', 'responses'):
                receipt = output / 'attempts' / path.name
                if receipt.exists() and read_json(receipt)['status'] == 'started':
                    continue
            destination = review / 'external/results' / path.relative_to(output)
            raw = path.read_bytes()
            if destination.exists() and destination.read_bytes() != raw:
                require(path.name in ('summary.json', 'drafts.jsonl', 'quality-issues.jsonl'),
                        'Immutable generation evidence changed')
                unchanged_file(review / 'external/history' / (digest(destination.read_bytes()) + '-' + path.name),
                               destination.read_bytes())
                legacy.atomic_write(destination, raw)
            else:
                unchanged_file(destination, raw)
        summary = read_json(output / 'summary.json') if (output / 'summary.json').exists() else {
            'planned_items': plan['maximum_items'], 'planned_requests': len(jobs),
            'completed_requests': 0, 'attempts': 0, 'returned_items': 0}
        completed = {row['request_id'] for row in rows if row['status'] == 'completed'}
        # A request-start callback precedes generation.write_summary; expose live
        # receipt counts rather than the preceding summary's stale counters.
        summary = {**summary, 'planned_requests': len(jobs), 'attempts': len(rows),
                   'completed_requests': len(completed),
                   'uncertain_attempts': sum(r['status'] == 'started' for r in rows),
                   'unconfirmed_provider_outcomes': sum(bool(r.get('outcome_unknown')) for r in rows)}
        incomplete = []
        for job in jobs:
            if job['id'] in completed:
                continue
            history = [r for r in rows if r['request_id'] == job['id']]
            last = history[-1] if history else {}
            reason = ('unknown-outcome' if any(r['status'] == 'started' or r.get('outcome_unknown') for r in history)
                      else 'content-validation' if last.get('failure_category') == 'content'
                      else 'retry-limit' if len(history) >= 30
                      else 'provider-failure' if last.get('failure_scope') == 'provider'
                      else 'not-completed')
            incomplete.append({'request_id': job['id'], 'reason': reason, 'attempts': len(history)})
        checkpoint = {'schema_version': 1, 'recorded_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                      'batch': batch, 'generation': summary,
                      'status': state, 'complete': not incomplete,
                      'incomplete_requests': incomplete, 'error': error,
                      'failure_categories': {category: sum(r.get('failure_category') == category for r in rows)
                                             for category in ('transport', 'content', 'credential-echo')},
                      'uncertain_attempts': sum(row['status'] == 'started' for row in rows),
                      'automatic_adoption': False, 'packaging_deferred': True,
                      'process_status': 'Check live process and receipts; this is a saved checkpoint.'}
        write_json(review / 'generation-progress.json', checkpoint)
        if progress is not None:
            progress(checkpoint)
        return checkpoint

    def recover():
        if (output / 'run.json').exists():
            rows = receipts()
            require(not any(r['status'] == 'started' or r.get('outcome_unknown') for r in rows),
                    'Inspect uncertain requests before resuming')
            if any(r['status'] == 'failed' and 'response_sha256' in r for r in rows):
                report = recover_saved(work / 'plan', CACHE / 'api.local.json', output)
                emit({'event': 'offline_recovery', **report})

    def generation_progress(event):
        emit(event)
        archive()

    with run_lock(work):
        # Only frozen generation inputs are checked. Independent review decisions may progress concurrently.
        emit({'event': 'batch_started', 'batch': batch, 'targets': plan['maximum_items'],
              'requests': len(jobs), 'caps': caps, 'max_attempts_per_request': 30, 'max_wait_seconds': 30})
        try:
            recover()
            archive()
            for job in jobs:
                require(not cancelled(), 'Batch stopped by marker')

                def history():
                    return [{**row, 'retryable': False} if row.get('failure_category') == 'content' else row
                            for row in receipts() if row['request_id'] == job['id']]

                def attempt():
                    try:
                        return generate(work / 'plan', CACHE / 'api.local.json', output, execute=True,
                                        **caps, retry_failed=True, request_ids=[job['id']], progress=generation_progress)
                    finally:
                        recover()
                        archive()

                ok = retry_request(attempt, history, max_retries=29,
                                   emit=lambda event: emit({'request_id': job['id'], **event}), cancelled=cancelled)
                emit({'event': 'request_finished', 'request_id': job['id'], 'success': ok})
                if not ok and history() and history()[-1].get('failure_scope') == 'provider':
                    raise ValueError('Provider configuration or authorization failure; batch stopped')
            state = 'completed' if {r['request_id'] for r in receipts() if r['status'] == 'completed'} == {
                j['id'] for j in jobs} else 'incomplete'
            report = archive()
            emit({'event': 'batch_completed' if state == 'completed' else 'batch_incomplete',
                  'incomplete_requests': report['incomplete_requests'],
                  'completed_requests': report['generation']['completed_requests'],
                  'planned_requests': len(jobs), 'attempts': report['generation']['attempts']})
            return report
        except Exception as failure:
            state, error = 'failed', {'type': type(failure).__name__, 'message': str(failure)}
            emit({'event': 'batch_failed', 'error': error})
            raise
        finally:
            archive()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch', help='Frozen batch directory name')
    raise SystemExit(0 if run(parser.parse_args().batch)['status'] == 'completed' else 2)
