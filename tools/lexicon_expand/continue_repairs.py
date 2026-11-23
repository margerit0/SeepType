"""Continue the forty unattempted repairs without rewriting the ten-item trial."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.lexicon_expand.common import CACHE, ROOT, Invalid, canonical, digest, read_json, read_jsonl, require, write_json
from tools.lexicon_expand.generation import generate, read_attempts
from tools.lexicon_expand.planning import load_plan, make_job, save_plan
from tools.lexicon_expand.repair_trial import REVIEW, unchanged_file
from tools.lexicon_expand.retry import retry_request
from tools.lexicon_expand.review_pilot import BATCH, verify_protected

PLAN = CACHE / 'repair-remaining-40-20261109'
RESULTS = CACHE / 'repair-remaining-40-results-20261109'
REVIEW40 = ROOT / 'data/lexicon-expansion/reviews/repair-remaining-40-20261109'


def prepare():
    base, _ = load_plan(CACHE / 'repair-v2')
    targets = read_jsonl(CACHE / 'repair-v2/selected-targets.jsonl')
    remaining = read_jsonl(REVIEW / 'remaining-revision-requests.jsonl')
    wanted = {r['id'] for r in remaining}
    selected = [t for t in targets if t['original_sense']['id'] in wanted]
    require(len(selected) == len(wanted) == 40, 'Expected forty remaining repair identities')
    trial_ids = {r['original_sense_id'] for r in read_jsonl(REVIEW / 'revisions.jsonl')}
    require(not wanted & trial_ids, 'Do not resend completed trial requests')
    prompt = (CACHE / 'repair-v2/prompt.txt').read_text(encoding='utf-8')
    jobs = [make_job('repair_senses', selected[i:i + 5], prompt, response_version=3,
                     quality_policy=base['quality_policy']) for i in range(0, 40, 5)]
    plan = {k: v for k, v in base.items() if k != 'files'}
    plan.update(maximum_items=40, request_count=8,
                continuation_of='repair-trial-10-20261109',
                review_authorization='用户：委托你复审并继续后续任务',
                automatic_adoption=False)
    save_plan(PLAN, plan, jobs, selected, prompt)
    protected = {e['path']: e['sha256'] for e in read_json(REVIEW / 'provenance.json')['protected_inputs']}
    for directory in (REVIEW, BATCH):
        for path in directory.rglob('*'):
            if path.is_file():
                protected[path.relative_to(ROOT).as_posix()] = digest(path.read_bytes())
    provenance = {'schema_version': 1,
                  'authorization': '用户：委托你复审并继续后续任务',
                  'method': 'user-delegated-agent-semantic-review',
                  'protected_inputs': [{'path': p, 'sha256': sha} for p, sha in sorted(protected.items())],
                  'planned_senses': 40, 'original_accepted_senses': 504,
                  'original_rejected_senses': 31}
    unchanged_file(REVIEW40 / 'provenance.json',
                   (json.dumps(provenance, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    return {'planned_senses': 40, 'requests': 8,
            'protected_inputs_verified': verify_protected(provenance), 'model_requests': 0}


def run():
    plan, jobs = load_plan(PLAN)
    def emit(event):
        print(json.dumps(event, ensure_ascii=False), flush=True)
    def history(job):
        if not (RESULTS / 'run.json').exists():
            return []
        run = read_json(RESULTS / 'run.json')
        rows = [a for a in read_attempts(RESULTS, jobs, run['identity']) if a['request_id'] == job['id']]
        # A transport retry can succeed unchanged. A content failure needs a
        # reviewed new request, never an identical automatic content retry.
        return [{**a, 'retryable': False} if a.get('failure_category') == 'content' else a for a in rows]
    for job in jobs:
        if (RESULTS / 'stop.json').exists():
            emit({'event': 'stopped', 'reason': 'stop marker; completed requests preserved'})
            break
        try:
            ok = retry_request(
                lambda: generate(PLAN, CACHE / 'api.local.json', RESULTS, execute=True,
                    max_items=40, max_requests=60, max_output_budget=245760,
                    retry_failed=True, request_ids=[job['id']], progress=emit),
                lambda: history(job), max_retries=15, emit=emit,
                cancelled=lambda: (RESULTS / 'stop.json').exists())
        except Invalid:
            if not (RESULTS / 'stop.json').exists():
                raise
            emit({'event': 'stopped', 'reason': 'stop marker; receipt preserved'})
            break
        emit({'event': 'request_finished', 'request_id': job['id'], 'success': ok})
    return archive()


def archive():
    plan, jobs = load_plan(PLAN)
    run = read_json(RESULTS / 'run.json')
    require(run['identity'] == digest(canonical({'plan': plan, 'provider': run['provider']})),
            'Run identity changed')
    attempts = read_attempts(RESULTS, jobs, run['identity'])
    completed = [a for a in attempts if a['status'] == 'completed']
    require(len(completed) == len({a['request_id'] for a in completed}), 'Duplicate completion')
    records = sorted([r for a in completed for r in a['records']], key=lambda r: r['id'])
    require(records == read_jsonl(RESULTS / 'drafts.jsonl'), 'Drafts differ from external evidence')
    for directory, names in ((PLAN, ['plan.json', 'requests.jsonl', 'selected-targets.jsonl', 'prompt.txt']),
                              (RESULTS, ['run.json', 'summary.json', 'drafts.jsonl', 'quality-issues.jsonl'])):
        for name in names:
            prefix = 'plan' if directory == PLAN else 'results'
            destination = REVIEW40 / 'external' / prefix / name
            raw = (directory / name).read_bytes()
            if name in {'summary.json', 'drafts.jsonl', 'quality-issues.jsonl'} and destination.exists() and destination.read_bytes() != raw:
                old = destination.read_bytes()
                unchanged_file(REVIEW40 / 'external/results/progress-snapshots' / (digest(old) + '-' + name), old)
                from tools.lexicon_expand.storage import atomic_write
                atomic_write(destination, raw)
            else:
                unchanged_file(destination, raw)
    for folder in ('attempts', 'responses'):
        for path in sorted((RESULTS / folder).glob('*.json')):
            unchanged_file(REVIEW40 / 'external/results' / folder / path.name, path.read_bytes())
    result = {**read_json(RESULTS / 'summary.json'),
              'protected_inputs_verified': verify_protected(read_json(REVIEW40 / 'provenance.json'))}
    write_json(REVIEW40 / 'generation-summary.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'generate', 'archive'])
    args = parser.parse_args()
    print(json.dumps({'plan': prepare, 'generate': run, 'archive': archive}[args.command](),
                     ensure_ascii=False, indent=2))
