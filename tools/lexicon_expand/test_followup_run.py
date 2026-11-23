from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.lexicon_expand import followup_run as followup
from tools.lexicon_expand.common import Invalid, canonical, digest, read_json, write_json
from tools.lexicon_expand.generation import run_lock


class FollowupTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for name, value in (('ROOT', root), ('CACHE', root / '.cache')):
            p = patch.object(followup, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.current = datetime(2026, 11, 10, 10, tzinfo=timezone.utc)
        self.config = {'queue': 'queue', 'predecessor': 'before', 'successor': 'after',
                       'created_at': self.current.isoformat(),
                       'expires_at': (self.current + timedelta(hours=6)).isoformat(),
                       'poll_seconds': 1, 'frozen_inputs': {}}
        plan = {'maximum_items': 1}
        for name in ('before', 'after'):
            meta = {'plan_sha256': digest(canonical(plan))}
            write_json(root / '.cache' / name / 'batch-plan.json', meta)
        for folder in (root / '.cache/queue', root / 'data/lexicon-expansion/reviews/queue'):
            write_json(folder / 'queue.json', self.config)
        p = patch.object(followup, 'load_plan', return_value=(plan, []))
        p.start()
        self.addCleanup(p.stop)
        return root

    def test_waiting_does_not_prepare_credentials_or_start_successor(self):
        root = self.fixture()
        credentials = Mock()
        def stop(_):
            write_json(root / '.cache/queue/stop.json', {})
        with patch.object(followup, 'predecessor_status', return_value={'status': 'waiting-predecessor'}), \
             patch.object(followup, 'run_batch') as run:
            result = followup.run('queue', prepare_credentials=credentials, sleep=stop, now=lambda: self.current)
        credentials.assert_not_called()
        run.assert_not_called()
        self.assertEqual(result['status'], 'stopped-before-successor')

    def test_ready_predecessor_starts_once_and_completed_queue_is_reused(self):
        self.fixture()
        order = []
        generation = {'completed_requests': 3, 'planned_requests': 3, 'uncertain_attempts': 0}
        with patch.object(followup, 'predecessor_status', side_effect=lambda _: order.append('verified') or {'status': 'ready'}), \
             patch.object(followup, 'run_batch', side_effect=lambda _, **kw: order.append('generation') or {'generation': generation}) as run:
            result = followup.run('queue', prepare_credentials=lambda: order.append('credentials'), now=lambda: self.current)
            followup.run('queue', now=lambda: self.current)
        self.assertEqual(order, ['verified', 'credentials', 'generation'])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args, ('after',))
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['semantic_review'], 'pending')

    def test_successor_progress_is_visible_and_incomplete_result_stays_incomplete(self):
        root = self.fixture()
        generation = {'completed_requests': 1, 'planned_requests': 3}
        def running(_, *, progress):
            progress({'generation': generation, 'status': 'running', 'uncertain_attempts': 0})
            state = read_json(root / '.cache/queue/state.json')
            self.assertEqual(state['status'], 'running-successor')
            self.assertEqual(state['successor_generation']['completed_requests'], 1)
            return {'generation': generation, 'complete': False}
        with patch.object(followup, 'predecessor_status', return_value={'status': 'ready'}), \
             patch.object(followup, 'run_batch', side_effect=running):
            result = followup.run('queue', now=lambda: self.current)
        self.assertEqual(result['status'], 'successor-incomplete')

    def test_incomplete_predecessor_and_expiry_never_start_successor(self):
        self.fixture()
        with patch.object(followup, 'predecessor_status', return_value={'status': 'predecessor-incomplete'}), \
             patch.object(followup, 'run_batch') as run:
            result = followup.run('queue', now=lambda: self.current)
            expired = followup.run('queue', now=lambda: self.current + timedelta(hours=7))
        run.assert_not_called()
        self.assertEqual(result['status'], 'predecessor-incomplete')
        self.assertEqual(expired['status'], 'expired-before-successor')

    def test_changed_frozen_input_blocks_before_credentials(self):
        root = self.fixture()
        path = root / 'evidence.json'
        write_json(path, {'original': True})
        self.config['frozen_inputs'] = {'evidence.json': digest(path.read_bytes())}
        for folder in (root / '.cache/queue', root / 'data/lexicon-expansion/reviews/queue'):
            write_json(folder / 'queue.json', self.config)
        write_json(path, {'changed': True})
        credentials = Mock()
        with self.assertRaisesRegex(Invalid, 'Frozen queue input changed'):
            followup.run('queue', prepare_credentials=credentials)
        credentials.assert_not_called()

    def test_active_producer_lock_is_waiting_and_does_not_inspect_receipts(self):
        root = self.fixture()
        with run_lock(root / '.cache/before'), patch.object(followup, 'read_attempts') as receipts:
            result = followup.predecessor_status('before')
        receipts.assert_not_called()
        self.assertEqual(result['status'], 'waiting-predecessor')

    def test_complete_receipts_need_all_targets_and_no_unknown_outcomes(self):
        plan = {'maximum_items': 2}
        jobs = [{'id': 'request', 'payload': {'targets': [{'target_id': 'one'}, {'target_id': 'two'}]}}]
        self.assertIsNone(followup.complete_records(plan, jobs, []))
        with self.assertRaisesRegex(Invalid, 'uncertain'):
            followup.complete_records(plan, jobs, [{'status': 'started'}])
        rows = [{'status': 'completed', 'request_id': 'request', 'records': [{'id': 'one'}]}]
        with self.assertRaisesRegex(Invalid, 'coverage'):
            followup.complete_records(plan, jobs, rows)
        rows[0]['records'].append({'id': 'two'})
        self.assertEqual(len(followup.complete_records(plan, jobs, rows)), 2)

    def test_duplicate_queue_copies_and_path_escape_are_rejected(self):
        root = self.fixture()
        write_json(root / 'data/lexicon-expansion/reviews/queue/queue.json', {'changed': True})
        with self.assertRaisesRegex(Invalid, 'copies differ'):
            followup.validate_queue('queue')
        for name in ('..', '../escape', 'a/b', 'a\\b'):
            with self.assertRaises(Invalid):
                followup.validate_queue(name)
