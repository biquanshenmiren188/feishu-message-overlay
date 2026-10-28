/* Actual production HTML/bundle with synthetic streams, identity and policies. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const runtime=path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {chromium,webkit}=createRequire(runtime)('playwright');
const candidate=path.resolve(process.argv[2]||'../feed-filter-candidate'),baseline=path.resolve(process.argv[3]||'../feed-filter-live-baseline'),output=path.resolve(process.argv[4]||'../feed-filter-browser-results');
fs.mkdirSync(output,{recursive:true});
const cfg=JSON.parse(fs.readFileSync(path.join(candidate,'plan.json'))),hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
for(const [name,expected]of Object.entries(cfg.stageHashes))assert.equal(hash(fs.readFileSync(path.join(candidate,name))),expected,name);
const message=(id,coin='UNITREE',group='ordinary',stamp=Date.now()-60000)=>({id,groupId:group,senderType:'bot',title:`R0 +0.4% | ${coin} | FF | P75 +0.6% | GT→AS`,body:`R0 +0.4% | ${coin} | FF | P75 +0.6% | GT→AS\n盘口差 +0.5%`,sentAt:new Date(stamp).toISOString(),actions:[{label:'查看雷达',url:`https://leida.shenmiren.work/radar/?symbol=${coin}`}]});
const initialFeed=()=>({messages:[message('unitree'),message('btc','BTC'),message('muted','PREDICT')],pinned:{...message('strong','UNITREE','pinned'),title:'强信号 | UNITREE | 3组',body:'强信号 | UNITREE | 3组\nR0 | FF | GT→AS | +0.25%\nR0 | FF | GT→BG | +0.29%\nR0 | FF | GT→OK | +0.12%'},updatedAt:new Date().toISOString(),sourceConnected:true});
const fingerprint=m=>hash(JSON.stringify([m.id,m.title,m.body,m.sentAt]));
const bare=()=>({excluded_coins:[],advanced:{coins:[]}});
const results=[];
function report(){fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({candidate,baseline,stageHashes:cfg.stageHashes,results},null,2));}
(async()=>{
 for(const [engineName,engine]of [['chromium',chromium],['webkit',webkit]]){
  const browser=await engine.launch({headless:true});
  try{for(const width of [1440,393,320]){
   const context=await browser.newContext({viewport:{width,height:width===1440?1000:852},serviceWorkers:'block'}),page=await context.newPage();
   const errors=[],posts=[],unexpected=[],external=[],loadedAssets={};page.on('pageerror',e=>errors.push(e.message));
   const original=initialFeed();let source=structuredClone(original),hidden=true,fail=false,gate=null,apiCount=0,cardFail=false,desktopEnabled=true;
   const decisions=token=>({revision:1,desktopEnabled,decisions:Object.fromEntries([...source.messages,...(source.pinned?[source.pinned]:[])].map(m=>[m.id,{fingerprint:fingerprint(m),action:token==='Bearer second'?'allow':m.title.includes('PREDICT')?'mute':hidden&&m.title.includes('UNITREE')?'hide':'allow'}]))});
   await context.addInitScript(feed=>{
    localStorage.setItem('radar-settings-token','first');localStorage.setItem('robot-push-ui',JSON.stringify({enabled:false,sound:true}));
    window.audioStarts=0;window.testCopied=[];Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.testCopied.push(text);}}});
    window.AudioContext=class{state='running';destination={};async resume(){}async suspend(){this.state='suspended';}async decodeAudioData(){return {};}createBufferSource(){return {connect(){},disconnect(){},stop(){},start(){window.audioStarts++;}};}};
    window.testFeed=feed;window.testPorts=[];window.testStamp=Date.now();
    window.testCard=asset=>({id:asset,pair:asset,asset,strategy:'FF',enteredAt:new Date(Date.now()-6000).toISOString(),updatedAt:new Date().toISOString(),validUntil:new Date(Date.now()+120000).toISOString(),v2Residual:{level:1,bps:55},details:{netBps:12,marketBps:30,p75Bps:40,indexBps:0,legs:[{exchange:'binance',spot:false,symbol:asset+'USDT',rate:.0001,hours:4,oi:371600,volume:3000000},{exchange:'gate',spot:false,symbol:asset+'_USDT',rate:.0002,hours:4,oi:371600,volume:3000000}],transferWallets:[]},radarUrl:'https://leida.shenmiren.work/radar/?symbol='+asset});
    window.testData=name=>name==='feed'?window.testFeed:{status:'connected',receivedAt:new Date().toISOString(),snapshot:{sampledAt:new Date(++window.testStamp).toISOString(),complete:true,active:['BLOCK','ALLOW'].map(window.testCard),retained:[],retentionSeconds:30}};
    window.SharedWorker=class{constructor(){const port={onmessage:null,start(){queueMicrotask(()=>port.onmessage?.({data:{type:'ready'}}));},postMessage({channels=[]}){port.channels=channels;for(const name of channels)queueMicrotask(()=>port.onmessage?.({data:{type:'data',name,data:window.testData(name)}}));},close(){}};this.port=port;window.testPorts.push(port);}};
    window.testPush=feed=>{if(feed)window.testFeed=feed;window.testStamp=Math.max(window.testStamp,Date.now());for(const port of window.testPorts)for(const name of port.channels||[])port.onmessage?.({data:{type:'data',name,data:window.testData(name)}});};
   },original);
   await context.route('**/*',async route=>{
    const req=route.request(),u=new URL(req.url());
    if(u.origin!=='https://blocked.test'){external.push(u.origin+u.pathname);return route.abort('blockedbyclient');}
    if(req.method()!=='GET'){posts.push(u.pathname);return route.fulfill({status:403,json:{error:'Synthetic test forbids writes'}});}
    if(u.pathname.endsWith('/api/message-decisions')){apiCount++;const data=decisions(req.headers().authorization),failed=fail,wait=gate;if(wait)await wait;try{return await route.fulfill({status:failed?403:200,json:failed?{error:'Synthetic denied'}:data});}catch{return;}}
    if(u.pathname.endsWith('/api/card-decisions')||u.pathname.endsWith('/api/card-oi')){
     const n=Date.now(),oi=Object.fromEntries(['BLOCK','ALLOW'].map(id=>[id,Object.fromEntries(['left','right'].map((side,i)=>[side,{exchange:i?'gate':'binance',market:'perp',threshold:u.pathname.endsWith('/api/card-oi')?null:50,checkedAt:n,time:n-1000,expiresAt:n+299000,basis:'double-v1',status:'ok',value:id==='BLOCK'?371600:871898}]))]));
     return route.fulfill({status:cardFail?403:200,json:cardFail?{error:'Synthetic denied'}:u.pathname.endsWith('/api/card-oi')?{oi}:{revision:1,cardsEnabled:true,decisions:{BLOCK:'hide',ALLOW:'allow'},oi}});
    }
    if(u.pathname.endsWith('/api/coin-blocks'))return route.fulfill({json:{desktop:{desktop:{rules:{hide:bare(),mute:bare()}},cards:{settings:bare()}},mobile:{settings:bare()}}});
    if(u.pathname.endsWith('/api/status'))return route.fulfill({json:{blockedHistory:[]}});
    if(u.pathname.endsWith('/api/desktop-settings'))return route.fulfill({json:{history:[]}});
    if(u.pathname.includes('/api/'))return route.fulfill({status:401,json:{error:'Not used by this isolated test'}});
    if(u.pathname.endsWith('/manifest.webmanifest'))return route.fulfill({json:{}});
    if(u.pathname.endsWith('/notice.wav'))return route.fulfill({contentType:'audio/wav',body:'synthetic'});
    let rel=u.pathname.replace(/^\/radar\//,'');if(rel==='robot-push/'||rel==='push-test/')rel=rel==='push-test/'?'pwa-index.html':'robot-push/index.html';
    for(const base of [candidate,baseline]){const file=path.resolve(base,rel);if(file.startsWith(base+path.sep)&&fs.existsSync(file)&&fs.statSync(file).isFile()){const bytes=fs.readFileSync(file);loadedAssets[rel]=hash(bytes);return route.fulfill({contentType:rel.endsWith('.js')?'text/javascript':rel.endsWith('.css')?'text/css':rel.endsWith('.html')?'text/html':rel.endsWith('.svg')?'image/svg+xml':'image/png',body:bytes});}}
    if(!u.pathname.endsWith('favicon.ico'))unexpected.push(u.pathname);return route.fulfill({status:404,body:''});
   });
   const wait=fn=>page.waitForFunction(fn,null,{timeout:15000}),wake=()=>page.evaluate(()=>window.dispatchEvent(new Event('focus'))),refresh=()=>page.evaluate(()=>document.dispatchEvent(new Event('radar-rules-saved')));
   const ids=()=>page.locator('#feed > article').evaluateAll(nodes=>nodes.map(node=>node.dataset.id));
   const push=async()=>{await page.evaluate(data=>window.testPush(data),source);await wake();};
   const prefix=engineName+'-'+width;
   try{
    await page.goto('https://blocked.test/radar/robot-push/');await wait(()=>document.querySelector('#feed > [data-id="btc"]')&&document.querySelector('.bp-board>.bp-card')?.textContent.includes('871.90k'));
    assert.deepEqual(await ids(),['btc','muted']);assert.equal(await page.locator('#pinned > article').count(),0);assert.equal(await page.evaluate(()=>window.audioStarts),0);
    assert.equal(loadedAssets[cfg.bundle],cfg.stageHashes[cfg.bundle]);
    assert.equal(await page.locator('.bp-board>.bp-card').count(),1);
    assert.match(await page.locator('.bp-board .bp-leg-stats .bp-metric').filter({has:page.locator('span').filter({hasText:/^OI$/})}).first().getAttribute('title'),/双边.*50 万 USDT/);
    assert.equal(await page.locator('.bp-board [data-action="manage-rules"]').count(),1);
    await page.locator('.bp-board [data-action="copy-gc"]').click();await wait(()=>window.testCopied.length>0);assert(Object.keys(JSON.parse(await page.evaluate(()=>window.testCopied.at(-1)))).length>0);
    await page.locator('.bp-board [data-action="manage-rules"]').click();await page.locator('.bp-rule-result').filter({hasText:'已加载云端规则'}).waitFor();await page.getByRole('button',{name:'关闭币种规则',exact:true}).click();
    await page.locator('.bp-blocked-button').click();await page.locator('.bp-blocked-list .bp-card').waitFor();assert.match(await page.locator('.bp-blocked-list').innerText(),/BLOCK/);await page.keyboard.press('Escape');
    await page.locator('.rp-blocked-entry').click();await page.locator('.rp-blocked-list [data-message-id="unitree"]').waitFor();assert.equal(await page.locator('.rp-blocked-list [data-message-id="strong"]').count(),1);assert.equal(await page.locator('.rp-blocked-list [data-message-id="muted"]').count(),0);
    await page.screenshot({path:path.join(output,prefix+'-blocked.png')});
    source.messages.push(message('late-hidden','UNITREE','ordinary',Date.now()+10));await push();
    await wait(()=>document.querySelector('.rp-blocked-entry').textContent.includes('3'));
    assert.equal(await page.locator('.rp-blocked-list [data-message-id]').count(),2,'Open blocked viewer remains a fixed snapshot');
    await page.locator('.rp-blocked-dialog').getByRole('button',{name:'刷新',exact:true}).click();await page.locator('.rp-blocked-list [data-message-id="late-hidden"]').waitFor();
    await page.getByRole('button',{name:/^电脑历史/}).click();assert.match(await page.locator('.rp-blocked-list').innerText(),/没有.*历史/);await page.getByRole('button',{name:'关闭已屏蔽推送',exact:true}).click();
    const layout=await page.evaluate(()=>({width:innerWidth,docWidth:document.documentElement.scrollWidth,cardWidth:document.querySelector('.bp-board>.bp-card').getBoundingClientRect().width}));assert(layout.docWidth<=width+1);await page.screenshot({path:path.join(output,prefix+'-page.png')});
    hidden=false;await refresh();await page.locator('#feed > [data-id="unitree"]').waitFor();assert.equal(await page.locator('#pinned > [data-id="strong"]').count(),1);assert.equal(await page.evaluate(()=>window.audioStarts),0);
    await page.locator('#feed > [data-id="unitree"] .message-head').click();await page.locator('#message-detail[open]').waitFor();
    hidden=true;if(width<900)await page.evaluate(()=>{const e=new Event('touchstart',{bubbles:true});Object.defineProperty(e,'touches',{value:[{clientY:100}]});document.querySelector('#board').dispatchEvent(e);});
    assert.deepEqual(await page.evaluate(()=>{document.dispatchEvent(new Event('radar-rules-saved'));return {count:document.querySelectorAll('#feed > article,#pinned > article').length,detail:document.querySelector('#message-detail').open};}),{count:0,detail:false});
    if(width<900)await page.evaluate(()=>{const e=new Event('touchend',{bubbles:true});Object.defineProperty(e,'touches',{value:[]});document.querySelector('#board').dispatchEvent(e);});
    await page.locator('#feed > [data-id="btc"]').waitFor();
    source.messages.push(message('new-muted','PREDICT','ordinary',Date.now()+10));await push();await page.locator('#feed > [data-id="new-muted"]').waitFor();assert.equal(await page.evaluate(()=>window.audioStarts),0);
    source.messages.push(message('new-allowed','BTC','ordinary',Date.now()+10));await push();await page.locator('#feed > [data-id="new-allowed"]').waitFor();assert.equal(await page.evaluate(()=>window.audioStarts),1);
    await refresh();await page.locator('#feed > [data-id="btc"]').waitFor();assert.equal(await page.evaluate(()=>window.audioStarts),1);
    source.messages=source.messages.map(m=>m.id==='btc'?{...m,title:'R0 +0.4% | UNITREE | FF',body:'UNITREE changed content'}:m);await push();assert.equal(await page.locator('#feed > [data-id="btc"]').count(),0);
    desktopEnabled=false;await refresh();await wait(()=>document.querySelector('#empty').textContent.includes('已关闭'));assert.equal(await page.locator('#feed > article,#pinned > article').count(),0);assert.equal(await page.locator('.bp-board>.bp-card').count(),1);
    desktopEnabled=true;await refresh();await page.locator('#feed > [data-id="muted"]').waitFor();
    let release;gate=new Promise(resolve=>{release=resolve;});const before=apiCount;await refresh();const deadline=Date.now()+15000;while(apiCount===before&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,10));assert(apiCount>before,'Gated request started');
    assert.equal(await page.evaluate(()=>{localStorage.setItem('radar-settings-token','second');window.dispatchEvent(new StorageEvent('storage',{key:'radar-settings-token'}));return document.querySelectorAll('#feed > article').length;}),0);
    gate=null;release();await wake();await page.locator('#feed > [data-id="unitree"]').waitFor();assert.equal(await page.locator('#pinned > [data-id="strong"]').count(),1);
    fail=true;await refresh();assert.equal(await page.locator('#feed > article').count(),0);await page.locator('#empty').filter({hasText:'校验'}).waitFor();
    await page.evaluate(()=>{localStorage.removeItem('radar-settings-token');window.dispatchEvent(new StorageEvent('storage',{key:'radar-settings-token'}));});await page.locator('#feed > [data-id="unitree"]').waitFor();assert.equal(await page.locator('#pinned > [data-id="strong"]').count(),1);assert.equal(await page.evaluate(()=>window.audioStarts),1);
    source=structuredClone(original);hidden=true;fail=false;
    await page.goto('https://blocked.test/radar/push-test/');await wait(()=>document.querySelector('#feed > [data-id="btc"]')&&document.querySelector('.bp-board>.bp-card')?.textContent.includes('871.90k'));assert.deepEqual(await ids(),['btc','muted']);assert.equal(await page.locator('#pinned > article').count(),0);assert.equal(await page.evaluate(()=>window.audioStarts),0);
    assert.deepEqual(posts,[]);assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);assert.deepEqual(external,[]);
    results.push({engine:engineName,width,passed:true,layout,loadedAssets,checks:['actual deployed HTML and patched bundle','normal and pinned strong signal hidden','web-current blocked entry includes both','mute visible and silent','restore without replay','new allow sounds once','same-ID changed content cannot reuse proof','touch revocation and open-detail clear','identity switch and late request','403 clears','anonymous restores all','PWA entry','double-sided card OI','card manager and GC plain JSON','blocked cards retained','no overflow','zero POST and zero external traffic']});console.log(prefix+': PASS');
   }catch(e){await page.screenshot({path:path.join(output,prefix+'-failure.png')});results.push({engine:engineName,width,passed:false,error:e.stack,errors,unexpected,external,posts,loadedAssets});throw e;}
   finally{await context.close();report();}
  }}finally{await browser.close();}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
