import {createSnapshotFetch} from './snapshot-fetch.js';
// An explicit base also works inside a SharedWorker, whose URL is a module URL.
const metrics={requests:0,notModified:0,delta:0};
export const pushMetrics=()=>({...metrics});
const snapshotFetch=createSnapshotFetch(async(...args)=>{
  metrics.requests++;
  const response=await fetch(...args);
  if(response.status===304)metrics.notModified++;
  if(response.headers.get('Content-Type')?.includes('application/vnd.radar.delta+json'))metrics.delta++;
  return response;
});
export function createPushReader(fetchSnapshot=snapshotFetch){
 const parsed=new Map();
 return async function readPushSnapshot(name,signal){
  if(!['feed','basispulse'].includes(name))throw Error('Unknown push stream');
  const response=await fetchSnapshot(new URL('/radar/robot-push/'+name+'.json',import.meta.url).href,{credentials:'same-origin',redirect:'error',signal});
  if(!response.ok)throw Error('Push unavailable');
  if(response.headers.get('X-Radar-Unchanged')==='1'&&parsed.has(name)){signal.throwIfAborted();return parsed.get(name);}
  const data=await response.json();signal.throwIfAborted();
  if(name==='feed'&&(!data||!Array.isArray(data.messages)))throw Error('Invalid feed');
  if(name==='basispulse'&&!['connected','connecting','reconnecting','auth_required'].includes(data?.status))throw Error('Invalid cards');
  parsed.set(name,data);return data;
 };
}
export const readPushSnapshot=createPushReader();
