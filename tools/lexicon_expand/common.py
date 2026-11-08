"""Small, deterministic file helpers shared by the expansion commands."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from tools.lexicon.pipeline import atomic_write, unique_keys

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/lexicon-expansion"
CACHE = ROOT / ".cache/lexicon-expansion"


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_keys)


def write_json(path, value):
    atomic_write(Path(path), (json.dumps(value, ensure_ascii=False, indent=2,
                                       allow_nan=False) + "\n").encode("utf-8"))


def read_jsonl(path):
    rows = []
    with Path(path).open(encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            require(bool(line.strip()), f"Blank record at line {number}")
            rows.append(json.loads(line, object_pairs_hook=unique_keys))
    return rows


def write_jsonl(path, rows):
    atomic_write(Path(path), b"".join(canonical(row) + b"\n" for row in rows))


def generated_directory(path):
    resolved = Path(path).resolve()
    require(resolved.is_relative_to(CACHE.resolve()) and resolved != CACHE.resolve(),
            "Expansion outputs must be in a subdirectory of .cache/lexicon-expansion")
    return resolved


def word_key(value):
    require(isinstance(value, str), "Expected a word string")
    return " ".join(value.replace("’", "'").replace("‘", "'").split()).casefold()


def clean_text(value, label, maximum=256):
    require(isinstance(value, str) and value == value.strip() and bool(value),
            f"Invalid {label}")
    require(len(value.encode("utf-8")) <= maximum, f"Oversized {label}")
    require(not any(ord(c) < 32 or ord(c) == 127 for c in value),
            f"Control character in {label}")
    return value


def english(value):
    clean_text(value, "English", 128)
    require(re.fullmatch(r"[A-Za-z][A-Za-z0-9 ',.!?&/-]*", value) is not None,
            "English must be a plain word or short phrase")
    require(len(value.split()) <= 8 and "..." not in value and "…" not in value,
            "English phrase is too long or truncated")
    require(not re.search(r"\b(?:see also|variant of|classifier for|abbr\. for)\b", value, re.I),
            "Unresolved dictionary metadata")
    return value
