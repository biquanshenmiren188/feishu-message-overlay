import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
let engines;
try{const p=createRequire(import.meta.url)('playwright');engines={chromium:p.chromium,webkit:p.webkit};}catch(e){if(process.env.RADAR_BROWSER_TESTS==='1')throw e;}
const source=await readFile(new URL('./blocked-pushes.js',import.meta.url),'utf8'),css=await readFile(new URL('./blocked-pushes.css',import.meta.url),'utf8');
for(const name of ['chromium','webkit'])test(`${name}: current hidden messages remain a read-only snapshot, separate from history`,{skip:!engines&&'Playwright unavailable'},async t=>{
 const browser=await engines[name].launch({headless:true});t.after(()=>browser.close());
 const context=await browser.newContext({viewport:{width:1440,height:900},serviceWorkers:'block'});t.after(()=>context.close());
 const page=await context.newPage(),requests=[],errors=[];let historyStatus=200,historyGate=null;
 page.on('pageerror',e=>errors.push(e.message));
 await context.addInitScript(()=>{
  localStorage.setItem('radar-settings-token','synthetic-one');
  window.webSnapshot={bound:true,ready:true,blocked:[{id:'ordinary',title:'UNITREE | FF',body:'普通消息\n<img src="https://invalid.example/">',sentAt:'2026-10-28T12:00:00Z'},{id:'pinned',title:'强信号 | UNITREE | 3组',body:'R0 | FF | GT→AS',sentAt:'2026-10-28T12:01:00Z'}]};
  window.emitWeb=()=>document.dispatchEvent(new CustomEvent('radar-feed-policy-snapshot',{detail:window.webSnapshot}));
  document.addEventListener('radar-feed-policy-request',()=>window.emitWeb());
 });
 await context.route('**/*',async route=>{
  const req=route.request(),u=new URL(req.url());requests.push({method:req.method(),path:u.pathname});if(u.origin!=='https://hidden.test')return route.abort();
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:'<!doctype html><html lang="zh-CN"><meta name="viewport" content="width=device-width,initial-scale=1"><div class="feed-tools"></div><script type="module" src="/blocked-pushes.js"></script></html>'});
  if(u.pathname.endsWith('/blocked-pushes.js'))return route.fulfill({contentType:'text/javascript',body:source});
  if(u.pathname.endsWith('/blocked-pushes.css'))return route.fulfill({contentType:'text/css',body:css});
  const entry={id:'ordinary',channel:'desktop',action:'hide',at:1793188800,coin:'UNITREE',rank:'R0',value:'+0.2%',reasons:['币种屏蔽']};
  if(u.pathname.endsWith('/desktop-settings')||u.pathname.endsWith('/status')){
   if(historyGate&&req.headers().authorization===historyGate.auth)await historyGate.promise;
   return route.fulfill({status:historyStatus,json:u.pathname.endsWith('/desktop-settings')?{history:[entry,{...entry,id:'mute',action:'mute'}]}:{blockedHistory:[entry]}});
  }
  return route.fulfill({status:404,body:''});
 });
 await page.goto('https://hidden.test/');
 const entry=page.locator('.rp-blocked-entry'),list=page.locator('.rp-blocked-list');
 await entry.filter({hasText:'已屏蔽 2 条'}).waitFor();await entry.click();
 await page.locator('[data-message-id="ordinary"]').waitFor();assert.equal(await list.locator('article').count(),2);assert.equal(await list.locator('img').count(),0);
 assert.match(await list.innerText(),/强信号/);assert.match(await list.innerText(),/<img src=/);
 await page.evaluate(()=>{window.webSnapshot={bound:true,ready:true,blocked:[{id:'new',title:'NEW',body:'new body',sentAt:'2026-10-28T12:02:00Z'}]};window.emitWeb();window.dispatchEvent(new Event('focus'));});
 assert.equal(await entry.innerText(),'已屏蔽 1 条');assert.match(await list.innerText(),/UNITREE/);assert.doesNotMatch(await list.innerText(),/NEW/);
 await page.getByRole('button',{name:/^电脑历史/}).click();await page.getByRole('button',{name:'电脑历史 1',exact:true}).waitFor();assert.equal(await list.locator('article').count(),1);assert.match(await list.innerText(),/币种屏蔽/);
 await page.getByRole('button',{name:/^手机历史/}).click();assert.equal(await list.locator('article').count(),1);
 await page.getByRole('button',{name:/^网页当前/}).click();assert.equal(await list.locator('article').count(),2);
 await page.getByRole('button',{name:'刷新',exact:true}).click();await page.locator('[data-message-id="new"]').waitFor();assert.equal(await list.locator('article').count(),1);
 for(const width of [1440,393,320]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);const box=await page.locator('.rp-blocked-dialog').boundingBox();assert(box.x>=0&&box.x+box.width<=width+1);}
 await page.evaluate(()=>{window.webSnapshot={bound:true,ready:false,blocked:[]};window.emitWeb();});assert.equal(await list.locator('article').count(),0);assert.match(await page.locator('.rp-blocked-status').innerText(),/等待/);
 await page.evaluate(()=>{localStorage.setItem('radar-settings-token','synthetic-two');window.webSnapshot={bound:true,ready:false,blocked:[]};window.dispatchEvent(new Event('storage'));});await page.locator('.rp-blocked-dialog').waitFor({state:'detached'});
 assert.equal(await page.locator('[data-message-id]').count(),0);
 await page.evaluate(()=>{window.webSnapshot={bound:true,ready:true,blocked:[]};window.emitWeb();});await entry.filter({hasText:'已屏蔽 0 条'}).waitFor();await entry.click();await page.getByText('当前网页没有已屏蔽消息。',{exact:true}).waitFor();
 historyStatus=401;await page.getByRole('button',{name:'刷新',exact:true}).click();await page.getByRole('button',{name:/^电脑历史/}).click();await page.locator('.rp-blocked-status').filter({hasText:'连接已失效'}).waitFor();assert.equal(await list.locator('article').count(),0);
 await page.getByRole('button',{name:'关闭已屏蔽推送',exact:true}).click();historyStatus=200;
 let release;historyGate={auth:'Bearer synthetic-two',promise:new Promise(resolve=>{release=resolve;})};await entry.click();
 await page.evaluate(()=>{localStorage.setItem('radar-settings-token','synthetic-three');window.webSnapshot={bound:true,ready:false,blocked:[]};window.dispatchEvent(new Event('storage'));});await page.locator('.rp-blocked-dialog').waitFor({state:'detached'});release();historyGate=null;
 await page.evaluate(()=>{window.webSnapshot={bound:true,ready:true,blocked:[]};window.emitWeb();});await entry.click();await page.getByText('当前网页没有已屏蔽消息。',{exact:true}).waitFor();assert.equal(await page.locator('[data-message-id]').count(),0);
 await page.getByRole('button',{name:'关闭已屏蔽推送',exact:true}).click();await page.evaluate(()=>{localStorage.removeItem('radar-settings-token');window.webSnapshot={bound:false,ready:false,blocked:[]};window.dispatchEvent(new Event('storage'));});assert.equal(await entry.isDisabled(),true);
 assert.deepEqual(errors,[]);assert.equal(requests.some(r=>r.method!=='GET'),false);assert.equal(requests.some(r=>r.path.includes('invalid.example')),false);
});
