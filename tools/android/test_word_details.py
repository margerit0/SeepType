import json
from pathlib import Path
import unittest

from tools.android.word_details import _pinyin, pack_details


SNAPSHOT = Path(__file__).resolve().parents[2] / "data/lexicon-expansion/android-runtime"


class WordDetailsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = (SNAPSHOT / "word-details.jsonl").read_bytes()
        cls.examples = (SNAPSHOT / "word-detail-examples.json").read_bytes()
        cls.assets = pack_details(cls.rows, cls.examples)
        cls.words = {word: readings for content in cls.assets.values() for word, readings in json.loads(content).items()}

    def test_full_snapshot_is_indexed_without_fabricating_examples(self):
        lock = json.loads((SNAPSHOT / "snapshot.json").read_bytes())
        self.assertEqual(sum(map(len, self.words.values())), lock["englishTriggerReadings"])
        self.assertLess(max(map(len, self.assets.values())), 64 * 1024)
        self.assertEqual(self.assets, pack_details(self.rows, self.examples))
        all_senses = [sense for readings in self.words.values() for entry in readings.values() for sense in entry["senses"]]
        self.assertCountEqual((sense["id"] for sense in all_senses if "exampleEn" in sense),
                              (example["id"] for example in json.loads(self.examples)))

    def test_default_first_and_polyphonic_details_stay_separate(self):
        solve = self.words["解决"]["jie jue"]
        self.assertEqual(solve["pinyin"], "jiějué")
        self.assertEqual([sense["english"] for sense in solve["senses"]], ["solve", "settle"])
        self.assertEqual([sense["collocation"] for sense in solve["senses"]], ["solve a problem", "settle a dispute"])
        for code, pinyin, meanings in (("hai", "hái", ["even", "yet"]), ("huan", "huán", ["return"])):
            entry = self.words["还"][code]
            self.assertEqual(entry["pinyin"], pinyin)
            self.assertEqual([sense["english"] for sense in entry["senses"]], meanings)

    def test_wrong_example_binding_is_rejected(self):
        example = dict(json.loads(self.examples)[0], reading="ji jue")
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            pack_details(self.rows, json.dumps([example]))
        with self.assertRaisesRegex(ValueError, "no runtime sense"):
            pack_details(self.rows, json.dumps([dict(example, id="deleted-sense")]))

    def test_pinyin_text_preserves_tones_and_boundaries(self):
        self.assertEqual(_pinyin(["xi1 an1"]), "xī'ān")
        self.assertEqual(_pinyin(["liu2 shui3"]), "liúshuǐ")
        self.assertEqual(_pinyin(["lv4 se4"]), "lǜsè")
        self.assertEqual(_pinyin(["shu1 fu5"]), "shūfu")
        self.assertEqual(_pinyin(["di4", "di5"]), "")
