"""Authenticated, bounded single-writer publisher. No Feishu credentials or body logs."""
import argparse, base64, gzip, hashlib, json, os, re, sqlite3, subprocess, tempfile, time, sys
if __name__=="__main__":sys.modules.setdefault("server",sys.modules[__name__])
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from desktop_cards import read_cards
from state_delta import state_request, conditional_state

ROUTE='/radar/api/robot-push/publish'
CONFIG_ROUTE='/radar/api/robot-push/configure'
CONTROL_ROUTE='/radar/api/robot-push/control'
MAX_BODY=512*1024
HEX=re.compile(r'^[0-9a-f]{64}$')

class Rejected(Exception):
    def __init__(self,code,reason): self.code,self.reason=code,reason

def canonical(stamp,nonce,body,route=ROUTE):
    return f'robot-push-v1\nPOST\n{route}\n{stamp}\n{nonce}\n{hashlib.sha256(body).hexdigest()}'.encode()

def utc(value):
    try:
        stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
        if stamp.tzinfo is None: raise ValueError()
        return stamp.timestamp()
    except (ValueError,TypeError,AttributeError): raise Rejected(400,'invalid_time')

def iso(value): return datetime.fromtimestamp(value,timezone.utc).isoformat().replace('+00:00','Z')

def safe_url(value):
    if not isinstance(value,str) or len(value)>4096 or any(ord(c)<=32 for c in value): return False
    try:
        u=urlsplit(value)
        return u.scheme in ('http','https') and bool(u.hostname) and u.username is None and u.password is None
    except ValueError: return False

def message(raw,allowed,now):
    keys={'id','groupId','senderType','sentAt','title','body','actions'}
    if not isinstance(raw,dict) or not keys.issubset(raw) or set(raw)-keys-{'headerTone'}: raise Rejected(400,'message_schema')
    if 'headerTone' in raw and raw['headerTone'] not in ('blue','red','green','orange','purple','indigo','turquoise','yellow','grey'): raise Rejected(400,'header_tone')
    if raw['senderType']!='bot' or raw['groupId'] not in allowed: raise Rejected(403,'source_not_allowed')
    if not isinstance(raw['id'],str) or not HEX.fullmatch(raw['id']): raise Rejected(400,'message_id')
    if not isinstance(raw['body'],str) or len(raw['body'])>16000 or not isinstance(raw['title'],str) or len(raw['title'])>1024: raise Rejected(400,'text_limit')
    if utc(raw['sentAt'])>now+60: raise Rejected(400,'future_message')
    if not isinstance(raw['actions'],list) or len(raw['actions'])>8: raise Rejected(400,'actions_limit')
    for action in raw['actions']:
        if not isinstance(action,dict) or set(action)!={'label','url'} or not isinstance(action['label'],str) or len(action['label'])>128 or not safe_url(action['url']): raise Rejected(400,'unsafe_action')
    return raw

class Publisher:
    def __init__(self,directory,public_key):
        self.directory=Path(directory); self.directory.mkdir(parents=True,exist_ok=True)
        self.public_key=Path(public_key)
        der=subprocess.run(['openssl','pkey','-pubin','-in',str(public_key),'-outform','DER'],capture_output=True,timeout=3,check=True).stdout
        self.key_id=hashlib.sha256(der).hexdigest()[:16]
        self.db=sqlite3.connect(self.directory/'metadata.sqlite')
        self.db.execute('CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY, accepted REAL NOT NULL)')
        self.db.commit()
        self.normal={};self.pin=None;self.pin_group='';self.accepted=0;self.duplicates=0;self.rejected=0;self.last_source=0
        path=self.directory/'feed.json'
        if path.exists():
            old=json.loads(path.read_text(encoding="utf-8"))
            self.normal={m['id']:m for m in old.get('messages',[])[:30]}
            self.pin=old.get('pinned');self.pin_group=old.get('pinnedGroupId','')
        self.write(False,time.time())

    def write(self,connected,now):
        # Retain the last 30 accepted rows across idle periods and page reloads.
        # Incoming-message freshness checks remain in the receiver/accept path.
        ordered=sorted(self.normal.values(),key=lambda m:utc(m['sentAt']),reverse=True)[:30]
        data={'sourceConnected':connected,'updatedAt':iso(now),'messages':ordered,'pinned':self.pin,'pinnedGroupId':self.pin_group}
        encoded=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
        while len(encoded)>2*1024*1024 and ordered:
            ordered.pop();encoded=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
        self.normal={m['id']:m for m in ordered}
        temporary=self.directory/'feed.tmp';temporary.write_bytes(encoded);temporary.chmod(0o640);os.replace(temporary,self.directory/'feed.json')

    def authenticate(self,headers,body,now,route=ROUTE):
        if len(body)>MAX_BODY: raise Rejected(413,'request_limit')
        stamp=headers.get('X-Publish-Time','');nonce=headers.get('X-Publish-Nonce','')
        requested_key=headers.get('X-Publish-Key','')
        verify_key=self.public_key
        reader=requested_key!=self.key_id
        if reader:
            if not re.fullmatch(r'[0-9a-f]{16}',requested_key) or route!=CONTROL_ROUTE:
                raise Rejected(401,'unknown_key')
            try: read_only=state_request(json.loads(body))
            except (ValueError,UnicodeError): read_only=False
            if not read_only: raise Rejected(403,'reader_state_only')
            verify_key=self.public_key.parent/('desktop-reader-'+requested_key+'.pem')
            if not verify_key.is_file(): raise Rejected(401,'unknown_key')
        if not re.fullmatch(r'[0-9]{10,11}',stamp) or abs(now-int(stamp))>60 or not re.fullmatch(r'[0-9a-f]{32}',nonce): raise Rejected(401,'expired_or_invalid')
        signed_nonce=nonce
        if reader: nonce=requested_key+':'+nonce
        self.db.execute('DELETE FROM nonces WHERE accepted<?',(now-125,));self.db.commit()
        if self.db.execute('SELECT 1 FROM nonces WHERE nonce=?',(nonce,)).fetchone(): raise Rejected(409,'replay')
        if reader:
            rate=self.db.execute('SELECT count(*) FROM nonces WHERE accepted>? AND nonce LIKE ?',(now-60,requested_key+':%')).fetchone()[0]
        else:
            rate=self.db.execute("SELECT count(*) FROM nonces WHERE accepted>? AND nonce NOT LIKE '%:%'",(now-60,)).fetchone()[0]
        if rate>=30: raise Rejected(429,'rate_limit')
        try: signature=base64.b64decode(headers.get('X-Publish-Signature',''),validate=True)
        except (ValueError,TypeError): raise Rejected(401,'invalid_signature')
        if not 64<=len(signature)<=80: raise Rejected(401,'invalid_signature')
        with tempfile.TemporaryDirectory(prefix='robot-verify-') as temporary:
            sig=Path(temporary)/'signature.der';sig.write_bytes(signature)
            result=subprocess.run(['openssl','dgst','-sha256','-verify',str(verify_key),'-signature',str(sig)],input=canonical(stamp,signed_nonce,body,route),capture_output=True,timeout=3)
        if result.returncode: raise Rejected(401,'invalid_signature')
        return nonce

    def accept(self,headers,body,now=None):
        now=time.time() if now is None else now
        nonce=self.authenticate(headers,body,now)
        try: payload=json.loads(body)
        except (ValueError,UnicodeError): raise Rejected(400,'invalid_json')
        expected={'sourceConnected','allowedGroups','pinnedGroupId','normalIds','messages','pinned'}
        if not isinstance(payload,dict) or set(payload)!=expected or type(payload['sourceConnected']) is not bool: raise Rejected(400,'snapshot_schema')
        allowed=payload['allowedGroups'];normal_ids=payload['normalIds'];pin_group=payload['pinnedGroupId']
        if not isinstance(allowed,list) or len(allowed)>2000 or any(not isinstance(v,str) or not HEX.fullmatch(v) for v in allowed): raise Rejected(400,'groups_schema')
        allowed=set(allowed)
        if not isinstance(normal_ids,list) or len(normal_ids)>100 or any(not isinstance(v,str) or not HEX.fullmatch(v) for v in normal_ids) or len(set(normal_ids))!=len(normal_ids): raise Rejected(400,'ids_schema')
        if not isinstance(pin_group,str) or pin_group and pin_group not in allowed: raise Rejected(403,'pin_source')
        if not isinstance(payload['messages'],list) or len(payload['messages'])>8: raise Rejected(400,'batch_limit')
        incoming=[message(m,allowed,now) for m in payload['messages']]
        if any(m['id'] not in normal_ids or m['groupId']==pin_group for m in incoming): raise Rejected(400,'message_membership')
        new_pin=message(payload['pinned'],allowed,now) if payload['pinned'] is not None else None
        if new_pin is not None and new_pin['groupId']!=pin_group: raise Rejected(400,'pin_mismatch')
        self.db.execute('INSERT INTO nonces VALUES (?,?)',(nonce,now));self.db.commit()
        self.normal={k:m for k,m in self.normal.items() if k in normal_ids and m['groupId'] in allowed and m['groupId']!=pin_group}
        added=0
        for m in incoming:
            if now-utc(m['sentAt'])>=1800: continue
            if m['id'] in self.normal:self.duplicates+=1;continue
            self.normal[m['id']]=m;added+=1
        if pin_group!=self.pin_group or not pin_group:self.pin=None
        self.pin_group=pin_group
        if new_pin is not None and (self.pin is None or utc(new_pin['sentAt'])>=utc(self.pin['sentAt'])):self.pin=new_pin
        self.accepted+=added;self.last_source=now if payload['sourceConnected'] else 0
        self.write(payload['sourceConnected'],now)
        return {'accepted':added,'normalCount':len(self.normal),'pinned':self.pin is not None,'ackIds':list(self.normal),'pinAck':self.pin['id'] if self.pin else None}

class Handler(BaseHTTPRequestHandler):
    server_version='RobotPush/1'
    def log_message(self,*args): pass
    def setup(self):
        super().setup();self.connection.settimeout(6)
    def respond(self,status,value):
        body=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
        compress=len(body)>1024 and any(token.strip().lower()=='gzip' for token in self.headers.get('Accept-Encoding','').split(','))
        if compress: body=gzip.compress(body,compresslevel=3)
        self.send_response(status);self.send_header('Content-Type','application/json')
        if compress: self.send_header('Content-Encoding','gzip')
        self.send_header('Vary','Accept-Encoding');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path!='/health':self.respond(404,{'error':'not_found'});return
        p=self.server.publisher;self.respond(200,{'ready':True,'accepted':p.accepted,'duplicates':p.duplicates,'rejected':p.rejected,'normalCount':len(p.normal),'pinned':p.pin is not None,'lastSourceAge':round(time.time()-p.last_source,1) if p.last_source else None})
    def do_POST(self):
        if self.path not in (ROUTE,CONFIG_ROUTE,CONTROL_ROUTE):self.respond(404,{'error':'not_found'});return
        try:
            if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type')!='application/json':raise Rejected(400,'request_headers')
            length=int(self.headers.get('Content-Length','-1'))
            if not 1<=length<=(8192 if self.path!=ROUTE else MAX_BODY):raise Rejected(413,'request_limit')
            body=self.rfile.read(length)
            if len(body)!=length:raise Rejected(400,'incomplete')
            receiver=getattr(self.server,'receiver',None)
            if self.path==CONTROL_ROUTE:
                if receiver is None:raise Rejected(409,'cloud_not_active')
                now=time.time();publisher=self.server.publisher
                nonce=publisher.authenticate(self.headers,body,now,CONTROL_ROUTE)
                publisher.db.execute('INSERT INTO nonces VALUES (?,?)',(nonce,now));publisher.db.commit()
                control=json.loads(body)
                if state_request(control):
                    result=receiver.state()
                    result['opportunities']=read_cards(publisher.directory)
                    result=conditional_state(result,control.get('known'))
                    if control.get('desktopRules') == 1:
                        try:
                            from urllib.request import urlopen
                            with urlopen('http://127.0.0.1:18885/internal/desktop-state',timeout=8) as policy:
                                result['desktopRules']=json.loads(policy.read(1024*1024))
                        except Exception:result['desktopRulesUnavailable']=True
                elif isinstance(control,dict) and set(control)=={'action','pinnedGroupId'} and control['action']=='pin':result=receiver.select_pin(control['pinnedGroupId'])
                else:raise Rejected(400,'invalid_control')
            elif self.path==CONFIG_ROUTE:
                if receiver is not None:raise Rejected(409,'stop_cloud_before_reconfigure')
                config=getattr(self.server,'configuration',None)
                if config is None:raise Rejected(503,'configuration_not_enabled')
                now=time.time();publisher=self.server.publisher
                nonce=publisher.authenticate(self.headers,body,now,CONFIG_ROUTE)
                publisher.db.execute('INSERT INTO nonces VALUES (?,?)',(nonce,now));publisher.db.commit()
                from cloud_config import ConfigurationError
                try:result=config.submit(json.loads(body))
                except ConfigurationError as error:raise Rejected(400,str(error))
            else:
                if receiver is not None:raise Rejected(409,'cloud_is_authoritative')
                result=self.server.publisher.accept(self.headers,body)
            self.respond(200,result)
        except Rejected as error:self.server.publisher.rejected+=1;self.respond(error.code,{'error':error.reason})
        except (ValueError,TypeError,TimeoutError):self.respond(400,{'error':'invalid_request'})
        except Exception:self.respond(503,{'error':'temporarily_unavailable'})

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',default='/var/lib/robot-push');p.add_argument('--public-key',default='/etc/robot-push/publisher-public.pem');p.add_argument('--port',type=int,default=18883);p.add_argument('--cloud-config-directory');p.add_argument('--expected-app-id-file');p.add_argument('--cloud-mode',action='store_true');p.add_argument('--node',default='/opt/robot-push/node/bin/node');p.add_argument('--cloud-entry',default='/opt/robot-push/cloud-bridge/cloud-main.mjs');args=p.parse_args()
    server=HTTPServer(('127.0.0.1',args.port),Handler);server.publisher=Publisher(args.directory,args.public_key)
    if args.cloud_config_directory and args.expected_app_id_file:
        from cloud_config import CloudConfiguration
        server.configuration=CloudConfiguration(args.cloud_config_directory,Path(args.expected_app_id_file).read_text().strip())
    if args.cloud_mode:
        if not args.cloud_config_directory:raise ValueError('cloud_configuration_required')
        from cloud_receiver import CloudReceiver
        import signal
        receiver=CloudReceiver(server.publisher,args.cloud_config_directory,args.node,args.cloud_entry)
        server.receiver=receiver;server.timeout=.5;running=True
        def stop(signum,frame):
            nonlocal running
            running=False
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        try:
            while running:
                receiver.tick();server.handle_request()
        finally:receiver.close();server.server_close()
    else:server.serve_forever(poll_interval=1)

if __name__=='__main__': main()
