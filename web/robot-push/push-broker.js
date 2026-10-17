// One conditional cache reader per stream, shared by visible subscribers only.
export function createPushBroker(read, {clock=Date.now, later=setTimeout, cancel=clearTimeout}={}) {
  const clients=new Map(), streams=new Map();
  const names=new Set(['feed','basispulse']);
  const audience=name=>[...clients].filter(([,c])=>c.names.has(name));
  function stop(s){cancel(s.timer);s.timer=null;s.controller?.abort();s.controller=null;}
  function prune(){for(const [id,c] of clients)if(clock()-c.seen>45000)clients.delete(id);}
  async function poll(name,s){
    prune();if(!audience(name).length){stop(s);return;}if(s.controller)return;
    const controller=new AbortController();s.controller=controller;
    const deadline=later(()=>controller.abort(),8000);
    try{
      const data=await read(name,controller.signal);controller.signal.throwIfAborted();
      if(s.controller!==controller)return;
      const unchanged=s.last?.data===data;
      s.failures=0;s.last={type:'data',name,data};s.at=clock();
      for(const [,c] of audience(name))c.send(unchanged?{type:'unchanged',name}:s.last);
    }catch{
      if(s.controller===controller){s.failures++;s.last=null;for(const [,c] of audience(name))c.send({type:'error',name});}
    }finally{
      cancel(deadline);
      if(s.controller===controller){s.controller=null;prune();if(audience(name).length)s.timer=later(()=>{s.timer=null;void poll(name,s)},s.failures?Math.min(30000,5000*2**Math.min(s.failures-1,3)):5000);}
    }
  }
  return {
    update(id, requested, send){
      const old=clients.get(id), selected=new Set(requested.filter(n=>names.has(n)));
      if(selected.size)clients.set(id,{names:selected,send,seen:clock()});else clients.delete(id);
      for(const name of names){
        let s=streams.get(name);if(!s){s={timer:null,controller:null,failures:0,last:null,at:0};streams.set(name,s);}
        if(!audience(name).length){stop(s);continue;}
        if(selected.has(name)&&!old?.names.has(name)&&s.last&&clock()-s.at<5000)send(s.last);
        if(!s.controller&&s.timer===null)void poll(name,s);
      }
    },
    close(){for(const s of streams.values())stop(s);clients.clear();}
  };
}
