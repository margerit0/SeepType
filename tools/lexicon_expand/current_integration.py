"""Resolve a hash-bound review index and integrate its selected accepted view.

Original reviews remain immutable. Local revisions keep their original candidate
hash and receive an ID only when exported as adopted records.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from tools.lexicon_expand.common import ROOT, canonical, digest, read_json, read_jsonl, require, write_json, write_jsonl
from tools.lexicon_expand.integration import EvidenceIndex, build
from tools.lexicon_expand.quality_v3 import require_pronunciation_review

REVIEWS = ROOT / 'data/lexicon-expansion/reviews'
CURRENT = REVIEWS / 'repair-16-codex-20261117/current-review-index.json'
BASELINE = REVIEWS / 'adopted-expansion-all-20261114'
OUTPUT = REVIEWS / 'adopted-expansion-8000-20261117'


def selected_view(index_path, *, files=None, folders=None):
    files = set() if files is None else files
    folders = set() if folders is None else folders
    index_path = Path(index_path)
    files.add(index_path)
    index = read_json(index_path)
    if 'base_index' in index:
        base = ROOT / index['base_index']
        require(digest(base.read_bytes()) == index['base_index_sha256'], 'Review base index changed')
        selected = selected_view(base, files=files, folders=folders)
    else:
        selected = {}
        for batch in index['review_batches']:
            folder = ROOT / batch['directory']
            require(digest((folder / 'review-packet.json').read_bytes()) == batch['packet_sha256'],
                    'Indexed review packet changed')
            add_folder(selected, folder, files, folders)
    for supplement in index.get('supplements', []):
        add_folder(selected, ROOT / supplement['folder'], files, folders)
    if 'supplement' in index:
        spec = index['supplement']
        folder = ROOT / spec['folder']
        if 'sense_overrides' in spec:
            files.add(folder / spec['sense_overrides'])
            folders.add(folder)
            revised = {r['packet_id']: r for r in read_jsonl(folder / 'reviewed-candidates.jsonl')}
            for override in read_json(folder / spec['sense_overrides'])['items']:
                old_id = override['original_packet_id']
                require(old_id in selected, 'Override original absent from selected view')
                old = selected[old_id]
                prior_id = override.get('prior_packet_id', old_id)
                require(old['packet_id'] == prior_id and old['candidate_sha256'] ==
                        override.get('prior_candidate_sha256', override['original_candidate_sha256']),
                        'Revision does not replace the currently selected candidate')
                new = revised[override['selected_packet_id']]
                require(new['candidate_sha256'] == override['selected_candidate_sha256'] and
                        new['target_id'] == old['target_id'] and new['decision']['decision'] == override['decision'],
                        'Override candidate/target/decision mismatch')
                selected[old_id] = {**new, '_source_path': (folder / 'reviewed-candidates.jsonl').relative_to(ROOT).as_posix()}
        else:
            # These supplements revisit empty results only; no accepted sense is
            # removed. Quarantined identities therefore never enter this view.
            add_folder(selected, folder / 'packet-01' if (folder / 'packet-01').exists() else folder, files, folders)
            files.add(folder / spec['target_overrides'])
    if 'accepted_senses' in index:
        counts = Counter(r['decision']['decision'] for r in selected.values())
        require(counts['accepted'] == index['accepted_senses'] and counts['rejected'] == index['repair_senses'] and
                counts['deferred'] == index['deferred_senses'] and len(selected) == index['reviewed_nonempty_senses'],
                'Selected view does not reconcile with review index: ' + str(index_path))
    return selected


def add_folder(selected, folder, files, folders):
    folders.add(folder)
    path = folder / 'reviewed-candidates.jsonl'
    files.add(path)
    for row in read_jsonl(path):
        if row.get('candidate') is None:
            continue
        require(row['packet_id'] not in selected, 'Repeated selected review identity')
        selected[row['packet_id']] = {**row, '_source_path': path.relative_to(ROOT).as_posix()}


class CurrentEvidence(EvidenceIndex):
    def bind_candidate(self, source, index_path, line):
        kind = source.get('generation', {}).get('kind')
        if not source['packet_id'].startswith('revision') and kind != 'assistant-authored-source-grounded':
            return super().bind_candidate(source, index_path, line)
        sense, decision, pid = source['candidate'], source['decision'], source['packet_id']
        require(digest(canonical(sense)) == source['candidate_sha256'] == decision['candidate_sha256'],
                'Local candidate/review hash mismatch')
        require(decision['decision'] == 'accepted' and decision['reason'].strip(), 'Local source not accepted')
        require(sense['quality']['disposition'] != 'blocked', 'Blocked local source')
        require_pronunciation_review(sense, decision)
        packets = [p for p in self.packets[pid] if p[2]['candidate'] == sense]
        decisions = [d for d in self.decisions[pid] if d[2] == decision]
        require(packets and decisions, 'Local review packet or decision absent')
        pp, pn, packet = self.preferred(packets)
        dp, dn, _ = self.preferred(decisions)
        links = {'selected_index': self.binding(index_path, line=line, row_sha256=digest(canonical(source))),
                 'review_packet': self.binding(pp, item_index=pn, packet_id=pid),
                 'semantic_decision': self.binding(dp, item_index=dn, decision_sha256=digest(canonical(decision)))}
        ancestry = []
        if pid.startswith('revision'):
            folder = str(Path(pp).parent).replace('\\', '/')
            draft_path = folder + '/revisions.jsonl'
            drafts = [(n, r) for n, r in enumerate(self.jsonl(draft_path), 1)
                      if digest(canonical(r.get('revision_fields', r.get('revised_candidate')))) == packet['revision_fields_sha256']
                      and r['target_id'] == source['target_id']]
            require(len(drafts) == 1, 'Local revision draft missing or ambiguous')
            n, draft = drafts[0]
            fields = draft.get('revision_fields', draft.get('revised_candidate'))
            require({k: sense[k] for k in fields} == fields, 'Local draft fields changed')
            links['authored_revision'] = self.binding(draft_path, line=n, row_sha256=digest(canonical(draft)))
            for key, sha_key in [('original_packet_id', 'original_candidate_sha256'), ('prior_packet_id', 'prior_candidate_sha256')]:
                if key not in source:
                    continue
                parents = [p for p in self.packets[source[key]] if p[2]['candidate_sha256'] == source[sha_key]]
                require(parents, 'Revision ancestry missing')
                ap, an, parent = self.preferred(parents)
                require(parent['target_id'] == source['target_id'], 'Revision changed original target')
                ancestry.append(self.binding(ap, item_index=an, packet_id=source[key], candidate_sha256=source[sha_key]))
        else:
            records = self.records[source['source_record_sha256']]
            require(records, 'Authored source record absent')
            rp, rn, record = self.preferred(records)
            require(sense in record['senses'] and record['generation'] == source['generation'], 'Authored source mismatch')
            links['original_draft'] = self.binding(rp, line=rn, record_sha256=source['source_record_sha256'])
            authored = str(Path(rp).parent / 'authored-drafts.json').replace('\\', '/')
            require(digest(self.raw(authored)) == source['generation']['authored_drafts_sha256'], 'Authored input bytes changed')
            links['authored_input'] = self.binding(authored)
        return {**source, '_integration': {'bindings': links, 'ancestry': ancestry, 'packs': source.get('packs', [])}}


def prepare(output=OUTPUT):
    output = Path(output)
    files, folders = set(), set()
    selected = selected_view(CURRENT, files=files, folders=folders)
    accepted = [r for r in selected.values() if r['decision']['decision'] == 'accepted']
    require(len(accepted) == 9739, 'Wrong authorized scope')
    for folder in folders:
        files.update(p for p in folder.iterdir() if p.is_file())
        preservation = folder / 'review-input-preservation.json'
        if preservation.exists():
            files.update(ROOT / name for name in read_json(preservation)['files'])
    files.update(p for p in BASELINE.iterdir() if p.is_file())
    # Freeze the current bytes, including original response archives named by
    # review preservation manifests, without changing earlier manifests.
    manifest = {'schema_version': 1, 'files': {p.relative_to(ROOT).as_posix():
                {'sha256': digest(p.read_bytes()), 'bytes': p.stat().st_size}
                for p in sorted(files) if p.exists()}}
    frozen = output / 'history/initial-input-manifest.json'
    if frozen.exists():
        require(read_json(frozen) == manifest, 'Integration inputs changed since freeze')
    else:
        write_json(frozen, manifest)
    selected_rows = [{k: v for k, v in r.items() if k != '_source_path'} for r in accepted]
    write_jsonl(output / 'selected-accepted-candidates.jsonl', selected_rows)
    # Source files and their exact line locations remain in a separate immutable
    # selection manifest; the new selection file is a derived view.
    write_json(output / 'selected-source-locations.json', {'items': [
        {'packet_id': r['packet_id'], 'path': r['_source_path']} for r in accepted]})
    plan = {'schema_version': 2, 'client_date': '2026-11-17',
            'baseline_directory': BASELINE.relative_to(ROOT).as_posix(),
            'baseline_records': 3401, 'baseline_sha256': digest((BASELINE / 'accepted-senses.jsonl').read_bytes()),
            'older_baseline_path': 'data/lexicon-expansion/reviews/adopted-expansion-b-20261110/accepted-senses.jsonl',
            'current_review_index': CURRENT.relative_to(ROOT).as_posix(),
            'current_review_index_sha256': digest(CURRENT.read_bytes()),
            'expected_unique_source_candidates': len(accepted), 'excluded_deferred_senses': 40,
            'excluded_quarantined_empty_targets': 4, 'generation_calls': 0}
    write_json(output / 'integration-plan.json', plan)
    print('Prepared selected accepted view:', len(accepted), 'frozen files:', len(manifest['files']), flush=True)


def load_current_sources(output):
    plan = read_json(output / 'integration-plan.json')
    require(digest((ROOT / plan['current_review_index']).read_bytes()) == plan['current_review_index_sha256'], 'Current index changed')
    evidence = CurrentEvidence(read_json(output / 'history/initial-input-manifest.json'))
    files, folders = set(), set()
    view = selected_view(ROOT / plan['current_review_index'], files=files, folders=folders)
    selected = [r for r in view.values() if r['decision']['decision'] == 'accepted']
    sources, counts = [], Counter()
    for selected_row in selected:
        source = {k: v for k, v in selected_row.items() if k != '_source_path'}
        path = selected_row['_source_path']
        # Packet order in the original per-review export is stable.
        if path not in evidence._raw_cache:
            evidence.raw(path)
        counts[path] += 1
        sources.append(source)
    by_path = defaultdict(dict)
    for path in counts:
        by_path[path] = {r['packet_id']: n for n, r in enumerate(evidence.jsonl(path), 1)}
    sources = [evidence.bind_candidate(source, row['_source_path'], by_path[row['_source_path']][source['packet_id']])
               for source, row in zip(sources, selected)]
    require(len(sources) == plan['expected_unique_source_candidates'], 'Selected source count changed')
    for path in sorted(files):
        evidence.raw(path.relative_to(ROOT).as_posix())
    return sources, [{'path': p, 'expected_records': n, 'unique_source_candidates': n,
                      'sha256': evidence.files[p]['sha256']} for p, n in counts.items()], evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=OUTPUT)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.snapshot)
    else:
        summary = build(args.snapshot, source_loader=load_current_sources)
        print({k: v for k, v in summary.items() if k != 'artifacts'})


if __name__ == '__main__':
    main()
