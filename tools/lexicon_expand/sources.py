"""Read pinned word lists. Never import ECDICT translations or invent entries."""
from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from urllib.request import Request, urlopen

from tools.lexicon_expand.common import (
    DATA, ROOT, Invalid, canonical, digest, read_json, read_jsonl,
    require, word_key,
)
from tools.lexicon.pipeline import atomic_write

LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


def project_ecdict(raw):
    """Keep spelling, exam membership and ranks; hash the original logical row."""
    reader = csv.DictReader(StringIO(raw.decode("utf-8-sig")))
    require({"word", "tag", "bnc", "frq"}.issubset(reader.fieldnames or []),
            "Unexpected ECDICT columns")
    rows = []
    for row_number, row in enumerate(reader, 1):
        require(None not in row and all(value is not None for value in row.values()),
                "Malformed ECDICT row")
        if "ielts" not in row["tag"].split():
            continue
        ranks = {}
        for field in ("bnc", "frq"):
            ranks[field] = int(row[field]) if row[field] else 0
            require(ranks[field] >= 0, "Negative frequency rank")
        rows.append({"word": row["word"], "tags": row["tag"].split(), **ranks,
                     "source_row": row_number, "source_row_sha256": digest(canonical(row))})
    require(bool(rows), "No IELTS-tagged rows found")
    return rows


def local_file(relative):
    path = (ROOT / relative).resolve()
    require(path.is_relative_to(ROOT.resolve()), "Source path escapes workspace")
    return path


def verify_sources(data=DATA, full=False):
    lock = read_json(Path(data) / "sources.lock.json")
    require(lock["schema_version"] == 1, "Unknown source lock version")
    ids = set()
    for source in lock["sources"]:
        require(source["id"] not in ids, "Duplicate source ID")
        ids.add(source["id"])
        local = local_file(source["local_file"]).read_bytes()
        require(digest(local) == source["local_sha256"],
                f"Changed source excerpt: {source['id']}")
        if full:
            raw = local_file(source["cache_file"]).read_bytes()
            require(len(raw) == source["bytes"] and digest(raw) == source["sha256"],
                    f"Changed upstream snapshot: {source['id']}")
            if source["format"] == "ecdict-ielts-facts-v1":
                projected = b"".join(canonical(row) + b"\n" for row in project_ecdict(raw))
                require(projected == local, "ECDICT excerpt no longer matches its source")
            else:
                require(raw == local, "Profile snapshot differs from upstream bytes")
    for notice in lock["notices"]:
        require(digest(local_file(notice["local_file"]).read_bytes()) == notice["sha256"],
                "Changed source notice")
    return lock


def fetch_sources(data=DATA):
    """Restore exactly the recorded public snapshots; never advance a revision."""
    lock = verify_sources(data)
    result = []
    for source in lock["sources"]:
        path = local_file(source["cache_file"])
        if path.exists():
            raw = path.read_bytes()
        else:
            request = Request(source["url"], headers={"User-Agent": "StudyIME-lexicon-expansion/0.1"})
            with urlopen(request, timeout=45) as response:
                require(response.url.startswith("https://"), "Source must remain on HTTPS")
                raw = response.read(source["bytes"] + 1)
        require(len(raw) == source["bytes"] and digest(raw) == source["sha256"],
                f"Snapshot mismatch: {source['id']}")
        atomic_write(path, raw)
        result.append({"id": source["id"], "bytes": len(raw), "verified": True})
    verify_sources(data, full=True)
    return result


def targets_from_sources(data=DATA):
    lock = verify_sources(data)
    targets = {}

    def add(word, pack, reference, pos=None, level=None, rank=None):
        key = word_key(word)
        require(bool(key) and len(key.encode("utf-8")) <= 128, "Invalid source headword")
        target = targets.setdefault(key, {"id": "en-" + digest(key.encode())[:20],
                                          "english": key, "source_forms": set(), "packs": set(),
                                          "parts_of_speech": set(), "cefr_levels": set(),
                                          "frequency_rank": None, "source_refs": []})
        target["source_forms"].add(word)
        target["packs"].add(pack)
        if pos:
            target["parts_of_speech"].add(pos)
        if level:
            require(level in LEVELS, "Unknown CEFR level")
            target["cefr_levels"].add(level)
        if rank and (target["frequency_rank"] is None or rank < target["frequency_rank"]):
            target["frequency_rank"] = rank
        if reference not in target["source_refs"]:
            target["source_refs"].append(reference)

    for source in lock["sources"]:
        path = local_file(source["local_file"])
        if source["format"] == "ecdict-ielts-facts-v1":
            rows = read_jsonl(path)
            require(len(rows) == source["selected_rows"], "IELTS excerpt count changed")
            for row in rows:
                require("ielts" in row["tags"], "Non-IELTS row in excerpt")
                ranks = [row[field] for field in ("bnc", "frq") if row[field] > 0]
                add(row["word"], "ielts", {"source_id": source["id"], "row": row["source_row"],
                                           "row_sha256": row["source_row_sha256"]},
                    rank=min(ranks) if ranks else None)
        else:
            rows = list(csv.DictReader(StringIO(path.read_text(encoding="utf-8-sig"))))
            require(len(rows) == source["selected_rows"], "CEFR profile count changed")
            for number, row in enumerate(rows, 1):
                for form in row["headword"].split("/"):
                    add(form.strip(), "cefr", {"source_id": source["id"], "row": number,
                                               "row_sha256": digest(canonical(row))},
                        pos=row["pos"], level=row["CEFR"])
    result = []
    for key, target in sorted(targets.items()):
        for field in ("source_forms", "packs", "parts_of_speech", "cefr_levels"):
            target[field] = sorted(target[field])
        target["source_refs"].sort(key=lambda reference: (reference["source_id"], reference["row"]))
        result.append(target)
    require(len({target["id"] for target in result}) == len(result), "Target ID collision")
    return result, lock
