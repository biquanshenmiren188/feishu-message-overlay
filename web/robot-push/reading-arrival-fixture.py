from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
root=Path('web/robot-push')
mock=r"""<script>
let fetches=0;const began=Date.now();
const message=(id,index,groupId='regular')=>({id,groupId,senderType:'bot',sentAt:new Date(began+index*1000-30000).toISOString(),title:'Synthetic '+id,body:groupId==='regular'?Array.from({length:45},(_,i)=>'Synthetic readable line '+i).join('\n'):'Synthetic pinned content',actions:[]});
window.fetch=async()=>({ok:true,json:async()=>({sourceConnected:true,updatedAt:new Date().toISOString(),messages:++fetches===1?[message('a',0),message('b',1),message('c',2)]:[message('a',0),message('b',1),message('c',2),message('d',3)],pinned:message('pin',0,'pinned')})});
</script>"""
fixture=r"""<!doctype html><meta charset='utf-8'><iframe id='app' src='/app' style='width:390px;height:844px'></iframe><pre id='result'>running</pre><script>
const checks=[],samples=[];const frame=document.getElementById('app');const check=(name,ok)=>checks.push({name,passed:!!ok});
function sample(name){const d=frame.contentDocument,b=d.getElementById('board'),p=d.getElementById('pinned'),y=b.getBoundingClientRect().top+p.offsetHeight;const e=[...d.querySelectorAll('#feed .message')].find(x=>x.getBoundingClientRect().bottom>y+4);const s={name,id:e?.dataset.id,offset:Math.round(b.scrollTop),targetY:Math.round(e.getBoundingClientRect().top-y),pin:d.querySelector('#pinned .message')?.dataset.id};samples.push(s);return s;}
frame.addEventListener('load',()=>{
setTimeout(()=>check('initialOldest',sample('initial').id==='a'),1000);
setTimeout(()=>check('fullFiveSecondDwell',sample('beforeDue').id==='a'),4500);
setTimeout(()=>check('arrivalDoesNotSkipB',sample('firstDue').id==='b'),6300);
setTimeout(()=>check('nextIsC',sample('secondDue').id==='c'),11300);
setTimeout(()=>{check('newArrivalReadAfterOlderItems',sample('thirdDue').id==='d');check('pinNeverCycles',samples.every(x=>x.pin==='pin'));check('threeActualVisualAdvances',samples[2].offset>samples[1].offset&&samples[3].offset>samples[2].offset&&samples[4].offset>samples[3].offset);check('headingsVisible',samples.every(x=>x.targetY>=-4));document.getElementById('result').textContent=JSON.stringify({checks,samples,passed:checks.every(c=>c.passed)});},16300);
});</script>"""
class H(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  if self.path=='/':body=fixture.encode();mime='text/html; charset=utf-8'
  elif self.path=='/app':body=root.joinpath('index.html').read_text(encoding='utf-8').replace('<head>','<head>'+mock).encode();mime='text/html; charset=utf-8'
  elif self.path in ['/page.mjs','/feed.mjs','/demo.mjs','/style.css']:
   body=root.joinpath(self.path[1:]).read_bytes();mime='text/css' if self.path.endswith('.css') else 'application/javascript'
  else:self.send_error(404);return
  self.send_response(200);self.send_header('Content-Type',mime);self.end_headers();self.wfile.write(body)
HTTPServer(('127.0.0.1',8095),H).serve_forever()
