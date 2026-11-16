import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const code=readFileSync(new URL('./fixtures/geometry-probe.js',import.meta.url),'utf8').split('/* Temporary geometry-only probe')[1];
function run({expired=false,coarse=true,total=0,storageError=false,touch=0,screenSize=820}={}) {
 const requests=[],timers=[];let removed=0,appended=0;
 const body={scrollWidth:820,getBoundingClientRect:()=>({left:0,width:820}),appendChild:()=>appended++};
 const date=class extends Date {static now(){return Date.UTC(2026,10,expired?17:14);}};
 const context={URL,Date:date,Number,Math,JSON,screen:{width:screenSize,height:screenSize,availWidth:screenSize,availHeight:screenSize},
  window:{visualViewport:{width:820,height:1100,offsetLeft:0,offsetTop:0,scale:1}},
  innerWidth:820,innerHeight:1100,outerWidth:820,outerHeight:1180,devicePixelRatio:2,
  matchMedia:q=>({matches:q.includes('coarse')?coarse:true}),navigator:{standalone:true,maxTouchPoints:touch},
  location:{href:'https://example.com/radar/?secret=NEVER-SEND#private',pathname:'/radar/',origin:'https://example.com'},
  document:{currentScript:{src:'https://example.com/radar/robot-push/home-launch-abc.js?v=old'},readyState:'complete',body,
   documentElement:{clientWidth:820,scrollWidth:820},querySelector:()=>null,
   createElement:()=>({style:{},remove:()=>removed++})},
  getComputedStyle:()=>({paddingTop:'0px',paddingRight:'40px',paddingBottom:'0px',paddingLeft:'0px'}),
  sessionStorage:{getItem:()=>{if(storageError)throw Error('blocked');return String(total);},setItem:(_,v)=>{total=Number(v);}},
  setTimeout:f=>timers.push(f),fetch:(url,options)=>{requests.push({url,options});return Promise.resolve();}};
 vm.runInNewContext('/* Temporary geometry-only probe'+code,context);timers.forEach(f=>f());
 return {requests,total,removed,appended};
}
test('records only geometry to the same static asset; no page query or fragment',()=>{
 const r=run();assert.equal(r.requests.length,3);assert.equal(r.removed,r.appended);
 for(const req of r.requests){const u=new URL(req.url);assert.equal(u.pathname,'/radar/robot-push/home-launch-abc.js');assert.equal(u.searchParams.has('v'),false);assert.ok(!req.url.includes('NEVER'));assert.equal(req.options.referrerPolicy,'no-referrer');const d=JSON.parse(u.searchParams.get('radar_geometry_v1'));assert.deepEqual(d.safe,[0,40,0,0]);assert.equal(d.page,'main');}
});
test('expires without requests',()=>assert.equal(run({expired:true}).requests.length,0));
test('desktop stays untouched',()=>assert.equal(run({coarse:false}).requests.length,0));
test('session cap applies across pages',()=>{assert.equal(run({total:17}).requests.length,1);assert.equal(run({total:18}).requests.length,0);});
test('blocked storage cannot break navigation or send unbounded probes',()=>assert.equal(run({storageError:true}).requests.length,0));

test('small outer-screen claims and touch devices with a fine primary pointer still report',()=>{assert.equal(run({screenSize:400}).requests.length,3);assert.equal(run({coarse:false,touch:5}).requests.length,3);});
