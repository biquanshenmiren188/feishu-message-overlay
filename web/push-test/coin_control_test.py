import unittest
from unittest.mock import Mock
from coin_control import dispatch
class CoinControlTest(unittest.TestCase):
 def test_only_explicit_coin_operations_reach_shared_engine(self):
  desktop=Mock();owner=object();request={'requestId':'existing-request'}
  dispatch(desktop,owner,{'op':'state'});desktop.coin_state.assert_called_once_with(owner)
  dispatch(desktop,owner,{'op':'block','request':request});desktop.block_coins.assert_called_once_with(request,owner)
  dispatch(desktop,owner,{'op':'edit','request':request});desktop.edit_coins.assert_called_once_with(request,owner)
  for data in ({},{'op':'state','extra':True},{'op':'configure','request':{}},{'op':'edit','request':[]}):
   with self.assertRaises(ValueError):dispatch(desktop,owner,data)
if __name__=='__main__':unittest.main()
