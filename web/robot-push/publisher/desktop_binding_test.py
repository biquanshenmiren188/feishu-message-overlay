import json, unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from desktop_binding import desktop_state
from state_delta import state_request
from coin_control import coin_control, valid_control

class DesktopBindingTest(unittest.TestCase):
    def test_unbound_is_all_allow_even_if_policy_service_is_offline(self):
        with patch('desktop_binding.urlopen',side_effect=AssertionError('unbound must not read owner rules')):
            result=desktop_state('', 'a'*16)
        self.assertEqual(result['pushBinding'],dict(protocol=1,bound=False,canManage=False))
        self.assertTrue(result['desktopRules']['desktopEnabled']);self.assertTrue(result['desktopRules']['cardsEnabled'])
        self.assertEqual(result['desktopRules']['messages'],{})

    def test_bound_proxy_is_fixed_destination_and_does_not_fall_back_on_failure(self):
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{"pushBinding":{"protocol":1,"bound":true,"canManage":true}}'
        with patch('desktop_binding.urlopen',return_value=response) as send:
            self.assertTrue(desktop_state('12345678','a'*16)['pushBinding']['bound'])
            request=send.call_args.args[0]
            self.assertEqual(request.full_url,'http://127.0.0.1:18885/internal/desktop-binding')
            self.assertEqual(json.loads(request.data),dict(pushCode='12345678',client='a'*16))
        with patch('desktop_binding.urlopen',side_effect=HTTPError('http://127.0.0.1',400,'bad',{},None)):
            with self.assertRaises(HTTPError):desktop_state('00000000','a'*16)

    def test_state_request_rejects_unknown_fields_and_malformed_code(self):
        for code in ('','12345678'):
            self.assertTrue(state_request(dict(action='state',desktopRules=1,pushCode=code,known={'messages':'a'*64})))
        for code in ('123','１２３４５６７８',None,12345678,{},'12345678\n'):
            self.assertFalse(state_request(dict(action='state',desktopRules=1,pushCode=code)))
        self.assertFalse(state_request(dict(action='state',pushCode='12345678')))
        self.assertFalse(state_request(dict(action='state',desktopRules=1,pushCode='12345678',profileId='legacy')))

    def test_bound_coin_controls_reach_only_scoped_fixed_route(self):
        control=dict(action='coin-rules',pushCode='12345678',request={'op':'state'})
        self.assertTrue(valid_control(control))
        self.assertFalse(valid_control(dict(control,pushCode='')))
        self.assertFalse(valid_control(dict(control,profileId='legacy')))
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{}'
        with patch('coin_control.urlopen',return_value=response) as send:
            self.assertTrue(coin_control(control,'a'*16)['ok'])
            req=send.call_args.args[0]
            self.assertEqual(req.full_url,'http://127.0.0.1:18885/internal/coin-rules')
            self.assertEqual(json.loads(req.data),dict(pushCode='12345678',client='a'*16,request={'op':'state'}))
        with self.assertRaises(ValueError):coin_control(control)

if __name__ == '__main__':unittest.main()
