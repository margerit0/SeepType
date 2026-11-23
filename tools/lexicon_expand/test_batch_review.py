from copy import deepcopy
import unittest

from tools.lexicon_expand.batch_review import validate_decisions
from tools.lexicon_expand.common import Invalid, canonical, digest


class BatchReviewTests(unittest.TestCase):
    def fixture(self, flags=()):
        sense = {'pos': 'n', 'meaning_zh': '独立测试义项',
                 'quality': {'disposition': 'review-required' if flags else 'checks-passed',
                             'findings': [{'code': f} for f in flags]}}
        item = {'packet_id': 'candidate', 'candidate': sense, 'candidate_sha256': digest(canonical(sense))}
        decision = {'packet_id': 'candidate', 'candidate_sha256': item['candidate_sha256'],
                    'decision': 'accepted', 'reason': '明确逐项语义决定', 'evidence_ids': []}
        return item, decision

    def test_complete_review_accepts_without_rewriting_original(self):
        p, d = self.fixture()
        original = deepcopy(p)
        self.assertEqual(validate_decisions([p], [d], set())['candidate'], d)
        self.assertEqual(p, original)

    def test_missing_duplicate_stale_and_unknown_evidence_are_rejected(self):
        p, d = self.fixture()
        for rows in ([], [d, d], [{**d, 'candidate_sha256': 'stale'}], [{**d, 'evidence_ids': ['invented']}]):
            with self.assertRaises(Invalid):
                validate_decisions([p], rows, set())

    def test_case_flag_requires_explicit_confirmation_and_evidence(self):
        p, d = self.fixture(('source-case-unconfirmed',))
        with self.assertRaisesRegex(Invalid, 'case evidence'):
            validate_decisions([p], [d], set())
        d['case_review'] = {'confirmed': True, 'reason': '专名范围已确认', 'evidence': '出版者词典条目'}
        validate_decisions([p], [d], set())

    def test_phrase_reading_flag_cannot_be_implicitly_approved(self):
        p, d = self.fixture(('phrase-reading-unconfirmed',))
        with self.assertRaisesRegex(Invalid, 'pronunciation review'):
            validate_decisions([p], [d], set())
        d['pronunciation_review'] = {'confirmed': True, 'reason': '整词组件与语境一致', 'evidence': '固定来源及语境记录'}
        validate_decisions([p], [d], set())

    def test_repair_requires_resolved_original_intent_and_same_pos(self):
        p, d = self.fixture()
        p['repair_context'] = {'original_sense': {'pos': 'n'}}
        with self.assertRaisesRegex(Invalid, 'original intent'):
            validate_decisions([p], [d], set())
        d['original_issue_resolved'] = True
        validate_decisions([p], [d], set())
        p['repair_context']['original_sense']['pos'] = 'v'
        with self.assertRaisesRegex(Invalid, 'original intent'):
            validate_decisions([p], [d], set())

    def test_empty_result_is_unresolved_and_never_accepted(self):
        p, d = self.fixture()
        p.update(candidate=None, candidate_sha256=digest(canonical(None)))
        d['candidate_sha256'] = p['candidate_sha256']
        with self.assertRaisesRegex(Invalid, 'Empty result'):
            validate_decisions([p], [d], set())
        d['decision'] = 'unresolved'
        validate_decisions([p], [d], set())
