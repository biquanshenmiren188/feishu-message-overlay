"""Accepted history persists; incoming stale events still cannot become alerts."""
import hashlib,json,tempfile,time
from pathlib import Path
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import server
from contract_local import crypto_command
from cloud_receiver import CloudReceiver

def run():
    now=time.time();digest=lambda v:hashlib.sha256(str(v).encode()).hexdigest()
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);key=ec.generate_private_key(ec.SECP256R1());public=root/'public.pem'
        public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        group=digest('group')
        def msg(i):return dict(id=digest(i),groupId=group,senderType='bot',sentAt=server.iso(now-(40-i)*3600),title='Synthetic',body='Fixture',actions=[])
        with patch.object(server.subprocess,'run',crypto_command):
            p=server.Publisher(root/'state',public)
            p.normal={m['id']:m for m in map(msg,range(40))};p.pin={**msg(0),'groupId':digest('pin')}
            p.write(True,now);assert len(p.normal)==30 and digest(10) in p.normal and digest(9) not in p.normal
            pin=p.pin.copy();p.db.close();p=server.Publisher(root/'state',public)
            p.write(True,now+86400);assert len(p.normal)==30 and p.pin==pin
            r=CloudReceiver(p,root,'not-started','not-started');r.connected=True;r.verified=True;r.groups=[{'groupId':group}]
            r.apply({'kind':'message','message':msg(-1)},now);assert digest(-1) not in p.normal and p.accepted==0
            assert len(json.loads((root/'state/feed.json').read_text())['messages'])==30
            p.db.close()
    return dict(passed=True,checks=['latest30','idle','restart','independentPin','staleIncomingRejected'])

if __name__=='__main__':print(json.dumps(run()))
