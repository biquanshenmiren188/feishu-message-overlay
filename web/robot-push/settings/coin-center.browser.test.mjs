// Real-DOM checks with isolated state/API; use bundled Playwright via NODE_PATH.
// RADAR_BROWSER_TESTS=1 makes a missing browser dependency a failure.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile,mkdir} from 'node:fs/promises';
import {join} from 'node:path';
let chromium;
try{({chromium}=createRequire(import.meta.url)('playwright'));}catch(error){if(process.env.RADAR_BROWSER_TESTS==='1')throw error;}
const channels=['desktop','mute','cards','mobile'];
const fixture=()=>({profiles:Object.fromEntries(channels.map(c=>[c,{coins:[]}])),desktopLoaded:true,mobileLoaded:true});
const rule=(data,c,exchange,enabled,coin='PTB')=>data.profiles[c].coins.push({coin,exchange,enabled});
const sort=changes=>[...changes].sort((a,b)=>[a.channel,a.coin,a.exchange].join('|').localeCompare([b.channel,b.coin,b.exchange].join('|')));

test('settings matrix presents one desktop mode without altering untouched legacy rules',{skip:!chromium&&'Playwright unavailable; set NODE_PATH and RADAR_BROWSER_TESTS=1 to run'},async t=>{
 const browser=await chromium.launch({headless:true});t.after(()=>browser.close());
 const html=(await readFile(new URL('index.html',import.meta.url),'utf8')).replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');
 const css=await readFile(new URL('style.css',import.meta.url),'utf8'),source=await readFile(new URL('coin-center.js',import.meta.url),'utf8');
 async function setup(t,data=fixture(),width=1280){
  const context=await browser.newContext({viewport:{width,height:900}});t.after(()=>context.close());const page=await context.newPage(),writes=[],errors=[];let saved=structuredClone(data);
  page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());
   if(url.origin!=='https://coin-center.test')return route.abort('blockedbyclient');
   if(url.pathname==='/edit'){
    const body=request.postDataJSON();writes.push(body);
    for(const change of body.changes){const rows=saved.profiles[change.channel].coins;const at=rows.findIndex(r=>r.coin===change.coin&&r.exchange===change.exchange);if(at!==-1)rows.splice(at,1);if(change.after!==null)rows.push({coin:change.coin,exchange:change.exchange,enabled:change.after});}
    return route.fulfill({json:{saved,operation:{results:Object.fromEntries(channels.map(c=>[c,{state:body.changes.some(x=>x.channel===c)?'saved':'skipped'}]))}}});
   }
   if(url.pathname.endsWith('/style.css'))return route.fulfill({contentType:'text/css',body:css});
   if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
   return route.fulfill({status:404,body:'Isolated test asset'});
  });
  await page.goto('https://coin-center.test/');
  await page.evaluate(data=>{
   window.testState=structuredClone(data);
   window.RadarRules={exchanges:[['binance','Binance'],['gate','Gate']],name:e=>e};
   window.RadarCoinSettings={snapshot:()=>structuredClone(window.testState),receive:data=>{window.testState=structuredClone(data.saved);},toast:()=>{}};
   window.RadarCoinAPI={planLabel:()=> '测试方案',edit:async request=>(await fetch('/edit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)})).json()};
  },data);
  await page.addScriptTag({content:source});await page.evaluate(()=>window.RadarCoinCenter.matrix('PTB'));
  t.after(()=>assert.deepEqual(errors,[]));
  return {page,writes,saved:()=>structuredClone(saved)};
 }
 const save=async page=>{await page.locator('#center-save').click();await page.locator('#center-results').filter({hasText:'全部保存'}).waitFor();};
 const select=page=>page.locator('[data-matrix-desktop-mode]').first();

 for(const [before,after] of [['none','hide'],['none','mute'],['hide','mute'],['mute','hide'],['hide','none'],['mute','none']])await t.test(`${before} to ${after} stages an exact mutually exclusive change until save`,async t=>{
  const data=fixture();if(before!=='none')rule(data,before==='hide'?'desktop':'mute','all',true);
  const {page,writes}=await setup(t,data);
  assert.deepEqual(await select(page).locator('option').allTextContents(),['电脑屏蔽','电脑静音','未设置']);
  assert.equal(await page.locator('select[data-matrix-channel="desktop"],select[data-matrix-channel="mute"]').count(),0);
  assert.equal(await select(page).inputValue(),before);assert.equal(await page.locator('#center-save').isDisabled(),true);
  await select(page).selectOption(after);assert.equal(writes.length,0);assert.equal(await page.locator('#center-save').isEnabled(),true);
  await save(page);assert.equal(writes.length,1);
  const expected=[];if(before!=='none')expected.push({channel:before==='hide'?'desktop':'mute',coin:'PTB',exchange:'all',before:true,after:null});if(after!=='none')expected.push({channel:after==='hide'?'desktop':'mute',coin:'PTB',exchange:'all',before:null,after:true});
  assert.deepEqual(sort(writes[0].changes),sort(expected));
 });

 await t.test('cancel and Escape discard staged selection without writes',async t=>{
  const data=fixture();rule(data,'desktop','all',true);const {page,writes,saved}=await setup(t,data);
  await select(page).selectOption('mute');await page.locator('#center-cancel').click();
  await page.evaluate(()=>window.RadarCoinCenter.matrix('PTB'));assert.equal(await select(page).inputValue(),'hide');assert.equal(await page.locator('#center-save').isDisabled(),true);
  await select(page).selectOption('none');await page.keyboard.press('Escape');await page.evaluate(()=>window.RadarCoinCenter.matrix('PTB'));
  assert.equal(await select(page).inputValue(),'hide');assert.equal(writes.length,0);assert.deepEqual(saved(),data);
 });

 for(const enabled of [true,false])await t.test(`untouched ${enabled?'dual-enabled':'disabled'} legacy desktop values survive another channel edit`,async t=>{
  const data=fixture();rule(data,'desktop','all',enabled);rule(data,'mute','all',enabled);const {page,writes,saved}=await setup(t,data);
  assert.equal(await select(page).inputValue(),enabled?'hide':'none');assert.equal(await page.locator('#center-change-count').textContent(),'0');assert.equal(await page.locator('#center-save').isDisabled(),true);
  await page.locator('select[data-matrix-channel="cards"]').selectOption('on');await save(page);
  assert.deepEqual(writes[0].changes,[{channel:'cards',coin:'PTB',exchange:'all',before:null,after:true}]);
  assert.deepEqual(saved().profiles.desktop,data.profiles.desktop);assert.deepEqual(saved().profiles.mute,data.profiles.mute);
 });

 await t.test('selecting a mode clears the opposite legacy mode but preserves other scopes and channels',async t=>{
  const data=fixture();rule(data,'desktop','all',true);rule(data,'mute','all',true);rule(data,'desktop','gate',false);rule(data,'mute','gate',true);rule(data,'cards','gate',false);rule(data,'mobile','all',true);rule(data,'desktop','all',true,'IRYS');
  const {page,writes,saved}=await setup(t,data);await select(page).selectOption('mute');await save(page);
  assert.deepEqual(writes[0].changes,[{channel:'desktop',coin:'PTB',exchange:'all',before:true,after:null}]);
  const expected=structuredClone(data);expected.profiles.desktop.coins=expected.profiles.desktop.coins.filter(r=>r.coin!=='PTB'||r.exchange!=='all');assert.deepEqual(saved(),expected);
 });

 await t.test('new exchange scope and renamed coin retain precise original scope changes',async t=>{
  const data=fixture();rule(data,'desktop','gate',true);rule(data,'cards','gate',false);const {page,writes}=await setup(t,data);
  await page.locator('#center-coin').fill('ALT');await select(page).selectOption('mute');await page.locator('#center-add-scope').click();
  await page.locator('.matrix-row').nth(1).locator('[data-matrix-desktop-mode]').selectOption('hide');
  assert.equal(writes.length,0);await save(page);
  assert.deepEqual(sort(writes[0].changes),sort([{channel:'desktop',coin:'PTB',exchange:'gate',before:true,after:null},{channel:'cards',coin:'PTB',exchange:'gate',before:false,after:null},{channel:'mute',coin:'ALT',exchange:'gate',before:null,after:true},{channel:'cards',coin:'ALT',exchange:'gate',before:null,after:false},{channel:'desktop',coin:'ALT',exchange:'all',before:null,after:true}]));
 });

 for(const width of [1280,393])await t.test(`three visible channels fit ${width}px and retain manual save`,async t=>{
  const {page,writes}=await setup(t,fixture(),width);await select(page).selectOption('mute');
  assert.deepEqual(await page.locator('.matrix-row label span').allTextContents(),['交易所范围','电脑推送','行情卡片','手机推送']);
  const box=await page.locator('#coin-manager').evaluate(dialog=>{const r=dialog.getBoundingClientRect();return {left:r.left,right:r.right,viewport:innerWidth,scroll:dialog.scrollWidth,client:dialog.clientWidth};});
  assert.ok(box.left>=0&&box.right<=box.viewport,JSON.stringify(box));assert.ok(box.scroll<=box.client+1,JSON.stringify(box));
  await page.locator('#center-save').scrollIntoViewIfNeeded();assert.equal(await page.locator('#center-save').isVisible(),true);assert.equal(await page.locator('#center-save').isEnabled(),true);assert.equal(writes.length,0);
  if(process.env.RADAR_TEST_SCREENSHOT_DIR){await mkdir(process.env.RADAR_TEST_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:join(process.env.RADAR_TEST_SCREENSHOT_DIR,`coin-center-desktop-mode-${width}.png`),fullPage:true});}
 });
});
