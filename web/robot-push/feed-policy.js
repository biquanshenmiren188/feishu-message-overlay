import {FeedStore} from './feed-color.js?v=20261028-feed1';

export const DECISION_TTL=10000;
export function fingerprintText(message){
  const fields=['id','title','body','sentAt'].map(key=>message?.[key]);
  return fields.every(value=>typeof value==='string')?JSON.stringify(fields):null;
}
export async function fingerprintMessage(message){
  const text=fingerprintText(message);if(text===null)return null;
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes),value=>value.toString(16).padStart(2,'0')).join('');
}

// Keep the public source separately from its visible projection. Removing a row
// from the projection must not mark it permanently consumed by FeedStore.seen.
export class FeedPolicyState {
  constructor(){this.raw=new Map();this.source=new FeedStore();this.hashes=new Map();this.observed=new Set();this.pendingSound=new Set();this.started=false;this.reset('');}
  reset(token){this.token=token;this.invalidate();}
  invalidate(){this.data=null;this.receivedAt=0;this.pendingSound.clear();}
  ingest(batch,now=Date.now()){
    const candidates=new Map(this.source.messages.map(message=>[message.id,this.raw.get(message.id)]));
    for(const message of batch.messages||[])if(message&&typeof message.id==='string')candidates.set(message.id,message);
    const pinned=batch.pinned===undefined?(this.source.pinned&&this.raw.get(this.source.pinned.id)):batch.pinned;
    const next=new FeedStore();
    next.ingest({messages:[...candidates.values()].filter(Boolean),pinned:pinned||null},now);
    const raw=new Map();
    for(const message of next.messages)raw.set(message.id,candidates.get(message.id));
    if(next.pinned)raw.set(next.pinned.id,pinned);
    for(const [id,message] of raw){
      if(this.started&&!this.observed.has(id))this.pendingSound.add(id);
      this.observed.add(id);
      if(this.hashes.get(id)?.text!==fingerprintText(message))this.hashes.delete(id);
    }
    if(this.observed.size>100)this.observed=new Set(raw.keys());
    for(const id of this.hashes.keys())if(!raw.has(id))this.hashes.delete(id);
    for(const id of this.pendingSound)if(!raw.has(id))this.pendingSound.delete(id);
    this.started=true;this.raw=raw;this.source=next;
  }
  recordHash(id,text,hash){if(hash&&this.raw.has(id)&&fingerprintText(this.raw.get(id))===text)this.hashes.set(id,{text,hash});}
  accept(data,now){
    if(!data||!Number.isInteger(data.revision)||typeof data.desktopEnabled!=='boolean'||!data.decisions||typeof data.decisions!=='object'||Array.isArray(data.decisions)||Object.values(data.decisions).some(value=>!value||!['allow','mute','hide'].includes(value.action)||!/^([a-f0-9]{64})$/.test(value.fingerprint)))throw Error('消息规则响应无效');
    this.data=data;this.receivedAt=now;
  }
  outcome(message,now){
    if(!this.token)return 'public';
    if(!this.data||now-this.receivedAt>=DECISION_TTL)return 'pending';
    if(!this.data.desktopEnabled)return 'hide';
    const decision=this.data.decisions[message.id],hash=this.hashes.get(message.id)?.hash;
    return decision&&hash===decision.fingerprint?decision.action:'pending';
  }
  project(now){
    const visible=message=>['public','allow','mute'].includes(this.outcome(message,now));
    return {messages:this.source.messages.filter(visible),pinned:this.source.pinned&&visible(this.source.pinned)?this.source.pinned:null};
  }
  blockedSnapshot(now){
    const ready=!!this.token&&!!this.data&&now-this.receivedAt<DECISION_TTL;
    const blocked=ready?[...this.source.messages,...(this.source.pinned?[this.source.pinned]:[])].filter(message=>this.outcome(message,now)==='hide').map(({id,title,body,sentAt})=>({id,title,body,sentAt})):[];
    return {bound:!!this.token,ready,blocked};
  }
  takeAudible(now){
    const audible=[];
    for(const message of [...this.source.messages,...(this.source.pinned?[this.source.pinned]:[])]){
      if(!this.pendingSound.has(message.id))continue;
      const action=this.outcome(message,now);if(action==='pending')continue;
      this.pendingSound.delete(message.id);if(['public','allow'].includes(action))audible.push(message);
    }
    return audible;
  }
  emptyMessage(now){
    if(!this.token)return '等待新的机器人消息';
    if(!this.data||now-this.receivedAt>=DECISION_TTL)return '等待本方案消息规则校验后显示';
    if(!this.data.desktopEnabled)return '本方案电脑推送已关闭，可在消息设置恢复';
    const messages=[...this.source.messages,...(this.source.pinned?[this.source.pinned]:[])];
    if(messages.some(message=>this.outcome(message,now)==='pending'))return '等待本方案消息规则校验后显示';
    return messages.length?'当前消息均已被本方案规则屏蔽':'等待新的机器人消息';
  }
}

export function createFeedPolicy(onChange,{publicOnly=false}={}){
  const state=new FeedPolicyState();let identity='',epoch=0,request=null,expiration=null,lastFetch=0,lastProjection='';
  const token=()=>{if(publicOnly)return '';try{return localStorage.getItem('radar-settings-token')||localStorage.getItem('radar-test-token')||'';}catch{return '';}};
  function publish(){
    const now=Date.now(),projection=state.project(now),text=JSON.stringify(projection),audible=state.takeAudible(now);
    if(text!==lastProjection||audible.length){lastProjection=text;onChange(projection,{audible,emptyMessage:state.emptyMessage(now)});}
    else onChange(null,{audible:[],emptyMessage:state.emptyMessage(now)});
    document.dispatchEvent(new CustomEvent('radar-feed-policy-snapshot',{detail:state.blockedSnapshot(now)}));
  }
  function syncIdentity(){
    const next=token();if(next!==identity){identity=next;epoch++;request?.controller.abort();request=null;clearTimeout(expiration);state.reset(next);publish();}
    return next;
  }
  function invalidate(){epoch++;request?.controller.abort();request=null;clearTimeout(expiration);state.invalidate();publish();}
  async function refresh(){
    const auth=syncIdentity();if(!auth||request||document.hidden)return;
    const own={auth,epoch,controller:new AbortController()};request=own;lastFetch=Date.now();
    const timeout=setTimeout(()=>own.controller.abort(),7000);
    try{
      const response=await fetch('/radar/push-test/api/message-decisions',{headers:{Authorization:'Bearer '+auth},cache:'no-store',redirect:'error',signal:own.controller.signal});
      if(request!==own||auth!==token()||epoch!==own.epoch)return;
      if(!response.ok)throw Error('消息规则同步失败');
      const data=await response.json();if(request!==own||auth!==token()||epoch!==own.epoch)return;
      state.accept(data,Date.now());clearTimeout(expiration);
      expiration=setTimeout(()=>{if(epoch===own.epoch){state.invalidate();publish();void refresh();}},DECISION_TTL);
    }catch{if(request===own&&auth===token()&&epoch===own.epoch){state.invalidate();clearTimeout(expiration);}}
    finally{clearTimeout(timeout);if(request===own){request=null;syncIdentity();publish();}}
  }
  async function receive(batch){
    syncIdentity();state.ingest(batch);publish();
    const missing=[...state.raw].filter(([id])=>!state.hashes.has(id));
    await Promise.all(missing.map(async([id,message])=>{const text=fingerprintText(message);try{state.recordHash(id,text,await fingerprintMessage(message));}catch{/* Bound rows remain pending without proof. */}}));
    syncIdentity();publish();if(Date.now()-lastFetch>=1000)void refresh();
  }
  const wake=()=>{syncIdentity();publish();void refresh();};
  window.addEventListener('storage',event=>{if(!event.key||['radar-settings-token','radar-test-token','radar-rules-revision'].includes(event.key)){if(event.key==='radar-rules-revision')invalidate();wake();}});
  document.addEventListener('radar-profile-changing',()=>{invalidate();syncIdentity();queueMicrotask(wake);});
  document.addEventListener('radar-rules-saved',()=>{invalidate();wake();});
  document.addEventListener('radar-feed-policy-request',()=>{syncIdentity();document.dispatchEvent(new CustomEvent('radar-feed-policy-snapshot',{detail:state.blockedSnapshot(Date.now())}));});
  window.addEventListener('focus',wake);document.addEventListener('visibilitychange',()=>{if(!document.hidden)wake();});
  syncIdentity();setTimeout(refresh,0);setInterval(()=>{syncIdentity();publish();if(Date.now()-lastFetch>=3000)void refresh();},1000);
  return {receive};
}
