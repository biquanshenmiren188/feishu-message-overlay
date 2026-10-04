// Preparation only: no transport, credential, disk or log APIs.
export class ForwardOutbox {
  #on=false; #groups=new Set(); #queue=[]; #seen=new Map(); #baseline=0;
  configure({enabled=false,groups=[]},now){
    this.clear();this.#on=enabled===true;this.#groups=new Set(groups);this.#baseline=now;
  }
  clear(){this.#queue=[];this.#seen.clear();}
  stop(){this.#on=false;this.clear();}
  get count(){return this.#queue.length;}
  offer(message,now){
    if(!this.#on || !this.#groups.has(message?.sourceId) || message?.senderKind!=='bot')return 'filtered';
    if(!Number.isFinite(message.sentAt) || message.sentAt<=this.#baseline || message.sentAt>now+60000 || now-message.sentAt>=120000)return 'stale';
    for(const [id,at] of this.#seen)if(now-at>=120000)this.#seen.delete(id);
    this.#queue=this.#queue.filter(m=>now-m.sentAt<120000);
    if(typeof message.id!=='string'||!message.id||message.id.length>256)return 'invalid';
    const key=message.sourceId+'\0'+message.id;
    if(this.#seen.has(key))return 'duplicate';
    if(this.#queue.length>=64||this.#seen.size>=128)return 'full';
    if(typeof message.text!=='string'||message.text.length>16000)return 'invalid';
    this.#seen.set(key,now);
    this.#queue.push({id:message.id,sourceId:message.sourceId,text:message.text,sentAt:message.sentAt});
    return 'queued';
  }
  take(now){while(this.#queue.length){const m=this.#queue.shift();if(now-m.sentAt<120000)return m}return null;}
}
