import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.lexicon_expand import batch_run as batch
from tools.lexicon_expand.common import Invalid, canonical, digest, write_json


class BatchRunTests(unittest.TestCase):
    def fixture(self, statuses=()):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        work = root / '.cache/lexicon-expansion/example'
        review = root / 'data/lexicon-expansion/reviews/example'
        plan = {'maximum_items': 5}
        config = {'max_output_tokens': 4096}
        jobs = [{'id': 'request-one'}]
        identity = digest(canonical({'plan': plan, 'provider': config}))
        meta = {'batch': 'example', 'targets': 5, 'request_count': 1,
                'plan_sha256': digest(canonical(plan)), 'provider_sha256': digest(canonical(config)),
                'max_attempts_per_request': 30, 'max_retries': 29, 'max_wait_seconds': 30,
                'generation_caps': {'max_items': 5, 'max_requests': 30, 'max_output_budget': 30 * 4096}}
        for folder in (work, review):
            write_json(folder / 'batch-plan.json', meta)
        write_json(work / 'results/run.json', {'identity': identity})
        rows = [{'request_id': 'request-one', 'status': status, 'retryable': True,
                 'finished_at': '2000-01-01T00:00:00+00:00'} for status in statuses]
        write_json(work / 'results/summary.json', {'completed_requests': sum(r['status'] == 'completed' for r in rows),
                                                  'attempts': len(rows)})
        for name, value in (('ROOT', root), ('CACHE', root / '.cache/lexicon-expansion')):
            p = patch.object(batch, name, value)
            p.start()
            self.addCleanup(p.stop)
        for name, value in (('load_plan', (plan, jobs)), ('load_config', config), ('read_attempts', rows)):
            p = patch.object(batch, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(batch, 'recover_saved')
        p.start()
        self.addCleanup(p.stop)
        return work, review, rows

    def test_completed_request_is_reused_without_model_call(self):
        work, review, rows = self.fixture(('completed',))
        with patch.object(batch, 'generate') as generate:
            result = batch.run('example')
        generate.assert_not_called()
        self.assertEqual(result['generation']['completed_requests'], 1)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(result['complete'])

    def test_thirty_historical_failures_exhaust_request_without_new_call(self):
        self.fixture(('failed',) * 30)
        with patch.object(batch, 'generate') as generate:
            result = batch.run('example')
        generate.assert_not_called()
        self.assertEqual(result['generation']['attempts'], 30)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['incomplete_requests'][0]['reason'], 'retry-limit')

    def test_content_failure_is_not_retried_and_progress_reports_incomplete(self):
        _, _, rows = self.fixture(('failed',))
        rows[0].update(failure_category='content')
        checkpoints = []
        with patch.object(batch, 'generate') as generate:
            result = batch.run('example', progress=checkpoints.append)
        generate.assert_not_called()
        self.assertEqual(result['incomplete_requests'][0]['reason'], 'content-validation')
        self.assertEqual(checkpoints[-1]['status'], 'incomplete')

    def test_saved_response_is_recovered_before_retry_and_keeps_attempt_count(self):
        work, _, rows = self.fixture(('failed',))
        rows[0].update(response_sha256='saved', failure_category='content')
        def recover(*args):
            rows[0].update(status='completed')
            write_json(work / 'results/summary.json', {'completed_requests': 1, 'attempts': 1})
            return {'model_requests': 0, 'recovered': [{'sequence': 1}], 'rejected': []}
        with patch.object(batch, 'recover_saved', side_effect=recover), patch.object(batch, 'generate') as generate:
            result = batch.run('example')
        generate.assert_not_called()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['generation']['attempts'], 1)

    def test_uncertain_request_blocks_before_call(self):
        self.fixture(('started',))
        with patch.object(batch, 'generate') as generate:
            with self.assertRaisesRegex(Invalid, 'uncertain'):
                batch.run('example')
        generate.assert_not_called()

    def test_independent_review_can_change_while_frozen_generation_runs(self):
        work, review, rows = self.fixture()

        def complete(*args, **kwargs):
            write_json(review / 'evaluation-decisions.json', {'items': ['independent authored decision']})
            rows.append({'request_id': 'request-one', 'status': 'completed'})
            write_json(work / 'results/summary.json', {'completed_requests': 1, 'attempts': 1})

        with patch.object(batch, 'generate', side_effect=complete) as generate:
            result = batch.run('example')
        generate.assert_called_once()
        self.assertEqual(result['generation']['completed_requests'], 1)

    def test_metadata_tampering_stops_before_model_call(self):
        work, review, rows = self.fixture()
        write_json(review / 'batch-plan.json', {'tampered': True})
        with patch.object(batch, 'generate') as generate:
            with self.assertRaisesRegex(Invalid, 'copies differ'):
                batch.run('example')
        generate.assert_not_called()

    def test_path_cannot_escape_batch_directory(self):
        for name in ('.', '..', '../escape', '..\\escape', '/absolute'):
            with self.assertRaises(Invalid):
                batch.run(name)
