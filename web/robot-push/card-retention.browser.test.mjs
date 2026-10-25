import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
let chromium;
try{({chromium}=createRequire(import.meta.url)('playwright'));}catch(e){if(process.env.RADAR_BROWSER_TESTS==='1')throw e;}
const model=await readFile(new URL('./basispulse-model.js',import.meta.url),'utf8');
const source=await readFile(new URL('./basispulse.js',import.meta.url),'utf8');
const renderers=[['source',null]];
if(process.env.RADAR_RETENTION_RENDERER)renderers.push(['deployed bundle',await readFile(process.env.RADAR_RETENTION_RENDERER,'utf8')]);
const stub=`export function cardNode(c){const card=document.createElement('article');card.className='bp-card';card.dataset.id=c.data.id;const age=document.createElement('span');card.append(age);return {card,age,stamp:JSON.stringify([c.data,[]])};}`;
const policy=`export function createCardPolicy(){return {visible:c=>!window.blocked,decorate(){},summary(rows){window.summaryRows=rows.map(x=>x.data.id);}};}`;
for(const [name,compiled] of renderers)test('shared thirty second retention renders consistently: '+name,{skip:!chromium},async t=>{
 const browser=await chromium.launch({headless:true,args:['--enable-logging=stderr']});t.after(()=>browser.close());
 const context=await browser.newContext();t.after(()=>context.close());const page=await context.newPage();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));t.after(()=>assert.deepEqual(errors,[]));
 const harness=compiled?`import {Opportunities,opportunityState} from '/model.js';import {cardNode} from '/card.js';import {createCardPolicy} from '/policy.js';
 let Rn=new Opportunities(),Ve=new Map(),W=null,Mt=false,Fn=-Infinity,li=10000;
 const Xe=document.querySelector('.bp-board'),Ne=document.querySelector('.bp-count'),kt=document.querySelector('.bp-empty');
 const __radarScroll={defer:()=>window.defer},__radarPreserve=(board,fn)=>fn(),En=opportunityState,Dn=cardNode,Ln=()=>[],ci=()=>'',di=()=>'';
 const __cardPolicy=createCardPolicy();${compiled}
 window.tick=Nt;window.ingest=e=>{W=e;Rn.ingest(e);Nt()};window.ready=true;`:
 source.replaceAll("'./push-subscription.js'","'/subscription.js'").replaceAll("'./mobile-scroll.js'","'/scroll.js'")
 .replace(/'\.\/card-policy\.js[^']*'/,"'/policy.js'").replace(/'\.\/basispulse-model\.js[^']*'/,"'/model.js'")
 .replace(/'\.\/basispulse-card\.js[^']*'/,"'/card.js'").replace(/'\.\/basispulse-transfers\.js[^']*'/,"'/transfers.js'")+`\nwindow.tick=render;window.ready=true;`;
 const files={'/harness.js':harness,'/model.js':model,'/card.js':stub,'/policy.js':policy,
 '/subscription.js':`export function subscribePush(name,handler){window.ingest=e=>handler.data(e);}`,
 '/scroll.js':`export const mobileScrollGate={defer:()=>window.defer};export const preserveCardViewport=(board,fn)=>fn();`,
 '/transfers.js':`export const radarMatrix=()=>[];`};
 await context.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin!=='https://retention.test')return route.abort();
  if(files[u.pathname])return route.fulfill({contentType:'text/javascript',body:files[u.pathname]});
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:`<main id="basis-pane">${compiled?'<span class="bp-count"></span><section class="bp-board"></section><p class="bp-empty"></p>':''}</main><script>window.now=Date.parse('2026-10-25T00:00:00Z');Date.now=()=>window.now;window.defer=false;window.blocked=false;</script><script type="module" src="/harness.js"></script>`});
  return route.fulfill({status:404,body:''});});
 const base=Date.parse('2026-10-25T00:00:00Z'),iso=n=>new Date(base+n).toISOString();
 const card={id:'span-one',pair:'BG>BN:JCT',asset:'JCT',enteredAt:iso(-1000),validUntil:iso(120000),details:{legs:[]}};
 const packet=(at,active,retained=[],complete=true)=>({status:'connected',receivedAt:iso(at),snapshot:{sampledAt:iso(at),complete,active,retained}});
 const load=async()=>{await page.goto('https://retention.test');await page.waitForFunction(()=>window.ready);};
 const ingest=async(time,data)=>page.evaluate(({time,data})=>{window.now=time;window.ingest(data)},{time:base+time,data});
 const tick=async(time,defer=false)=>page.evaluate(({time,defer})=>{window.now=time;window.defer=defer;window.tick()},{time:base+time,defer});
 const visible=()=>page.locator('.bp-card').count();
 await load();await ingest(0,packet(0,[card]));assert.equal(await visible(),1);
 const failed=packet(1000,[],[{card,expiredAt:iso(1000)}]);
 await ingest(9000,failed);assert.equal(await visible(),1);assert.equal(await page.locator('.bp-card').getAttribute('data-state'),'expired');assert.equal(await page.locator('.bp-count').innerText(),'0 ACTIVE');
 await tick(30999,true);assert.equal(await visible(),1);
 await tick(31000,true);assert.equal(await visible(),0,'scrolling cannot extend shared thirty-second retention');
 assert.deepEqual(await page.evaluate(()=>window.summaryRows),[]);
 await load();await ingest(29000,failed);assert.equal(await visible(),1,'refresh loads the retained card');
 await tick(31000);assert.equal(await visible(),0,'refresh does not restart the timer');
 await load();await page.evaluate(()=>window.blocked=true);await ingest(2000,failed);assert.equal(await visible(),0,'retention does not bypass blocking');
 await page.evaluate(()=>window.blocked=false);await tick(3000);assert.equal(await visible(),1);
 await ingest(4000,packet(4000,[{...card,id:'span-new'}],failed.snapshot.retained));
 assert.equal(await visible(),1);assert.equal(await page.locator('.bp-card').getAttribute('data-id'),'span-new');assert.equal(await page.locator('.bp-card').getAttribute('data-state'),'active');
 await load();await ingest(32000,failed);assert.equal(await visible(),0,'late delivery does not revive expired history');
});
