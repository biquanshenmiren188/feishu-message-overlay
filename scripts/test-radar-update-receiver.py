import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

spec=importlib.util.spec_from_file_location('receiver',Path(__file__).with_name('radar-update-receiver.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'public';self.key=Path(self.temp.name)/'key.pem'
        subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048','-out',str(self.key)],check=True,capture_output=True)
    def tearDown(self): self.temp.cleanup()
    def packet(self,tag='v2026.11.05.1',content=b'synthetic exe',extra=None):
        blob=io.BytesIO()
        with zipfile.ZipFile(blob,'w') as z:
            z.writestr('FeishuMessageOverlay.exe',content)
            z.writestr('update-manifest.json',json.dumps({'Protocol':1,'Version':tag,'Files':{'FeishuMessageOverlay.exe':hashlib.sha256(content).hexdigest()}}))
            if extra:z.writestr(extra,b'bad')
        data=blob.getvalue();meta={'Version':tag,'Size':len(data),'Sha256':hashlib.sha256(data).hexdigest(),'SourceCommit':'a'*40}
        return json.dumps(meta).encode()+b'\n'+data
    def receive(self,data):return r.receive(io.BytesIO(data),self.root,self.key)
    def test_success_and_signature(self):
        self.receive(self.packet())
        envelope=json.loads((self.root/'latest.json').read_bytes());payload=base64.b64decode(envelope['payload'])
        pub=Path(self.temp.name)/'pub.pem';sig=Path(self.temp.name)/'sig';sig.write_bytes(base64.b64decode(envelope['signature']))
        subprocess.run(['openssl','pkey','-in',str(self.key),'-pubout','-out',str(pub)],check=True,capture_output=True)
        subprocess.run(['openssl','dgst','-sha256','-verify',str(pub),'-signature',str(sig),'-sigopt','rsa_padding_mode:pss','-sigopt','rsa_pss_saltlen:32'],input=payload,check=True,capture_output=True)
        self.assertEqual(json.loads(payload)['Version'],'v2026.11.05.1')
    def test_idempotent_retry(self):
        packet=self.packet();self.receive(packet);before=(self.root/'latest.json').read_bytes();self.receive(packet)
        self.assertEqual(before,(self.root/'latest.json').read_bytes())
    def test_failed_upload_preserves_latest(self):
        self.receive(self.packet());before=(self.root/'latest.json').read_bytes()
        packet=self.packet('v2026.11.05.2')
        for data in (packet[:-5],packet+b'extra',packet[:-1]+b'x'):
            with self.assertRaises(Exception):self.receive(data)
            self.assertEqual(before,(self.root/'latest.json').read_bytes())
    def test_immutable_and_downgrade(self):
        self.receive(self.packet())
        for data in (self.packet(content=b'changed'),self.packet('v2026.11.04.1')):
            with self.assertRaises(ValueError):self.receive(data)
    def test_zip_path_and_unlisted_config(self):
        for name in ('../escape','storage-location.json','secret.dpapi','extra.txt'):
            with self.assertRaises(ValueError):self.receive(self.packet(extra=name))
            self.assertFalse((self.root/'latest.json').exists())
    def test_header_limits(self):
        for data in (b'x'*4097,b'{}\n',b'{}'):
            with self.assertRaises(Exception):self.receive(data)
    def test_new_release_keeps_previous(self):
        self.receive(self.packet());before=(self.root/'latest.json').read_bytes();self.receive(self.packet('v2026.11.05.2'))
        self.assertEqual(before,(self.root/'previous.json').read_bytes())
        self.assertTrue((self.root/'v2026.11.05.1'/'release.json').exists())

if __name__=='__main__':unittest.main()
