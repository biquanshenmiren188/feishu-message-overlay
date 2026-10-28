// Broadcast invalidation only; never include a push code, rule or message payload.
export function notifyRulesChanged(){
  try{localStorage.setItem('radar-rules-revision',Date.now()+':'+Math.random());}catch{}
  document.dispatchEvent(new Event('radar-rules-saved'));
}
