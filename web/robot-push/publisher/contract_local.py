"""Offline cross-language crypto verification; production still uses OpenSSL CLI."""
import json, subprocess, sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature
import server
import contract_test

def crypto_command(args, **kwargs):
    if args[:3] == ['openssl', 'pkey', '-pubin']:
        public = serialization.load_pem_public_key(Path(args[args.index('-in')+1]).read_bytes())
        data = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        return subprocess.CompletedProcess(args, 0, stdout=data, stderr=b'')
    if args[:3] == ['openssl', 'dgst', '-sha256']:
        public = serialization.load_pem_public_key(Path(args[args.index('-verify')+1]).read_bytes())
        signature = Path(args[args.index('-signature')+1]).read_bytes()
        try:
            public.verify(signature, kwargs['input'], ec.ECDSA(hashes.SHA256()))
            code = 0
        except InvalidSignature:
            code = 1
        return subprocess.CompletedProcess(args, code, stdout=b'', stderr=b'')
    raise AssertionError('Unexpected external command in isolated crypto test')

if __name__ == '__main__':
    server.subprocess.run = crypto_command
    result = contract_test.run(sys.argv[1], sys.argv[2])
    result['verificationBackend'] = 'Python cryptography; .NET ECDSA DER signatures'
    result['serverOpenSslCliTested'] = False
    print(json.dumps(result))
