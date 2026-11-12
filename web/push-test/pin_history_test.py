import copy, io, json, threading, unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import desktop_binding_test as base
from server import BASE, handler

class PinHistoryTest(unittest.TestCase):
    setUp=base.DesktopBindingTest.setUp
    data=base.DesktopBindingTest.data

    def test_public_bound_isolation_and_no_delivery_side_effects(self):
        self.bindings.coins(dict(self.data(),request=dict(op='block',request=dict(requestId='history-fixture',coins=['BTC'],exchange='all'))))
        first=json.loads(self.feed.read_text())['messages'][0]
        second=dict(first,id='b'*64,title='ETH | FF | R2 +1.13%')
        envelope=dict(messages=[first,second],currentId=first['id'],limit=5)
        before={p:p.read_bytes() for p in self.profiles.directory.rglob('*') if p.is_file()}
        with patch('desktop_rules.DesktopRules',return_value=self.legacy):app=ThreadingHTTPServer(('127.0.0.1',0),handler(self.profiles))
        thread=threading.Thread(target=app.serve_forever,daemon=True);thread.start()
        def get(auth=None):
            client=HTTPConnection('127.0.0.1',app.server_port)
            client.request('GET',BASE+'api/pinned-history',headers={} if auth is None else {'Authorization':'Bearer '+auth})
            response=client.getresponse();result=(response.status,json.loads(response.read()));client.close();return result
        try:
            with patch('urllib.request.urlopen',side_effect=lambda *a,**k:io.BytesIO(json.dumps(envelope).encode())) as fetch:
                self.assertEqual(len(get()[1]['messages']),2)
                code,value=get(self.codes[0]['token']);self.assertEqual(code,200);self.assertEqual([m['id'] for m in value['messages']],['b'*64]);self.assertEqual(value['hiddenCount'],1)
                self.assertEqual(len(get(self.codes[1]['token'])[1]['messages']),2)
                calls=fetch.call_count;self.assertEqual(get('invalid')[0],401);self.assertEqual(fetch.call_count,calls)
            with patch('urllib.request.urlopen',side_effect=OSError('offline')):self.assertEqual(get()[0],503)
            self.assertEqual(before,{p:p.read_bytes() for p in self.profiles.directory.rglob('*') if p.is_file()})
            self.assertEqual(self.sent,[])
        finally:app.shutdown();thread.join();app.server_close()

if __name__=='__main__':unittest.main()
