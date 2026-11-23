"""Validate external model output and attach pending-review provenance ourselves."""
from __future__ import annotations

import json
import re

from tools.lexicon_expand.normalization import ResponseValidationError, unique_keys
from tools.lexicon_expand.common import canonical, clean_text, digest, english, require, word_key

PARTS_OF_SPEECH = {"n", "v", "adj", "adv", "pron", "prep", "conj", "num", "det", "interj", "phrase"}


def validate_reply(content, job, generation):
    position = {'path': '$'}
    try:
        return _validate_reply(content, job, generation, position)
    except ResponseValidationError:
        raise
    except json.JSONDecodeError as error:
        raise ResponseValidationError('Invalid JSON response',
                                      f'$ (line {error.lineno}, column {error.colno})') from None
    except (ValueError, TypeError, KeyError) as error:
        # Only our fixed validation messages may reach receipts, never model text.
        from tools.lexicon_expand.common import Invalid
        message = str(error) if isinstance(error, Invalid) else 'Invalid response field type'
        raise ResponseValidationError(message, position['path']) from None


def _validate_reply(content, job, generation, position):
    version = job['payload'].get('response_schema_version', 2)
    require(version in (2, 3), 'Unknown response schema version')
    require(job['task'] in ('map_targets', 'scene_terms', 'repair_senses'), 'Unknown response task')
    require(job['task'] != 'repair_senses' or version == 3, 'Repair task requires response version 3')
    if version == 3:
        from tools.lexicon_expand.quality import check_sense, policy
        selected_policy = job['payload'].get('quality_policy', {})
        require(selected_policy == policy(selected_policy.get('version')), 'Quality policy changed')
    require(isinstance(content, str), "Provider returned non-text content")
    require(len(content.encode("utf-8")) <= 2 * 1024 * 1024, "Oversized model content")
    reply = json.loads(content, object_pairs_hook=unique_keys)
    require(isinstance(reply, dict) and set(reply) == {"results"}, "Expected only a results array")
    require(isinstance(reply["results"], list), "results must be an array")
    expected = {target["target_id"]: target for target in job["payload"]["targets"]}
    require(len(reply["results"]) == len(expected), "Model omitted or added targets")
    seen, scene_words, records = set(), set(), []
    for result_index, result in enumerate(reply["results"]):
        position["path"] = f"$.results[{result_index}]"
        require(isinstance(result, dict) and set(result) == {
            "target_id", "english", "senses", "unresolved_reason"}, "Unexpected result fields")
        target_id = result["target_id"]
        require(isinstance(target_id, str) and target_id in expected and target_id not in seen,
                "Unknown or repeated target ID")
        seen.add(target_id)
        target = expected[target_id]
        position["path"] = f"$.results[{result_index}].english"
        value = result["english"]
        senses = result["senses"]
        position["path"] = f"$.results[{result_index}].senses"
        limit = 1 if job['task'] == 'repair_senses' else 3
        require(isinstance(senses, list) and len(senses) <= limit, "Too many senses for task")
        position["path"] = f"$.results[{result_index}].english"
        if job["task"] in ("map_targets", "repair_senses"):
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
            position["path"] = f"$.results[{result_index}].unresolved_reason"
            clean_text(result["unresolved_reason"], "unresolved reason", 800)
        references = {reference["id"]: reference for reference in target["dictionary_references"]}
        normalized, sense_keys, used_refs = [], set(), set()
        for sense_index, sense in enumerate(senses):
            base_path = f"$.results[{result_index}].senses[{sense_index}]"
            position["path"] = base_path
            fields = {"chinese", "pinyin", "pos", "meaning_zh", "source_ref_ids"}
            if version == 3:
                fields.add('english')
            require(isinstance(sense, dict) and set(sense) == fields, "Unexpected sense fields")
            sense_english = sense['english'] if version == 3 else value
            if version == 3:
                position['path'] = base_path + '.english'
                english(sense_english)
                require(word_key(sense_english) == word_key(value), 'Sense substituted the target word')
            position["path"] = base_path + ".chinese"
            chinese = clean_text(sense["chinese"], "Chinese trigger", 64)
            require(re.fullmatch(r"[\u3400-\u9fff]{1,16}", chinese) is not None,
                    "Chinese trigger must contain 1 to 16 Han characters")
            position["path"] = base_path + ".pinyin"
            pinyin = clean_text(sense["pinyin"], "pinyin", 128)
            syllables = pinyin.split(" ")
            if version == 2:
                require(len(syllables) == len(chinese) and all(
                    re.fullmatch("[a-z]+[1-5]", syllable) for syllable in syllables),
                    "Pinyin must have one numbered syllable per Han character")
            position["path"] = base_path + ".pos"
            require(isinstance(sense["pos"], str) and sense["pos"] in PARTS_OF_SPEECH, "Unknown part of speech")
            position["path"] = base_path + ".meaning_zh"
            meaning = clean_text(sense["meaning_zh"], "sense note", 600)
            require(any("\u3400" <= char <= "\u9fff" for char in meaning), "Sense note must include Chinese")
            position["path"] = base_path + ".source_ref_ids"
            refs = sense["source_ref_ids"]
            require(isinstance(refs, list) and all(isinstance(item, str) for item in refs),
                    "Source reference IDs must be strings")
            require(len(refs) == len(set(refs)) and set(refs).issubset(references),
                    "Unknown or repeated dictionary reference")
            key = (chinese, pinyin, sense["pos"], meaning)
            if version == 3:
                key += (sense_english,)
            require(key not in sense_keys, "Repeated sense")
            sense_keys.add(key)
            used_refs.update(refs)
            normalized.append({
                "id": "sense-" + digest(canonical([target_id, *key]))[:20],
                "chinese": chinese, "pinyin": pinyin, "pos": sense["pos"],
                "display_english": sense_english, "commit_english": sense_english, "meaning_zh": meaning,
                "source_ref_ids": refs,
                "trigger_matches_supplied_reference": any(references[ref]["chinese"] == chinese
                                                          for ref in refs),
            })
            if version == 3:
                normalized[-1]['quality'] = check_sense(normalized[-1], target,
                                                       version=selected_policy['version'])
        record = {
            "schema_version": version, "id": target_id, "english": value,
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
        if version == 3:
            record['lookup_key'] = word_key(value) if value is not None else None
            if job['task'] == 'repair_senses':
                record['repair_of'] = {'target_id': target['original_target_id'],
                                       'sense_id': target['original_sense']['id'],
                                       'source_record_sha256': target['source_record_sha256']}
        records.append(record)
    require(seen == set(expected), "Incomplete model response")
    return sorted(records, key=lambda record: record["id"])
