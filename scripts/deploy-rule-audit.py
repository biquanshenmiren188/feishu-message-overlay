"""Publish bounded rule fixes and phone version compatibility, preserving data.

Usage on host: python3 deploy-rule-audit.py STAGE SOURCE_SHA
Stage hashes and candidate validation are mandatory. Backend rollback restores
code only; static release is cloned so unrelated published assets are retained.
"""
import fcntl,hashlib,json,os,re,runpy,shutil,stat,subprocess,sys,time
from pathlib import Path

common=runpy.run_path(str(Path(__file__).with_name('deploy-aster-oi.py')))
settings_digest,other_pids,healthy=(common[k] for k in ('settings_digest','other_pids','healthy'))
ROOT=Path('/opt/radar-webpush-test');CURRENT=Path('/opt/funding-radar-web/current')
FALLBACK=ROOT/'public/index.html';ASSET='robot-push/notification-settings.js'
BACKENDS=('advanced_rules.py','signals.py','desktop_rules.py','live.py','server.py','hyperliquid_oi.py','oi_source_cache.py')

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def atomic(path,raw,metadata):
    tmp=path.with_name(path.name+'.audit-next')
    try:
        with tmp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,stat.S_IMODE(metadata.st_mode));os.chown(tmp,metadata.st_uid,metadata.st_gid);os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)
def switch(target):
    tmp=CURRENT.with_name('current.audit-next');tmp.symlink_to(target);os.replace(tmp,CURRENT)
def main():
    stage=Path(sys.argv[1]);sha=sys.argv[2];assert re.fullmatch('[a-f0-9]{40}',sha)
    plan=json.loads((stage/'audit-plan.json').read_text())
    assert set(plan['backends'])==set(BACKENDS)
    for name,expected in plan['candidate'].items():assert digest(stage/name)==expected,name
    validation=json.loads((stage/'audit-validation.json').read_text());assert validation['hashes']==plan['candidate']
    for name in BACKENDS:compile((stage/name).read_bytes(),name,'exec')
    with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        old=CURRENT.resolve();assert old.parent==Path('/opt/funding-radar-web/releases')
        for name,expected in plan['backends'].items():
            assert (digest(ROOT/name) if (ROOT/name).exists() else None)==expected,'Changed backend: '+name
        assert digest(old/ASSET)==plan['assetBaseline'],'Changed notification settings'
        before=settings_digest();pids=other_pids();fallback=FALLBACK.read_bytes();fallback_meta=FALLBACK.stat()
        release='20261026-rule-audit-'+str(int(time.time()))
        new=old.parent/release;backup=Path('/opt/funding-radar-web/backups')/release;backup.mkdir(mode=0o700)
        old_code={name:(ROOT/name).read_bytes() if (ROOT/name).exists() else None for name in BACKENDS}
        metadata={name:(ROOT/name).stat() if (ROOT/name).exists() else (ROOT/'advanced_rules.py').stat() for name in BACKENDS}
        for name,raw in old_code.items():
            if raw is not None:(backup/name).write_bytes(raw)
        (backup/'pwa-index.html').write_bytes(fallback);(backup/'audit-plan.json').write_bytes((stage/'audit-plan.json').read_bytes())
        originals={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file()}
        shutil.copytree(old,new,symlinks=True)
        shutil.copyfile(stage/'notification-settings.js',new/ASSET)
        def entry(raw):
            value,count=re.subn(rb'notification-settings\.js\?v=[^"\s<>]+',('notification-settings.js?v=20261026-audit-'+sha[:8]).encode(),raw)
            assert count==1,'Unexpected settings entry count';return value
        (new/'robot-push/index.html').write_bytes(entry((old/'robot-push/index.html').read_bytes()))
        new_fallback=entry(fallback)
        manifest_path=new/'settings-preview-source.json';manifest=json.loads(manifest_path.read_text())
        manifest['rule_audit']={'source_sha':sha,'backends':{n:plan['candidate'][n] for n in BACKENDS},'asset':digest(new/ASSET)}
        manifest_path.write_text(json.dumps(manifest,indent=2))
        excluded={ASSET,'robot-push/index.html','settings-preview-source.json'}
        assert all(digest(new/name)==value for name,value in originals.items() if name not in excluded)
        changed=False;switched=False
        try:
            assert settings_digest()==before and other_pids()==pids and CURRENT.resolve()==old and FALLBACK.read_bytes()==fallback
            changed=True;subprocess.run(['systemctl','stop','radar-webpush-test'],check=True)
            for name in BACKENDS:atomic(ROOT/name,(stage/name).read_bytes(),metadata[name])
            atomic(FALLBACK,new_fallback,fallback_meta);switch(new);switched=True
            subprocess.run(['systemctl','start','radar-webpush-test'],check=True);healthy()
            assert settings_digest()==before,'Rules or bindings changed'
            assert other_pids()==pids,'Unrelated services changed'
            assert all(digest(ROOT/name)==plan['candidate'][name] for name in BACKENDS)
            assert digest(new/ASSET)==plan['candidate']['notification-settings.js']
            result=dict(source_sha=sha,release=str(new),previous=str(old),backup=str(backup),
                        rulesAndBindingsPreserved=True,unrelatedServicesUnchanged=True,restartedServices=['radar-webpush-test'],
                        preservedFiles=len(originals)-len(excluded),hashes=plan['candidate'])
            (backup/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
        except BaseException:
            if changed:
                subprocess.run(['systemctl','stop','radar-webpush-test'],check=True)
                for name,raw in old_code.items():
                    if raw is None:(ROOT/name).unlink(missing_ok=True)
                    else:atomic(ROOT/name,raw,metadata[name])
                atomic(FALLBACK,fallback,fallback_meta)
                if switched:switch(old)
                subprocess.run(['systemctl','start','radar-webpush-test'],check=True);healthy()
            raise

if __name__=='__main__':main()
