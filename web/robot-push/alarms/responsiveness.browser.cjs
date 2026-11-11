const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
const assets=process.env.ALARM_ASSETS||__dirname;
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true}),page=await browser.newPage({viewport:{width:393,height:852}});let requests=0,delay=300,writes=[];
const state={revision:1,enabled:true,device:{label:'iPhone'},events:[],rules:[{id:'a',exchange:'binance',market:'future',priceType:'last',symbol:'BTCUSDT',condition:'above',target:'90000',enabled:true,repeat:false,state:{price:'73000',status:'watching',sampleAt:Date.now()/1000}}]};
await page.addInitScript(()=>{if(!localStorage.getItem('radar-settings-token'))localStorage.setItem('radar-settings-token','synthetic-a');});
await page.route('**/*',async r=>{const u=new URL(r.request().url());if(u.pathname.endsWith('/catalog'))return r.fulfill({json:{items:[{symbol:'BTCUSDT',base:'BTC',last:'73000',unit:'BTC'}]}});if(u.pathname.endsWith('/change')){const body=r.request().postDataJSON();writes.push(body);if(body.action==='save')state.rules[0]={...state.rules[0],...body.rule};if(body.action==='delete')state.rules=[];state.revision++;return r.fulfill({json:{ok:true}});}if(u.pathname.endsWith('/state')){requests++;assert.equal(u.searchParams.get('events'),'latest-test');await new Promise(ok=>setTimeout(ok,delay));return r.fulfill({json:state});}const name=u.pathname.split('/').pop()||'index.html';let file=path.join(assets,name);if(name==='search.js')file=path.join(__dirname,'search.js');if(!fs.existsSync(file))return r.fulfill({body:'',contentType:'text/css'});return r.fulfill({body:fs.readFileSync(file),contentType:name.endsWith('html')?'text/html':name.endsWith('css')?'text/css':'text/javascript'});});
await page.goto('https://fixture.test/radar/robot-push/alarms/',{waitUntil:'domcontentloaded'});
assert.match(await page.locator('#alarm-status').innerText(),/正在同步/);assert.doesNotMatch(await page.locator('main').innerText(),/未连接|未绑定|规则 0/);
await page.waitForFunction(()=>!document.querySelector('#add-alarm').disabled);assert.equal(requests,1);
assert.deepEqual(await page.locator('.alarm-actions button').allTextContents(),['编辑','删除']);assert.doesNotMatch(await page.locator('.alarm-row').innerText(),/最近采样/);
await page.evaluate(()=>{window.savedRow=document.querySelector('.alarm-row');window.savedButton=document.querySelector('[data-action=edit]');window.savedButton.focus();for(let i=0;i<5;i++)document.querySelector('#refresh-alarms').click();});
await page.waitForTimeout(400);assert.equal(requests,2);assert.equal(await page.evaluate(()=>window.savedRow===document.querySelector('.alarm-row')),true);
state.rules[0].state.price='74000';await page.click('#refresh-alarms');await page.waitForFunction(()=>document.querySelector('.alarm-price').textContent==='74,000');assert.equal(await page.evaluate(()=>window.savedRow===document.querySelector('.alarm-row')&&window.savedButton===document.querySelector('[data-action=edit]')),true);
await page.waitForFunction(()=>Object.keys(sessionStorage).some(k=>k.startsWith('radar-alarm-snapshot')));
delay=1200;await page.reload({waitUntil:'domcontentloaded'});await page.waitForFunction(()=>document.querySelector('#alarm-status').textContent.includes('上次数据'));
assert.equal(await page.locator('.alarm-row').count(),1);assert.equal(await page.locator('#add-alarm').isDisabled(),true);assert.equal(await page.locator('[data-action=edit]').isDisabled(),true);
await page.fill('#alarm-search','BTC');assert.equal(await page.locator('[data-action=edit]').isDisabled(),true);
await page.waitForFunction(()=>!document.querySelector('#add-alarm').disabled);
await page.evaluate(()=>{sessionStorage.clear();});await page.reload({waitUntil:'domcontentloaded'});assert.equal(await page.locator('.alarm-row').count(),0);assert.equal(await page.locator('.is-loading .alarm-toolbar').isVisible(),false);
await page.waitForFunction(()=>!document.querySelector('#add-alarm').disabled);
await page.evaluate(()=>localStorage.setItem('radar-settings-token','synthetic-b'));await page.reload({waitUntil:'domcontentloaded'});assert.equal(await page.locator('.alarm-row').count(),0);assert.doesNotMatch(await page.locator('#alarm-status').innerText(),/上次数据/);await page.waitForFunction(()=>!document.querySelector('#add-alarm').disabled);

// Pause/resume stays available inside edit, never creates a duplicate rule.
for(const enabled of [false,true]){
 await page.click('[data-action=edit]');await page.waitForFunction(()=>document.querySelector('#quote-preview').textContent.includes('73,000'));
 await page.locator('[name=enabled]').setChecked(enabled);await page.click('#save-alarm');await page.waitForFunction(()=>!document.querySelector('#alarm-editor').open);
 assert.equal(writes.at(-1).action,'save');assert.equal(writes.at(-1).id,'a');assert.equal(writes.at(-1).rule.enabled,enabled);assert.equal(writes.at(-1).rule.level,'critical');
}
// Verify the actual browser timer cadence, including a backgrounded document.
delay=0;await page.clock.install();requests=0;await page.reload();await page.waitForFunction(()=>!document.querySelector('#add-alarm').disabled);await page.waitForTimeout(50);
assert.equal(requests,1);await page.clock.runFor(9999);assert.equal(requests,1);await page.clock.runFor(1);await page.waitForFunction(()=>document.querySelector('#add-alarm')&&!document.querySelector('#add-alarm').disabled);await page.waitForTimeout(50);assert.equal(requests,2);
await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'});document.dispatchEvent(new Event('visibilitychange'));});
await page.clock.runFor(30000);assert.equal(requests,2);
await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'visible'});document.dispatchEvent(new Event('visibilitychange'));});await page.waitForTimeout(50);assert.equal(requests,3);
// Changing only the sample timestamp must not change the rendered row.
await page.evaluate(()=>{window.rowChanges=0;new MutationObserver(m=>window.rowChanges+=m.length).observe(document.querySelector('.alarm-row'),{subtree:true,childList:true,characterData:true,attributes:true});});
state.rules[0].state.sampleAt=await page.evaluate(()=>Date.now()/1000);await page.click('#refresh-alarms');await page.waitForTimeout(50);
await page.evaluate(()=>window.rowChanges=0);state.rules[0].state.sampleAt+=1;await page.click('#refresh-alarms');await page.waitForTimeout(50);assert.equal(await page.evaluate(()=>window.rowChanges),0);

page.once('dialog',d=>d.accept());await page.click('[data-action=delete]');await page.waitForFunction(()=>!document.querySelector('.alarm-row'));assert.equal(writes.at(-1).action,'delete');
console.log(JSON.stringify({initialRequests:1,parallelClicks:5,coalescedRequests:1,rowAndButtonPreserved:true,noFalseDisconnectedFlash:true,cachedReadOnlyUntilVerified:true,compactColdStart:true,cacheIsolatedByIdentity:true,onlyEditAndDelete:true,editEnableAndDelete:true,pollEvery10Seconds:true,hiddenPagePaused:true,timestampOnlyDoesNotMutateRow:true}));await browser.close();})().catch(e=>{console.error(e);process.exitCode=1});
