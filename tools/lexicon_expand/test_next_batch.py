"""Review gates prevent stale, incomplete, blocked or unresolved adoption."""
from copy import deepcopy
import unittest

from tools.lexicon_expand.common import Invalid, canonical, digest, read_jsonl, word_key
from tools.lexicon_expand.next_batch import BASE, PLAN, REVIEW, attempt_limit_policy, reviewed_senses
from tools.lexicon_expand.review_pilot import verify_protected


class NextBatchTests(unittest.TestCase):
    def test_raised_attempt_budget_preserves_history_and_excludes_completed_requests(self):
        jobs = [{'id': 'completed'}, {'id': 'exhausted'}, {'id': 'pending'}]
        attempts = [{'request_id': 'completed', 'status': 'failed', 'reserved_output_tokens': 4096}] * 2
        attempts += [{'request_id': 'completed', 'status': 'completed', 'reserved_output_tokens': 4096}]
        attempts += [{'request_id': 'exhausted', 'status': 'failed', 'reserved_output_tokens': 4096}] * 16
        policy = attempt_limit_policy(jobs, attempts, 30, 4096)
        self.assertEqual(19, policy['historical_attempts'])
        self.assertEqual(44, policy['remaining_attempt_slots'])
        self.assertEqual(63, policy['generation_caps']['max_requests'])
        self.assertEqual(63 * 4096, policy['generation_caps']['max_output_budget'])
        attempts += [{'request_id': 'pending', 'status': 'started', 'reserved_output_tokens': 4096}]
        with self.assertRaisesRegex(Invalid, 'uncertain'):
            attempt_limit_policy(jobs, attempts, 30, 4096)

    def setUp(self):
        sense = {'id': 'test-sense', 'chinese': '吸收', 'pinyin': 'xi1 shou1',
                 'commit_english': 'absorb', 'meaning_zh': '测试用例',
                 'quality': {'disposition': 'checks-passed', 'base_reading_present': True}}
        self.record = {'id': 'test-record', 'english': 'absorb', 'packs': ['test'], 'senses': [sense],
                       'generation': {'kind': 'test'}, 'review': {'status': 'pending'}, 'release_ready': False}
        self.decision = {'target_id': self.record['id'], 'sense_id': sense['id'],
                         'candidate_sha256': digest(canonical(sense)),
                         'decision': 'accepted', 'reason': 'Explicit test review; no product data written.'}

    def check_review(self, decisions=None, baseline=()):
        return reviewed_senses([self.record], [self.decision] if decisions is None else decisions,
                               baseline, '2026-11-09T00:00:00+00:00')

    def test_stale_sense_cannot_be_adopted(self):
        self.record['senses'][0]['meaning_zh'] += '改变'
        with self.assertRaisesRegex(Invalid, 'Stale candidate'):
            self.check_review()

    def test_missing_or_repeated_decision_rejected(self):
        for decisions in ([], [self.decision, self.decision]):
            with self.assertRaisesRegex(Invalid, 'exactly one'):
                self.check_review(decisions)

    def test_blocked_pronunciation_cannot_be_adopted(self):
        self.record['senses'][0]['quality']['disposition'] = 'blocked'
        self.decision['candidate_sha256'] = digest(canonical(self.record['senses'][0]))
        with self.assertRaisesRegex(Invalid, 'Blocked sense'):
            self.check_review()

    def test_unresolved_cannot_be_adopted(self):
        self.record['senses'] = []
        self.decision.update(sense_id='-', candidate_sha256=digest(canonical(None)))
        with self.assertRaisesRegex(Invalid, 'Unresolved result'):
            self.check_review()

    def test_duplicate_requires_archive_decision(self):
        with self.assertRaisesRegex(Invalid, 'Duplicate accepted'):
            self.check_review(baseline=self.record['senses'])
        self.decision['decision'] = 'duplicate'
        accepted, rows = self.check_review(baseline=self.record['senses'])
        self.assertEqual([], accepted)
        self.assertEqual('duplicate', rows[0]['decision'])

    def test_acceptance_preserves_exact_model_sense_and_pending_record(self):
        original = deepcopy(self.record)
        accepted, reviewed = self.check_review()
        self.assertEqual(original, self.record)
        for key, value in original['senses'][0].items():
            self.assertEqual(value, accepted[0][key])
        self.assertFalse(reviewed[0]['human_approved'])

    def test_locked_plan_contains_one_hundred_unseen_targets(self):
        if not (PLAN / 'plan.json').exists():
            self.skipTest('Next batch not prepared in this checkout')
        from tools.lexicon_expand.common import read_json
        from tools.lexicon_expand.planning import load_plan
        plan, jobs = load_plan(PLAN)
        targets = read_jsonl(PLAN / 'selected-targets.jsonl')
        excluded = set(read_json(REVIEW / 'provenance.json')['excluded_english'])
        self.assertEqual(100, len({word_key(t['english']) for t in targets}))
        self.assertTrue(all(word_key(t['english']) not in excluded for t in targets))
        self.assertEqual(100, sum(j['units'] for j in jobs))
        self.assertEqual(20, len(jobs))
        self.assertEqual(544, len(read_jsonl(BASE / 'accepted-senses.jsonl')))
        self.assertGreater(verify_protected(read_json(REVIEW / 'provenance.json')), 100)


if __name__ == '__main__':
    unittest.main()
