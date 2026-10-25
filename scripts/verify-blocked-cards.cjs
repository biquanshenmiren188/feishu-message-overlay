/* Isolated actual-production-candidate test. All streams and policies are synthetic. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const runtime=path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {chromium,webkit}=createRequire(runtime)('playwright');
const candidate=path.resolve(process.argv[2]||'../blocked-candidate'),baseline=path.resolve('../blocked-live-baseline'),output=path.resolve(process.argv[3]||'../blocked-browser-results');
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
  await context.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());if(u.origin!=='https://blocked.test')return route.abort();
   if(req.method()!=='GET'){posts.push(u.pathname);return route.fulfill({status:403,json:{error:'No writes allowed'}});}
   if(u.pathname.endsWith('/api/card-decisions'))return route.fulfill({status,json:status===200?policy:{error:'Test unauthorized'}});
   if(u.pathname.endsWith('/api/coin-blocks'))return route.fulfill({json:{desktop:{desktop:{rules:{hide:bare(),mute:bare()}},cards:{settings:bare()}},mobile:{settings:bare()}}});
   if(u.pathname.includes('/api/'))return route.fulfill({status:401,json:{error:'Not used by this read-only test'}});
   if(u.pathname.endsWith('/manifest.webmanifest'))return route.fulfill({json:{}});
   let rel=u.pathname.replace(/^\/radar\//,'');if(rel==='robot-push/'||rel==='push-test/')rel=rel==='push-test/'?'pwa-index.html':'robot-push/index.html';
   for(const base of [candidate,baseline]){const file=path.resolve(base,rel);if(file.startsWith(base+path.sep)&&fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({contentType:rel.endsWith('.js')?'text/javascript':rel.endsWith('.css')?'text/css':rel.endsWith('.html')?'text/html':rel.endsWith('.svg')?'image/svg+xml':'image/png',body:fs.readFileSync(file)});}
   if(!u.pathname.endsWith('favicon.ico'))unexpected.push(u.pathname);return route.fulfill({status:404,body:''});
  });
  const wake=async()=>{await page.evaluate(()=>window.dispatchEvent(new Event('focus')));};
  const wait=fn=>page.waitForFunction(fn,null,{timeout:8000});
  const open=async()=>{await page.locator('.bp-blocked-button').click();await page.locator('.bp-blocked-dialog[open]').waitFor();};
  const close=async()=>{await page.getByRole('button',{name:'关闭已屏蔽卡片',exact:true}).click();await page.locator('.bp-blocked-dialog').waitFor({state:'detached'});};
  try{
   await page.goto('https://blocked.test/radar/robot-push/');await wait(()=>document.querySelector('.bp-blocked-button')?.textContent==='已屏蔽 1 张'&&!document.querySelector('.bp-blocked-button').disabled);
   assert.equal(await page.locator('.bp-board>.bp-card').count(),1);await open();
   assert.equal(await page.locator('.bp-blocked-list .bp-card').count(),1);assert.equal(await page.locator('.bp-blocked-list .bp-name h2').innerText(),'BLOCK');
   assert.equal(await page.locator('.bp-blocked-list .bp-age').innerText(),'已屏蔽');assert.match(await page.locator('.bp-blocked-reason').innerText(),/本方案规则屏蔽/);assert.equal(await page.locator('.bp-board>.bp-card').count(),1);
   await page.locator('.bp-blocked-list [data-action="manage-rules"]').click();await page.locator('.bp-rule-result').filter({hasText:'已加载云端规则'}).waitFor();await page.keyboard.press('Escape');await page.locator('.bp-rule-dialog').waitFor({state:'detached'});
   await page.keyboard.press('Escape');await page.locator('.bp-blocked-dialog').waitFor({state:'detached'});assert.equal(await page.locator('.bp-blocked-button').evaluate(e=>e===document.activeElement),true);
   const layouts=[];
   for(const width of [1440,393,320]){
    await page.setViewportSize({width,height:width===1440?1000:852});await open();
    const measured=await page.evaluate(()=>{const d=document.querySelector('.bp-blocked-dialog'),b=document.querySelector('.bp-blocked-button');return {width:innerWidth,docWidth:document.documentElement.scrollWidth,dialogWidth:d.clientWidth,dialogContent:d.scrollWidth,buttonHeight:b.getBoundingClientRect().height,cardWidth:d.querySelector('.bp-card').getBoundingClientRect().width};});
    assert(measured.docWidth<=width+1);assert(measured.dialogContent<=measured.dialogWidth+1);assert(measured.buttonHeight>=43);layouts.push(measured);
    await page.screenshot({path:path.join(output,engineName+'-'+width+'.png')});await close();
   }
   await open();policy={...policy,cardsEnabled:false};await wake();await wait(()=>document.querySelectorAll('.bp-blocked-list .bp-card').length===2);assert.match(await page.locator('.bp-blocked-reason').first().innerText(),/接收已关闭/);
   policy={...policy,cardsEnabled:true,decisions:{BLOCK:'allow',ALLOW:'allow'}};await wake();await wait(()=>document.querySelector('.bp-blocked-help')?.textContent.includes('当前没有'));assert.equal(await page.locator('.bp-blocked-list .bp-card').count(),0);assert.equal(await page.locator('.bp-board>.bp-card').count(),2);
   policy={...policy,decisions:{BLOCK:'hide',ALLOW:'allow'}};await wake();await wait(()=>document.querySelectorAll('.bp-blocked-list .bp-card').length===1);
   status=403;await wake();await wait(()=>document.querySelector('.bp-blocked-help')?.textContent.includes('尚未确认'));assert.equal(await page.locator('.bp-blocked-list .bp-card').count(),0);assert.equal(await page.locator('.bp-blocked-button').isDisabled(),true);
   status=200;await wake();await wait(()=>document.querySelectorAll('.bp-blocked-list .bp-card').length===1);
   await page.evaluate(()=>{localStorage.setItem('radar-settings-token','different-fixture');window.dispatchEvent(new Event('storage'));});await page.locator('.bp-blocked-dialog').waitFor({state:'detached'});
   await wait(()=>!document.querySelector('.bp-blocked-button').disabled);await open();await page.evaluate(()=>{window.testRetired=true;window.testPush();});await wait(()=>document.querySelectorAll('.bp-blocked-list .bp-card').length===0);assert.equal(await page.locator('.bp-blocked-button').innerText(),'已屏蔽 0 张');await close();
   await page.evaluate(()=>{localStorage.removeItem('radar-settings-token');window.dispatchEvent(new Event('storage'));});await wait(()=>document.querySelector('.bp-blocked-button').hidden);
   await page.goto('https://blocked.test/radar/push-test/');await wait(()=>document.querySelector('.bp-blocked-button')?.textContent==='已屏蔽 1 张'&&!document.querySelector('.bp-blocked-button').disabled);await open();assert.equal(await page.locator('.bp-blocked-list .bp-name h2').innerText(),'BLOCK');
   assert.deepEqual(posts,[],'Preview must never write rules or send notifications');assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);
   results.push({engine:engineName,passed:true,layouts,checks:['blocked preview and unchanged main list','native Escape/focus and nested manager','three layouts','receive-off','unblock refresh','denied clears preview','identity reset','expiry removes without restart','guest mode','PWA entry','zero writes']});console.log(engineName+': PASS');
  }catch(e){await page.screenshot({path:path.join(output,engineName+'-failure.png')});results.push({engine:engineName,passed:false,error:e.stack,errors,unexpected,posts});throw e;}
  finally{await context.close();await browser.close();fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({candidate,bundle:cfg.bundle,results},null,2));}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
