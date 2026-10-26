"""Publish the inspected strong-signal expression and signals.py only.

Usage on host: python3 deploy-strong-v2.py STAGE SOURCE_SHA [--apply]
Default is read-only preflight. No native installer is touched. Rollback restores
code and entry files only, never saved rules, settings, bindings or history.
"""
import fcntl,hashlib,json,os,re,runpy,shutil,stat,subprocess,sys,time
from pathlib import Path

common=runpy.run_path(str(Path(__file__).with_name('deploy-aster-oi.py')))
settings_digest,other_pids,healthy=(common[k] for k in ('settings_digest','other_pids','healthy'))
ROOT=Path('/opt/radar-webpush-test');CURRENT=Path('/opt/funding-radar-web/current')
FALLBACK=ROOT/'public/index.html';SERVICE='radar-webpush-test'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def safe(name):return bool(name) and not name.startswith('/') and '..' not in name.split('/') and '\\' not in name
def atomic(path,raw,metadata):
    tmp=path.with_name(path.name+'.strong-v2-next')
    try:
        with tmp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,stat.S_IMODE(metadata.st_mode));os.chown(tmp,metadata.st_uid,metadata.st_gid);os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)
def switch(target):
    tmp=CURRENT.with_name('current.strong-v2-next');tmp.symlink_to(target);os.replace(tmp,CURRENT)

def main():
    stage=Path(sys.argv[1]).resolve();sha=sys.argv[2];apply='--apply' in sys.argv[3:]
    assert re.fullmatch('[a-f0-9]{40}',sha)
    plan=json.loads((stage/'strong-v2-plan.json').read_text())
    assert plan['sourceCommit']==sha,'Candidate source commit mismatch'
    bundle=plan['bundle'];assert re.fullmatch(r'performance-20261017/bot-cards-strong-v2-[a-f0-9]{16}\.js',bundle)
    assert set(plan['staticFiles'])=={bundle,'robot-push/index.html'}
    assert set(plan['backendFiles'])=={'signals.py'}
    for name,expected in plan['candidateFiles'].items():assert safe(name) and digest(stage/name)==expected,'Candidate changed: '+name
    for name,expected in plan['staticFiles'].items():assert plan['candidateFiles']['static/'+name]==expected
    assert plan['candidateFiles']['backend/signals.py']==plan['backendFiles']['signals.py']
    assert plan['candidateFiles']['fallback/index.html']==plan['fallbackSha256']
    validation=json.loads((stage/'strong-v2-validation.json').read_text())
    assert validation['sourceCommit']==sha and validation['hashes']==plan['candidateFiles'],'Candidate not validated'
    assert validation['productionSummaryTests']>=28 and validation['backendTests']>=140,'Incomplete candidate checks'
    compile((stage/'backend/signals.py').read_bytes(),'signals.py','exec')
    with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old=CURRENT.resolve(strict=True);assert old.parent==Path('/opt/funding-radar-web/releases')
        for name,expected in plan['baseline']['staticFiles'].items():
            assert safe(name) and digest(old/name)==expected,'Changed inspected static file: '+name
        assert digest(ROOT/'signals.py')==plan['baseline']['backendSha256'],'Changed signals backend'
        assert digest(FALLBACK)==plan['baseline']['fallbackSha256'],'Changed PWA fallback'
        assert not (old/bundle).exists(),'Immutable bundle already exists'
        before=settings_digest();pids=other_pids();fallback=FALLBACK.read_bytes();fallback_meta=FALLBACK.stat()
        old_code=(ROOT/'signals.py').read_bytes();metadata=(ROOT/'signals.py').stat()
        if not apply:
            print(json.dumps(dict(preflight=True,source_sha=sha,current=str(old),inspectedRelease=plan['baseline']['release'],bundle=bundle)));return
        name=time.strftime('%Y%m%d',time.gmtime())+'-strong-v2-'+str(int(time.time()))
        new=old.parent/name;backup=Path('/opt/funding-radar-web/backups')/name;backup.mkdir(mode=0o700)
        (backup/'previous-target.txt').write_text(str(old));(backup/'signals.py').write_bytes(old_code)
        (backup/'pwa-index.html').write_bytes(fallback)
        (backup/'strong-v2-plan.json').write_bytes((stage/'strong-v2-plan.json').read_bytes())
        originals={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file()}
        shutil.copytree(old,new,symlinks=True)
        for name in plan['staticFiles']:
            target=new/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(stage/'static'/name,target);target.chmod(0o644)
        for name,expected in originals.items():
            assert digest(old/name)==expected,'Concurrent source change: '+name
            if name not in plan['staticFiles']:assert digest(new/name)==expected,'Unrelated static changed: '+name
        changed=False;switched=False
        try:
            assert settings_digest()==before and other_pids()==pids and CURRENT.resolve()==old
            assert (ROOT/'signals.py').read_bytes()==old_code and FALLBACK.read_bytes()==fallback
            changed=True;subprocess.run(['systemctl','stop',SERVICE],check=True)
            assert settings_digest()==before,'Rules/bindings changed before code swap'
            atomic(ROOT/'signals.py',(stage/'backend/signals.py').read_bytes(),metadata)
            atomic(FALLBACK,(stage/'fallback/index.html').read_bytes(),fallback_meta)
            switch(new);switched=True
            subprocess.run(['systemctl','start',SERVICE],check=True);healthy()
            assert settings_digest()==before,'Rules or bindings changed'
            assert other_pids()==pids,'Unrelated services changed'
            assert digest(ROOT/'signals.py')==plan['backendFiles']['signals.py']
            assert digest(FALLBACK)==plan['fallbackSha256']
            assert all(digest(new/n)==value for n,value in plan['staticFiles'].items())
            result=dict(source_sha=sha,release=str(new),previous=str(old),backup=str(backup),
                        inspectedRelease=plan['baseline']['release'],rulesAndBindingsPreserved=True,
                        unrelatedServicesUnchanged=True,restartedServices=[SERVICE],
                        preservedFiles=sum(name not in plan['staticFiles'] for name in originals),hashes=plan['candidateFiles'])
            (backup/'result.json').write_text(json.dumps(result,indent=2))
            (new/'strong-v2-source.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
        except BaseException:
            if changed:
                subprocess.run(['systemctl','stop',SERVICE],check=True)
                atomic(ROOT/'signals.py',old_code,metadata);atomic(FALLBACK,fallback,fallback_meta)
                if switched:switch(old)
                subprocess.run(['systemctl','start',SERVICE],check=True);healthy()
            raise

if __name__=='__main__':main()
