"""Conditional protocol, compression, and restart recovery without production data."""
import copy
import gzip
import io
import json
from state_delta import conditional_state, state_request
from server import Handler

state = {'cloudMode': True, 'sourceConnected': True, 'groups': [{'id': 'oc_fixture'}],
         'messages': [{'id': str(i), 'body': 'Synthetic message. ' * 500} for i in range(100)],
         'pinned': {'id': 'pinned'}, 'pinnedGroupId': 'fixture',
         'opportunities': {'status': 'connected', 'receivedAt': 'original', 'snapshot': None}}
full = conditional_state(state)
assert all(full[k] == v for k, v in state.items())
idle = conditional_state(state, full['revisions'])
assert set(idle) == {'cloudMode', 'sourceConnected', 'protocol', 'revisions'}
changed = copy.deepcopy(state)
changed['messages'].append({'id': 'new', 'body': 'new message'})
changed['pinned'] = None
changed['pinnedGroupId'] = ''
changed['sourceConnected'] = False
delta = conditional_state(changed, full['revisions'])
assert delta['messages'][-1]['id'] == 'new' and delta['pinned'] is None
assert delta['sourceConnected'] is False and 'groups' not in delta and 'opportunities' not in delta
changed['opportunities']['receivedAt'] = 'next'
assert 'opportunities' in conditional_state(changed, delta['revisions'])
# No per-reader server memory: a process restart and a client restart both converge.
assert conditional_state(copy.deepcopy(state), full['revisions']) == idle
assert conditional_state(state, {}) == full
assert 'messages' in conditional_state(state, {'messages': '0' * 64})
assert state_request({'action': 'state', 'known': full['revisions']})
for invalid in [None, [], {'action': 'pin'}, {'action': 'state', 'known': []},
                {'action': 'state', 'known': {'messages': 'bad'}},
                {'action': 'state', 'known': {'secret': 'a' * 64}}]:
    assert not state_request(invalid)

class Response:
    def __init__(self, accept):
        self.headers = {'Accept-Encoding': accept}
        self.wfile = io.BytesIO()
        self.sent = {}
    def send_response(self, status): self.status = status
    def send_header(self, key, value): self.sent[key] = value
    def end_headers(self): pass

compressed = Response('gzip')
Handler.respond(compressed, 200, full)
assert json.loads(gzip.decompress(compressed.wfile.getvalue())) == full
assert compressed.sent['Content-Encoding'] == 'gzip'
assert int(compressed.sent['Content-Length']) == len(compressed.wfile.getvalue())
for accept in ['', 'gzip;q=0']:
    plain = Response(accept)
    Handler.respond(plain, 200, full)
    assert 'Content-Encoding' not in plain.sent and json.loads(plain.wfile.getvalue()) == full
print(json.dumps({'passed': True, 'syntheticOnly': True,
                  'fullBytes': len(json.dumps(full).encode()), 'unchangedBytes': len(json.dumps(idle).encode()),
                  'gzipBytes': len(compressed.wfile.getvalue())}))
