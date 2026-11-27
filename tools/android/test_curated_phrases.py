# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the shipped phrase table, its readings and Android resource wiring."""
from collections import defaultdict
from pathlib import Path
import csv
import re
import unittest

from tools.android import prepare_data


ROOT = Path(__file__).resolve().parents[2]
PHRASES = ROOT / "android/rime/study_phrases.dict.yaml"
BASE = ROOT / "data/lexicon-expansion/android-runtime/cedict_study.dict.yaml"
NAMES = ROOT / "data/lexicon-expansion/android-names/names.tsv"


def dictionary_rows(path):
    source = path.read_text(encoding="utf-8")
    header, separator, body = source.partition("\n...\n")
    if not separator:
        raise ValueError(f"Missing Rime dictionary header: {path}")
    return header, [line.split("\t") for line in body.splitlines() if line and not line.startswith("#")]


class CuratedPhrasesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header, cls.rows = dictionary_rows(PHRASES)
        _, cls.base = dictionary_rows(BASE)
        with NAMES.open(encoding="utf-8", newline="") as source:
            cls.names = {row["zh"] for row in csv.DictReader(source, delimiter="\t")}

    def test_count_format_and_no_existing_headwords(self):
        self.assertIn("name: study_phrases", self.header)
        self.assertEqual(1000, len(self.rows))
        base_words = {row[0] for row in self.base} | self.names | {"让我"}
        words = set()
        for row in self.rows:
            self.assertEqual(3, len(row), row)
            word, reading, weight = row
            with self.subTest(word=word):
                self.assertRegex(word, r"^[\u4e00-\u9fff]{2,8}$")
                self.assertEqual(len(word), len(reading.split(" ")))
                self.assertTrue(all(re.fullmatch(r"[a-z]+", code) for code in reading.split(" ")))
                self.assertEqual("1000", weight)
                self.assertNotIn(word, words)
                self.assertNotIn(word, base_words)
            words.add(word)

    def test_each_character_reading_exists_in_the_fixed_base(self):
        readings = defaultdict(set)
        for word, code, *_ in self.base:
            syllables = code.split(" ")
            if len(word) == len(syllables):
                for char, syllable in zip(word, syllables):
                    readings[char].add(syllable)
        for word, code, _ in self.rows:
            for char, syllable in zip(word, code.split(" ")):
                with self.subTest(word=word, character=char):
                    self.assertIn(syllable, readings[char])

    def test_selected_polyphonic_and_colloquial_readings(self):
        readings = {word: code for word, code, _ in self.rows}
        expected = {
            "松弛感": "song chi gan", "氛围感": "fen wei gan", "网络热梗": "wang luo re geng",
            "游戏攻略": "you xi gong lve", "上大分": "shang da fen", "丝血": "si xue",
            "留个爪": "liu ge zhua", "视频时长": "shi pin shi chang", "对局时长": "dui ju shi chang",
            "打卡地": "da ka di", "着眼于": "zhuo yan yu", "记得带钥匙": "ji de dai yao shi",
            "等会儿": "deng hui er", "请重试": "qing chong shi",
        }
        for word, code in expected.items():
            with self.subTest(word=word):
                self.assertEqual(code, readings.get(word))

    def test_dictionary_is_imported_and_in_the_refreshed_resource_set(self):
        parent = (ROOT / "android/rime/study_android.dict.yaml").read_text(encoding="utf-8")
        self.assertRegex(parent, r"(?m)^  - study_phrases$")
        self.assertEqual(PHRASES, prepare_data.RIME_SOURCES["rime/study_phrases.dict.yaml"])


if __name__ == "__main__":
    unittest.main()
