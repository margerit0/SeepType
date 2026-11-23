"""Build a separate development data snapshot from explicit adoption routes.

No provider calls, semantic verdicts, Rime builds, or packages are produced.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone

from tools.lexicon import pipeline as legacy
from tools.lexicon_expand.common import (
    ROOT, canonical, digest, read_json, read_jsonl, require, write_json, write_jsonl,
)
from tools.lexicon_expand.quality_v3 import require_pronunciation_review
from tools.lexicon_expand.review_pilot import dictionary_readings
from tools.lexicon_expand.runtime import choices_from_tsv, compile_model, trigger_additions

REVIEWS = ROOT / 'data/lexicon-expansion/reviews'
OUTPUT = REVIEWS / 'adopted-expansion-20261110'


def identity(sense):
    return tuple(sense[k] for k in ('chinese', 'pinyin', 'commit_english', 'pos'))


def resolve(baseline, candidates, routes):
    """Validate authored routes; identical spelling alone cannot merge meanings."""
    require(len({r['id'] for r in baseline}) == len(baseline), 'Duplicate baseline ID')
    by_source = {r['packet_id']: r for r in candidates}
    require(len(by_source) == len(candidates), 'Duplicate source candidate')
    require(len(routes) == len(by_source) and
            {r['packet_id'] for r in routes} == set(by_source), 'Incomplete adoption routes')
    by_baseline = {r['id']: r for r in baseline}
    selected, provenance = {}, defaultdict(list)
    for route in routes:
        source = by_source[route['packet_id']]
        sense = source['candidate']
        require(source['decision']['decision'] == 'accepted', 'Unaccepted adoption source')
        require(route['candidate_sha256'] == source['decision']['candidate_sha256'] == digest(canonical(sense)),
                'Stale adoption candidate hash')
        require(route['reason'].strip(), 'Authored adoption reason required')
        action, destination = route['action'], route['destination']
        require(action in ('adopt', 'merge-reviewed-version', 'already-in-baseline'), 'Unknown adoption action')
        if action == 'already-in-baseline':
            require(destination in by_baseline and identity(sense) == identity(by_baseline[destination]),
                    'Baseline duplicate differs in trigger, English, or part of speech')
        else:
            require(destination in by_source, 'Missing selected source')
            chosen = by_source[destination]
            require(chosen['decision']['decision'] == 'accepted' and identity(sense) == identity(chosen['candidate']),
                    'Merged version differs in trigger, English, or part of speech')
            if action == 'adopt':
                require(destination == route['packet_id'], 'Adopt must select its own original content')
                selected[destination] = chosen
            else:
                require(destination != route['packet_id'], 'Merge must name another selected source')
        provenance[destination].append({**route, 'generation': source['generation'],
                                       'source_record_sha256': source['source_record_sha256'],
                                       'semantic_review': source['decision']})
    require(all(r['destination'] in selected or r['action'] == 'already-in-baseline' for r in routes),
            'Merged destination was not adopted')
    added = []
    for pid, source in sorted(selected.items()):
        sense = source['candidate']
        require(sense['id'] not in by_baseline, 'Adopted sense ID collides with baseline')
        added.append({**sense, 'verdict': 'accepted', 'english': source['english'],
                      'target_id': source['target_id'], 'packs': source['packs'],
                      'reason': source['decision']['reason'], 'reviewer': 'Codex',
                      'method': 'user-delegated-agent-semantic-review',
                      'adoption_packet_id': pid, 'provenance': provenance[pid],
                      'human_approved': False, 'release_ready': False})
    require(len({r['id'] for r in added}) == len(added), 'Selected source sense IDs collide')
    return baseline + added, dict(provenance)


def load_candidates(names=('generation-v3-20261109', 'expansion-104-20261110')):
    candidates = []
    for name in names:
        folder = REVIEWS / name
        packet = read_json(folder / 'review-packet.json')['items']
        decisions = read_json(folder / 'evaluation-decisions.json')
        require(decisions['packet_sha256'] == digest((folder / 'review-packet.json').read_bytes()),
                'Review packet hash changed')
        verdicts = {r['packet_id']: r for r in decisions['items']}
        require(len(verdicts) == len(packet) and set(verdicts) == {p['packet_id'] for p in packet},
                'Semantic review is incomplete')
        originals = {}
        paths = list((folder / 'external').glob('*-results/drafts.jsonl'))
        if not paths:
            paths = [folder / 'external/results/drafts.jsonl']
        for path in paths:
            profile = path.parent.name.removesuffix('-results')
            for record in read_jsonl(path):
                for sense in record['senses'] or [None]:
                    key = [profile, record['id'], sense] if name.startswith('generation-v3') else [record['id'], sense]
                    pid = 'candidate-' + digest(canonical(key))[:24]
                    originals[pid] = (record, sense)
        require(set(originals) == set(verdicts), 'Review differs from archived generation evidence')
        for p in packet:
            pid = p['packet_id']
            record, sense = originals[pid]
            decision = verdicts[pid]
            require(sense == p['candidate'] and
                    decision['candidate_sha256'] == p['candidate_sha256'] == digest(canonical(sense)),
                    'Semantic review no longer matches original candidate')
            if decision['decision'] != 'accepted':
                continue
            require_pronunciation_review(sense, decision)
            candidates.append({**p, 'decision': decision, 'generation': record['generation'],
                               'target_id': record['id'], 'packs': record['packs'],
                               'review_batch': name, 'source_record_sha256': digest(canonical(record))})
    return candidates


def build(output=None, *, baseline_folder=None, review_names=None):
    output = output or OUTPUT
    baseline_folder = baseline_folder or REVIEWS / 'next-100-20261109'
    manifest = read_json(output / 'adoption-decisions.json')
    for path, sha in manifest['frozen_inputs'].items():
        require(digest((ROOT / path).read_bytes()) == sha, 'Frozen adoption input changed: ' + path)
    baseline_path = baseline_folder / 'accepted-senses.jsonl'
    baseline = read_jsonl(baseline_path)
    candidates = load_candidates() if review_names is None else load_candidates(review_names)
    accepted, provenance = resolve(baseline, candidates, manifest['items'])
    choices = choices_from_tsv(output / 'primary-choices.tsv')
    model = compile_model(accepted, choices, legacy.validate().entries)
    readings, _, _, _ = dictionary_readings()
    additions = trigger_additions(accepted, readings)
    old_additions = read_jsonl(baseline_folder / 'trigger-additions.jsonl')
    old_keys = {(r['chinese'], r['code']) for r in old_additions}
    new_additions = [r for r in additions if (r['chinese'], r['code']) not in old_keys]
    new = accepted[len(baseline):]
    # Preserve the complete original baseline byte prefix as well as its records.
    legacy.atomic_write(output / 'accepted-senses.jsonl', baseline_path.read_bytes() +
                        b''.join(canonical(row) + b'\n' for row in new))
    write_jsonl(output / 'new-accepted-senses.jsonl', new)
    write_jsonl(output / 'trigger-additions.jsonl', additions)
    write_jsonl(output / 'new-trigger-additions.jsonl', new_additions)
    write_json(output / 'adoption-provenance.json', provenance)
    write_json(output / 'runtime-model.json', model)
    summary = {'schema_version': 1, 'recorded_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'status': 'reviewed-development-data-snapshot', 'baseline_senses_preserved': len(baseline),
               'reviewed_source_candidates': len(candidates),
               'adoption_routes': dict(Counter(r['action'] for r in manifest['items'])),
               'new_accepted_senses': len(new), 'accepted_senses': len(accepted),
               'total_supplemental_readings': len(additions), 'new_supplemental_readings': len(new_additions),
               'explicit_common_sense_choices': len(choices), 'runtime_data_compiles': True,
               'native_runtime_regression_performed': False, 'packaging_deferred': True,
               'human_approved': False, 'release_ready': False,
               'frozen_inputs_verified': len(manifest['frozen_inputs']),
               'artifacts': {n: digest((output / n).read_bytes()) for n in
                             ('adoption-decisions.json', 'primary-choices.tsv', 'accepted-senses.jsonl',
                              'new-accepted-senses.jsonl', 'adoption-provenance.json',
                              'trigger-additions.jsonl', 'new-trigger-additions.jsonl', 'runtime-model.json')}}
    write_json(output / 'summary.json', summary)
    write_json(ROOT / 'experiments/lexicon-expansion/results' / (output.name + '.json'), summary)
    return summary


if __name__ == '__main__':
    import json
    print(json.dumps(build(), ensure_ascii=False, indent=2))
