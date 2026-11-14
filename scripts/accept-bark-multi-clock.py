"""Real-clock, isolated multi-device sender acceptance. No real Bark/network sends.

Runs Store + send_event for three rounds against a simulated HTTP boundary.
One recipient times out; the other two must each dispatch every 30 seconds.
"""
import json
from pathlib import Path
import secrets
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web' / 'alarms'))
from store import Store
from server import send_event
from test_alarms import rule, quote

records = []
class Response:
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self, *_): return b'{"code":200}'

def transport(request, **_):
    payload = json.loads(request.data)
    records.append((time.monotonic(), payload))
    assert payload['body'].startswith('自定义报警内容验收\n\n')
    assert (payload['level'], payload['volume'], payload['call']) == ('critical', 5, '1')
    if payload['device_key'].endswith('_1'):
        time.sleep(.7)
        raise TimeoutError('isolated recipient failure')
    return Response()

class MarketView:
    def snapshot(self): return {('binance', 'future', 'BTCUSDT'): quote(101, time.time())}, {}

market = MarketView()
with tempfile.TemporaryDirectory(prefix='bark-clock-') as directory:
    store = Store(directory)
    def change(**value):
        return store.mutate('acceptance', dict(value, revision=store.view('acceptance')['revision'], requestId=secrets.token_hex(16)), market.snapshot()[0])
    for n in range(3): change(action='bind', key='clock_demo_device_' + str(n), label='验收设备 ' + str(n))
    change(action='save', rule=rule(repeat=True,alarmContent='自定义报警内容验收'))
    started = time.monotonic()
    with patch('server.build_opener') as opener, ThreadPoolExecutor(max_workers=8) as workers:
        opener.return_value.open.side_effect = transport
        jobs = []
        while len(records) < 9:
            assert time.monotonic() - started < 70, 'Dispatch deadline exceeded'
            store.tick(market.snapshot()[0], time.time())
            while (event := store.claim()) is not None:
                jobs.append(workers.submit(send_event, store, event, market))
            time.sleep(.05)
        for job in jobs: job.result()
    intervals = []
    for n in range(3):
        rows = [(at, payload) for at, payload in records if payload['device_key'] == 'clock_demo_device_' + str(n)]
        assert len(rows) == 3 and len({payload['id'] for _, payload in rows}) == 3
        gaps = [rows[i + 1][0] - rows[i][0] for i in (0, 1)]
        assert all(29.99 <= gap < 31 for gap in gaps), gaps
        intervals.append([round(gap, 3) for gap in gaps])
    states = [event['status'] for event in store.view('acceptance')['events']]
    assert states.count('accepted') == 6 and states.count('unknown') == 3
    store.db.close()
print(json.dumps(dict(passed=True, devices=3, rounds=3, intervalsSeconds=intervals, accepted=6, isolatedTimeouts=3,
                      realClock=True, simulatedHttp=True, productionDataUntouched=True)))
