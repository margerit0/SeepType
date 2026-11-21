# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic, host-side checks of the curation input (no Gradle or network)."""
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.android import offline_names

BASE = ("---\nname: cedict_study\n...\n"
        "中立\tzhong li\t12882\n重力\tzhong li\t7244\n中离\tzhong li\t1\n"
        "芙\tfu\t50\n宁\tning\t80\n娜\tna\t55\n").encode()
BASE_ONLY = ("中离", "zhong li", "character", "原神", "Q65059474", "Q1000", "987", "zh-cn", "dev-checked", "", "")
HOMOPHONE = ("钟离", "zhong li", "character", "原神", "Q65059474", "Q107287615", "123", "zh-cn", "dev-checked", "", "")
FURINA = ("芙宁娜", "fu ning na", "character", "原神", "Q65059474", "Q122582963", "456", "zh-hans", "dev-checked",
          "Furina", "https://genshin.hoyoverse.com/en/news/detail/113484")


class OfflineNamesTest(unittest.TestCase):
    def load(self, *rows):
        with tempfile.TemporaryDirectory() as root, patch.object(offline_names, "SOURCE", Path(root)):
            source = Path(root)
            (source / "sources.json").write_text('{"source":"Wikidata","license":"CC0-1.0","collectedOn":"2026-11-21"}', encoding="utf-8")
            data = io.StringIO(newline="")
            writer = csv.writer(data, delimiter="\t", lineterminator="\n")
            writer.writerow(offline_names.FIELDS)
            writer.writerows(rows)
            (source / "names.tsv").write_bytes(data.getvalue().encode())
            return offline_names.load_names(BASE)

    def test_dedup_distinguishes_repeated_reading_from_same_word(self):
        files, version = self.load(BASE_ONLY, HOMOPHONE, FURINA)
        self.assertEqual((version["entries"], version["alreadyInBase"], version["sharedReadings"]), (2, 1, 1))
        dict_source = files["rime/study_offline_names.dict.yaml"].decode()
        self.assertIn("钟离\tzhong li\t1\n", dict_source)
        self.assertNotIn("中离\t", dict_source)
        collision = json.loads(files["notices/android-names/collisions.json"])["sharedReadings"][0]
        self.assertEqual(collision, {"pinyin": "zhong li", "names": ["钟离"], "base": ["中离", "中立", "重力"]})
        self.assertIn(b'commit_english = "Furina"', files["rime/lua/study_offline_names_en.lua"])
        self.assertNotIn("钟离".encode(), files["rime/lua/study_offline_names_en.lua"])

    def test_duplicate_curated_rows_fail_with_line_number(self):
        with self.assertRaisesRegex(ValueError, r"Duplicate name and reading in names.tsv:3"):
            self.load(FURINA, FURINA)

    def test_entry_requires_reading_provenance_and_source_for_english(self):
        for index, bad, message in [(1, "funingna", "reading"), (5, "Q0", "provenance"),
                                    (6, "", "provenance"), (10, "", "English requires")]:
            row = list(FURINA)
            row[index] = bad
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, message):
                self.load(row)

    def test_series_is_a_work_and_uses_its_own_qid(self):
        series = ("芙宁", "fu ning", "series", "芙宁", "Q10", "Q10", "234", "zh-cn", "dev-checked", "", "")
        files, version = self.load(series)
        self.assertEqual(version["entries"], 1)
        self.assertIn("芙宁\tfu ning\t1\n", files["rime/study_offline_names.dict.yaml"].decode())
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.load((*series[:4], "Q11", *series[5:]))
        self.assertEqual(self.load((*series[:7], "alias:zh", *series[8:]))[1]["entries"], 1)
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.load((*series[:7], "alias:en", *series[8:]))

    def test_names_only_change_updates_packaged_digest(self):
        first, first_meta = self.load(FURINA)
        second, second_meta = self.load(FURINA, HOMOPHONE)
        self.assertNotEqual(first_meta["tsvSha256"], second_meta["tsvSha256"])
        self.assertNotEqual(first["rime/study_offline_names.dict.yaml"], second["rime/study_offline_names.dict.yaml"])
        self.assertEqual(first["notices/android-names/sources.json"], second["notices/android-names/sources.json"])


if __name__ == "__main__":
    unittest.main()
