"""Isolated configuration contract; all credentials and keys here are synthetic."""
import json, os, tempfile, time, base64
from pathlib import Path
from unittest.mock import patch
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
import server
from contract_local import crypto_command
from cloud_config import CloudConfiguration, ConfigurationError

def run():
    checks=[]
    with tempfile.TemporaryDirectory() as root:
        root=Path(root)
        config=CloudConfiguration(root/'private','cli_fixture',lambda app,secret: secret=='synthetic-only-value')
        data={'appId':'cli_fixture','appSecret':'synthetic-only-value','pinnedGroupId':''}
        result=config.submit(data)
        assert result=={'configured':True,'appId':'cli_fixture','phase':'prepared','receiverStarted':False}
        assert 'appSecret' not in json.dumps(result)
        checks.append('prepared_only_safe_response')
        before=(root/'private/application.json').read_bytes()
        for change in ({'appId':'cli_other'},{'appSecret':'wrong-synthetic'},{'pinnedGroupId':'invalid'},{'extra':True}):
            try:config.submit(data|change);raise AssertionError('invalid input accepted')
            except ConfigurationError:pass
            assert (root/'private/application.json').read_bytes()==before
        checks.append('invalid_input_preserves_configuration')
        if os.name!='nt':
            assert (root/'private').stat().st_mode&0o777==0o700
            assert (root/'private/application.json').stat().st_mode&0o777==0o600
            checks.append('linux_private_permissions')
        key=ec.generate_private_key(ec.SECP256R1())
        public=root/'public.pem'
        public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        with patch.object(server.subprocess,'run',crypto_command):
            publisher=server.Publisher(root/'state',public)
            try:
                body=json.dumps(data).encode();now=time.time();stamp=str(int(now));nonce='3'*32
                signature=key.sign(server.canonical(stamp,nonce,body,server.CONFIG_ROUTE),ec.ECDSA(hashes.SHA256()))
                headers={'X-Publish-Key':publisher.key_id,'X-Publish-Time':stamp,'X-Publish-Nonce':nonce,'X-Publish-Signature':base64.b64encode(signature).decode()}
                assert publisher.authenticate(headers,body,now,server.CONFIG_ROUTE)==nonce
                try:publisher.authenticate(headers,body,now,server.ROUTE);raise AssertionError('cross-route signature accepted')
                except server.Rejected as error:assert error.code==401
                checks.append('signature_bound_to_configuration_route')
                assert json.loads((root/'state/feed.json').read_text())['sourceConnected'] is False
                checks.append('configuration_does_not_start_receiver')
            finally:publisher.db.close()
    return {'passed':True,'checks':checks,'syntheticOnly':True,'realCredentialUsed':False}

if __name__=='__main__':print(json.dumps(run()))
