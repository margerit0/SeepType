"""Run one bounded follow-up only after its predecessor has completed safely."""
from datetime import datetime, timezone
import time

from tools.lexicon_expand.batch_run import run as run_batch
from tools.lexicon_expand.common import (
    CACHE, ROOT, Invalid, canonical, digest, read_json, read_jsonl, require, write_json,
)
from tools.lexicon_expand.generation import read_attempts, run_lock
from tools.lexicon_expand.planning import load_plan
from tools.lexicon_expand.recover import recover_saved


def complete_records(plan, jobs, attempts):
    require(not any(a['status'] == 'started' or a.get('outcome_unknown') for a in attempts),
            'Predecessor has an uncertain provider outcome')
    completed = [a for a in attempts if a['status'] == 'completed']
    require(len({a['request_id'] for a in completed}) == len(completed), 'Repeated completed request')
    if {a['request_id'] for a in completed} != {j['id'] for j in jobs}:
        return None
    records = sorted([r for a in completed for r in a['records']], key=lambda r: r['id'])
    expected = {t['target_id'] for j in jobs for t in j['payload']['targets']}
    require(len(records) == len(expected) == plan['maximum_items'] and
            {r['id'] for r in records} == expected, 'Predecessor returned unexpected target coverage')
    return records


def predecessor_status(batch):
    """An active producer is waiting, never permission to start another caller."""
    work = CACHE / batch
    plan, jobs = load_plan(work / 'plan')
    output = work / 'results'
    try:
        with run_lock(work):
            require(not (work / 'stop.json').exists() and not (output / 'stop.json').exists(),
                    'Predecessor has a stop marker')
            if not (output / 'run.json').exists():
                return {'status': 'predecessor-incomplete', 'completed_requests': 0}
            recover_saved(work / 'plan', CACHE / 'api.local.json', output)
            return verified_predecessor(plan, jobs, output)
    except Invalid as error:
        if str(error) == 'Another process is using this generation directory':
            return {'status': 'waiting-predecessor'}
        raise


def verified_predecessor(plan, jobs, output):
    with run_lock(output):
        run = read_json(output / 'run.json')
        identity = digest(canonical({'plan': plan, 'provider': run['provider']}))
        require(run['identity'] == identity, 'Predecessor run identity changed')
        attempts = read_attempts(output, jobs, identity)
        records = complete_records(plan, jobs, attempts)
        count = sum(a['status'] == 'completed' for a in attempts)
        if records is None:
            return {'status': 'predecessor-incomplete', 'completed_requests': count}
        require(read_jsonl(output / 'drafts.jsonl') == records,
                'Predecessor drafts differ from verified responses')
        return {'status': 'ready', 'completed_requests': count, 'returned_targets': len(records),
                'attempts': len(attempts)}


def validate_queue(queue_name):
    import re
    require(isinstance(queue_name, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', queue_name),
            'Use one queue directory name')
    work = CACHE / queue_name
    review = ROOT / 'data/lexicon-expansion/reviews' / queue_name
    raw = (work / 'queue.json').read_bytes()
    require(raw == (review / 'queue.json').read_bytes(), 'Frozen queue copies differ')
    config = read_json(work / 'queue.json')
    require(config['queue'] == queue_name and config['predecessor'] != config['successor'], 'Invalid queue identity')
    for name in (config['predecessor'], config['successor']):
        require(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', name), 'Invalid queued batch name')
    require(1 <= config['poll_seconds'] <= 30, 'Invalid queue polling interval')
    start = datetime.fromisoformat(config['created_at'])
    end = datetime.fromisoformat(config['expires_at'])
    require(start.tzinfo is not None and end.tzinfo is not None and
            0 < (end - start).total_seconds() <= 6 * 3600, 'Queue must expire within six hours')
    for path, sha in config['frozen_inputs'].items():
        target = (ROOT / path).resolve()
        require(target.is_relative_to(ROOT) and digest(target.read_bytes()) == sha, 'Frozen queue input changed')
    for name in (config['predecessor'], config['successor']):
        plan, _ = load_plan(CACHE / name / 'plan')
        meta = read_json(CACHE / name / 'batch-plan.json')
        require(meta['plan_sha256'] == digest(canonical(plan)), 'Queued batch plan changed')
    return config


def run(queue_name, *, prepare_credentials=None, sleep=time.sleep, now=None):
    """Credential preparation occurs only after verified predecessor completion."""
    now = now or (lambda: datetime.now(timezone.utc))
    config = validate_queue(queue_name)
    work = CACHE / queue_name
    review = ROOT / 'data/lexicon-expansion/reviews' / queue_name

    def save(status, **details):
        state = {'schema_version': 1, 'recorded_at': now().isoformat(timespec='seconds'),
                 'queue': queue_name, 'predecessor': config['predecessor'], 'successor': config['successor'],
                 'status': status, 'automatic_adoption': False, 'packaging_deferred': True, **details}
        write_json(work / 'state.json', state)
        write_json(review / 'queue-state.json', state)
        return state

    with run_lock(work):
        if (work / 'state.json').exists():
            previous = read_json(work / 'state.json')
            if previous['status'] == 'completed':
                return previous
        try:
            while True:
                if (work / 'stop.json').exists() or (CACHE / config['successor'] / 'stop.json').exists():
                    return save('stopped-before-successor')
                if now() >= datetime.fromisoformat(config['expires_at']):
                    return save('expired-before-successor')
                predecessor = predecessor_status(config['predecessor'])
                if predecessor['status'] == 'waiting-predecessor':
                    save('waiting-predecessor', predecessor_check=predecessor,
                         successor_model_requests_started=0, credentials_prepared=False)
                    sleep(config['poll_seconds'])
                    continue
                if predecessor['status'] != 'ready':
                    return save('predecessor-incomplete', predecessor_check=predecessor,
                                successor_model_requests_started=0, credentials_prepared=False)
                validate_queue(queue_name)
                save('starting-successor', predecessor_check=predecessor)
                if prepare_credentials is not None:
                    prepare_credentials()
                def batch_progress(checkpoint):
                    save('running-successor', predecessor_check=predecessor,
                         successor_generation=checkpoint['generation'],
                         successor_status=checkpoint['status'],
                         uncertain_attempts=checkpoint['uncertain_attempts'])

                result = run_batch(config['successor'], progress=batch_progress)
                generation = result['generation']
                complete = (generation['completed_requests'] == generation['planned_requests'] and
                            generation.get('uncertain_attempts', 0) == 0 and
                            generation.get('unconfirmed_provider_outcomes', 0) == 0 and
                            result.get('uncertain_attempts', 0) == 0 and result.get('complete', True))
                return save('completed' if complete else 'successor-incomplete', successor_generation=generation,
                            predecessor_check=predecessor, semantic_review='pending')
        except Exception as error:
            save('failed', error_type=type(error).__name__, error=str(error))
            raise
