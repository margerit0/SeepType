"""Recover saved API responses offline, preserving original receipts and bytes."""
from tools.lexicon_expand import provider
from tools.lexicon_expand.common import CACHE, canonical, digest, generated_directory, read_json, require
from tools.lexicon_expand.storage import write_json
from tools.lexicon_expand.generation import now, read_attempts, run_lock, write_summary
from tools.lexicon_expand.normalization import ResponseValidationError, parse_reply
from tools.lexicon_expand.planning import load_plan


def recover_saved(plan_directory, config_path, output):
    plan, jobs = load_plan(plan_directory)
    config = provider.load_config(config_path)
    output = generated_directory(output)
    identity = digest(canonical({'plan': plan, 'provider': config}))
    recovered, rejected = [], []
    with run_lock(output):
        require(read_json(output / 'run.json')['identity'] == identity, 'Recovery configuration changed')
        attempts = read_attempts(output, jobs, identity)
        require(not any(a['status'] == 'started' or a.get('outcome_unknown') for a in attempts),
                'Inspect uncertain requests before offline recovery')
        done = {a['request_id'] for a in attempts if a['status'] == 'completed'}
        expected = {j['id']: j for j in jobs}
        for attempt in reversed(attempts):
            if attempt['status'] != 'failed' or attempt['request_id'] in done or 'response_sha256' not in attempt:
                continue
            sequence = attempt['sequence']
            raw = (output / 'responses' / f'{sequence:05d}.json').read_bytes()
            require(digest(raw) == attempt['response_sha256'], 'Saved provider response changed')
            try:
                content, _, model = provider.decode_response(raw)
                job = expected[attempt['request_id']]
                generation = {'kind': 'external-api', 'endpoint': config['endpoint'],
                              'requested_model': config['model'], 'reported_model': model,
                              'request_id': job['id'], 'request_sha256': job['request_sha256'],
                              'prompt_sha256': plan['prompt_sha256'], 'response_sha256': digest(raw),
                              'received_at': attempt['finished_at']}
                records, generation = parse_reply(content, job, generation)
            except (ValueError, TypeError, KeyError) as error:
                rejected.append({'sequence': sequence, 'request_id': attempt['request_id'],
                                 'validation_error': error.detail if isinstance(error, ResponseValidationError) else {
                                     'code': 'provider-envelope', 'path': '$', 'message': 'Invalid provider response envelope'}})
                continue
            receipt_path = output / 'attempts' / f'{sequence:05d}.json'
            recovery = {'version': 1, 'identity': identity, 'request_id': attempt['request_id'],
                        'sequence': sequence, 'receipt_sha256': digest(receipt_path.read_bytes()),
                        'response_sha256': digest(raw), 'recovered_at': now(),
                        'generation': generation, 'records': records}
            write_json(output / 'recoveries' / receipt_path.name, recovery)
            done.add(attempt['request_id'])
            recovered.append({'sequence': sequence, 'request_id': attempt['request_id'], 'items': len(records),
                              'changes': generation.get('normalization', {}).get('changes', [])})
        write_summary(output, plan, read_attempts(output, jobs, identity))
    return {'model': config['model'], 'recovered': recovered, 'rejected': rejected, 'model_requests': 0}


def recover_parallel():
    output = CACHE / 'pilot-results-combined'
    with run_lock(output):
        report = {'recorded_at': now(), 'model_requests': 0, 'providers': [
            recover_saved(CACHE / 'pilot', CACHE / config, CACHE / directory)
            for config, directory in [('api.local.json', 'pilot-results-v1'),
                                      ('api.grok.local.json', 'pilot-results-grok')]]}
        write_json(output / 'recovery-report.json', report)
        return report


if __name__ == '__main__':
    import json
    print(json.dumps(recover_parallel(), ensure_ascii=False, indent=2))
