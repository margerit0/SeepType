"""Backoff timing, durable retry limits, cancellation and transport classification."""
import io
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from tools.lexicon_expand import provider, retry
from tools.lexicon_expand.common import Invalid
from tools.lexicon_expand.generation import GenerationFailure, now


class RetryTests(unittest.TestCase):
    def run_request(self, rows, attempt, maximum=15):
        events = []
        with patch.object(retry, 'wait_until') as wait:
            result = retry.retry_request(attempt, lambda: rows, max_retries=maximum,
                                         emit=events.append, cancelled=lambda: False)
        return result, events, wait

    def test_failures_wait_three_six_twelve_then_success_stops_retrying(self):
        rows = []
        def send():
            if len(rows) < 3:
                rows.append({'status': 'failed', 'retryable': True, 'finished_at': now()})
                raise GenerationFailure('HTTP 504', retryable=True)
            rows.append({'status': 'completed'})
        result, events, wait = self.run_request(rows, send)
        self.assertTrue(result)
        self.assertEqual(len(rows), 4)
        self.assertEqual([e['delay_seconds'] for e in events], [3, 6, 12])
        self.assertEqual(wait.call_count, 3)

    def test_fifteen_retries_allow_exactly_sixteen_attempts_and_do_not_reset_on_resume(self):
        rows = []
        def send():
            rows.append({'status': 'failed', 'retryable': True, 'finished_at': now()})
            raise GenerationFailure('HTTP 429', retryable=True)
        result, events, wait = self.run_request(rows, send)
        self.assertFalse(result)
        self.assertEqual(len(rows), 16)
        self.assertEqual(wait.call_count, 15)
        self.assertEqual([e['delay_seconds'] for e in events if e['event']=='retry_scheduled'],
                         [3, 6, 12, 24] + [30] * 11)
        self.assertEqual(events[-1]['reason'], 'retry-limit')
        with patch.object(retry, 'wait_until') as wait_again:
            self.assertFalse(retry.retry_request(lambda: self.fail('extra attempt'), lambda: rows,
                             max_retries=15, emit=lambda e: None, cancelled=lambda: False))
        wait_again.assert_not_called()

    def test_resume_keeps_original_due_time_and_retry_number(self):
        rows = [{'status': 'failed', 'retryable': True, 'finished_at': '2026-11-08T00:00:00+00:00'}] * 2
        result, events, wait = self.run_request(rows, lambda: rows.append({'status': 'completed'}))
        self.assertTrue(result)
        self.assertEqual(events[0]['retry_number'], 2)
        self.assertEqual(wait.call_args.args[0], '2026-11-08T00:00:06+00:00')

    def test_raised_limit_keeps_sixteen_failures_and_stops_at_thirty_total_attempts(self):
        rows = [{'status': 'failed', 'retryable': True, 'finished_at': now()} for _ in range(16)]
        def send():
            rows.append({'status': 'failed', 'retryable': True, 'finished_at': now()})
            raise GenerationFailure('HTTP 429', retryable=True)
        result, events, wait = self.run_request(rows, send, maximum=29)
        self.assertFalse(result)
        self.assertEqual(len(rows), 30)
        self.assertEqual(wait.call_count, 14)
        scheduled = [e for e in events if e['event'] == 'retry_scheduled']
        self.assertEqual([e['retry_number'] for e in scheduled], list(range(16, 30)))
        self.assertTrue(all(e['delay_seconds'] == 30 for e in scheduled))
        result, _, wait = self.run_request(rows, lambda: self.fail('limit reset'), maximum=29)
        self.assertFalse(result)
        wait.assert_not_called()

    def test_resume_caps_long_wait_and_preserves_remaining_attempts(self):
        rows = [{'status': 'failed', 'retryable': True,
                 'finished_at': '2026-11-08T00:00:00+00:00'} for _ in range(12)]
        def send():
            rows.append({'status': 'failed', 'retryable': True, 'finished_at': now()})
            raise GenerationFailure('HTTP 504', retryable=True)
        result, events, wait = self.run_request(rows, send)
        self.assertFalse(result)
        self.assertEqual(len(rows), 16)
        scheduled = [e for e in events if e['event'] == 'retry_scheduled']
        self.assertEqual([e['retry_number'] for e in scheduled], [12, 13, 14, 15])
        self.assertEqual([e['delay_seconds'] for e in scheduled], [30] * 4)
        self.assertEqual(wait.call_args_list[0].args[0], '2026-11-08T00:00:30+00:00')
        self.assertEqual(events[-1]['reason'], 'retry-limit')

    def test_resume_sends_immediately_if_capped_deadline_already_passed(self):
        rows = [{'status': 'failed', 'retryable': True,
                 'finished_at': '1970-01-01T00:00:00+00:00'} for _ in range(12)]
        with patch.object(retry.time, 'time', return_value=31), \
             patch.object(retry.time, 'sleep') as sleep:
            self.assertTrue(retry.retry_request(lambda: rows.append({'status': 'completed'}), lambda: rows,
                            max_retries=15, emit=lambda e: None, cancelled=lambda: False))
        sleep.assert_not_called()
        self.assertEqual(len(rows), 13)

    def test_completed_or_nonretryable_receipts_never_send_again(self):
        for row, expected in [({'status':'completed'}, True),
                              ({'status':'failed', 'retryable':False}, False)]:
            result, _, wait = self.run_request([row], lambda: self.fail('unexpected request'))
            self.assertEqual(result, expected)
            wait.assert_not_called()

    def test_configuration_errors_and_uncertain_results_are_not_retried(self):
        with self.assertRaisesRegex(Invalid, 'uncertain'):
            self.run_request([{'status':'started'}], lambda: self.fail('unexpected request'))
        with self.assertRaisesRegex(Invalid, 'configuration'):
            self.run_request([], lambda: (_ for _ in ()).throw(Invalid('configuration changed')))

    def test_waits_are_chunked_and_cancellation_prevents_the_next_attempt(self):
        with patch.object(retry.time, 'time', side_effect=[0, 30, 60]), \
             patch.object(retry.time, 'sleep') as sleep:
            retry.wait_until('1970-01-01T00:01:00+00:00', lambda e: None, lambda: False)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [30, 30])
        with self.assertRaisesRegex(Invalid, 'stopped'):
            retry.retry_request(lambda: self.fail('unexpected request'), lambda: [], max_retries=15,
                                emit=lambda e: None, cancelled=lambda: True)

    def test_only_transient_http_errors_are_retryable(self):
        config = {'endpoint':'https://provider.invalid/v1/chat/completions', 'model':'test-model',
                  'token_parameter':'max_tokens', 'max_output_tokens':4096,
                  'temperature':None, 'response_format':'none', 'timeout_seconds':5}
        for code in [401, 403, 408, 429, 500, 502, 503, 504]:
            error = HTTPError(config['endpoint'], code, 'Test failure', {}, io.BytesIO(b''))
            with self.subTest(code=code), patch.object(provider, 'build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(provider.ProviderFailure) as caught:
                    provider.complete(config, 'TEST-ONLY-KEY', {'messages':[]})
            self.assertEqual(caught.exception.retryable, code not in [401, 403])


if __name__ == '__main__':
    unittest.main()
