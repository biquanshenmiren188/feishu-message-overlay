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
 const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||undefined});t.after(()=>browser.close());
 const html=(await readFile(new URL('index.html',import.meta.url),'utf8')).replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');
 const css=await readFile(new URL('style.css',import.meta.url),'utf8'),source=await readFile(new URL('coin-center.js',import.meta.url),'utf8'),listSource=await readFile(new URL('coin-list.js',import.meta.url),'utf8');
 async function setup(t,data=fixture(),width=1280,firstMuteFailure=false){
  const context=await browser.newContext({viewport:{width,height:900}});t.after(()=>context.close());const page=await context.newPage(),writes=[],networkWrites=[],errors=[];let saved=structuredClone(data);
  page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());if(request.method()==='POST')networkWrites.push(url.pathname);
   if(url.origin!=='https://coin-center.test')return route.abort('blockedbyclient');
   if(url.pathname==='/edit'){
    const body=request.postDataJSON();writes.push(body);
    const results=Object.fromEntries(channels.map(c=>[c,{state:body.changes.some(x=>x.channel===c)?'saved':'skipped'}]));if(firstMuteFailure&&writes.length===1)results.mute={state:firstMuteFailure==='pending'?'pending':'failed',error:'测试静音未保存'};
    for(const change of body.changes){if(results[change.channel].state!=='saved')continue;const rows=saved.profiles[change.channel].coins;const at=rows.findIndex(r=>r.coin===change.coin&&r.exchange===change.exchange);if(at!==-1)rows.splice(at,1);if(change.after!==null)rows.push({coin:change.coin,exchange:change.exchange,enabled:change.after});}
    return route.fulfill({json:{saved,operation:{results}}});
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
  return {page,writes,networkWrites,saved:()=>structuredClone(saved)};
 }
 const save=async page=>{await page.locator('#center-save').click();await page.locator('#center-results').filter({hasText:'全部保存'}).waitFor();};
 const select=page=>page.locator('[data-matrix-desktop-mode]').first();

 for(const [before,after] of [['none','hide'],['none','mute'],['hide','mute'],['mute','hide'],['hide','none'],['mute','none']])await t.test(`${before} to ${after} stages an exact mutually exclusive change until save`,async t=>{
  const data=fixture();if(before!=='none')rule(data,before==='hide'?'desktop':'mute','all',true);
  const {page,writes}=await setup(t,data);
  assert.deepEqual(await select(page).locator('option').allTextContents(),['正常推送','仅静音','屏蔽']);
  assert.equal(await page.locator('select[data-matrix-channel="desktop"],select[data-matrix-channel="mute"]').count(),0);
  assert.equal(await select(page).inputValue(),before);assert.equal(await page.locator('#center-save').isDisabled(),true);
  await select(page).selectOption(after);assert.equal(writes.length,0);assert.equal(await page.locator('#center-save').isEnabled(),true);
  const label={none:'正常推送',mute:'仅静音',hide:'屏蔽'};
  assert.deepEqual(await page.locator('#center-changes li').allInnerTexts(),[`PTB / 全部交易所 / 电脑推送：${label[before]} → ${label[after]}`]);assert.equal(await page.locator('#center-change-count').textContent(),'1');
  await save(page);assert.equal(writes.length,1);
  assert.deepEqual(await page.locator('#center-changes li').allInnerTexts(),[`PTB / 全部交易所 / 电脑推送：${label[after]}`]);
  const expected=[];if(before!=='none')expected.push({channel:before==='hide'?'desktop':'mute',coin:'PTB',exchange:'all',before:true,after:null});if(after!=='none')expected.push({channel:after==='hide'?'desktop':'mute',coin:'PTB',exchange:'all',before:null,after:true});
  assert.deepEqual(sort(writes[0].changes),sort(expected));
 });

 await t.test('partial desktop save summarizes actual combined state without claiming the requested mode succeeded',async t=>{
  const data=fixture();rule(data,'desktop','all',true);const {page,writes}=await setup(t,data,1280,true);await select(page).selectOption('mute');
  await page.locator('#center-save').click();await page.locator('#center-retry').waitFor({state:'visible'});
  assert.match(await page.locator('#center-results').textContent(),/电脑推送：正常推送（当前已保存；未完成：仅静音 测试静音未保存）/);assert.doesNotMatch(await page.locator('#center-results').textContent(),/电脑推送：仅静音（已保存）/);
  await page.locator('#center-retry').click();await page.locator('#center-results').filter({hasText:'全部保存'}).waitFor();assert.deepEqual(writes[1],writes[0]);assert.deepEqual(await page.locator('#center-changes li').allInnerTexts(),['PTB / 全部交易所 / 电脑推送：仅静音']);
 });

 await t.test('a pending channel cannot produce all-saved status and retries the same operation',async t=>{
  const data=fixture();rule(data,'desktop','all',true);const {page,writes}=await setup(t,data,1280,'pending');await select(page).selectOption('mute');
  await page.locator('#center-save').click();await page.locator('#center-retry').waitFor({state:'visible'});
  assert.doesNotMatch(await page.locator('#center-results').textContent(),/全部保存/);assert.match(await page.locator('#center-results').textContent(),/未完成/);assert.equal(await page.locator('#center-save').isDisabled(),true);
  await page.locator('#center-retry').click();await page.locator('#center-results').filter({hasText:'全部保存'}).waitFor();assert.deepEqual(writes[1],writes[0]);assert.deepEqual(await page.locator('#center-changes li').allInnerTexts(),['PTB / 全部交易所 / 电脑推送：仅静音']);
 });

 for(const action of ['mute','block'])await t.test(`batch ${action} clears only the opposite target-scope computer rule`,async t=>{
  const data=fixture();rule(data,'desktop','gate',action==='mute');rule(data,'mute','gate',action==='block');rule(data,'cards','gate',false);rule(data,'mobile','gate',false);rule(data,'desktop','all',true);rule(data,'mute','all',true);rule(data,'desktop','gate',true,'IRYS');
  const {page,writes,saved}=await setup(t,data);await page.locator('#center-cancel').click();await page.evaluate(action=>window.RadarCoinCenter.batch([{coin:'PTB',exchange:'gate'}],action),action);
  assert.equal(writes.length,0);const summary=await page.locator('#center-changes li').allInnerTexts();assert.equal(summary.filter(x=>x.includes('电脑推送')).length,1);assert.match(summary.find(x=>x.includes('电脑推送')),action==='mute'?/电脑推送：屏蔽 → 仅静音/:/电脑推送：仅静音 → 屏蔽/);
  await save(page);const changes=writes[0].changes;assert.equal(changes.every(c=>c.coin==='PTB'&&c.exchange==='gate'),true);
  const expected=[{channel:action==='mute'?'desktop':'mute',coin:'PTB',exchange:'gate',before:true,after:null},{channel:action==='mute'?'mute':'desktop',coin:'PTB',exchange:'gate',before:false,after:true}];if(action==='block')for(const channel of ['cards','mobile'])expected.push({channel,coin:'PTB',exchange:'gate',before:false,after:true});assert.deepEqual(sort(changes),sort(expected));
  for(const channel of channels)assert.deepEqual(saved().profiles[channel].coins.filter(r=>r.coin!=='PTB'||r.exchange!=='gate'),data.profiles[channel].coins.filter(r=>r.coin!=='PTB'||r.exchange!=='gate'));
  if(action==='mute')for(const channel of ['cards','mobile'])assert.deepEqual(saved().profiles[channel],data.profiles[channel]);
  assert.equal((await page.locator('#center-changes li').allInnerTexts()).filter(x=>x.includes('电脑推送')).length,1);
 });

 await t.test('restoring only mute rules still summarizes a retained same-scope hide as blocked',async t=>{
  const data=fixture();rule(data,'desktop','gate',true);rule(data,'mute','gate',true);const {page,writes}=await setup(t,data);await page.locator('#center-cancel').click();await page.evaluate(()=>window.RadarCoinCenter.batch([{coin:'PTB',exchange:'gate'}],'pause'));
  for(const channel of ['desktop','cards','mobile'])await page.locator(`[data-center-target="${channel}"]`).uncheck();
  assert.deepEqual(await page.locator('#center-changes li').allInnerTexts(),['PTB / gate / 电脑推送：屏蔽 → 屏蔽']);await save(page);assert.deepEqual(writes[0].changes,[{channel:'mute',coin:'PTB',exchange:'gate',before:true,after:false}]);assert.deepEqual(await page.locator('#center-changes li').allInnerTexts(),['PTB / gate / 电脑推送：屏蔽']);
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
  await page.locator('[data-matrix-block-mode="cards"]').selectOption('on');await save(page);
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

 for(const channel of ['cards','mobile'])await t.test(`${channel} has explicit normal/block choices and saved scope results`,async t=>{
  const data=fixture();rule(data,channel,'all',true);const {page,writes}=await setup(t,data);const choice=page.locator(`[data-matrix-block-mode="${channel}"]`);
  assert.deepEqual(await choice.locator('option').allTextContents(),['正常推送','屏蔽']);await choice.selectOption('none');
  assert.equal(writes.length,0);assert.match(await page.locator('#center-changes').innerText(),/本范围草稿.*尚未保存/s);assert.match(await page.locator('#center-changes').innerText(),/屏蔽 → 正常推送/);
  await save(page);assert.deepEqual(writes[0].changes,[{channel,coin:'PTB',exchange:'all',before:true,after:null}]);
  assert.match(await page.locator('#center-changes').innerText(),/本范围已保存.*正常推送/s);assert.doesNotMatch(await page.locator('#coin-manager').innerText(),/未设置|已启用|已停用|电脑静音/);
 });

 for(const channel of ['cards','mobile'])await t.test(`legacy inactive ${channel} stays unchanged when another channel is saved`,async t=>{
  const data=fixture();rule(data,channel,'all',false);const {page,writes}=await setup(t,data);
  assert.equal(await page.locator(`[data-matrix-block-mode="${channel}"]`).inputValue(),'none');assert.equal(await page.locator('#center-save').isDisabled(),true);
  await select(page).selectOption('mute');await save(page);assert.deepEqual(writes[0].changes,[{channel:'mute',coin:'PTB',exchange:'all',before:null,after:true}]);
  await page.locator('#center-cancel').click();await page.evaluate(()=>window.RadarCoinCenter.matrix('PTB'));
  await page.locator(`[data-matrix-block-mode="${channel}"]`).selectOption('none');await save(page);assert.deepEqual(writes[1].changes,[{channel,coin:'PTB',exchange:'all',before:false,after:null}]);
 });

 await t.test('saved list labels distinguish normal, muted and blocked while retaining all-exchange coverage',async t=>{
  const data=fixture();rule(data,'desktop','all',true,'BLOCK');rule(data,'mute','all',true,'MUTE');rule(data,'cards','all',false,'NORMAL');rule(data,'mobile','all',true,'PHONE');rule(data,'cards','all',true,'SCOPE');rule(data,'cards','gate',false,'SCOPE');
  const {page,networkWrites}=await setup(t,data);await page.locator('#center-cancel').click();
  await page.evaluate(()=>{window.RadarCoinSettings.syncUI=()=>{};window.RadarCoinAPI.load=async()=>({saved:window.testState,operations:[]});});await page.addScriptTag({content:listSource});
  const row=coin=>page.locator('.blocked-coin-row').filter({hasText:coin});
  assert.match(await row('BLOCK').innerText(),/电脑消息 · 屏蔽/);assert.match(await row('MUTE').innerText(),/电脑消息 · 仅静音/);
  assert.match(await row('NORMAL').innerText(),/行情卡片 · 正常推送/);assert.match(await row('PHONE').innerText(),/手机推送 · 屏蔽/);
  const scopeRows=await row('SCOPE').allInnerTexts();assert.equal(scopeRows.length,2);for(const text of scopeRows)assert.match(text,/行情卡片 · 屏蔽/);
  assert.doesNotMatch(await page.locator('#blocked-list').innerText(),/未设置|已启用|已停用|电脑静音/);
  await page.locator('#refresh-coins').click();await page.locator('#coin-sync-status').filter({hasText:'其他筛选仍按原设置'}).waitFor();assert.deepEqual(networkWrites,[]);
 });

 await t.test('saved coin search is exact and preserves multiplier and wrapped coin identities',async t=>{
  const data=fixture();for(const coin of ['BTC','WBTC','1000BTC','BTCB'])rule(data,'desktop','all',true,coin);
  const {page,networkWrites}=await setup(t,data);await page.locator('#center-cancel').click();
  await page.evaluate(()=>{window.RadarCoinSettings.syncUI=()=>{};});await page.addScriptTag({content:listSource});
  for(const q of ['BTC',' btc ']){await page.fill('#blocked-search',q);assert.deepEqual(await page.locator('.blocked-identity b').allTextContents(),['BTC']);}
  await page.fill('#blocked-search','BT');assert.equal(await page.locator('.blocked-coin-row').count(),0);
  await page.fill('#blocked-search','1000BTC');assert.deepEqual(await page.locator('.blocked-identity b').allTextContents(),['1000BTC']);
  await page.fill('#blocked-search','');assert.equal(await page.locator('.blocked-coin-row').count(),4);assert.deepEqual(networkWrites,[]);
 });

 await t.test('operation history describes actual channel states and distinguishes unsaved failures',async t=>{
  const {page,networkWrites}=await setup(t);await page.locator('#center-cancel').click();
  await page.evaluate(()=>{window.RadarCoinSettings.syncUI=()=>{};});await page.addScriptTag({content:listSource});
  await page.evaluate(()=>document.dispatchEvent(new CustomEvent('radar-coin-center-updated',{detail:{operations:[{id:'isolated-history',kind:'edit',at:1700000000,coins:['PTB'],changes:[{channel:'cards',coin:'PTB',exchange:'all',before:false,after:true},{channel:'mobile',coin:'PTB',exchange:'all',before:true,after:null},{channel:'mute',coin:'PTB',exchange:'gate',before:true,after:false},{channel:'desktop',coin:'PTB',exchange:'all',before:true,after:null},{channel:'mute',coin:'PTB',exchange:'all',before:true,after:null}],results:{desktop:{state:'saved'},cards:{state:'saved'},mobile:{state:'failed',error:'测试未保存'},mute:{state:'saved'}}}]}})));
  await page.locator('.operation-history, #coin-operations details').evaluateAll(items=>items.forEach(item=>item.open=true));
  const entries=await page.locator('#coin-operations li').allInnerTexts();
  assert.match(entries[0],/行情卡片：正常推送 → 屏蔽 · 已保存/);assert.match(entries[1],/手机推送：屏蔽 → 正常推送（删除本范围规则） · 测试未保存/);assert.match(entries[2],/取消仅静音规则 · 已保存/);assert.doesNotMatch(entries[2],/正常推送/);assert.match(entries[3],/移除电脑屏蔽规则 · 已保存/);assert.match(entries[4],/移除仅静音规则 · 已保存/);assert.doesNotMatch(entries[3]+entries[4],/正常推送/);
  assert.doesNotMatch(await page.locator('#coin-operations').innerText(),/未设置|已启用|已停用|电脑静音/);assert.deepEqual(networkWrites,[]);
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
