"""Public main must contain an independently checkable Windows development snapshot."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.lexicon_expand.common import Invalid, ROOT
from tools.lexicon_expand.windows_snapshot import RUNTIME, SCHEMAS, SHARED, load_snapshot


class WindowsSnapshotTests(unittest.TestCase):
    def test_pinned_snapshot_rebuilds_lua_and_covers_all_schemes(self):
        snapshot = load_snapshot()
        details = (ROOT / SHARED / 'word-details.jsonl').read_bytes().splitlines()
        self.assertEqual(set(snapshot.model['entries']), {json.loads(row)['chinese'] for row in details})
        self.assertEqual(len(details), snapshot.metadata['englishTriggerReadings'])
        self.assertGreaterEqual(snapshot.metadata['windowsEngineChecks'], len(details) * len(SCHEMAS))
        self.assertTrue(snapshot.cases)
        self.assertFalse(snapshot.metadata['releaseReady'])

    def test_unpaired_shared_snapshot_is_rejected(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for path in (RUNTIME, SHARED):
                (root / path).mkdir(parents=True)
            (root / RUNTIME / 'snapshot.json').write_bytes((ROOT / RUNTIME / 'snapshot.json').read_bytes())
            (root / SHARED / 'snapshot.json').write_bytes(b'{}')
            with self.assertRaisesRegex(Invalid, 'hash mismatch'):
                load_snapshot(root)
