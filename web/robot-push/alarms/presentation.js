// Feed health belongs to the server router, never to the device wall clock.
// An old/delayed page snapshot can hide its price, but cannot invent a feed outage.
export function presentRule(rule,{serverTime,elapsed=0,verified=true}={}){
 const state=rule.state||{};
 let status=rule.enabled?(state.status||'waiting'):'paused';
 if(rule.enabled&&Number.isFinite(serverTime)&&rule.expiresAt&&rule.expiresAt<serverTime)status='expired';
 const stamps=[state.sampleAt,state.observedAt].filter(t=>Number.isFinite(t)&&t>0);
 const fresh=verified&&Number.isFinite(serverTime)&&Number.isFinite(elapsed)&&elapsed>=0&&
   stamps.length===2&&stamps.every(t=>serverTime-t>=-2&&serverTime-t+elapsed<=12)&&
   !['stale','unavailable'].includes(status);
 return {status,fresh};
}
