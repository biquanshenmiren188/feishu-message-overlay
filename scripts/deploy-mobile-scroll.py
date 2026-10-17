"""Deploy a reviewed scroll candidate onto the exact inspected release, atomically."""
import argparse,base64,json,pathlib,subprocess,paramiko
p=argparse.ArgumentParser();p.add_argument('--baseline',type=pathlib.Path,required=True);p.add_argument('--candidate',type=pathlib.Path,required=True);a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[1]
payload={'baseline':json.loads((a.baseline/'manifest.json').read_text(encoding='utf-8')),
         'candidate':json.loads((a.candidate/'candidate.json').read_text(encoding='utf-8')),
         'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
         'files':{str(f.relative_to(a.candidate)).replace('\\','/'):base64.b64encode(f.read_bytes()).decode() for f in (a.candidate/'scroll-stability-20261017').iterdir()}}
script=r'''
import pathlib,json,hashlib,fcntl,os,time,shutil,base64,subprocess
P=PAYLOAD
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pids():return {n:subprocess.check_output(['systemctl','show',n,'--property=MainPID','--value'],text=True).strip() for n in ['robot-push','radar-webpush-test']}
def integrate(raw):
 html=raw.decode();old='/radar/'+P['candidate']['original'];new='/radar/'+P['candidate']['bundle']
 assert html.count(old)==1 and html.count('</head>')==1 and 'scroll-stability-20261017' not in html
 html=html.replace(old,new).replace('</head>','<link rel="stylesheet" href="/radar/scroll-stability-20261017/mobile-scroll.css">\n</head>')
 assert '/radar/radar-brand.css' in html,'Keep approved branding'
 return html.encode()
current=pathlib.Path('/opt/funding-radar-web/current');fallback=pathlib.Path('/opt/radar-webpush-test/public/index.html')
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 old=current.resolve();assert str(old)==P['baseline']['release'],'Reinspect changed production release'
 for n,h in P['baseline']['hashes'].items():assert sha(old/n)==h,n
 previous=fallback.read_bytes();nextFallback=integrate(previous);nextHtml=integrate((old/'robot-push/index.html').read_bytes())
 name='20261017-mobile-scroll-'+str(int(time.time()));new=old.parent/name;backup=pathlib.Path('/opt/funding-radar-web/backups')/name
 before=pids();backup.mkdir(parents=True);(backup/'pwa-index.html').write_bytes(previous);shutil.copytree(old,new,symlinks=True)
 for n,b in P['files'].items():
  f=new/n;assert not f.exists();f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(base64.b64decode(b))
 (new/'robot-push/index.html').write_bytes(nextHtml)
 count=0
 for f in old.rglob('*'):
  if f.is_file() and str(f.relative_to(old))!='robot-push/index.html':assert sha(f)==sha(new/f.relative_to(old));count+=1
 switched=False;tmp=fallback.with_suffix('.scroll-next')
 try:
  assert fallback.read_bytes()==previous
  tmp.write_bytes(nextFallback);shutil.copymode(fallback,tmp)
  link=current.with_name('current.scroll-next');link.symlink_to(new);os.replace(link,current);switched=True;os.replace(tmp,fallback)
  assert pids()==before
  report={'commit':P['commit'],'release':str(new),'previous':str(old),'backup':str(backup),'unchangedFiles':count,'servicesUnchanged':True,'hashes':{n:sha(new/n) for n in [*P['files'],'robot-push/index.html']},'fallbackSha256':sha(fallback)}
  (backup/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
 except Exception:
  tmp.write_bytes(previous);os.replace(tmp,fallback)
  if switched:
   link=current.with_name('current.scroll-rollback');link.symlink_to(old);os.replace(link,current)
  raise
'''.replace('PAYLOAD',repr(payload),1)
cfg=json.loads((pathlib.Path.home()/'.ssh/tencent-radar-initial.json').read_text());cfg['hostname']=cfg.pop('host')
c=paramiko.SSHClient();c.load_host_keys(str(pathlib.Path.home()/'.ssh/tencent-radar-known-hosts'))
try:
 c.connect(**cfg,timeout=15,look_for_keys=False,allow_agent=False)
 stdin,out,err=c.exec_command('sudo -n python3 -',timeout=90);stdin.write(script);stdin.channel.shutdown_write()
 result,error=out.read().decode(),err.read().decode();assert out.channel.recv_exit_status()==0,error[:2000];print(result)
finally:c.close()
