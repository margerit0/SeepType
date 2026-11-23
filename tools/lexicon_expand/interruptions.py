"""Inspect abandoned calls without rewriting their original request receipts."""
from datetime import datetime, timezone
import os

from tools.lexicon_expand.common import digest, read_json, require
from tools.lexicon_expand.storage import write_json


def process_alive(pid):
    require(type(pid) is int and pid > 0, 'Invalid background process ID')
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            require(ctypes.get_last_error() == 87, 'Cannot verify background process exit')
            return False
        try:
            code = wintypes.DWORD()
            require(kernel.GetExitCodeProcess(handle, ctypes.byref(code)), 'Cannot inspect background process')
            return code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def effective_interruption(output, path, attempt):
    resolution_path = output / 'interruptions' / path.name
    if not resolution_path.exists():
        return attempt
    row = read_json(resolution_path)
    require(attempt['status'] == 'started' and row['receipt_sha256'] == digest(path.read_bytes()),
            'Interruption does not match the original request receipt')
    require(row['schema_version'] == 1 and row['action'] == 'retry-with-unknown-outcome'
            and row['identity'] == attempt['identity'] and row['sequence'] == attempt['sequence']
            and row['request_id'] == attempt['request_id'], 'Interruption belongs to another request')
    require(row['owner_exit_confirmed'] is True and row['response_absent'] is True,
            'Interruption inspection is incomplete')
    require(not (output / 'responses' / path.name).exists(),
            'Interrupted request now has a saved response; inspect it before retrying')
    return {**attempt, 'original_status': 'started', 'status': 'failed',
            'finished_at': row['inspected_at'], 'interrupted_at': row['inspected_at'],
            'outcome_unknown': True, 'retryable': True, 'failure_scope': 'request',
            'failure_category': 'interrupted', 'failure_kind': 'InterruptedRequest',
            'failure_message': 'Previous process exited without a saved response; provider outcome and usage remain unknown'}


def inspect_interrupted(output, owner, timeout_seconds):
    """Caller holds the combined and provider locks; authorization is explicit."""
    require(not process_alive(owner['pid']), 'Background process is still running')
    inspected_at = datetime.now(timezone.utc)
    owner_started = datetime.fromisoformat(owner['started_at'])
    inspected = []
    for path in sorted((output / 'attempts').glob('*.json')):
        attempt = read_json(path)
        if attempt['status'] != 'started' or (output / 'interruptions' / path.name).exists():
            continue
        started = datetime.fromisoformat(attempt['started_at'])
        require(owner_started <= started and (inspected_at - started).total_seconds() >= timeout_seconds,
                'Interrupted request does not match the exited owner or has not timed out')
        require(not (output / 'responses' / path.name).exists(),
                'Interrupted request has a saved response; inspect it before retrying')
        row = {'schema_version': 1, 'action': 'retry-with-unknown-outcome',
               'identity': attempt['identity'], 'request_id': attempt['request_id'],
               'sequence': attempt['sequence'], 'receipt_sha256': digest(path.read_bytes()),
               'inspected_at': inspected_at.isoformat(timespec='seconds'),
               'owner_pid': owner['pid'], 'owner_started_at': owner['started_at'],
               'owner_exit_confirmed': True, 'response_absent': True,
               'outcome_unknown': True}
        write_json(output / 'interruptions' / path.name, row)
        inspected.append(row)
    return inspected
