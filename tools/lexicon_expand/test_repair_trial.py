"""Trial boundary checks: selection, user review gate, and original preservation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.lexicon_expand.common import CACHE, Invalid, canonical, digest, read_json, read_jsonl, write_json
from tools.lexicon_expand.generation import generate
from tools.lexicon_expand.repair_trial import (
    SELECTION, prepare_trial, render_trial, select_trial, unchanged_file, validate_pending,
)
from tools.lexicon_expand.review_pilot import BATCH, verify_protected


@unittest.skipUnless(BATCH.is_dir(), 'Historical repair-trial inputs are not bundled')
class RepairTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.targets = read_jsonl(CACHE / 'repair-v2/selected-targets.jsonl')
        cls.revisions = read_jsonl(BATCH / 'revision-requests.jsonl')

    def pending_fixture(self):
        targets, _ = select_trial(self.targets, self.revisions)
        records = [{'id': t['target_id'], 'repair_of': {
            'target_id': t['original_target_id'], 'sense_id': t['original_sense']['id'],
            'source_record_sha256': t['source_record_sha256']},
            'senses': [], 'review': {'status': 'pending'}, 'selected_sense_id': None,
            'release_ready': False, 'generation': {'kind': 'external-api'}} for t in targets]
        return targets, records

    def test_exact_ten_revision_senses_cover_four_categories_and_exclude_535_others(self):
        selected, slots = select_trial(self.targets, self.revisions)
        self.assertEqual(len(selected), 10)
        self.assertEqual(len(set(t['target_id'] for t in selected)), 10)
        self.assertEqual({s['category'] for s in slots}, {'拼音', '大小写', '词义', '搭配'})
        self.assertEqual({(s['row'], s['sense_number']) for s in slots},
                         {(r, s) for r, s, _ in SELECTION})
        excluded = read_jsonl(BATCH / 'accepted-senses.jsonl') + [
            r for r in read_jsonl(BATCH / 'issues.jsonl') if r['verdict'] == 'rejected']
        self.assertEqual(len(excluded), 535)
        self.assertFalse({t['original_sense']['id'] for t in selected} & {r['id'] for r in excluded})

    def test_omitted_or_nonrevision_slot_rejected(self):
        with self.assertRaises(Invalid):
            select_trial(self.targets, self.revisions[:-1])
        altered = copy.deepcopy(self.revisions)
        next(r for r in altered if r['row'] == 226)['verdict'] = 'accepted'
        with self.assertRaises(Invalid):
            select_trial(self.targets, altered)

    def test_incomplete_duplicate_or_substituted_results_rejected(self):
        targets, records = self.pending_fixture()
        self.assertEqual(len(validate_pending(records, targets)), 10)
        for bad in (records[:-1], records[:-1] + records[:1],
                    [dict(records[0], id='foreign')] + records[1:]):
            with self.assertRaises(Invalid):
                validate_pending(bad, targets)

    def test_external_response_cannot_mark_itself_approved_or_rewrite_ancestry(self):
        targets, records = self.pending_fixture()
        for mutation in ({'review': {'status': 'accepted'}}, {'release_ready': True},
                         {'selected_sense_id': 'invented'}, {'generation': {'kind': 'test-only'}},
                         {'repair_of': {}}, {'senses': [{}, {}]}):
            bad = copy.deepcopy(records)
            bad[0].update(mutation)
            with self.assertRaises(Invalid):
                validate_pending(bad, targets)

    def test_all_488_historical_protected_files_unchanged(self):
        self.assertEqual(verify_protected(read_json(BATCH / 'provenance.json')), 488)

    def test_original_evidence_and_existing_review_files_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'evidence.json'
            unchanged_file(path, b'original')
            unchanged_file(path, b'original')
            with self.assertRaises(Invalid):
                unchanged_file(path, b'changed')
            self.assertEqual(path.read_bytes(), b'original')

    def test_verified_response_archive_and_report_keep_every_candidate_pending(self):
        def complete(config, key, job):
            results = []
            for target in job['payload']['targets']:
                original = target['original_sense']
                # Replay originals, including their errors; no test-created vocabulary.
                sense = {k: original[k] for k in ('chinese', 'pinyin', 'pos', 'meaning_zh', 'source_ref_ids')}
                sense['english'] = original['commit_english']
                unresolved = target['english'] == 'consist'
                results.append({'target_id': target['target_id'], 'english': target['english'],
                                'senses': [] if unresolved else [sense],
                                'unresolved_reason': '仅测试：保留未解决状态' if unresolved else None})
            return canonical({'model': 'TEST-ONLY', 'choices': [{'finish_reason': 'stop',
                'message': {'content': json.dumps({'results': results}, ensure_ascii=False)}}],
                'usage': {'prompt_tokens': 3, 'completion_tokens': 4, 'total_tokens': 7}})

        (CACHE / 'tests').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=CACHE / 'tests') as directory:
            root = Path(directory)
            plan, results, review = root / 'plan', root / 'results', root / 'review'
            prepare_trial(plan, review)
            config = root / 'test.config.json'
            write_json(config, {'base_url': 'https://test.invalid', 'model': 'TEST-ONLY'})
            with patch('tools.lexicon_expand.provider.read_key', return_value='test-credential'), \
                    patch('tools.lexicon_expand.provider.complete', side_effect=complete):
                generate(plan, config, results, execute=True, max_items=10, max_requests=2)
            summary = render_trial(plan, results, review)
            self.assertEqual(summary['returned_candidates'], 9)
            self.assertEqual(summary['unresolved_senses'], 1)
            self.assertEqual(summary['user_approved_senses'], 0)
            self.assertEqual(summary['newly_adopted_senses'], 0)
            self.assertEqual(summary['preserved_accepted_senses'], 504)
            self.assertEqual(summary['excluded_rejected_senses'], 31)
            self.assertEqual(len(read_jsonl(review / 'remaining-revision-requests.jsonl')), 40)
            self.assertTrue(all(r['review']['status'] == 'pending-user-review' and not r['adopted']
                                for r in read_jsonl(review / 'revisions.jsonl')))
            response = results / 'responses/00001.json'
            archived = review / 'external/results/responses/00001.json'
            self.assertEqual(response.read_bytes(), archived.read_bytes())
            self.assertEqual(render_trial(plan, results, review), summary)
            response.write_bytes(b'{}')
            with self.assertRaises(Invalid):
                render_trial(plan, results, review)


if __name__ == '__main__':
    unittest.main()
