"""Audit-derived regression cases, legacy compatibility, and mocked v3 transport."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.lexicon_expand import generation, planning, provider, quality, responses
from tools.lexicon_expand.catalog import load_prepared
from tools.lexicon_expand.common import CACHE, ROOT, Invalid, canonical, digest, read_json, read_jsonl, write_json
from tools.lexicon_expand.evaluation import make_comparison, PROMPT_EXAMPLES
from tools.lexicon_expand.normalization import parse_reply
from tools.lexicon_expand.review_pilot import BATCH, source_inputs, verify_protected


@unittest.skipUnless(BATCH.is_dir(), 'Historical V2 pilot archive is not bundled')
class QualityV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.decisions, cls.meta = source_inputs()
        catalog, _, _ = load_prepared()
        cls.catalog = {t['id']: t for t in catalog}
        cls.index = quality.reading_index()

    def setUp(self):
        (CACHE / 'tests').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=CACHE / 'tests')
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, number, version=3):
        original = self.records[number - 1]
        target = {'target_id': original['id'], 'english': original['english'],
                  'packs': original['packs'], 'cefr_levels': original['cefr_levels'],
                  'source_refs': original['source_refs'], 'dictionary_references': original['dictionary_references'],
                  'source_forms': self.catalog.get(original['id'], {}).get('source_forms', [])}
        senses = [{k: s[k] for k in ('chinese', 'pinyin', 'pos', 'meaning_zh', 'source_ref_ids')}
                  for s in original['senses']]
        if version == 3:
            for sense, source in zip(senses, original['senses']):
                sense['english'] = source['commit_english']
        reply = {'results': [{'target_id': original['id'], 'english': original['english'],
                              'senses': senses, 'unresolved_reason': None}]}
        job = planning.make_job('map_targets', [target], 'TEST ONLY', response_version=version)
        return job, reply

    def parse(self, job, reply):
        return responses.validate_reply(json.dumps(reply, ensure_ascii=False), job, {'kind': 'test-only'})

    def test_all_300_legacy_records_replay_without_content_or_identity_changes(self):
        for n, original in enumerate(self.records, 1):
            job, reply = self.fixture(n, version=2)
            result = responses.validate_reply(json.dumps(reply, ensure_ascii=False), job, original['generation'])
            self.assertEqual(result, [original], n)

    def test_may_month_and_modal_have_distinct_committed_case(self):
        job, reply = self.fixture(191)
        reply['results'][0]['senses'][0]['english'] = 'May'
        record = self.parse(job, reply)[0]
        self.assertEqual(record['lookup_key'], 'may')
        self.assertEqual([s['commit_english'] for s in record['senses']], ['May', 'may'])
        self.assertEqual(len({s['id'] for s in record['senses']}), 2)
        self.assertTrue(all(s['display_english'] == s['commit_english'] for s in record['senses']))
        self.assertTrue(all(s['quality']['disposition'] == 'checks-passed' for s in record['senses']))

    def test_capitalized_source_form_passes_without_title_casing_other_senses(self):
        job, reply = self.fixture(83)
        before = self.parse(job, reply)[0]['senses'][0]
        self.assertEqual(before['commit_english'], 'london')
        self.assertEqual(before['quality']['disposition'], 'review-required')
        reply['results'][0]['senses'][0]['english'] = 'London'
        after = self.parse(job, reply)[0]['senses'][0]
        self.assertEqual(after['commit_english'], 'London')
        self.assertEqual(after['quality']['disposition'], 'checks-passed')
        self.assertNotEqual(before['id'], after['id'])

    def test_sense_cannot_substitute_or_expand_fixed_target(self):
        job, reply = self.fixture(197)
        reply['results'][0]['senses'][0]['english'] = 'care for'
        with self.assertRaisesRegex(Invalid, 'Sense substituted'):
            self.parse(job, reply)

    def test_new_schema_requires_per_sense_english(self):
        job, reply = self.fixture(1)
        del reply['results'][0]['senses'][0]['english']
        with self.assertRaisesRegex(Invalid, 'Unexpected sense fields'):
            self.parse(job, reply)

    def test_model_cannot_supply_quality_approval(self):
        job, reply = self.fixture(1)
        reply['results'][0]['senses'][0]['quality'] = {'semantic_review': 'approved'}
        with self.assertRaisesRegex(Invalid, 'Unexpected sense fields'):
            self.parse(job, reply)

    def test_matching_readings_do_not_grant_semantic_approval(self):
        job, reply = self.fixture(104)
        record = self.parse(job, reply)[0]
        human_nature = record['senses'][2]
        self.assertEqual(human_nature['quality']['disposition'], 'checks-passed')
        self.assertEqual(human_nature['quality']['semantic_review'], 'pending')
        self.assertEqual(record['review']['status'], 'pending')
        self.assertIsNone(record['review']['reviewer'])
        self.assertFalse(record['release_ready'])

    def test_exactly_six_known_bad_pinyin_senses_are_blocked(self):
        summary, queue, _ = quality.audit_records(self.records, self.catalog, self.index)
        blocked = [r for r in queue if r['quality']['disposition'] == 'blocked']
        self.assertEqual({r['target_id'] for r in blocked},
                         {self.records[n - 1]['id'] for n in (226, 228, 230, 256, 272, 274)})
        self.assertEqual(summary['dispositions']['blocked'], 6)
        self.assertEqual(summary['semantic_approvals'], 0)

    def test_all_504_review_accepted_senses_avoid_hard_block(self):
        selected = [{**r, 'senses': [s for s, code in zip(r['senses'], d['decisions']) if code == 'P']}
                    for r, d in zip(self.records, self.decisions)]
        summary, _, _ = quality.audit_records(selected, self.catalog, self.index)
        self.assertEqual(summary['senses'], 504)
        self.assertEqual(summary['dispositions'].get('blocked', 0), 0)

    def test_bill_wrong_tone_is_caught_despite_toneless_match(self):
        sense = self.records[273]['senses'][0]
        result = quality.check_sense(sense, {}, self.index)
        self.assertTrue(result['base_reading_present'])
        self.assertFalse(result['numbered_reading_present'])
        self.assertEqual(result['disposition'], 'blocked')

    def test_baggage_claim_correct_polyphone_is_not_rejected(self):
        sense = self.records[201]['senses'][0]
        result = quality.check_sense(sense, {}, self.index)
        self.assertEqual(sense['pinyin'], 'xing2 li5 ti2 qu3')
        self.assertEqual(result['disposition'], 'checks-passed')
        self.assertFalse(result['base_reading_present'])
        self.assertEqual(result['findings'], [{'code': 'missing-chinese-trigger', 'severity': 'integration'}])

    def test_all_six_audited_pronunciation_corrections_remove_hard_block(self):
        correct = {226: 'mian4 shi4', 228: 'qiu2 zhi2 xin4', 230: 'ren2 mai4 tuo4 zhan3',
                   256: 'ban4 li3 ru4 zhu4', 272: 'cai4 dan1', 274: 'zhang4 dan1'}
        for n, pinyin in correct.items():
            sense = {**self.records[n - 1]['senses'][0], 'pinyin': pinyin}
            self.assertNotEqual(quality.check_sense(sense, {}, self.index)['disposition'], 'blocked', n)

    def test_known_characters_but_unlisted_word_reading_requires_review(self):
        index = quality.ReadingIndex('test', {'银行': {'yin2 hang2'}},
                                     {'银': {'yin2'}, '行': {'hang2', 'xing2'}})
        result = index.check('银行', 'yin2 xing2')
        self.assertEqual(result['findings'][0]['code'], 'word-reading-unconfirmed')
        self.assertEqual(result['findings'][0]['severity'], 'review')

    def test_accepted_neutral_tone_variants_are_not_normalized_or_rejected(self):
        index = quality.ReadingIndex('test', {'行李': {'xing2 li3', 'xing2 li5'}},
                                     {'行': {'xing2'}, '李': {'li3', 'li5'}})
        self.assertEqual(index.check('行李', 'xing2 li5')['findings'], [])
        self.assertEqual(index.check('行李', 'xing2 li3')['findings'], [])

    def test_unknown_character_reading_is_flagged_not_guessed(self):
        index = quality.ReadingIndex('test', {}, {})
        result = index.check('水', 'shui3')
        self.assertIn({'code': 'character-reading-unknown', 'severity': 'review', 'character': '水'}, result['findings'])
        self.assertFalse(any(f['severity'] == 'blocked' for f in result['findings']))

    def test_one_bad_sense_does_not_discard_other_target(self):
        bad_job, bad = self.fixture(274)
        good_job, good = self.fixture(73)
        job = planning.make_job('map_targets', bad_job['payload']['targets'] + good_job['payload']['targets'],
                                'TEST ONLY', response_version=3)
        result = self.parse(job, {'results': bad['results'] + good['results']})
        self.assertEqual(len(result), 2)
        self.assertEqual(sum(s['quality']['disposition'] == 'blocked' for r in result for s in r['senses']), 1)
        self.assertEqual(sum(s['quality']['disposition'] == 'checks-passed' for r in result for s in r['senses']), 1)

    def test_malformed_v3_pinyin_is_quarantined_without_discarding_other_target(self):
        bad_job, bad = self.fixture(274)
        good_job, good = self.fixture(73)
        bad['results'][0]['senses'][0]['pinyin'] = 'zhang4'
        job = planning.make_job('map_targets', bad_job['payload']['targets'] + good_job['payload']['targets'],
                                'TEST ONLY', response_version=3)
        result = self.parse(job, {'results': bad['results'] + good['results']})
        self.assertEqual(len(result), 2)
        blocked = [s for r in result for s in r['senses'] if s['quality']['disposition'] == 'blocked']
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]['quality']['findings'][0]['code'], 'pinyin-format')

    def test_repair_plan_contains_only_50_revision_senses(self):
        output = self.directory / 'repair'
        plan = planning.make_repair_plan(BATCH, output)
        _, jobs = planning.load_plan(output)
        actual = {(t['original_target_id'], t['original_sense']['id']) for j in jobs for t in j['payload']['targets']}
        expected = {(r['id'], s['id']) for r, d in zip(self.records, self.decisions)
                    for s, code in zip(r['senses'], d['decisions']) if code == 'R'}
        self.assertEqual(actual, expected)
        self.assertEqual((plan['maximum_items'], plan['request_count']), (50, 10))
        self.assertEqual(plan['preserved_accepted_senses'], 504)
        self.assertEqual(plan['excluded_rejected_senses'], 31)
        self.assertFalse(plan['automatic_adoption'])

    def repair_fixture(self):
        output = self.directory / 'repair'
        planning.make_repair_plan(BATCH, output)
        job = planning.load_plan(output)[1][0]
        target = job['payload']['targets'][0]
        single = planning.make_job('repair_senses', [target], 'TEST ONLY', response_version=3)
        source = target['original_sense']
        sense = {k: source[k] for k in ('chinese', 'pinyin', 'pos', 'meaning_zh', 'source_ref_ids')}
        sense['english'] = target['english']
        return single, {'results': [{'target_id': target['target_id'], 'english': target['english'],
                                    'senses': [sense], 'unresolved_reason': None}]}, target

    def test_repair_reply_keeps_origin_and_remains_pending(self):
        job, reply, target = self.repair_fixture()
        result = self.parse(job, reply)[0]
        self.assertEqual(result['repair_of']['sense_id'], target['original_sense']['id'])
        self.assertEqual(result['repair_of']['source_record_sha256'], target['source_record_sha256'])
        self.assertEqual(result['review']['status'], 'pending')

    def test_repair_cannot_add_extra_senses(self):
        job, reply, _ = self.repair_fixture()
        reply['results'][0]['senses'] *= 2
        with self.assertRaisesRegex(Invalid, 'Too many senses'):
            self.parse(job, reply)

    def test_unfixable_repair_can_remain_unresolved(self):
        job, reply, _ = self.repair_fixture()
        reply['results'][0].update(senses=[], unresolved_reason='测试：当前目标无法可靠承担该义项')
        self.assertEqual(self.parse(job, reply)[0]['senses'], [])

    def test_v2_plan_snapshot_is_independent_of_future_template_changes(self):
        output = self.directory / 'new'
        planning.make_plan(output=output, word_count=1, scene_count=0)
        changed = self.directory / 'future-prompt.txt'
        changed.write_text('TEST FUTURE PROMPT', encoding='utf-8')
        with patch.dict(planning.PROMPTS, {2: changed}):
            plan, jobs = planning.load_plan(output)
        self.assertEqual(plan['schema_version'], 3)
        self.assertEqual(jobs[0]['messages'][0]['content'], (output / 'prompt.txt').read_text(encoding='utf-8'))

    def test_new_plan_cannot_overwrite_legacy_plan_directory(self):
        output = self.directory / 'legacy'
        planning.make_plan(output=output, word_count=1, scene_count=0, prompt_version=1)
        before = {p.name: p.read_bytes() for p in output.iterdir()}
        with self.assertRaisesRegex(Invalid, 'different plan'):
            planning.make_plan(output=output, word_count=1, scene_count=0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_prompt_snapshot_tampering_is_rejected(self):
        output = self.directory / 'new'
        planning.make_plan(output=output, word_count=1, scene_count=0)
        (output / 'prompt.txt').write_text('TEST TAMPER', encoding='utf-8')
        with self.assertRaisesRegex(Invalid, 'Prompt changed'):
            planning.load_plan(output)

    def test_real_old_plan_still_loads_after_new_profile(self):
        plan, _ = planning.load_plan()
        self.assertEqual(plan['schema_version'], 2)
        self.assertEqual(plan['maximum_items'], 300)

    def test_comparison_has_same_40_targets_and_excludes_all_prompt_examples(self):
        with patch.object(provider, 'read_key') as key, patch.object(provider, 'complete') as call:
            manifest = make_comparison(self.directory / 'comparison')
        key.assert_not_called()
        call.assert_not_called()
        a = planning.load_plan(self.directory / 'comparison/v1')[1]
        b = planning.load_plan(self.directory / 'comparison/v2')[1]
        aa = [t for j in a for t in j['payload']['targets']]
        bb = [t for j in b for t in j['payload']['targets']]
        self.assertEqual(aa, bb)
        self.assertEqual(len(aa), 40)
        self.assertFalse({t['english'] for t in aa} & PROMPT_EXAMPLES)
        self.assertEqual(manifest['sample_groups'], {'known_pinyin_problems': 5, 'case_problems': 5,
                                                   'other_review_problems': 10, 'accepted_controls': 20})
        self.assertIsNone(manifest['measured_quality_improvement'])

    def test_v3_generation_preserves_good_target_and_resumes_without_duplicate_calls(self):
        a_job, a = self.fixture(274)
        b_job, b = self.fixture(73)
        job = planning.make_job('map_targets', a_job['payload']['targets'] + b_job['payload']['targets'],
                                'TEST ONLY', response_version=3)
        plan = {'schema_version': 3, 'maximum_items': 2, 'request_count': 1,
                'prepared_directory': str(CACHE / 'prepared'), 'prompt_sha256': 'test-only',
                'quality_policy': quality.policy()}
        raw = canonical({'model': 'test-model', 'choices': [{'finish_reason': 'stop',
                         'message': {'content': json.dumps({'results': a['results'] + b['results']}, ensure_ascii=False)}}],
                         'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}})
        config = self.directory / 'config.json'
        write_json(config, {'base_url': 'https://provider.invalid', 'model': 'test-model',
                            'api_key_env': 'STUDYIME_TEST_KEY'})
        output = self.directory / 'results'
        with patch.object(generation, 'load_plan', return_value=(plan, [job])), \
             patch.object(provider, 'read_key', return_value='TEST-ONLY-CREDENTIAL') as key, \
             patch.object(provider, 'complete', return_value=raw) as call:
            summary = generation.generate(self.directory / 'plan', config, output, execute=True)
            self.assertEqual(call.call_count, 1)
            key.reset_mock(); call.reset_mock()
            resumed = generation.generate(self.directory / 'plan', config, output, execute=True)
            key.assert_not_called(); call.assert_not_called()
        self.assertEqual(summary, resumed)
        self.assertEqual(summary['returned_items'], 2)
        self.assertEqual(summary['blocked_senses'], 1)
        self.assertEqual(summary['semantic_approved_senses'], 0)
        self.assertEqual(len(read_jsonl(output / 'drafts.jsonl')), 2)

    def test_new_response_normalization_is_still_auditable(self):
        job, reply = self.fixture(73)
        reply['results'][0]['senses'][0]['pos'] = 'noun'
        records, metadata = parse_reply(json.dumps(reply, ensure_ascii=False), job, {})
        self.assertEqual(records[0]['senses'][0]['pos'], 'n')
        self.assertEqual(metadata['normalization']['changes'][0]['rule'], 'pos-alias')

    def test_all_488_historical_inputs_are_unchanged(self):
        self.assertEqual(verify_protected(self.meta), 488)


if __name__ == '__main__':
    unittest.main()
