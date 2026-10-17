"""Add compact settings assets to a copied live release without replacing feature modules."""
import argparse
import json
import pathlib
import paramiko

parser=argparse.ArgumentParser()
parser.add_argument('--expected-release',required=True)
args=parser.parse_args()
web=pathlib.Path(__file__).resolve().parents[1]
files={n:(web/'robot-push'/n).read_text(encoding='utf-8') for n in ['settings-layout.css','settings-layout.js']}
payload=dict(files=files,expected=args.expected_release)
script=r'''
import pathlib,json,fcntl,subprocess,shutil,os,time,re,hashlib
P=PAYLOAD
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pids():return {n:subprocess.check_output(['systemctl','show',n,'--property=MainPID','--value'],text=True).strip() for n in ['robot-push','radar-webpush-test']}
current=pathlib.Path('/opt/funding-radar-web/current')
fallback=pathlib.Path('/opt/radar-webpush-test/public/index.html')
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 old=current.resolve();assert str(old)==P['expected'],'Production changed; inspect the new release first'
 module=(old/'robot-push/notification-settings.js').read_text()
 assert all(s in module for s in ['ns-head','ns-body','ns-actions','ns-form'])
 before=pids();previous=fallback.read_bytes()
 name='20261017-compact-settings-'+str(int(time.time()))
 new=old.parent/name;backup=pathlib.Path('/opt/funding-radar-web/backups')/name
 backup.mkdir(parents=True);(backup/'pwa-index.html').write_bytes(previous)
 shutil.copytree(old,new,symlinks=True)
 for n,data in P['files'].items():(new/'robot-push'/n).write_text(data)
 def integrate(html):
  assert html.count('</head>')==1 and html.count('</body>')==1
  assert html.count('notification-settings.js?v=')==1
  html=re.sub(r'<link\b[^>]*href=["\']/radar/robot-push/settings-layout\.css[^"\']*["\'][^>]*>\s*','',html)
  html=re.sub(r'<script\b[^>]*src=["\']/radar/robot-push/settings-layout\.js[^"\']*["\'][^>]*>\s*</script>\s*','',html)
  # Force a fresh settings module while preserving its current feature implementation.
  html=re.sub(r'notification-settings\.js\?v=[^"\s]+','notification-settings.js?v='+sha(new/'robot-push/notification-settings.js')[:12]+'-compact1',html)
  html=html.replace('</head>','<link rel="stylesheet" href="/radar/robot-push/settings-layout.css?v=20261017-compact1">\n</head>')
  return html.replace('</body>','<script type="module" src="/radar/robot-push/settings-layout.js?v=20261017-compact1"></script></body>')
 page=new/'robot-push/index.html';page.write_text(integrate(page.read_text()))
 newfallback=integrate(previous.decode()).encode()
 count=0
 for p in old.rglob('*'):
  relative=str(p.relative_to(old))
  if p.is_file() and relative not in ['robot-push/index.html','robot-push/settings-layout.css','robot-push/settings-layout.js']:
   assert sha(p)==sha(new/relative),relative
   count+=1
 switched=False
 try:
  assert fallback.read_bytes()==previous
  tmp=fallback.with_suffix('.compact-next');tmp.write_bytes(newfallback);shutil.copymode(fallback,tmp)
  link=current.with_name('current.compact-next');link.symlink_to(new);os.replace(link,current);switched=True
  os.replace(tmp,fallback)
  assert pids()==before
  report=dict(release=str(new),previous=str(old),backup=str(backup),unchangedFiles=count,servicesUnchanged=True,
              layoutHashes={n:sha(new/'robot-push'/n) for n in P['files']},settingsModulePreserved=sha(new/'robot-push/notification-settings.js')==sha(old/'robot-push/notification-settings.js'))
  (backup/'deployment.json').write_text(json.dumps(report,indent=2));(new/'compact-settings-release.json').write_text(json.dumps(report,indent=2))
  print(json.dumps(report))
 except Exception:
  tmp.write_bytes(previous);os.replace(tmp,fallback)
  if switched:
   link=current.with_name('current.compact-rollback');link.symlink_to(old);os.replace(link,current)
  raise
'''.replace('PAYLOAD',repr(payload),1)
cfg=json.loads((pathlib.Path.home()/'.ssh/tencent-radar-initial.json').read_text());cfg['hostname']=cfg.pop('host')
c=paramiko.SSHClient();c.load_host_keys(str(pathlib.Path.home()/'.ssh/tencent-radar-known-hosts'))
try:
 c.connect(**cfg,timeout=15,look_for_keys=False,allow_agent=False)
 stdin,stdout,stderr=c.exec_command('sudo -n python3 -',timeout=90)
 stdin.write(script);stdin.channel.shutdown_write()
 result=stdout.read().decode();error=stderr.read().decode()
 if stdout.channel.recv_exit_status():raise RuntimeError(error[:2000])
 print(result)
finally:c.close()
