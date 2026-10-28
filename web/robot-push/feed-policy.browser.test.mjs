import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';

let engines;
try{const {chromium,webkit}=createRequire(import.meta.url)('playwright');engines={chromium,webkit};}
catch(error){if(process.env.RADAR_BROWSER_TESTS==='1')throw error;}
const digest=message=>createHash('sha256').update(JSON.stringify([message.id,message.title,message.body,message.sentAt])).digest('hex');
const makeMessage=(id,coin='UNITREE',groupId='ordinary',stamp=Date.now()-60000)=>({id,groupId,senderType:'bot',title:`R0 +0.4% | ${coin} | FF`,body:`${coin} 期货套利\n买入：GATE\n卖出：ASTER`,sentAt:new Date(stamp).toISOString(),actions:[]});

test('website feed uses saved per-code decisions for ordinary, pinned, history and sound', {skip:!engines&&'Playwright unavailable'},async t=>{
  for(const [engineName,engine] of Object.entries(engines))for(const width of [1440,393,320])await t.test(`${engineName} ${width}px`,async t=>{
    const browser=await engine.launch({headless:true});t.after(()=>browser.close());
    const context=await browser.newContext({viewport:{width,height:852}}),page=await context.newPage();
    const errors=[],requests=[];page.on('pageerror',error=>errors.push(error.message));
    let source={messages:[makeMessage('unitree'),makeMessage('btc','BTC'),makeMessage('muted','PREDICT')],pinned:makeMessage('strong','UNITREE','pinned'),updatedAt:new Date().toISOString(),sourceConnected:true};
    let hidden=true,fail=false,enabled=true,gate=null,apiCount=0;
    const result=token=>({revision:1,desktopEnabled:enabled,decisions:Object.fromEntries([...source.messages,...(source.pinned?[source.pinned]:[])].map(message=>[message.id,{fingerprint:digest(message),action:token==='Bearer second'?'allow':message.title.includes('PREDICT')?'mute':hidden&&message.title.includes('UNITREE')?'hide':'allow'}]))});
    await context.addInitScript(()=>{
      localStorage.setItem('radar-settings-token','first');localStorage.setItem('robot-push-ui',JSON.stringify({enabled:false,sound:true}));
      window.audioStarts=0;
      window.AudioContext=class {state='running';destination={};async resume(){}async suspend(){this.state='suspended';}async decodeAudioData(){return {};}createBufferSource(){return {connect(){},disconnect(){},stop(){},start(){window.audioStarts++;}};}};
    });
    await context.route('**/*',async route=>{
      const req=route.request(),url=new URL(req.url()),name=url.pathname.split('/').at(-1);requests.push({path:url.pathname,method:req.method()});
      if(url.origin!=='https://feed-rule.test')return route.abort('blockedbyclient');
      if(url.pathname==='/radar/push-test/api/message-decisions'){
        apiCount++;const response=result(req.headers().authorization),failure=fail,wait=gate;if(wait)await wait;
        try{return await route.fulfill({status:failure?403:200,json:failure?{error:'Synthetic denied'}:response});}catch{return;}
      }
      if(name==='push-subscription.js')return route.fulfill({contentType:'text/javascript',body:`export function subscribePush(name,handlers){window.deliverFeed=handlers.data;queueMicrotask(()=>handlers.data(${JSON.stringify(source)}));return ()=>{};}`});
      if(name==='notice.wav')return route.fulfill({contentType:'audio/wav',body:'synthetic'});
      if(url.pathname==='/radar/robot-push/'){
        const html=(await readFile(new URL('index.html',import.meta.url),'utf8')).replace(/<script[\s\S]*?<\/script>/g,'').replace('<main>','<main class="feed-pane">').replace('</body>','<script type="module" src="./page.js"></script></body>');
        return route.fulfill({contentType:'text/html',body:html});
      }
      if(/^[a-z0-9.-]+\.(js|css)$/i.test(name)){
        try{return await route.fulfill({contentType:name.endsWith('.css')?'text/css':'text/javascript',body:await readFile(new URL(name,import.meta.url),'utf8')});}catch{}
      }
      return route.fulfill({status:404,body:'No fixture'});
    });
    const ids=()=>page.locator('#feed > article').evaluateAll(nodes=>nodes.map(node=>node.dataset.id));
    const refresh=()=>page.evaluate(()=>document.dispatchEvent(new Event('radar-rules-saved')));
    await page.goto('https://feed-rule.test/radar/robot-push/');
    await page.locator('#feed > [data-id="btc"]').waitFor();
    assert.deepEqual(await ids(),['btc','muted']);assert.equal(await page.locator('#pinned > article').count(),0);assert.equal(await page.evaluate(()=>window.audioStarts),0);

    hidden=false;await refresh();await page.locator('#feed > [data-id="unitree"]').waitFor();
    assert.equal(await page.locator('#pinned > [data-id="strong"]').count(),1);assert.equal(await page.evaluate(()=>window.audioStarts),0);
    await page.locator('#feed > [data-id="unitree"]').click();await page.locator('#message-detail[open]').waitFor();
    hidden=true;
    if(width<900)await page.evaluate(()=>{const event=new Event('touchstart',{bubbles:true});Object.defineProperty(event,'touches',{value:[{clientY:100}]});document.querySelector('#board').dispatchEvent(event);});
    const revoked=await page.evaluate(()=>{document.dispatchEvent(new Event('radar-rules-saved'));return {count:document.querySelectorAll('#feed > article,#pinned > article').length,detail:document.querySelector('#message-detail').open};});
    assert.deepEqual(revoked,{count:0,detail:false});
    if(width<900)await page.evaluate(()=>{const event=new Event('touchend',{bubbles:true});Object.defineProperty(event,'touches',{value:[]});document.querySelector('#board').dispatchEvent(event);});
    await page.locator('#feed > [data-id="btc"]').waitFor();
    assert.deepEqual(await ids(),['btc','muted']);

    // New muted arrivals stay visible and silent. Allow arrivals sound once.
    source.messages.push(makeMessage('new-muted','PREDICT','ordinary',Date.now()+10));await page.evaluate(data=>window.deliverFeed(data),source);
    await page.dispatchEvent('body','focus');await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
    await page.locator('#feed > [data-id="new-muted"]').waitFor();assert.equal(await page.evaluate(()=>window.audioStarts),0);
    source.messages.push(makeMessage('new-allowed','BTC','ordinary',Date.now()+10));await page.evaluate(data=>window.deliverFeed(data),source);await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
    await page.locator('#feed > [data-id="new-allowed"]').waitFor();assert.equal(await page.evaluate(()=>window.audioStarts),1);
    await refresh();await page.locator('#feed > [data-id="btc"]').waitFor();assert.equal(await page.evaluate(()=>window.audioStarts),1);

    // Same ID is now a blocked coin; old proof must not flash the changed row.
    source.messages=source.messages.map(message=>message.id==='btc'?{...message,title:'R0 +0.4% | UNITREE | FF',body:'UNITREE changed content'}:message);
    await page.evaluate(data=>window.deliverFeed(data),source);
    assert.equal(await page.locator('#feed > [data-id="btc"]').count(),0);
    await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await page.locator('#feed > [data-id="muted"]').waitFor();

    // The previous request cannot restore a cleared identity, even if it finishes late.
    let release;gate=new Promise(resolve=>{release=resolve;});const before=apiCount;await refresh();await page.waitForFunction(()=>document.querySelectorAll('#feed > article').length===0);
    while(apiCount===before)await new Promise(resolve=>setTimeout(resolve,10));
    const switched=await page.evaluate(()=>{localStorage.setItem('radar-settings-token','second');window.dispatchEvent(new StorageEvent('storage',{key:'radar-settings-token'}));return document.querySelectorAll('#feed > article').length;});assert.equal(switched,0);
    gate=null;release();await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await page.locator('#feed > [data-id="unitree"]').waitFor();
    assert.equal(await page.locator('#pinned > [data-id="strong"]').count(),1);

    fail=true;await refresh();assert.equal(await page.locator('#feed > article').count(),0);await page.locator('#empty').filter({hasText:'校验'}).waitFor();
    await page.evaluate(()=>{localStorage.removeItem('radar-settings-token');window.dispatchEvent(new StorageEvent('storage',{key:'radar-settings-token'}));});
    await page.locator('#feed > [data-id="unitree"]').waitFor();assert.equal(await page.locator('#pinned > [data-id="strong"]').count(),1);
    assert.equal(await page.evaluate(()=>window.audioStarts),1);assert.equal(requests.some(request=>request.method==='POST'),false);assert.deepEqual(errors,[]);
  });
});
