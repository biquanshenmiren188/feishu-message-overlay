/* Isolated actual-production-candidate test. All streams and policies are synthetic. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const runtime=path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {chromium,webkit}=createRequire(runtime)('playwright');
const candidate=path.resolve(process.argv[2]||'../blocked-pushes-candidate'),baseline=path.resolve('../blocked-pushes-live-baseline'),output=path.resolve(process.argv[3]||'../blocked-pushes-browser-results');
fs.mkdirSync(output,{recursive:true});
const cfg=JSON.parse(fs.readFileSync(path.join(candidate,'deployment.json')));
const bare=()=>({excluded_coins:[],advanced:{coins:[]}});
(async()=>{
 const results=[];
 for(const [engineName,engine]of [['chromium',chromium],['webkit',webkit]]){
  const browser=await engine.launch({headless:true});const context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'}),page=await context.newPage();
  let policy={revision:1,cardsEnabled:true,decisions:{BLOCK:'hide',ALLOW:'allow'}},status=200;const errors=[],posts=[],unexpected=[];page.on('pageerror',e=>errors.push(e.message));
  await context.addInitScript(()=>{
   localStorage.setItem('radar-settings-token','isolated-fixture');
   window.testPorts=[];window.testCards=['BLOCK','ALLOW'];window.testRetired=false;window.testStamp=Date.now();
   window.testCard=asset=>({id:asset,pair:asset,asset,strategy:'FF',enteredAt:new Date(Date.now()-6000).toISOString(),updatedAt:new Date().toISOString(),validUntil:new Date(Date.now()+120000).toISOString(),v2Residual:{level:1,bps:55},details:{netBps:12,marketBps:30,p75Bps:40,indexBps:0,legs:[{exchange:'BINANCE',symbol:asset+'USDT',rate:.0001,hours:4,oi:2000000,volume:3000000},{exchange:'GATE',symbol:asset+'_USDT',rate:.0002,hours:4,oi:2000000,volume:3000000}],transferWallets:[]},radarUrl:'https://leida.shenmiren.work/radar/?symbol='+asset});
   window.testData=name=>name==='feed'?{messages:[],pinned:null}:{status:'connected',receivedAt:new Date().toISOString(),snapshot:{sampledAt:new Date(++window.testStamp).toISOString(),complete:true,active:window.testRetired?[]:window.testCards.map(window.testCard),retained:window.testRetired?window.testCards.map(asset=>({card:window.testCard(asset),expiredAt:new Date(Date.now()-31000).toISOString()})):[],retentionSeconds:30}};
   window.SharedWorker=class{constructor(){const port={onmessage:null,start(){queueMicrotask(()=>port.onmessage?.({data:{type:'ready'}}));},postMessage({channels=[]}){port.channels=channels;for(const name of channels)queueMicrotask(()=>port.onmessage?.({data:{type:'data',name,data:window.testData(name)}}));},close(){}};this.port=port;window.testPorts.push(port);}};
   window.testPush=()=>{window.testStamp=Math.max(window.testStamp,Date.now());for(const port of window.testPorts)for(const name of port.channels||[])port.onmessage?.({data:{type:'data',name,data:window.testData(name)}});};
  });
  const row=(id,channel='desktop',action='hide')=>({id,channel,action,at:1792912000,messageAt:1792911900,coin:'FIXTURE'+id,mode:'FF',rank:'R1',value:'+0.5%',buy:'BG',sell:'GT',reasons:['币种已屏蔽','仅作隔离测试'],revision:2});
  let desktop={history:[row('a'),row('mute','desktop','mute'),row('card','cards')]},mobile={blockedHistory:[row('m')]},apiStatus=200,late=null;
  await context.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());if(u.origin!=='https://blocked.test')return route.abort();
   if(req.method()!=='GET'){posts.push(u.pathname);return route.fulfill({status:403,json:{error:'No writes allowed'}});}
   if(u.pathname.endsWith('/api/card-decisions'))return route.fulfill({status,json:status===200?policy:{error:'Test unauthorized'}});
   if(u.pathname.endsWith('/api/coin-blocks'))return route.fulfill({json:{desktop:{desktop:{rules:{hide:bare(),mute:bare()}},cards:{settings:bare()}},mobile:{settings:bare()}}});
   if(u.pathname.endsWith('/api/desktop-settings')||u.pathname.endsWith('/api/status')){
    const payload=u.pathname.endsWith('/api/status')?mobile:desktop, code=apiStatus;
    if(late)await late;
    return route.fulfill({status:code,json:code===200?payload:{error:'fixture denied'}}).catch(()=>{});
   }
   if(u.pathname.includes('/api/'))return route.fulfill({status:401,json:{error:'Not used by this read-only test'}});
   if(u.pathname.endsWith('/manifest.webmanifest'))return route.fulfill({json:{}});
   let rel=u.pathname.replace(/^\/radar\//,'');if(rel==='robot-push/'||rel==='push-test/')rel=rel==='push-test/'?'pwa-index.html':'robot-push/index.html';
   for(const base of [candidate,baseline]){const file=path.resolve(base,rel);if(file.startsWith(base+path.sep)&&fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({contentType:rel.endsWith('.js')?'text/javascript':rel.endsWith('.css')?'text/css':rel.endsWith('.html')?'text/html':rel.endsWith('.svg')?'image/svg+xml':'image/png',body:fs.readFileSync(file)});}
   if(!u.pathname.endsWith('favicon.ico'))unexpected.push(u.pathname);return route.fulfill({status:404,body:''});
  });
  const wait=fn=>page.waitForFunction(fn,null,{timeout:10000});
  const open=async()=>{await page.locator('.rp-blocked-entry').click();await page.locator('.rp-blocked-dialog[open]').waitFor();await wait(()=>!document.querySelector('.rp-blocked-controls button:last-child').disabled);};
  const close=async()=>{await page.getByRole('button',{name:'关闭已屏蔽推送',exact:true}).click();await page.locator('.rp-blocked-dialog').waitFor({state:'detached'});};
  const wake=()=>page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  try{
   await page.goto('https://blocked.test/radar/robot-push/');
   await wait(()=>document.querySelector('.rp-blocked-entry')?.textContent==='已屏蔽 2 条');
   await wait(()=>document.querySelector('.bp-blocked-button')?.textContent==='已屏蔽 1 张');
   await open();await wait(()=>document.querySelectorAll('.rp-blocked-message').length===1);
   assert.match(await page.locator('.rp-blocked-message').innerText(),/FIXTUREa/);
   assert.doesNotMatch(await page.locator('.rp-blocked-list').innerText(),/FIXTUREmute|FIXTUREcard/);
   await page.getByRole('button',{name:'手机推送 1',exact:true}).click();assert.match(await page.locator('.rp-blocked-message').innerText(),/FIXTUREm/);
   await page.keyboard.press('Escape');await page.locator('.rp-blocked-dialog').waitFor({state:'detached'});
   assert(await page.locator('.rp-blocked-entry').evaluate(e=>e===document.activeElement));
   const layouts=[];
   for(const width of [1440,393,320]){
    await page.setViewportSize({width,height:width===1440?1000:852});await open();
    const measured=await page.evaluate(()=>{const d=document.querySelector('.rp-blocked-dialog'),b=document.querySelector('.rp-blocked-entry');return {width:innerWidth,docWidth:document.documentElement.scrollWidth,dialogWidth:d.clientWidth,dialogContent:d.scrollWidth,buttonHeight:b.getBoundingClientRect().height};});
    assert(measured.docWidth<=width+1);assert(measured.dialogContent<=measured.dialogWidth+1);assert(measured.buttonHeight>=43);layouts.push(measured);
    await page.screenshot({path:path.join(output,engineName+'-'+width+'.png')});await close();
   }
   await open();apiStatus=403;await wake();await wait(()=>document.querySelector('.rp-blocked-status')?.textContent.includes('连接已失效'));
   assert.equal(await page.locator('.rp-blocked-message').count(),0);assert.equal(await page.locator('.rp-blocked-entry').innerText(),'已屏蔽推送');
   apiStatus=200;mobile={blockedHistory:[]};await page.getByRole('button',{name:'刷新',exact:true}).click();await wait(()=>document.querySelector('.rp-blocked-empty'));
   desktop={history:[row('<img onerror=alert(1)>')]};await page.getByRole('button',{name:'电脑推送 1',exact:true}).click();await page.getByRole('button',{name:'刷新',exact:true}).click();
   await wait(()=>document.querySelector('.rp-blocked-message')?.textContent.includes('<img'));assert.equal(await page.locator('.rp-blocked-message img').count(),0);
   await close();let release;late=new Promise(r=>release=r);await wake();
   desktop={history:[]};mobile={blockedHistory:[]};
   await page.evaluate(()=>{localStorage.setItem('radar-settings-token','fixture-second');document.dispatchEvent(new Event('radar-profile-changing'));window.dispatchEvent(new Event('storage'));});
   release();late=null;
   await wake();await wait(()=>document.querySelector('.rp-blocked-entry')?.textContent==='已屏蔽 0 条');await open();assert.equal(await page.locator('.rp-blocked-message').count(),0);
   await page.evaluate(()=>{localStorage.removeItem('radar-settings-token');window.dispatchEvent(new Event('storage'));});await page.locator('.rp-blocked-dialog').waitFor({state:'detached'});assert(await page.locator('.rp-blocked-entry').isDisabled());
   desktop={history:[row('pwa')]};await page.goto('https://blocked.test/radar/push-test/');await wait(()=>document.querySelector('.rp-blocked-entry')?.textContent==='已屏蔽 1 条');await open();
   await page.getByRole('button',{name:'电脑推送 1',exact:true}).click();assert.match(await page.locator('.rp-blocked-message').innerText(),/FIXTUREpwa/);
   await page.evaluate(()=>{document.dispatchEvent(new Event('radar-profile-changing'));});await page.locator('.rp-blocked-dialog').waitFor({state:'detached'});
   assert.deepEqual(posts,[]);assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);
   results.push({engine:engineName,passed:true,layouts,checks:['desktop/mobile channels','mute/cards excluded','Escape/focus','three layouts','403 clears records without zero claim','empty channel','XSS inert','late identity response discarded','unbind clears dialog','PWA entry','profile change closes dialog','card preview preserved','zero writes']});console.log(engineName+': PASS');
  }catch(e){await page.screenshot({path:path.join(output,engineName+'-failure.png')});results.push({engine:engineName,passed:false,error:e.stack,errors,unexpected,posts});throw e;}
  finally{await context.close();await browser.close();fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({candidate,stageHashes:cfg.stageHashes,results},null,2));}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
