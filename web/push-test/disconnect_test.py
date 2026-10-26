import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from server import handler,BASE

class DisconnectTest(unittest.TestCase):
    def make(self):
        account=SimpleNamespace(authenticate=lambda token:True,receipt=Mock())
        Handler=handler(account);h=Handler.__new__(Handler)
        h.send_response=Mock();h.send_header=Mock();h.end_headers=Mock();h.wfile=Mock()
        h.headers={'Content-Length':'2','Authorization':'Bearer fixture'}
        h.rfile=io.BytesIO(b'{}');h.path=BASE+'api/receipt';h.client_address=('127.0.0.1',1)
        return h,account

    def test_disconnect_does_not_retry_response_or_committed_operation(self):
        for error in (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
            for phase in ('headers','body'):
                h,account=self.make()
                (h.end_headers if phase=='headers' else h.wfile.write).side_effect=error()
                h.do_POST()
                account.receipt.assert_called_once_with({})
                h.send_response.assert_called_once_with(200)
                self.assertTrue(h.close_connection)

    def test_other_server_errors_are_not_silenced(self):
        h,_=self.make();h.wfile.write.side_effect=RuntimeError('disk or programmer failure')
        with self.assertRaises(RuntimeError):h.reply(200,{'ok':True})

    def test_success_still_sends_json_and_no_store(self):
        h,_=self.make();h.reply(200,{'ok':True})
        self.assertEqual(json.loads(h.wfile.write.call_args.args[0]),{'ok':True})
        h.send_header.assert_any_call('Cache-Control','no-store')

if __name__=='__main__':unittest.main()
