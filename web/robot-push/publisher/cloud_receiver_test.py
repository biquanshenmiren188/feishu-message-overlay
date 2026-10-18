"""Synthetic lifecycle checks; no SDK process, real credential, or network."""
import hashlib,json,tempfile,time
from pathlib import Path
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import server
from contract_local import crypto_command
from cloud_receiver import CloudReceiver

def run():
    checks=[];now=time.time();digest=lambda value:hashlib.sha256(value.encode()).hexdigest()
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);key=ec.generate_private_key(ec.SECP256R1());public=root/'public.pem'
        public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        private=root/'private';private.mkdir();(private/'application.json').write_text(json.dumps({'appId':'cli_fixture','appSecret':'synthetic-not-real','pinnedGroupId':'','phase':'prepared'}))
        with patch.object(server.subprocess,'run',crypto_command):
            p=server.Publisher(root/'state',public);r=CloudReceiver(p,private,'not-started','not-started')
            group=digest('oc_fixture');other=digest('oc_other')
            def msg(number,source=group):return {'id':digest(str(number)),'groupId':source,'senderType':'bot','sentAt':server.iso(now),'title':'Synthetic','body':'Fixture only','actions':[]}
            r.apply({'kind':'membership','verified':True,'groups':[{'id':'oc_fixture','groupId':group,'name':'Synthetic'},{'id':'oc_other','groupId':other,'name':'Other'}]},now)
            r.apply({'kind':'status','connected':True},now)
            r.apply({'kind':'message','message':msg(1)},now);r.apply({'kind':'message','message':msg(1)},now)
            assert len(p.normal)==1 and p.accepted==1 and p.duplicates==1;checks.append('persistent_dedup')
            r.select_pin(group);assert p.pin['id']==digest('1') and not p.normal
            r.apply({'kind':'message','message':msg(2)},now);assert p.pin['id']==digest('2') and not p.normal
            r.apply({'kind':'message','message':msg(3,other)},now);assert len(p.normal)==1;checks.append('independent_pin_replace')
            p.write(True,now+1801);assert len(p.normal)==1 and p.pin['id']==digest('2');checks.append('idle_history_preserves_pin')
            r.apply({'kind':'membership','verified':False,'groups':[]},now);assert p.pin is None and not r.state()['sourceConnected'];checks.append('membership_failure_closes_scope')
            r.apply({'kind':'message','message':msg(4)},now);assert p.accepted==3;checks.append('unverified_event_ignored')
            assert r.process is None;checks.append('test_never_starts_sdk')
            p.db.close()
    return {'passed':True,'checks':checks,'syntheticOnly':True}

if __name__=='__main__':print(json.dumps(run()))
