"""Regression checks for reviewed multi-sense data and Chinese supplements."""
import copy
import unittest

from tools.lexicon_expand.common import Invalid
from tools.lexicon_expand.runtime import compile_model, lua_bytes, supplement_dictionary, trigger_additions


def sense(sid='month', chinese='五月', english='May', pinyin='wu3 yue4'):
    return {'id': sid, 'chinese': chinese, 'display_english': english,
            'commit_english': english, 'pinyin': pinyin, 'verdict': 'accepted'}


class RuntimeTests(unittest.TestCase):
    def test_case_and_full_multiword_commit_are_preserved(self):
        model = compile_model([sense(), sense('phrase', '求职信', 'cover letter', 'qiu2 zhi2 xin4')], {})
        raw = lua_bytes(model)
        self.assertIn(b'commit_english = "May"', raw)
        self.assertIn(b'commit_english = "cover letter"', raw)
        self.assertNotIn(b'"may"', raw)

    def test_ambiguous_Chinese_needs_authored_choice_and_keeps_all_senses(self):
        rows = [sense('a', '可能', 'may', 'ke3 neng2'), sense('b', '可能', 'might', 'ke3 neng2')]
        with self.assertRaises(Invalid):
            compile_model(rows, {})
        model = compile_model(rows, {'可能': {'english': 'may', 'reason': '常用推测义'}})
        entry = model['entries']['可能']
        self.assertEqual(entry['primary_sense_id'], 'a')
        self.assertEqual(len(entry['senses']), 2)

    def test_unaccepted_foreign_primary_and_stale_choices_fail(self):
        with self.assertRaises(Invalid):
            compile_model([{**sense(), 'verdict': 'needs-revision'}], {})
        with self.assertRaises(Invalid):
            compile_model([sense()], {'五月': {'english': 'May', 'reason': 'unneeded'}})
        rows = [sense(), sense('other', '五月', 'month', 'wu3 yue4')]
        with self.assertRaises(Invalid):
            compile_model(rows, {'五月': {'english': 'FOREIGN', 'reason': 'wrong'}})

    def test_duplicate_ids_and_display_commit_mismatch_fail(self):
        with self.assertRaises(Invalid):
            compile_model([sense(), sense()], {})
        with self.assertRaises(Invalid):
            compile_model([{**sense(), 'display_english': 'may'}], {})

    def test_same_english_different_sources_are_preserved(self):
        model = compile_model([sense('first'), sense('second')], {})
        self.assertEqual(len(model['entries']['五月']['senses']), 2)

    def test_different_pronunciations_keep_separate_selected_English(self):
        rows = [sense('return', '还', 'return', 'huan2'), sense('even', '还', 'even', 'hai2')]
        entry = compile_model(rows, {})['entries']['还']
        self.assertTrue(entry['requires_reading'])
        self.assertEqual(entry['primary_by_reading'], {'huan': 'return', 'hai': 'even'})
        self.assertIn(b'requires_reading = true', lua_bytes(compile_model(rows, {})))

    def test_authored_choice_is_applied_within_its_reading_only(self):
        rows = [sense('return', '还', 'return', 'huan2'), sense('even', '还', 'even', 'hai2'),
                sense('still', '还', 'still', 'hai2')]
        model = compile_model(rows, {'还': {'english': 'even', 'reason': '限定比较级强调义'}})
        self.assertEqual(model['entries']['还']['primary_by_reading'], {'huan': 'return', 'hai': 'even'})

    def test_legacy_preview_is_fallback_and_original_is_unchanged(self):
        old = [{**sense('legacy'), 'display_english': 'may', 'commit_english': 'may',
                'review': {'status': 'pending'}}]
        before = copy.deepcopy(old)
        model = compile_model([sense()], {}, old)
        self.assertEqual(model['entries']['五月']['primary_sense_id'], 'month')
        self.assertEqual(old, before)
        model = compile_model([], {}, old)
        self.assertEqual(model['entries']['五月']['senses'][0]['commit_english'], 'may')

    def test_missing_reading_not_missing_word_and_duplicate_triggers(self):
        rows = [sense('a'), sense('b')]
        self.assertEqual(trigger_additions(rows, {('五月', 'wu yue')}), [])
        missing = trigger_additions(rows, {('五月', 'wu ri')})
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]['sense_ids'], ['a', 'b'])

    def test_supplement_preserves_base_and_uses_complete_pinyin(self):
        base = b'---\nname: test\n...\n'
        rows = trigger_additions([sense()], set())
        value = supplement_dictionary(base, rows)
        self.assertTrue(value.startswith(base))
        self.assertIn('五月\twu yue\t100\n'.encode(), value)


if __name__ == '__main__':
    unittest.main()
