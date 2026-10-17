import {applySnapshot} from './snapshot-delta.js';
const supported=new Set(['/api/market-stats','/radar/robot-push/feed.json','/radar/robot-push/basispulse.json']);
export function createSnapshotFetch(fetcher=(...args)=>globalThis.fetch(...args),base=()=>globalThis.location?.href){
 const snapshots=new Map();
 return async function snapshotFetch(input,init={}){
  const originBase=base();if(!originBase||input instanceof Request)return fetcher(input,init);
  const url=new URL(String(input),originBase);
  if(url.origin!==new URL(originBase).origin||!supported.has(url.pathname)||url.search||(init.method&&init.method!=='GET'))return fetcher(input,init);
  const previous=snapshots.get(url.href);
  for(let attempt=0;attempt<2;attempt++){
   const headers=new Headers(init.headers);headers.delete('If-None-Match');headers.delete('X-Radar-Base');
   if(!attempt&&previous){headers.set('If-None-Match',previous.etag);headers.set('X-Radar-Base',previous.etag);}
   const response=await fetcher(input,{...init,headers,cache:'no-store'});
   if(!response.ok&&response.status!==304)return response;
   let data;
   try{
    if(response.status===304){if(attempt||!previous)throw Error('Missing snapshot');data=previous.data;}
    else if(response.headers.get('Content-Type')?.includes('application/vnd.radar.delta+json')){
     const delta=await response.json();
     if(attempt||!previous||delta.base!==previous.etag)throw Error('Snapshot base mismatch');
     data=applySnapshot(previous.data,delta.ops);
    }else{
     if(!response.headers.get('Content-Type')?.includes('application/json'))return response;
     data=await response.json();
    }
   }catch(error){if(!attempt)continue;throw error;}
   init.signal?.throwIfAborted();
   const body=response.status===304?previous.body:JSON.stringify(data),etag=response.headers.get('ETag');
   if(etag&&body.length<=8000000)snapshots.set(url.href,{etag,data,body});else snapshots.delete(url.href);
   const output=new Headers(response.headers);output.set('Content-Type','application/json');output.delete('Content-Encoding');output.delete('Content-Length');output.delete('X-Radar-Unchanged');if(response.status===304)output.set('X-Radar-Unchanged','1');
   return new Response(body,{status:200,headers:output});
  }
 };
}
export const snapshotFetch=createSnapshotFetch();
