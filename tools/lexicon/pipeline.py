"""Pinned offline lexicon preparation, human review import and reproducible export."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/lexicon"
LICENSE = "CC-BY-SA-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
SHA = re.compile(r"[0-9a-f]{64}")
SOURCE_LINE = re.compile(r"(\S+) (\S+) \[([^\[\]]+)\] /(.*)/")
STATUSES = {"pending", "approved-for-distribution", "rejected"}


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path):
    require(path.stat().st_size <= 8 * 1024 * 1024, f"Oversized JSON: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)


def text(value, label, limit=2048):
    require(isinstance(value, str) and value.strip() == value and bool(value), f"Invalid {label}")
    require(len(value.encode("utf-8")) <= limit, f"Oversized {label}")
    require(not any(ord(c) < 32 or ord(c) == 127 for c in value), f"Control character in {label}")
    return value


def english(value):
    text(value, "English", 128)
    require(re.fullmatch(r"[A-Za-z][A-Za-z0-9 ',.!?;:()&/-]*", value) is not None,
            "English must be a short, plain English word or phrase")
    require("..." not in value and "…" not in value, "Ellipsis cannot be committed")
    require(not re.search(r"(?:CL:|https?://|see also|variant of|also pr\.|Taiwan pr\.|"
                          r"abbr\. for|classifier for|\((?:coll|slang|fig|computing)\.?\))",
                          value, re.I), "Unresolved dictionary metadata in English")
    return value


def timestamp(value):
    text(value, "review timestamp", 64)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Review timestamp must include its timezone")


def inside(directory: Path, relative: str) -> Path:
    path = (directory / relative).resolve()
    require(path.is_relative_to(directory.resolve()) and not Path(relative).is_absolute(),
            f"Data path escapes its directory: {relative}")
    return path


def atomic_write(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".",
                                     suffix=".tmp", delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(content)
        except BaseException:
            output.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_source(line):
    match = SOURCE_LINE.fullmatch(line)
    require(match is not None, "Malformed CC-CEDICT v1 source entry")
    traditional, chinese, pinyin, gloss = match.groups()
    return {"traditional": traditional, "chinese": chinese, "pinyin": pinyin, "gloss": gloss}


def entry_hash(entry, lock):
    content = {key: value for key, value in entry.items() if key != "review"}
    return sha256(canonical({"entry": content, "source_id": lock["source_id"],
                             "snapshot_sha256": lock["artifact"]["text_sha256"],
                             "license": lock["license"]}))


@dataclass
class Lexicon:
    directory: Path
    data: dict
    lock: dict
    sources: dict

    @property
    def entries(self):
        return self.data["entries"]

    @property
    def content_hash(self):
        return sha256(canonical({"id": self.data["id"], "version": self.data["version"],
                                 "entries": [entry_hash(e, self.lock) for e in self.entries]}))

    @property
    def counts(self):
        counts = Counter(e["review"]["status"] for e in self.entries)
        return {status: counts[status] for status in sorted(STATUSES)}


def validate(directory: Path = DATA, snapshot: Path | None = None, *, data_override=None) -> Lexicon:
    directory = directory.resolve()
    data = read_json(directory / "entries.json") if data_override is None else data_override
    lock = read_json(directory / "source.lock.json")
    require(type(data["schema_version"]) is int and data["schema_version"] == 1,
            "Unsupported lexicon schema")
    require(type(lock["schema_version"]) is int and lock["schema_version"] == 1,
            "Unsupported source lock schema")
    require(data["source_id"] == lock["source_id"], "Source snapshot identity mismatch")
    text(data["id"], "lexicon ID", 80)
    require(re.fullmatch(r"[a-z0-9-]+", data["id"]), "Invalid lexicon ID")
    text(data["version"], "version", 40)
    require(lock["license"] == LICENSE and lock["license_url"] == LICENSE_URL,
            "Unsupported or conflicting source license")
    require(lock["license_review"]["status"] == "verified", "Source license has not been verified")
    require(f"#! license={LICENSE_URL}" in lock["original_header"], "License missing from snapshot header")
    require(f"#! date={lock['snapshot_date']}" in lock["original_header"], "Snapshot date mismatch")
    require(f"#! entries={lock['entry_count']}" in lock["original_header"], "Snapshot count mismatch")
    for field in ("archive_sha256", "text_sha256"):
        require(SHA.fullmatch(lock["artifact"][field]), f"Invalid {field}")
    require(set(lock["files"]) == {"sources/entries.json", "licenses/CC-BY-SA-4.0.txt"},
            "Unexpected source evidence files")
    for filename, digest in lock["files"].items():
        require(SHA.fullmatch(digest), f"Invalid evidence digest: {filename}")
        require(sha256(inside(directory, filename).read_bytes()) == digest,
                f"Source evidence hash mismatch: {filename}")
    source_file = read_json(directory / "sources/entries.json")
    require(source_file["source_id"] == lock["source_id"], "Excerpt belongs to a different snapshot")
    sources = {}
    for source in source_file["entries"]:
        require(type(source["line_number"]) is int and source["line_number"] > 0, "Invalid source line")
        digest = sha256(source["text"].encode("utf-8"))
        require(source["sha256"] == digest and digest not in sources, "Duplicate or altered source entry")
        sources[digest] = {**source, **parse_source(source["text"])}
    require(type(data["expected_entries"]) is int and data["expected_entries"] > 0 and
            len(data["entries"]) == data["expected_entries"], "Incomplete lexicon batch")
    ids, chinese = set(), set()
    for entry in data["entries"]:
        identifier = text(entry["id"], "entry ID", 80)
        require(identifier not in ids, f"Duplicate entry ID: {identifier}")
        ids.add(identifier)
        word = text(entry["chinese"], "Chinese word", 64)
        require(re.fullmatch(r"[\u3400-\u9fff]{1,16}", word), f"Invalid Chinese word: {word}")
        require(word not in chinese, f"Duplicate Chinese word: {word}")
        chinese.add(word)
        text(entry["category"], "category", 80)
        english(entry["display_english"])
        english(entry["commit_english"])
        require(entry["display_english"] == entry["commit_english"],
                f"{word}: the current Lua runtime requires identical display and commit text")
        require(entry["license"] == LICENSE, f"Wrong license: {word}")
        text(entry["modification"], "modification note", 2048)
        require(type(entry["review_attention"]) is bool, "Invalid review attention flag")
        source_ids = [entry["source_entry_sha256"], *entry["alternative_source_entries"]]
        require(len(set(source_ids)) == len(source_ids), f"Repeated source reference: {word}")
        for source_id in source_ids:
            require(source_id in sources and sources[source_id]["chinese"] == word,
                    f"Missing or mismatched source for {word}")
        review = entry["review"]
        require(review["status"] in STATUSES, f"Invalid review state: {word}")
        if review["status"] == "pending":
            require(all(review.get(k) is None for k in ("method", "reviewer", "reviewed_at", "content_sha256")),
                    f"Pending entry contains approval metadata: {word}")
        else:
            require(review["method"] == "human", f"Human review required for {word}")
            text(review["reviewer"], "reviewer", 120)
            timestamp(review["reviewed_at"])
            require(review["content_sha256"] == entry_hash(entry, lock), f"Stale review for {word}")
    if snapshot is not None:
        raw = snapshot.read_bytes()
        require(sha256(raw) == lock["artifact"]["text_sha256"], "Full snapshot hash mismatch")
        lines = raw.decode("utf-8-sig").splitlines()
        require(sum(bool(line) and not line.startswith("#") for line in lines) == lock["entry_count"],
                "Full snapshot entry count mismatch")
        for source in sources.values():
            require(source["line_number"] <= len(lines) and
                    lines[source["line_number"] - 1] == source["text"], "Excerpt not found at pinned source line")
    return Lexicon(directory, data, lock, sources)


def summary(lexicon: Lexicon):
    return {"schema_version": 1, "id": lexicon.data["id"], "version": lexicon.data["version"],
            "entries": len(lexicon.entries), "categories": dict(Counter(e["category"] for e in lexicon.entries)),
            "review_counts": lexicon.counts,
            "review_attention": sum(e["review_attention"] for e in lexicon.entries),
            "content_sha256": lexicon.content_hash,
            "source_snapshot": lexicon.lock["source_id"],
            "license": LICENSE,
            "release_ready": lexicon.counts["pending"] == 0 and lexicon.counts["approved-for-distribution"] > 0}


def make_review(lexicon: Lexicon) -> bytes:
    rows = []
    for entry in lexicon.entries:
        source = lexicon.sources[entry["source_entry_sha256"]]
        rows.append({**entry, "original_sha256": entry_hash(entry, lexicon.lock),
                     "pinyin": source["pinyin"], "source_text": source["text"],
                     "alternative_texts": [lexicon.sources[key]["text"] for key in entry["alternative_source_entries"]]})
    payload = {"content_sha256": lexicon.content_hash, "version": lexicon.data["version"],
               "source_date": lexicon.lock["snapshot_date"], "entries": rows}
    # The JSON is inert text. Escaping '<' prevents a dictionary value from
    # closing the script element; the UI always inserts values via textContent.
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    template = Path(__file__).with_name("review.html").read_text(encoding="utf-8")
    require(template.count("__LEXICON_DATA__") == 1, "Review template placeholder missing")
    return template.replace("__LEXICON_DATA__", encoded).encode("utf-8")


def apply_review(lexicon: Lexicon, decisions: dict):
    require(type(decisions["schema_version"]) is int and decisions["schema_version"] == 1,
            "Unsupported review format")
    require(decisions["base_sha256"] == lexicon.content_hash, "Review belongs to an older or different lexicon")
    reviewer = text(decisions["reviewer"], "reviewer", 120)
    timestamp(decisions["reviewed_at"])
    require(decisions["method"] == "human", "Machine checks cannot stand in for human review")
    require(isinstance(decisions["decisions"], list) and bool(decisions["decisions"]), "Empty review")
    data = json.loads(json.dumps(lexicon.data, ensure_ascii=False))
    by_id = {e["id"]: e for e in data["entries"]}
    seen = set()
    for decision in decisions["decisions"]:
        identifier = decision["id"]
        require(identifier in by_id and identifier not in seen, "Unknown or duplicate review entry")
        seen.add(identifier)
        entry = by_id[identifier]
        require(decision["original_sha256"] == entry_hash(entry, lexicon.lock), "Stale entry in review")
        require(decision["status"] in STATUSES, "Unknown review decision")
        value = english(decision["english"])
        previous = entry["commit_english"]
        entry["display_english"] = entry["commit_english"] = value
        if previous != value:
            entry["modification"] += f" 人工修订：{previous} → {value}。"
        if decision["status"] == "pending":
            entry["review"] = {"status": "pending", "method": None, "reviewer": None,
                               "reviewed_at": None, "content_sha256": None}
        else:
            entry["review"] = {"status": decision["status"], "method": "human", "reviewer": reviewer,
                               "reviewed_at": decisions["reviewed_at"], "content_sha256": entry_hash(entry, lexicon.lock)}
    return data


def build_files(lexicon: Lexicon, mode: str) -> dict[str, bytes]:
    lexicon = validate(lexicon.directory, data_override=lexicon.data)
    require(mode in {"preview", "release"}, "Unknown build mode")
    if mode == "release":
        require(lexicon.counts["pending"] == 0,
                f"Release export blocked: {lexicon.counts['pending']} entries await human review")
        require(lexicon.counts["approved-for-distribution"] > 0, "Release needs at least one approved entry")
    selected = [e for e in lexicon.entries if e["review"]["status"] != "rejected"]
    require(bool(selected), "No entries eligible for export")
    header = "-- REVIEW PREVIEW: not human-approved product data.\n" if mode == "preview" else "-- Human-reviewed lexicon.\n"
    header += f"-- Adapted from CC-CEDICT {lexicon.lock['snapshot_date']}; {LICENSE}.\n"
    header += f"-- {LICENSE_URL} See NOTICE.txt and the accompanying source records.\n"
    # Plain Lua string literals use UTF-8; ASCII controls and backslashes in
    # English are rejected by validation, and quoted Chinese keys are exact.
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    lua = header + "return {\n" + "".join(
        f"  [{quote(e['chinese'])}] = {quote(e['commit_english'])},\n"
        for e in sorted(selected, key=lambda item: item["chinese"])) + "}\n"
    files = {"lexicon.lua": lua.encode("utf-8"), "records.json": json_bytes(selected),
             "source.lock.json": (lexicon.directory / "source.lock.json").read_bytes(),
             "NOTICE.txt": (lexicon.directory / "NOTICE.txt").read_bytes()}
    for filename in lexicon.lock["files"]:
        files[filename] = inside(lexicon.directory, filename).read_bytes()
    if mode == "preview":
        files["review.html"] = make_review(lexicon)
    manifest = {**summary(lexicon), "mode": mode, "exported_entries": len(selected),
                "product_data": mode == "release",
                "files": {name: sha256(content) for name, content in sorted(files.items())}}
    files["manifest.json"] = json_bytes(manifest)
    return files


def zip_bytes(files: dict[str, bytes]) -> bytes:
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content, compresslevel=9)
    return result.getvalue()


def export(lexicon: Lexicon, output: Path, mode: str):
    output = output.resolve()
    require(output != lexicon.directory, "Do not export over the authoritative data directory")
    files = build_files(lexicon, mode)
    for name, content in files.items():
        atomic_write(inside(output, name), content)
    archive = output / f"{lexicon.data['id']}-{mode}.zip"
    atomic_write(archive, zip_bytes(files))
    return {"directory": str(output), "archive": str(archive), "archive_sha256": sha256(archive.read_bytes()),
            "mode": mode, "entries": json.loads(files["manifest.json"])["exported_entries"]}


def fetch_source(lexicon: Lexicon, cache: Path):
    artifact = lexicon.lock["artifact"]
    digest = artifact["archive_sha256"]
    archive_path = cache / (digest + ".txt.gz")
    if archive_path.exists():
        archive = archive_path.read_bytes()
    else:
        request = Request(artifact["url"], headers={"User-Agent": "StudyIME-lexicon-preparation/0.1"})
        with urlopen(request, timeout=40) as response:
            require(response.url.startswith("https://"), "Source download must stay on HTTPS")
            archive = response.read(20 * 1024 * 1024 + 1)
    require(sha256(archive) == digest and len(archive) == artifact["archive_bytes"],
            "Upstream snapshot changed; use the pinned cache or deliberately review a new snapshot")
    with gzip.GzipFile(fileobj=io.BytesIO(archive)) as compressed:
        raw = compressed.read(32 * 1024 * 1024 + 1)
    require(sha256(raw) == artifact["text_sha256"] and len(raw) == artifact["text_bytes"],
            "Uncompressed source hash mismatch")
    atomic_write(archive_path, archive)
    raw_path = cache / (digest + ".txt")
    atomic_write(raw_path, raw)
    validate(lexicon.directory, raw_path)
    return {"snapshot": str(raw_path), "sha256": sha256(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate")
    check.add_argument("--snapshot", type=Path)
    check.add_argument("--report", type=Path)
    build = commands.add_parser("build")
    build.add_argument("--mode", choices=["preview", "release"], default="release")
    build.add_argument("--output", type=Path, required=True)
    review = commands.add_parser("review")
    review.add_argument("--output", type=Path, required=True)
    apply = commands.add_parser("import-review")
    apply.add_argument("decisions", type=Path)
    fetch = commands.add_parser("fetch-source")
    fetch.add_argument("--cache", type=Path, default=ROOT / ".cache/dictionaries/cc-cedict")
    args = parser.parse_args()
    lexicon = validate(args.data, getattr(args, "snapshot", None))
    if args.command == "validate":
        result = {**summary(lexicon), "passed": True, "full_snapshot_checked": args.snapshot is not None,
                  "scope": "Structure, exact source linkage and approval metadata; not human language review"}
        if args.report:
            atomic_write(args.report, json_bytes(result))
    elif args.command == "build":
        result = export(lexicon, args.output, args.mode)
    elif args.command == "review":
        atomic_write(args.output, make_review(lexicon))
        result = {"review_page": str(args.output.resolve()), **summary(lexicon)}
    elif args.command == "import-review":
        updated = apply_review(lexicon, read_json(args.decisions))
        validate(lexicon.directory, data_override=updated)
        atomic_write(lexicon.directory / "entries.json", json_bytes(updated))
        result = summary(validate(lexicon.directory))
    else:
        result = fetch_source(lexicon, args.cache)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except (Invalid, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Lexicon preparation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
