"""Receipt-based exponential backoff; waits and limits survive process restarts."""
from datetime import datetime, timedelta
import time

from tools.lexicon_expand.common import require
from tools.lexicon_expand.generation import GenerationFailure


MAX_RETRY_DELAY_SECONDS = 30
MAX_RETRIES = 29


def retry_delay(number, base_seconds=3):
    require(type(number) is int and 1 <= number <= MAX_RETRIES,
            f'Retry number must be between 1 and {MAX_RETRIES}')
    return min(base_seconds * 2 ** (number - 1), MAX_RETRY_DELAY_SECONDS)


def wait_until(due_at, emit, cancelled):
    deadline = datetime.fromisoformat(due_at).timestamp()
    while True:
        require(not cancelled(), 'Retry run was stopped')
        remaining = deadline - time.time()
        if remaining <= 0:
            return
        emit({'event': 'retry_waiting', 'remaining_seconds': round(remaining, 1), 'next_attempt_at': due_at})
        # Short waits let Ctrl+C / stop.json interrupt the backoff promptly.
        time.sleep(min(30, remaining))


def retry_request(attempt, history, *, max_retries, emit, cancelled):
    """History includes all receipts governed by this limit, including earlier runs."""
    require(type(max_retries) is int and 0 <= max_retries <= MAX_RETRIES,
            f'max_retries must be between 0 and {MAX_RETRIES}')
    while True:
        require(not cancelled(), 'Retry run was stopped')
        rows = history()
        if any(row['status'] == 'completed' for row in rows):
            return True
        require(not any(row['status'] == 'started' for row in rows), 'Inspect uncertain requests before continuing')
        failures = [row for row in rows if row['status'] == 'failed']
        if failures:
            last = failures[-1]
            if not last.get('retryable', False) or len(failures) > max_retries:
                emit({'event': 'retry_stopped', 'failed_attempts': len(failures),
                      'failure_scope': last.get('failure_scope', 'request' if last.get('retryable') else 'provider'),
                      'validation_error': last.get('validation_error'),
                      'error': last.get('failure_message'),
                      'reason': 'retry-limit' if last.get('retryable', False) else 'non-retryable-error'})
                return False
            delay = retry_delay(len(failures))
            due = (datetime.fromisoformat(last['finished_at']) + timedelta(seconds=delay)).isoformat(timespec='seconds')
            emit({'event': 'retry_scheduled', 'retry_number': len(failures), 'max_retries': max_retries,
                  'delay_seconds': delay, 'max_delay_seconds': MAX_RETRY_DELAY_SECONDS,
                  'next_attempt_at': due, 'error': last.get('failure_message'),
                  'validation_error': last.get('validation_error')})
            wait_until(due, emit, cancelled)
        try:
            attempt()
        except GenerationFailure:
            # The receipt is authoritative, including after an interrupted wait.
            continue
        return True
