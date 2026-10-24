"""Run on the radar server: verified incremental release, never restore user data."""
import fcntl, hashlib, json, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

stage=Path(sys.argv[1]); sha=sys.argv[2]
plan=json.loads((stage/'deployment.json').read_text())
current=Path('/opt/funding-radar-web/current')
push=Path('/opt/radar-webpush-test'); publisher=Path('/opt/robot-push')
state=Path('/var/lib/radar-webpush-test'); fallback=push/'public/index.html'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def call(args):return subprocess.check_output(args,text=True).strip()
def settings():
    result={}
    for path in [state/'state.json',*sorted((state/'profiles').glob('*/state.json'))]:
        data=json.loads(path.read_text());live=data.get('live',{})
        result[str(path)]={k:data.get(k) for k in ('token','subscription','subscriptions')}|{'settings':live.get('settings'),'revision':live.get('revision')}
    for path in [state/'desktop-rules.json',*sorted((state/'profiles').glob('*/desktop-rules.json'))]:
        if path.exists():
            data=json.loads(path.read_text());result[str(path)]={k:data.get(k) for k in ('desktop','cards','revision','coinOperations')}
    return result
def health(port,path,key):
    for attempt in range(40):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=3) as response:assert json.load(response)[key]
            return
        except Exception:
            if attempt==39:raise
            time.sleep(.25)
def binding_probe():
    # Read-only: the original profile is already present. Never return its code.
    code=json.loads(Path('/etc/radar-webpush-test/config.json').read_text())['pairCode']
    for value,bound in [('',False),(code,True)]:
        req=urllib.request.Request('http://127.0.0.1:18885/internal/desktop-binding',data=json.dumps({'pushCode':value,'client':'0'*16}).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=12) as response:data=json.load(response)
        assert data['pushBinding']==dict(protocol=1,bound=bound,canManage=bound)
        if not bound:assert data['desktopRules']==dict(revision=0,messages={},cards={},desktopEnabled=True,cardsEnabled=True)

with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    old=current.resolve();assert str(old)==plan['baseline']['current'],'Production release changed'
    for directory,names in plan['backend'].items():
        for name in names:
            expected=plan['baseline']['files'][directory].get(name)
            destination=Path(directory)/name
            assert (digest(destination)==expected if expected else not destination.exists()),'Production source changed: '+name
    for name,expected in plan['stageHashes'].items():assert digest(stage/name)==expected,'Staging hash mismatch'
    assets=plan['assets']
    for name,expected in plan['assetBaseline'].items():assert digest(old/name)==expected,'Production asset changed'
    oldfallback=fallback.read_bytes();oldindex=(old/'robot-push/index.html').read_text()
    import re
    refs=re.findall(r'/radar/(performance-[^"\s]+/bot-cards-[a-f0-9]+\.js)',oldindex)
    assert len(refs)==1,'Unexpected BOT bundle'
    source=old/refs[0];text=source.read_text()
    newtext,count=re.subn(r'card-policy\.js\?v=[A-Za-z0-9-]+','card-policy.js?v=20261024-binding1',text)
    assert count==1 and newtext!=text,'Unexpected policy import'
    raw=newtext.encode();bundle=str(source.parent.relative_to(old))+'/bot-cards-'+hashlib.sha256(raw).hexdigest()[:12]+'.js'
    oldref='/radar/'+refs[0];newref='/radar/'+bundle
    assert oldindex.count(oldref)==oldfallback.decode().count(oldref)==1
    def updated_html(text):
        text=text.replace(oldref,newref)
        text,count=re.subn(r'notification-settings\.js\?v=[A-Za-z0-9-]+','notification-settings.js?v=20261024-binding1',text)
        assert count==1,'Unexpected settings module reference'
        return text
    name='20261024-desktop-binding-'+str(int(time.time()))
    new=old.parent/name;backup=Path('/opt/funding-radar-web/backups')/name;backup.mkdir(mode=0o700)
    excluded={*assets,'robot-push/index.html','settings-preview-source.json'}
    preserved={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file() and str(p.relative_to(old)) not in excluded}
    shutil.copytree(old,new,symlinks=True)
    for asset in assets:shutil.copyfile(stage/asset,new/asset)
    (new/bundle).write_bytes(raw);(new/'robot-push/index.html').write_text(updated_html(oldindex))
    manifest=json.loads((new/'settings-preview-source.json').read_text());manifest.update(source_sha=sha,mode='per-code-desktop-binding')
    manifest['assets'].update({n:digest(new/n) for n in [*assets,bundle,'robot-push/index.html']})
    for directory,names in plan['backend'].items():
        group='push' if directory==str(push) else 'publisher'
        manifest['backend' if group=='push' else 'publisher'].update({n:digest(stage/group/n) for n in names})
    (new/'settings-preview-source.json').write_text(json.dumps(manifest,indent=2))
    assert all(digest(new/n)==value for n,value in preserved.items())
    (backup/'pwa-index.html').write_bytes(oldfallback)
    (backup/'deployment.json').write_text(json.dumps(plan,indent=2))
    restores=[]
    try:
        subprocess.run(['systemctl','stop','robot-push','radar-webpush-test'],check=True)
        before=settings()
        for directory,names in plan['backend'].items():
            group='push' if directory==str(push) else 'publisher'
            (backup/group).mkdir()
            for filename in names:
                target=Path(directory)/filename;original=backup/group/filename
                existed=target.exists()
                if existed:shutil.copy2(target,original)
                restores.append((target,original,existed))
                temporary=target.with_suffix('.py.next');shutil.copyfile(stage/group/filename,temporary);temporary.chmod(0o644);os.replace(temporary,target)
        subprocess.run(['systemctl','start','radar-webpush-test'],check=True);health(18885,'/radar/push-test/api/health','ok')
        subprocess.run(['systemctl','start','robot-push'],check=True);health(18883,'/health','ready')
        binding_probe();assert settings()==before,'User settings changed'
        link=current.with_name('current.desktop-binding-next');link.symlink_to(new);os.replace(link,current)
        temp=fallback.with_suffix('.next');temp.write_text(updated_html(oldfallback.decode()));temp.chmod(0o644);os.replace(temp,fallback)
        assert (push/'public/settings').resolve()==new/'robot-push/settings'
        assert all(digest(Path(d)/n)==digest(stage/('push' if d==str(push) else 'publisher')/n) for d,ns in plan['backend'].items() for n in ns)
        result=dict(source_sha=sha,release=str(new),previous=str(old),backup=str(backup),bundle=bundle,preservedFiles=len(preserved),rulesPreserved=True,phoneBindingsPreserved=True,bindingProtocolVerified=True)
        (backup/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    except Exception:
        if current.resolve()==new:
            link=current.with_name('current.desktop-binding-rollback');link.symlink_to(old);os.replace(link,current)
        fallback.write_bytes(oldfallback)
        subprocess.run(['systemctl','stop','robot-push','radar-webpush-test'],check=True)
        for target,original,existed in restores:
            if existed:shutil.copy2(original,target)
            else:target.unlink(missing_ok=True)
        subprocess.run(['systemctl','start','radar-webpush-test','robot-push'],check=True)
        raise
