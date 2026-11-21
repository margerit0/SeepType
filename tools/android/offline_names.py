# SPDX-License-Identifier: GPL-3.0-or-later
"""Package a vetted Android-only name list without consulting a network source."""
from __future__ import annotations

from collections import defaultdict
import csv
import hashlib
import io
import json
import re
from urllib.parse import urlsplit

from tools.android.common import ROOT

SOURCE = ROOT / "data/lexicon-expansion/android-names"
FIELDS = ("zh", "pinyin", "kind", "work", "work_qid", "qid", "revision", "label_lang", "review", "english", "english_source")
NAME_WEIGHT = 1
QID = re.compile(r"Q[1-9][0-9]*")
HAN_NAME = re.compile(r"[\u3400-\u9fff\U00020000-\U000323af]{2,20}")


def json_bytes(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def load_names(base_dictionary):
    raw = (SOURCE / "names.tsv").read_bytes()
    source_record = (SOURCE / "sources.json").read_bytes()
    source = json.loads(source_record)
    if source["source"] != "Wikidata" or source["license"] != "CC0-1.0" or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", source["collectedOn"]):
        raise ValueError("Expected a dated Wikidata source record under CC0")
    sha256 = hashlib.sha256(raw).hexdigest()
    by_reading = defaultdict(set)
    _, separator, dictionary_rows = base_dictionary.decode("utf-8").partition("\n...\n")
    if not separator:
        raise ValueError("Missing Windows dictionary header boundary")
    syllables = set()
    for line in dictionary_rows.splitlines():
        if not line or line.startswith("#"):
            continue
        zh, reading, *_ = line.split("\t")
        by_reading[reading].add(zh)
        syllables.update(reading.split(" "))
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")), delimiter="\t", quoting=csv.QUOTE_NONE)
    if tuple(reader.fieldnames or ()) != FIELDS:
        raise ValueError(f"Invalid offline name columns: expected {FIELDS}")
    names = set()
    entries = defaultdict(set)
    english = defaultdict(list)
    duplicates = []
    for row in reader:
        line = reader.line_num
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f"Wrong number of columns in names.tsv:{line}")
        zh, reading = row["zh"], row["pinyin"]
        code = reading.split(" ")
        if (not HAN_NAME.fullmatch(zh) or len(zh) != len(code) or
                any(not re.fullmatch(r"[a-z]+", part) or part not in syllables for part in code)):
            raise ValueError(f"Invalid name or split Mandarin reading in names.tsv:{line}: {zh} / {reading}")
        kind = row["kind"]
        if (kind not in ("film", "series", "game", "character") or not row["work"].strip() or
                not all(QID.fullmatch(row[key]) for key in ("qid", "work_qid")) or
                (kind == "character") == (row["qid"] == row["work_qid"]) or
                not re.fullmatch(r"[1-9][0-9]{0,11}", row["revision"]) or
                row["label_lang"].removeprefix("alias:") not in ("zh-cn", "zh-hans", "zh") or row["review"] != "dev-checked"):
            raise ValueError(f"Invalid review or Wikidata provenance in names.tsv:{line}")
        en, reference = row["english"], row["english_source"]
        parsed = urlsplit(reference)
        if bool(en) != bool(reference) or (en and (en != en.strip() or not all(" " <= char <= "~" for char in en)
                or len(en) > 128 or parsed.scheme != "https" or not parsed.hostname or parsed.username)):
            raise ValueError(f"English requires a separately checked HTTPS source in names.tsv:{line}")
        key = (zh, reading)
        if key in names:
            raise ValueError(f"Duplicate name and reading in names.tsv:{line}: {zh} / {reading}")
        names.add(key)
        if zh in by_reading.get(reading, ()):
            duplicates.append({"zh": zh, "pinyin": reading})
            continue
        entries[reading].add(zh)
        if en:
            english[zh].append((reading, en))
    if not entries:
        raise ValueError("No new offline names to package")

    homophones = [{"pinyin": code, "names": sorted(added), "base": sorted(by_reading.get(code, ()))}
                 for code, added in sorted(entries.items()) if len(added) > 1 or by_reading.get(code)]
    summary = {"source": source["source"], "collectedOn": source["collectedOn"], "license": source["license"],
               "tsvSha256": sha256, "entries": sum(map(len, entries.values())), "alreadyInBase": len(duplicates),
               "sharedReadings": len(homophones), "verifiedEnglishRows": sum(map(len, english.values()))}
    rows = ((reading, zh) for reading in sorted(entries) for zh in sorted(entries[reading]))
    dictionary = ("# Android offline names; provenance in notices/android-names/\n"
                  f"---\nname: study_offline_names\nversion: '{sha256[:20]}'\nsort: by_weight\n...\n"
                  + "".join(f"{zh}\t{reading}\t{NAME_WEIGHT}\n" for reading, zh in rows)).encode("utf-8")
    payload = {"rime/study_offline_names.dict.yaml": dictionary,
               "rime/lua/study_offline_names_en.lua": english_table(english),
               "notices/android-names/names.tsv": raw,
               "notices/android-names/sources.json": source_record,
               "notices/android-names/collisions.json": json_bytes({"alreadyInBase": duplicates, "sharedReadings": homophones})}
    return payload, summary


def english_table(english):
    """Emit the review schema of study_core.lua; keep English scoped to its pronunciation."""
    def quote(value):
        return json.dumps(value, ensure_ascii=False)

    result = ["-- Generated Android-only English names with separate source checks.\nreturn {\n"]
    for zh, translations in sorted(english.items()):
        result.append(f"  [{quote(zh)}] = {{requires_reading = true, primary_sense_id = 'name1',\n    primary_by_reading = {{")
        for i, (reading, _) in enumerate(translations, 1):
            result.append(f"[{quote(reading)}] = 'name{i}', ")
        result.append("},\n    senses = {\n")
        for i, (_, en) in enumerate(translations, 1):
            result.append(f"      {{id = 'name{i}', display_english = {quote(en)}, commit_english = {quote(en)}}},\n")
        result.append("    }},\n")
    result.append("}\n")
    return "".join(result).encode("utf-8")
