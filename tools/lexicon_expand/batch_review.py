"""Bind separately authored reviews to complete frozen single-arm generations."""
from collections import Counter
from datetime import datetime, timezone
import json
import re

from tools.lexicon_expand.common import (
    CACHE, ROOT, canonical, digest, read_json, read_jsonl, require, write_json, write_jsonl,
)
from tools.lexicon_expand.generation import read_attempts
from tools.lexicon_expand.planning import load_plan
from tools.lexicon_expand.quality_v3 import require_pronunciation_review
from tools.lexicon_expand.repair_trial import unchanged_file

BASELINE = ROOT / 'data/lexicon-expansion/reviews/adopted-expansion-20261110/accepted-senses.jsonl'


def folder_for(batch):
    require(isinstance(batch, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', batch), 'Invalid review batch')
    return ROOT / 'data/lexicon-expansion/reviews' / batch


def prepare_packet(batch, *, baseline_path=None):
    baseline_path = BASELINE if baseline_path is None else baseline_path
    folder = folder_for(batch)
    plan, jobs = load_plan(CACHE / batch / 'plan')
    output = CACHE / batch / 'results'
    run = read_json(output / 'run.json')
    require(run['identity'] == digest(canonical({'plan': plan, 'provider': run['provider']})), 'Generation identity changed')
    attempts = read_attempts(output, jobs, run['identity'])
    complete = [a for a in attempts if a['status'] == 'completed']
    require(len(complete) == len({a['request_id'] for a in complete}) == len(jobs) and
            not any(a['status'] == 'started' or a.get('outcome_unknown') for a in attempts), 'Generation is incomplete')
    records = sorted([r for a in complete for r in a['records']], key=lambda r: r['id'])
    require(records == read_jsonl(folder / 'external/results/drafts.jsonl') == read_jsonl(output / 'drafts.jsonl'),
            'Archived drafts differ from original responses')
    targets = {t['target_id']: t for j in jobs for t in j['payload']['targets']}
    require(len(records) == plan['maximum_items'] and {r['id'] for r in records} == set(targets), 'Incomplete target coverage')
    guard_path = folder / 'review-input-preservation.json'
    if not guard_path.exists():
        paths = [p for p in folder.rglob('*') if p.is_file()] + [baseline_path]
        write_json(guard_path, {'schema_version': 1, 'baseline_senses': len(read_jsonl(baseline_path)),
                               'files': {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in paths}})
    require(baseline_path.relative_to(ROOT).as_posix() in read_json(guard_path)['files'],
            'Review baseline differs from frozen inputs')
    packet = []
    for record in sorted(records, key=lambda r: r['english'].casefold()):
        require(record['review']['status'] == 'pending' and not record['release_ready'], 'Original drafts must remain pending')
        for sense in record['senses'] or [None]:
            row = {'packet_id': 'candidate-' + digest(canonical([record['id'], sense]))[:24],
                   'target_id': record['id'], 'english': record['english'], 'candidate': sense,
                   'candidate_sha256': digest(canonical(sense)), 'source_record_sha256': digest(canonical(record)),
                   'generation': record['generation'], 'unresolved_reason': record['unresolved_reason']}
            if 'repair_of' in record:
                target = targets[record['id']]
                row['repair_of'] = record['repair_of']
                row['repair_context'] = {k: target[k] for k in ('original_sense', 'repair_category', 'repair_focus', 'review_reason')}
            packet.append(row)
    raw = json.dumps({'schema_version': 1, 'items': packet}, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    unchanged_file(folder / 'review-packet.json', raw)
    return packet


def validate_decisions(packet, decisions, evidence_ids):
    by_id = {d['packet_id']: d for d in decisions}
    require(len(by_id) == len(decisions) == len(packet) and set(by_id) == {p['packet_id'] for p in packet},
            'Each candidate requires one authored review decision')
    for p in packet:
        decision = by_id[p['packet_id']]
        require(decision['candidate_sha256'] == p['candidate_sha256'] == digest(canonical(p['candidate'])) and
                decision['reason'].strip(), 'Stale or unexplained review decision')
        require(decision['decision'] in ('accepted', 'rejected', 'deferred', 'unresolved'), 'Unknown review verdict')
        require(set(decision.get('evidence_ids', [])) <= evidence_ids, 'Unknown review evidence')
        sense = p['candidate']
        if sense is None:
            require(decision['decision'] == 'unresolved', 'Empty result cannot be accepted')
            continue
        require(decision['decision'] != 'unresolved', 'A returned sense requires a semantic verdict')
        if decision['decision'] != 'accepted':
            continue
        require(sense['quality']['disposition'] != 'blocked', 'Blocked candidate cannot be accepted')
        require_pronunciation_review(sense, decision)
        flags = {f['code'] for f in sense['quality']['findings']}
        if 'source-case-unconfirmed' in flags:
            case = decision.get('case_review', {})
            require(case.get('confirmed') is True and case.get('reason', '').strip() and
                    case.get('evidence', '').strip(), 'Explicit case evidence required')
        if 'repair_context' in p:
            require(sense['pos'] == p['repair_context']['original_sense']['pos'] and
                    decision.get('original_issue_resolved') is True, 'Repair must resolve the original intent')
    return by_id


def finalize(batch, *, baseline_path=None):
    folder = folder_for(batch)
    packet = prepare_packet(batch, baseline_path=baseline_path)
    meta = read_json(folder / 'evaluation-decisions.json')
    require(meta['method'] == 'user-delegated-agent-semantic-review' and meta['reviewer'] == 'Codex' and
            meta['packet_sha256'] == digest((folder / 'review-packet.json').read_bytes()), 'Authored review identity changed')
    evidence = read_json(folder / 'review-evidence.json')
    evidence_ids = {s['id'] for s in evidence['sources']}
    decisions = validate_decisions(packet, meta['items'], evidence_ids)
    preservation = read_json(folder / 'review-input-preservation.json')
    guard = preservation['files']
    changed = [p for p, sha in guard.items() if digest((ROOT / p).read_bytes()) != sha]
    require(not changed, 'Original review input changed')
    reviewed = [{**p, 'decision': decisions[p['packet_id']], 'adopted': False} for p in packet]
    accepted = [p for p in reviewed if p['decision']['decision'] == 'accepted']
    repair = [p for p in reviewed if p['decision']['decision'] in ('rejected', 'deferred')]
    write_jsonl(folder / 'reviewed-candidates.jsonl', reviewed)
    write_jsonl(folder / 'accepted-candidates.jsonl', accepted)
    write_json(folder / 'post-review-repair-queue.json', {'schema_version': 1, 'status': 'reviewed-not-regenerated', 'items': repair})
    summary = {'schema_version': 1, 'batch': batch, 'reviewed_at': meta['reviewed_at'],
               'finalized_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'method': meta['method'], 'reviewed_items': len(packet),
               'returned_targets': len({p['target_id'] for p in packet}),
               'accepted_targets': len({p['target_id'] for p in accepted}),
               'verdicts': dict(Counter(d['decision'] for d in meta['items'])),
               'pronunciation_confirmations': sum('pronunciation_review' in d for d in meta['items']),
               'case_confirmations': sum(d.get('case_review', {}).get('confirmed') is True for d in meta['items']),
               'preserved_input_files': len(guard), 'unexpected_input_changes': changed,
               'baseline_development_senses': preservation['baseline_senses'], 'adopted_senses_this_review': 0,
               'human_approved': False, 'release_ready': False, 'model_requests': 0, 'packaging_performed': False}
    write_json(folder / 'review-summary.json', summary)
    labels = {'accepted': '通过', 'rejected': '返修', 'deferred': '暂缓', 'unresolved': '未解决'}
    lines = ['# 逐项复审：' + batch, '', '方式：用户委派代理语义复审；不是人工发行批准。', '',
             f"共{len(packet)}项；判定{summary['verdicts']}；有通过义项的目标{summary['accepted_targets']}/{summary['returned_targets']}。", '',
             f"原稿、收据、已采用{preservation['baseline_senses']}条开发记录均保持。通过候选另存，当前未采用、未打包。", '',
             '| 序号 | 英文/词性 | 中文/拼音 | 原说明 | 决定 | 理由 |', '|---:|---|---|---|---|---|']
    for i, p in enumerate(packet, 1):
        s, d = p['candidate'], decisions[p['packet_id']]
        lines.append('| ' + ' | '.join((str(i), s['commit_english'] + '/' + s['pos'] if s else p['english'],
                                      s['chinese'] + '/' + s['pinyin'] if s else '空结果',
                                      s['meaning_zh'] if s else p['unresolved_reason'], labels[d['decision']], d['reason'])) + ' |')
    lines += ['', '## 证据', '', '网页仅作短转述；固定词典组件、行号和摘要见review-evidence.json。', '']
    for source in evidence['sources']:
        lines.append('- ' + source['id'] + '：' + source['finding'])
    (folder / 'review.md').write_bytes(('\n'.join(lines) + '\n').encode('utf-8'))
    write_json(ROOT / 'experiments/lexicon-expansion/results' / (batch + '-semantic-review.json'),
               {**summary, 'artifact_sha256': {name: digest((folder / name).read_bytes()) for name in
                 ('review-packet.json', 'evaluation-decisions.json', 'review-evidence.json', 'review-summary.json',
                  'reviewed-candidates.jsonl', 'accepted-candidates.jsonl', 'post-review-repair-queue.json', 'review.md')}})
    return summary
