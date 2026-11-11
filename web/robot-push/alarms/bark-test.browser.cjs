// Synthetic API only: never sends a notification or uses production credentials.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const assets=process.env.ALARM_ASSETS||__dirname;
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{for(const width of [1440,393,320]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];
  let state={revision:1,enabled:true,device:null,rules:[],events:[{id:'old-test',ruleId:'test',at:1700000000,status:'accepted'}]},writes=[],fail=false,reject=false,detailReads=0;
  await page.addInitScript(()=>localStorage.setItem('radar-settings-token','synthetic-a'));
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;
   const json=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
   if(p.endsWith('/state'))return json(state);
   if(p.endsWith('/history')){const n=Number(new URL(req.url()).searchParams.get('page')||1);return json({items:Array.from({length:n===3?5:20},(_,i)=>({id:String((n-1)*20+i),title:'BTCUSDT 上穿 100',at:1700000000,status:'accepted'})),total:45,page:n,before:1700000001});}
   if(p.endsWith('/event')){detailReads++;return json({body:'测试详情',attempts:1});}
   if(p.endsWith('/catalog'))return json({items:[{symbol:'BTCUSDT',base:'BTC',last:'73000',unit:'BTC'}]});
   if(p.endsWith('/change')){
    const body=req.postDataJSON();writes.push(body);
    assert.equal(req.headers().authorization,'Bearer synthetic-a');
    if(fail){fail=false;return route.abort();}
    if(reject){reject=false;return json({error:'请间隔一分钟再发送测试通知'},400);}
    if(body.action==='save'){state.rules=[{...body.rule,id:'synthetic-rule',state:{status:'watching',price:'73000',sampleAt:Date.now()/1000}}];state.revision++;return json({ok:true});}
    state.events=[{id:'test-event',ruleId:'test',at:Date.now()/1000,status:'queued',attempts:0,title:'测试',body:'合成测试'}];state.revision++;
    return json({ok:true,revision:state.revision});
   }
   if(p.endsWith('/shared-account.js'))return route.fulfill({contentType:'text/javascript',body:"window.testToken='synthetic-a';window.RadarAccount={token:()=>window.testToken};window.RadarIdentity={code:()=> '12345688'};"});
   let file=p.split('/').at(-1)||'index.html';
   let dir=['index.html','app.js','style.css'].includes(file)&&p.includes('/alarms/')?assets:__dirname;
   if(!p.includes('/alarms/')){
    try{return route.fulfill({contentType:p.endsWith('.svg')?'image/svg+xml':'text/css',body:await fs.readFile(path.join(assets,'site',p.replace(/^\/radar\//,'')))});}catch{return route.fulfill({contentType:'text/css',body:''});}
   }
   try{return route.fulfill({contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html',body:await fs.readFile(path.join(dir,file))});}catch{return route.fulfill({status:404,body:''});}
  });
  await page.clock.install();await page.goto('https://bark-fixture.test/radar/robot-push/alarms/');
  await page.waitForFunction(()=>!document.querySelector('#bind-device').disabled);
  assert.equal(await page.locator('#bark-test-result').isVisible(),false);
  assert.equal(await page.locator('#test-bark-inline').isDisabled(),true);
  const loaded=page.waitForResponse(r=>r.url().includes('/catalog'));await page.click('#add-alarm');await loaded;await page.waitForTimeout(100);
  assert.equal(await page.locator('#alarm-symbols option').count(),0);
  assert.equal(await page.locator('[name=symbol]').getAttribute('list'),null);
  assert.equal(await page.locator('#rule-preview').count(),0);
  await page.fill('[name=symbol]','BT');assert.equal(await page.locator('#alarm-symbols option').count(),0);
  await page.fill('[name=symbol]','btc');assert.equal(await page.locator('#alarm-symbols option').count(),1);
  await page.fill('[name=symbol]','');assert.equal(await page.locator('#alarm-symbols option').count(),0);assert.equal(await page.locator('[name=symbol]').getAttribute('list'),null);
  await page.fill('[name=symbol]','BTCUSDT');await page.fill('[name=target]','68000');await page.selectOption('[name=condition]','below');
  await page.waitForFunction(()=>document.querySelector('#alarm-symbols option'));
  assert.equal(await page.locator('#alarm-form input:visible,#alarm-form select:visible').count(),5);
  if(process.env.ALARM_SCREENSHOTS)await page.screenshot({path:path.join(process.env.ALARM_SCREENSHOTS,`simple-alarm-${width}.png`),fullPage:true});
  await page.click('#save-alarm');await page.waitForFunction(()=>!document.querySelector('#alarm-editor').open);
  assert.deepEqual(await page.locator('.alarm-actions button').allTextContents(),['编辑','删除']);assert.doesNotMatch(await page.locator('.alarm-row').innerText(),/最近采样/);
  const rule=writes.pop().rule;assert.equal(rule.level,'critical');assert.equal(rule.hold,0);assert.equal(rule.immediate,true);assert.equal(rule.hysteresis,'0');assert.equal(rule.market,'future');assert.equal(rule.expiresAt,null);
  state.device={label:'我的 iPhone',suffix:'000001'};await page.click('#refresh-alarms');
  await page.waitForFunction(()=>!document.querySelector('#test-bark-inline').disabled);
  await page.click('#test-bark-inline');await page.waitForFunction(()=>document.querySelector('#bark-test-result').textContent.includes('等待发送'));
  assert.equal(writes.length,1);assert.equal(writes[0].action,'test');assert.equal(await page.locator('#test-bark-inline').isDisabled(),true);
  for(const status of ['sending','retry','accepted','failed','unknown','expired','cancelled']){
   state.events[0].status=status;state.events[0].error=status==='failed'?'Bark 拒绝请求':null;
   await page.click('#refresh-alarms');await page.waitForFunction(s=>document.querySelector('#bark-test-result').dataset.state===s,status);
   if(status==='accepted')assert.match(await page.locator('#bark-test-result').innerText(),/Bark 已接受/);
   if(status==='failed')assert.match(await page.locator('#bark-test-result').innerText(),/Bark 拒绝请求/);
  }
  reject=true;await page.click('#test-bark-inline');await page.waitForFunction(()=>document.querySelector('#alarm-notice').textContent.includes('一分钟'));
  fail=true;await page.click('#test-bark-inline');await page.locator('#pending-action').waitFor({state:'visible'});
  const failed=writes.at(-1);assert.equal(await page.locator('#test-bark-inline').isDisabled(),true);
  await page.click('#retry-action');await page.waitForFunction(()=>document.querySelector('#pending-action').hidden);assert.deepEqual(writes.at(-1),failed);
  state.events[0].status='accepted';await page.click('#refresh-alarms');await page.waitForFunction(()=>document.querySelector('#bark-test-result').dataset.state==='accepted');
  await page.click('#refresh-alarms');await page.clock.runFor(8001);assert.equal(await page.locator('#bark-test-result').isVisible(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no overflow '+width);
  if(process.env.ALARM_SCREENSHOTS)await page.screenshot({path:path.join(process.env.ALARM_SCREENSHOTS,`bark-test-${width}.png`),fullPage:true});
  await page.click('a[href="history.html"]');await page.waitForFunction(()=>document.querySelectorAll('#event-list details').length===20);
  assert.equal(detailReads,0);await page.locator('#event-list summary').first().click();await page.waitForFunction(()=>document.querySelector('.history-body').textContent.includes('测试详情'));assert.equal(detailReads,1);
  await page.click('#history-next');await page.waitForFunction(()=>document.querySelector('#history-page').textContent.includes('第 2'));assert.equal(await page.locator('#event-list details').count(),20);
  await page.click('#history-next');await page.waitForFunction(()=>document.querySelectorAll('#event-list details').length===5);assert.equal(await page.locator('#history-next').isDisabled(),true);
  await page.reload();await page.waitForFunction(()=>document.querySelectorAll('#event-list details').length===20);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'history fits '+width);
  if(process.env.ALARM_SCREENSHOTS)await page.screenshot({path:path.join(process.env.ALARM_SCREENSHOTS,`alarm-history-${width}.png`),fullPage:true});
  await page.goto('https://bark-fixture.test/radar/robot-push/alarms/');await page.waitForFunction(()=>!document.querySelector('#bind-device').disabled);
  await page.evaluate(()=>{localStorage.removeItem('radar-settings-token');document.dispatchEvent(new Event('radar-profile-changing'));});
  assert.equal(await page.locator('#bark-test-result').isVisible(),false);assert.equal(await page.locator('#test-bark-inline').isDisabled(),true);
  assert.deepEqual(errors,[]);console.log(JSON.stringify({width,passed:true,writes:writes.length}));await page.close();
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
