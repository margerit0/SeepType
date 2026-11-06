"""Deterministic, offline-first packaging helpers (Python standard library)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache/packaging"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_changed(path: Path, data: bytes | str):
    if isinstance(data, str):
        data = data.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def package_path(value: str) -> str:
    """Reject Windows aliases, ADS, device names, traversal and ambiguous names."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"Invalid package path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value:
        raise ValueError(f"Noncanonical package path: {value!r}")
    for part in path.parts:
        if part in (".", "..") or part[-1:] in (".", " "):
            raise ValueError(f"Unsafe package component: {value!r}")
        if re.search(r'[<>:"|?*\x00-\x1f]', part) or re.match(
                r"(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part):
            raise ValueError(f"Reserved package path: {value!r}")
    return value


def deterministic_zip(path: Path, files: dict[str, bytes]):
    names = sorted(files)
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Case-insensitive package path collision")
    for name in names:
        package_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Stored entries make archive bytes independent of zlib version and level.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in names:
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_STORED
            archive.writestr(entry, files[name])


def product():
    import uuid
    data = json.loads((ROOT / "packaging/product.json").read_text(encoding="utf-8"))
    for value in data["guids"].values():
        uuid.UUID(value)
    return data
