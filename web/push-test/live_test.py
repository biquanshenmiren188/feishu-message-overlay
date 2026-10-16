import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
from live import Live
from preferences import DEFAULTS, validate, matches
from signals import parse_message


def message(n, at, rank='R0', percent='+0.39%', coin=None):
    return dict(id=f'{n:064x}', senderType='bot', sentAt=datetime.fromtimestamp(at, timezone.utc).isoformat(),
                title=f'{coin or "COIN"+str(n)} | FS | V2收敛 | {rank} {percent}',
                body='买 OKX 永续 → 卖 BITGET 现货\n净收益0.141% · 盘口差+0.217%')


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.now=time.time()
        self.config=self.root/'config.json'
        self.config.write_text(json.dumps(dict(pairCode='12345678',expiresAt=0,publicKey='public')))
        self.sent=[]
        self.app=Live(self.root/'state',self.config,lambda sub,p:self.sent.append(p) or 201)
        self.app.state['subscription']={'test':True}
        self.app.state['seq']=14

    def tick(self, rows, now=None, connected=True):
        now=self.now if now is None else now
        self.app.tick(dict(sourceConnected=connected,updatedAt=datetime.fromtimestamp(now,timezone.utc).isoformat(),messages=rows),now)

    def settings(self, **changes):
        s=self.app.state['live'];self.app.configure(dict(revision=s['revision'],settings=dict(s['settings'],**changes)))

    def test_real_parser_rank_percentage_arbitrary_levels(self):
        for rank in ['R0','R1','R2','R3','R4','R5+','R6+','R1000+']:
            row=parse_message(message(1,self.now,rank),self.now)
            self.assertEqual(row['rank'],rank);self.assertEqual(row['value'],'+0.39%')
        m=message(1,self.now);m['title']='COIN1 | FS | 净收益0.1%'
        self.assertIsNone(parse_message(m,self.now))
        m['title']='COIN1 | FS | R0 +0.1% R1 +0.2%'
        self.assertIsNone(parse_message(m,self.now))

    def test_four_rows_sorted_actual_clock_sequence_preserved(self):
        rows=[message(n,self.now-6+n) for n in range(1,7)]
        self.tick(list(reversed(rows)))
        p=self.sent[0];self.assertEqual(p['seq'],15);self.assertEqual(p['title'],'')
        self.assertEqual(len(p['rows']),4)
        self.assertTrue(p['rows'][0].endswith('COIN3'));self.assertTrue(p['rows'][-1].endswith('COIN6'))
        from server import compact_rows
        self.assertIn('+0.39% R0 FS OK→BG',p['rows'][0])
        self.assertEqual(p['rows'],self.app.render(self.app.selected(self.now)))

    def test_dedup_and_restart(self):
        rows=[message(1,self.now)]
        self.tick(rows);self.tick(rows,self.now+70)
        app=Live(self.root/'state',self.config,lambda sub,p:self.sent.append(p) or 201)
        self.app=app;self.tick(rows,self.now+80)
        self.assertEqual(len(self.sent),1)

    def test_cross_group_content_dedup(self):
        self.tick([message(1,self.now,coin='BTC'),message(2,self.now,coin='BTC')])
        self.assertEqual(len(self.sent[0]['rows']),1)

    def test_frequency_batches_and_no_periodic_alert(self):
        self.tick([message(1,self.now)])
        self.tick([message(2,self.now+10)],self.now+10)
        self.tick([message(3,self.now+20)],self.now+20)
        self.assertEqual(len(self.sent),1)
        self.tick([],self.now+60)
        self.assertEqual(len(self.sent),2);self.assertEqual(len(self.sent[-1]['rows']),3)
        self.tick([],self.now+130);self.assertEqual(len(self.sent),2)

    def test_disabled_drops_pending_without_replay(self):
        self.tick([message(1,self.now)])
        self.tick([message(2,self.now+5)],self.now+5)
        self.settings(notify_enabled=False)
        self.tick([message(3,self.now+70)],self.now+70)
        self.settings(notify_enabled=True)
        self.tick([message(2,self.now+5),message(3,self.now+70)],self.now+80)
        self.assertEqual(len(self.sent),1)

    def test_stale_source_and_old_messages_no_alert(self):
        self.tick([message(1,self.now)],connected=False);self.assertFalse(self.sent)
        self.tick([message(2,self.now-180)]);self.assertFalse(self.sent)
        self.app.tick(dict(sourceConnected=True,updatedAt='2020-01-01T00:00:00Z',messages=[message(3,self.now)]),self.now)
        self.assertFalse(self.sent)

    def test_filters_receive_all_and_blocking(self):
        row=parse_message(message(1,self.now,'R1000+'),self.now)
        self.assertTrue(matches(row,DEFAULTS))
        for block in ['R1000','R1000+']:
            self.assertFalse(matches(row,dict(DEFAULTS,excluded_ranks=[block])))
        for changes in [dict(excluded_coins=['COIN1']),dict(excluded_modes=['FS']),dict(excluded_exchanges=['BITGET']),dict(min_percent=0.4)]:
            self.assertFalse(matches(row,dict(DEFAULTS,**changes)))
        self.settings(excluded_ranks=['R0'])
        self.tick([message(1,self.now),message(2,self.now,'R1000+')])
        self.assertEqual(len(self.sent[0]['rows']),1)
        self.assertIn('R1000+',self.sent[0]['rows'][0])

    def test_settings_validation_conflict_and_persist(self):
        for change in [dict(rows=6),dict(rows=True),dict(min_percent=float('nan')),dict(excluded_ranks=['R*']),dict(notify_interval_seconds=1)]:
            with self.assertRaises(ValueError):validate(dict(DEFAULTS,**change))
        self.settings(rows=2,excluded_ranks=['r05+'])
        with self.assertRaises(ValueError):self.app.configure(dict(revision=0,settings=DEFAULTS))
        app=Live(self.root/'state',self.config)
        self.assertEqual(app.public_status()['settings']['rows'],2)
        self.assertEqual(app.public_status()['settings']['excluded_ranks'],['R5+'])

    def test_production_token_survives_trial_expiry_and_no_demos(self):
        token=self.app.pair('12345678');self.assertTrue(self.app.authenticate(token))
        with self.assertRaises(ValueError):self.app.start()
        with self.assertRaises(ValueError):self.app.resend()
        public=json.dumps(self.app.public_status());self.assertNotIn(token,public)

    def test_unknown_failure_does_not_repeat_or_leak(self):
        def fail(*args):raise RuntimeError('private-endpoint-secret')
        self.app.sender=fail
        self.tick([message(1,self.now)])
        self.assertEqual(self.app.state['live']['pending'],[])
        self.tick([message(1,self.now)],self.now+70)
        self.assertEqual(self.app.state['seq'],15)
        self.assertNotIn('private-endpoint-secret',json.dumps(self.app.public_status()))

    def test_expired_subscription_and_rate_limit(self):
        class Failed(Exception):
            def __init__(self,status):self.response=type('Response',(),{'status_code':status})()
        def reject(*args):raise Failed(429)
        self.app.sender=reject;self.tick([message(1,self.now)])
        self.assertEqual(self.app.state['live']['retryAt'],self.now+120)
        self.tick([],self.now+60);self.assertEqual(self.app.state['seq'],15)
        def gone(*args):raise Failed(410)
        self.app.sender=gone;self.tick([],self.now+120)
        self.assertNotIn('subscription',self.app.state)

if __name__=='__main__':unittest.main()
