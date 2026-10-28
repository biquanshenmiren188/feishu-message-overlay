import copy,json,time,unittest
from unittest.mock import patch
import desktop_rules_test as base
from advanced_rules import DEFAULT,card_oi_evidence,reasons

class CardOITest(unittest.TestCase):
 setUp=base.DesktopRulesTest.setUp
 tearDown=base.DesktopRulesTest.tearDown
 configure=base.DesktopRulesTest.configure
 def test_display_evidence_is_the_exact_filter_snapshot(self):
  self.configure('cards',change=lambda s:s['advanced'].update(globalOI=50))
  now=time.time();values={ex:{ex+':BTCUSDT':dict(value=800000 if ex=='binance' else 371600,time=now*1000,basis='double-v1')} for ex in ('binance','gate')}
  self.app.oi._read=lambda ex,n:(ex,values[ex])
  result=self.app.web_cards()
  self.assertEqual(result['decisions']['pair-one'],'hide')
  right=result['oi']['pair-one']['right'];self.assertEqual(right['value'],371600);self.assertEqual(right['threshold'],50)
  values['gate']['gate:BTCUSDT']['value']=500000
  result=self.app.web_cards();self.assertEqual(result['decisions']['pair-one'],'allow');self.assertEqual(result['oi']['pair-one']['right']['value'],500000)
  self.assertEqual(right['value'],371600,'Previously returned evidence must not mutate with cache')
 def test_disabled_or_missing_does_not_return_misleading_reference_value(self):
  self.configure('cards',change=lambda s:s['advanced'].update(globalOI=50,missing='allow'))
  self.app.oi._read=lambda ex,n:(ex,{})
  result=self.app.web_cards();self.assertEqual(result['decisions']['pair-one'],'allow')
  self.assertEqual(result['oi']['pair-one']['right']['status'],'missing');self.assertNotIn('value',result['oi']['pair-one']['right'])
  self.configure('cards',change=lambda s:s.update(notify_enabled=False))
  self.assertEqual(self.app.web_cards()['oi']['pair-one'],{})
 def test_overrides_spot_and_expiry_match_evaluator(self):
  now=time.time();a=copy.deepcopy(DEFAULT);a.update(globalOI=50,exchangeOI={'aster':{'mode':'custom','value':90}})
  row=dict(coin='EVAA',buy='GATE',sell='ASTER',mode='SF',oiCheckedAt=now,oi={'right':dict(value=870000,basis='double-v1',time=now*1000)})
  evidence=card_oi_evidence(row,a);self.assertEqual(evidence['right']['threshold'],90);self.assertEqual(evidence['left']['market'],'spot');self.assertNotIn('value',evidence['left']);self.assertTrue(reasons(row,a))
  a['coinOI']=[dict(coin='EVAA',exchange='aster',enabled=True,value=80)]
  self.assertEqual(card_oi_evidence(row,a)['right']['threshold'],80);self.assertFalse(reasons(row,a))
  row['oi']['right']['time']-=300001
  self.assertEqual(card_oi_evidence(row,a)['right']['status'],'missing');self.assertTrue(reasons(row,a))
  a['exchangeOI']['aster']['mode']='none';a['coinOI']=[]
  self.assertEqual(card_oi_evidence(row,a)['right']['status'],'not-filtered');self.assertFalse(reasons(row,a))

if __name__=='__main__':unittest.main()
