/** Coalesce structural updates until native touch scrolling (including inertia) rests.
 * Passive observation only: never cancel a gesture or move the user's scroll offset.
 */
export function createScrollGate(target, {quietMs=240, later=setTimeout, cancel=clearTimeout}={}) {
  const phone=target.matchMedia('(max-width:900px)'), pending=new Map();
  let touching=false, settling=false, timer=null, inputRevision=0, inputScroller=target.document;
  const documentScroller=node=>node===target||node===target.document||node===target.document.scrollingElement||node===target.document.documentElement||node===target.document.body;
  function scrollerFor(node){
    for(;node&&!documentScroller(node);node=node.parentElement){
      const style=target.getComputedStyle?.(node);
      if(/^(auto|scroll|overlay)$/.test(style?.overflowY||'')&&node.scrollHeight>node.clientHeight+1)return node;
    }
    return target.document;
  }
  function flush() {
    timer=null;
    if(touching||target.document.hidden)return;
    settling=false;
    const tasks=[...pending.values()];pending.clear();
    for(const task of tasks)task();
  }
  function rest() { cancel(timer);timer=null;if(!touching)timer=later(flush,quietMs); }
  function motion(event) {
    if(!phone.matches)return;
    if(event?.type==='scroll'){
      // A BOT auto-advance emits a real DOM scroll event too. Only extend the
      // inertia belonging to an observed user gesture, on that same scroller.
      if(!touching&&!settling)return;
      if(inputScroller===target.document?!documentScroller(event.target):event.target!==inputScroller)return;
    }else{inputRevision++;if(event?.type!=='touchmove')inputScroller=scrollerFor(event?.target);settling=true;}
    rest();
  }
  function start(event) { if(!phone.matches)return;inputRevision++;inputScroller=scrollerFor(event?.target);touching=true;settling=true;cancel(timer);timer=null; }
  function end(event) { if(!phone.matches)return;inputRevision++;touching=Boolean(event.touches?.length);if(!touching)rest(); }
  const passive={passive:true,capture:true};
  target.addEventListener('touchstart',start,passive);
  target.addEventListener('touchmove',motion,passive);
  target.addEventListener('touchend',end,passive);
  target.addEventListener('touchcancel',end,passive);
  target.addEventListener('scroll',motion,passive);
  target.addEventListener('wheel',motion,passive);
  target.addEventListener('pointerdown',event=>{if(event.pointerType!=='touch')motion(event);},passive);
  target.addEventListener('keydown',event=>{if(['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(event.key)&&!event.target?.closest?.('input,textarea,[contenteditable="true"]'))motion(event);},passive);
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

const placeholderKeys=new WeakMap(),transactions=new WeakSet(),emptyHolds=new WeakMap();
export const CARD_LAYOUT_GRACE_MS=3500;
const placeholderSelector='.bp-reading-placeholder';
const cardSelector='.bp-card[data-id],.bp-card[data-pair],'+placeholderSelector;
const cardKey=node=>placeholderKeys.get(node)??(node.dataset.pair?`pair:${node.dataset.pair}`:node.dataset.id?`id:${node.dataset.id}`:null);

/** Hide removed/blocked content immediately without changing a moving page's
 * geometry. No text, links, handlers or private card attributes survive. */
export function retireCardNode(card,deferred,{target=globalThis.window}={}){
  if(!card)return;
  if(!deferred){card.remove();return;}
  const rect=card.getBoundingClientRect(),placeholder=card.ownerDocument.createElement('div'),style=target?.getComputedStyle?.(card);
  placeholder.className='bp-reading-placeholder';placeholder.setAttribute('aria-hidden','true');placeholder.inert=true;
  Object.assign(placeholder.style,{height:Math.max(0,rect.height)+'px',minHeight:Math.max(0,rect.height)+'px',boxSizing:'border-box',marginTop:style?.marginTop||'0px',marginBottom:style?.marginBottom||'0px',visibility:'hidden',pointerEvents:'none',flex:'none'});
  const key=cardKey(card);if(key)placeholderKeys.set(placeholder,key);
  const release=card.parentElement&&reserveHeight(card.parentElement,target);
  try{card.replaceWith(placeholder);}finally{release?.();}
}
export function clearCardPlaceholders(board){for(const node of board.querySelectorAll(placeholderSelector))node.remove();}

function reserveHeight(board,target){
  if(!board.style)return null;
  const value=board.style.getPropertyValue('min-height'),priority=board.style.getPropertyPriority('min-height'),style=target.getComputedStyle?.(board);
  const inset=style?.boxSizing==='border-box'?0:['paddingTop','paddingBottom','borderTopWidth','borderBottomWidth'].reduce((n,k)=>n+(parseFloat(style?.[k])||0),0);
  board.style.setProperty('min-height',Math.max(0,board.getBoundingClientRect().height-inset)+'px');
  return ()=>{if(value)board.style.setProperty('min-height',value,priority);else board.style.removeProperty('min-height');};
}
function releaseHold(board){const hold=emptyHolds.get(board);if(hold){emptyHolds.delete(board);hold.cancel(hold.timer);hold.cleanup();hold.release();}}
function holdEmpty(board,snapshot,release,{target,later,cancel}){
  if(emptyHolds.has(board)||!release)return;
  const discard=()=>releaseHold(board),types=['touchstart','pointerdown','wheel','keydown'];
  for(const type of types)target.addEventListener(type,discard,{passive:true,capture:true});
  target.addEventListener('resize',discard);target.visualViewport?.addEventListener('resize',discard);
  target.document.addEventListener('visibilitychange',discard);
  const hold={...snapshot,release,cancel,cleanup(){for(const type of types)target.removeEventListener(type,discard,true);target.removeEventListener('resize',discard);target.visualViewport?.removeEventListener('resize',discard);target.document.removeEventListener('visibilitychange',discard);}};
  hold.timer=later(discard,CARD_LAYOUT_GRACE_MS);emptyHolds.set(board,hold);
}
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
export function preserveCardViewport(board,mutate,{target=globalThis.window,gate=mobileScrollGate,later=setTimeout,cancel=clearTimeout}={}) {
  if(board&&transactions.has(board))return mutate();
  const document=target?.document,view=target&&viewport(target);
  let held=board&&emptyHolds.get(board);
  if(held&&(held.revision!==gate.inputRevision||!view||held.view.top!==view.top||held.view.height!==view.height||held.view.scale!==view.scale)){releaseHold(board);held=null;}
  if(!board||board.isConnected===false||!document||document.hidden||!target.matchMedia('(max-width:900px)').matches
      ||gate.active||view.scale!==1||!Number.isFinite(view.height)||view.height<=0||target.scrollY<=0
      ||visibleModal(document)||independentScroller(board,target)){if(held)releaseHold(board);return mutate();}
  const boardRect=board.getBoundingClientRect();
  // A card merely peeking below the BOT pane does not make this a card-reading view.
  if(boardRect.top>view.top+view.height/2||boardRect.bottom<=view.top)return mutate();
  const cards=[...board.querySelectorAll(cardSelector)].map(node=>({key:cardKey(node),rect:node.getBoundingClientRect()}));
  const occurrences=new Map();
  for(const {key} of cards)if(key)occurrences.set(key,(occurrences.get(key)||0)+1);
  for(const card of cards)if(occurrences.get(card.key)>1)card.key=null;
  const first=cards.findIndex(({key,rect})=>key&&rect.height>0&&rect.width>0&&rect.bottom>view.top&&rect.top<view.top+view.height);
  if(first<0&&!held)return mutate();
  // First visible card, other visible cards, then its nearest preceding neighbour.
  const candidates=held?.candidates??[];
  if(!held){for(let i=first;i<cards.length;i++){
      if(i>first&&cards[i-1].rect.top>=view.top+view.height)break;
      candidates.push(cards[i]);
    }
    if(first>0)candidates.push(cards[first-1]);
  }
  const revision=gate.inputRevision;
  const release=held?.release??reserveHeight(board,target);
  let result,keepHeight=false;transactions.add(board);
  try{return result=mutate();}
  finally{
    transactions.delete(board);
    // Async mutation is deliberately unsupported: never restore after user input.
    if(!result?.then&&board.isConnected!==false&&!document.hidden&&gate.inputRevision===revision
        &&target.matchMedia('(max-width:900px)').matches&&!visibleModal(document)){
      const after=viewport(target);
      if(after.top===view.top&&after.height===view.height&&after.scale===view.scale){
        const remaining=new Map(),nodes=[...board.querySelectorAll(cardSelector)];
        for(const node of nodes){
          const key=cardKey(node);if(key)remaining.set(key,remaining.has(key)?null:node);
        }
        if(!nodes.length&&release){
          // Rules can temporarily hide every card until their next response.
          // Keep only geometry and keys for one bounded poll, never card content.
          holdEmpty(board,{candidates,view,revision},release,{target,later,cancel});keepHeight=true;
        }else{
          if(held)releaseHold(board);else release?.();
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
    if(!keepHeight){if(emptyHolds.has(board))releaseHold(board);else release?.();}
  }
}

/** Mobile's document scroll must not change the size of a pane above the cards. */
export function stablePaneBottom(paneBottom, viewportBottom, stacked) {
  return stacked ? paneBottom : Math.min(viewportBottom,paneBottom);
}
