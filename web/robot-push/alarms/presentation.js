// Feed health belongs to the server router, never to the device wall clock.
// The router evaluates quote timestamps. The page only checks its connection age.
export function presentRule(rule,{serverTime,elapsed=0,verified=true}={}){
 const state=rule.state||{};
 let status=rule.enabled?(state.status||'waiting'):'paused';
 if(rule.enabled&&Number.isFinite(serverTime)&&rule.expiresAt&&rule.expiresAt<serverTime)status='expired';
 const fresh=verified&&Number.isFinite(serverTime)&&Number.isFinite(elapsed)&&elapsed>=0&&elapsed<=12&&
   Number.isFinite(state.sampleAt)&&state.sampleAt>0&&Number.isFinite(state.observedAt)&&state.observedAt>0&&
   ['watching','alarming','waiting','confirming'].includes(status);
 return {status,fresh};
}
