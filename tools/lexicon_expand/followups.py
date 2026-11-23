"""Replay explicitly selected external followups without losing prior repairs."""
from __future__ import annotations

from tools.lexicon_expand.common import CACHE, ROOT, canonical, digest, generated_directory, read_json, require
from tools.lexicon_expand.generation import read_attempts
from tools.lexicon_expand.planning import load_plan
from tools.lexicon_expand.repair_trial import unchanged_file


def apply_followups(original, generated, manifest_path):
    if not manifest_path.exists():
        return generated
    manifest = read_json(manifest_path)
    require(manifest['schema_version'] == 1, 'Unknown followup manifest version')
    generated = dict(generated)
    original_provider = read_json(CACHE / 'repair-remaining-40-results-20261109/run.json')['provider']
    for item in manifest['batches']:
        plan_directory = generated_directory(ROOT / item['plan_directory'])
        results_directory = generated_directory(ROOT / item['results_directory'])
        plan, jobs = load_plan(plan_directory)
        run = read_json(results_directory / 'run.json')
        require(all(run['provider'][k] == original_provider[k] for k in ('endpoint', 'model')),
                'Followup changed the authorized endpoint or model')
        require(run['identity'] == digest(canonical({'plan': plan, 'provider': run['provider']})),
                'Followup run identity changed')
        attempts = read_attempts(results_directory, jobs, run['identity'])
        completed = [a for a in attempts if a['status'] == 'completed']
        require(len(completed) == len(jobs) and len({a['request_id'] for a in completed}) == len(jobs),
                'Followup must finish completely before it can supersede a repair')
        require(not any(a['status'] == 'started' for a in attempts), 'Followup has an uncertain request')
        records = [r for a in completed for r in a['records']]
        require(len(records) == len(item['supersedes']), 'Followup replacement coverage differs')
        replaced = set()
        for record in records:
            sid = record['repair_of']['sense_id']
            require(sid in original and sid in generated and sid not in replaced, 'Unknown or duplicate followup ancestry')
            require(record['repair_of']['target_id'] == original[sid]['target_id'], 'Followup target ancestry differs')
            require(item['supersedes'].get(sid) == digest(canonical(generated[sid]['candidate'])),
                    'Followup refers to a stale previous candidate')
            require(record['review']['status'] == 'pending' and not record['release_ready'],
                    'External followup cannot approve itself')
            require(len(record['senses']) <= 1, 'Followup must repair only one original sense')
            previous = generated[sid]
            generated[sid] = {'candidate': record['senses'][0] if record['senses'] else None,
                              'generation': record['generation'], 'unresolved_reason': record['unresolved_reason'],
                              'superseded_result': previous, 'followup_plan_sha256': digest(canonical(plan))}
            replaced.add(sid)
        require(replaced == set(item['supersedes']), 'Followup replacement identity differs')
        archive = (manifest_path.parent / 'followups' / plan_directory.name).resolve()
        require(archive.is_relative_to(manifest_path.parent.resolve()), 'Followup archive escapes review directory')
        for folder, directory, names in (
                ('plan', plan_directory, ('plan.json', 'requests.jsonl', 'selected-targets.jsonl', 'prompt.txt')),
                ('results', results_directory, ('run.json', 'summary.json', 'drafts.jsonl', 'quality-issues.jsonl'))):
            for name in names:
                unchanged_file(archive / folder / name, (directory / name).read_bytes())
        for folder in ('attempts', 'responses'):
            for path in sorted((results_directory / folder).glob('*.json')):
                unchanged_file(archive / 'results' / folder / path.name, path.read_bytes())
    return generated
