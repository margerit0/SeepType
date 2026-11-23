from copy import deepcopy
import unittest

from tools.lexicon_expand.common import Invalid, canonical, digest
from tools.lexicon_expand.repair_followup import select_repairs


class RepairFollowupTests(unittest.TestCase):
    def fixture(self):
        sense = {'id': 'sense', 'chinese': '分析', 'pos': 'n'}
        record = {'id': 'target', 'english': 'analysis', 'senses': [sense]}
        sha = digest(canonical(sense))
        item = {'packet_id': 'candidate', 'target_id': 'target', 'candidate': sense,
                'candidate_sha256': sha, 'source_record_sha256': digest(canonical(record)),
                'decision': {'decision': 'rejected', 'candidate_sha256': sha, 'reason': '过程结果混写'}}
        route = {'packet_id': 'candidate', 'candidate_sha256': sha, 'action': 'repair',
                 'reason': '明确返修', 'focus': '只保留过程', 'category': 'sense-boundary'}
        return [record], [item], [route], {'target': {'english': 'analysis'}}, []

    def test_only_rejected_sense_is_selected_and_ancestry_is_retained(self):
        args = self.fixture()
        original = deepcopy(args)
        selected, held = select_repairs(*args)
        self.assertEqual(args, original)
        self.assertEqual(len(selected), 1)
        self.assertEqual(held, [])
        self.assertEqual(selected[0]['original_target_id'], 'target')
        self.assertEqual(selected[0]['original_sense'], args[0][0]['senses'][0])
        self.assertNotEqual(selected[0]['target_id'], 'target')

    def test_uncertain_reading_is_held_without_generation_target(self):
        args = self.fixture()
        args[2][0]['action'] = 'hold-for-evidence'
        selected, held = select_repairs(*args)
        self.assertEqual(selected, [])
        self.assertEqual(len(held), 1)

    def test_incomplete_routes_stale_hash_and_already_accepted_are_rejected(self):
        for variation in ('missing', 'stale', 'accepted'):
            args = self.fixture()
            if variation == 'missing':
                args[2].clear()
            elif variation == 'stale':
                args[2][0]['candidate_sha256'] = 'wrong'
            else:
                args[4].append({'id': 'sense'})
            with self.assertRaises(Invalid):
                select_repairs(*args)
