"""Durable runtime output writes under Windows sharing restrictions."""
import json
import os
import time

from tools.lexicon.pipeline import atomic_write as _atomic_write
from tools.lexicon_expand.common import canonical


def atomic_write(path, content):
    # Retry only the local write, never the associated provider request.
    for attempt in range(8):
        try:
            return _atomic_write(path, content)
        except PermissionError as error:
            if os.name != 'nt' or getattr(error, 'winerror', None) not in (5, 32, 33) or attempt == 7:
                raise
            time.sleep(min(0.05 * 2 ** attempt, 0.2))


def write_json(path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8'))


def write_jsonl(path, rows):
    atomic_write(path, b''.join(canonical(row) + b'\n' for row in rows))
