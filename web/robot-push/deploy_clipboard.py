"""Patch only the active BOT card module graph, preserving independent live fixes."""
import argparse
import json
import pathlib
import re
import paramiko

HERE=pathlib.Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--baseline',type=pathlib.Path,required=True)
parser.add_argument('--prepare',type=pathlib.Path)
args=parser.parse_args()
baseline=json.loads((args.baseline/'manifest.json').read_text(encoding='utf-8'))
html=baseline['pages']['robot-push/index.html']['html']
entry=re.search(r'src="\./([^"/]+)/source-entry\.js[^"\s]*"',html)
assert entry,'Inspect the current BOT entry before updating'
oldfolder=entry[1];newfolder='clipboard-20261017-v2'
assert oldfolder!=newfolder
oldroot=args.baseline/'robot-push'/oldfolder
sources={n:(oldroot/n).read_text(encoding='utf-8') for n in ['source-entry.js','basispulse.js','basispulse-card.js']}
old_card=(HERE/'basispulse-card.js').read_text(encoding='utf-8')
original=sources['basispulse-card.js']
# Preserve live GC/Unicode builders and presentation; replace only the two copy handlers.
start="  const footer=el('footer','bp-card-foot')"
end="  const radar=safeRadar(d.radarUrl);"
assert original.count(start)==old_card.count(start)==1
assert original.count(end)==old_card.count(end)==1
assert original.count('copyText(')==2
original=re.sub(r"^import \{copyText,showCopyFallback\} from '[^']+/clipboard\.js\?v=20261017-copy1';\n",'',original,count=1)
assert 'import {copyText' not in original
replacement=old_card[old_card.index(start):old_card.index(end)]
sources['basispulse-card.js']="import {copyText} from './clipboard.js?v=20261017-copy2';\n"+original[:original.index(start)]+replacement+original[original.index(end):]
sources['clipboard.js']=(HERE/'clipboard.js').read_text(encoding='utf-8')
# Only these modules get a new URL. Shared worker and all unchanged imports retain identity.
def rebase(match):
    quote,name=match.groups();target=newfolder if name.split('?')[0] in sources else oldfolder
    return quote+'/radar/robot-push/'+target+'/'+name+quote
import_pattern=r'''(['"])(?:\./|/radar/robot-push/'''+re.escape(oldfolder)+r'''/)([^'"\n]+)\1'''
files={'robot-push/'+newfolder+'/'+n:re.sub(import_pattern,rebase,s) for n,s in sources.items()}
payload=dict(baseline=baseline,files=files,oldfolder=oldfolder,newfolder=newfolder,
             originals={n:(oldroot/n).read_text(encoding='utf-8') for n in ['source-entry.js','basispulse.js','basispulse-card.js']})
if args.prepare:
    for n,s in files.items():
        p=args.prepare/'radar'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8')
    print(json.dumps({'prepared':list(files),'base':baseline['release']}))
    raise SystemExit

remote=r'''
import pathlib,json,fcntl,shutil,hashlib,os,time,subprocess
P=PAYLOAD
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pids():return {n:subprocess.check_output(['systemctl','show',n,'--property=MainPID','--value'],text=True).strip() for n in ['robot-push','radar-webpush-test']}
def patch(html):
 old='./'+P['oldfolder']+'/source-entry.js';new='./'+P['newfolder']+'/source-entry.js'
 assert html.count(old)==1
 return html.replace(old,new)
current=pathlib.Path('/opt/funding-radar-web/current');fallback=pathlib.Path('/opt/radar-webpush-test/public/index.html')
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 old=current.resolve();assert str(old)==P['baseline']['release'],'Production changed; inspect first'
 for n,item in P['baseline']['pages'].items():assert sha(old/n)==item['sha256'],n
 for n,s in P['originals'].items():assert (old/'robot-push'/P['oldfolder']/n).read_text()==s,n
 assert not (old/'robot-push'/P['newfolder']).exists()
 previous=fallback.read_bytes();nextfallback=patch(previous.decode()).encode();before=pids()
 name='20261017-bot-clipboard-'+str(int(time.time()));new=old.parent/name;backup=pathlib.Path('/opt/funding-radar-web/backups')/name
 backup.mkdir(parents=True);(backup/'pwa-index.html').write_bytes(previous)
 shutil.copytree(old,new,symlinks=True)
 for n,s in P['files'].items():
  p=new/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
 page=new/'robot-push/index.html';page.write_text(patch(page.read_text()))
 count=0
 for f in old.rglob('*'):
  n=str(f.relative_to(old))
  if f.is_file() and n!='robot-push/index.html':assert sha(f)==sha(new/n),n;count+=1
 tmp=fallback.with_suffix('.clipboard-next');switched=False
 try:
  assert fallback.read_bytes()==previous
  tmp.write_bytes(nextfallback);shutil.copymode(fallback,tmp)
  link=current.with_name('current.clipboard-next');link.symlink_to(new);os.replace(link,current);switched=True
  os.replace(tmp,fallback);assert pids()==before
  report=dict(release=str(new),previous=str(old),backup=str(backup),unchangedFiles=count,servicesUnchanged=True,hashes={n:sha(new/n) for n in P['files']})
  (backup/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
 except Exception:
  tmp.write_bytes(previous);os.replace(tmp,fallback)
  if switched:
   link=current.with_name('current.clipboard-rollback');link.symlink_to(old);os.replace(link,current)
  raise
'''.replace('PAYLOAD',repr(payload),1)
cfg=json.loads((pathlib.Path.home()/'.ssh/tencent-radar-initial.json').read_text());cfg['hostname']=cfg.pop('host')
c=paramiko.SSHClient();c.load_host_keys(str(pathlib.Path.home()/'.ssh/tencent-radar-known-hosts'))
try:
 c.connect(**cfg,timeout=15,look_for_keys=False,allow_agent=False)
 i,o,e=c.exec_command('sudo -n python3 -',timeout=90);i.write(remote);i.channel.shutdown_write()
 result=o.read().decode();error=e.read().decode()
 if o.channel.recv_exit_status():raise RuntimeError(error[:2000])
 print(result)
finally:c.close()
