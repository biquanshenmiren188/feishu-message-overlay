"""Publish only matched OI evidence and its web display; preserve live overlays/data."""
import fcntl,hashlib,json,os,re,runpy,shutil,stat,subprocess,sys,time
from pathlib import Path
common=runpy.run_path(str(Path(__file__).with_name('deploy-aster-oi.py')))
settings_digest,other_pids,healthy=(common[k] for k in ('settings_digest','other_pids','healthy'))
ROOT=Path('/opt/radar-webpush-test');CURRENT=Path('/opt/funding-radar-web/current');FALLBACK=ROOT/'public/index.html'
BACKENDS=('advanced_rules.py','desktop_rules.py','server.py')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def atomic(path,raw,metadata):
 tmp=path.with_name(path.name+'.oi-display-next')
 try:
  with tmp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  os.chmod(tmp,stat.S_IMODE(metadata.st_mode));os.chown(tmp,metadata.st_uid,metadata.st_gid);os.replace(tmp,path)
 finally:tmp.unlink(missing_ok=True)
def switch(target):
 tmp=CURRENT.with_name('current.oi-display-next');tmp.symlink_to(target);os.replace(tmp,CURRENT)
def main():
 stage=Path(sys.argv[1]);sha=sys.argv[2];assert re.fullmatch('[a-f0-9]{40}',sha)
 plan=json.loads((stage/'plan.json').read_text());assert plan['sourceCommit']==sha
 for name,expected in plan['stageHashes'].items():
  assert not Path(name).is_absolute() and '..' not in Path(name).parts
  assert digest(stage/name)==expected,name
 validation=json.loads((stage/'validation.json').read_text());assert validation['hashes']==plan['stageHashes'] and validation['passed']
 assets=['robot-push/card-oi.js','robot-push/card-policy.js',plan['bundle'],'robot-push/index.html']
 with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);old=CURRENT.resolve();assert old.parent==Path('/opt/funding-radar-web/releases')
  for name,h in plan['backends'].items():assert digest(ROOT/name)==h,'Backend changed: '+name
  for name,h in plan['baselineHashes'].items():assert digest(old/name)==h,'Static changed: '+name
  assert digest(FALLBACK)==plan['fallbackHash'],'Fallback changed'
  before=settings_digest();pids=other_pids();fallback=FALLBACK.read_bytes();fallback_meta=FALLBACK.stat()
  name='20261028-card-oi-'+str(int(time.time()));new=old.parent/name;backup=Path('/opt/funding-radar-web/backups')/name;backup.mkdir(mode=0o700)
  originals={n:(ROOT/n).read_bytes() for n in BACKENDS};metadata={n:(ROOT/n).stat() for n in BACKENDS}
  for n,raw in originals.items():(backup/n).write_bytes(raw)
  (backup/'pwa-index.html').write_bytes(fallback);(backup/'plan.json').write_bytes((stage/'plan.json').read_bytes())
  excluded=set(assets)|{'settings-preview-source.json'}
  preserved={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file() and str(p.relative_to(old)) not in excluded}
  shutil.copytree(old,new,symlinks=True)
  for a in assets:
   assert not (new/a).is_symlink();shutil.copyfile(stage/a,new/a)
  manifest_path=new/'settings-preview-source.json';manifest=json.loads(manifest_path.read_text());manifest['card_oi_consistency']=dict(source_sha=sha,hashes=plan['stageHashes']);manifest_path.write_text(json.dumps(manifest,indent=2))
  assert all(digest(new/n)==h for n,h in preserved.items())
  changed=False;switched=False
  try:
   assert settings_digest()==before and other_pids()==pids and CURRENT.resolve()==old and FALLBACK.read_bytes()==fallback
   changed=True;subprocess.run(['systemctl','stop','radar-webpush-test'],check=True)
   assert settings_digest()==before,'Settings changed before install'
   for n in BACKENDS:atomic(ROOT/n,(stage/n).read_bytes(),metadata[n])
   atomic(FALLBACK,(stage/'pwa-index.html').read_bytes(),fallback_meta);switch(new);switched=True
   subprocess.run(['systemctl','start','radar-webpush-test'],check=True);healthy()
   assert settings_digest()==before and other_pids()==pids,'Settings or unrelated services changed'
   assert all(digest(ROOT/n)==plan['stageHashes'][n] for n in BACKENDS)
   assert all(digest(new/n)==plan['stageHashes'][n] for n in assets)
   assert digest(FALLBACK)==plan['stageHashes']['pwa-index.html']
   result=dict(source_sha=sha,release=str(new),previous=str(old),backup=str(backup),rulesAndBindingsPreserved=True,unrelatedServicesUnchanged=True,restartedServices=['radar-webpush-test'],preservedFiles=len(preserved),hashes=plan['stageHashes'])
   (backup/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
  except BaseException:
   if changed:
    subprocess.run(['systemctl','stop','radar-webpush-test'],check=True)
    for n,raw in originals.items():atomic(ROOT/n,raw,metadata[n])
    atomic(FALLBACK,fallback,fallback_meta)
    if switched:switch(old)
    subprocess.run(['systemctl','start','radar-webpush-test'],check=True);healthy()
   raise
if __name__=='__main__':main()
