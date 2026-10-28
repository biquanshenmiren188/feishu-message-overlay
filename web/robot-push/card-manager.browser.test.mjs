// Real-DOM regression: NODE_PATH may point to a bundled Playwright installation.
// Set RADAR_BROWSER_TESTS=1 to require it; no request leaves the isolated test page.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile, mkdir} from 'node:fs/promises';
import {join} from 'node:path';

let chromium;
try { ({chromium}=createRequire(import.meta.url)('playwright')); }
catch(error) { if(process.env.RADAR_BROWSER_TESTS==='1')throw error; }
const channels=['desktop','mute','cards','mobile'];
const settings=()=>({excluded_coins:[],advanced:{coins:[]}});
const fixture=()=>({desktop:{desktop:{rules:{hide:settings(),mute:settings()}},cards:{settings:settings()}},mobile:{settings:settings()}});
const policy=(data,c)=>c==='desktop'?data.desktop.desktop.rules.hide:c==='mute'?data.desktop.desktop.rules.mute:c==='cards'?data.desktop.cards.settings:data.mobile.settings;
const rule=(data,channel,exchange,enabled)=>policy(data,channel).advanced.coins.push({coin:'PTB',exchange,enabled});
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};

test('card manager uses one management entrance and stages blocking until explicit save', {skip:!chromium&&'Playwright unavailable; set NODE_PATH and RADAR_BROWSER_TESTS=1 to run'}, async t=>{
  const browser=await chromium.launch({headless:true,args:['--enable-logging=stderr']});
  t.after(()=>browser.close());
  const files=new Map(await Promise.all(['card-manager.js','card-policy.js','card-policy.css','card-oi.js','rule-events.js'].map(async name=>[name,await readFile(new URL(name,import.meta.url),'utf8')])));

  async function setup(t,{data=fixture(),loadGate,loadStatus=200,firstPostFailure,viewport={width:1280,height:800}}={}){
    const context=await browser.newContext({viewport});t.after(()=>context.close());
    const page=await context.newPage(),requests=[],errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    let state=structuredClone(data),postCount=0;
    await context.route('**/*',async route=>{
      const request=route.request(),url=new URL(request.url()),name=url.pathname.split('/').at(-1);
      if(url.origin!=='https://radar-rules.test')return route.abort('blockedbyclient');
      if(url.pathname.startsWith('/radar/push-test/api/')){
        const record={route:name,method:request.method(),body:request.postDataJSON()};requests.push(record);
        if(name==='card-decisions')return route.fulfill({json:{revision:1,cardsEnabled:true,decisions:{'PTB:BN>GT':'allow'}}});
        if(record.method==='GET'){
          if(loadGate)await loadGate.promise;
          return route.fulfill({status:loadStatus,json:loadStatus===200?state:{error:'测试规则读取被拒绝'}});
        }
        postCount++;
        if(firstPostFailure==='network'&&postCount===1)return route.abort('connectionreset');
        const changes=record.body.changes||[];
        const results=Object.fromEntries(channels.map(c=>[c,{state:changes.some(change=>change.channel===c)?'saved':'skipped'}]));
        if(firstPostFailure==='partial'&&postCount===1)results.mobile={state:'failed',error:'测试临时失败'};
        if(firstPostFailure==='desktop-partial'&&postCount===1)results.mute={state:'failed',error:'测试静音未保存'};
        for(const change of changes){
          if(results[change.channel].state!=='saved')continue;
          const target=policy(state,change.channel);
          target.advanced.coins=target.advanced.coins.filter(r=>r.coin!==change.coin||r.exchange!==change.exchange);
          if(change.after!==null)target.advanced.coins.push({coin:change.coin,exchange:change.exchange,enabled:change.after});
        }
        return route.fulfill({json:{...state,operation:{results}}});
      }
      if(files.has(name))return route.fulfill({contentType:name.endsWith('.css')?'text/css':'text/javascript',body:files.get(name)});
      if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/card-policy.css"><style>body{margin:0;background:#f3f6f8;font-family:Arial,"Microsoft YaHei",sans-serif}#toolbar,.bp-card{margin:20px}</style><div id="toolbar"></div><article class="bp-card"><footer class="bp-card-foot"><a class="bp-radar">行情</a></footer></article></html>'});
      return route.fulfill({status:404,body:'Unexpected test route'});
    });
    await page.goto('https://radar-rules.test/');
    await page.evaluate(async()=>{
      localStorage.setItem('radar-settings-token','isolated-test-code');
      window.savedCalls=0;
      window.manager=await import('/card-manager.js');
      window.openTestManager=()=>window.manager.openCardManager('PTB',{onSaved:()=>window.savedCalls++});
    });
    t.after(()=>assert.deepEqual(errors,[],'No uncaught page errors'));
    return {page,requests,posts:()=>requests.filter(r=>r.method==='POST'),state:()=>structuredClone(state)};
  }
  const readRows=page=>page.locator('.bp-rule-row').evaluateAll(rows=>rows.map(row=>({exchange:row.querySelector('[data-scope]').value,...Object.fromEntries([...row.querySelectorAll('[data-channel]')].map(s=>[s.dataset.channel,s.value]))})));
  const open=async(page,stage=false)=>{await page.evaluate(()=>window.openTestManager());await page.locator('.bp-rule-result').filter({hasText:'已加载云端规则'}).waitFor();if(stage){await page.locator('[data-block]').click();await page.locator('.bp-rule-result').filter({hasText:'尚未保存'}).waitFor();}};
  const saved=page=>page.waitForFunction(()=>document.querySelector('.bp-rule-result')?.textContent.includes('已保存')&&document.querySelector('[data-retry]').hidden);

  await t.test('inside button only stages; save alone sends the exact three-channel edit',async t=>{
    const {page,posts}=await setup(t);await open(page);
    assert.equal(await page.locator('[data-save]').isDisabled(),true);
    await page.locator('[data-block]').click();
    assert.deepEqual(await readRows(page),[{exchange:'all',desktop:'on',mute:'none',cards:'on',mobile:'on'}]);
    assert.match(await page.locator('.bp-rule-result').textContent(),/尚未保存/);
    assert.equal(posts().length,0);assert.equal(await page.evaluate(()=>window.savedCalls),0);
    assert.equal(await page.locator('[data-save]').isEnabled(),true);
    await page.locator('[data-save]').click();await saved(page);
    assert.equal(posts().length,1);assert.equal(posts()[0].route,'edit-coins');
    assert.deepEqual(posts()[0].body.changes,['desktop','cards','mobile'].map(channel=>({channel,coin:'PTB',exchange:'all',before:null,after:true})));
    assert.equal(await page.evaluate(()=>window.savedCalls),1);
    assert.equal(await page.locator('[data-save]').isDisabled(),true);
  });

  await t.test('outside card only offers Manage; Close and Escape discard staged blocking',async t=>{
    const {page,posts,state}=await setup(t);
    await page.evaluate(async()=>{const {createCardPolicy}=await import('/card-policy.js');const p=createCardPolicy(document.querySelector('#toolbar'),()=>{});p.decorate(document.querySelector('.bp-card'),{asset:'PTB'});});
    assert.equal(await page.locator('[data-action="block-all"]').count(),0);
    assert.equal(await page.locator('[data-action="manage-rules"]').count(),1);
    await page.locator('[data-action="manage-rules"]').click();
    await page.locator('.bp-rule-result').filter({hasText:'已加载云端规则'}).waitFor();
    await page.locator('[data-block]').click();
    await page.locator('.bp-rule-result').filter({hasText:'尚未保存'}).waitFor();
    assert.equal(posts().length,0);
    await page.locator('footer [data-close]').click();await page.locator('dialog').waitFor({state:'detached'});
    await page.locator('[data-action="manage-rules"]').click();
    await page.locator('.bp-rule-result').filter({hasText:'已加载云端规则'}).waitFor();
    assert.deepEqual(await readRows(page),[{exchange:'all',desktop:'none',mute:'none',cards:'none',mobile:'none'}]);
    await page.locator('[data-block]').click();await page.keyboard.press('Escape');
    await page.locator('dialog').waitFor({state:'detached'});
    assert.equal(posts().length,0);assert.deepEqual(state(),fixture());
  });

  await t.test('block selects desktop hide and preserves other scopes and unsaved edits',async t=>{
    const data=fixture();rule(data,'mute','all',true);rule(data,'cards','gate',false);
    const {page,posts}=await setup(t,{data});await open(page);
    const gate=page.locator('.bp-rule-row').nth(1);
    await gate.locator('[data-block-mode="cards"]').selectOption('on');
    await gate.locator('[data-desktop-mode]').selectOption('mute');
    assert.equal(await page.locator('[data-block]').isEnabled(),true);
    await page.locator('[data-block]').click();await page.locator('[data-block]').click();
    assert.deepEqual(await readRows(page),[{exchange:'all',desktop:'on',mute:'none',cards:'on',mobile:'on'},{exchange:'gate',desktop:'none',mute:'on',cards:'on',mobile:'none'}]);
    assert.equal(posts().length,0);
    await page.locator('[data-save]').click();await saved(page);
    const edits=posts()[0].body.changes;
    assert.equal(edits.length,6);
    assert.deepEqual(edits.find(c=>c.channel==='mute'&&c.exchange==='all'),{channel:'mute',coin:'PTB',exchange:'all',before:true,after:null});
    assert.deepEqual(edits.filter(c=>c.exchange==='gate').sort((a,b)=>a.channel.localeCompare(b.channel)),[{channel:'cards',coin:'PTB',exchange:'gate',before:false,after:true},{channel:'mute',coin:'PTB',exchange:'gate',before:null,after:true}]);
  });

  await t.test('blocking adds a missing all scope without replacing scoped rules',async t=>{
    const data=fixture();rule(data,'mute','gate',true);rule(data,'cards','gate',false);
    const {page,posts}=await setup(t,{data});await open(page,true);await page.locator('[data-block]').click();
    assert.deepEqual(await readRows(page),[{exchange:'gate',desktop:'none',mute:'on',cards:'off',mobile:'none'},{exchange:'all',desktop:'on',mute:'none',cards:'on',mobile:'on'}]);
    assert.equal(posts().length,0);
  });

  for(const firstPostFailure of ['partial','network'])await t.test(`${firstPostFailure} save failure preserves the exact request for explicit retry`,async t=>{
    const {page,posts}=await setup(t,{firstPostFailure});await open(page,true);
    await page.locator('[data-save]').click();await page.locator('[data-retry]').waitFor({state:'visible'});
    await page.waitForFunction(()=>!document.querySelector('[data-retry]').disabled);
    assert.equal(posts().length,1);assert.equal(await page.locator('[data-save]').isDisabled(),true);assert.equal(await page.locator('[data-block]').isDisabled(),true);
    await page.locator('[data-retry]').click();await saved(page);
    assert.equal(posts().length,2);assert.deepEqual(posts()[1],posts()[0]);
    assert.equal(await page.evaluate(()=>window.savedCalls),firstPostFailure==='partial'?2:1);
  });

  for(const loadStatus of [401,403])await t.test(`${loadStatus} rule load never allows staging or saving`,async t=>{
    const {page,posts}=await setup(t,{loadStatus});await page.evaluate(()=>window.openTestManager());
    await page.locator('.bp-rule-result').filter({hasText:'测试规则读取被拒绝'}).waitFor();
    assert.equal(await page.locator('[data-save]').isDisabled(),true);assert.equal(await page.locator('[data-block]').isDisabled(),true);
    assert.equal(posts().length,0);assert.equal(await page.locator('.bp-rule-row').count(),0);
  });

  await t.test('loading and identity changes reject late responses and writes',async t=>{
    const loadGate=deferred(),{page,posts,requests}=await setup(t,{loadGate});
    const requested=page.waitForRequest(request=>request.url().endsWith('/coin-blocks'));
    await page.evaluate(()=>window.openTestManager());await requested;
    await page.locator('.bp-rule-result').filter({hasText:'正在加载'}).waitFor();
    assert.equal(await page.locator('[data-block]').isDisabled(),true);assert.equal(await page.locator('[data-save]').isDisabled(),true);
    await page.evaluate(()=>{localStorage.setItem('radar-settings-token','different-isolated-code');window.dispatchEvent(new Event('storage'));});
    loadGate.resolve();
    await page.locator('.bp-rule-result').filter({hasText:'连接码已切换'}).waitFor();
    assert.equal(requests.filter(r=>r.route==='coin-blocks').length,1);assert.equal(posts().length,0);
    assert.equal(await page.locator('.bp-rule-row').count(),0);assert.equal(await page.locator('[data-save]').isDisabled(),true);
  });

  await t.test('switching identity after staging disables save and does not write',async t=>{
    const {page,posts}=await setup(t);await open(page,true);
    await page.evaluate(()=>{localStorage.setItem('radar-settings-token','different-isolated-code');window.dispatchEvent(new Event('storage'));document.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));});
    assert.equal(await page.locator('[data-save]').isDisabled(),true);assert.equal(await page.locator('[data-block]').isDisabled(),true);assert.equal(posts().length,0);
  });

  await t.test('duplicate scopes remain invalid and cannot be silently overwritten by block',async t=>{
    const {page,posts}=await setup(t);await open(page);await page.locator('[data-add]').click();
    await page.locator('.bp-rule-row').nth(1).locator('[data-scope]').selectOption('all');
    assert.match(await page.locator('.bp-rule-review').textContent(),/重复/);
    assert.equal(await page.locator('[data-block]').isDisabled(),true);assert.equal(await page.locator('[data-save]').isDisabled(),true);assert.equal(posts().length,0);
  });

  await t.test('already saved three-channel blocking has no pending change or extra write',async t=>{
    const data=fixture();for(const c of ['desktop','cards','mobile'])rule(data,c,'all',true);
    const {page,posts}=await setup(t,{data});await open(page);await page.locator('[data-block]').click();
    await page.locator('.bp-rule-result').filter({hasText:'无需重复保存'}).waitFor();
    assert.equal(await page.locator('[data-save]').isDisabled(),true);assert.equal(posts().length,0);
  });

  await t.test('desktop push is one three-option select and saving switches the exact mode',async t=>{
    const data=fixture();rule(data,'desktop','all',true);rule(data,'cards','gate',true);
    const {page,posts}=await setup(t,{data});await open(page);
    const choice=page.locator('[data-desktop-mode]').first();
    assert.deepEqual(await choice.locator('option').allTextContents(),['正常推送','仅静音','屏蔽']);
    assert.equal(await choice.inputValue(),'hide');
    assert.equal(await page.locator('select[data-channel="desktop"],select[data-channel="mute"]').count(),0);
    await choice.selectOption('mute');assert.equal(posts().length,0);
    assert.match(await page.locator('.bp-rule-review').textContent(),/电脑推送：屏蔽 → 仅静音/);
    assert.equal((await page.locator('.bp-rule-review').textContent()).match(/电脑推送：/g).length,1);
    await page.locator('[data-save]').click();await saved(page);
    assert.deepEqual(posts()[0].body.changes,[{channel:'desktop',coin:'PTB',exchange:'all',before:true,after:null},{channel:'mute',coin:'PTB',exchange:'all',before:null,after:true}]);
    assert.equal(await page.locator('.bp-rule-result').textContent(),'全部交易所 · 电脑推送：仅静音（已保存）');
    await page.locator('[data-desktop-mode]').first().selectOption('none');
    await page.locator('[data-save]').click();await saved(page);
    assert.deepEqual(posts()[1].body.changes,[{channel:'mute',coin:'PTB',exchange:'all',before:true,after:null}]);
    assert.equal(await page.locator('.bp-rule-result').textContent(),'全部交易所 · 电脑推送：正常推送（已保存）');
    await page.locator('[data-desktop-mode]').last().selectOption('hide');
    await page.locator('[data-save]').click();await saved(page);
    assert.deepEqual(posts()[2].body.changes,[{channel:'desktop',coin:'PTB',exchange:'gate',before:null,after:true}]);
    assert.equal(await page.locator('.bp-rule-result').textContent(),'Gate · 电脑推送：屏蔽（已保存）');
  });

  await t.test('partial desktop mode save reports the actual merged state and retains retry',async t=>{
    const data=fixture();rule(data,'desktop','all',true);const {page,posts}=await setup(t,{data,firstPostFailure:'desktop-partial'});await open(page);
    await page.locator('[data-desktop-mode]').selectOption('mute');await page.locator('[data-save]').click();await page.locator('[data-retry]').waitFor({state:'visible'});
    await page.waitForFunction(()=>!document.querySelector('[data-retry]').disabled);
    const text=await page.locator('.bp-rule-result').textContent();assert.equal((text.match(/电脑推送：/g)||[]).length,1);assert.match(text,/电脑推送：正常推送（当前已保存；未完成：仅静音 测试静音未保存）/);assert.doesNotMatch(text,/电脑推送：仅静音（已保存）/);
    await page.locator('[data-retry]').click();await saved(page);assert.deepEqual(posts()[1],posts()[0]);assert.equal(await page.locator('.bp-rule-result').textContent(),'全部交易所 · 电脑推送：仅静音（已保存）');
  });

  for(const original of [{desktop:true,mute:true},{desktop:false,mute:false}])await t.test(`untouched legacy desktop values ${JSON.stringify(original)} are preserved`,async t=>{
    const data=fixture();for(const [channel,value] of Object.entries(original))rule(data,channel,'all',value);
    const {page,posts}=await setup(t,{data});await open(page);
    assert.equal(await page.locator('[data-save]').isDisabled(),true);
    assert.equal(await page.locator('[data-desktop-mode]').inputValue(),original.desktop?'hide':'none');
    await page.locator('[data-block-mode="cards"]').selectOption('on');
    await page.locator('[data-save]').click();await saved(page);
    assert.deepEqual(posts()[0].body.changes,[{channel:'cards',coin:'PTB',exchange:'all',before:null,after:true}]);
  });

  for(const channel of ['cards','mobile'])await t.test(`${channel} uses normal/block labels and changes only on explicit save`,async t=>{
    const data=fixture();rule(data,channel,'all',true);const {page,posts}=await setup(t,{data});await open(page);
    const choice=page.locator(`[data-block-mode="${channel}"]`);
    assert.deepEqual(await choice.locator('option').allTextContents(),['正常推送','屏蔽']);
    await choice.selectOption('none');assert.equal(posts().length,0);assert.match(await page.locator('.bp-rule-review').textContent(),/本范围草稿/);
    await page.locator('footer [data-close]').click();await page.locator('dialog').waitFor({state:'detached'});await open(page);
    assert.equal(await choice.inputValue(),'on');await choice.selectOption('none');await page.locator('[data-save]').click();await saved(page);
    assert.deepEqual(posts()[0].body.changes,[{channel,coin:'PTB',exchange:'all',before:true,after:null}]);
    assert.match(await page.locator('.bp-rule-result').textContent(),/正常推送（已保存）/);
    await choice.selectOption('on');assert.match(await page.locator('.bp-rule-result').textContent(),/草稿尚未保存/);
    await page.locator('[data-save]').click();await saved(page);
    assert.deepEqual(posts()[1].body.changes,[{channel,coin:'PTB',exchange:'all',before:null,after:true}]);
    assert.match(await page.locator('.bp-rule-result').textContent(),/屏蔽（已保存）/);
    assert.doesNotMatch(await page.locator('dialog').innerText(),/未设置|已启用|已停用|电脑静音/);
  });

  for(const channel of ['cards','mobile'])await t.test(`legacy inactive ${channel} displays normal and remains untouched until a user choice`,async t=>{
    const data=fixture();rule(data,channel,'all',false);const {page,posts}=await setup(t,{data});await open(page);
    assert.equal(await page.locator(`[data-block-mode="${channel}"]`).inputValue(),'none');assert.equal(await page.locator('[data-save]').isDisabled(),true);
    const other=channel==='cards'?'mobile':'cards';await page.locator(`[data-block-mode="${other}"]`).selectOption('on');await page.locator('[data-save]').click();await saved(page);
    assert.deepEqual(posts()[0].body.changes,[{channel:other,coin:'PTB',exchange:'all',before:null,after:true}]);
    await page.locator(`[data-block-mode="${channel}"]`).selectOption('none');await page.locator('[data-save]').click();await saved(page);
    assert.deepEqual(posts()[1].body.changes,[{channel,coin:'PTB',exchange:'all',before:false,after:null}]);
  });

  for(const width of [1280,393])await t.test(`draft dialog fits ${width}px viewport and exposes save`,async t=>{
    const {page,posts}=await setup(t,{viewport:{width,height:852}});await open(page,true);
    const geometry=await page.locator('dialog').evaluate(dialog=>{const r=dialog.getBoundingClientRect();return {left:r.left,right:r.right,viewport:innerWidth,scrollWidth:dialog.scrollWidth,clientWidth:dialog.clientWidth};});
    assert.ok(geometry.left>=0&&geometry.right<=geometry.viewport,JSON.stringify(geometry));
    assert.ok(geometry.scrollWidth<=geometry.clientWidth+1,JSON.stringify(geometry));
    assert.equal(await page.locator('[data-save]').isVisible(),true);assert.equal(await page.locator('[data-save]').isEnabled(),true);assert.equal(posts().length,0);
    if(process.env.RADAR_TEST_SCREENSHOT_DIR){await mkdir(process.env.RADAR_TEST_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:join(process.env.RADAR_TEST_SCREENSHOT_DIR,`coin-rule-save-${width}.png`),fullPage:true});}
  });
});
