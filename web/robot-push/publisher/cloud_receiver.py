"""One owned SDK subprocess, private pipes, one state writer; no payload logging."""
import json, queue, subprocess, threading, time
from pathlib import Path
from server import message, utc, Rejected

class CloudReceiver:
    def __init__(self,publisher,config_directory,node,entry):
        self.publisher=publisher;self.directory=Path(config_directory)
        self.node=node;self.entry=entry;self.process=None;self.reader=None
        self.events=queue.Queue(maxsize=128);self.groups=[];self.verified=False;self.connected=False
        self.retry_at=0;self.retry_delay=5;self.last_write=0;self.stopping=False;self.overflow=False
        self.publisher.db.execute('CREATE TABLE IF NOT EXISTS cloud_seen (id TEXT PRIMARY KEY, accepted REAL NOT NULL)')
        self.publisher.db.commit()

    def start(self):
        if self.process is not None or self.stopping:return
        # Credential remains internal to these two local service processes.
        data=json.loads((self.directory/'application.json').read_text())
        if data.get('phase') not in ('prepared','active'):raise ValueError('configuration_not_prepared')
        self.publisher.pin_group=data.get('pinnedGroupId','')
        if self.publisher.pin and self.publisher.pin['groupId']!=self.publisher.pin_group:self.publisher.pin=None
        self.process=subprocess.Popen([self.node,self.entry],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',bufsize=1)
        self.process.stdin.write(json.dumps({'appId':data['appId'],'appSecret':data['appSecret']})+'\n');self.process.stdin.flush();data.clear()
        self.overflow=False
        process=self.process
        def read():
            try:
                while True:
                    line=process.stdout.readline(600001)
                    if not line:break
                    if len(line)>600000:raise ValueError()
                    self.events.put_nowait(json.loads(line))
            except Exception:
                self.overflow=True
            finally:
                try:self.events.put_nowait({'kind':'closed'})
                except queue.Full:self.overflow=True
        self.reader=threading.Thread(target=read,daemon=True);self.reader.start()

    def apply(self,event,now):
        kind=event.get('kind');p=self.publisher
        if kind=='membership':
            groups=event.get('groups',[])
            if not isinstance(groups,list) or len(groups)>2000:raise ValueError()
            self.verified=event.get('verified') is True
            self.groups=groups if self.verified else []
            allowed={g['groupId'] for g in self.groups}
            p.normal={k:m for k,m in p.normal.items() if m['groupId'] in allowed}
            if p.pin and p.pin['groupId'] not in allowed:p.pin=None
        elif kind=='status':self.connected=event.get('connected') is True
        elif kind=='message':
            if not self.connected or not self.verified:return
            allowed={g['groupId'] for g in self.groups};m=message(event.get('message'),allowed,now)
            if now-utc(m['sentAt'])>=1800:return
            p.db.execute('DELETE FROM cloud_seen WHERE accepted<?',(now-1800,))
            if p.db.execute('SELECT 1 FROM cloud_seen WHERE id=?',(m['id'],)).fetchone():p.duplicates+=1;return
            if p.db.execute('SELECT count(*) FROM cloud_seen').fetchone()[0]>=10000:raise ValueError('bounded_dedup_limit')
            p.db.execute('INSERT INTO cloud_seen VALUES (?,?)',(m['id'],now));p.db.commit()
            if m['groupId']==p.pin_group:
                if p.pin is None or utc(m['sentAt'])>=utc(p.pin['sentAt']):p.pin=m
            else:p.normal[m['id']]=m
            p.accepted+=1
        elif kind=='closed':raise ValueError('bridge_closed')
        else:return
        p.last_source=now if self.connected and self.verified else 0
        p.write(self.connected and self.verified,now);self.last_write=now

    def stop_child(self):
        process=self.process;self.process=None
        if process:
            try:
                if process.stdin:process.stdin.close()
                process.wait(timeout=3)
            except (OSError,subprocess.TimeoutExpired):
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            if process.stdout:process.stdout.close()
        if self.reader:self.reader.join(timeout=1);self.reader=None
        while True:
            try:self.events.get_nowait()
            except queue.Empty:break

    def tick(self,now=None):
        now=time.time() if now is None else now
        if self.stopping:return
        try:
            if self.process is None:
                if now<self.retry_at:return
                self.start()
            if self.overflow:raise ValueError('bridge_queue_limit')
            for _ in range(128):
                try:event=self.events.get_nowait()
                except queue.Empty:break
                self.apply(event,now)
            if self.process.poll() is not None:raise ValueError('bridge_exit')
            if self.connected and self.verified:
                self.retry_delay=5
                if now-self.last_write>=20:self.publisher.write(True,now);self.last_write=now
        except Exception:
            self.stop_child();self.connected=False;self.verified=False;self.groups=[]
            self.publisher.write(False,now);self.retry_at=now+self.retry_delay;self.retry_delay=min(60,self.retry_delay*2)

    def state(self):
        p=self.publisher
        return {'cloudMode':True,'sourceConnected':self.connected and self.verified,'groups':self.groups,'messages':list(p.normal.values()),'pinned':p.pin,'pinnedGroupId':p.pin_group}

    def select_pin(self,group):
        allowed={g['groupId'] for g in self.groups}
        if not self.verified or group and group not in allowed:raise Rejected(403,'pin_source')
        data=json.loads((self.directory/'application.json').read_text());data['pinnedGroupId']=group
        temporary=self.directory/'application.pending'
        import os
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as output:json.dump(data,output);output.flush();os.fsync(output.fileno())
        os.replace(temporary,self.directory/'application.json');data.clear()
        p=self.publisher;p.pin_group=group
        candidates=[m for m in [*p.normal.values(),p.pin] if m and m['groupId']==group]
        p.pin=max(candidates,key=lambda m:utc(m['sentAt'])) if candidates else None
        p.normal={k:m for k,m in p.normal.items() if m['groupId']!=group};p.write(self.connected and self.verified,time.time())
        return {'saved':True,'pinnedGroupId':group}

    def close(self):
        self.stopping=True;self.stop_child();self.connected=False;self.publisher.write(False,time.time())
