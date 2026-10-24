"""Server-side static-only deployment of a verified card reading candidate."""
import fcntl,hashlib,json,os,pathlib,shutil,subprocess,sys,time

stage=pathlib.Path(sys.argv[1]);commit=sys.argv[2]
plan=json.loads((stage/'candidate.json').read_text())
current=pathlib.Path('/opt/funding-radar-web/current')
fallback=pathlib.Path('/opt/radar-webpush-test/public/index.html')

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def processes():
    return {name:subprocess.check_output(['systemctl','show',name,'--property=MainPID','--value'],text=True).strip()
            for name in ('robot-push','radar-webpush-test')}
def switch(path,target):
    temp=path.with_name(path.name+'.card-scroll-next')
    temp.symlink_to(target);os.replace(temp,path)

with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    old=current.resolve()
    assert str(old)==plan['baseline']['release'],'Production release changed; inspect again'
    for name,expected in plan['baseline']['hashes'].items():assert digest(old/name)==expected,name
    assert digest(fallback)==plan['fallbackBefore'],'PWA fallback changed'
    for name,expected in plan['hashes'].items():assert digest(stage/name)==expected,name
    assert len(commit)==40 and all(c in '0123456789abcdef' for c in commit)
    before=processes();previous=fallback.read_bytes()
    name='20261024-card-scroll-'+str(int(time.time()))
    new=old.parent/name;backup=pathlib.Path('/opt/funding-radar-web/backups')/name
    backup.mkdir(mode=0o700);(backup/'pwa-index.html').write_bytes(previous)
    shutil.copytree(old,new,symlinks=True)
    assets=[n for n in plan['hashes'] if n!='pwa-index.html']
    for name in assets:
        dest=new/name;dest.parent.mkdir(parents=True,exist_ok=True)
        assert name=='robot-push/index.html' or not dest.exists(),'Refuse to overwrite a shared asset'
        shutil.copyfile(stage/name,dest);dest.chmod(0o644)
    preserved=0
    for path in old.rglob('*'):
        if path.is_file() and str(path.relative_to(old))!='robot-push/index.html':
            assert digest(path)==digest(new/path.relative_to(old));preserved+=1
    switched=False;temp=fallback.with_suffix('.card-scroll-next')
    try:
        assert fallback.read_bytes()==previous
        shutil.copyfile(stage/'pwa-index.html',temp);shutil.copymode(fallback,temp)
        switch(current,new);switched=True;os.replace(temp,fallback)
        assert processes()==before,'Unrelated service changed during release'
        assert all(digest(new/n)==plan['hashes'][n] for n in assets)
        assert digest(fallback)==plan['hashes']['pwa-index.html']
        report=dict(source_sha=commit,release=str(new),previous=str(old),backup=str(backup),
                    bundle=plan['bundle'],module=plan['module'],hashes=plan['hashes'],
                    preservedFiles=preserved,servicesUnchanged=True,desktopRestarted=False)
        (backup/'deployment.json').write_text(json.dumps(report,indent=2))
        (new/'card-scroll-source.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
    except BaseException:
        try:
            temp.write_bytes(previous);shutil.copymode(fallback,temp);os.replace(temp,fallback)
        finally:
            if switched:switch(current,old)
        raise
