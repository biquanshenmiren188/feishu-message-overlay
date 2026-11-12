"""Incremental cluster rollout. Backups contain code only; rules never restored."""
import pathlib,json,hashlib,fcntl,subprocess,shutil,os,time,sys,runpy
P=pathlib.Path
stage=P(sys.argv[1]);sha=sys.argv[2];plan=json.loads((stage/'plan.json').read_text());base=plan['baseline'];current=P('/opt/funding-radar-web/current')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def atomic(p,raw):
 stat=p.stat();tmp=p.with_name(p.name+'.cluster-next');tmp.write_bytes(raw);os.chmod(tmp,stat.st_mode);os.chown(tmp,stat.st_uid,stat.st_gid);os.replace(tmp,p)
def switch(p):
 tmp=current.with_name('current.cluster-next');tmp.symlink_to(p);os.replace(tmp,current)
common=runpy.run_path(str(stage/'deploy-aster-oi.py'))
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 assert str(current.resolve())==base['root'],'Live release changed'
 for p,h in base['hashes'].items():assert digest(P(p))==h,p
 for p,h in plan['files'].items():assert digest(stage/p)==h,p
 targets={stage/'backend/signals.py':P('/opt/radar-webpush-test/signals.py'),stage/'backend/desktop_rules.py':P('/opt/radar-webpush-test/desktop_rules.py'),stage/'backend/cloud_receiver.py':P('/opt/robot-push/cloud_receiver.py'),stage/'fallback/index.html':P('/opt/radar-webpush-test/public/index.html')}
 for p in targets:
  if p.suffix=='.py':compile(p.read_bytes(),str(p),'exec')
 before=common['settings_digest']();old=current.resolve();name='20261112-cluster-'+str(time.time_ns());new=old.parent/name;backup=P('/opt/funding-radar-web/backups')/name;backup.mkdir(mode=0o700)
 originals={p:p.read_bytes() for p in targets.values()}
 for p,b in originals.items():(backup/p.name).write_bytes(b)
 (backup/'previous.txt').write_text(str(old));shutil.copytree(old,new,symlinks=True)
 for source in (stage/'static').rglob('*'):
  if source.is_file():dest=new/source.relative_to(stage/'static');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);dest.chmod(0o644)
 changed=set(str(p.relative_to(stage/'static')) for p in (stage/'static').rglob('*') if p.is_file())
 for p in old.rglob('*'):
  if p.is_file() and str(p.relative_to(old)) not in changed:assert digest(p)==digest(new/p.relative_to(old))
 try:
  for source,target in targets.items():atomic(target,source.read_bytes())
  switch(new)
  subprocess.run(['systemctl','restart','robot-push','radar-webpush-test'],check=True)
  common['healthy']();assert common['settings_digest']()==before,'settings changed'
  result={'sourceCommit':sha,'release':str(new),'previous':str(old),'backup':str(backup),'settingsPreserved':True,'files':plan['files']}
  (new/'cluster-source.json').write_text(json.dumps(result));print(json.dumps(result))
 except BaseException:
  for p,b in originals.items():atomic(p,b)
  switch(old);subprocess.run(['systemctl','restart','robot-push','radar-webpush-test'],check=True);raise
