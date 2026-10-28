import copy
import json
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import desktop_rules_test as rules_base
import desktop_binding_test as binding_base
from desktop_rules import DesktopRules
from server import BASE, handler


class MessageDecisionsTest(unittest.TestCase):
    setUp = rules_base.DesktopRulesTest.setUp
    tearDown = rules_base.DesktopRulesTest.tearDown
    configure = rules_base.DesktopRulesTest.configure

    def ordinary(self, coin='UNITREE', identity='a'*64, **changes):
        return dict(self.message, title=f'{coin} | FF | R0 +0.43%', id=identity,
                    body='买 GATE 永续 → 卖 ASTER 永续', **changes)

    def write_feed(self, messages, pinned=None):
        self.feed.write_text(json.dumps(dict(messages=messages, pinned=pinned), ensure_ascii=False), encoding='utf-8')

    def test_saved_coin_block_applies_to_old_history_and_strong_pinned_read_only(self):
        self.configure(change=lambda s:s['advanced']['coins'].append(dict(coin='UNITREE',exchange='all',enabled=True)))
        old=self.ordinary(sentAt='2020-01-01T00:00:00Z')
        allowed=self.ordinary('BTC','b'*64)
        strong=dict(old,id='c'*64,title='强信号聚集 | UNITREE | 3 组同时 ACTIVE',body='\n'.join(
            f'R0 | FF | 买 GATE 永续 → 卖 {venue} 永续\nV2收敛 · 180秒 · 净均 +0.25% · ACTIVE 5s'
            for venue in ('ASTER','BITGET','OKX')))
        self.write_feed([old,allowed],strong)
        before=copy.deepcopy(self.app.data); files={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result=self.app.web_messages()
        self.assertEqual({key:value['action'] for key,value in result['decisions'].items()}, {'a'*64:'hide','b'*64:'allow','c'*64:'hide'})
        self.assertEqual(self.app.data,before)
        self.assertEqual(self.app.last_seen,0)
        self.assertEqual(files,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(set(result),{'revision','desktopEnabled','decisions'})
        self.assertNotIn('UNITREE',json.dumps(result))

    def test_mute_hide_precedence_and_disabled_channel_use_native_policy(self):
        self.write_feed([self.ordinary()])
        self.configure(action='mute',change=lambda s:s['excluded_coins'].append('UNITREE'))
        result=self.app.web_messages();self.assertEqual(result['decisions']['a'*64]['action'],'mute')
        self.configure(action='hide',change=lambda s:s['excluded_coins'].append('UNITREE'))
        self.assertEqual(self.app.web_messages()['decisions']['a'*64]['action'],'hide')
        self.write_feed([self.ordinary('BTC')])
        self.configure(change=lambda s:s.update(notify_enabled=False))
        result=self.app.web_messages();self.assertFalse(result['desktopEnabled']);self.assertEqual(result['decisions']['a'*64]['action'],'hide')

    def test_defaults_include_all_but_never_create_state(self):
        self.write_feed([self.ordinary()])
        result=self.app.web_messages()
        self.assertTrue(result['desktopEnabled']);self.assertEqual(result['decisions']['a'*64]['action'],'allow')
        self.assertFalse(self.app.path.exists());self.assertFalse(self.app.card_cache_path.exists())

    def test_scope_and_unranked_routes_reuse_same_evaluator(self):
        self.configure(change=lambda s:s['advanced']['coins'].append(dict(coin='UNITREE',exchange='aster',enabled=True)))
        as_route=self.ordinary()
        bg_route=dict(as_route,id='b'*64,body='买 GATE 永续 → 卖 BITGET 永续')
        dex=dict(as_route,id='c'*64,title='DEX套利',body='1. [P1] [期期] UNITREE | 多 GATE 永续 / 空 ASTER 永续')
        self.write_feed([as_route,bg_route,dex])
        expected={m['id']:self.app.decision('desktop',m['id'],self.app.rows(m,time.time()),time.time(),record=False) or 'allow' for m in (as_route,bg_route,dex)}
        self.assertEqual(expected,{'a'*64:'hide','b'*64:'allow','c'*64:'hide'})
        self.assertEqual({k:v['action'] for k,v in self.app.web_messages()['decisions'].items()},expected)

    def test_fingerprint_raw_unicode_and_same_id_changes(self):
        fixture=dict(senderType='bot',id='a'*64,title='机器人 🧪 | FF',body='买 GATE → 卖 ASTER\n"报价" \\ 测试\u2028',sentAt='2026-10-28T21:01:17.123+08:00')
        # Generated independently with Node's SHA256(JSON.stringify(fields)).
        expected='66027d99003130040699f969da2f2272763924f6e80555d93053a0c2b3094c59'
        original=DesktopRules.message_fingerprint(fixture);self.assertEqual(original,expected)
        self.assertEqual(len(original),64)
        for key in ('title','body','sentAt'):
            self.assertNotEqual(DesktopRules.message_fingerprint(dict(fixture,**{key:fixture[key]+' '})),original)
        for invalid in (None,dict(fixture,sentAt=None),dict(fixture,title=123),dict(fixture,body='\ud800'),dict(fixture,senderType='person')):
            self.assertIsNone(DesktopRules.message_fingerprint(invalid))

    def test_pinned_not_truncated_after_bounded_history(self):
        messages=[self.ordinary('BTC',f'{i:064x}') for i in range(1001)]
        pinned=self.ordinary('UNITREE','f'*64)
        self.write_feed(messages,pinned)
        self.configure(change=lambda s:s['excluded_coins'].append('UNITREE'))
        result=self.app.web_messages()['decisions']
        self.assertEqual(len(result),1001);self.assertNotIn(f'{1000:064x}',result)
        self.assertEqual(result['f'*64]['action'],'hide')

    def test_bad_source_is_error_and_malformed_messages_have_no_allow(self):
        for raw in ('{}','[]','{"messages":null}','not json'):
            self.feed.write_text(raw)
            with self.assertRaises((ValueError,TypeError)):self.app.web_messages()
        self.write_feed([None,dict(self.ordinary(),title=None)])
        self.assertEqual(self.app.web_messages()['decisions'],{})
        self.feed.unlink()
        with self.assertRaises(OSError):self.app.web_messages()


class MessageDecisionsHTTPTest(unittest.TestCase):
    setUp = binding_base.DesktopBindingTest.setUp

    def test_route_is_scoped_no_store_read_only_and_source_failures_close(self):
        owner=self.profiles.accounts['legacy']
        token=self.profiles.pair('12345678','fixture-owner')
        owner_policy=self.bindings.policy(owner)
        other_policy=self.bindings.policy(self.accounts[0])
        for policy,action in ((owner_policy,'hide'),(other_policy,'mute')):
            settings=copy.deepcopy(policy.data['desktop']['rules'][action]);settings['excluded_coins']=['BTC']
            policy.configure(dict(revision=0,channel='desktop',settings=settings,action=action))
        constructed=[]
        def constructor(directory,*args):
            policy=DesktopRules(directory,self.feed,self.cards);constructed.append(policy);return policy
        with patch('desktop_rules.DesktopRules',side_effect=constructor):
            http=ThreadingHTTPServer(('127.0.0.1',0),handler(self.profiles))
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        def get(token):
            conn=HTTPConnection(*http.server_address)
            conn.request('GET',BASE+'api/message-decisions',headers={'Authorization':'Bearer '+token})
            response=conn.getresponse();status=response.status;cache=response.getheader('Cache-Control');value=json.loads(response.read());conn.close()
            return status,cache,value
        before={p:p.read_bytes() for p in self.profiles.directory.rglob('*') if p.is_file()}
        try:
            for bearer in ('','wrong'):
                status,cache,value=get(bearer);self.assertEqual(status,401);self.assertEqual(cache,'no-store');self.assertNotIn('decisions',value)
            for bearer,expected in ((token,'hide'),(self.codes[0]['token'],'mute'),(self.codes[1]['token'],'allow')):
                status,cache,value=get(bearer);self.assertEqual(status,200);self.assertEqual(cache,'no-store')
                self.assertEqual(value['decisions']['a'*64]['action'],expected)
                self.assertEqual(set(value),{'revision','desktopEnabled','decisions'})
                self.assertNotIn(bearer,json.dumps(value));self.assertNotIn('BTC',json.dumps(value))
            self.feed.unlink()
            status,cache,value=get(token);self.assertEqual(status,503);self.assertEqual(cache,'no-store');self.assertEqual(set(value),{'error'})
            self.assertEqual(before,{p:p.read_bytes() for p in self.profiles.directory.rglob('*') if p.is_file()})
            self.assertTrue(all(p.last_seen==0 for p in constructed));self.assertEqual(self.sent,[])
        finally:
            http.shutdown();http.server_close();thread.join()


if __name__=='__main__':unittest.main()
