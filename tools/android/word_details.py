"""Build reading-specific detail assets without changing the Rime lexicon."""
import hashlib
import json
import re
import unicodedata


POS_LABELS = {
    "adj": "形容词", "adv": "副词", "conj": "连词", "det": "限定词", "interj": "感叹词",
    "n": "名词", "num": "数词", "phrase": "短语", "prep": "介词", "pron": "代词", "v": "动词",
}
ASSET_PREFIX = "word-details-v1/"


def _pinyin(numbered_readings):
    # Rime's phrase code is toneless. Don't pick a tone where the snapshot
    # itself has multiple numbered readings for the same code.
    if len(numbered_readings) != 1:
        return ""
    result = []
    for syllable in numbered_readings[0].split():
        text, tone = syllable[:-1].replace("u:", "ü").replace("v", "ü"), syllable[-1]
        if tone in "1234":
            index = next((text.index(v) for v in ("a", "e", "ou") if v in text), None)
            if index is None:
                index = max((i for i, c in enumerate(text) if c in "aeiouü"), default=len(text) - 1)
            mark = "\u0304\u0301\u030c\u0300"[int(tone) - 1]
            text = unicodedata.normalize("NFC", text[:index+1] + mark + text[index+1:])
        if result and syllable[0] in "aoe":
            result.append("'")
        result.append(text)
    return "".join(result)


def snapshot_rows(runtime, triggers, accepted):
    """Use the verified trigger-to-sense relation, not grouping by word alone."""
    entries = runtime["entries"]
    metadata = {row["id"]: row for row in accepted}
    covered = set()
    rows = []
    for trigger in sorted(triggers, key=lambda row: (row["chinese"], row["code"])):
        word, reading = trigger["chinese"], trigger["code"]
        entry = entries[word]
        default = entry["primary_by_reading"][reading] if entry["requires_reading"] else entry["primary_sense_id"]
        ids = trigger["sense_ids"]
        valid = {sense["id"]: sense for sense in entry["senses"]}
        if (word, reading) in covered or default not in ids or len(ids) != len(set(ids)):
            raise ValueError(f"Inconsistent detail trigger: {word}/{reading}")
        covered.add((word, reading))
        senses = []
        for sense_id in [default, *(i for i in ids if i != default)]:
            english = valid[sense_id]["commit_english"]
            if english != valid[sense_id]["display_english"]:
                raise ValueError(f"Inconsistent English text: {sense_id}")
            sense = {"id": sense_id, "english": english}
            source = metadata.get(sense_id)
            if source is not None:
                if source["chinese"] != word or source["commit_english"] != english:
                    raise ValueError(f"Inconsistent sense metadata: {sense_id}")
                sense.update(pos=POS_LABELS[source["pos"]], usage=source["meaning_zh"])
            elif not sense_id.startswith("legacy-"):
                raise ValueError(f"Missing sense metadata: {sense_id}")
            senses.append(sense)
        row = {"chinese": word, "reading": reading, "senses": senses}
        if pinyin := _pinyin(trigger["numbered_readings"]):
            row["pinyin"] = pinyin
        rows.append(row)
    return b"".join(_json(row) + b"\n" for row in rows)


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def pack_details(snapshot, examples):
    """Each lookup reads one small APK asset; no data is enrolled in Rime."""
    authored = {}
    for example in json.loads(examples):
        sense_id = example["id"]
        if sense_id in authored:
            raise ValueError(f"Duplicate example: {sense_id}")
        authored[sense_id] = example
    matched = set()
    shards = {}
    for line in snapshot.splitlines():
        row = json.loads(line)
        word, reading = row.pop("chinese"), row.pop("reading")
        bucket = hashlib.sha256(word.encode("utf-8")).digest()[0] & 0x7f
        readings = shards.setdefault(bucket, {}).setdefault(word, {})
        if reading in readings:
            raise ValueError(f"Duplicate detail lookup key: {word}/{reading}")
        readings[reading] = row
        for sense in row["senses"]:
            sense_id = sense["id"]
            if sense_id not in authored:
                continue
            example = authored[sense_id]
            if (word, reading, sense["english"]) != (example["chinese"], example["reading"], example["english"]):
                raise ValueError(f"Example no longer matches its sense: {sense_id}")
            for key in ("collocation", "exampleEn", "exampleZh") + (("usage",) if "usage" in example else ()):
                value = example[key]
                if not value.strip() or len(value) > 200 or any(ord(c) < 32 for c in value):
                    raise ValueError(f"Invalid {key}: {sense_id}")
                sense[key] = value
            if "pos" in example:
                sense["pos"] = POS_LABELS[example["pos"]]
            if not re.search(r"(?<!\w)" + re.escape(sense["english"]) + r"(?!\w)", sense["exampleEn"], re.I):
                raise ValueError(f"Example should contain the target English form: {sense_id}")
            matched.add(sense_id)
    if missing := authored.keys() - matched:
        raise ValueError(f"Examples have no runtime sense: {sorted(missing)}")
    return {f"{ASSET_PREFIX}{bucket:02x}.json": _json(rows) for bucket, rows in sorted(shards.items())}
