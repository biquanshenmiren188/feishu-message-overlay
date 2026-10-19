const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
// Usage: node scripts/pwa-startup-browser-test.cjs <directory with live-sw.js and candidate/sw.js>
const root=path.resolve(process.argv[2]||'.');
let offline=false,feedCount=0;
const shell=`<!doctype html><html><head><base href="/radar/robot-push/"><meta name="viewport" content="width=device-width"><title>启动缓存测试</title><link rel="stylesheet" href="/radar/test-shell-123456789abc.css"></head><body><header>聚宝扫描 · 缓存隔离测试</header><nav>全市场费率　机会筛选　BOT</nav><section id="pinned"></section><section id="feed"></section><p id="status">读取测试数据</p><script>
const nav=performance.getEntriesByType('navigation')[0];
fetch('/radar/robot-push/feed.json').then(async r=>{document.getElementById('status').textContent=r.ok?'实时测试消息 '+(await r.json()).seq:'网络不可用，无缓存消息';}).catch(()=>{document.getElementById('status').textContent='网络不可用，无缓存消息';});
requestAnimationFrame(()=>requestAnimationFrame(()=>setTimeout(()=>parent.postMessage({kind:'startup-sample',ttfb:nav.responseStart,elapsed:performance.now(),paint:performance.getEntriesByType('paint').find(x=>x.name==='first-contentful-paint')?.startTime,css:getComputedStyle(document.body).backgroundColor},location.origin),40)));
</script></body></html>`;
const page=`<!doctype html><meta charset="utf-8"><title>PWA 启动隔离验证</title><style>body{font:16px system-ui;padding:24px;background:#f5f7fa}button{padding:12px}iframe{width:393px;height:270px;background:white;border:1px solid #ddd}pre{white-space:pre-wrap} .row{display:flex;gap:24px}</style><h1>PWA 启动隔离验证</h1><p>仅本机测试，无真实消息、订阅或账户。模拟 HTML 与 CSS 各等待 2 秒。</p><button id="run">运行前后对比</button><div class="row"><iframe id="frame" src="about:blank"></iframe><pre id="log">尚未运行</pre></div><script>
const log=document.getElementById('log'),frame=document.getElementById('frame');const rows=[];
function show(x){log.textContent=JSON.stringify(x,null,2)}
async function install(variant){const reg=await navigator.serviceWorker.register('/radar/push-test/sw.js?variant='+variant,{scope:'/radar/push-test/',updateViaCache:'none'});let worker=reg.installing||reg.waiting||reg.active;if(worker.state!=='activated')await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('activation timeout')),12000);worker.addEventListener('statechange',()=>{if(worker.state==='activated'){clearTimeout(t);resolve()}})});}
async function visit(label){show({stage:label,rows});const data=await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('load timeout')),15000);function receive(e){if(e.origin!==location.origin||e.source!==frame.contentWindow||e.data?.kind!=='startup-sample')return;removeEventListener('message',receive);clearTimeout(t);resolve(e.data)}addEventListener('message',receive);frame.src='/radar/push-test/';});rows.push({label,...data});show({rows});}
document.getElementById('run').onclick=async()=>{document.getElementById('run').disabled=true;try{await install('before');await visit('before-prime');for(let i=1;i<=3;i++)await visit('before-warm-'+i);await install('after');await visit('after-prime');for(let i=1;i<=3;i++)await visit('after-warm-'+i);await fetch('/test/offline',{method:'POST'});await visit('after-offline');show({done:true,rows});}catch(e){show({error:String(e),rows})}};
</script>`;
const server=http.createServer(async(req,res)=>{
 const url=new URL(req.url,'http://localhost:8765');
 const send=(type,body,status=200)=>{res.writeHead(status,{'Content-Type':type,'Cache-Control':'no-store'});res.end(body)};
 if(url.pathname==='/test/')return send('text/html; charset=utf-8',page);
 if(url.pathname==='/test/offline'){offline=true;return send('text/plain','ok')}
 if(url.pathname==='/radar/push-test/sw.js')return send('application/javascript',fs.readFileSync(path.join(root,url.searchParams.get('variant')==='before'?'live-sw.js':'candidate/sw.js')));
 if(url.pathname==='/radar/robot-push/feed.json')return send('application/json',JSON.stringify({seq:++feedCount}),offline?503:200);
 if(['/radar/push-test/','/radar/push-test/index.html'].includes(url.pathname)){
  await new Promise(r=>setTimeout(r,2000));return send('text/html; charset=utf-8',offline?'unavailable':shell,offline?503:200);
 }
 if(url.pathname==='/radar/test-shell-123456789abc.css'){
  await new Promise(r=>setTimeout(r,2000));return send('text/css','body{font:18px system-ui;background:#f4f8f6;color:#161b22;padding:12px}header{font-weight:700;font-size:24px}nav{padding:16px 0}',offline?503:200);
 }
 if(url.pathname.endsWith('.css'))return send('text/css','');
 if(url.pathname.endsWith('.js'))return send('application/javascript','');
 if(url.pathname.endsWith('.webmanifest'))return send('application/manifest+json','{}');
 if(url.pathname.endsWith('.png'))return send('image/png','');
 return send('text/plain','not found',404);
});
server.listen(8765,'127.0.0.1',()=>console.log('Local PWA test: http://127.0.0.1:8765/test/'));
