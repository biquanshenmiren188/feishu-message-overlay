"""Incremental settings/backend release; never restart the desktop or publisher."""
import fcntl,hashlib,json,os,shutil,subprocess,sys,time,urllib.request
from pathlib import Path
stage=Path(sys.argv[1]);sha=sys.argv[2]
current=Path('/opt/funding-radar-web/current');backend=Path('/opt/radar-webpush-test/desktop_rules.py');state=Path('/var/lib/radar-webpush-test')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def get(path):
    with urllib.request.urlopen('http://127.0.0.1:18885'+path,timeout=10) as response:return json.load(response)
def pid():return subprocess.check_output(['systemctl','show','robot-push','--property=MainPID'],text=True)
def mobile():
    out={}
    for p in [state/'state.json',*sorted((state/'profiles').glob('*/state.json'))]:
        d=json.loads(p.read_text());out[str(p)]={k:d.get(k) for k in ('token','subscription','subscriptions')}|{'settings':d.get('live',{}).get('settings'),'revision':d.get('live',{}).get('revision')}
    return out
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    old=current.resolve()
    assert old.name=='20261023-message-nav-1792724745','Inspect changed production baseline'
    assert digest(backend)=='f64bfe9ab5bd39d1d46b098a16d3e042e13e9950e0536f5d0216ba0f3fbe68b0','Backend baseline changed'
    release='20261023-split-rules-'+str(int(time.time()));new=old.parent/release
    backup=Path('/opt/funding-radar-web/backups')/release;backup.mkdir(mode=0o700)
    previous_mobile=mobile();publisher_pid=pid()
    excluded={'robot-push/settings/'+name for name in ('app.js','index.html','style.css')}|{'settings-preview-source.json'}
    preserved={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file() and str(p.relative_to(old)) not in excluded}
    shutil.copytree(old,new,symlinks=True)
    for name in ('app.js','index.html','style.css'):shutil.copyfile(stage/name,new/'robot-push/settings'/name)
    manifest={'source_sha':sha,'repository':'biquanshenmiren188/feishu-message-overlay','mode':'independent-mute-hide','assets':{name:digest(new/'robot-push/settings'/name) for name in ('app.js','index.html','style.css','rules.js')}}
    (new/'settings-preview-source.json').write_text(json.dumps(manifest,indent=2))
    assert all(digest(new/p)==h for p,h in preserved.items())
    shutil.copyfile(backend,backup/'desktop_rules.py')
    subprocess.run(['systemctl','stop','radar-webpush-test'],check=True)
    before=json.loads((state/'desktop-rules.json').read_text())
    shutil.copyfile(state/'desktop-rules.json',backup/'desktop-rules-private.json')
    (backup/'desktop-rules-private.json').chmod(0o600)
    try:
        temp=backend.with_suffix('.next');shutil.copyfile(stage/'desktop_rules.py',temp);temp.chmod(0o644);os.replace(temp,backend)
        subprocess.run(['systemctl','start','radar-webpush-test'],check=True)
        for attempt in range(40):
            try:get('/radar/push-test/api/health');break
            except Exception:
                if attempt==39:raise
                time.sleep(.25)
        decision=get('/internal/desktop-state');assert decision['revision']==before['revision']
        # The first signed request records migration without changing the version.
        import importlib.util
        sys.path.insert(0,str(backend.parent))
        from desktop_rules import DesktopRules
        migrated=DesktopRules(state).status()
        assert migrated['cards']==before['cards']
        assert migrated['desktop']['settings']==before['desktop']['settings']
        assert migrated['desktop']['rules'][before['desktop']['action']]==before['desktop']['settings']
        assert mobile()==previous_mobile and pid()==publisher_pid
        link=current.with_name('current.split-rules-next');link.symlink_to(new);os.replace(link,current)
        result={'source_sha':sha,'release':str(new),'previous':str(old),'backup':str(backup),'preservedFiles':len(preserved),'revision':decision['revision'],'existingRulesPreserved':True,'mobileBindingsPreserved':True,'publisherUnchanged':True,'desktopRestarted':False}
        (backup/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    except Exception:
        if current.resolve()==new:
            link=current.with_name('current.split-rules-rollback');link.symlink_to(old);os.replace(link,current)
        shutil.copyfile(backup/'desktop_rules.py',backend)
        subprocess.run(['systemctl','restart','radar-webpush-test'],check=True)
        # Never overwrite potentially newer user settings with the private backup.
        raise
