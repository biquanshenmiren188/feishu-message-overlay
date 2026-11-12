"""Deploy five-message pin scrolling without rebuilding unrelated live assets."""
import pathlib,json,hashlib,fcntl,subprocess,shutil,os,time,sys,runpy
P=pathlib.Path
stage=P(sys.argv[1]);source=sys.argv[2];plan=json.loads((stage/'plan.json').read_text());base=plan['baseline'];current=P('/opt/funding-radar-web/current')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def atomic(p,raw):
 st=(p if p.exists() else p.parent/'server.py').stat();tmp=p.with_name(p.name+'.history-next');tmp.write_bytes(raw);os.chmod(tmp,st.st_mode);os.chown(tmp,st.st_uid,st.st_gid);os.replace(tmp,p)
def switch(p):
 tmp=current.with_name('current.history-next');tmp.symlink_to(p);os.replace(tmp,current)
common=runpy.run_path(str(stage/'deploy-aster-oi.py'))
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 assert str(current.resolve())==base['root'],'Live release changed'
 for p,h in base['hashes'].items():assert digest(P(p))==h,p
 for p,h in plan['files'].items():assert digest(stage/p)==h,p
 assert not P('/opt/robot-push/pin_history.py').exists(),'Unexpected existing archive implementation'
 targets={stage/'backend/publisher-server.py':P('/opt/robot-push/server.py'),stage/'backend/cloud_receiver.py':P('/opt/robot-push/cloud_receiver.py'),stage/'backend/pin_history.py':P('/opt/robot-push/pin_history.py'),stage/'backend/push-server.py':P('/opt/radar-webpush-test/server.py'),stage/'fallback/index.html':P('/opt/radar-webpush-test/public/index.html')}
 for p in targets:
  if p.suffix=='.py':compile(p.read_bytes(),str(p),'exec')
 before=common['settings_digest']();old=current.resolve();name='20261112-pin-history-'+str(time.time_ns());new=old.parent/name;backup=P('/opt/funding-radar-web/backups')/name;backup.mkdir(mode=0o700)
 originals={p:p.read_bytes() if p.exists() else None for p in targets.values()}
 for index,(p,raw) in enumerate(originals.items()):
  if raw is not None:(backup/(str(index)+'-'+p.name)).write_bytes(raw)
 (backup/'rollback.json').write_text(json.dumps({'previous':str(old),'files':{str(p):str(index)+'-'+p.name if raw is not None else None for index,(p,raw) in enumerate(originals.items())}}))
 shutil.copytree(old,new,symlinks=True)
 for p in (stage/'static').rglob('*'):
  if p.is_file():target=new/p.relative_to(stage/'static');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target);target.chmod(0o644)
 changed={str(p.relative_to(stage/'static')) for p in (stage/'static').rglob('*') if p.is_file()};preserved=0
 for p in old.rglob('*'):
  if p.is_file() and str(p.relative_to(old)) not in changed:assert digest(p)==digest(new/p.relative_to(old));preserved+=1
 try:
  for p,target in targets.items():atomic(target,p.read_bytes())
  switch(new);subprocess.run(['systemctl','restart','robot-push','radar-webpush-test'],check=True)
  common['healthy']();assert common['settings_digest']()==before,'Settings changed'
  result={'sourceCommit':source,'release':str(new),'previous':str(old),'backup':str(backup),'settingsPreserved':True,'preservedStaticFiles':preserved,'files':plan['files']}
  (new/'pin-history-source.json').write_text(json.dumps(result));print(json.dumps(result))
 except BaseException:
  for p,raw in originals.items():
   if raw is not None:atomic(p,raw)
   elif p.exists():p.unlink()
  switch(old);subprocess.run(['systemctl','restart','robot-push','radar-webpush-test'],check=True);raise
