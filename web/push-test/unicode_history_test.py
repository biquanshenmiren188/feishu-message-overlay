"""Desktop history is filtered independently from mobile notification freshness."""
import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import time
import unittest

from desktop_rules import DesktopRules
from live import Live
from preferences import DEFAULTS,exclusion_reasons
from signals import parse_message,parse_messages
from advanced_rules import OISnapshot
from oi_source_cache import OISourceCache


class UnicodeHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.now=time.time()
        self.feed=self.root/'feed.json';self.feed.write_text('{"messages":[]}')
        self.cards=self.root/'cards.json';self.cards.write_text('{"snapshot":{"active":[]}}')
        self.app=DesktopRules(self.root,self.feed,self.cards)
        sources=OISourceCache();self.addCleanup(sources.close);self.app.oi=OISnapshot(source_cache=sources)

    def message(self,coin='BULLA',age=5,**change):
        return dict(dict(id='a'*64,senderType='bot',title=coin+' | FF | R1 +0.81%',
                         body='买 ASTER 永续 → 卖 BINANCE 永续',
                         sentAt=datetime.fromtimestamp(self.now-age,timezone.utc).isoformat()),**change)

    def decision(self,message):
        return self.app.decision('desktop',message['id'],self.app.rows(message,self.now),self.now)

    def test_unicode_and_long_symbols_keep_real_r_fields_on_both_paths(self):
        rule=self.app.data['desktop']['rules']['hide'];rule['excluded_ranks']=['R1']
        for coin in ('币安人生','龙虾','A'*32,'币'*32,'xyz:ANSEM'):
            message=self.message(coin);mobile=parse_messages(message,self.now);desktop=self.app.rows(message,self.now)
            self.assertEqual(mobile,desktop)
            self.assertEqual(mobile[0]['coin'],coin.upper());self.assertEqual(mobile[0]['rank'],'R1')
            self.assertEqual(self.decision(message),'hide')
        for coin in ('A'*33,'币'*33):self.assertEqual(parse_messages(self.message(coin),self.now),[])

    def test_unicode_min_percent_coin_and_exact_namespace_filters(self):
        row=parse_message(self.message('币安人生'),self.now)
        rule=dict(copy.deepcopy(DEFAULTS),min_percent=1)
        self.assertTrue(exclusion_reasons(row,rule))
        row=parse_message(self.message('xyz:ANSEM'),self.now)
        self.assertFalse(exclusion_reasons(row,dict(copy.deepcopy(DEFAULTS),excluded_coins=['ANSEM'])))

    def test_unicode_strong_signal_routes_keep_rank_and_fingerprint(self):
        message=self.message(title='🚨 强信号聚集｜币安人生｜2 组同时 ACTIVE',
                             body='R1｜FF｜买 ASTER → 卖 BINANCE\n净均 +0.81% · ACTIVE 2s\nR2｜SF｜买 GATE → 卖 ASTER\n净均 +1.1% · ACTIVE 4s')
        rows=parse_messages(message,self.now)
        self.assertEqual([r['coin'] for r in rows],['币安人生','币安人生'])
        self.assertEqual([r['rank'] for r in rows],['R1','R2'])
        self.assertNotEqual(rows[0]['id'],rows[1]['id'])
        self.assertEqual(rows,self.app.rows(message,self.now))

    def strong_v2_message(self,**change):
        # Synthetic values/coin, with the six-group envelope and per-route
        # metadata prefix observed in the live source. No private feed fixture.
        groups=[('R1','FF','BITGET','ASTER','+0.61'),('R1','SF','GATE','ASTER','+0.52'),
                ('R2','FF','BINANCE','ASTER','+0.43'),('R3','SF','BINANCE','ASTER','+0.34'),
                ('R6+','FF','BYBIT','ASTER','-0.25'),('R0','FF','OKX','ASTER','+0.16')]
        body='最近180秒净收益均值最高 +9.99%\n'+'\n'.join(
            f'{rank}｜{mode}｜买 {buy} → 卖 {sell}\nV2收敛 · 180秒 · 净均 {value}% · ACTIVE 2s'
            for rank,mode,buy,sell,value in groups)
        return self.message(title='🚨🚨 强信号聚集｜TOKEN｜6 组同时 ACTIVE',body=body,**change)

    def test_strong_v2_metadata_keeps_per_route_values_rules_and_identity(self):
        message=self.strong_v2_message();rows=parse_messages(message,self.now)
        self.assertEqual([r['value'] for r in rows],['+0.61%','+0.52%','+0.43%','+0.34%','-0.25%','+0.16%'])
        self.assertEqual([r['rank'] for r in rows],['R1','R1','R2','R3','R6+','R0'])
        self.assertEqual(rows,self.app.rows(message,self.now))
        legacy=dict(message,body=message['body'].replace('V2收敛 · 180秒 · ',''))
        self.assertEqual(rows,parse_messages(legacy,self.now))
        self.app.data['desktop']['rules']['hide']['excluded_ranks']=['R6+']
        self.assertIsNone(self.decision(message))

    def test_strong_v2_rejects_incomplete_groups_and_unconfirmed_prefixes(self):
        message=self.strong_v2_message();body=message['body']
        variants=[body.replace('V2收敛 · 180秒 · 净均 +0.43% · ACTIVE 2s',''),
                  body.replace('V2收敛 · 180秒 · ', '其他说明 · 180秒 · ',1),
                  body.replace('V2收敛 · 180秒 · ', 'V3收敛 · 180秒 · ',1),
                  body.replace('V2收敛 · 180秒 · ', 'V2收敛 · 0秒 · ',1),
                  body.replace('净均 +0.43%', '资金费 +0.43%',1),
                  body.replace('净均 +0.43%', '净均 +0.43',1),
                  body.replace('买 OKX → 卖 ASTER','买 OKX → 卖 UNKNOWN',1),
                  body+'\nR0｜FF｜买 OKX → 卖 ASTER\nV2收敛 · 180秒 · 净均 +0.99% · ACTIVE 1s']
        for changed in variants:
            with self.subTest(body=changed):
                self.assertEqual(parse_messages(dict(message,body=changed),self.now),[])
        self.assertEqual(parse_messages(dict(message,title=message['title'].replace('6 组','7 组')),self.now),[])

    def test_strong_v2_history_still_obeys_mobile_freshness(self):
        message=self.strong_v2_message(age=1801)
        self.assertEqual(parse_messages(message,self.now),[])
        self.assertEqual(len(self.app.rows(message,self.now)),6)
        self.app.data['desktop']['rules']['hide']['excluded_coins']=['TOKEN']
        self.assertEqual(self.decision(message),'hide')

    def test_malformed_strong_signal_cannot_bypass_configured_desktop_filters(self):
        complete=self.message(title='强信号聚集｜UNITREE｜2 组同时 ACTIVE',body='R0｜FF｜买 GATE → 卖 ASTER\n净均 +0.25% · ACTIVE 1s\nR0｜FF｜买 GATE → 卖 BITGET\n净均 +0.29% · ACTIVE 1s')
        cases=[dict(complete,body=complete['body'].replace('净均 +0.29% · ACTIVE 1s','')),
               dict(complete,body=complete['body'].replace('BITGET','UNKNOWN')),
               dict(complete,title=complete['title'].replace('2 组','3 组')),
               dict(complete,body='没有可校验的组合'),
               dict(complete,title='强信号聚集｜UNITREE',body='没有可校验的组合'),
               dict(complete,title=complete['title'].replace('UNITREE','币安人生')),
               dict(complete,body=complete['body'].replace('R0','RNaN',1))]
        # The Unicode variant is deliberately malformed too.
        cases[-2]['body']=cases[-2]['body'].replace('净均 +0.29% · ACTIVE 1s','')
        for message in cases:
            with self.subTest(title=message['title'],body=message['body']):
                self.assertEqual(parse_messages(message,self.now),[])
                rows=self.app.rows(message,self.now)
                self.assertTrue(rows);self.assertTrue(all(r.get('invalidSignal') for r in rows))
                self.assertTrue(all(r['coin'] in ('UNITREE','币安人生') for r in rows))
                self.assertIsNone(self.decision(message),'Default receive-all must remain unchanged')
        self.app.data['desktop']['rules']['hide']['excluded_coins']=['UNITREE']
        self.assertEqual(self.decision(complete),'hide')
        for message in cases:self.assertEqual(self.decision(message),'hide')
        rows=self.app.rows(cases[1],self.now)
        self.assertEqual([(r['buy'],r['sell'],r['mode']) for r in rows],[('GATE','ASTER','FF'),('GATE','','FF')])
        self.app.data['desktop']['rules']['hide']['excluded_coins']=[]
        self.app.data['desktop']['rules']['mute']['excluded_coins']=['UNITREE']
        for message in cases:self.assertEqual(self.decision(message),'mute')
        for title,body in [('普通公告：强信号聚集 UNITREE 更新','普通内容'),('强信号聚集功能说明','UNITREE'),('UNITREE 新闻','强信号聚集｜UNITREE｜2 组同时 ACTIVE')]:
            message=self.message(title=title,body=body)
            self.assertEqual(self.app.rows(message,self.now),[]);self.assertIsNone(self.decision(message))

    def test_malformed_strong_mobile_messages_never_enter_send_queue(self):
        config=self.root/'config.json';config.write_text(json.dumps(dict(pairCode='12345678',expiresAt=0,publicKey='public')))
        sent=[];live=Live(self.root/'mobile-invalid-strong',config,lambda s,p:sent.append(p) or 201)
        live.state['subscription']={'endpoint':'https://test.push.apple.com/test','keys':{'auth':'test','p256dh':'test'}}
        strong=self.strong_v2_message()
        bad=dict(strong,body=strong['body'].replace('净均 +0.43% · ACTIVE 2s',''))
        other=dict(bad,id='b'*64,body=strong['body'].replace('ASTER','UNKNOWN'))
        feed=dict(sourceConnected=True,updatedAt=datetime.fromtimestamp(self.now,timezone.utc).isoformat(),messages=[bad],pinned=other)
        live.tick(feed,self.now)
        self.assertEqual(sent,[]);self.assertEqual(live.state['live']['pending'],[])
        self.assertEqual(live.state['live']['history'],[])

    def test_old_retained_messages_keep_hide_and_mute(self):
        self.app.data['desktop']['rules']['hide']['excluded_coins']=['BULLA']
        for age in (1799,1801,86400,30*86400):
            message=self.message(age=age)
            self.assertEqual(self.decision(message),'hide')
            if age>1800:self.assertEqual(parse_messages(message,self.now),[])
        self.app.data['desktop']['rules']['hide']['excluded_coins']=[]
        self.app.data['desktop']['rules']['mute']['excluded_exchanges']=['ASTER']
        self.assertEqual(self.decision(self.message(age=86400)),'mute')

    def test_history_still_rejects_invalid_identity_time_and_future(self):
        for change in (dict(sentAt='bad'),dict(sentAt='2026-10-26T12:00:00'),dict(id='bad'),dict(senderType='user')):
            self.assertEqual(self.app.rows(self.message(**change),self.now),[])
        self.assertEqual(self.app.rows(self.message(age=-31),self.now),[])

    def test_ranked_legacy_title_does_not_skip_percent_or_rank(self):
        message=self.message(title='专题｜币安人生｜FF｜R1 +0.81%')
        self.app.data['desktop']['rules']['hide']['min_percent']=1
        self.assertEqual(self.decision(message),'hide')
        rows=self.app.rows(message,self.now)
        self.assertFalse(rows[0]['unranked']);self.assertEqual(rows[0]['value'],'+0.81%')

    def test_bad_rank_or_direction_is_not_unranked_bypass_with_filters(self):
        cases=[self.message(title='BULLA | FF | R1 NaN%'),self.message(title='BULLA | FF | R1 +0.5% R2 +0.6%'),
               self.message(body='买 ASTER 现货 → 卖 BINANCE 永续'),self.message(body='买 ASTER 永续 → 卖 UNKNOWN 永续'),
               self.message(body='missing direction')]
        for message in cases:
            self.assertIsNone(self.decision(message)) # Receive-all remains all.
        self.app.data['desktop']['rules']['hide']['excluded_ranks']=['R1']
        for message in cases:self.assertEqual(self.decision(message),'hide')
        self.assertIsNone(self.decision(self.message(title='普通公告 RAM 更新',body='普通内容 R1')))

    def test_real_topic_coin_route_and_oi_rules_apply_without_using_take_as_r(self):
        message=self.message(title='',body='[Binance/Aster 专题价差] 1 个信号\n条件: take > 0.50%\n1. IRYS | 多 Binance / 空 Aster\n当前 take: 0.9446%\n已持续 3分0秒')
        rows=self.app.rows(message,self.now)
        self.assertEqual([(r['coin'],r['mode'],r['buy'],r['sell']) for r in rows],[('IRYS','FF','BINANCE','ASTER')])
        self.assertTrue(rows[0]['unranked']);self.assertEqual(parse_messages(message,self.now),[])
        rule=self.app.data['desktop']['rules']['hide'];rule.update(min_percent=99,excluded_ranks=['R0','R1'])
        self.assertIsNone(self.decision(message))
        rule['excluded_coins']=['IRYS'];self.assertEqual(self.decision(message),'hide')
        rule['excluded_coins']=[];rule['advanced']['globalOI']=50
        self.app.oi._read=lambda ex,n:(ex,{ex+':IRYSUSDT':dict(value=499999,time=n*1000,basis='double-v1')})
        self.assertEqual(self.decision(message),'hide')

    def test_topic_envelope_required_and_namespace_preserved(self):
        body='1. xyz:ANSEM | 多 Binance / 空 Aster\n当前 take: 0.8%'
        self.assertEqual(self.app.rows(self.message(title='普通消息',body=body),self.now),[])
        rows=self.app.rows(self.message(title='[Binance/Aster 专题价差] 1 个信号',body=body),self.now)
        self.assertEqual(rows[0]['coin'],'XYZ:ANSEM')

    def test_real_dex_multi_route_any_block_hides_whole_message_and_spot_ignored(self):
        message=self.message(title='',body='[Dex 套利监控命中][最高P3]\n1. [P3][现期] IRYS | 多 Gate 现货 / 空 Bitget 永续\n净费率: -0.01%/h\n2. [P2][期现] 币安人生 | 多 Aster 永续 / 借卖 Binance 现货\n净费率: +0.02%/h')
        rows=self.app.rows(message,self.now)
        self.assertEqual([(r['coin'],r['mode']) for r in rows],[('IRYS','SF'),('币安人生','FS')])
        self.assertEqual(parse_messages(message,self.now),[])
        rule=self.app.data['desktop']['rules']['hide'];rule['advanced']['globalOI']=50
        calls=[]
        def read(ex,n):
            calls.append(ex)
            return ex,{ex+':'+coin+'USDT':dict(value=1e6,time=n*1000,basis='double-v1') for coin in ('IRYS','币安人生')}
        self.app.oi._read=read
        self.assertIsNone(self.decision(message));self.assertEqual(set(calls),{'aster','bitget'})
        rule['advanced']['coins']=[dict(coin='币安人生',exchange='aster',enabled=True)]
        self.assertEqual(self.decision(message),'hide')

    def test_mobile_new_unicode_sends_once_old_and_topic_do_not_replay(self):
        config=self.root/'config.json';config.write_text(json.dumps(dict(pairCode='12345678',expiresAt=0,publicKey='public')))
        sent=[];live=Live(self.root/'mobile',config,lambda s,p:sent.append(p) or 201)
        live.state['subscription']={'endpoint':'https://test.push.apple.com/test','keys':{'auth':'test','p256dh':'test'}}
        message=self.message('币安人生');old=self.message(age=1801,id='b'*64)
        topic=self.message(id='c'*64,title='',body='[Binance/Aster 专题价差] 1 个信号\n1. IRYS | 多 Binance / 空 Aster')
        feed=dict(sourceConnected=True,updatedAt=datetime.fromtimestamp(self.now,timezone.utc).isoformat(),messages=[message,old,topic])
        live.tick(feed,self.now);self.assertEqual(len(sent),1);self.assertIn('币安人生',sent[0]['rows'][0])
        feed['updatedAt']=datetime.fromtimestamp(self.now+61,timezone.utc).isoformat()
        live.tick(feed,self.now+61);self.assertEqual(len(sent),1)

    def test_v6_build_diagnostics_are_preserved_without_changing_v5_fallback(self):
        config=self.root/'config.json';config.write_text(json.dumps(dict(pairCode='12345678',expiresAt=0,publicKey='public')))
        live=Live(self.root/'mobile',config,lambda *args:201)
        for version in ('radar-delivery-v6','radar-delivery-v6-20261019-startup1','radar-delivery-v6-20261018-treasure1',
                        'radar-delivery-v4','radar-delivery-v5'):
            result=live.device_status(dict(permission='default',version=version))
            self.assertEqual(result['version'],version)
        for version in ('radar-delivery-v6-', 'radar-delivery-v6-20261019-'+('x'*97),'radar-delivery-v6-a\n',
                        'radar-delivery-v6-20261019-X','radar-delivery-v6-a.1','radar-delivery-v7',None,42):
            self.assertEqual(live.device_status(dict(permission='default',version=version))['version'],'unknown')
        payload=dict(kind='radar-six-test',title='',seq=1,run='live',rows=['test'])
        live.device_status(dict(permission='default',version='radar-delivery-v6-20261019-startup1'))
        self.assertEqual(live.notification_payload(payload),payload)
        live.device_status(dict(permission='default',version='radar-delivery-v5'))
        self.assertIn('notification',live.notification_payload(payload))


if __name__=='__main__':unittest.main()
