"""Guarded incremental deployment. Stage contains an inspected baseline manifest.

Preserves unrelated assets and stored rules/devices. The only restarts are the
two Python services whose modules change. No live notification tests are sent.
"""
import fcntl, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from pathlib import Path
from urllib.request import urlopen

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def command(*args):return subprocess.check_output(args,text=True).strip()
def limits():return command('systemctl','show','radar-alarms','--property=CPUQuotaPerSecUSec','--value')
def switch(link,target):
    temp=link.with_name(link.name+'.runtime-next');temp.symlink_to(target);os.replace(temp,link)
def atomic(path,data,mode=0o644):
    temp=path.with_name(path.name+'.runtime-next');temp.write_bytes(data);temp.chmod(mode);os.replace(temp,path)
def health():
    for port,path in [(18885,'push-test/api'),(18886,'alarms-api')]:
        for attempt in range(30):
            try:
                with urlopen(f'http://127.0.0.1:{port}/radar/{path}/health',timeout=2) as r:data=json.load(r)
                assert data['ok'];break
            except Exception:
                if attempt==29:raise
                time.sleep(.5)

def main():
    stage=Path(sys.argv[1]);manifest=json.loads((stage/'manifest.json').read_text())
    safety=module('runtime_safety',stage/'scripts/deploy-bot-resource-budget.py')
    patcher=module('transfer_patch',stage/'scripts/patch-transfer-pause.py')
    web=Path('/opt/funding-radar-web');current=web/'current';alarms=Path('/opt/radar-alarms/current')
    push=Path('/opt/radar-webpush-test');fallback=push/'public/index.html'
    with open('/var/lib/funding-radar-storage/guard.lock','a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old=current.resolve();old_alarm=alarms.resolve()
        assert str(old)==manifest['web'] and str(old_alarm)==manifest['alarms']
        for name,digest in manifest['baseline'].items():assert sha(Path(name))==digest,name
        assert limits()=='350ms','Unexpected alarm CPU quota'
        state=safety.protected_state();robot=command('systemctl','show','robot-push','--property=MainPID','--value')
        label='20261116-runtime-load-'+str(time.time_ns());new=web/'releases'/label
        new_alarm=old_alarm.parent/label;backup=web/'backups'/label
        # Manifest is prepared from the exact files tested on this host.
        for name,digest in manifest['candidate'].items():assert sha(stage/name)==digest,name
        if '--apply' not in sys.argv:
            print(json.dumps(dict(preflight=True,protectedState=state)));return
        backup.mkdir(mode=0o700);(backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
        originals={n:(push/n).read_bytes() for n in ('live.py','signals.py')}
        old_fallback=fallback.read_bytes()
        for n,b in originals.items():(backup/n).write_bytes(b)
        (backup/'pwa.html').write_bytes(old_fallback)
        shutil.copytree(old,new,symlinks=True);shutil.copytree(old_alarm,new_alarm,symlinks=True)
        for n in ('market.py','sources.py'):shutil.copyfile(stage/'web/alarms'/n,new_alarm/n)
        # Copy the entire inspected module graph under a new immutable namespace.
        prefix='assets/duo-view-e82cf7d51669';new_prefix='assets/runtime-load-'+manifest['mainSource'][:12]
        shutil.copytree(old/prefix,new/new_prefix)
        for p in (new/new_prefix).rglob('*.js'):
            text=p.read_text()
            if p.name=='m-55976ee5ea57.js':text=patcher.patch(text)
            p.write_text(text.replace('/radar/'+prefix+'/', '/radar/'+new_prefix+'/'))
        home=(old/'index.html').read_text();assert prefix in home
        (new/'index.html').write_text(home.replace(prefix,new_prefix))
        pin='robot-push/pin-history.js';shutil.copyfile(stage/'web'/pin,new/pin)
        entry='performance-20261017/bot-entry-bc358114f0e5e30c.js'
        entry_new='performance-20261017/bot-entry-runtime-'+manifest['source'][:12]+'.js'
        old_url='/radar/robot-push/pin-history.js?v=20261112-history5'
        new_url='/radar/robot-push/pin-history.js?v='+manifest['source'][:12]
        text=(old/entry).read_text();assert text.count(old_url)==1
        (new/entry_new).write_text(text.replace(old_url,new_url))
        html=(old/'robot-push/index.html').read_bytes();assert html.count(entry.encode())==1 and old_fallback.count(entry.encode())==1
        (new/'robot-push/index.html').write_bytes(html.replace(entry.encode(),entry_new.encode()))
        new_fallback=old_fallback.replace(entry.encode(),entry_new.encode())
        changed={'index.html',pin,'robot-push/index.html'}
        before={str(p.relative_to(old)):sha(p) for p in old.rglob('*') if p.is_file() and not p.is_symlink() and p.name!='market-display-cache.json'}
        for n,h in before.items():
            if n not in changed:assert sha(new/n)==h,'Unrelated asset changed: '+n
        for p in old_alarm.rglob('*.py'):
            if p.name not in ('market.py','sources.py'):assert sha(new_alarm/p.relative_to(old_alarm))==sha(p)
        assert safety.protected_state()==state
        try:
            command('systemctl','set-property','radar-alarms','CPUQuota=100%')
            switch(alarms,new_alarm)
            command('systemctl','restart','radar-alarms')
            for n in originals:atomic(push/n,(stage/'web/push-test'/n).read_bytes())
            command('systemctl','restart','radar-webpush-test')
            health()
            atomic(fallback,new_fallback);switch(current,new)
            assert safety.protected_state()==state,'Protected configuration changed'
            assert command('systemctl','show','robot-push','--property=MainPID','--value')==robot
            assert limits()=='1s'
            report=dict(source=manifest['source'],mainSource=manifest['mainSource'],release=str(new),alarmRelease=str(new_alarm),previous=str(old),previousAlarm=str(old_alarm),backup=str(backup),protectedState=state,bindingsAndRulesPreserved=True,unrelatedAssetsPreserved=len(before)-len(changed),alarmQuota='100%',robotPidUnchanged=True)
            (backup/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
        except BaseException:
            if current.resolve()==new:switch(current,old)
            if fallback.read_bytes()==new_fallback:atomic(fallback,old_fallback)
            if alarms.resolve()==new_alarm:switch(alarms,old_alarm);command('systemctl','restart','radar-alarms')
            for n,b in originals.items():atomic(push/n,b)
            command('systemctl','restart','radar-webpush-test')
            if limits()=='1s':command('systemctl','set-property','radar-alarms','CPUQuota=35%')
            raise

if __name__=='__main__':main()
