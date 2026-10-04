"""Consume public signatures made inside the Windows app; never receives a private key."""
import base64,json,tempfile,time
from pathlib import Path
from server import Publisher,Rejected,MAX_BODY

def run(public_key,vectors_path):
    vectors=json.loads(Path(vectors_path).read_text());checks=[]
    with tempfile.TemporaryDirectory(prefix='robot-contract-') as directory:
        p=Publisher(directory,public_key)
        def send(name,headers=None,body=None,now=None):
            v=vectors[name];return p.accept(headers or v['headers'],base64.b64decode(v['body']) if body is None else body,float(v['headers']['X-Publish-Time']) if now is None else now)
        def reject(name,status,**kw):
            try:send(name,**kw);raise AssertionError('Rejected request was accepted')
            except Rejected as e:assert e.code==status,(name,e.code);checks.append(name+':'+str(status))
        result=send('valid');assert result['accepted']==1 and result['normalCount']==1;checks.append('valid_ecdsa_der')
        reject('valid',409)
        result=send('duplicate');assert result['accepted']==0 and result['normalCount']==1;checks.append('message_id_dedup')
        # A fresh nonce with the old signature must fail authentication.
        h=dict(vectors['valid']['headers']);h['X-Publish-Nonce']='0'*32
        reject('valid',401,headers=h)
        h=dict(vectors['valid']['headers']);h['X-Publish-Key']='wrong';reject('valid',401,headers=h)
        reject('valid',413,body=b'x'*(MAX_BODY+1))
        reject('valid',401,now=float(vectors['valid']['headers']['X-Publish-Time'])+61)
        reject('batchLimit',400);reject('human',403)
        result=send('pin');assert result['normalCount']==0 and result['pinned'];checks.append('independent_pin')
        result=send('pinClearNormal');assert result['pinned'];checks.append('normal_clear_preserves_pin')
        send('offline');feed=json.loads((Path(directory)/'feed.json').read_text());assert feed['sourceConnected'] is False and feed['pinned'];checks.append('explicit_source_offline')
        p.db.close();p=Publisher(directory,public_key);reject('valid',409);checks.append('replay_survives_restart')
        now=float(vectors['valid']['headers']['X-Publish-Time'])
        for i in range(30):p.db.execute('INSERT INTO nonces VALUES (?,?)',(f'limit{i}',now))
        p.db.commit();h=dict(vectors['valid']['headers']);h['X-Publish-Nonce']='1'*32;reject('valid',429,headers=h)
        p.db.close()
    return {'passed':True,'checks':checks,'syntheticOnly':True,'privateKeyReceived':False}

if __name__=='__main__':
    import sys
    print(json.dumps(run(sys.argv[1],sys.argv[2]),separators=(',',':')))
