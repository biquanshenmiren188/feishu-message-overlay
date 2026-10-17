/** Coalesce structural updates until native touch scrolling (including inertia) rests.
 * Passive observation only: never cancel a gesture or move the user's scroll offset.
 */
export function createScrollGate(target, {quietMs=240, later=setTimeout, cancel=clearTimeout}={}) {
  const phone=target.matchMedia('(max-width:900px)'), pending=new Map();
  let touching=false, settling=false, timer=null;
  function flush() {
    timer=null;
    if(touching||target.document.hidden)return;
    settling=false;
    const tasks=[...pending.values()];pending.clear();
    for(const task of tasks)task();
  }
  function rest() { cancel(timer);timer=null;if(!touching)timer=later(flush,quietMs); }
  function motion() { if(!phone.matches)return;settling=true;rest(); }
  function start() { if(!phone.matches)return;touching=true;settling=true;cancel(timer);timer=null; }
  function end(event) { touching=Boolean(event.touches?.length);if(!touching)rest(); }
  const passive={passive:true,capture:true};
  target.addEventListener('touchstart',start,passive);
  target.addEventListener('touchmove',motion,passive);
  target.addEventListener('touchend',end,passive);
  target.addEventListener('touchcancel',end,passive);
  target.addEventListener('scroll',motion,passive);
  target.addEventListener('wheel',motion,passive);
  target.document.addEventListener('visibilitychange',()=>{
    touching=false;cancel(timer);timer=null;
    if(!target.document.hidden)flush();
  });
  phone.addEventListener('change',()=>{if(!phone.matches){touching=false;flush();}});
  return {
    defer(key,task=key) {
      if(!phone.matches||!touching&&!settling)return false;
      pending.set(key,task);return true;
    }
  };
}
export const mobileScrollGate=typeof window==='undefined'?{defer:()=>false}:createScrollGate(window);

/** Mobile's document scroll must not change the size of a pane above the cards. */
export function stablePaneBottom(paneBottom, viewportBottom, stacked) {
  return stacked ? paneBottom : Math.min(viewportBottom,paneBottom);
}
