"""Provider migration preserves provenance, durable limits and existing drafts."""
import copy
from contextlib import ExitStack
import unittest
from unittest.mock import patch

from tools.lexicon_expand import gemini_takeover, generation, interruptions, parallel_run, planning, provider, retry
from tools.lexicon_expand import test_expansion as fixtures
from tools.lexicon_expand.common import Invalid, digest, read_json, read_jsonl, write_json


class GeminiTakeoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ExpansionTests.setUpClass()

    def setUp(self):
        self.fixture = fixtures.ExpansionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        f = self.fixture
        self.jobs = [planning.make_job('map_targets', [{**f.target, 'target_id': str(i)}], 'TEST ONLY')
                     for i in range(4)]
        self.plan = {**f.plan, 'maximum_items': 4, 'request_count': 4}
        for name, model in [('api.local.json', 'first-model'), ('api.grok.local.json', 'second-model')]:
            write_json(f.directory / name, {**f.config, 'model': model})
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module in (gemini_takeover, parallel_run):
            self.stack.enter_context(patch.object(module, 'CACHE', f.directory))
        for module in (gemini_takeover, parallel_run, generation):
            self.stack.enter_context(patch.object(module, 'load_plan', return_value=(self.plan, self.jobs)))
        self.stack.enter_context(patch.object(provider, 'read_key', return_value=f.key))
        self.stack.enter_context(patch.object(retry, 'wait_until'))
        with patch.object(provider, 'complete', side_effect=self.original_response):
            parallel_run.run(execute=True, retry_failed=True, max_retries=1)
        self.combined = f.directory / 'pilot-results-combined'

    def reply(self, job):
        reply = copy.deepcopy(self.fixture.reply)
        reply['results'][0]['target_id'] = job['payload']['targets'][0]['target_id']
        return reply

    def original_response(self, config, key, job):
        reply = self.reply(job)
        if job['id'] == self.jobs[1]['id']:
            reply['results'][0].update(senses=[], unresolved_reason='TEST ONLY unresolved item')
        elif job['id'] == self.jobs[3]['id']:
            raise provider.ProviderFailure('HTTP 504')
        return self.fixture.envelope(reply)

    def test_takeover_fills_only_gaps_preserves_original_receipts_and_resumes_without_calls(self):
        original_records = read_jsonl(self.combined / 'drafts.jsonl')
        files = [p for name in ('pilot-results-v1', 'pilot-results-grok')
                 for p in (self.fixture.directory / name).rglob('*.json')]
        before = {p: digest(p.read_bytes()) for p in files}
        calls = {}

        def respond(config, key, job):
            self.assertEqual(config['model'], 'first-model')
            calls[job['id']] = calls.get(job['id'], 0) + 1
            self.assertIn(job['id'], (self.jobs[1]['id'], self.jobs[3]['id']))
            if job['id'] == self.jobs[3]['id'] and calls[job['id']] == 1:
                raise provider.ProviderFailure('HTTP 504')
            return self.fixture.envelope(self.reply(job))

        with patch.object(provider, 'complete', side_effect=respond) as call:
            preview = gemini_takeover.run()
            call.assert_not_called()
            self.assertFalse((self.combined / 'gemini-takeover.json').exists())
            self.assertEqual(preview['pending_requests'], 2)
            result = gemini_takeover.run(execute=True)
            self.assertEqual(call.call_count, 3)
            self.assertEqual(result['resolved_draft_items'], 4)
            self.assertEqual(result['attempts_including_legacy'], 10)
            merged = {r['id']: r for r in read_jsonl(self.combined / 'drafts.jsonl')}
            for record in original_records:
                if record['senses']:
                    self.assertEqual(merged[record['id']], record)
            self.assertEqual({p: digest(p.read_bytes()) for p in files}, before)
            call.reset_mock()
            self.assertEqual(gemini_takeover.run(execute=True)['resolved_draft_items'], 4)
            call.assert_not_called()
            with self.assertRaisesRegex(Invalid, 'Pilot now uses Gemini takeover'):
                parallel_run.run(execute=True)

    def test_content_failure_is_not_blindly_retried_and_other_jobs_continue(self):
        def respond(config, key, job):
            reply = self.reply(job)
            if job['id'] == self.jobs[1]['id']:
                reply['results'][0]['senses'][0]['pos'] = 'unsupported'
            return self.fixture.envelope(reply)

        with patch.object(provider, 'complete', side_effect=respond) as call:
            result = gemini_takeover.run(execute=True)
            self.assertEqual(call.call_count, 2)
            self.assertEqual(result['resolved_draft_items'], 3)
            call.reset_mock()
            gemini_takeover.run(execute=True)
            call.assert_not_called()

    def test_exhausted_original_shared_budget_prevents_any_new_api_call(self):
        path = self.combined / 'retry-policy.json'
        policy = read_json(path)
        policy['shared_attempt_cap'] = read_json(self.combined / 'summary.json')['attempts_including_legacy']
        write_json(path, policy)
        with patch.object(provider, 'complete') as call:
            with self.assertRaisesRegex(Invalid, 'shared budget'):
                gemini_takeover.run(execute=True)
            call.assert_not_called()
        self.assertFalse((self.combined / 'gemini-takeover.json').exists())

    def test_changed_original_receipt_is_rejected_after_takeover(self):
        with patch.object(provider, 'complete', side_effect=lambda config, key, job: self.fixture.envelope(self.reply(job))):
            gemini_takeover.run(execute=True)
        path = self.fixture.directory / 'pilot-results-grok/attempts/00001.json'
        path.write_bytes(path.read_bytes() + b'\n')
        with patch.object(provider, 'complete') as call:
            with self.assertRaisesRegex(Invalid, 'Original pilot receipts or policy changed'):
                gemini_takeover.run(execute=True)
            call.assert_not_called()

    def test_uncertain_original_request_prevents_takeover(self):
        path = self.fixture.directory / 'pilot-results-grok/attempts/00003.json'
        row = read_json(path)
        row['status'] = 'started'
        write_json(path, row)
        with patch.object(provider, 'complete') as call:
            with self.assertRaisesRegex(Invalid, 'in-flight'):
                gemini_takeover.run(execute=True)
            call.assert_not_called()

    def interrupted_takeover(self):
        with patch.object(provider, 'complete', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                gemini_takeover.run(execute=True)
        output = self.fixture.directory / 'pilot-results-gemini-takeover'
        path = output / 'attempts/00001.json'
        attempt = read_json(path)
        attempt['started_at'] = '2026-01-01T00:01:00+00:00'
        write_json(path, attempt)
        write_json(self.combined / 'background-state.json',
                   {'pid': 123456, 'started_at': '2026-01-01T00:00:00+00:00'})
        return output, path

    def test_interrupted_resume_preserves_receipt_budget_and_unknown_outcome(self):
        output, path = self.interrupted_takeover()
        original = path.read_bytes()
        with patch.object(provider, 'complete', side_effect=lambda config, key, job: self.fixture.envelope(self.reply(job))) as call:
            with self.assertRaisesRegex(Invalid, 'uncertain takeover'):
                gemini_takeover.run(execute=True)
            call.assert_not_called()
            with patch.object(interruptions, 'process_alive', return_value=False):
                result = gemini_takeover.run(execute=True, resume_interrupted=True)
            self.assertEqual(call.call_count, 2)
            self.assertEqual(result['resolved_draft_items'], 4)
            self.assertEqual(result['unconfirmed_provider_outcomes'], 1)
            self.assertEqual(result['uncertain_attempts'], 0)
            self.assertEqual(result['attempts_including_legacy'], 10)
            self.assertEqual(result['reserved_output_tokens'], 10 * self.fixture.config['max_output_tokens'])
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(read_json(path)['status'], 'started')
            self.assertTrue((output / 'interruptions/00001.json').exists())
            call.reset_mock()
            gemini_takeover.run(execute=True)
            call.assert_not_called()

    def test_interrupted_resume_rejects_live_owner_and_saved_response(self):
        output, path = self.interrupted_takeover()
        with patch.object(provider, 'complete') as call:
            with patch.object(interruptions, 'process_alive', return_value=True):
                with self.assertRaisesRegex(Invalid, 'still running'):
                    gemini_takeover.run(execute=True, resume_interrupted=True)
            (output / 'responses').mkdir(exist_ok=True)
            (output / 'responses/00001.json').write_bytes(b'{}')
            with patch.object(interruptions, 'process_alive', return_value=False):
                with self.assertRaisesRegex(Invalid, 'saved response'):
                    gemini_takeover.run(execute=True, resume_interrupted=True)
            call.assert_not_called()
            self.assertFalse((output / 'interruptions/00001.json').exists())

    def test_interrupted_inspection_is_explicit_and_rejects_recent_request(self):
        output, path = self.interrupted_takeover()
        with self.assertRaisesRegex(Invalid, 'requires --execute'):
            gemini_takeover.run(resume_interrupted=True)
        attempt = read_json(path)
        attempt['started_at'] = generation.now()
        write_json(path, attempt)
        with patch.object(interruptions, 'process_alive', return_value=False):
            with self.assertRaisesRegex(Invalid, 'has not timed out'):
                gemini_takeover.run(execute=True, resume_interrupted=True)
        self.assertFalse((output / 'interruptions/00001.json').exists())

    def test_interruption_overlay_rejects_receipt_tampering(self):
        output, path = self.interrupted_takeover()
        owner = read_json(self.combined / 'background-state.json')
        with patch.object(interruptions, 'process_alive', return_value=False):
            interruptions.inspect_interrupted(output, owner, 90)
        path.write_bytes(path.read_bytes() + b'\n')
        with patch.object(provider, 'complete') as call:
            with self.assertRaisesRegex(Invalid, 'does not match'):
                gemini_takeover.run(execute=True)
            call.assert_not_called()

    def incomplete_takeover(self):
        def respond(config, key, job):
            if job['id'] == self.jobs[3]['id']:
                raise provider.ProviderFailure('HTTP 429')
            reply = self.reply(job)
            reply['results'][0]['senses'][0]['pos'] = 'unsupported'
            return self.fixture.envelope(reply)
        with patch.object(provider, 'complete', side_effect=respond):
            return gemini_takeover.run(execute=True)

    def test_user_authorized_rerun_fills_only_remaining_targets_and_preserves_history(self):
        before_summary = self.incomplete_takeover()
        self.assertEqual(before_summary['resolved_draft_items'], 2)
        before_records = read_jsonl(self.combined / 'drafts.jsonl')
        files = [p for name in ('pilot-results-v1', 'pilot-results-grok', 'pilot-results-gemini-takeover')
                 for p in (self.fixture.directory / name).rglob('*.json')]
        before = {p: p.read_bytes() for p in files}
        with patch.object(provider, 'complete', side_effect=lambda config, key, job: self.fixture.envelope(self.reply(job))) as call:
            preview = gemini_takeover.run(rerun_issues=True)
            call.assert_not_called()
            self.assertEqual(preview['preserved_resolved_items'], 2)
            self.assertEqual(preview['targets_in_selected_requests'], 2)
            self.assertFalse((self.combined / 'gemini-rerun-issues.json').exists())
            result = gemini_takeover.run(execute=True, rerun_issues=True)
            self.assertEqual(call.call_count, 2)
            self.assertEqual(result['resolved_draft_items'], 4)
            self.assertEqual(result['attempts_including_legacy'], before_summary['attempts_including_legacy'] + 2)
            self.assertEqual(result['reserved_output_tokens'], before_summary['reserved_output_tokens'] +
                             2 * self.fixture.config['max_output_tokens'])
            self.assertEqual({p: p.read_bytes() for p in files}, before)
            merged = {r['id']: r for r in read_jsonl(self.combined / 'drafts.jsonl')}
            for record in before_records:
                if record['senses']:
                    self.assertEqual(merged[record['id']], record)
            call.reset_mock()
            gemini_takeover.run(execute=True, rerun_issues=True)
            call.assert_not_called()
            with self.assertRaisesRegex(Invalid, 'issue rerun'):
                gemini_takeover.run(execute=True)
            call.assert_not_called()

    def test_issue_rerun_retry_counts_survive_restart(self):
        before_summary = self.incomplete_takeover()
        with patch.object(provider, 'complete', side_effect=provider.ProviderFailure('HTTP 429')) as call:
            result = gemini_takeover.run(execute=True, rerun_issues=True)
            self.assertEqual(call.call_count, 4)
            self.assertEqual(result['attempts_including_legacy'], before_summary['attempts_including_legacy'] + 4)
            call.reset_mock()
            gemini_takeover.run(execute=True, rerun_issues=True)
            call.assert_not_called()

    def test_issue_rerun_rejects_changed_previous_takeover_receipt(self):
        self.incomplete_takeover()
        with patch.object(provider, 'complete', side_effect=provider.ProviderFailure('HTTP 429')):
            gemini_takeover.run(execute=True, rerun_issues=True)
        path = self.fixture.directory / 'pilot-results-gemini-takeover/attempts/00001.json'
        path.write_bytes(path.read_bytes() + b'\n')
        with patch.object(provider, 'complete') as call:
            with self.assertRaisesRegex(Invalid, 'Original pilot receipts or policy changed'):
                gemini_takeover.run(execute=True, rerun_issues=True)
            call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
