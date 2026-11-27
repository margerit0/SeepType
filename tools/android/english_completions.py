"""Export a sorted single-word index from pinned CEFR-J and wordfreq data."""

import csv
from functools import lru_cache
import io
import json
import re

from tools.android.common import ROOT, digest
from tools.dictionary.wordfreq import frequency_groups

ASSET = "rime/english-completions.tsv"
ENGLISH_FREQUENCIES = {
    "source_file": "wordfreq-3.1.1/wordfreq/data/large_en.msgpack.gz",
    "source_sha256": "dffae8066b78dce0a6667cf5f58e567054f902674667090a7ac8a8a44628b05c",
}
SINGLE_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")


@lru_cache(maxsize=1)
def build_index():
    expansion = ROOT / "data/lexicon-expansion"
    sources = json.loads((expansion / "sources.lock.json").read_bytes())["sources"]
    cefr = next(item for item in sources if item["id"] == "cefrj-1.5-d4e45b75")
    path = ROOT / cefr["local_file"]
    if digest(path) != cefr["local_sha256"]:
        raise ValueError("Pinned CEFR-J wordlist changed")
    rows = csv.DictReader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline=""))
    words = {part.lower() for row in rows for variant in row["headword"].split("/")
             if SINGLE_WORD.fullmatch(part := variant.strip())}
    wordfreq = json.loads((ROOT / "data/chinese/sources.lock.json").read_bytes())["wordfreq"]
    ranks = {}
    groups = frequency_groups({**wordfreq, **ENGLISH_FREQUENCIES})
    for rank, group in enumerate(groups):
        for word in group:
            if word in words:
                ranks[word] = rank
    return "".join(f"{word}\t{ranks.get(word, len(groups))}\n" for word in sorted(words)).encode("ascii")
