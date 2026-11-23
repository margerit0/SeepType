"""Adoption guardrails and preservation of previously working runtime options."""
import copy
import unittest

from tools.lexicon_expand.common import Invalid, canonical, digest
from tools.lexicon_expand.integration import resolve_routes, retained_legacy
from tools.lexicon_expand.runtime import compile_model
from tools.lexicon_expand.verify_integration import alternative_layers


def source(pid, chinese='吸收', english='absorb', meaning='吸收物质', pos='v', pinyin='xi1 shou1'):
    sense = {'id': 'sense-' + pid, 'chinese': chinese, 'commit_english': english,
             'display_english': english, 'meaning_zh': meaning, 'pos': pos, 'pinyin': pinyin}
    sha = digest(canonical(sense))
    return {'packet_id': pid, 'candidate': sense, 'candidate_sha256': sha, 'english': english,
            'target_id': 'target-' + pid, 'packs': [],
            'decision': {'decision': 'accepted', 'candidate_sha256': sha, 'reason': '已逐项审核'}}


def route(row, action='adopt', destination=None, **kwargs):
    return {'packet_id': row['packet_id'], 'candidate_sha256': row['candidate_sha256'],
            'action': action, 'destination': destination or row['packet_id'], 'reason': '比较原说明后采用', **kwargs}


class IntegrationTests(unittest.TestCase):
    def test_identical_submission_does_not_collapse_distinct_meanings(self):
        physical, knowledge = source('physical'), source('knowledge', meaning='理解并掌握知识')
        rows, _ = resolve_routes([], [physical, knowledge], [route(physical), route(knowledge)])
        self.assertEqual([r['meaning_zh'] for r in rows], ['吸收物质', '理解并掌握知识'])

    def test_merge_requires_an_explicit_semantic_adjudication(self):
        first, second = source('one'), source('two')
        routes = [route(first), route(second, 'merge-reviewed-version', 'one')]
        with self.assertRaises(Invalid):
            resolve_routes([], [first, second], routes)
        routes[1]['semantic_adjudication'] = {'reason': '同一材料吸收义的重复稿'}
        rows, provenance = resolve_routes([], [first, second], routes)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(provenance['one']), 2)

    def test_merge_cannot_silently_change_pos_or_reading(self):
        first, second = source('one'), source('two', pos='n')
        with self.assertRaises(Invalid):
            resolve_routes([], [first, second], [route(first), route(second, 'merge-reviewed-version', 'one',
                semantic_adjudication={'reason': 'Not sufficient: different POS'})])

    def test_incomplete_routes_and_rejected_sources_fail(self):
        row = source('one')
        with self.assertRaises(Invalid):
            resolve_routes([], [row], [])
        row['decision']['decision'] = 'deferred'
        with self.assertRaises(Invalid):
            resolve_routes([], [row], [route(row)])

    def test_changed_review_hash_cannot_be_adopted(self):
        row = source('one')
        row['decision']['candidate_sha256'] = 'changed'
        with self.assertRaises(Invalid):
            resolve_routes([], [row], [route(row)])

    def test_alias_retains_its_own_original_chinese_and_reading(self):
        first = source('one', '普通', 'ordinary', '平常无特殊之处', 'adj', 'pu3 tong1')
        second = source('two', '一般', 'ordinary', '平平常常的', 'adj', 'yi1 ban1')
        rows, _ = resolve_routes([], [first, second], [route(first),
            route(second, 'adopt-search-alias', semantic_anchor='one')])
        self.assertEqual(len(rows), 2)
        self.assertEqual((rows[1]['chinese'], rows[1]['pinyin']), ('一般', 'yi1 ban1'))
        other = source('other', '一般', 'average', '中等水平', 'adj', 'yi1 ban1')
        with self.assertRaises(Invalid):
            resolve_routes([], [first, other], [route(first),
                route(other, 'adopt-search-alias', semantic_anchor='one')])

    def test_baseline_rows_are_not_rewritten(self):
        baseline = [{**source('base')['candidate'], 'verdict': 'accepted', 'original': 'keep'}]
        before = copy.deepcopy(baseline)
        row = source('new')
        result, _ = resolve_routes(baseline, [row], [route(row, 'already-in-baseline', 'sense-base')])
        self.assertEqual(result, before)
        self.assertEqual(baseline, before)

    def test_local_revision_gets_an_id_without_changing_reviewed_candidate(self):
        row = source('revision')
        del row['candidate']['id']
        row['candidate_sha256'] = row['decision']['candidate_sha256'] = digest(canonical(row['candidate']))
        before = copy.deepcopy(row)
        result, _ = resolve_routes([], [row], [route(row)])
        self.assertEqual(result[0]['id'], 'sense-revision')
        self.assertEqual(row, before)

    def test_legacy_overlap_survives_a_second_integration(self):
        from types import SimpleNamespace
        row = {'id': 'file', 'chinese': '文件', 'source_entry_sha256': 'sha', 'review': {'status': 'pending'}}
        validation = SimpleNamespace(entries=[row], sources={'sha': {'pinyin': 'wen2 jian4'}})
        model = {'entries': {'文件': {'senses': [{'id': 'legacy-file'}, {'id': 'expanded-file'}]}}}
        kept = retained_legacy([{'chinese': '文件'}], model, validation)
        self.assertEqual(kept, [{**row, 'pinyin': 'wen2 jian4'}])

    def test_opt_in_retains_old_legacy_default_and_new_candidate(self):
        new = {**source('file', '文件', 'file', '计算机文件', 'n', 'wen2 jian4')['candidate'], 'verdict': 'accepted'}
        old = {**source('document', '文件', 'document', '文件', 'n', 'wen2 jian4')['candidate'],
               'review': {'status': 'pending'}}
        before = copy.deepcopy(old)
        choice = {'文件': {'english': 'document', 'reason': '保留旧运行时默认'}}
        model = compile_model([new], choice, [old], retain_legacy_words={'文件'})
        self.assertEqual(model['entries']['文件']['primary_sense_id'], 'legacy-sense-document')
        self.assertEqual({s['commit_english'] for s in model['entries']['文件']['senses']}, {'file', 'document'})
        self.assertEqual(old, before)
        with self.assertRaises(Invalid):
            compile_model([new], {}, [old], retain_legacy_words={'文件'})

    def test_alternate_validation_never_crosses_readings_or_changes_delivered_model(self):
        rows = [{**source('return', '还', 'return', '归还', 'v', 'huan2')['candidate'], 'verdict': 'accepted'},
                {**source('even', '还', 'even', '甚至', 'adv', 'hai2')['candidate'], 'verdict': 'accepted'},
                {**source('still', '还', 'still', '仍然', 'adv', 'hai2')['candidate'], 'verdict': 'accepted'}]
        model = compile_model(rows, {'还': {'english': 'even', 'reason': '比较强调'}})
        before = copy.deepcopy(model)
        readings = [{'chinese': '还', 'code': 'huan', 'sense_ids': ['sense-return']},
                    {'chinese': '还', 'code': 'hai', 'sense_ids': ['sense-even', 'sense-still']}]
        layers = alternative_layers(model, readings)
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0]['model']['entries']['还']['primary_by_reading'],
                         {'huan': 'sense-return', 'hai': 'sense-still'})
        self.assertEqual(model, before)


if __name__ == '__main__':
    unittest.main()
