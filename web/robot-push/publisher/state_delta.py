"""Stateless conditional components for signed desktop readers; legacy readers get full state."""
import hashlib
import json
import re

PARTS = {'groups': ('groups',), 'messages': ('messages',),
         'pin': ('pinned', 'pinnedGroupId'), 'opportunities': ('opportunities',)}

def state_request(value):
    if isinstance(value,dict) and value.get('desktopRules') == 1:
        value={k:v for k,v in value.items() if k!='desktopRules'}
    if not isinstance(value, dict) or value.get('action') != 'state':
        return False
    if set(value) == {'action'}:
        return True
    known = value.get('known')
    return (set(value) == {'action', 'known'} and isinstance(known, dict)
            and set(known) <= PARTS.keys()
            and all(isinstance(v, str) and re.fullmatch(r'[0-9a-f]{64}', v) for v in known.values()))

def conditional_state(state, known=None):
    result = {'cloudMode': state['cloudMode'], 'sourceConnected': state['sourceConnected'],
              'protocol': 1, 'revisions': {}}
    for part, fields in PARTS.items():
        component = {field: state[field] for field in fields}
        digest = hashlib.sha256(json.dumps(component, ensure_ascii=False, sort_keys=True,
                                          separators=(',', ':')).encode()).hexdigest()
        result['revisions'][part] = digest
        if (known or {}).get(part) != digest:
            result.update(component)
    return result
