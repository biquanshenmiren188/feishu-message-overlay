import {createPushBroker} from './push-broker.js';
import {readPushSnapshot,pushMetrics} from './push-reader.js';
const handlers=new Map();let worker=null,local=null,readyTimer=null,hidden=false;
function receive(message){
  if(message.type==='ready'){clearTimeout(readyTimer);readyTimer=null;sync();return;}
  if(hidden||document.hidden)return;
  // Diagnostic counters contain no message bodies or credentials.
  document.documentElement.dataset.pushTransport=local?'local':'shared';
  document.documentElement.dataset.pushMetrics=JSON.stringify(message.metrics||pushMetrics());
  for(const h of handlers.get(message.name)||[])if(message.type==='data')h.data(message.data);else if(message.type==='unchanged')h.unchanged?.();else if(message.type==='error')h.error?.();
}
function sync(){
  const channels=hidden||document.hidden?[]:[...handlers.keys()];
  if(local)local.update('page',channels,receive);else worker?.port.postMessage({channels});
}
function fallback(){
  if(local)return;clearTimeout(readyTimer);readyTimer=null;
  if(worker){worker.port.postMessage({channels:[]});worker.port.close();worker=null;}
  local=createPushBroker(readPushSnapshot);sync();
}
function start(){
  if(local||worker)return;
  try{
    const url=new URL('./push-worker.js',import.meta.url);
    worker=new SharedWorker(url,{type:'module',name:'robot-push:'+url.pathname});
    worker.onerror=fallback;worker.port.onmessage=event=>receive(event.data);worker.port.start();
    readyTimer=setTimeout(fallback,3000);
  }catch{fallback();}
}
document.addEventListener('visibilitychange',sync);
window.addEventListener('pagehide',()=>{hidden=true;sync()});
window.addEventListener('pageshow',()=>{hidden=false;sync()});
// Local-only lease messages prevent a killed tab from keeping the worker polling.
setInterval(sync,15000);
export function subscribePush(name,handler){
  if(!['feed','basispulse'].includes(name))throw Error('Unknown push stream');
  if(!handlers.has(name))handlers.set(name,new Set());handlers.get(name).add(handler);
  start();sync();
  return ()=>{handlers.get(name)?.delete(handler);if(!handlers.get(name)?.size)handlers.delete(name);sync();};
}
