import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createPushBroker} from './push-broker.js';
import {createSnapshotFetch} from './snapshot-fetch.js';
import {radarMatrix} from './basispulse-transfers.js';
function fixture(read){
  let now=0,seq=0;const jobs=new Map();
  const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve()};
  const advance=async ms=>{const end=now+ms;for(;;){const next=[...jobs].filter(([,j])=>j.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;now=next[1].at;jobs.delete(next[0]);next[1].fn();await flush();}now=end;await flush()};
  const broker=createPushBroker(read,{clock:()=>now,later:(fn,ms)=>{const id=++seq;jobs.set(id,{fn,at:now+ms});return id},cancel:id=>jobs.delete(id)});
  return {broker,advance,flush};
}
test('two visible tabs share one request per stream; no transfer or market calls',async()=>{
  const calls=[],a=[],b=[];const f=fixture(async name=>{calls.push(name);return {sequence:calls.length}});
  f.broker.update('a',['feed','basispulse'],m=>a.push(m));f.broker.update('b',['feed','basispulse'],m=>b.push(m));await f.flush();
  assert.deepEqual(calls,['feed','basispulse']);assert.equal(a.length,2);assert.equal(b.length,2);
  await f.advance(4999);assert.equal(calls.length,2);await f.advance(1);assert.equal(calls.length,4);
  f.broker.update('a',[],()=>{});await f.advance(5000);assert.equal(a.length,4);assert.equal(b.length,6);
  f.broker.update('b',[],()=>{});await f.advance(60000);assert.equal(calls.length,6);
  f.broker.update('b',['feed'],m=>b.push(m));await f.flush();assert.equal(calls.length,7);f.broker.close();
});
test('hiding aborts in-flight work and late completion cannot overwrite resumed data',async()=>{
  const pending=[],received=[];const f=fixture((name,signal)=>new Promise(resolve=>pending.push({signal,resolve})));
  f.broker.update('a',['basispulse'],m=>received.push(m));f.broker.update('a',[],()=>{});assert.equal(pending[0].signal.aborted,true);
  f.broker.update('a',['basispulse'],m=>received.push(m));pending[1].resolve('new');await f.flush();pending[0].resolve('old');await f.flush();
  assert.deepEqual(received.map(m=>m.data),['new']);f.broker.close();
});
test('lost tab lease stops unattended polling; heartbeats do not multiply requests',async()=>{
  let calls=0;const f=fixture(async()=>++calls);
  f.broker.update('a',['feed'],()=>{});await f.flush();
  for(let i=0;i<10;i++)f.broker.update('a',['feed'],()=>{});
  assert.equal(calls,1);await f.advance(100000);const stopped=calls;assert.equal(stopped,10);await f.advance(100000);assert.equal(calls,stopped);f.broker.close();
});
test('outage backs off, successful recovery broadcasts immediately',async()=>{
  let calls=0,fail=true;const events=[];const f=fixture(async()=>{calls++;if(fail)throw Error();return 'recovered'});
  f.broker.update('a',['feed'],m=>events.push(m));await f.flush();await f.advance(5000);assert.equal(calls,2);
  await f.advance(9999);assert.equal(calls,2);fail=false;await f.advance(1);assert.equal(events.at(-1).data,'recovered');await f.advance(5000);assert.equal(calls,4);f.broker.close();
});
test('conditional 304 and delta keep original source timestamps and messages',async()=>{
  const base={updatedAt:'2026-10-09T00:00:00Z',messages:[{id:'a',body:'original'}]}, requests=[];
  const responses=[new Response(JSON.stringify(base),{headers:{'Content-Type':'application/json',ETag:'"a"'}}),new Response(null,{status:304,headers:{ETag:'"a"'}}),new Response(JSON.stringify({base:'"a"',ops:[['set',['updatedAt'],'2026-10-09T00:00:05Z']]}),{headers:{'Content-Type':'application/vnd.radar.delta+json',ETag:'"b"'}})];
  const read=createSnapshotFetch(async(u,init)=>{requests.push(init);return responses.shift()},()=> 'https://example.test/radar/robot-push/');
  assert.deepEqual(await (await read('./feed.json')).json(),base);assert.deepEqual(await (await read('./feed.json')).json(),base);
  assert.deepEqual(await (await read('./feed.json')).json(),{...base,updatedAt:'2026-10-09T00:00:05Z'});
  assert.equal(requests[1].headers.get('If-None-Match'),'"a"');assert.equal(requests[2].headers.get('X-Radar-Base'),'"a"');
});
test('broken delta recovers once with full snapshot, never applies a mismatched base',async()=>{
  const responses=[new Response('{"messages":[]}',{headers:{'Content-Type':'application/json',ETag:'"a"'}}),new Response('{"base":"wrong","ops":[]}',{headers:{'Content-Type':'application/vnd.radar.delta+json'}}),new Response('{"messages":[1]}',{headers:{'Content-Type':'application/json',ETag:'"b"'}})];const headers=[];
  const read=createSnapshotFetch(async(u,init)=>{headers.push(init.headers);return responses.shift()},()=> 'https://example.test/radar/robot-push/');await read('./feed.json');assert.deepEqual(await(await read('./feed.json')).json(),{messages:[1]});assert.equal(headers[2].has('X-Radar-Base'),false);
});
test('push-only wallet evidence stays time bounded and never claims an automatic query',()=>{
  const now=Date.now(),legs=[{exchange:'gate',symbol:'ABCUSDT'}],wallet={key:'gate:ABC',checkedAt:new Date(now).toISOString(),expiresAt:new Date(now+120000).toISOString(),refreshFailed:false,text:'【官方｜Gate】：充开/提关 ETH'};
  const fresh=radarMatrix(legs,()=>null,now,[wallet]);assert.deepEqual(fresh.rows[0].cells,[['open','closed']]);assert.doesNotMatch(fresh.text,/正在查询|自动重试/);
  const expired=radarMatrix(legs,()=>null,now+120001,[wallet]);assert.deepEqual(expired.rows[0].cells,[['unknown','unknown']]);
});

test('unchanged snapshots send only a heartbeat; a new tab receives the full cached snapshot',async()=>{
 const data={messages:[{id:'a',body:'synthetic'}]},events=[],joined=[];const f=fixture(async()=>data);
 f.broker.update('a',['feed'],m=>events.push(m));await f.flush();await f.advance(5000);
 assert.deepEqual(events.map(m=>m.type),['data','unchanged']);assert.equal('data' in events[1],false);
 f.broker.update('b',['feed'],m=>joined.push(m));assert.equal(joined[0].data,data);
 f.broker.close();
});
test('304 reuses the parsed snapshot without altering original freshness',async()=>{
 const {createPushReader}=await import('./push-reader.js');let calls=0;
 const read=createPushReader(async()=>++calls===1?new Response('{"messages":[],"updatedAt":"original"}',{headers:{'Content-Type':'application/json'}}):{ok:true,headers:new Headers({'X-Radar-Unchanged':'1'}),json(){throw Error('304 should not parse again')}});
 const a=await read('feed',new AbortController().signal),b=await read('feed',new AbortController().signal);assert.equal(a,b);assert.equal(b.updatedAt,'original');
});
