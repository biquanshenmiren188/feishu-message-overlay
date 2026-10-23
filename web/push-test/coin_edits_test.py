import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import coin_blocks_test
from advanced_rules import DEFAULT
from desktop_rules import DesktopRules
from coin_edits import rule_map

class CoinEditsTest(unittest.TestCase):
 setUp=coin_blocks_test.CoinBlocksTest.setUp
 def req(self,changes,identity='edit-request-001',**extra):return dict(requestId=identity,changes=changes,**extra)
 def change(self,c='mute',coin='PTB',ex='all',before=None,after=True):return dict(channel=c,coin=coin,exchange=ex,before=before,after=after)
 def test_matrix_add_edit_pause_delete_preserves_other_fields(self):
  self.app.data['cards']['settings']['advanced']['globalOI']=17
  original=copy.deepcopy(self.phone.state)
  changes=[self.change(c) for c in ('desktop','mute','cards','mobile')]
  first=self.app.edit_coins(self.req(changes),self.phone)
  self.assertTrue(all(v['state']=='saved' for v in first['operation']['results'].values()))
  second=self.app.edit_coins(self.req([self.change('mute',before=True,after=False),self.change('cards',before=True,after=None)],'edit-request-002'),self.phone)
  self.assertEqual(rule_map(second['desktop']['desktop']['rules']['mute']),{('PTB','all'):False})
  self.assertEqual(rule_map(second['desktop']['cards']['settings']),{})
  self.assertEqual(second['desktop']['cards']['settings']['advanced']['globalOI'],17)
  self.assertTrue(rule_map(second['mobile']['settings'])[('PTB','all')]);self.assertEqual(self.phone.state.get('subscription'),original.get('subscription'));self.assertEqual(self.sent,[])
 def test_legacy_exact_scope_delete_and_undo(self):
  settings=self.phone.state['live']['settings'];settings['excluded_coins']=['PTB','MITO'];settings.setdefault('advanced',copy.deepcopy(DEFAULT))['coins']=[dict(coin='PTB',exchange='gate',enabled=True)]
  delete=self.change('mobile',before=True,after=None);result=self.app.edit_coins(self.req([delete]),self.phone)
  self.assertEqual(rule_map(result['mobile']['settings']),{('MITO','all'):True,('PTB','gate'):True})
  undo=self.app.edit_coins(self.req([dict(delete,before=None,after=True)],'edit-request-undo',undoOf='edit-request-001'),self.phone)
  self.assertTrue(rule_map(undo['mobile']['settings'])[('PTB','all')]);self.assertTrue(rule_map(undo['mobile']['settings'])[('PTB','gate')])
 def test_conflicts_do_not_overwrite_and_channel_is_atomic(self):
  self.app.data['cards']['settings']['advanced']['coins']=[dict(coin='PTB',exchange='all',enabled=False)]
  result=self.app.edit_coins(self.req([self.change('cards',before=True,after=None),self.change('cards',coin='ETH'),self.change('mute')]),self.phone)
  self.assertEqual(result['operation']['results']['cards']['state'],'failed');self.assertEqual(rule_map(result['desktop']['cards']['settings']),{('PTB','all'):False});self.assertEqual(result['operation']['results']['mute']['state'],'saved')
 def test_retry_durable_and_only_failed_channel(self):
  request=self.req([self.change('mute'),self.change('mobile')])
  with patch.object(self.phone,'configure',side_effect=OSError('private path')):first=self.app.edit_coins(request,self.phone)
  self.assertEqual(first['operation']['results']['mobile']['state'],'failed');self.assertNotIn('private path',json.dumps(first))
  restored=DesktopRules(self.root/'state');second=restored.edit_coins(request,self.phone)
  self.assertEqual(first['desktop']['revision'],second['desktop']['revision']);again=restored.edit_coins(request,self.phone);self.assertEqual(second['operation'],again['operation']);self.assertEqual(second['mobile']['revision'],again['mobile']['revision'])
 def test_undo_refuses_new_rule_and_invalid_reference(self):
  self.app.edit_coins(self.req([self.change()]),self.phone)
  deleted=self.req([self.change(before=True,after=None)],'edit-request-del');self.app.edit_coins(deleted,self.phone)
  self.app.edit_coins(self.req([self.change(after=False)],'edit-request-new'),self.phone)
  with self.assertRaises(ValueError):self.app.edit_coins(self.req([self.change()],'edit-request-undo',undoOf='edit-request-del'),self.phone)
  with self.assertRaises(ValueError):self.app.edit_coins(self.req([self.change(coin='ETH')],'edit-request-undo2',undoOf='edit-request-del'),self.phone)
  self.assertFalse(rule_map(self.app.data['desktop']['rules']['mute'])[('PTB','all')])
 def test_request_validation_and_identity_collision(self):
  valid=self.change();before=copy.deepcopy(self.app.data)
  for changes in ([dict(valid,before=1)],[dict(valid,channel='bad')],[dict(valid,exchange='bad')],[valid,valid],[dict(valid,before=True)],[]):
   with self.assertRaises(ValueError):self.app.edit_coins(self.req(changes),self.phone)
  self.assertEqual(before,self.app.data)
  request=self.req([valid]);self.app.edit_coins(request,self.phone)
  with self.assertRaises(ValueError):self.app.block_coins(dict(self.request,requestId=request['requestId']),self.phone)
  with self.assertRaises(ValueError):self.app.edit_coins(self.req([self.change(coin='ETH')]),self.phone)
 def test_intent_write_failure_is_no_change(self):
  with patch.object(self.app,'save',side_effect=OSError('disk')):
   with self.assertRaises(OSError):self.app.edit_coins(self.req([self.change()]),self.phone)
  self.assertEqual(self.app.status()['revision'],0);self.assertEqual(rule_map(self.app.data['desktop']['rules']['mute']),{})
 def test_interrupted_mobile_commit_retries_without_lost_edits(self):
  request=self.req([self.change('mobile')]);save=self.app.save;calls=0
  def flaky():
   nonlocal calls
   calls+=1
   if calls==2:raise OSError('journal write')
   save()
  with patch.object(self.app,'save',side_effect=flaky):first=self.app.edit_coins(request,self.phone)
  self.assertEqual(first['operation']['results']['mobile']['state'],'failed');revision=self.phone.state['live']['revision']
  second=self.app.edit_coins(request,self.phone);self.assertEqual(second['operation']['results']['mobile']['state'],'saved');self.assertEqual(second['mobile']['revision'],revision)

if __name__=='__main__':unittest.main()
