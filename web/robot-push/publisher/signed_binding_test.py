"""Real signed publisher HTTP dispatch to an isolated real profile HTTP server."""
import base64, copy, hashlib, json, secrets, subprocess, sys, tempfile, threading, time, unittest
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path
from urllib.request import Request, urlopen as real_urlopen
from unittest.mock import patch
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from contract_local import crypto_command
import server


CHILD = r'''
import json,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
from http.server import ThreadingHTTPServer
import profiles,desktop_rules
from profiles import Profiles
from server import handler
root=Path(sys.argv[1]);config=root/'config.json'
config.write_text(json.dumps(dict(pairCode='12345678',expiresAt=0,publicKey='fixture')))
app=Profiles(root/'state',config,lambda *args:(_ for _ in ()).throw(AssertionError('test sent a notification')))
profiles.secrets.randbelow=lambda maximum:87654321
app.create_code('a'*32)
for account in app.accounts.values():
 account.state['subscription']={'endpoint':'https://fixture.push.apple.com/isolated','keys':{'auth':'synthetic','p256dh':'synthetic'}}
 account.save()
feed=root/'feed.json';cards=root/'cards.json'
feed.write_text(json.dumps(dict(messages=[dict(id='a'*64,senderType='bot',title='BTC | FF | R2 +1.13%',body='买 BINANCE 永续 → 卖 GATE 永续',sentAt=datetime.now(timezone.utc).isoformat())])))
cards.write_text(json.dumps(dict(snapshot=dict(complete=True,active=[dict(id='one',pair='pair-one',asset='BTC',strategy='FF',validUntil=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat(),v2Residual=dict(level=2,bps=113),details=dict(legs=[dict(exchange='binance'),dict(exchange='gate')]))]))))
original=desktop_rules.DesktopRules
legacy=original(app.directory,feed,cards)
legacy.data['desktop']['settings']['notify_enabled']=False
for rules in legacy.data['desktop']['rules'].values():rules['notify_enabled']=False
legacy.save()
desktop_rules.DesktopRules=lambda directory,*args:original(directory,feed,cards)
http=ThreadingHTTPServer(('127.0.0.1',0),handler(app))
(root/'ready.json').write_text(json.dumps(dict(port=http.server_port)))
http.serve_forever()
'''


class SignedBindingTest(unittest.TestCase):
    def test_signed_dispatch_profile_isolation_and_unbound_all(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);phone=root/'phone';phone.mkdir()
            child=subprocess.Popen([sys.executable,'-c',CHILD,str(phone)],cwd=Path(__file__).resolve().parents[2]/'push-test',stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            http=None;thread=None
            try:
                deadline=time.monotonic()+10
                while not (phone/'ready.json').exists():
                    if child.poll() is not None:raise AssertionError(child.stderr.read().decode())
                    if time.monotonic()>deadline:raise AssertionError('Profile HTTP fixture startup timed out')
                    time.sleep(.02)
                port=json.loads((phone/'ready.json').read_text())['port']
                def bridge(request,**kwargs):
                    self.assertIn(request.full_url,('http://127.0.0.1:18885/internal/desktop-binding','http://127.0.0.1:18885/internal/coin-rules'))
                    forwarded=Request(request.full_url.replace(':18885',':'+str(port)),data=request.data,headers=dict(request.header_items()),method=request.get_method())
                    return real_urlopen(forwarded,**kwargs)
                keys=[ec.generate_private_key(ec.SECP256R1()) for _ in range(2)];ids=[]
                for i,key in enumerate(keys):
                    pub=key.public_key();der=pub.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
                    ids.append(hashlib.sha256(der).hexdigest()[:16])
                    (root/('publisher-public.pem' if i==0 else 'desktop-reader-'+ids[-1]+'.pem')).write_bytes(pub.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
                ready=threading.Event();failure=[]
                class Receiver:
                    def state(self):return dict(cloudMode=True,sourceConnected=True,groups=[],messages=[],pinned=None,pinnedGroupId='')
                def serve():
                    nonlocal http
                    try:
                        http=HTTPServer(('127.0.0.1',0),server.Handler)
                        http.publisher=server.Publisher(root/'publisher',root/'publisher-public.pem');http.receiver=Receiver();ready.set();http.serve_forever()
                        http.publisher.db.close()
                    except BaseException as error:failure.append(error);ready.set()
                with patch.object(server.subprocess,'run',crypto_command),patch('desktop_binding.urlopen',side_effect=bridge),patch('coin_control.urlopen',side_effect=bridge):
                    thread=threading.Thread(target=serve,daemon=True);thread.start();self.assertTrue(ready.wait(10));self.assertEqual(failure,[])
                    def request(data):
                        body=json.dumps(data).encode();stamp=str(int(time.time()));nonce=secrets.token_hex(16)
                        signature=keys[1].sign(server.canonical(stamp,nonce,body,server.CONTROL_ROUTE),ec.ECDSA(hashes.SHA256()))
                        headers={'Content-Type':'application/json','X-Publish-Key':ids[1],'X-Publish-Time':stamp,'X-Publish-Nonce':nonce,'X-Publish-Signature':base64.b64encode(signature).decode()}
                        conn=HTTPConnection(*http.server_address,timeout=10);conn.request('POST',server.CONTROL_ROUTE,body,headers);response=conn.getresponse();value=json.loads(response.read());conn.close();return response.status,value
                    def state(code):return request(dict(action='state',desktopRules=1,pushCode=code))
                    before={p:p.read_bytes() for p in (phone/'state').rglob('state.json')}
                    status,unbound=state('');self.assertEqual(status,200);self.assertFalse(unbound['pushBinding']['bound']);self.assertTrue(unbound['desktopRules']['desktopEnabled'])
                    status,owner=state('12345678');self.assertEqual(status,200);self.assertFalse(owner['desktopRules']['desktopEnabled'])
                    status,personal=state('87654321');self.assertEqual(status,200);self.assertTrue(personal['desktopRules']['desktopEnabled'])
                    self.assertEqual(before,{p:p.read_bytes() for p in (phone/'state').rglob('state.json')})
                    status,invalid=state('00000000');self.assertEqual(status,400);self.assertNotIn('messages',invalid);self.assertNotIn('pushBinding',invalid)
                    self.assertEqual(request(dict(action='coin-rules',request={'op':'state'}))[0],403)
                    control=dict(action='coin-rules',pushCode='87654321',request=dict(op='block',request=dict(requestId='signed-http-001',coins=['BTC'],exchange='all')))
                    status,edited=request(control);self.assertEqual(status,200);self.assertTrue(edited['ok'])
                    self.assertEqual(state('87654321')[1]['desktopRules']['cards'],{'pair-one':'hide'})
                    self.assertEqual(state('12345678')[1]['desktopRules']['cards'],{})
                    self.assertEqual(state('')[1]['desktopRules']['messages'],{})
                    self.assertEqual(state('')[1]['desktopRules']['cards'],{})
                    for path,raw in before.items():self.assertEqual(json.loads(raw)['subscription'],json.loads(path.read_bytes())['subscription'])
                    self.assertNotIn('87654321',json.dumps(edited))
                    http.shutdown();thread.join(10);self.assertFalse(thread.is_alive());http.server_close();http=None
                self.assertEqual(failure,[])
            finally:
                if http is not None:http.shutdown();http.server_close()
                if thread is not None:thread.join(10)
                child.terminate();child.wait(timeout=10);child.stderr.close()


if __name__=='__main__':unittest.main()
