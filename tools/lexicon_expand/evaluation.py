"""Prepare held-out, same-target comparisons; never score semantic quality by lookup."""
from pathlib import Path

from tools.lexicon_expand.catalog import load_prepared
from tools.lexicon_expand.common import CACHE, ROOT, canonical, digest, generated_directory, read_json, require, write_json
from tools.lexicon_expand.planning import PROMPTS, make_job, save_plan
from tools.lexicon_expand.quality import check_sense, policy, reading_index
from tools.lexicon_expand.review_pilot import BATCH, source_inputs


PROMPT_EXAMPLES = {'may', 'refund', 'menu'}


def make_comparison(output=CACHE / 'comparison-v2-final', *, review_batch=BATCH, prepared=CACHE / 'prepared'):
    records, decisions, _ = source_inputs(Path(review_batch))
    catalog, _, catalog_manifest = load_prepared(prepared)
    by_id = {t['id']: t for t in catalog}
    candidates = [(r, d) for r, d in zip(records, decisions) if r['english'] not in PROMPT_EXAMPLES]
    index = reading_index()
    blocked = [pair for pair in candidates if any(
        check_sense(s, {}, index)['disposition'] == 'blocked' for s in pair[0]['senses'])]
    chosen = {r['id'] for r, _ in blocked}
    case = [(r, d) for r, d in candidates if r['id'] not in chosen and set(d['decisions']) != {'P'}
            and any(any(f['code'] == 'source-case-unconfirmed'
                        for f in check_sense(s, by_id.get(r['id'], {}), index)['findings'])
                    for s in r['senses'])][:5]
    chosen.update(r['id'] for r, _ in case)
    other_bad = [(r, d) for r, d in candidates if r['id'] not in chosen and set(d['decisions']) != {'P'}]
    control = [(r, d) for r, d in candidates if set(d['decisions']) == {'P'}]
    other_count = 20 - len(blocked) - len(case)
    sample = blocked + case + other_bad[:other_count] + control[:20]
    require(len(sample) == 40, 'Expected 40 comparison targets')
    targets = [{
        'target_id': r['id'], 'english': r['english'], 'packs': r['packs'],
        'source_forms': by_id.get(r['id'], {}).get('source_forms', []),
        'source_refs': r['source_refs'],
        'dictionary_references': by_id.get(r['id'], r)['dictionary_references'],
    } for r, _ in sample]
    output = generated_directory(output)
    manifests = {}
    for prompt_version in (1, 2):
        prompt_path = PROMPTS[prompt_version]
        prompt = prompt_path.read_text(encoding='utf-8')
        version = 2 if prompt_version == 1 else 3
        jobs = [make_job('map_targets', targets[start:start + 5], prompt, response_version=version)
                for start in range(0, len(targets), 5)]
        plan = {'schema_version': version, 'status': 'offline-plan-not-executed',
                'word_targets': 40, 'scene_slots': 0, 'maximum_items': 40,
                'maximum_senses_per_item': 3, 'request_count': 8, 'batch_size': 5,
                'prompt_sha256': digest(prompt_path.read_bytes()) if version == 2 else digest(prompt.encode('utf-8')),
                'prepared_directory': str(Path(prepared).resolve()),
                'catalog_manifest_sha256': digest(canonical(catalog_manifest))}
        if version == 3:
            plan.update(prompt_version=2, response_schema_version=3, quality_policy=policy())
        manifests[str(prompt_version)] = save_plan(output / f'v{prompt_version}', plan, jobs, targets, prompt)
    manifest = {'schema_version': 1, 'items_per_version': 40, 'requests_per_version': 8,
                'target_ids': [t['target_id'] for t in targets],
                'sample_groups': {'known_pinyin_problems': len(blocked), 'case_problems': len(case),
                                  'other_review_problems': other_count, 'accepted_controls': 20},
                'excluded_prompt_examples': sorted(PROMPT_EXAMPLES),
                'source_drafts_sha256': digest((Path(review_batch) / 'source-drafts.jsonl').read_bytes()),
                'plans_sha256': {k: digest(canonical(v)) for k, v in manifests.items()},
                'real_api_calls': 0, 'measured_quality_improvement': None,
                'evaluation_rules': [
                    'Use identical provider/model/parameters and separate outputs for each version.',
                    'This compares the full v1/v2 generation format and prompt, not prompt wording alone.',
                    'Compare complete-target coverage, blocked pronunciation, case flags and token usage.',
                    'Review meaning and usability independently; dictionary matches are not semantic approval.',
                    'Count unresolved outputs as coverage loss; fewer senses alone is not a quality win.',
                    'The 40 items are held out from prompt examples, not an unseen external test set.',
                ]}
    if (output / 'comparison.json').exists():
        require(read_json(output / 'comparison.json') == manifest, 'Comparison manifest changed')
    write_json(output / 'comparison.json', manifest)
    return manifest
