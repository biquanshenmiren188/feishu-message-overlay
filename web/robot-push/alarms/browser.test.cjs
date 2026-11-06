// Synthetic browser/account/API fixtures only; no production credentials or notifications.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(process.env.RADAR_TASK_ROOT||'C:/Users/Admin/Documents/Codex/2026-11-06/bark');
const repo=path.join(root,'work/push'),candidate=path.join(root,'work/center-candidate/static');
const origin='https://radar-alarms.test';
const settings={notify_enabled:true,rows:4,notify_interval_seconds:60,min_percent:null,excluded_ranks:[],excluded_coins:[],excluded_modes:[],excluded_exchanges:[]};
const initial=()=>({revision:0,enabled:true,device:null,rules:[],events:[]});
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'}),results=[];
 try{
 for(const width of [1440,393,320]){
  const context=await browser.newContext({viewport:{width,height:width===1440?1000:852},reducedMotion:'reduce'});
  const page=await context.newPage(),errors=[],writes=[],states={a:initial(),b:initial()};let failNext=false,scopeOnly=false;
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  await context.addInitScript(()=>localStorage.setItem('radar-settings-token','synthetic_token_a_123456789'));
  await context.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname,profile=req.headers().authorization?.includes('_b_')?'b':'a';
   const json=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
   if(url.origin!==origin)return route.abort();
   if(scopeOnly&&['/radar/','/radar/position-limits/','/radar/robot-push/','/radar/push-test/'].includes(p))return route.fulfill({contentType:'text/html',body:'<!doctype html><header class="topbar compact-header"><strong>雷达</strong></header><nav class="site-nav"><a>全市场费率</a></nav><div class="feed-tools"></div><script type="module" src="/radar/robot-push/shared-account.js?v=20261106-2"></script>'});
   if(p.startsWith('/radar/push-test/api/')||p.startsWith('/radar/push-center-api/')){
    const kind=p.split('/').at(-1);
    if(kind==='status')return json({profileId:profile,revision:0,publicKey:'synthetic',settings,subscribed:false,blockedHistory:[]});
    if(kind==='binding')return json({pushCode:profile==='a'?'12345688':'12345699'});
    if(kind==='pair')return json({token:'synthetic_token_b_123456789'});
    if(kind==='desktop-settings')return json({revision:0,connected:true,desktop:{action:'mute',settings,rules:{mute:settings,hide:settings}},cards:{action:'hide',settings},history:[]});
    if(kind==='coin-blocks')return json({revision:0,desktop:{action:'mute',settings,rules:{mute:settings,hide:settings}},cards:{action:'hide',settings},mobile:{settings,revision:0},operations:[]});
    return json({});
   }
   if(p.startsWith('/radar/alarms-api/')){
    if(p.endsWith('/state'))return json(states[profile]);
    if(p.endsWith('/catalog'))return json({items:['BTCUSDT','ETHUSDT','1000RATSUSDT'].map((symbol,i)=>({symbol,base:symbol.slice(0,-4),unit:symbol.slice(0,-4),last:['76000','2300','0.03'][i],mark:['76001','2301','0.0301'][i],observedAt:Date.now()/1000}))});
    if(p.endsWith('/change')){
     const b=req.postDataJSON();writes.push(b);
     if(failNext){failNext=false;return route.abort('failed');}
     const s=states[profile];if(b.revision!==s.revision)return json({error:'设置已更新'},409);
     if(b.action==='save'){const id=b.id||String(s.revision+1).padStart(32,'a');s.rules=s.rules.filter(r=>r.id!==id);s.rules.push({...b.rule,id,state:{status:'watching',sampleAt:Date.now()/1000,price:'76000'}});}
     if(b.action==='toggle')s.rules.find(r=>r.id===b.id).enabled=b.enabled;
     if(b.action==='delete')s.rules=s.rules.filter(r=>r.id!==b.id);
     if(b.action==='enabled')s.enabled=b.enabled;
     if(b.action==='bind')s.device={label:b.label,suffix:'000001'};
     if(b.action==='unbind')s.device=null;
     s.revision++;return json({ok:true,revision:s.revision});
    }
   }
   const aliases={'/radar/radar-ui-v2.css':'radar-ui-v2.css','/radar/radar-brand-treasure-v2.svg':'radar-brand-treasure-v2.svg','/radar/robot-push/notification-settings.css':'notification-settings.css'};
   let file=aliases[p]?path.join(root,'work/baseline',aliases[p]):path.join(candidate,p.replace(/^\/radar\//,''));
   if(p.endsWith('/'))file=path.join(file,'index.html');
   try{await fs.access(file);}catch{file=path.join(repo,'web',p.replace(/^\/radar\//,''));if(p.endsWith('/'))file=path.join(file,'index.html');}
   try{const body=await fs.readFile(file),ext=path.extname(file);return route.fulfill({contentType:({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'})[ext]||'application/octet-stream',body});}catch{return route.fulfill({status:404,body:''});}
  });
  await page.goto(origin+'/radar/robot-push/alarms/');await page.waitForFunction(()=>!document.querySelector('#add-alarm').disabled);
  await page.locator('.radar-account-entry').waitFor();assert.match(await page.locator('.radar-account-entry').innerText(),/推送中心[\s\S]*已连接/);assert.match(await page.locator('.radar-account-entry').getAttribute('href'),/center\/$/);
  assert.equal(await page.locator('nav.site-nav a').count(),7);
  const navFits=await page.evaluate(()=>{const n=document.querySelector('.site-nav').getBoundingClientRect();return [...document.querySelectorAll('.site-nav>a')].every(a=>a.getBoundingClientRect().bottom<=n.bottom+1)&&document.querySelector('main').getBoundingClientRect().top>=n.bottom;});assert.equal(navFits,true,'navigation overlaps content '+width);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);assert.equal(overflow,false,'page overflow '+width);
  await fs.mkdir(path.join(root,'outputs/verification'),{recursive:true});
  await page.screenshot({path:path.join(root,`outputs/verification/alarms-empty-${width}.png`),fullPage:true});
  await page.click('#add-alarm');await page.fill('[name=symbol]','BTCUSDT');await page.fill('[name=target]','80000');await page.selectOption('[name=repeat]','true');await page.selectOption('[name=hold]','3');
  await page.fill('[name=note]','突破观察');assert.match(await page.locator('#rule-preview').innerText(),/80000/);
  await page.screenshot({path:path.join(root,`outputs/verification/alarm-editor-${width}.png`),fullPage:true});
  await page.click('#save-alarm');await page.waitForFunction(()=>!document.querySelector('#alarm-editor').open);
  assert.equal(states.a.rules.length,1);assert.equal(states.a.rules[0].hold,3);
  await page.locator('[data-action=copy]').click();await page.fill('[name=target]','82000');await page.click('#save-alarm');await page.waitForFunction(()=>!document.querySelector('#alarm-editor').open);assert.equal(states.a.rules.length,2);
  await page.locator('[data-action=toggle]').first().click();await page.waitForTimeout(100);assert.equal(states.a.rules[0].enabled,false);
  await page.selectOption('#alarm-filter','paused');assert.equal(await page.locator('.alarm-row').count(),1);await page.selectOption('#alarm-filter','all');
  await page.click('#bind-device');await page.fill('#bark-form [name=key]','synthetic_device_12345');await page.fill('#bark-form [name=label]','我的 iPhone');await page.click('#save-bark');await page.waitForFunction(()=>!document.querySelector('#bark-editor').open);assert.equal(states.a.device.label,'我的 iPhone');
  await page.screenshot({path:path.join(root,`outputs/verification/alarms-list-${width}.png`),fullPage:true});
  // Unknown write response must retry the original immutable request id/body.
  failNext=true;await page.locator('[data-action=toggle]').first().click();await page.locator('#pending-action').waitFor({state:'visible'});const failed=writes.at(-1);await page.click('#retry-action');await page.waitForFunction(()=>document.querySelector('#pending-action').hidden);assert.deepEqual(writes.at(-1),failed);
  await page.evaluate(()=>window.RadarAccount.open());assert.match(await page.locator('#ns-bound-code').innerText(),/12345688/);
  await page.screenshot({path:path.join(root,`outputs/verification/push-code-${width}.png`),fullPage:true});
  await page.click('#ns-switch-open');await page.fill('#ns-switch-code','12345699');await page.click('#ns-switch-submit');await page.waitForFunction(()=>document.querySelector('#ns-bound-code').textContent==='12345699');await page.click('.ra-close');
  await page.waitForFunction(()=>document.querySelector('#alarm-count').textContent==='0');assert.equal(states.a.rules.length,2);assert.equal(states.b.rules.length,0);assert.equal(states.b.device,null);
  await page.goto(origin+'/radar/robot-push/settings/');
  await page.waitForFunction(()=>document.querySelector('.ra-entry-status')?.textContent==='已连接');
  assert.equal(await page.locator('#mobile-account').count(),0);
  await page.evaluate(()=>window.RadarAccount.open());await page.locator('#ns-switch-open').waitFor({state:'visible'});await page.click('.ra-close');
  await page.screenshot({path:path.join(root,`outputs/verification/settings-account-${width}.png`),fullPage:true});
  assert.deepEqual(errors,[],'browser errors '+width);
  scopeOnly=true;
  for(const scope of ['/radar/','/radar/position-limits/','/radar/robot-push/','/radar/push-test/']){
   await page.goto(origin+scope);await page.locator('.radar-seven-nav').waitFor();
   assert.equal(await page.locator('.radar-account-entry').count(),scope.includes('push')?1:0,'account entry scope '+scope);if(scope.includes('push')){await page.waitForFunction(()=>document.querySelector('.ra-entry-status')?.textContent==='已连接');}
   if(scope.includes('push')){await page.locator('#notification-settings').waitFor({state:'attached'});assert.equal(await page.locator('#notification-settings').count(),1);}
  }
  assert.deepEqual(errors,[],'scope browser errors '+width);
  results.push({width,passed:true,checks:['layout','create','copy','pause','filter','bind','immutable-retry','full-code','switch-isolation'],writes:writes.length});
  await context.close();
 }
 await fs.writeFile(path.join(root,'outputs/verification/browser-results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
