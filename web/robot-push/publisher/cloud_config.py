"""User-submitted service credential configuration. Never logs request data."""
import json, os, re, urllib.request
from pathlib import Path

class ConfigurationError(Exception):
    pass

def verify_application(app_id, secret):
    request = urllib.request.Request(
        'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
        data=json.dumps({'app_id':app_id,'app_secret':secret}).encode(),
        headers={'Content-Type':'application/json'}, method='POST')
    try:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        with urllib.request.build_opener(NoRedirect).open(request, timeout=8) as response:
            data=json.loads(response.read(32769))
        return data.get('code')==0 and isinstance(data.get('tenant_access_token'),str) and len(data['tenant_access_token'])>0
    except Exception:
        return False

class CloudConfiguration:
    def __init__(self, directory, expected_app_id, verifier=verify_application):
        self.directory=Path(directory)
        self.expected_app_id=expected_app_id
        self.verifier=verifier

    @property
    def configured(self):
        return (self.directory/'application.json').is_file()

    def submit(self, data):
        if not isinstance(data,dict) or set(data)!={'appId','appSecret','pinnedGroupId'}:
            raise ConfigurationError('invalid_configuration')
        app_id=data['appId'];secret=data['appSecret'];pin=data['pinnedGroupId']
        if not isinstance(app_id,str) or app_id!=self.expected_app_id or not re.fullmatch(r'cli_[a-zA-Z0-9]+',app_id):
            raise ConfigurationError('application_mismatch')
        if not isinstance(secret,str) or not 8<=len(secret)<=256 or any(ord(c)<33 for c in secret):
            raise ConfigurationError('invalid_secret_format')
        if not isinstance(pin,str) or pin and not re.fullmatch(r'[0-9a-f]{64}',pin):
            raise ConfigurationError('invalid_pin_selection')
        if not self.verifier(app_id,secret):
            raise ConfigurationError('application_verification_failed')
        self.directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.directory.chmod(0o700)
        target=self.directory/'application.json';temporary=self.directory/'application.pending'
        # Only this account/root can read the server credential. No token is persisted.
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        try:
            os.chmod(temporary,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as output:
                json.dump({'appId':app_id,'appSecret':secret,'pinnedGroupId':pin,'phase':'prepared'},output,separators=(',',':'))
                output.flush();os.fsync(output.fileno())
            os.replace(temporary,target)
            if os.name!='nt':
                directory_fd=os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(directory_fd)
                finally:os.close(directory_fd)
        finally:
            if temporary.exists():temporary.unlink()
        return {'configured':True,'appId':app_id,'phase':'prepared','receiverStarted':False}
