"""Validate external model output and attach pending-review provenance ourselves."""
from __future__ import annotations

import json
import re

from tools.lexicon.pipeline import unique_keys
from tools.lexicon_expand.common import canonical, clean_text, digest, english, require, word_key

PARTS_OF_SPEECH = {"n", "v", "adj", "adv", "pron", "prep", "conj", "num", "det", "interj", "phrase"}


def validate_reply(content, job, generation):
    require(isinstance(content, str), "Provider returned non-text content")
    require(len(content.encode("utf-8")) <= 2 * 1024 * 1024, "Oversized model content")
    reply = json.loads(content, object_pairs_hook=unique_keys)
    require(isinstance(reply, dict) and set(reply) == {"results"}, "Expected only a results array")
    require(isinstance(reply["results"], list), "results must be an array")
    expected = {target["target_id"]: target for target in job["payload"]["targets"]}
    require(len(reply["results"]) == len(expected), "Model omitted or added targets")
    seen, scene_words, records = set(), set(), []
    for result in reply["results"]:
        require(isinstance(result, dict) and set(result) == {
            "target_id", "english", "senses", "unresolved_reason"}, "Unexpected result fields")
        target_id = result["target_id"]
        require(isinstance(target_id, str) and target_id in expected and target_id not in seen,
                "Unknown or repeated target ID")
        seen.add(target_id)
        target = expected[target_id]
        value = result["english"]
        senses = result["senses"]
        require(isinstance(senses, list) and len(senses) <= 3, "Expected up to three senses")
        if job["task"] == "map_targets":
            english(value)
            require(word_key(value) == word_key(target["english"]), "Model substituted a target word")
        elif value is not None:
            english(value)
        if senses:
            require(value is not None and result["unresolved_reason"] is None,
                    "Resolved item must contain English and no unresolved reason")
            if job["task"] == "scene_terms":
                require(word_key(value) not in scene_words, "Repeated English term within a scene request")
                scene_words.add(word_key(value))
        else:
            clean_text(result["unresolved_reason"], "unresolved reason", 800)
        references = {reference["id"]: reference for reference in target["dictionary_references"]}
        normalized, sense_keys, used_refs = [], set(), set()
        for sense in senses:
            require(isinstance(sense, dict) and set(sense) == {
                "chinese", "pinyin", "pos", "meaning_zh", "source_ref_ids"}, "Unexpected sense fields")
            chinese = clean_text(sense["chinese"], "Chinese trigger", 64)
            require(re.fullmatch(r"[\u3400-\u9fff]{1,16}", chinese) is not None,
                    "Chinese trigger must contain 1 to 16 Han characters")
            pinyin = clean_text(sense["pinyin"], "pinyin", 128)
            syllables = pinyin.split(" ")
            require(len(syllables) == len(chinese) and all(
                re.fullmatch("[a-z]+[1-5]", syllable) for syllable in syllables),
                "Pinyin must have one numbered syllable per Han character")
            require(sense["pos"] in PARTS_OF_SPEECH, "Unknown part of speech")
            meaning = clean_text(sense["meaning_zh"], "sense note", 600)
            require(any("\u3400" <= char <= "\u9fff" for char in meaning), "Sense note must include Chinese")
            refs = sense["source_ref_ids"]
            require(isinstance(refs, list) and all(isinstance(item, str) for item in refs),
                    "Source reference IDs must be strings")
            require(len(refs) == len(set(refs)) and set(refs).issubset(references),
                    "Unknown or repeated dictionary reference")
            key = (chinese, pinyin, sense["pos"], meaning)
            require(key not in sense_keys, "Repeated sense")
            sense_keys.add(key)
            used_refs.update(refs)
            normalized.append({
                "id": "sense-" + digest(canonical([target_id, *key]))[:20],
                "chinese": chinese, "pinyin": pinyin, "pos": sense["pos"],
                "display_english": value, "commit_english": value, "meaning_zh": meaning,
                "source_ref_ids": refs,
                "trigger_matches_supplied_reference": any(references[ref]["chinese"] == chinese
                                                          for ref in refs),
            })
        record = {
            "schema_version": 2, "id": target_id, "english": value,
            "packs": target["packs"], "cefr_levels": target.get("cefr_levels", []),
            "senses": normalized, "selected_sense_id": None,
            "unresolved_reason": result["unresolved_reason"],
            "source_refs": target["source_refs"],
            "dictionary_references": [references[ref] for ref in sorted(used_refs)],
            "generation": generation,
            "review": {"status": "pending", "method": None, "reviewer": None,
                       "reviewed_at": None, "content_sha256": None},
            "release_ready": False,
        }
        records.append(record)
    require(seen == set(expected), "Incomplete model response")
    return sorted(records, key=lambda record: record["id"])
