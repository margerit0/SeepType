import copy
import unittest

from tools.lexicon_expand.adoption import resolve
from tools.lexicon_expand.common import Invalid, canonical, digest


class AdoptionTests(unittest.TestCase):
    def source(self, pid='one', pos='n', sid='sense-one'):
        sense = dict(id=sid, chinese='记录', pinyin='ji4 lu4', commit_english='record',
                     display_english='record', pos=pos, meaning_zh='记下的信息')
        sha = digest(canonical(sense))
        return dict(packet_id=pid, english='record', target_id='target-' + pid, packs=['ielts'],
                    candidate=sense, generation={'request_id': pid},
                    source_record_sha256='source-hash',
                    decision={'decision': 'accepted', 'candidate_sha256': sha, 'reason': '独立语义复审通过'})

    def route(self, source, action='adopt', destination=None):
        return dict(packet_id=source['packet_id'], candidate_sha256=digest(canonical(source['candidate'])),
                    action=action, destination=destination or source['packet_id'], reason='显式采用此原稿版本')

    def test_preserves_baseline_and_combines_reviewed_version_provenance(self):
        first = self.source()
        second = self.source('two', sid='sense-two')
        base = [dict(id='old', verdict='accepted', chinese='旧', pinyin='jiu4', commit_english='old', pos='adj')]
        original = copy.deepcopy(base)
        result, provenance = resolve(base, [first, second], [self.route(first), self.route(second, 'merge-reviewed-version', 'one')])
        self.assertEqual(base, original)
        self.assertEqual(result[:1], original)
        self.assertEqual(len(result), 2)
        self.assertEqual(len(provenance['one']), 2)
        self.assertEqual(result[1]['meaning_zh'], first['candidate']['meaning_zh'])

    def test_record_noun_and_verb_cannot_be_folded(self):
        noun = self.source()
        verb = self.source('two', pos='v', sid='sense-two')
        with self.assertRaisesRegex(Invalid, 'part of speech'):
            resolve([], [noun, verb], [self.route(noun), self.route(verb, 'merge-reviewed-version', 'one')])
        result, _ = resolve([], [noun, verb], [self.route(noun), self.route(verb)])
        self.assertEqual({r['pos'] for r in result}, {'n', 'v'})

    def test_stale_candidate_or_missing_route_is_rejected(self):
        source = self.source()
        route = self.route(source)
        source['candidate']['meaning_zh'] = '已被改写'
        with self.assertRaisesRegex(Invalid, 'hash'):
            resolve([], [source], [route])
        with self.assertRaisesRegex(Invalid, 'Incomplete'):
            resolve([], [source], [])

    def test_unaccepted_source_cannot_be_adopted(self):
        source = self.source()
        source['decision']['decision'] = 'deferred'
        with self.assertRaisesRegex(Invalid, 'Unaccepted'):
            resolve([], [source], [self.route(source)])

    def test_baseline_duplicate_requires_exact_part_of_speech(self):
        source = self.source()
        base = [{**source['candidate'], 'id': 'base', 'pos': 'v', 'verdict': 'accepted'}]
        with self.assertRaisesRegex(Invalid, 'part of speech'):
            resolve(base, [source], [self.route(source, 'already-in-baseline', 'base')])

    def test_selected_id_collision_and_unselected_merge_are_rejected(self):
        one = self.source()
        two = self.source('two')
        with self.assertRaisesRegex(Invalid, 'IDs collide'):
            resolve([], [one, two], [self.route(one), self.route(two)])
        with self.assertRaisesRegex(Invalid, 'not adopted'):
            resolve([], [one, two], [self.route(one, 'merge-reviewed-version', 'two'),
                                   self.route(two, 'merge-reviewed-version', 'one')])
