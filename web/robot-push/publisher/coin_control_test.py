import io,json,unittest
from urllib.error import HTTPError
from unittest.mock import patch,MagicMock
from coin_control import coin_control,valid_control
class CoinControlTest(unittest.TestCase):
 def test_only_allowlisted_operations_and_fixed_loopback_target(self):
  request={'op':'block','request':{'requestId':'native-check-001','coins':['PTB'],'exchange':'all'}}
  response=MagicMock();response.__enter__.return_value.read.return_value=b'{"operation":{"results":{}}}'
  with patch('coin_control.urlopen',return_value=response) as send:
   self.assertTrue(coin_control({'action':'coin-rules','request':request})['ok'])
   req=send.call_args.args[0];self.assertEqual(req.full_url,'http://127.0.0.1:18885/internal/coin-rules');self.assertEqual(json.loads(req.data),request)
 def test_no_arbitrary_operation_or_destination(self):
  for data in ({'action':'coin-rules','request':{'op':'configure','request':{}}},{'action':'coin-rules','request':{'op':'state','url':'http://evil.invalid'}},{'action':'coin-rules','request':{'op':'edit','request':[]}},[]):
   self.assertFalse(valid_control(data))
   with self.assertRaises(ValueError):coin_control(data)
 def test_conflict_is_reported_not_success(self):
  error=HTTPError('http://127.0.0.1',400,'bad',{},io.BytesIO('{"error":"规则冲突"}'.encode()))
  with patch('coin_control.urlopen',side_effect=error):self.assertEqual(coin_control({'action':'coin-rules','request':{'op':'state'}}),{'ok':False,'error':'规则冲突'})
if __name__=='__main__':unittest.main()
