"""Build the sourced StudyIME Chinese base and its recorded comparison variants.

This transforms only Chinese headwords and Mandarin readings from the fixed
CC-CEDICT snapshot. The separate 200-entry English review batch is never edited.
The product uses wordfreq plus Unihan shares for polyphonic single characters.
Uniform and character-only weights remain comparison modes.
"""
from collections import Counter
import argparse
import json
import math
from pathlib import Path
import re
import sys
import unicodedata
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, file_hash, json_bytes, sha256, write_changed
from tools.lexicon.pipeline import parse_source


def unihan_readings():
    source = json.loads((ROOT / "data/chinese/sources.lock.json").read_bytes())["unicode"]
    archive = ROOT / source["archive"]
    if file_hash(archive) != source["archive_sha256"] or file_hash(ROOT / source["license_file"]) != source["license_sha256"]:
        raise ValueError("Fixed Unicode data or notice changed")
    with zipfile.ZipFile(archive) as bundle:
        raw = bundle.read(source["source_file"])
    if sha256(raw) != source["source_sha256"]: raise ValueError("Unihan reading data changed")
    readings, count = Counter(), 0
    for line in raw.decode("utf-8").splitlines():
        if "\tkHanyuPinlu\t" not in line: continue
        codepoint, property_name, value = line.split("\t")
        count += 1
        character = chr(int(codepoint[2:], 16))
        for reading, frequency in re.findall(r"([^ ()]+)\((\d+)\)", value):
            code = []
            for char in unicodedata.normalize("NFD", reading):
                if char == "\u0308" and code and code[-1] == "u": code[-1] = "v"
                elif not unicodedata.combining(char): code.append(char)
            normalized = "".join(code)
            if not re.fullmatch("[a-z]+", normalized): raise ValueError("Unsupported Unihan reading")
            readings[(character, normalized)] += int(frequency)
    if count != source["records"]: raise ValueError("Unexpected Unihan frequency record count")
    return readings, source


def geometric_mean(values):
    product = math.prod(values)
    if len(values) == 1: return values[0]
    if len(values) == 2: return math.isqrt(product)
    low, high = 1, max(values) + 1
    while high - low > 1:
        middle = (low + high) // 2
        if middle ** len(values) <= product: low = middle
        else: high = middle
    return low


def files(weighting="wordfreq", *, comparison=False):
    if weighting not in ["uniform", "unicode", "wordfreq"]: raise ValueError("Unknown ranking experiment")
    lock = json.loads((ROOT / "data/lexicon/source.lock.json").read_bytes())
    text_path = ROOT / ".cache/dictionaries/cc-cedict" / (lock["artifact"]["archive_sha256"] + ".txt")
    raw = text_path.read_bytes()
    if sha256(raw) != lock["artifact"]["text_sha256"]:
        raise ValueError("The full fixed CC-CEDICT snapshot changed")
    entries, simplified, accepted_sources, rejected, count = {}, {}, 0, Counter(), 0
    for line in raw.decode("utf-8-sig").splitlines():
        if not line or line.startswith("#"): continue
        count += 1
        source = parse_source(line)
        word = source["chinese"]
        # Keep complete Han headwords; ASCII abbreviations and mixed scripts
        # require their own input conventions and are outside this experiment.
        if not all("\u3400" <= c <= "\u9fff" or "\U00020000" <= c <= "\U000323af" or c == "〇" for c in word):
            rejected["mixed-script-or-punctuated-headword"] += 1
            continue
        syllables = source["pinyin"].lower().replace("u:", "v").split()
        if not syllables or not all(re.fullmatch("[a-z]+[1-5]", syllable) for syllable in syllables):
            rejected["nonstandard-mandarin-reading"] += 1
            continue
        code = " ".join(syllable[:-1] for syllable in syllables)
        entries.setdefault((word, code), []).append(sha256(line.encode("utf-8")))
        simplified.setdefault((word, code), set()).add(source["chinese"])
        accepted_sources += 1
    if count != lock["entry_count"] or not entries:
        raise ValueError("Unexpected CC-CEDICT source entry count")
    weights, frequency_source, pronunciation_source = {}, None, None
    polyphonic = {}
    if weighting == "wordfreq":
        from tools.dictionary.wordfreq import frequencies
        vocabulary, frequency_source = frequencies()
        readings, pronunciation_source = unihan_readings()
        for word, code in entries:
            if len(word) == 1: polyphonic.setdefault(word, set()).add(code)
        polyphonic = {word: codes for word, codes in polyphonic.items() if len(codes) > 1}
        for key in entries:
            word, code = key
            weight = vocabulary.get(word, 1)
            if word in polyphonic:
                shares = {reading: max(1, readings[(word, reading)]) for reading in polyphonic[word]}
                weight = max(1, weight * shares[code] // sum(shares.values()))
            weights[key] = weight
    if weighting == "unicode":
        readings, frequency_source = unihan_readings()
        words = {word for forms in simplified.values() for word in forms}
        compounds = Counter()
        for word in sorted(words):
            for length in range(2, min(len(word), 9)):
                for start in range(len(word) - length + 1):
                    part = word[start:start + length]
                    if part in words: compounds[part] += 1
        for key, forms in simplified.items():
            codes = key[1].split()
            candidates = []
            for word in forms:
                if len(word) != len(codes):
                    candidates.append(1)
                    continue
                frequencies = [max(1, readings[(character, code)]) for character, code in zip(word, codes)]
                weight = geometric_mean(frequencies)
                # A deterministic vocabulary prior, not a measured word count.
                if len(word) > 1: weight *= 1 + min(compounds[word], 50)
                candidates.append(max(1, weight))
            weights[key] = max(candidates)
    header = (
        "# CC-CEDICT Chinese headwords/readings for StudyIME\n"
        "# CC-CEDICT community contributors; published by MDBG; based on CEDICT by Paul Andrew Denisowski.\n"
        "# Source: https://cc-cedict.org/wiki/ ; fixed snapshot " + lock["snapshot_date"] + "\n"
        "# License: CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/\n"
        "# Changes: Han/Mandarin filtering, duplicate sense removal, lowercase toneless pinyin (u: -> v).\n" +
        ("# Ranking: uniform weights.\n" if weighting == "uniform" else
         "# Ranking: wordfreq 3.1.1 Chinese word frequency bins, CC BY-SA 4.0; see bundled credits.\n"
         "# Polyphonic single characters use Unicode 17.0.0 kHanyuPinlu reading shares; Unicode License V3.\n"
         "# Headwords use the source's simplified Chinese field.\n" if weighting == "wordfreq" else
         "# Ranking: Unicode 17.0.0 kHanyuPinlu character-reading counts plus CC-CEDICT compound counts.\n"
         "# Unicode data (c) 2025 Unicode, Inc.; Unicode License V3. Derived word weights are not corpus word frequencies.\n") +
        "# The separate 200-entry English review batch is unchanged.\n"
        "---\nname: cedict_study\nversion: '20261106-" + weighting + "-1'\nsort: by_weight\nuse_preset_vocabulary: false\n...\n"
    )
    ordered = sorted(entries, key=lambda item: (item[1], item[0]))
    dictionary = (header + "".join(word + "\t" + code + "\t" + str(weights.get((word, code), 100)) + "\n" for word, code in ordered)).encode("utf-8")
    mapping = {word + "\t" + code: entries[(word, code)] for word, code in ordered}
    report = {"schema_version": 1, "status": "comparison-only" if comparison else "StudyIME developer-preview Chinese base; everyday typing acceptance pending",
              "source": {key: lock[key] for key in ["source_id", "snapshot_date", "attribution", "homepage", "license", "license_url"]},
              "source_text_sha256": sha256(raw), "source_entries": count, "accepted_source_entries": accepted_sources,
              "dictionary_entries": len(entries), "distinct_headwords": len({word for word, code in entries}),
              "deduplicated_senses": accepted_sources - len(entries), "rejected": dict(rejected),
              "dictionary_sha256": sha256(dictionary), "source_mapping_sha256": sha256(json_bytes(mapping)),
              "generator_sha256": file_hash(Path(__file__)), "frequency_data": frequency_source,
              "pronunciation_data": pronunciation_source, "polyphonic_characters": len(polyphonic),
              "weighting": weighting,
              "weighting_formula": "uniform 100" if weighting == "uniform" else "max(1,floor(10**((900-negative_centibel_bin)/100))), missing=1; exact simplified headword lookup. For single characters with multiple exported readings, multiply by max(1,Unihan reading count)/sum of those reading counts, floor and clamp to 1" if weighting == "wordfreq" else "floor(integer geometric mean of per-character reading counts, absent=1) * (1+min(known containing CC-CEDICT compounds,50)); single characters use reading counts only",
              "english_review_modified": False, "limits": ["Candidate weights need usability comparison", "Does not replace or approve any of the 200 English review entries"]}
    output = {"cedict_study.dict.yaml": dictionary, "source-mapping.json": json_bytes(mapping),
            "provenance.json": json_bytes(report), "CC-BY-SA-4.0.txt": (ROOT / "data/lexicon/licenses/CC-BY-SA-4.0.txt").read_bytes()}
    if weighting == "unicode":
        output["UNICODE-LICENSE.txt"] = (ROOT / frequency_source["license_file"]).read_bytes()
    elif weighting == "wordfreq":
        output["WORDFREQ-LICENSE.txt"] = (ROOT / frequency_source["license_file"]).read_bytes()
        output["WORDFREQ-README.md"] = (ROOT / frequency_source["data_license_statement"]).read_bytes()
        output["UNICODE-LICENSE.txt"] = (ROOT / pronunciation_source["license_file"]).read_bytes()
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weighting", choices=["uniform", "unicode", "wordfreq"], default="wordfreq")
    args = parser.parse_args()
    output = ROOT / ".cache/dictionary" / ("cedict-" + args.weighting + "-experiment")
    generated = files(args.weighting)
    for name, content in generated.items(): write_changed(output / name, content)
    print(generated["provenance.json"].decode("utf-8"))
