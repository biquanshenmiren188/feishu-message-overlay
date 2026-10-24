/** Coalesce structural updates until native touch scrolling (including inertia) rests.
 * Passive observation only: never cancel a gesture or move the user's scroll offset.
 */
export function createScrollGate(target, {quietMs=240, later=setTimeout, cancel=clearTimeout}={}) {
  const phone=target.matchMedia('(max-width:900px)'), pending=new Map();
  let touching=false, settling=false, timer=null, inputRevision=0;
  function flush() {
    timer=null;
    if(touching||target.document.hidden)return;
    settling=false;
    const tasks=[...pending.values()];pending.clear();
    for(const task of tasks)task();
  }
  function rest() { cancel(timer);timer=null;if(!touching)timer=later(flush,quietMs); }
  function motion(event) { if(!phone.matches)return;if(event?.type!=='scroll')inputRevision++;settling=true;rest(); }
  function start() { if(!phone.matches)return;inputRevision++;touching=true;settling=true;cancel(timer);timer=null; }
  function end(event) { if(!phone.matches)return;inputRevision++;touching=Boolean(event.touches?.length);if(!touching)rest(); }
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
    get active(){return phone.matches&&(touching||settling);},
    get inputRevision(){return inputRevision;},
    defer(key,task=key) {
      if(!phone.matches||!touching&&!settling)return false;
      pending.set(key,task);return true;
    }
  };
}
export const mobileScrollGate=typeof window==='undefined'?{defer:()=>false,active:false,inputRevision:0}:createScrollGate(window);

const cardSelector='.bp-card[data-id],.bp-card[data-pair]';
const cardKey=node=>node.dataset.pair?`pair:${node.dataset.pair}`:node.dataset.id?`id:${node.dataset.id}`:null;
function visibleModal(document) {
  return [...document.querySelectorAll('dialog[open],[aria-modal="true"]')]
    .some(node=>!node.hidden&&node.getClientRects().length>0);
}
function viewport(target) {
  const visual=target.visualViewport;
  return {top:visual?.offsetTop||0,height:visual?.height||target.innerHeight,scale:visual?.scale||1};
}
function independentScroller(board,target) {
  for(let node=board;node&&node!==target.document.body&&node!==target.document.documentElement;node=node.parentElement){
    const style=target.getComputedStyle?.(node);
    if(style?.position==='fixed'||/^(auto|scroll|overlay)$/.test(style?.overflowY||'')&&node.scrollHeight>node.clientHeight+1)return true;
  }
  return false;
}

/** Keep a card being read in place through one synchronous DOM transaction.
 * Call around the complete reorder/replace/remove pass, not around each card.
 * Native scrolling is never intercepted. No delayed callback can fight a later gesture.
 */
export function preserveCardViewport(board,mutate,{target=globalThis.window,gate=mobileScrollGate}={}) {
  const document=target?.document,view=target&&viewport(target);
  if(!board||board.isConnected===false||!document||document.hidden||!target.matchMedia('(max-width:900px)').matches
      ||gate.active||view.scale!==1||!Number.isFinite(view.height)||view.height<=0||target.scrollY<=0
      ||visibleModal(document)||independentScroller(board,target))return mutate();
  const boardRect=board.getBoundingClientRect();
  // A card merely peeking below the BOT pane does not make this a card-reading view.
  if(boardRect.top>view.top+view.height/2||boardRect.bottom<=view.top)return mutate();
  const cards=[...board.querySelectorAll(cardSelector)].map(node=>({key:cardKey(node),rect:node.getBoundingClientRect()}));
  const occurrences=new Map();
  for(const {key} of cards)if(key)occurrences.set(key,(occurrences.get(key)||0)+1);
  for(const card of cards)if(occurrences.get(card.key)>1)card.key=null;
  const first=cards.findIndex(({key,rect})=>key&&rect.height>0&&rect.width>0&&rect.bottom>view.top&&rect.top<view.top+view.height);
  if(first<0)return mutate();
  // First visible card, other visible cards, then its nearest preceding neighbour.
  const candidates=[];
  for(let i=first;i<cards.length;i++){
    if(i>first&&cards[i-1].rect.top>=view.top+view.height)break;
    candidates.push(cards[i]);
  }
  if(first>0)candidates.push(cards[first-1]);
  const revision=gate.inputRevision;
  let result;
  try{return result=mutate();}
  finally{
    // Async mutation is deliberately unsupported: never restore after user input.
    if(!result?.then&&board.isConnected!==false&&!document.hidden&&gate.inputRevision===revision
        &&target.matchMedia('(max-width:900px)').matches&&!visibleModal(document)){
      const after=viewport(target);
      if(after.top===view.top&&after.height===view.height&&after.scale===view.scale){
        const remaining=new Map();
        for(const node of board.querySelectorAll(cardSelector)){
          const key=cardKey(node);if(key)remaining.set(key,remaining.has(key)?null:node);
        }
        for(const candidate of candidates){
          const node=remaining.get(candidate.key);if(!node)continue;
          const rect=node.getBoundingClientRect();if(rect.height<=0||rect.width<=0)continue;
          const difference=rect.top-candidate.rect.top;
          if(Number.isFinite(difference)&&Math.abs(difference)>.5){
            const scroller=document.scrollingElement||document.documentElement;
            const max=Math.max(0,scroller.scrollHeight-scroller.clientHeight);
            const top=Math.max(0,Math.min(max,target.scrollY+difference));
            if(Math.abs(top-target.scrollY)>.5)target.scrollTo({left:target.scrollX||0,top,behavior:'instant'});
          }
          break;
        }
      }
    }
  }
}

/** Mobile's document scroll must not change the size of a pane above the cards. */
export function stablePaneBottom(paneBottom, viewportBottom, stacked) {
  return stacked ? paneBottom : Math.min(viewportBottom,paneBottom);
}
