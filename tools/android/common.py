"""Android build helpers. All downloads and outputs belong to this checkout."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache/android"
DOWNLOADS = CACHE / "downloads"


def digest(path: Path, algorithm="sha256") -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def write(path: Path, content: str | bytes):
    content = content.encode("utf-8") if isinstance(content, str) else content
    if path.is_file() and path.read_bytes() == content:
        return
    safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def json_write(path: Path, content):
    write(path, json.dumps(content, ensure_ascii=False, indent=2) + "\n")


def safe(path: Path) -> Path:
    resolved = path.resolve()
    roots = [ROOT.resolve()]
    location = ROOT / ".cache/android-cache-location.json"
    if location.is_file():
        configuration = json.loads(location.read_text(encoding="utf-8-sig"))
        if Path(configuration["workspace"]).resolve() != ROOT.resolve():
            raise ValueError("External Android cache belongs to another workspace")
        roots.append(Path(configuration["path"]).resolve())
    if not any(resolved.is_relative_to(root) and resolved != root for root in roots):
        raise ValueError(f"Output outside Android worktree: {path}")
    return resolved


def fetch(url: str, path: Path, expected: str | None = None, algorithm="sha256"):
    safe(path)
    if path.is_file() and (not expected or digest(path, algorithm) == expected):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    print(f"Download {path.name}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "StudyIME-Android-build/0.1"})
    with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as output:
        if not response.url.startswith("https://"):
            raise ValueError("Download left HTTPS")
        shutil.copyfileobj(response, output, 1024 * 1024)
    if expected and digest(partial, algorithm) != expected:
        raise ValueError(f"Checksum mismatch: {path.name}")
    partial.replace(path)
    return path


def extract(archive: Path, destination: Path, select=lambda _: True, strip=1):
    """Extract regular files only; reject traversals and archive symlinks."""
    safe(destination)
    destination.mkdir(parents=True, exist_ok=True)

    def output(name):
        parts = name.replace("\\", "/").split("/")
        if name.startswith(("/", "\\")) or any(p in ("..",) or ":" in p for p in parts):
            raise ValueError(f"Unsafe archive path: {name}")
        relative = "/".join(parts[strip:])
        if not relative or not select(relative):
            return None
        path = destination / relative
        safe(path)
        if not path.resolve().is_relative_to(destination.resolve()):
            raise ValueError("Archive escaped destination")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                if member.is_dir():
                    continue
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    continue
                path = output(member.filename)
                if path:
                    with bundle.open(member) as source, path.open("wb") as target:
                        shutil.copyfileobj(source, target)
                    if os.name != "nt":
                        path.chmod((member.external_attr >> 16) & 0o777 or 0o644)
    else:
        with tarfile.open(archive) as bundle:
            for member in bundle:
                if not member.isfile():
                    continue
                path = output(member.name)
                if path:
                    with bundle.extractfile(member) as source, path.open("wb") as target:
                        shutil.copyfileobj(source, target)
                    if os.name != "nt":
                        path.chmod(member.mode & 0o777)


def run(argv, name: str, *, env=None, cwd=ROOT):
    log = CACHE / "logs" / (name + ".log")
    log.parent.mkdir(parents=True, exist_ok=True)
    print(name, flush=True)
    with log.open("wb") as output:
        result = subprocess.run([str(value) for value in argv], cwd=cwd, env=env,
                                stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        print(log.read_text(encoding="utf-8", errors="replace")[-14000:])
        raise RuntimeError(f"{name} failed ({result.returncode}); see {log}")
    return log
