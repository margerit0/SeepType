"""Small, auditable representation changes; never infer words or meanings."""
import json
import re

from tools.lexicon_expand.common import Invalid, canonical, digest, require


class ResponseValidationError(Invalid):
    def __init__(self, message, path='$'):
        super().__init__(message)
        self.detail = {'code': re.sub('[^a-z0-9]+', '-', message.lower()).strip('-'),
                       'path': path, 'message': message}


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ResponseValidationError('Duplicate JSON key')
        result[key] = value
    return result


def normalize_reply(content, *, expected_metadata=None):
    require(isinstance(content, str), 'Provider returned non-text content')
    require(len(content.encode('utf-8')) <= 2 * 1024 * 1024, 'Oversized model content')
    changes = []
    fenced = re.fullmatch(r'\s*```(?:json)?\r?\n([\s\S]*?)\r?\n```\s*', content)
    if fenced:
        content = fenced[1]
        changes.append({'rule': 'complete-json-fence', 'path': '$'})
    try:
        reply = json.loads(content, object_pairs_hook=unique_keys)
    except json.JSONDecodeError as error:
        raise ResponseValidationError('Invalid JSON response', f'$ (line {error.lineno}, column {error.colno})') from None
    if (expected_metadata is not None and isinstance(reply, dict) and
            set(reply) == {'results', 'response_schema_version', 'quality_policy'}):
        echoed = {key: reply[key] for key in ('response_schema_version', 'quality_policy')}
        # Only exact request metadata may be removed. Candidate fields are unchanged.
        if canonical(echoed) == canonical(expected_metadata):
            reply = {'results': reply['results']}
            changes.append({'rule': 'exact-request-metadata-echo', 'path': '$',
                            'removed_keys': sorted(echoed), 'verified_metadata_sha256': digest(canonical(echoed))})
    if isinstance(reply, dict) and isinstance(reply.get('results'), list):
        for i, row in enumerate(reply['results']):
            if not isinstance(row, dict) or not isinstance(row.get('senses'), list):
                continue
            for j, sense in enumerate(row['senses']):
                if not isinstance(sense, dict):
                    continue
                for field in ('pos', 'pinyin'):
                    before = sense.get(field)
                    if not isinstance(before, str):
                        continue
                    after = before
                    if field == 'pos':
                        after = {'noun': 'n', 'verb': 'v'}.get(before, before)
                    elif re.fullmatch(r'[a-zü:]+[1-5](?: [a-zü:]+[1-5])*', before):
                        after = before.replace('u:', 'v').replace('ü', 'v')
                    if after != before:
                        sense[field] = after
                        changes.append({'rule': 'pos-alias' if field == 'pos' else 'pinyin-umlaut',
                                        'path': f'$.results[{i}].senses[{j}].{field}',
                                        'before': before, 'after': after})
    normalized = canonical(reply).decode('utf-8') if changes else content
    version = 2 if any(c['rule'] == 'exact-request-metadata-echo' for c in changes) else 1
    return normalized, {'version': version, 'changes': changes,
                        'normalized_content_sha256': digest(normalized.encode('utf-8'))}


def parse_reply(content, job, generation):
    from tools.lexicon_expand.responses import validate_reply
    payload = job['payload']
    expected = ({key: payload[key] for key in ('response_schema_version', 'quality_policy')}
                if payload.get('response_schema_version') == 3 and 'quality_policy' in payload else None)
    normalized, audit = normalize_reply(content, expected_metadata=expected)
    generation = dict(generation)
    if audit['changes']:
        generation['normalization'] = audit
    else:
        generation.pop('normalization', None)
    return validate_reply(normalized, job, generation), generation
