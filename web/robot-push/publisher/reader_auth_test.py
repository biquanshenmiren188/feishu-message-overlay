"""Synthetic reader authorization regression; no production credentials or messages."""
import base64, hashlib, json, secrets, tempfile, time
from pathlib import Path
from unittest.mock import patch
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
import server
from contract_local import crypto_command


def run():
    checks=[]
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)
        keys=[ec.generate_private_key(ec.SECP256R1()) for _ in range(2)]
        ids=[]
        for index,key in enumerate(keys):
            public=key.public_key()
            der=public.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
            ids.append(hashlib.sha256(der).hexdigest()[:16])
            path=root/('publisher-public.pem' if index==0 else 'desktop-reader-'+ids[-1]+'.pem')
            path.write_bytes(public.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        with patch.object(server.subprocess,'run',crypto_command):
            publisher=server.Publisher(root/'state',root/'publisher-public.pem')
            def request(index,payload,route=server.CONTROL_ROUTE,age=0,nonce=None):
                body=json.dumps(payload).encode();stamp=str(int(time.time())-age);nonce=nonce or secrets.token_hex(16)
                signature=keys[index].sign(server.canonical(stamp,nonce,body,route),ec.ECDSA(hashes.SHA256()))
                return {'X-Publish-Key':ids[index],'X-Publish-Time':stamp,'X-Publish-Nonce':nonce,'X-Publish-Signature':base64.b64encode(signature).decode()},body,route
            def check(name,request,code=None):
                headers,body,route=request
                try: result=publisher.authenticate(headers,body,time.time(),route)
                except server.Rejected as error:
                    assert error.code==code,(name,error.code,code);checks.append(name);return
                assert code is None,(name,'unexpected acceptance');checks.append(name);return result
            check('primary state preserved',request(0,{'action':'state'}))
            check('primary configure preserved',request(0,{},server.CONFIG_ROUTE))
            check('primary publish preserved',request(0,{},server.ROUTE))
            check('reader state accepted',request(1,{'action':'state'}))
            check('reader conditional state accepted',request(1,{'action':'state','known':{'messages':'a'*64}}))
            check('reader invalid cursor denied',request(1,{'action':'state','known':{'messages':'bad'}}),403)
            check('reader unknown component denied',request(1,{'action':'state','known':{'secrets':'a'*64}}),403)
            check('reader pin denied',request(1,{'action':'pin','pinnedGroupId':''}),403)
            check('reader extra fields denied',request(1,{'action':'state','extra':True}),403)
            check('reader configure denied',request(1,{},server.CONFIG_ROUTE),401)
            check('reader publish denied',request(1,{},server.ROUTE),401)
            req=request(1,{'action':'state'});req[0]['X-Publish-Key']='../publisher-public'
            check('path traversal denied',req,401)
            req=request(1,{'action':'state'});req[0]['X-Publish-Key']='0'*16
            check('unregistered key denied',req,401)
            req=request(1,{'action':'state'});req[0]['X-Publish-Signature']=base64.b64encode(b'x'*70).decode()
            check('invalid signature denied',req,401)
            check('expired request denied',request(1,{'action':'state'},age=120),401)
            req=request(1,{'action':'state'});nonce=check('first nonce accepted',req)
            publisher.db.execute('INSERT INTO nonces VALUES (?,?)',(nonce,time.time()));publisher.db.commit()
            check('replay denied',req,409)
            check('same raw nonce primary independent',request(0,{'action':'state'},nonce=req[0]['X-Publish-Nonce']))
            publisher.db.execute('DELETE FROM nonces')
            publisher.db.executemany('INSERT INTO nonces VALUES (?,?)',[(secrets.token_hex(16),time.time()) for _ in range(30)]);publisher.db.commit()
            check('primary quota enforced',request(0,{'action':'state'}),429)
            check('reader quota independent',request(1,{'action':'state'}))
            publisher.db.execute('DELETE FROM nonces')
            publisher.db.executemany('INSERT INTO nonces VALUES (?,?)',[(ids[1]+':'+secrets.token_hex(16),time.time()) for _ in range(30)]);publisher.db.commit()
            check('reader quota enforced',request(1,{'action':'state'}),429)
            check('primary unaffected by reader quota',request(0,{'action':'state'}))
            publisher.db.execute('DELETE FROM nonces');publisher.db.commit()
            (root/('desktop-reader-'+ids[1]+'.pem')).rename(root/'revoked.pem')
            check('revocation immediate',request(1,{'action':'state'}),401)
            publisher.db.close()
    return {'passed':len(checks),'checks':checks,'syntheticOnly':True,'backend':'cryptography ECDSA; OpenSSL adapter'}


if __name__=='__main__': print(json.dumps(run()))
