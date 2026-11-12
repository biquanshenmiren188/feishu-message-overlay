"""Fixed loopback bridge after existing desktop signature verification."""
import json
from urllib.request import Request, urlopen


def desktop_state(code, client, *, pin_history=False):
    if code == '' and not pin_history:
        return dict(pushBinding=dict(protocol=1, bound=False, canManage=False),
                    desktopRules=dict(revision=0, messages={}, cards={}, desktopEnabled=True, cardsEnabled=True))
    request = Request('http://127.0.0.1:18885/internal/desktop-binding',
                      data=json.dumps(dict(pushCode=code, client=client, **({'pinHistory':1} if pin_history else {}))).encode(),
                      headers={'Content-Type':'application/json'}, method='POST')
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read(1024*1024))
