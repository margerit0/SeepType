"""Context-reading review, historical replay, repair scope and fair prompt trials."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.lexicon_expand import catalog, planning, provider, quality, quality_v3
from tools.lexicon_expand.common import CACHE, Invalid, canonical, read_json, read_jsonl, write_json
from tools.lexicon_expand.normalization import parse_reply


archive_trial = unittest.skipUnless(quality_v3.BATCH.is_dir(), 'Historical V3 trial inputs are not bundled')


class QualityV3Tests(unittest.TestCase):
    def setUp(self):
        (CACHE/'tests').mkdir(parents=True, exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=CACHE/'tests')
        self.work=Path(self.temp.name)/'work'
        self.review=Path(self.temp.name)/'review'

    def tearDown(self): self.temp.cleanup()

    def test_contextual_de_is_not_proven_by_character_reading_and_never_rewritten(self):
        index=quality.ReadingIndex('test',{}, {'负':{'fu4'},'担':{'dan1'},'得':{'de2','de5'},'起':{'qi3'}})
        for pinyin in ('fu4 dan1 de2 qi3','fu4 dan1 de5 qi3'):
            sense={'chinese':'负担得起','pinyin':pinyin,'commit_english':'afford'}
            original=deepcopy(sense)
            self.assertEqual('checks-passed',quality.check_sense(sense,{},index,version=1)['disposition'])
            current=quality.check_sense(sense,{},index,version=2)
            self.assertEqual('review-required',current['disposition'])
            self.assertIn('phrase-reading-unconfirmed',{f['code'] for f in current['findings']})
            self.assertEqual(original,sense)

    def test_exact_supported_neutral_and_non_neutral_readings_remain_usable(self):
        index=quality.ReadingIndex('test',{'觉得':{'jue2 de5'},'取得':{'qu3 de2'}},
            {'觉':{'jue2'},'取':{'qu3'},'得':{'de2','de5'}})
        for zh,py in (('觉得','jue2 de5'),('取得','qu3 de2')):
            self.assertEqual([],index.check(zh,py,version=2)['findings'])

    def test_missing_phrase_is_review_condition_not_translation_rejection(self):
        index=quality.ReadingIndex('test',{}, {'民':{'min2'},'族':{'zu2'},'的':{'de5'}})
        result=index.check('民族的','min2 zu2 de5',version=2)
        self.assertEqual({'integration','review'},{f['severity'] for f in result['findings']})
        self.assertFalse(any(f['severity']=='blocked' for f in result['findings']))

    def test_regional_word_variant_is_reviewed_and_missing_tone_is_blocked(self):
        index=quality.ReadingIndex('test',{'关系':{'guan1 xi5'}}, {'关':{'guan1'},'系':{'xi4','xi5'}})
        self.assertEqual('word-reading-unconfirmed',index.check('关系','guan1 xi4',version=2)['findings'][0]['code'])
        self.assertFalse(any(f['severity']=='blocked' for f in index.check('关系','guan1 xi4',version=2)['findings']))
        self.assertEqual('pinyin-format',index.check('关系','guan1 xi',version=2)['findings'][0]['code'])

    def test_new_plan_binds_v3_and_policy_two_without_invalidating_v2(self):
        directory=self.work/'new'
        prepared=self.work/'prepared'
        catalog.prepare(prepared)
        legacy=self.work/'v2'
        planning.make_plan(prepared,output=legacy,word_count=1,scene_count=0,prompt_version=2)
        planning.make_plan(prepared,output=directory,word_count=1,scene_count=0,prompt_version=3)
        plan,jobs=planning.load_plan(directory)
        self.assertEqual((3,2),(plan['prompt_version'],plan['quality_policy']['version']))
        future=Path(self.temp.name)/'future.txt';future.write_text('Future template',encoding='utf-8')
        with patch.dict(planning.PROMPTS,{3:future}):
            self.assertEqual(plan,planning.load_plan(directory)[0])
        self.assertEqual(1,planning.load_plan(legacy)[0]['quality_policy']['version'])
        with self.assertRaisesRegex(Invalid,'Unknown quality'):
            quality.policy(99)

    def test_response_uses_bound_policy_and_preserves_original_pinyin(self):
        t={'target_id':'test-context','english':'afford','packs':['test'],'source_refs':[], 'dictionary_references':[]}
        job=planning.make_job('map_targets',[t],'TEST',response_version=3,quality_policy=quality.policy(2))
        reply={'results':[{'target_id':t['target_id'],'english':'afford','unresolved_reason':None,
            'senses':[{'english':'afford','chinese':'负担得起','pinyin':'fu4 dan1 de2 qi3','pos':'v',
                       'meaning_zh':'测试用语境，不写入产品词库','source_ref_ids':[]}]}]}
        result,_=parse_reply(json.dumps(reply,ensure_ascii=False),job,{})
        s=result[0]['senses'][0]
        self.assertEqual('fu4 dan1 de2 qi3',s['pinyin'])
        self.assertEqual('review-required',s['quality']['disposition'])
        self.assertEqual('pending',result[0]['review']['status'])

    @archive_trial
    def test_evaluation_excludes_prior_words_and_preserves_repair_ancestry(self):
        with patch.object(provider,'read_key') as key,patch.object(provider,'complete') as complete:
            meta=quality_v3.prepare(self.work,self.review,holdout_count=5)
        key.assert_not_called();complete.assert_not_called()
        for group in ('holdout','regression'):
            a=planning.load_plan(self.work/(group+'-v2'))[1]
            b=planning.load_plan(self.work/(group+'-v3'))[1]
            self.assertEqual([j['payload'] for j in a],[j['payload'] for j in b])
        holdout=read_jsonl(self.work/'holdout-v3/selected-targets.jsonl')
        self.assertFalse({t['english'].lower() for t in holdout}&quality_v3.EXAMPLES)
        previous={r['english'] for r in read_jsonl(quality_v3.BATCH/'external/results/drafts.jsonl')}
        self.assertFalse({t['english'] for t in holdout}&previous)
        repairs=read_jsonl(self.work/'repairs-v3/selected-targets.jsonl')
        self.assertEqual(7,len(repairs));self.assertEqual(665,meta['preserved_accepted_senses'])
        self.assertTrue(all(t['original_sense']['id'] and t['repair_category'] for t in repairs))
        self.assertFalse({r['id'] for r in read_jsonl(quality_v3.BATCH/'accepted-senses.jsonl')}&
                         {t['original_sense']['id'] for t in repairs})
        phrases=read_json(self.review/'phrase-candidates.json')['items']
        self.assertEqual({'rely on','rely upon'},{p['english'] for p in phrases})
        self.assertTrue(all(not p['adopted'] for p in phrases))

    @archive_trial
    def test_global_budget_stops_cleanly_and_resume_never_reissues_completed_requests(self):
        quality_v3.prepare(self.work,self.review,holdout_count=5)
        meta=read_json(self.work/'experiment.json');meta['max_total_attempts']=2
        write_json(self.work/'experiment.json',meta)
        def complete(config,key,job):
            results=[]
            for t in job['payload']['targets']:
                results.append({'target_id':t['target_id'],'english':t['english'],'unresolved_reason':'测试空结果','senses':[]})
            return canonical({'choices':[{'message':{'content':json.dumps({'results':results},ensure_ascii=False)},
                                         'finish_reason':'stop'}],'model':config['model']})
        with patch.object(provider,'read_key',return_value='TEST-NOT-A-CREDENTIAL'), \
             patch.object(provider,'complete',side_effect=complete) as send,patch('builtins.print'):
            result=quality_v3.run(self.work,self.review)
            self.assertEqual(2,send.call_count);self.assertEqual(2,result['completed_requests'])
            send.reset_mock();quality_v3.run(self.work,self.review);send.assert_not_called()
        packet,_=quality_v3.review_packet(self.work,self.review)
        self.assertEqual(10,len(packet))
        self.assertTrue(all('profile' not in p and 'generation' not in p for p in packet))
        public=quality_v3.packet_summary(self.work,self.review)
        self.assertEqual(10,public['candidates'])
        self.assertEqual({'candidates','review_packet','prompt_versions_hidden'},set(public))
        decisions=[{'packet_id':p['packet_id'],'candidate_sha256':p['candidate_sha256'],
                    'decision':'unresolved','reason':'测试：空结果单独计入覆盖损失，不记作通过。'} for p in packet]
        write_json(self.review/'evaluation-decisions.json',{'items':decisions})
        report=quality_v3.score(self.work,self.review)
        self.assertFalse(report['complete_generation'])
        self.assertEqual(0,report['profiles']['holdout-v3']['accepted_targets'])
        self.assertEqual(5,report['profiles']['holdout-v3']['unresolved_targets'])
        decisions[0]['candidate_sha256']='changed'
        write_json(self.review/'evaluation-decisions.json',{'items':decisions})
        with self.assertRaisesRegex(Invalid,'Stale'):
            quality_v3.score(self.work,self.review)

    @archive_trial
    def test_transport_failure_gives_both_prompt_arms_a_turn_before_retrying(self):
        quality_v3.prepare(self.work,self.review,holdout_count=5)
        meta=read_json(self.work/'experiment.json');meta['max_total_attempts']=2
        write_json(self.work/'experiment.json',meta)
        with patch.object(provider,'read_key',return_value='TEST-NOT-A-CREDENTIAL'), \
             patch.object(provider,'complete',side_effect=provider.ProviderFailure('HTTP 429')) as send, \
             patch('builtins.print'):
            result=quality_v3.run(self.work,self.review)
        self.assertEqual(2,send.call_count)
        self.assertEqual(1,result['profiles']['holdout-v2']['attempts'])
        self.assertEqual(1,result['profiles']['holdout-v3']['attempts'])

    @archive_trial
    def test_provider_authorization_failure_stops_whole_trial_immediately(self):
        quality_v3.prepare(self.work,self.review,holdout_count=5)
        with patch.object(provider,'read_key',return_value='TEST-NOT-A-CREDENTIAL'), \
             patch.object(provider,'complete',side_effect=provider.ProviderFailure('HTTP 401',retryable=False)) as send, \
             patch('builtins.print'):
            with self.assertRaisesRegex(Invalid,'authorization'):
                quality_v3.run(self.work,self.review)
        self.assertEqual(1,send.call_count)
        quality_v3.configure_expansion_retries(self.work,self.review,authorization='测试：沿用扩词重试机制')
        with patch.object(provider,'read_key') as key,patch.object(provider,'complete') as send,patch('builtins.print'):
            with self.assertRaisesRegex(Invalid,'authorization'):
                quality_v3.run(self.work,self.review)
        key.assert_not_called();send.assert_not_called()

    def test_expansion_retries_count_historical_failures_and_skip_completed_or_content_failures(self):
        from tools.lexicon_expand import retry
        from tools.lexicon_expand.generation import GenerationFailure
        rows=[{'request_id':'pending','status':'failed','retryable':True,
               'finished_at':'2026-11-08T00:00:00+00:00'} for _ in range(29)]
        rows += [{'request_id':'done','status':'completed'},
                 {'request_id':'content','status':'failed','retryable':True,'failure_category':'content'}]
        meta={'schedule':[{'profile':'test','request_id':rid} for rid in ('pending','done','content')]}
        def attempt(*args):
            rows.append({'request_id':'pending','status':'failed','retryable':True,
                         'finished_at':'2026-11-08T00:00:00+00:00'})
            raise GenerationFailure('HTTP 503',retryable=True)
        events=[]
        with patch.object(quality_v3,'receipts',side_effect=lambda *args:rows), \
             patch.object(quality_v3,'attempt_request',side_effect=attempt) as send, \
             patch.object(retry,'wait_until') as wait:
            quality_v3.run_expansion_retries(self.work,self.review,meta,{'max_retries':29},events.append,lambda:False)
            self.assertEqual(1,send.call_count)
            self.assertEqual(30,sum(a['request_id']=='pending' for a in rows))
            self.assertEqual(1,wait.call_count)
            scheduled=next(e for e in events if e['event']=='retry_scheduled')
            self.assertEqual((29,30),(scheduled['retry_number'],scheduled['delay_seconds']))
            send.reset_mock();wait.reset_mock()
            quality_v3.run_expansion_retries(self.work,self.review,meta,{'max_retries':29},events.append,lambda:False)
            send.assert_not_called();wait.assert_not_called()

    @archive_trial
    def test_explicit_resume_extends_total_allowance_preserving_experiment_and_completed_receipts(self):
        quality_v3.prepare(self.work,self.review,holdout_count=5)
        meta=read_json(self.work/'experiment.json');meta['max_total_attempts']=2
        write_json(self.work/'experiment.json',meta)
        original=(self.work/'experiment.json').read_bytes()
        def complete(config,key,job):
            results=[{'target_id':t['target_id'],'english':t['english'],'unresolved_reason':'测试空结果','senses':[]}
                     for t in job['payload']['targets']]
            return canonical({'choices':[{'message':{'content':json.dumps({'results':results},ensure_ascii=False)},
                                         'finish_reason':'stop'}],'model':config['model']})
        with patch.object(provider,'read_key',return_value='TEST-NOT-A-CREDENTIAL'), \
             patch.object(provider,'complete',side_effect=complete) as send,patch('builtins.print'):
            quality_v3.run(self.work,self.review)
            selected=quality_v3.configure_expansion_retries(self.work,self.review,authorization='测试：继续使用扩词重试')
            self.assertEqual(2,selected['historical_attempts'])
            self.assertEqual((len(meta['schedule'])-2)*30,selected['remaining_attempt_slots'])
            self.assertEqual(2+selected['remaining_attempt_slots'],selected['max_total_attempts'])
            self.assertEqual(selected,quality_v3.configure_expansion_retries(self.work,self.review,authorization='测试重复配置'))
            send.reset_mock()
            result=quality_v3.run(self.work,self.review)
            self.assertEqual(len(meta['schedule'])-2,send.call_count)
            self.assertEqual(len(meta['schedule']),result['completed_requests'])
            send.reset_mock();quality_v3.run(self.work,self.review);send.assert_not_called()
        self.assertEqual(original,(self.work/'experiment.json').read_bytes())
        from tools.lexicon_expand.common import digest
        for row in selected['historical_receipts']:
            self.assertEqual(row['sha256'],digest((self.work/row['path']).read_bytes()))
        changed={**selected,'max_total_attempts':selected['max_total_attempts']+1}
        write_json(self.work/quality_v3.RETRY_POLICY,changed)
        write_json(self.review/quality_v3.RETRY_POLICY,changed)
        with patch.object(provider,'read_key') as key,patch.object(provider,'complete') as send:
            with self.assertRaisesRegex(Invalid,'allowance differs'):
                quality_v3.run(self.work,self.review)
        key.assert_not_called();send.assert_not_called()
        write_json(self.work/quality_v3.RETRY_POLICY,selected)
        write_json(self.review/quality_v3.RETRY_POLICY,selected)
        receipt=self.work/selected['historical_receipts'][0]['path']
        receipt.write_bytes(receipt.read_bytes()+b' ')
        with patch.object(provider,'read_key') as key,patch.object(provider,'complete') as send:
            with self.assertRaisesRegex(Invalid,'Historical experiment receipt changed'):
                quality_v3.run(self.work,self.review)
        key.assert_not_called();send.assert_not_called()

    @archive_trial
    def test_trial_budget_cannot_be_raised_past_authorized_maximum(self):
        quality_v3.prepare(self.work,self.review,holdout_count=5)
        meta=read_json(self.work/'experiment.json');meta['max_total_attempts']=61
        write_json(self.work/'experiment.json',meta)
        with patch.object(provider,'read_key') as key,patch.object(provider,'complete') as send:
            with self.assertRaisesRegex(Invalid,'authorized attempt cap'):
                quality_v3.run(self.work,self.review)
        key.assert_not_called();send.assert_not_called()

    def test_unconfirmed_reading_cannot_be_approved_without_explicit_pronunciation_evidence(self):
        sense={'quality':{'findings':[{'code':'phrase-reading-unconfirmed','severity':'review'}]}}
        decision={'decision':'accepted','reason':'语义对应成立'}
        with self.assertRaisesRegex(Invalid,'Explicit pronunciation review'):
            quality_v3.require_pronunciation_review(sense,decision)
        decision['pronunciation_review']={'confirmed':True,'reason':'逐词和语法位置复核完成',
                                         'evidence':'测试固定的整词读音证据'}
        quality_v3.require_pronunciation_review(sense,decision)
        quality_v3.require_pronunciation_review(sense,{'decision':'rejected','reason':'待修'})


if __name__=='__main__': unittest.main()
