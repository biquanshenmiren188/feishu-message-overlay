"""Called only AFTER signature/replay verification on the control route."""
import json,re
from urllib.request import Request,urlopen
from urllib.error import HTTPError

def valid_control(control):
    if not isinstance(control,dict) or set(control) not in ({'action','request'}, {'action','request','pushCode'}) or control['action']!='coin-rules' or not isinstance(control['request'],dict):return False
    if 'pushCode' in control and (not isinstance(control['pushCode'],str) or not re.fullmatch('[0-9]{8}',control['pushCode'])):return False
    data=control['request']
    return set(data)=={'op'} and data['op']=='state' or set(data)=={'op','request'} and data['op'] in ('block','edit') and isinstance(data['request'],dict)

def coin_control(control, client=None):
    if not valid_control(control):raise ValueError('invalid_coin_control')
    data=control['request']
    if 'pushCode' in control:
        if not isinstance(client,str) or not re.fullmatch('[a-f0-9]{16}',client):raise ValueError('invalid_desktop_identity')
        data=dict(pushCode=control['pushCode'],client=client,request=data)
    raw=json.dumps(data).encode()
    if len(raw)>8192:raise ValueError('coin_control_too_large')
    req=Request('http://127.0.0.1:18885/internal/coin-rules',data=raw,headers={'Content-Type':'application/json'},method='POST')
    try:
        with urlopen(req,timeout=10) as response:return {'ok':True,'data':json.loads(response.read(1024*1024))}
    except HTTPError as e:
        try:reason=json.loads(e.read(8192)).get('error','规则保存失败')
        except (ValueError,AttributeError):reason='规则保存失败'
        finally:e.close()
        return {'ok':False,'error':str(reason)[:160]}
