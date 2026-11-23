"""A partial repair run cannot manufacture completion or semantic approval."""
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.lexicon_expand import finalize as module
from tools.lexicon_expand.common import Invalid


@unittest.skipUnless(module.FINAL.is_dir(), 'Historical repair archive is not bundled')
class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.author = Path(self.temp.name) / 'authored'
        self.author.mkdir()
        for name in ('provenance.json', 'repair-decisions.tsv', 'primary-choices.tsv'):
            (self.author / name).write_bytes((module.FINAL / name).read_bytes())
        self.original, generated = module.repair_inputs(require_complete=False)
        with (self.author / 'repair-decisions.tsv').open(encoding='utf-8', newline='') as stream:
            authored_ids = {row['original_sense_id'] for row in csv.DictReader(stream, delimiter='\t')}
        self.generated = {sid: generated[sid] for sid in authored_ids}

    def mutate(self, change):
        path = self.author / 'repair-decisions.tsv'
        with path.open(encoding='utf-8', newline='') as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        rows = change(rows)
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['original_sense_id', 'candidate_sha256', 'decision', 'reason'],
                                    delimiter='\t', lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)

    def run_snapshot(self):
        output = Path(self.temp.name) / 'output'
        with patch.object(module, 'FINAL', self.author), patch.object(module, 'SNAPSHOT', output), \
                patch.object(module, 'repair_inputs', return_value=(self.original, self.generated)):
            return module.finalize(snapshot=True)

    def test_full_completion_blocked_while_twenty_requests_missing(self):
        read = module.read_jsonl
        def partial(path):
            rows = read(path)
            return rows[:1] if path == module.REVIEW40 / 'external/results/drafts.jsonl' else rows
        with patch.object(module, 'archive'), patch.object(module, 'read_jsonl', side_effect=partial):
            with self.assertRaisesRegex(Invalid, 'All fifty repairs'):
                module.repair_inputs(require_complete=True)

    def test_stale_candidate_hash_cannot_pass(self):
        def change(rows):
            rows[0]['candidate_sha256'] = '0' * 64
            return rows
        self.mutate(change)
        with self.assertRaisesRegex(Invalid, 'Stale repair decision'):
            self.run_snapshot()

    def test_missing_authored_decision_cannot_silently_pass(self):
        self.mutate(lambda rows: rows[:-1])
        with self.assertRaisesRegex(Invalid, 'authored decision'):
            self.run_snapshot()

    def test_unresolved_external_result_cannot_be_accepted(self):
        def change(rows):
            next(r for r in rows if r['original_sense_id'] == 'sense-7ae8f2b363dc205d7156')['decision'] = 'accepted'
            return rows
        self.mutate(change)
        with self.assertRaisesRegex(Invalid, 'unresolved external result'):
            self.run_snapshot()


if __name__ == '__main__':
    unittest.main()
