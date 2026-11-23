"""Current review selection must follow frozen original and revision identities."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.lexicon_expand import current_integration as current
from tools.lexicon_expand.common import Invalid, digest, write_json, write_jsonl


class CurrentSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.object(current, 'ROOT', self.root).start()
        self.original = {'packet_id': 'old', 'target_id': 'target', 'candidate': {'chinese': '原稿'},
                         'candidate_sha256': 'old-sha', 'decision': {'decision': 'rejected'}}
        folder = self.root / 'base'
        write_json(folder / 'review-packet.json', {'items': [self.original]})
        write_jsonl(folder / 'reviewed-candidates.jsonl', [self.original])
        write_json(self.root / 'base.json', {'review_batches': [
            {'directory': 'base', 'packet_sha256': digest((folder / 'review-packet.json').read_bytes())}]})
        self.revision = {'packet_id': 'revision', 'target_id': 'target', 'candidate': {'chinese': '修订'},
                         'candidate_sha256': 'new-sha', 'decision': {'decision': 'accepted'}}
        write_jsonl(self.root / 'repair/reviewed-candidates.jsonl', [self.revision])
        self.override = {'original_packet_id': 'old', 'original_candidate_sha256': 'old-sha',
                         'selected_packet_id': 'revision', 'selected_candidate_sha256': 'new-sha', 'decision': 'accepted'}
        self.index = {'base_index': 'base.json', 'base_index_sha256': digest((self.root / 'base.json').read_bytes()),
                      'supplement': {'folder': 'repair', 'sense_overrides': 'overrides.json'},
                      'accepted_senses': 1, 'repair_senses': 0, 'deferred_senses': 0, 'reviewed_nonempty_senses': 1}

    def select(self):
        write_json(self.root / 'repair/overrides.json', {'items': [self.override]})
        write_json(self.root / 'current.json', self.index)
        return current.selected_view(self.root / 'current.json')

    def test_revision_replaces_original_without_increasing_count(self):
        rows = self.select()
        self.assertEqual(list(rows), ['old'])
        self.assertEqual(rows['old']['packet_id'], 'revision')
        self.assertEqual(self.original['decision']['decision'], 'rejected')

    def test_changed_base_index_is_rejected(self):
        self.index['base_index_sha256'] = 'stale'
        with self.assertRaisesRegex(Invalid, 'base index changed'):
            self.select()

    def test_stale_or_wrong_prior_revision_is_rejected(self):
        self.override['prior_packet_id'] = 'unselected-revision'
        with self.assertRaisesRegex(Invalid, 'currently selected'):
            self.select()

    def test_revision_cannot_change_target_or_claim_wrong_count(self):
        self.revision['target_id'] = 'another-target'
        write_jsonl(self.root / 'repair/reviewed-candidates.jsonl', [self.revision])
        with self.assertRaisesRegex(Invalid, 'target/decision mismatch'):
            self.select()
        self.revision['target_id'] = 'target'
        write_jsonl(self.root / 'repair/reviewed-candidates.jsonl', [self.revision])
        self.index['accepted_senses'] = 2
        with self.assertRaisesRegex(Invalid, 'does not reconcile'):
            self.select()


if __name__ == '__main__':
    unittest.main()
