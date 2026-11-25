from contextlib import closing
import tempfile
import unittest
import json
import sqlite3
import io
import time
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch

import tbtc_alert as alerts
from store import Store, Conflict
from server import send_event


class PriceAlertTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        history_patch=patch.object(alerts,'ROUND_HISTORY',Path(temp.name)/'rounds.sqlite')
        history_patch.start()
        self.addCleanup(history_patch.stop)
        self.store=Store(temp.name)
        self.addCleanup(self.store.db.close)
        alerts.initialize(self.store)
        for i,profile in enumerate(('alice','bob')):
            self.store.mutate(profile,dict(action='bind',key='synthetic-key-'+profile,label=profile,
                              revision=0,requestId=str(i)*32),{})
            alerts.configure(self.store,profile,dict(target=('1.0026','1.0040')[i],revision=0))

    def test_master_switch_is_personal_preserves_options_and_drops_old_events(self):
        store=self.store
        rules=(alerts.RULE,alerts.MINT_RULE,alerts.LARGE_RULE,alerts.DEPOSIT_RULE,alerts.SALE_RULE)
        old=alerts.configure(store,'alice',dict(target='1.0026',revision=1,saleEnabled=True,
                             mintEnabled=True,depositEnabled=True,largeMintEnabled=False))
        with store.db:
            for profile in ('alice','bob'):
                device=store.db.execute('SELECT * FROM devices WHERE profile=?',(profile,)).fetchone()
                for rule in rules:store.event(profile,rule,{'title':'test'},device,time.time())
        paused=alerts.configure(store,'alice',dict(masterEnabled=False,revision=old['revision']))
        for profile,status in [('alice','cancelled'),('bob','queued')]:
            rows=store.db.execute('SELECT status FROM events WHERE profile=?',(profile,)).fetchall()
            self.assertEqual([r[0] for r in rows],[status]*5)
        with self.assertRaises(Conflict):
            alerts.configure(store,'alice',dict(masterEnabled=True,revision=old['revision']))
        page=dict(at=time.time(),target=old['target'],venue='okx',rawOut='1003000000000000000')
        self.assertFalse(alerts.record_page(store,'alice',page)['allowed'])
        restored=alerts.configure(store,'alice',dict(masterEnabled=True,revision=paused['revision']))
        for key in old.keys()-{'revision','masterSince'}:self.assertEqual(old[key],restored[key])
        self.assertFalse(alerts.record_page(store,'alice',dict(page,at=restored['masterSince']-1))['allowed'])
        self.assertTrue(alerts.record_page(store,'alice',dict(page,at=time.time()))['allowed'])
        row=store.db.execute("SELECT * FROM tbtc_price_alerts WHERE profile='alice'").fetchone()
        for col in ('sale_since','deposit_since','mint_since','round_cursor'):
            self.assertEqual(row[col],restored['masterSince'])
        self.assertIsNone(row['large_mint_since'])

    def test_sale_webhook_and_poll_deduplicate_both_aave_sales(self):
        with patch('time.time',return_value=100):
            alerts.configure(self.store,'alice',dict(target=None,revision=1,saleEnabled=True))
        def row(tx,stamp,amount):
            return dict(tx=tx,address='seller',time=stamp,soldRaw=str(amount),source='aave')
        rows={(r['tx'],r['address']):r for r in (row('one',101,10*10**18),row('two',102,9995*10**15),
              row('equal',103,5*10**18),row('small',104,1),row('old',99,11*10**18))}
        with patch.object(alerts,'sale_data',return_value=rows),self.store.db:
            alerts.enqueue_sales(self.store,time.time())
            alerts.enqueue_sales(self.store,time.time())
            sent=set()
            for _ in range(2):
                event=self.store.claim()
                self.assertEqual(event['rule_id'],alerts.SALE_RULE)
                sent.add(json.loads(event['payload'])['tx'])
                self.assertTrue(self.store.begin_send(event))
            self.assertEqual(sent,{'one','two'})
            self.assertIsNone(self.store.claim())

    def test_sale_history_records_late_webhook_and_separate_device_receipts(self):
        self.store.mutate('alice',dict(action='bind',key='synthetic-key-tablet',label='tablet',
                          revision=1,requestId='a'*32),{})
        with patch('time.time',return_value=100):
            alerts.configure(self.store,'alice',dict(target=None,revision=1,saleEnabled=True))
        batch='d'*32
        row=dict(tx='tx',address='seller',time=101,soldRaw=str(9995*10**15),source='aave',
                 scannedAt=105,scanBatch=batch)
        with patch.object(alerts,'sale_data',return_value={('tx','seller'):row}),patch('time.time',return_value=110):
            with self.store.db:
                alerts.enqueue_sales(self.store,106)
                alerts.enqueue_sales(self.store,107,batch)
                alerts.enqueue_sales(self.store,108,batch)
            with patch('server.build_opener') as opener:
                opener.return_value.open.side_effect=[io.BytesIO(b'{"code":200}'),TimeoutError()]
                for _ in range(2):
                    send_event(self.store,self.store.claim())
                self.assertIsNone(self.store.claim())
            item,=alerts.history(self.store,'alice',{})['items']
            sale=item['sale']
            self.assertEqual((sale['trigger'],sale['scannedAt'],sale['webhookAt'],sale['amount']),('poll',105,107,'9.995'))
            self.assertEqual({d['label'] for d in sale['devices']},{'alice','tablet'})
            self.assertCountEqual(item['statuses'],['accepted','unknown'])
            for d in sale['devices']:
                attempt,=d['attempts']
                self.assertEqual((attempt['sentAt'],attempt['finishedAt'],attempt['status']),(110,110,d['status']))
            self.assertFalse(alerts.history(self.store,'bob',{})['items'])

    def test_sale_threshold_is_personal_strict_and_applies_to_new_sales(self):
        self.assertEqual(alerts.state(self.store,'alice')['saleThreshold'],'5')
        with patch('time.time',return_value=100):
            for profile,limit in [('alice','2.5'),('bob','10')]:
                alerts.configure(self.store,profile,dict(revision=1,target=None,saleEnabled=True,saleThreshold=limit))
        rows={}
        for tx,raw,stamp in [('before',8*10**18,99),('equal',25*10**17,101),('above',25*10**17+1,102)]:
            rows[tx,'seller']=dict(tx=tx,address='seller',time=stamp,soldRaw=str(raw))
        with patch.object(alerts,'sale_data',return_value=rows),self.store.db:
            alerts.enqueue_sales(self.store,time.time())
            event=self.store.claim()
            self.assertEqual((event['profile'],json.loads(event['payload'])['tx']),('alice','above'))
            self.assertTrue(self.store.begin_send(event))
            self.assertIsNone(self.store.claim())
        with self.assertRaises(ValueError):
            alerts.configure(self.store,'alice',dict(target=None,revision=2,saleThreshold='0'))
        self.assertEqual(alerts.configure(self.store,'alice',dict(target=None,revision=2))['saleThreshold'],'2.5')

    def test_mint_gap_is_personal_and_decided_on_missing_units(self):
        a=alerts.configure(self.store,'alice',dict(target='1.0026',revision=1,mintThreshold='0.00000001',mintEnabled=True))
        self.assertEqual(a['mintThreshold'],'0.00000001')
        self.assertEqual(alerts.state(self.store,'bob')['mintThreshold'],'10')
        legacy=alerts.configure(self.store,'alice',dict(target='1.0030',revision=a['revision']))
        self.assertEqual(legacy['mintThreshold'],a['mintThreshold'])
        for invalid in ('-1','0','1e3','0.000000001'):
            with self.assertRaises(ValueError):
                alerts.configure(self.store,'alice',dict(target=legacy['target'],revision=legacy['revision'],mintThreshold=invalid))
        record=dict(raw=str(12*10**18),unbackedRaw=str(10**18))
        self.assertFalse(alerts.meets_mint_threshold(record,18,'10'))
        self.assertTrue(alerts.meets_mint_threshold(record,18,'1'))

    def test_backed_mints_are_strictly_per_tx_and_independent_of_shortfall(self):
        config=alerts.configure(self.store,'alice',dict(target=None,revision=1,largeMintEnabled=True))
        self.assertFalse(config['mintEnabled'])
        self.assertEqual(config['largeMintThreshold'],'30')
        with tempfile.TemporaryDirectory() as tmp,patch.object(alerts,'SUPPLY',Path(tmp)/'supply.json'):
            now=int(time.time())+1
            def record(tx,raw,kind='matched'):
                return dict(tx=tx,raw=str(raw),reason='test',time=now,kind=kind)
            rows=[record('a',16*10**8),record('b',16*10**8),record('equal',30*10**8),
                  record('over',30*10**8+1),record('pending',100*10**8,'pending'),
                  record('review',100*10**8,'review')]
            alerts.SUPPLY.write_text(json.dumps(dict(time=now,chains=[dict(name='Sui',stamp=now,ok=True,decimals=8,history=rows)])))
            with patch('time.time',return_value=now+0.5):
                alerts.tick(self.store);alerts.tick(self.store)
                e=self.store.claim()
                self.assertEqual(e['rule_id'],alerts.LARGE_RULE)
                self.assertEqual(json.loads(e['payload'])['tx'],'over')
                self.assertEqual(len(self.store.view('alice')['events']),1)
                self.assertFalse(self.store.view('bob')['events'])
                alerts.configure(self.store,'alice',dict(target=None,revision=config['revision'],largeMintEnabled=False))
                self.assertFalse(self.store.begin_send(e))

    def update_price(self,stamp,value):
        with patch.object(alerts,'sample',return_value=(Decimal(value),'test',int(stamp),'second')):
            alerts.tick(self.store)

    def test_personal_history_groups_devices_and_retried_page_reports(self):
        now=time.time()
        page=dict(at=now,venue='venue',rawOut=str(10030*10**14),target='1.0026')
        for _ in range(2):alerts.record_page(self.store,'alice',page)
        with self.store.db:
            for _ in range(2):
                self.store.event('alice',alerts.MINT_RULE,dict(title='异常铸币',body='10 tBTC',tx='a'),None,now-1)
            for profile,rule in [('bob',alerts.RULE),('alice','unrelated')]:
                self.store.event(profile,rule,dict(title='其他记录',body='其他'),None,now-1)
            for i in range(6):
                self.store.event('alice',alerts.DEPOSIT_RULE,dict(title=str(i),body='BTC',outpoint=str(i)),None,now-2)
        first=alerts.history(self.store,'alice',{})
        self.assertEqual(first['total'],8)
        self.assertEqual(len(first['items']),6)
        self.assertEqual(first['items'][0]['kind'],'page')
        self.assertEqual(first['items'][1]['statuses'],['no_device','no_device'])
        second=alerts.history(self.store,'alice',dict(page=['2'],before=[first['before']]))
        self.assertEqual(len(second['items']),2)
        self.assertTrue({r['title'] for r in first['items']}.isdisjoint(r['title'] for r in second['items']))
        self.assertEqual(alerts.history(self.store,'bob',{})['total'],1)

    def test_early_bitcoin_deposit_push(self):
        with tempfile.TemporaryDirectory() as d,patch.object(alerts,'DEPOSITS',Path(d)/'deposits.json'):
            cfg=alerts.configure(self.store,'alice',dict(target=None,revision=1,depositEnabled=True))
            t=time.time()
            base=dict(txid='a'*64,vout=0,depositor='recipient',status='mempool',sats=3000000001,
                      revealedAt=t-500,verifiedAt=t)
            def write(*rows):
                alerts.DEPOSITS.write_text(json.dumps(dict(time=int(t),deposits=rows)))
                alerts.read_deposits.cache_clear()
            write(dict(base,sats=3000000000),dict(base,vout=1,status='unverified'),dict(base,vout=2,verifiedAt=t-10),
                  dict(base,vout=3,sats=1600000000),dict(base,vout=4,sats=1600000000))
            alerts.tick(self.store)
            self.assertIsNone(self.store.claim())
            write(base)
            alerts.tick(self.store)
            event=self.store.claim()
            self.assertEqual(event['rule_id'],alerts.DEPOSIT_RULE)
            self.assertIn('30.00000001 BTC',json.loads(event['payload'])['title'])
            self.assertTrue(self.store.begin_send(event))
            self.store.finish(event,'accepted')
            write(dict(base,status='confirmed'))
            alerts.tick(self.store)
            self.assertIsNone(self.store.claim())
            self.assertFalse(self.store.view('bob')['events'])
            write(dict(base,vout=5,status='confirmed'))
            alerts.tick(self.store)
            event=self.store.claim()
            alerts.configure(self.store,'alice',dict(target=None,revision=cfg['revision'],depositThreshold='40'))
            self.assertFalse(self.store.begin_send(event))

    def test_uses_second_rank_until_both_supporting_quotes_expire(self):
        row=dict(currency="cbBTC",size=1,reverse=False,at=99,rawOut=str(2*10**18),route="best")
        with tempfile.TemporaryDirectory() as d,patch.object(alerts,"SNAPSHOT",Path(d)/"q"):
            def write():alerts.SNAPSHOT.write_text(json.dumps(dict(time=99,quotes=[row])))
            write()
            self.assertIsNone(alerts.sample(100))
            row["second"]=dict(rawOut="1002600000000000000",at=98,validUntil=102,venue="1inch")
            write()
            self.assertEqual(alerts.sample(100),(Decimal("1.0026"),"1inch",98,"second"))
            self.assertIsNone(alerts.sample(102))

    def test_personal_target_and_recovery(self):
        self.update_price('1','1.0026')
        self.assertEqual(len(self.store.view('alice')['events']),1)
        for stamp in ('1','2','3'):
            self.update_price(stamp,'1.0026')
        events=self.store.view('alice')['events']
        self.assertEqual(len(events),1)
        self.assertFalse(self.store.view('bob')['events'])
        event=self.store.claim()
        with patch.object(alerts,'sample',return_value=('4',Decimal('1.0026'))):
            self.assertTrue(self.store.begin_send(event))
        self.store.finish(event,'accepted')
        self.update_price('4','1.00259999999')
        self.update_price('5','1.003')
        self.update_price('6','1.003')
        self.assertEqual(len(self.store.view('alice')['events']),2)
        with self.assertRaises(Conflict):
            alerts.configure(self.store,'alice',dict(target=None,revision=0))
        alerts.configure(self.store,'alice',dict(target=None,revision=1))
        self.assertIsNone(self.store.claim())
        self.assertEqual(alerts.state(self.store,'bob')['target'],'1.0040')

    def test_single_hit_survives_gap_and_dip_before_delivery(self):
        with patch.object(alerts,'sample',return_value=None):
            alerts.tick(self.store)
        self.assertIsNone(self.store.claim())
        self.update_price('1','1.0027')
        event=self.store.claim()
        with patch.object(alerts,'sample',return_value=None):
            alerts.tick(self.store)
        self.update_price('2','1.0027')
        self.assertIsNone(self.store.claim())
        self.update_price('3','1.0024')
        self.assertTrue(self.store.begin_send(event))
        self.update_price('4','1.0026')
        self.assertIsNotNone(self.store.claim())

    def test_replay_crossing_gap_and_dip_with_atomic_cursor(self):
        with closing(sqlite3.connect(alerts.ROUND_HISTORY)) as db, db:
            db.execute("CREATE TABLE quote_rounds(captured REAL, second_raw TEXT, venue TEXT, quoted_at REAL,venues INTEGER DEFAULT 2,best_raw TEXT)")
            now=time.time()
            for delay,value in [(-10,'1.010'),(1,'1.006'),(2,None),(3,'1.006'),(4,'1.001')]:
                raw=str(int(Decimal(value)*10**18)) if value else None
                db.execute("INSERT INTO quote_rounds(captured,second_raw,venue,quoted_at) VALUES(?,?,?,?)",(now+delay,raw,'OKX',now+delay))
        with patch('time.time',return_value=now+12):
            with patch.object(self.store,'event',side_effect=RuntimeError('interrupted')):
                with self.assertRaises(RuntimeError):alerts.tick_prices(self.store)
            alerts.tick_prices(self.store)
            alerts.tick_prices(self.store)
            for profile in ('alice','bob'):
                records=self.store.db.execute("SELECT payload FROM events WHERE rule_id=? AND profile=?",
                                              (alerts.RULE,profile)).fetchall()
                self.assertEqual(len(records),1)
                self.assertEqual(json.loads(records[0][0])['quoteAt'],now+1)
            self.assertTrue(self.store.begin_send(self.store.claim()))
            alerts.configure(self.store,'alice',dict(target='1.008',revision=1))
        with closing(sqlite3.connect(alerts.ROUND_HISTORY)) as db, db:
            for delay in (11,13):
                db.execute("INSERT INTO quote_rounds(captured,second_raw,venue,quoted_at) VALUES(?,?,?,?)",(now+delay,str(1009*10**15),'0x',now+delay))
        with patch('time.time',return_value=now+14):
            alerts.tick_prices(self.store)
        latest=self.store.db.execute("SELECT payload FROM events WHERE profile='alice' ORDER BY at DESC LIMIT 1").fetchone()
        self.assertEqual(json.loads(latest[0])['quoteAt'],now+13)

    def test_channels_preserve_target_and_cancel_only_bark(self):
        def update(page,bark):
            return alerts.configure(self.store,'alice',dict(target='1.0026',pageEnabled=page,
              barkEnabled=bark,revision=alerts.state(self.store,'alice')['revision']))
        self.update_price('1','1.0026')
        update(False,True)
        self.update_price('2','1.0026')
        event=self.store.claim()
        self.assertEqual(event['profile'],'alice')
        result=update(False,False)
        self.assertEqual(result['target'],'1.0026')
        with patch.object(alerts,'sample',return_value=('3',Decimal('1.0026'))):
            self.assertFalse(self.store.begin_send(event))
        update(True,False)
        self.update_price('4','1.0026')
        self.update_price('5','1.0026')
        self.assertIsNone(self.store.claim())
        self.assertTrue(alerts.state(self.store,'bob')['barkEnabled'])

    def test_upgrade_preserves_rule_and_restarts_confirmation_on_new_rank(self):
        with self.store.db:
            self.store.db.execute('DROP TABLE tbtc_price_alerts')
            self.store.db.execute('CREATE TABLE tbtc_price_alerts(profile TEXT PRIMARY KEY,target TEXT,revision INTEGER,last_sample TEXT,hits INTEGER DEFAULT 0,fired INTEGER DEFAULT 0)')
            self.store.db.execute("INSERT INTO tbtc_price_alerts VALUES('alice','1.0035',12,'kyber:123',2,1)")
        alerts.initialize(self.store)
        alerts.initialize(self.store)
        result=alerts.state(self.store,'alice')
        self.assertEqual((result['target'],result['revision'],result['pageEnabled'],result['barkEnabled']),('1.0035',12,True,True))
        self.assertEqual(self.store.db.execute('SELECT fired FROM tbtc_price_alerts').fetchone()[0],0)

    def test_mint_push_opt_in_is_independent_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(alerts,'SUPPLY',Path(directory)/'supply.json'):
            cfg=alerts.configure(self.store,'alice',dict(target=None,pageEnabled=False,barkEnabled=False,mintEnabled=True,revision=1))
            self.assertTrue(cfg['mintEnabled'])
            ts=time.time()
            record=dict(kind='review',time=int(ts)-60,flaggedAt=ts,tx='tx1',raw='1000300001',reason='归集不符')
            def write(rows,ok=True):
                alerts.SUPPLY.write_text(json.dumps(dict(time=int(ts),chains=[dict(name='Sui',ok=ok,stamp=int(ts),decimals=8,history=rows)])))
                alerts.read_mints.cache_clear()
            write([dict(record,tx='old',flaggedAt=ts-600),dict(record,tx='pending',kind='pending'),
                   dict(record,tx=None),dict(record,tx='matched',kind='matched'),record])
            alerts.tick(self.store);alerts.tick(self.store)
            self.assertFalse(self.store.view('bob')['events'])
            self.assertEqual(len(self.store.view('alice')['events']),1)
            event=self.store.claim()
            self.assertIn('10.00300001 tBTC',json.loads(event['payload'])['body'])
            self.assertEqual(event['rule_id'],'tbtc-mint')
            self.assertTrue(self.store.begin_send(event))
            self.store.finish(event,'accepted')
            # Older price-setting clients omit the new field.
            alerts.configure(self.store,'alice',dict(target='1.0020',revision=cfg['revision']))
            self.assertTrue(alerts.state(self.store,'alice')['mintEnabled'])
            write([dict(record,tx='tx2')]);alerts.tick(self.store);event=self.store.claim()
            write([]);self.assertFalse(self.store.begin_send(event))
            write([dict(record,tx='tx3')]);alerts.tick(self.store);event=self.store.claim()
            alerts.configure(self.store,'alice',dict(target='1.0020',mintEnabled=False,revision=3))
            self.assertFalse(self.store.begin_send(event))
            alerts.initialize(self.store)
            cfg=alerts.configure(self.store,'alice',dict(target='1.0020',mintEnabled=True,revision=4))
            write([dict(record,flaggedAt=time.time())]);alerts.tick(self.store)
            self.assertIsNone(self.store.claim())
