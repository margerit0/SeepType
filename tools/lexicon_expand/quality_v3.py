"""Classified sense repair and matched v2/v3 trials with immutable evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from tools.lexicon_expand.catalog import load_prepared
from tools.lexicon_expand.common import (CACHE, ROOT, Invalid, canonical, digest, english,
    generated_directory, read_json, read_jsonl, require, word_key, write_json, write_jsonl)
from tools.lexicon_expand.generation import generate, read_attempts, run_lock
from tools.lexicon_expand.planning import PROMPTS, load_plan, make_job, save_plan, select_targets
from tools.lexicon_expand.quality import policy
from tools.lexicon_expand.repair_trial import unchanged_file

WORK = CACHE / 'generation-v3-20261109'
REVIEW = ROOT / 'data/lexicon-expansion/reviews/generation-v3-20261109'
BATCH = ROOT / 'data/lexicon-expansion/reviews/next-100-20261109'
EXAMPLES = {'may', 'refund', 'menu', 'wear', 'record', 'claim', 'date', 'afford',
            'rely', 'rely on', 'rely upon', 'put on'}
CATEGORIES = {'pinyin-format', 'context-pronunciation', 'sense-boundary',
              'action-state', 'scope-restriction', 'fixed-phrase'}
MAX_ATTEMPTS = 60
RETRY_POLICY = 'expansion-retry-policy.json'


def target_fields(row):
    return {'target_id': row['id'], **{k: row.get(k, []) for k in
        ('english', 'source_forms', 'packs', 'cefr_levels', 'parts_of_speech',
         'source_refs', 'dictionary_references', 'existing_entries')}}


def save_profile(directory, targets, prompt_version, manifest, *, task='map_targets', sources=None):
    prompt = PROMPTS[prompt_version].read_text(encoding='utf-8')
    selected_policy = policy(2)
    jobs = [make_job(task, targets[i:i+5], prompt, response_version=3, quality_policy=selected_policy)
            for i in range(0, len(targets), 5)]
    plan = {'schema_version': 3, 'status': 'offline-plan-not-executed',
            'prompt_version': prompt_version, 'response_schema_version': 3,
            'quality_policy': selected_policy, 'prompt_sha256': digest(prompt.encode('utf-8')),
            'prepared_directory': str((CACHE/'prepared').resolve()),
            'catalog_manifest_sha256': digest(canonical(manifest)),
            'maximum_items': len(targets), 'maximum_senses_per_item': 1 if task=='repair_senses' else 3,
            'request_count': len(jobs), 'batch_size': 5, 'automatic_adoption': False,
            'review_sources': sources or {}}
    return save_plan(directory, plan, jobs, targets, prompt)


def prepare(work=WORK, review=REVIEW, *, holdout_count=20):
    work, review = generated_directory(work), Path(review)
    require(type(holdout_count) is int and 5 <= holdout_count <= 40, 'Holdout size must be 5 to 40')
    catalog, _, manifest = load_prepared()
    by_id = {t['id']: t for t in catalog}
    queue = read_json(BATCH/'repair-queue.json')['items']
    routes = read_json(REVIEW/'repair-routing.json')['items']
    routing = {r['sense_id']: r for r in routes}
    require(len(routes)==len(routing)==len(queue) and set(routing)=={r['sense_id'] for r in queue},
            'Each queued sense needs exactly one explicit repair category')
    accepted = read_jsonl(BATCH/'accepted-senses.jsonl')
    require(not {r['id'] for r in accepted} & set(routing), 'Accepted sense reached repair queue')
    records = {r['id']:r for r in read_jsonl(BATCH/'external/results/drafts.jsonl')}
    sources = {p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in
               (BATCH/'repair-queue.json', BATCH/'decisions.tsv', REVIEW/'repair-routing.json')}
    repairs, phrases, regression = [], [], []
    for item in queue:
        route = routing[item['sense_id']]
        require(route['category'] in CATEGORIES and route['focus'].strip(), 'Invalid repair category')
        record = records[item['target_id']]
        original = next(s for s in record['senses'] if s['id']==item['sense_id'])
        require(original==item['candidate'] and digest(canonical(original))==item['candidate_sha256'],
                'Queued candidate differs from external evidence')
        target = target_fields(by_id[item['target_id']])
        regression.append(target)
        if item['decision']=='deferred':
            require(route['category']=='fixed-phrase' and route.get('phrase_candidates'),
                    'Deferred fixed target requires explicit phrase candidates')
            for phrase in route['phrase_candidates']:
                english(phrase)
                require(word_key(phrase)!=word_key(item['english']), 'Phrase must have a separate identity')
                phrases.append({'id':'phrase-'+digest(canonical([item['sense_id'],phrase]))[:24],
                    'english':phrase,'original_target_id':item['target_id'],'original_sense_id':item['sense_id'],
                    'candidate_sha256':item['candidate_sha256'],'reason':item['reason'],
                    'status':'proposed-separate-target-not-generated','adopted':False})
            continue
        require(item['decision']=='rejected' and route['category']!='fixed-phrase', 'Invalid repair disposition')
        repairs.append({**target,'target_id':'repair-'+digest(canonical([item['target_id'],item['sense_id'],3]))[:24],
            'original_target_id':item['target_id'],'original_sense':original,
            'source_record_sha256':digest(canonical(record)), 'review_reason':item['reason'],
            'repair_category':route['category'],'repair_focus':route['focus']})
    require(len({t['target_id'] for t in regression})==len(regression), 'Repeated regression target')
    excluded = {word_key(r['commit_english']) for r in accepted}
    for path in (ROOT/'data/lexicon-expansion/reviews/pilot-300-20261109/source-drafts.jsonl',
                 BATCH/'external/results/drafts.jsonl'):
        excluded.update(word_key(r['english']) for r in read_jsonl(path))
    from tools.lexicon import pipeline as legacy
    excluded.update(word_key(r['commit_english']) for r in legacy.validate().entries)
    excluded.update(EXAMPLES)
    holdout = select_targets([t for t in catalog if word_key(t['english']) not in excluded], holdout_count)
    require(len(holdout)==holdout_count, 'Insufficient held-out targets')
    groups = {'regression':regression, 'holdout':[target_fields(t) for t in holdout]}
    profiles = {}
    for group, targets in groups.items():
        for version in (2,3):
            name = f'{group}-v{version}'
            profiles[name] = save_profile(work/name, targets, version, manifest)
    profiles['repairs-v3'] = save_profile(work/'repairs-v3', repairs, 3, manifest,
                                        task='repair_senses', sources=sources)
    schedule=[]
    # Interleave prompt versions; alternate which version goes first in each block.
    for group in ('holdout','regression'):
        count = profiles[group+'-v2']['request_count']
        for i in range(count):
            for version in ((2,3) if i%2==0 else (3,2)):
                name=f'{group}-v{version}'
                schedule.append({'profile':name,'request_id':load_plan(work/name)[1][i]['id']})
    schedule += [{'profile':'repairs-v3','request_id':j['id']} for j in load_plan(work/'repairs-v3')[1]]
    summary={'schema_version':1,'authorization':'用户：开始执行；实施v3提示词、读音复核、分类返修与小规模对照验证。',
        'profiles':{n:digest(canonical(p)) for n,p in profiles.items()},'schedule':schedule,
        'holdout_targets':holdout_count,'regression_targets':len(regression),'repair_senses':len(repairs),
        'phrase_candidates':len(phrases),'preserved_accepted_senses':len(accepted),
        'excluded_prompt_examples':sorted(EXAMPLES),'quality_policy_both_arms':policy(2),
        'max_total_attempts':MAX_ATTEMPTS,'max_reserved_output_tokens':MAX_ATTEMPTS*4096,
        'max_attempts_per_request':30,'max_wait_seconds':30,'automatic_adoption':False,
        'evaluation_rules':['Identical provider/model/parameters and quality policy in both arms.',
            'Regressions are exposed development examples and cannot measure generalization.',
            'Holdout targets exclude previous batches, existing lexicon and all prompt examples.',
            'Report accepted targets, accepted senses, unresolved targets and defects separately.',
            'Semantic decisions must be independently authored; lookup and fewer senses are not quality wins.']}
    from tools.lexicon_expand.provider import load_config
    selected_provider=load_config(CACHE/'api.local.json')
    require(selected_provider==read_json(BATCH/'external/results/run.json')['provider'],
            'Use the previously authorized provider and generation parameters')
    require(selected_provider['max_output_tokens']==4096, 'Experiment reservation requires 4096 tokens per call')
    summary['provider']=selected_provider
    unchanged_file(work/'experiment.json',(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    unchanged_file(review/'experiment.json',(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    write_json(review/'phrase-candidates.json',{'schema_version':1,'items':phrases})
    return summary


def receipts(work, profile):
    output=work/(profile+'-results')
    if not (output/'run.json').exists(): return []
    plan,jobs=load_plan(work/profile)
    run=read_json(output/'run.json')
    require(run['provider']==read_json(work/'experiment.json')['provider'], 'Trial provider differs between arms')
    require(run['identity']==digest(canonical({'plan':plan,'provider':run['provider']})), 'Experiment identity changed')
    return read_attempts(output,jobs,run['identity'])


def status(work=WORK):
    work=Path(work)
    meta=read_json(work/'experiment.json')
    rows={name:receipts(work,name) for name in meta['profiles']}
    return {'recorded_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'attempts':sum(len(a) for a in rows.values()),
        'completed_requests':sum(a['status']=='completed' for aa in rows.values() for a in aa),
        'planned_requests':len(meta['schedule']),
        'uncertain_attempts':sum(a['status']=='started' for aa in rows.values() for a in aa),
        'reserved_output_tokens':sum(a['reserved_output_tokens'] for aa in rows.values() for a in aa),
        'profiles':{name:{'attempts':len(aa),'completed_requests':sum(a['status']=='completed' for a in aa),
            'returned_targets':sum(len(a['records']) for a in aa if a['status']=='completed')}
                    for name,aa in rows.items()}}


def archive(work=WORK, review=REVIEW):
    work,review=Path(work),Path(review)
    for name in read_json(work/'experiment.json')['profiles']:
        for folder in (name,name+'-results'):
            for p in sorted((work/folder).rglob('*')):
                if p.is_file() and p.suffix in ('.json','.jsonl','.txt'):
                    if p.parent.name=='attempts' and read_json(p)['status']=='started': continue
                    destination=review/'external'/folder/p.relative_to(work/folder)
                    if destination.exists() and destination.read_bytes()!=p.read_bytes():
                        require(p.name in ('summary.json','drafts.jsonl','quality-issues.jsonl'), 'Immutable trial evidence changed')
                        unchanged_file(review/'external/history'/(digest(destination.read_bytes())+'-'+p.name),destination.read_bytes())
                        from tools.lexicon import pipeline as legacy
                        legacy.atomic_write(destination,p.read_bytes())
                    else: unchanged_file(destination,p.read_bytes())
    report=status(work)
    write_json(review/'generation-progress.json',report)
    return report


def review_packet(work=WORK,review=REVIEW):
    """Hide the prompt arm while retaining a hash-bound scoring key."""
    work,review=Path(work),Path(review)
    packet,key=[],{}
    for name in read_json(work/'experiment.json')['profiles']:
        targets={t['target_id']:t for t in read_jsonl(work/name/'selected-targets.jsonl')}
        for attempt in receipts(work,name):
            if attempt['status']!='completed': continue
            for record in attempt['records']:
                for sense in record['senses'] or [None]:
                    pid='candidate-'+digest(canonical([name,record['id'],sense]))[:24]
                    packet.append({'packet_id':pid,'english':record['english'],
                        'group':name.rsplit('-v',1)[0], 'candidate':sense,
                        'candidate_sha256':digest(canonical(sense)),
                        'unresolved_reason':record['unresolved_reason']})
                    if 'original_sense' in targets[record['id']]:
                        target=targets[record['id']]
                        packet[-1]['repair_context']={k:target[k] for k in
                            ('original_sense','repair_category','repair_focus','review_reason')}
                    key[pid]={'profile':name,'record':record,'sense_id':sense['id'] if sense else None}
    packet.sort(key=lambda row:row['packet_id'])
    write_json(review/'review-packet.json',{'schema_version':1,'items':packet,
        'instruction':'逐项独立审核，不能根据词典命中或程序标记自动批准。此文件隐藏prompt组别，实际生成来源保存在独立评分键。'})
    write_json(work/'review-key.json',key)
    return packet,key


def require_pronunciation_review(sense,decision):
    flags={f['code'] for f in sense['quality']['findings']}
    if decision['decision']=='accepted' and flags & {
            'phrase-reading-unconfirmed','word-reading-unconfirmed','character-reading-unknown'}:
        confirmation=decision.get('pronunciation_review',{})
        require(confirmation.get('confirmed') is True and
                isinstance(confirmation.get('reason'),str) and confirmation['reason'].strip() and
                isinstance(confirmation.get('evidence'),str) and confirmation['evidence'].strip(),
                'Explicit pronunciation review and evidence required for an unconfirmed phrase reading')


def packet_summary(work=WORK,review=REVIEW):
    packet,_=review_packet(work,review)
    return {'candidates':len(packet),'review_packet':str(Path(review)/'review-packet.json'),
            'prompt_versions_hidden':True}


def score(work=WORK,review=REVIEW, *, versions=(2,3), group_names=('holdout','regression'),
          preserved_senses=665):
    """Require authored decisions for every returned sense and unresolved target."""
    work,review=Path(work),Path(review)
    packet,key=review_packet(work,review)
    require(bool(packet),'No returned candidates to review')
    decisions=read_json(review/'evaluation-decisions.json')['items']
    by_id={r['packet_id']:r for r in decisions}
    require(len(by_id)==len(decisions)==len(packet) and set(by_id)==set(key),
            'Each returned candidate needs exactly one authored evaluation decision')
    groups={}
    require(len(versions)==2 and versions[0] != versions[1], 'Comparison requires two different prompt versions')
    accepted_repairs=[]
    for name in read_json(work/'experiment.json')['profiles']:
        plan,_=load_plan(work/name)
        aa=receipts(work,name)
        groups[name]={'planned_targets':plan['maximum_items'],'returned_targets':0,
            'accepted_targets':0,'returned_senses':0,'accepted_senses':0,'rejected_senses':0,
            'deferred_senses':0,'unresolved_targets':0,'attempts':len(aa),
            'reserved_output_tokens':sum(a['reserved_output_tokens'] for a in aa),
            'failed_attempts_by_category': {category:sum(a.get('failure_category')==category for a in aa)
                                          for category in ('transport','content','credential-echo')},
            'provider_reported_usage': {field:sum(a.get('usage',{}).get(field,0) for a in aa)
                                       for field in ('prompt_tokens','completion_tokens','total_tokens')},
            'attempts_with_reported_usage':sum(bool(a.get('usage')) for a in aa),
            'elapsed_seconds': ((datetime.fromisoformat(aa[-1].get('finished_at',aa[-1]['started_at'])) -
                                 datetime.fromisoformat(aa[0]['started_at'])).total_seconds() if aa else 0)}
    targets={name:set() for name in groups}
    accepted_targets={name:set() for name in groups}
    for item in packet:
        decision=by_id[item['packet_id']]
        require(decision['candidate_sha256']==item['candidate_sha256'] and decision['reason'].strip(),
                'Stale or unexplained evaluation decision')
        verdict=decision['decision']
        require(verdict in ('accepted','rejected','deferred','unresolved'),'Invalid evaluation verdict')
        origin=key[item['packet_id']]
        name,record=origin['profile'],origin['record']
        targets[name].add(record['id'])
        sense=item['candidate']
        if sense is None:
            require(verdict=='unresolved','Empty model result cannot be accepted')
            groups[name]['unresolved_targets']+=1
            continue
        require(verdict!='unresolved','A returned sense needs a semantic decision')
        groups[name]['returned_senses']+=1
        groups[name][verdict+'_senses']+=1
        if verdict=='accepted':
            require(sense['quality']['disposition']!='blocked','Blocked evaluation candidate cannot be accepted')
            require_pronunciation_review(sense,decision)
            accepted_targets[name].add(record['id'])
            if 'repair_context' in item:
                require(sense['pos']==item['repair_context']['original_sense']['pos'],
                        'Repair changed the original part-of-speech intent')
                accepted_repairs.append({'repair_of':record['repair_of'],'candidate':sense,
                    'generation':record['generation'],'decision':decision,'adopted':False})
    for name,row in groups.items():
        row['returned_targets']=len(targets[name]);row['accepted_targets']=len(accepted_targets[name])
    progress=status(work)
    complete=progress['completed_requests']==progress['planned_requests'] and progress['uncertain_attempts']==0
    paired={g:len(targets[f'{g}-v{versions[0]}'] & targets[f'{g}-v{versions[1]}']) for g in group_names}
    comparable=all(groups['holdout-v'+str(v)]['returned_targets']==
                   groups['holdout-v'+str(v)]['planned_targets'] for v in versions)
    result={'schema_version':1,'recorded_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'complete_generation':complete,'complete_review_of_returned_candidates':True,
        'paired_returned_targets':paired,'holdout_comparison_complete':comparable,
        'observed_holdout_accepted_target_delta':
            groups[f'holdout-v{versions[1]}']['accepted_targets']-groups[f'holdout-v{versions[0]}']['accepted_targets'] if comparable else None,
        'compared_prompt_versions':list(versions),
        'measured_general_quality_improvement':None,
        'profiles':groups,'generation':progress,'review_method':'user-delegated-agent-semantic-review',
        'limitations':['Single small same-provider sample; no broad accuracy or statistical significance claim.',
            'Regressions were visible in v3 prompt and are not held-out generalization evidence.',
            'Unreturned and unresolved targets count as coverage loss; fewer senses alone is not improvement.',
            'Do not attribute unequal transport completion to prompt semantic quality.',
            'Reviewer could see run progress; hidden version labels are not a strict blinded design.'],
        'automatic_adoption':False,'preserved_product_accepted_senses':preserved_senses,
        'decisions_sha256':digest((review/'evaluation-decisions.json').read_bytes())}
    write_json(review/'accepted-repair-candidates.json',{'schema_version':1,'items':accepted_repairs,'adopted':False})
    write_json(review/'evaluation-summary.json',result)
    return result


class BudgetReached(Invalid): pass


def expansion_retry_limits(meta, attempts):
    """Completed requests are reused; all historical attempts count toward thirty."""
    ids=[item['request_id'] for item in meta['schedule']]
    require(len(ids)==len(set(ids)), 'Duplicate experiment request identity')
    require(all(a['request_id'] in ids for a in attempts), 'Unknown experiment receipt')
    completed={a['request_id'] for a in attempts if a['status']=='completed'}
    remaining=sum(max(0,30-sum(a['request_id']==rid for a in attempts))
                  for rid in ids if rid not in completed)
    return {'historical_attempts':len(attempts),'historical_completed_requests':len(completed),
        'remaining_attempt_slots':remaining,'max_total_attempts':len(attempts)+remaining,
        'max_reserved_output_tokens':sum(a['reserved_output_tokens'] for a in attempts)+remaining*4096}


def validate_experiment(work, meta):
    from tools.lexicon_expand.provider import load_config
    require(load_config(CACHE/'api.local.json')==meta['provider'], 'Experiment provider configuration changed')
    require(type(meta['max_total_attempts']) is int and 0 < meta['max_total_attempts'] <= MAX_ATTEMPTS,
            'Experiment exceeds the authorized attempt cap')
    require(type(meta['max_attempts_per_request']) is int and 1 <= meta['max_attempts_per_request'] <= 30,
            'Experiment exceeds the authorized per-request cap')
    require(type(meta['max_reserved_output_tokens']) is int and
            4096 <= meta['max_reserved_output_tokens'] <= MAX_ATTEMPTS*4096,
            'Experiment exceeds the authorized output reservation')
    for name,expected in meta['profiles'].items():
        require(digest(canonical(load_plan(work/name)[0]))==expected, 'Experiment plan changed')


def expansion_retry_policy(work, review, meta):
    path=work/RETRY_POLICY
    if not path.exists(): return None
    selected=read_json(path)
    require(path.read_bytes()==(review/RETRY_POLICY).read_bytes(), 'Experiment retry policy copies differ')
    require(selected['experiment_sha256']==digest((work/'experiment.json').read_bytes()),
            'Experiment changed after retry authorization')
    require(selected['authorization'].strip() and selected['max_attempts_per_request']==30 and
            selected['max_retries']==29 and selected['max_wait_seconds']==30 and
            selected['mechanism']=='tools.lexicon_expand.retry.retry_request', 'Invalid expansion retry policy')
    historical=[]
    for receipt in selected['historical_receipts']:
        path=work/receipt['path']
        require(path.parent in {work/(n+'-results')/'attempts' for n in meta['profiles']} and
                digest(path.read_bytes())==receipt['sha256'], 'Historical experiment receipt changed')
        historical.append(read_json(path))
    require(len({r['path'] for r in selected['historical_receipts']})==len(historical),
            'Duplicate historical experiment receipt')
    require(all(selected[k]==v for k,v in expansion_retry_limits(meta,historical).items()),
            'Experiment retry allowance differs from historical receipts')
    return selected


def configure_expansion_retries(work=WORK, review=REVIEW, *, authorization):
    """Record an explicit resume allowance without rewriting the original experiment."""
    work,review=Path(work),Path(review)
    require(isinstance(authorization,str) and authorization.strip(), 'Retry authorization is required')
    with run_lock(work):
        meta=read_json(work/'experiment.json')
        validate_experiment(work,meta)
        if (work/RETRY_POLICY).exists(): return expansion_retry_policy(work,review,meta)
        attempts=[a for name in meta['profiles'] for a in receipts(work,name)]
        require(not any(a['status']=='started' for a in attempts),
                'Inspect uncertain experiment requests before configuring retries')
        selected={'schema_version':1,'authorization':authorization,
            'recorded_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'experiment_sha256':digest((work/'experiment.json').read_bytes()),
            'mechanism':'tools.lexicon_expand.retry.retry_request',
            'max_attempts_per_request':30,'max_retries':29,'max_wait_seconds':30,
            'historical_receipts':[{'path':p.relative_to(work).as_posix(),'sha256':digest(p.read_bytes())}
                for name in meta['profiles'] for p in sorted((work/(name+'-results')/'attempts').glob('*.json'))],
            **expansion_retry_limits(meta,attempts)}
        raw=(json.dumps(selected,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        unchanged_file(review/RETRY_POLICY,raw)
        unchanged_file(work/RETRY_POLICY,raw)
        return selected


def attempt_request(work, review, caps, item, emit):
    current=status(work)
    if current['attempts']>=caps['max_total_attempts']:
        raise BudgetReached('Experiment cumulative attempt budget reached')
    if current['reserved_output_tokens']+4096>caps['max_reserved_output_tokens']:
        raise BudgetReached('Experiment cumulative output reservation reached')
    require(current['uncertain_attempts']==0,'Inspect uncertain experiment requests before resuming')
    name,rid=item['profile'],item['request_id']
    aa=receipts(work,name)
    try:
        generate(work/name,CACHE/'api.local.json',work/(name+'-results'),execute=True,
            max_items=40,max_requests=len(aa)+1,
            max_output_budget=sum(a['reserved_output_tokens'] for a in aa)+4096,
            retry_failed=True,request_ids=[rid],progress=lambda e:emit({'profile':name,**e}))
    finally:
        archive(work,review)


def run_expansion_retries(work, review, meta, caps, emit, cancelled):
    from tools.lexicon_expand.retry import retry_request
    for item in meta['schedule']:
        name,rid=item['profile'],item['request_id']
        def history():
            return [{**a,'retryable':False} if a.get('failure_category')=='content' else a
                    for a in receipts(work,name) if a['request_id']==rid]
        ok=retry_request(lambda:attempt_request(work,review,caps,item,emit),history,
                         max_retries=caps['max_retries'],emit=lambda e:emit({'profile':name,'request_id':rid,**e}),
                         cancelled=cancelled)
        emit({'event':'request_finished','profile':name,'request_id':rid,'success':ok})
        if not ok and history()[-1].get('failure_scope')=='provider':
            raise Invalid('Provider configuration or authorization error; experiment stopped')


def run(work=WORK,review=REVIEW):
    from tools.lexicon_expand.generation import GenerationFailure
    from tools.lexicon_expand.retry import retry_delay, wait_until
    work,review=Path(work),Path(review)
    meta=read_json(work/'experiment.json')
    validate_experiment(work,meta)
    emit=lambda e:print(json.dumps(e,ensure_ascii=False),flush=True)
    cancelled=lambda:(work/'stop.json').exists()
    with run_lock(work):
        selected=expansion_retry_policy(work,review,meta)
        try:
            if selected:
                emit({'event':'retry_policy','mechanism':selected['mechanism'],
                      **{k:selected[k] for k in ('max_attempts_per_request','max_total_attempts',
                          'max_reserved_output_tokens','historical_attempts','remaining_attempt_slots')}})
                run_expansion_retries(work,review,meta,selected,emit,cancelled)
            while not selected:
                attempted=False
                deadlines=[]
                pending=False
                for item in meta['schedule']:
                    require(not cancelled(),'Experiment was stopped')
                    name,rid=item['profile'],item['request_id']
                    aa=receipts(work,name)
                    history=[a for a in aa if a['request_id']==rid]
                    if any(a['status']=='completed' for a in history): continue
                    require(not any(a['status']=='started' for a in history),
                            'Inspect uncertain experiment requests before resuming')
                    failures=[a for a in history if a['status']=='failed']
                    if failures:
                        last=failures[-1]
                        if last.get('failure_scope')=='provider':
                            raise Invalid('Provider configuration or authorization error; experiment stopped')
                        if len(failures)>=meta['max_attempts_per_request'] or not last.get('retryable') or last.get('failure_category')=='content':
                            continue
                        due=datetime.fromisoformat(last['finished_at'])+timedelta(seconds=retry_delay(len(failures)))
                        if due>datetime.now(timezone.utc):
                            deadlines.append(due);pending=True;continue
                    pending=True
                    try:
                        attempt_request(work,review,meta,item,emit)
                        ok=True
                    except GenerationFailure:
                        ok=False
                    attempted=True
                    emit({'event':'request_finished','profile':name,'request_id':rid,'success':ok})
                    if not ok and receipts(work,name)[-1].get('failure_scope')=='provider':
                        raise Invalid('Provider configuration or authorization error; experiment stopped')
                if not pending: break
                if not attempted and deadlines:
                    wait_until(min(deadlines).isoformat(timespec='seconds'),emit,cancelled)
        except BudgetReached as error:
            emit({'event':'budget_stopped','reason':str(error)})
        except Invalid:
            if not cancelled(): raise
            emit({'event':'stopped','reason':'Stop marker requested; receipts and budgets retained'})
        finally:
            archive(work,review)
    return status(work)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['plan','run','archive','status','review-packet','score','configure-retries'])
    parser.add_argument('--authorization',help='Explicit instruction authorizing expansion-style retry allowances')
    args=parser.parse_args()
    result=(configure_expansion_retries(authorization=args.authorization) if args.command=='configure-retries'
            else {'plan':prepare,'run':run,'archive':archive,'status':status,
                  'review-packet':packet_summary,'score':score}[args.command]())
    print(json.dumps(result,ensure_ascii=False,indent=2))
