"""Followup replay keeps ancestry and cannot bypass authored semantic review."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.lexicon_expand.common import Invalid, read_json, write_json
from tools.lexicon_expand.finalize import FINAL, repair_inputs
from tools.lexicon_expand.followups import apply_followups


@unittest.skipUnless(FINAL.is_dir(), 'Historical followup archive is not bundled')
class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.original, current = repair_inputs()
        self.base = {sid: result.get('superseded_result', result) for sid, result in current.items()}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manifest = Path(self.temp.name) / 'followup-plans.json'
        self.manifest.write_bytes((FINAL / 'followup-plans.json').read_bytes())

    def test_verified_followup_keeps_rejected_previous_candidate_and_pending_quality(self):
        generated = apply_followups(self.original, self.base, self.manifest)
        sid = 'sense-1608746921123f3876d2'
        self.assertIn('弧度', generated[sid]['superseded_result']['candidate']['meaning_zh'])
        self.assertNotIn('弧度', generated[sid]['candidate']['meaning_zh'])
        self.assertEqual(generated[sid]['candidate']['quality']['semantic_review'], 'pending')
        self.assertEqual(generated[sid]['generation']['kind'], 'external-api')

    def test_stale_superseded_candidate_hash_rejected(self):
        manifest = read_json(self.manifest)
        sid = next(iter(manifest['batches'][0]['supersedes']))
        manifest['batches'][0]['supersedes'][sid] = '0' * 64
        write_json(self.manifest, manifest)
        with self.assertRaisesRegex(Invalid, 'stale previous candidate'):
            apply_followups(self.original, self.base, self.manifest)

    def test_incomplete_followup_cannot_replace_a_reviewed_result(self):
        with patch('tools.lexicon_expand.followups.read_attempts', return_value=[]):
            with self.assertRaisesRegex(Invalid, 'finish completely'):
                apply_followups(self.original, self.base, self.manifest)


if __name__ == '__main__':
    unittest.main()
