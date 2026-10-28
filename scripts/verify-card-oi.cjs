/* Isolated actual-production-candidate test. All streams and policies are synthetic. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const runtime=path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {chromium,webkit}=createRequire(runtime)('playwright');
const candidate=path.resolve(process.argv[2]||'../card-oi-candidate-v2'),baseline=path.resolve('../card-oi-live-baseline-v2'),output=path.resolve(process.argv[3]||'../card-oi-browser-results-v2');
fs.mkdirSync(output,{recursive:true});
const cfg=JSON.parse(fs.readFileSync(path.join(candidate,'plan.json')));
const bare=()=>({excluded_coins:[],advanced:{coins:[]}});
(async()=>{
 const results=[];
 for(const [engineName,engine]of [['chromium',chromium],['webkit',webkit]]){
  const browser=await engine.launch({headless:true});const context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'}),page=await context.newPage();
  let policy={revision:1,cardsEnabled:true,decisions:{BLOCK:'hide',ALLOW:'allow'}},status=200;const errors=[],posts=[],unexpected=[];page.on('pageerror',e=>errors.push(e.message));
  await context.addInitScript(()=>{
   localStorage.setItem('radar-settings-token','isolated-fixture');
   window.testPorts=[];window.testCards=['BLOCK','ALLOW'];window.testRetired=false;window.testStamp=Date.now();
   window.testCard=asset=>({id:asset,pair:asset,asset,strategy:'FF',enteredAt:new Date(Date.now()-6000).toISOString(),updatedAt:new Date().toISOString(),validUntil:new Date(Date.now()+120000).toISOString(),v2Residual:{level:1,bps:55},details:{netBps:12,marketBps:30,p75Bps:40,indexBps:0,legs:[{exchange:'BINANCE',symbol:asset+'USDT',rate:.0001,hours:4,oi:371600,volume:3000000},{exchange:'GATE',symbol:asset+'_USDT',rate:.0002,hours:4,oi:371600,volume:3000000}],transferWallets:[]},radarUrl:'https://leida.shenmiren.work/radar/?symbol='+asset});
   window.testData=name=>name==='feed'?{messages:[],pinned:null}:{status:'connected',receivedAt:new Date().toISOString(),snapshot:{sampledAt:new Date(++window.testStamp).toISOString(),complete:true,active:window.testRetired?[]:window.testCards.map(window.testCard),retained:window.testRetired?window.testCards.map(asset=>({card:window.testCard(asset),expiredAt:new Date(Date.now()-31000).toISOString()})):[],retentionSeconds:30}};
   window.SharedWorker=class{constructor(){const port={onmessage:null,start(){queueMicrotask(()=>port.onmessage?.({data:{type:'ready'}}));},postMessage({channels=[]}){port.channels=channels;for(const name of channels)queueMicrotask(()=>port.onmessage?.({data:{type:'data',name,data:window.testData(name)}}));},close(){}};this.port=port;window.testPorts.push(port);}};
   window.testPush=()=>{window.testStamp=Math.max(window.testStamp,Date.now());for(const port of window.testPorts)for(const name of port.channels||[])port.onmessage?.({data:{type:'data',name,data:window.testData(name)}});};
  });
  let amount=871898,missing=false;
  await context.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());if(u.origin!=='https://blocked.test')return route.abort();
   if(req.method()!=='GET'){posts.push(u.pathname);return route.fulfill({status:403,json:{error:'No writes allowed'}});}
   if(u.pathname.endsWith('/api/card-decisions')||u.pathname.endsWith('/api/card-oi')){
    const n=Date.now(),oi=Object.fromEntries(['BLOCK','ALLOW'].map(id=>[id,Object.fromEntries(['left','right'].map((side,i)=>[side,{exchange:i?'gate':'binance',market:'perp',threshold:50,checkedAt:n,time:n-1000,expiresAt:n+299000,basis:'double-v1',status:missing?'missing':'ok',value:id==='BLOCK'?371600:amount}]))]));
    if(u.pathname.endsWith('/api/card-oi'))return route.fulfill({json:{oi:Object.fromEntries(Object.entries(oi).map(([id,sides])=>[id,Object.fromEntries(Object.entries(sides).map(([side,p])=>[side,{...p,threshold:null}]))]))}});
    return route.fulfill({status,json:status===200?{...policy,oi}:{error:'Test unauthorized'}});
   }
   if(u.pathname.endsWith('/api/status'))return route.fulfill({json:{blockedHistory:[]}});
   if(u.pathname.endsWith('/api/desktop-settings'))return route.fulfill({json:{history:[]}});
   if(u.pathname.endsWith('/api/coin-blocks'))return route.fulfill({json:{desktop:{desktop:{rules:{hide:bare(),mute:bare()}},cards:{settings:bare()}},mobile:{settings:bare()}}});
   if(u.pathname.includes('/api/'))return route.fulfill({status:401,json:{error:'Not used by this read-only test'}});
   if(u.pathname.endsWith('/manifest.webmanifest'))return route.fulfill({json:{}});
   let rel=u.pathname.replace(/^\/radar\//,'');if(rel==='robot-push/'||rel==='push-test/')rel=rel==='push-test/'?'pwa-index.html':'robot-push/index.html';
   for(const base of [candidate,baseline]){const file=path.resolve(base,rel);if(file.startsWith(base+path.sep)&&fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({contentType:rel.endsWith('.js')?'text/javascript':rel.endsWith('.css')?'text/css':rel.endsWith('.html')?'text/html':rel.endsWith('.svg')?'image/svg+xml':'image/png',body:fs.readFileSync(file)});}
   if(!u.pathname.endsWith('favicon.ico'))unexpected.push(u.pathname);return route.fulfill({status:404,body:''});
  });
  const wait=fn=>page.waitForFunction(fn,null,{timeout:10000});
  const wake=()=>page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  const oi=page.locator('.bp-board .bp-leg-stats .bp-metric').filter({has:page.locator('span').filter({hasText:/^OI$/})});
  try{
   await page.goto('https://blocked.test/radar/robot-push/');await wait(()=>document.querySelector('.bp-board .bp-card')?.textContent.includes('871.90k'));
   assert.equal(await page.locator('.bp-board>.bp-card').count(),1);assert.doesNotMatch(await page.locator('.bp-board').innerText(),/371.60k/);
   assert.match(await oi.first().getAttribute('title'),/50 万 USDT/);assert.match(await oi.first().getAttribute('title'),/双边/);
   await page.locator('.bp-blocked-button').click();await wait(()=>document.querySelector('.bp-blocked-list')?.textContent.includes('371.60k'));
   assert.match(await page.locator('.bp-blocked-list').innerText(),/BLOCK/);await page.keyboard.press('Escape');
   const layouts=[];
   for(const width of [1440,393,320]){
    await page.setViewportSize({width,height:width===1440?1000:852});
    const measured=await page.evaluate(()=>({width:innerWidth,docWidth:document.documentElement.scrollWidth,cardWidth:document.querySelector('.bp-board .bp-card').getBoundingClientRect().width}));
    assert(measured.docWidth<=width+1);layouts.push(measured);await page.locator('.bp-board>.bp-card').screenshot({path:path.join(output,engineName+'-'+width+'.png')});
   }
   amount=500000;await wake();await wait(()=>document.querySelector('.bp-board .bp-card')?.textContent.includes('500.00k'));assert.equal(await page.locator('.bp-board>.bp-card').count(),1);
   amount=499999;policy={...policy,decisions:{BLOCK:'hide',ALLOW:'hide'}};await wake();await wait(()=>document.querySelectorAll('.bp-board>.bp-card').length===0);
   await page.locator('.bp-blocked-button').click();await wait(()=>document.querySelectorAll('.bp-blocked-list .bp-card').length===2);await page.keyboard.press('Escape');
   missing=true;policy={...policy,decisions:{BLOCK:'hide',ALLOW:'allow'}};await wake();await wait(()=>document.querySelectorAll('.bp-board>.bp-card').length===1);assert.equal(await oi.first().locator('strong').innerText(),'—');assert.match(await oi.first().getAttribute('title'),/缺失或过期/);
   status=403;await wake();await wait(()=>document.querySelectorAll('.bp-board>.bp-card').length===0);
   missing=false;amount=871898;await page.evaluate(()=>{localStorage.removeItem('radar-settings-token');window.dispatchEvent(new Event('storage'));});await wait(()=>document.querySelectorAll('.bp-board>.bp-card').length===2&&document.querySelector('.bp-board')?.textContent.includes('871.90k'));assert.doesNotMatch(await page.locator('.bp-board').innerText(),/源 OI/);
   status=200;missing=false;amount=871898;
   await page.goto('https://blocked.test/radar/push-test/');await wait(()=>document.querySelector('.bp-board .bp-card')?.textContent.includes('871.90k'));
   assert.deepEqual(posts,[]);assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);
   results.push({engine:engineName,passed:true,layouts,checks:['exact backend snapshot replaces unrelated raw OI','threshold and basis available','blocked preview same proof','three layouts','500k equality allows','499999 hide','missing allow shows dash','denied clears cards','guest double OI without account data','PWA','zero writes']});console.log(engineName+': PASS');
  }catch(e){await page.screenshot({path:path.join(output,engineName+'-failure.png')});results.push({engine:engineName,passed:false,error:e.stack,errors,unexpected,posts});throw e;}
  finally{await context.close();await browser.close();fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({candidate,stageHashes:cfg.stageHashes,results},null,2));}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
