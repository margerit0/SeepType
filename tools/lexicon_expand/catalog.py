"""Measure coverage without treating dictionary references as finished translations."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

from tools.lexicon import pipeline as legacy
from tools.lexicon_expand.common import (
    CACHE, DATA, ROOT, Invalid, canonical, digest, english, generated_directory,
    read_json, read_jsonl, require, word_key, write_json, write_jsonl,
)
from tools.lexicon_expand.sources import targets_from_sources


def input_reading(chinese, pinyin):
    if not chinese or not all("\u3400" <= char <= "\u9fff" or
                             "\U00020000" <= char <= "\U000323af" or char == "〇"
                             for char in chinese):
        return None
    syllables = pinyin.lower().replace("u:", "v").split()
    if not syllables or not all(re.fullmatch("[a-z]+[1-5]", part) for part in syllables):
        return None
    return " ".join(part[:-1] for part in syllables)


def reference_keys(gloss):
    """Only exact slash-delimited senses, with an explicit infinitive-prefix rule."""
    for segment in gloss.split("/"):
        key = word_key(segment)
        if key:
            yield key, segment, "exact-definition"
        if key.startswith("to ") and len(key) > 3:
            yield key[3:], segment, "definition-without-infinitive-to"


def dictionary_references(targets, lexicon):
    artifact = lexicon.lock["artifact"]
    path = ROOT / ".cache/dictionaries/cc-cedict" / (artifact["archive_sha256"] + ".txt")
    require(path.exists(), "Pinned CC-CEDICT snapshot missing; run tools/lexicon/pipeline.py fetch-source")
    raw = path.read_bytes()
    require(digest(raw) == artifact["text_sha256"], "CC-CEDICT snapshot hash mismatch")
    wanted = {target["english"] for target in targets}
    references = defaultdict(list)
    headwords, input_records = set(), set()
    count = 0
    for number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        count += 1
        source = legacy.parse_source(line)
        code = input_reading(source["chinese"], source["pinyin"])
        if code is not None:
            headwords.add(source["chinese"])
            input_records.add((source["chinese"], code))
        found = {}
        for key, segment, rule in reference_keys(source["gloss"]):
            if key in wanted and key not in found:
                found[key] = (segment, rule)
        for key, (segment, rule) in found.items():
            sha = digest(line.encode("utf-8"))
            references[key].append({
                "id": "cedict-" + sha[:20], "source_id": lexicon.lock["source_id"],
                "source_row": number, "source_row_sha256": sha,
                "source_text": line, "chinese": source["chinese"],
                "pinyin": source["pinyin"], "matched_definition": segment,
                "matching_rule": rule, "input_dictionary_reachable": code is not None,
                "license": lexicon.lock["license"],
            })
    require(count == lexicon.lock["entry_count"], "Unexpected CC-CEDICT record count")
    for values in references.values():
        values.sort(key=lambda value: (not value["input_dictionary_reachable"],
                                       len(value["chinese"]), value["source_row"]))
    return references, headwords, len(input_records)


def coverage_counts(targets):
    return {
        "targets": len(targets),
        "with_existing_draft": sum(any(e["review_status"] == "pending"
                                       for e in t["existing_entries"]) for t in targets),
        "with_approved_existing_entry": sum(any(e["review_status"] == "approved-for-distribution"
                                               and e["input_dictionary_reachable"]
                                               for e in t["existing_entries"]) for t in targets),
        "with_dictionary_reference": sum(t["dictionary_reference_count"] > 0 for t in targets),
        "without_dictionary_reference": sum(t["dictionary_reference_count"] == 0 for t in targets),
        "with_reachable_dictionary_reference": sum(t["reachable_reference_count"] > 0 for t in targets),
        "api_eligible": sum(t["api_eligible"] for t in targets),
    }


def coverage_markdown(summary):
    rows = ["# 英语词库扩充：离线覆盖报告", "",
            "本报告只统计来源词形和现有记录；没有调用模型，没有新增英文释义。", "",
            "IELTS 范围为固定 ECDICT 快照的 ielts 标签清单，不代表官方或全部雅思词汇。", "",
            "| 范围 | 目标词形 | 已有审核稿 | 已人工通过且可输入 | CC-CEDICT 参考命中 | 参考未命中 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for pack, label in (("ielts", "IELTS"), ("cefr", "CEFR A1–C2"), ("all", "去重合计")):
        counts = summary["coverage"][pack]
        rows.append(f"| {label} | {counts['targets']} | {counts['with_existing_draft']} | "
                    f"{counts['with_approved_existing_entry']} | {counts['with_dictionary_reference']} | "
                    f"{counts['without_dictionary_reference']} |")
    rows += ["", "参考命中只表示词典里存在相同英文义项，不能代替词义选择、模型生成或人工审核。",
             "参考未命中可能由复合释义、词形或短语差异造成，不等于词典完全没有这个词。", "",
             "中文可输入性依据现有 CC-CEDICT 中文基础的字形与读音过滤规则计算；未操作已安装输入法。", "",
             f"现有中文基础：{summary['chinese_dictionary']['records']} 个词形/读音记录，"
             f"{summary['chinese_dictionary']['headwords']} 个不同词形。", "",
             "## 场景范围", "",
             "以下只有主题配置；具体英语词汇和短语等待外部 API 生成，尚无场景覆盖率。", ""]
    rows += [f"- {scene['name']}：{scene['scope']}" for scene in summary["scenarios"]]
    return "\n".join(rows) + "\n"


def prepare(output=CACHE / "prepared", data=DATA):
    output = generated_directory(output)
    targets, source_lock = targets_from_sources(data)
    lexicon = legacy.validate()
    references, headwords, input_record_count = dictionary_references(targets, lexicon)
    existing = defaultdict(list)
    for entry in lexicon.entries:
        existing[word_key(entry["commit_english"])].append({
            "id": entry["id"], "chinese": entry["chinese"],
            "english": entry["commit_english"], "review_status": entry["review"]["status"],
            "input_dictionary_reachable": entry["chinese"] in headwords,
        })
    for target in targets:
        values = references[target["english"]]
        target["dictionary_reference_count"] = len(values)
        target["reachable_reference_count"] = sum(v["input_dictionary_reachable"] for v in values)
        target["dictionary_references"] = values[:8]
        target["existing_entries"] = existing[target["english"]]
        try:
            english(target["english"])
            target["api_eligible"] = True
        except Invalid:
            target["api_eligible"] = False
    scenarios = read_json(Path(data) / "scenarios.json")["scenarios"]
    require(len({scene["id"] for scene in scenarios}) == len(scenarios), "Duplicate scenario ID")
    require(all(re.fullmatch("[a-z][a-z-]+", scene["id"]) for scene in scenarios), "Invalid scenario ID")
    summary = {
        "schema_version": 2, "status": "offline-targets-only", "model_requests": 0,
        "generated_translations": 0, "human_approved_new_entries": 0,
        "coverage": {pack: coverage_counts(targets if pack == "all" else
                                           [t for t in targets if pack in t["packs"]])
                     for pack in ("ielts", "cefr", "all")},
        "existing_lexicon": {"id": lexicon.data["id"], "review_counts": lexicon.counts},
        "chinese_dictionary": {"records": input_record_count, "headwords": len(headwords),
                               "source_sha256": lexicon.lock["artifact"]["text_sha256"]},
        "scenarios": scenarios,
        "limits": ["Exact headword/sense matching is a reference lookup, not translation verification",
                   "CEFR labels are source annotations, not inferred IELTS membership",
                   "Scenario English word lists have not been generated",
                   "No new runtime dictionary or installed product was changed"],
    }
    write_jsonl(output / "targets.jsonl", targets)
    write_json(output / "coverage.json", summary)
    legacy.atomic_write(output / "coverage.md", coverage_markdown(summary).encode("utf-8"))
    source_files = [Path(data) / "sources.lock.json", Path(data) / "scenarios.json",
                    legacy.DATA / "entries.json", legacy.DATA / "source.lock.json"]
    source_files += [ROOT / source["local_file"] for source in source_lock["sources"]]
    source_files += [ROOT / notice["local_file"] for notice in source_lock["notices"]]
    source_files += [Path(__file__), Path(__file__).with_name("sources.py"),
                     Path(__file__).with_name("common.py")]
    manifest = {
        "schema_version": 2,
        "inputs": {path.relative_to(ROOT).as_posix(): digest(path.read_bytes())
                   for path in sorted(source_files)},
        "files": {name: digest((output / name).read_bytes())
                  for name in ("targets.jsonl", "coverage.json", "coverage.md")},
    }
    write_json(output / "manifest.json", manifest)
    return summary


def load_prepared(directory=CACHE / "prepared"):
    directory = generated_directory(directory)
    manifest = read_json(directory / "manifest.json")
    require(manifest["schema_version"] == 2, "Unknown prepared catalog version")
    for name, expected in manifest["inputs"].items():
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT.resolve()), "Catalog input path escapes workspace")
        require(digest(path.read_bytes()) == expected, "Inputs changed; rerun prepare")
    require(set(manifest["files"]) == {"targets.jsonl", "coverage.json", "coverage.md"},
            "Unexpected prepared catalog artifacts")
    for name, expected in manifest["files"].items():
        require(digest((directory / name).read_bytes()) == expected, "Prepared catalog checksum mismatch")
    return read_jsonl(directory / "targets.jsonl"), read_json(directory / "coverage.json"), manifest
