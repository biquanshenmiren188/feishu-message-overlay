// Presentation only. Never contains application credentials or changes source text.
export const MAX_MESSAGES=100;
export const RETENTION_MS=30*60*1000;
export function safeUrl(value){
  if(typeof value!=='string'||/[\u0000-\u0020]/.test(value))return null;
  try{const url=new URL(value);return ['http:','https:'].includes(url.protocol)&&!url.username&&!url.password?value:null;}catch{return null;}
}
export function timeUTC8(value){
  const date=new Date(value);if(!Number.isFinite(date.getTime()))return '时间未知';
  const shifted=new Date(date.getTime()+8*3600000);return shifted.toISOString().slice(11,19);
}
function clean(message){
  if(!message||typeof message.id!=='string'||message.id.length>256||message.senderType!=='bot'||typeof message.body!=='string'||message.body.length>16000)return null;
  const stamp=Date.parse(message.sentAt);if(!Number.isFinite(stamp))return null;
  return {id:message.id,groupId:String(message.groupId??''),headerTone:['blue','red','green','orange','purple','indigo','turquoise','yellow','grey'].includes(message.headerTone)?message.headerTone:'grey',title:String(message.title??''),body:message.body,sentAt:new Date(stamp).toISOString(),actions:(message.actions??[]).filter(a=>typeof a.label==='string'&&safeUrl(a.url)).map(a=>({label:a.label,url:a.url}))};
}
export class FeedStore{
  messages=[];pinned=null;seen=new Map();revision=0;
  ingest(batch,now=Date.now()){
    const added=[],previousIds=this.messages.map(m=>m.id).join("|"),previousPin=JSON.stringify(this.pinned),retained=new Set(this.messages.map(m=>m.id));
    for(const raw of batch.messages??[]){const message=clean(raw);if(!message)continue;const stamp=Date.parse(message.sentAt);if(stamp>now+30000||now-stamp>RETENTION_MS||this.seen.has(message.id)||retained.has(message.id))continue;this.seen.set(message.id,stamp);this.messages.push(message);added.push(message.id);}
    if(batch.pinned!==undefined)this.pinned=batch.pinned===null?null:clean(batch.pinned);
    this.messages=this.messages.filter(m=>!this.pinned||m.groupId!==this.pinned.groupId).sort((a,b)=>Date.parse(a.sentAt)-Date.parse(b.sentAt)).slice(-MAX_MESSAGES);
    for(const [id,stamp] of this.seen)if(now-stamp>RETENTION_MS)this.seen.delete(id);
    if(this.seen.size>MAX_MESSAGES*2){const kept=new Set(this.messages.map(m=>m.id));for(const id of this.seen.keys())if(!kept.has(id))this.seen.delete(id);}
    if(previousIds!==this.messages.map(m=>m.id).join("|")||previousPin!==JSON.stringify(this.pinned))this.revision++;
    return added.filter(id=>this.messages.some(m=>m.id===id));
  }
}
export class AutoReader{
  enabled=true;seconds=5;current=null;deadline=null;idleUntil=null;pending=[];
  configure(enabled,seconds,now){this.enabled=enabled;this.seconds=Math.max(1,Math.min(300,Number(seconds)||5));this.idleUntil=null;this.deadline=enabled&&this.current?now+this.seconds*1000:null;}
  focus(id,now){this.current=id;this.deadline=this.enabled?now+this.seconds*1000:null;}
  arrived(ids,now=Date.now()){for(const id of ids)if(id!==this.current&&!this.pending.includes(id))this.pending.push(id);if(this.enabled&&this.current&&this.deadline===null&&this.idleUntil===null&&this.pending.length)this.deadline=now+this.seconds*1000;}
  manual(id,now){this.current=id;this.idleUntil=this.enabled?now+10000:null;this.deadline=null;}
  tick(now,ids,visible=true){
    if(!this.enabled||!visible)return null;
    this.pending=this.pending.filter(id=>ids.includes(id)&&id!==this.current);
    if(this.idleUntil!==null){if(now<this.idleUntil)return null;this.idleUntil=null;this.deadline=now+this.seconds*1000;return null;}
    if(this.deadline===null||now<this.deadline)return null;
    const index=ids.indexOf(this.current);const next=ids[index+1];
    if(!next){this.deadline=null;return null;}this.focus(next,now);return next;
  }
  nextDelay(now,ids){if(!this.enabled)return null;if(this.idleUntil!==null)return Math.max(1,this.idleUntil-now);const index=ids.indexOf(this.current);if(!this.pending.some(id=>ids.includes(id)&&id!==this.current)&&!ids[index+1])return null;return this.deadline===null?null:Math.max(1,this.deadline-now);}
}
