from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.lexicon_expand import wave
from tools.lexicon_expand import quality_v3
from tools.lexicon_expand.common import Invalid, canonical, digest, read_json, write_json, write_jsonl


class WaveTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        reviews = root / 'reviews'
        baseline = reviews / 'baseline.jsonl'
        write_jsonl(baseline, [])
        for name, value in [('ROOT', root), ('REVIEWS', reviews), ('BASELINE', baseline), ('CACHE', root / 'cache')]:
            p = patch.object(wave, name, value)
            p.start()
            self.addCleanup(p.stop)
        routes = []
        for name in ('first', 'second'):
            sense = {'id': 'sense-' + name, 'chinese': '尝试', 'pos': 'n'}
            record = {'id': name, 'english': 'attempt', 'senses': [sense]}
            sha = digest(canonical(sense))
            decision = {'packet_id': name, 'decision': 'rejected', 'candidate_sha256': sha, 'reason': '意图和行为混写'}
            item = {'packet_id': name, 'target_id': name, 'candidate': sense, 'candidate_sha256': sha,
                    'source_record_sha256': digest(canonical(record)), 'decision': decision}
            folder = reviews / name
            write_json(folder / 'post-review-repair-queue.json', {'items': [item]})
            write_json(folder / 'evaluation-decisions.json', {'items': [decision]})
            write_jsonl(folder / 'external/results/drafts.jsonl', [record])
            write_jsonl(folder / 'external/plan/selected-targets.jsonl', [{'target_id': name, 'english': 'attempt'}])
            routes.append({'source_queue_path': f'reviews/{name}/post-review-repair-queue.json',
                           'packet_id': name, 'candidate_sha256': sha, 'action': 'repair',
                           'reason': '修复被拒义项', 'category': 'sense-boundary', 'focus': '只保留实际尝试的名词义'})
        routing = root / 'routing.json'
        write_json(routing, {'items': routes})
        return root, routing, routes

    def test_cross_source_repairs_freeze_each_original_and_use_new_batch_identity(self):
        _, routing, _ = self.fixture()
        with patch.object(wave, 'freeze_batch', side_effect=lambda *a, **kw: (a, kw)):
            args, kwargs = wave.prepare_repairs('new-repairs', routing)
        self.assertEqual(len(args[1]), 2)
        self.assertEqual(len({t['target_id'] for t in args[1]}), 2)
        self.assertEqual({t['original_sense']['id'] for t in args[1]}, {'sense-first', 'sense-second'})
        self.assertEqual(kwargs['task'], 'repair_senses')
        self.assertEqual(len(kwargs['sources']), 10)

    def test_stale_duplicate_and_accepted_sources_cannot_be_repaired(self):
        root, routing, routes = self.fixture()
        for kind in ('stale', 'duplicate', 'accepted'):
            current = [dict(r) for r in routes]
            if kind == 'stale':
                current[0]['candidate_sha256'] = 'stale'
            elif kind == 'duplicate':
                current.append(current[0])
            else:
                write_jsonl(wave.BASELINE, [{'id': 'sense-first'}])
            write_json(routing, {'items': current})
            with self.assertRaises(Invalid), patch.object(wave, 'freeze_batch') as freeze:
                wave.prepare_repairs('new-repairs', routing)
            freeze.assert_not_called()

    def test_path_escape_is_rejected(self):
        _, routing, routes = self.fixture()
        routes[0]['source_queue_path'] = '../outside/post-review-repair-queue.json'
        write_json(routing, {'items': routes})
        with self.assertRaisesRegex(Invalid, 'Invalid source queue'):
            wave.prepare_repairs('new-repairs', routing)

    def profile_fixture(self):
        root, routing, routes = self.fixture()
        source = wave.REVIEWS / 'first'
        profile = 'holdout-v4'
        queue_path = source / 'post-review-repair-queue.json'
        queue = read_json(queue_path)
        queue['items'][0]['profile'] = profile
        write_json(queue_path, queue)
        write_json(source / 'experiment.json', {'profiles': {profile: 'frozen-plan'}})
        for original, destination in (
                ('results/drafts.jsonl', profile + '-results/drafts.jsonl'),
                ('plan/selected-targets.jsonl', profile + '/selected-targets.jsonl')):
            target = source / 'external' / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source / 'external' / original).read_bytes())
        # A conflicting flat source must never be used for a paired-profile route.
        write_jsonl(source / 'external/results/drafts.jsonl', [])
        routes[0]['profile'] = profile
        write_json(routing, {'items': routes, 'authorization': '用户：把返修的也重跑'})
        return root, routing, routes, queue_path

    def test_profile_repairs_preserve_arm_identity_and_current_baseline(self):
        _, routing, _, _ = self.profile_fixture()
        baseline = wave.REVIEWS / 'current.jsonl'
        write_jsonl(baseline, [{'id': 'existing-sense'}])
        with patch.object(wave, 'freeze_batch', side_effect=lambda *a, **kw: (a, kw)):
            args, kwargs = wave.prepare_repairs('new-repairs', routing, baseline_path=baseline)
        self.assertEqual(args[1][0]['repair_source']['profile'], 'holdout-v4')
        self.assertEqual(args[1][0]['original_sense']['id'], 'sense-first')
        self.assertIn('reviews/first/external/holdout-v4-results/drafts.jsonl', kwargs['sources'])
        self.assertIn('reviews/first/experiment.json', kwargs['sources'])
        self.assertNotIn('reviews/first/external/results/drafts.jsonl', kwargs['sources'])
        self.assertEqual(kwargs['details']['preserved_development_senses'], 1)
        self.assertEqual(kwargs['details']['authorization'], '用户：把返修的也重跑')

    def test_missing_wrong_or_escaping_profile_is_rejected_before_freeze(self):
        _, routing, routes, queue_path = self.profile_fixture()
        for profile in (None, 'holdout-v3', '../outside'):
            routes[0]['profile'] = profile
            if profile == '../outside':
                queue = read_json(queue_path)
                queue['items'][0]['profile'] = profile
                write_json(queue_path, queue)
            write_json(routing, {'items': routes})
            with self.subTest(profile=profile), patch.object(wave, 'freeze_batch') as freeze:
                with self.assertRaisesRegex(Invalid, 'profile'):
                    wave.prepare_repairs('new-repairs', routing)
                freeze.assert_not_called()

    def test_current_baseline_blocks_already_adopted_repair(self):
        _, routing, _, _ = self.profile_fixture()
        baseline = wave.REVIEWS / 'current.jsonl'
        write_jsonl(baseline, [{'id': 'sense-first'}])
        with self.assertRaisesRegex(Invalid, 'Stale repair source'), patch.object(wave, 'freeze_batch') as freeze:
            wave.prepare_repairs('new-repairs', routing, baseline_path=baseline)
        freeze.assert_not_called()

    def trial(self, rows):
        root, _, _ = self.fixture()
        provider = {'max_output_tokens': 4096}
        meta = {'profiles': {'holdout-v3': 'sha'}, 'schedule': [
            {'profile': 'holdout-v3', 'request_id': 'request'}], 'provider': provider,
            'max_total_attempts': 30, 'max_reserved_output_tokens': 30 * 4096}
        for name, value in [('prepare_trial', meta), ('load_config', provider), ('receipts', rows),
                            ('status', {'attempts': len(rows), 'reserved_output_tokens': len(rows) * 4096,
                                        'uncertain_attempts': sum(r['status'] == 'started' for r in rows),
                                        'completed_requests': sum(r['status'] == 'completed' for r in rows),
                                        'planned_requests': 1}), ('archive', {})]:
            p = patch.object(wave, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        return root

    def test_trial_success_is_reused_without_new_call(self):
        self.trial([{'request_id': 'request', 'status': 'completed'}])
        with patch.object(wave, 'generate') as generate:
            result = wave.run_trial('trial')
        generate.assert_not_called()
        self.assertEqual(result['status'], 'completed')

    def test_trial_unknown_outcome_blocks_and_content_failure_is_not_retried(self):
        self.trial([{'request_id': 'request', 'status': 'started'}])
        with patch.object(wave, 'generate') as generate:
            with self.assertRaisesRegex(Invalid, 'uncertain'):
                wave.run_trial('trial')
        generate.assert_not_called()

    def test_trial_content_failure_reports_incomplete_without_new_call(self):
        self.trial([{'request_id': 'request', 'status': 'failed', 'failure_category': 'content'}])
        with patch.object(wave, 'generate') as generate:
            result = wave.run_trial('trial')
        generate.assert_not_called()
        self.assertEqual(result['status'], 'incomplete')

    def test_v3_v4_score_keeps_empty_results_as_coverage_loss(self):
        root, _, _ = self.fixture()
        work, review = root / 'trial', root / 'review'
        write_json(work / 'experiment.json', {'profiles': {'holdout-v3':'sha3','holdout-v4':'sha4'}})
        packet, key, decisions = [], {}, []
        for v in (3,4):
            pid = f'candidate-{v}'
            packet.append({'packet_id':pid,'candidate':None,'candidate_sha256':digest(canonical(None))})
            key[pid] = {'profile':f'holdout-v{v}','record':{'id':'target'}}
            decisions.append({'packet_id':pid,'candidate_sha256':digest(canonical(None)),
                              'decision':'unresolved','reason':'测试：空结果不算通过。'})
        write_json(review / 'evaluation-decisions.json', {'items':decisions})
        with patch.object(quality_v3, 'review_packet', return_value=(packet,key)), \
             patch.object(quality_v3, 'load_plan', return_value=({'maximum_items':1},[])), \
             patch.object(quality_v3, 'receipts', return_value=[]), \
             patch.object(quality_v3, 'status', return_value={'completed_requests':2,'planned_requests':2,'uncertain_attempts':0}):
            result = quality_v3.score(work,review,versions=(3,4),group_names=('holdout',),preserved_senses=943)
        self.assertEqual(result['paired_returned_targets'], {'holdout':1})
        self.assertEqual(result['preserved_product_accepted_senses'],943)
        self.assertEqual(result['profiles']['holdout-v4']['accepted_targets'],0)
        self.assertEqual(result['profiles']['holdout-v4']['unresolved_targets'],1)

    def test_expansion_reuses_frozen_plan_and_rejects_silent_version_change(self):
        self.fixture()
        work, review = wave.folders('expansion')
        meta = {'prompt_version':3, 'targets':100}
        for folder in (work,review):
            write_json(folder / 'batch-plan.json',meta)
        with patch.object(wave,'load_plan') as load, patch.object(wave,'unseen_targets') as select:
            self.assertEqual(wave.prepare_expansion('expansion',version=3),meta)
            with self.assertRaisesRegex(Invalid,'Frozen expansion differs'):
                wave.prepare_expansion('expansion',version=4)
        load.assert_called_once()
        select.assert_not_called()

    def test_expansion_freezes_selection_snapshot_without_guarding_active_receipts(self):
        self.fixture()
        _, review = wave.folders('expansion')
        write_json(review / 'version-selection.json',{'selected_prompt_version':3})
        write_jsonl(wave.REVIEWS / 'adopted-expansion-b-20261110/accepted-senses.jsonl',[])
        with patch.object(wave,'unseen_targets',return_value=([{}]*100, {'active/drafts.jsonl':'sha'},['old'])), \
             patch.object(wave,'freeze_batch',side_effect=lambda *a,**kw:kw):
            result = wave.prepare_expansion('expansion',version=3)
        self.assertEqual(len(result['sources']),3)
        self.assertNotIn('active/drafts.jsonl',result['sources'])
        self.assertEqual(result['details']['maximum_automatic_batches'],1)


if __name__ == '__main__':
    unittest.main()
