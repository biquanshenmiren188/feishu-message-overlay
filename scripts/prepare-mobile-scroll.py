"""Apply bounded patches to the inspected production bundle; preserve other modules."""
import argparse,hashlib,json,pathlib,shutil
p=argparse.ArgumentParser();p.add_argument('--baseline',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[1]
name='performance-20261017/bot-f098d52385ae.js';old=(a.baseline/name).read_bytes()
assert hashlib.sha256(old).hexdigest()=='f098d52385aec033f0350f8093919758edbc9f289fd0523358e212a22487c15b','Inspect changed production bundle first'
s=old.decode();changes=[]
def replace(before,after):
 global s
 assert s.count(before)==1,before
 s=s.replace(before,after);changes.append(before)
replace('function qe(e=!1){','function qe(e=!1){if(__radarScroll.defer(qe,()=>qe(e)))return;')
replace('a=r?Math.min(i,r.getBoundingClientRect().bottom):i','a=r?__radarBottom(r.getBoundingClientRect().bottom,i,matchMedia("(max-width:900px)").matches):i')
replace('function q(e=null){','function q(e=null){if(__radarScroll.defer(q,()=>q(e)))return;')
replace('function Nt(){','function Nt(){const __defer=__radarScroll.defer(Nt);')
replace('n&&(Fn=e);','n&&!__defer&&(Fn=e);')
replace('if(!u||u.matrixStamp!==A||n&&u.stamp!==JSON.stringify([l.data,g])){','if(!__defer&&(!u||u.matrixStamp!==A||n&&u.stamp!==JSON.stringify([l.data,g]))){')
replace('}u.card.classList.toggle("bp-expired",!h)', '}if(!u)continue;u.card.classList.toggle("bp-expired",!h)')
replace('b!==u.card&&Xe.insertBefore(u.card,b||null)','!__defer&&b!==u.card&&Xe.insertBefore(u.card,b||null)')
replace('for(let[l,f]of Ve)r.has(l)||(f.card.remove(),Ve.delete(l));','for(let[l,f]of Ve)if(!r.has(l)){if(__defer){f.card.classList.add("bp-expired");f.card.dataset.state="expired";f.age.textContent="已失效";}else{f.card.remove();Ve.delete(l);}}')
replace('kt.hidden=c>0,','!__defer&&(kt.hidden=c>0),')
prefix='import {mobileScrollGate as __radarScroll,stablePaneBottom as __radarBottom} from "./mobile-scroll.js";\n'
body=(prefix+s).encode();newname='bot-'+hashlib.sha256(body).hexdigest()[:12]+'.js'
dest=a.out/'scroll-stability-20261017';dest.mkdir(parents=True,exist_ok=True);(dest/newname).write_bytes(body)
for f in ['mobile-scroll.js','mobile-scroll.css']:shutil.copyfile(root/'web/robot-push'/f,dest/f)
report={'original':name,'bundle':'scroll-stability-20261017/'+newname,'patches':len(changes),'sourceSha':hashlib.sha256(old).hexdigest(),'sha256':hashlib.sha256(body).hexdigest()}
(a.out/'candidate.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
