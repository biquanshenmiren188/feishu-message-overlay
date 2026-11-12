import {createPinHistory} from './pin-history.js';
import {subscribePush} from './push-subscription.js';
import {mobileScrollGate,stablePaneBottom,preserveCardViewport} from './mobile-scroll.js';
import {FeedStore,safeUrl,timeUTC8} from './feed-color.js?v=20261011-session';
import {CarouselReader} from './carousel.js?v=20261003m';
import {mobileSummary} from './summary.js?v=20261003m';
import {demoData} from './demo.js';
import {createFeedPolicy} from './feed-policy.js?v=20261028-1';
const $=id=>document.getElementById(id),store=new FeedStore(),reader=new CarouselReader();
const board=$('board'),feed=$('feed'),pin=$('pinned');let timer=null,poll=null,newCount=0,lastPinKey=null,lastWindowKey=null,manualHeld=false;
const pinHistory=createPinHistory({element:pin,renderCard:message=>card(message,true),onLayout:()=>{const atEnd=board.scrollHeight-board.clientHeight-board.scrollTop<=2;fitKey='';fitCards(true);if(atEnd){guardScroll();board.scrollTop=board.scrollHeight;}updateLatest();updateProgress();}});
const demo=new URLSearchParams(location.search).get('mode')==='demo';
let soundWanted=false,audio=null,primed=false,lastTone=-Infinity,toneRequests=0,audioBuffer=null,soundBusy=false,soundFailed=false;const activeSounds=new Set();const openedAt=Date.now();
try{const p=JSON.parse(localStorage.getItem('robot-push-ui')||'{}');reader.configure(p.enabled!==false,p.seconds||5,Date.now());soundWanted=p.sound===true;}catch{}
$('auto').checked=reader.enabled;$('seconds').textContent=reader.seconds+'s';
function save(){try{localStorage.setItem('robot-push-ui',JSON.stringify({enabled:reader.enabled,seconds:reader.seconds,sound:soundWanted}));}catch{}}
function stopSounds(){for(const sound of activeSounds){try{sound.stop();}catch{}sound.disconnect();}activeSounds.clear();}
function paintSound(){const ready=audio?.state==='running'&&audioBuffer;const label=soundBusy?'正在加载提示音':soundFailed?'声音加载失败，点击重试':!soundWanted?'开启声音提醒':ready?'关闭声音提醒':'点击解锁声音提醒';
 $('sound').dataset.state=soundFailed?'error':!soundWanted?'off':ready?'on':'locked';$('sound').dataset.requests=String(toneRequests);$('sound').disabled=soundBusy;$('sound').setAttribute('aria-pressed',String(!!(soundWanted&&ready)));$('sound').setAttribute('aria-label',label);$('sound').title=label+' · 金十提示音（与本机软件相同），跟随系统音量';}
let soundLoad=null,gestureArmed=false,soundPageHidden=false,lastGestureAttempt=-Infinity;
const soundGestureTypes=['click','touchend','keydown'];
function syncSoundGestures(){
 const arm=soundWanted&&!soundPageHidden&&!document.hidden&&!(audio?.state==='running'&&audioBuffer);
 if(arm===gestureArmed)return;gestureArmed=arm;
 for(const type of soundGestureTypes)document[arm?'addEventListener':'removeEventListener'](type,onSoundGesture,true);
}
function soundStateChanged(){paintSound();syncSoundGestures();}
function loadSound(){
 if(audioBuffer)return Promise.resolve();if(soundLoad)return soundLoad;
 soundBusy=true;soundStateChanged();
 soundLoad=(async()=>{const response=await fetch('./notice.wav?v=20261003m',{signal:AbortSignal.timeout(8000)});if(!response.ok)throw Error('Audio unavailable');audioBuffer=await audio.decodeAudioData(await response.arrayBuffer());})()
 .catch(()=>{soundFailed=true;}).finally(()=>{soundLoad=null;soundBusy=false;soundStateChanged();});return soundLoad;
}
function resumeWantedSound(){
 if(!soundWanted||soundPageHidden||document.hidden)return;
 soundFailed=false;
 try{
  audio??=new(window.AudioContext||window.webkitAudioContext)();audio.onstatechange=soundStateChanged;
  // Invoke synchronously inside the trusted gesture; never wait for the download first.
  // A policy-blocked startup resume can remain pending, so it must not block a later gesture.
  if(audio.state!=='running')Promise.resolve(audio.resume()).then(()=>{if(!soundWanted)void audio.suspend().catch(()=>{});soundStateChanged();}).catch(error=>{if(error?.name!=='NotAllowedError')soundFailed=true;soundStateChanged();});
  void loadSound();
 }catch{soundFailed=true;}
 soundStateChanged();
}
function onSoundGesture(event){
 if(!event.isTrusted||event.target?.closest?.('#sound')||event.type==='keydown'&&(!['Enter',' '].includes(event.key)||event.repeat||event.ctrlKey||event.metaKey||event.altKey||event.target?.closest?.('input,textarea,[contenteditable=true]')))return;
 if(performance.now()-lastGestureAttempt<200)return;lastGestureAttempt=performance.now();resumeWantedSound();
}
$('sound').addEventListener('click',()=>{
 if(soundBusy)return;
 if(soundWanted&&audio?.state==='running'&&audioBuffer){soundWanted=false;stopSounds();void audio.suspend().catch(()=>{});save();soundStateChanged();}
 else{soundWanted=true;save();resumeWantedSound();}
});
window.addEventListener('pagehide',()=>{soundPageHidden=true;syncSoundGestures();});
window.addEventListener('pageshow',()=>{soundPageHidden=false;syncSoundGestures();});
document.addEventListener('visibilitychange',syncSoundGestures);

function alertNew(messages){
 const fresh=messages.some(m=>m&&Date.parse(m.sentAt)>openedAt);
 if(!primed){primed=true;return;}
 if(!fresh||!soundWanted||audio?.state!=='running'||document.hidden||performance.now()-lastTone<2000)return;
 try{if(!audioBuffer)return;const sound=audio.createBufferSource();sound.buffer=audioBuffer;sound.connect(audio.destination);activeSounds.add(sound);sound.onended=()=>{activeSounds.delete(sound);sound.disconnect();};sound.start();lastTone=performance.now();toneRequests++;paintSound();}catch{}
}
function setConnection(state,label){$('connection').dataset.state=state;$('connection').title=label;$('connection').setAttribute('aria-label',label);}
soundStateChanged();if(soundWanted)resumeWantedSound();
function link(label,url){const a=document.createElement('a');a.textContent=label;a.setAttribute('href',url);a.target='_blank';a.rel='noopener noreferrer';return a;}
function bodyText(p,text){
 const regex=/https?:\/\/[^\s<>]+/giu;let offset=0;
 for(const match of text.matchAll(regex)){const raw=match[0],url=raw.replace(/[，。；！？”）\]}]+$/u,'');p.append(document.createTextNode(text.slice(offset,match.index)));p.append(safeUrl(url)?link(url,url):document.createTextNode(url));p.append(document.createTextNode(raw.slice(url.length)));offset=match.index+raw.length;}
 p.append(document.createTextNode(text.slice(offset)));
}
function card(message,pinned=false,detail=false){
 const article=document.createElement('article');article.className='message'+(pinned?' pin':'');article.dataset.id=message.id;
 const header=document.createElement('div');header.className='message-head';header.dataset.tone=message.headerTone||'grey';const title=document.createElement('h2');title.className='message-title';title.textContent=mobileSummary(message).title||message.title||(pinned?'置顶群最新一条':'机器人消息');
 const time=document.createElement('time');time.dateTime=message.sentAt;time.textContent=timeUTC8(message.sentAt);time.title=new Date(Date.parse(message.sentAt)+8*3600000).toISOString().slice(0,19).replace('T',' ')+' UTC+8';header.append(title,time);article.append(header);
 const body=document.createElement('div');body.className='body';for(const line of message.body.split(/\r\n|\r|\n/)){const p=document.createElement('p');bodyText(p,line);if(!line)p.append(document.createElement('br'));body.append(p);}article.append(body);
 if(!detail){
  const summary=mobileSummary(message),compact=document.createElement('div');compact.className='mobile-summary';
  title.textContent=summary.title||title.textContent;
  for(const [name,text] of Object.entries({spread:summary.spread,signals:summary.signals,risk:summary.warning?summary.risk:''})){if(!text)continue;const row=document.createElement('p');row.className='summary-'+name;row.textContent=text;row.title=text;if(name==='risk')row.dataset.warning=String(summary.warning);compact.append(row);}
  const hint=document.createElement('span');hint.className='detail-hint';hint.textContent='全文 ›';header.append(hint);article.append(compact);article.classList.add('compact-card');article.tabIndex=0;article.setAttribute('role','button');article.setAttribute('aria-label',(title.textContent||'消息')+'，查看完整原文');
  article.addEventListener('click',()=>openDetail(message,pinned));article.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();e.stopPropagation();openDetail(message,pinned);}});
 }
 if(message.actions.length){const actions=document.createElement('div');actions.className='actions';for(const action of message.actions)actions.append(link(action.label,action.url));article.append(actions);}return article;
}
function openDetail(message,pinned){
 if(detailOpen)return;
 const now=Date.now();detailOpen={scroll:board.scrollTop,focus:message.id,remaining:Math.max(1,reader.deadline-now),idle:reader.paused?Math.max(1,reader.idleUntil-now):null};
 clearTimeout(timer);timer=null;
 // Build a snapshot. Live receipt continues, but never replaces the open original text.
 $('detail-content').replaceChildren(card({...message,actions:message.actions.map(a=>({...a}))},pinned,true));
 $('message-detail').showModal();$('detail-content').scrollTop=0;
}
function closeDetail(){
 if($('message-detail').open)$('message-detail').close();
 if(!detailOpen)return;const saved=detailOpen;detailOpen=null;const now=Date.now();
 reader.synchronize(store.messages.map(m=>m.id),now);reader.deadline=now+Math.min(reader.seconds*1000,saved.remaining);
 if(saved.idle!==null&&reader.enabled){reader.paused=true;reader.idleUntil=now+saved.idle;}
 deferredRefresh=false;guardScroll();render();board.scrollTop=saved.scroll;
 ([...feed.children,...pin.children].find(e=>e.dataset.id===saved.focus)||board).focus({preventScroll:true});schedule();
}
$('detail-close').addEventListener('click',closeDetail);
$('message-detail').addEventListener('close',closeDetail);
$('message-detail').addEventListener('cancel',e=>{e.preventDefault();closeDetail();});
let backdropDown=null,backdropClick=false;
function outsideDetail(e){const rect=$('message-detail').getBoundingClientRect();return e.target===$('message-detail')&&(e.clientX<rect.left||e.clientX>rect.right||e.clientY<rect.top||e.clientY>rect.bottom);}
$('message-detail').addEventListener('pointerdown',e=>{backdropClick=false;backdropDown=outsideDetail(e)?{id:e.pointerId,x:e.clientX,y:e.clientY}:null;});
$('message-detail').addEventListener('pointerup',e=>{backdropClick=!!backdropDown&&backdropDown.id===e.pointerId&&outsideDetail(e)&&Math.hypot(e.clientX-backdropDown.x,e.clientY-backdropDown.y)<=8;backdropDown=null;});
$('message-detail').addEventListener('pointercancel',()=>{backdropDown=null;backdropClick=false;});
$('message-detail').addEventListener('click',e=>{const close=backdropClick&&outsideDetail(e);backdropClick=false;if(close){e.preventDefault();e.stopPropagation();closeDetail();}});

function firstVisible(){const top=board.getBoundingClientRect().top+(getComputedStyle(pin).position==='sticky'?pin.offsetHeight:0);return [...feed.children].find(el=>el.getBoundingClientRect().bottom>top+1)?.dataset.id??reader.current;}
function status(){
 board.dataset.readerCurrent=reader.current||'';board.dataset.rangeStart=reader.window()[0]||'';
 board.dataset.queueCount=String(reader.ids.length);board.dataset.queueIndex=String(reader.ids.indexOf(reader.current));
 board.dataset.dwell=String(reader.seconds);board.dataset.deadline=String(reader.deadline??'');
 board.dataset.idleUntil=String(reader.idleUntil??'');board.dataset.atTail=String(reader.pendingCount===0);board.dataset.pendingCount=String(reader.pendingCount);board.dataset.paused=String(reader.paused);
 board.dataset.version='full-history-20261018';board.dataset.capacity=String(reader.capacity);
}
let detailOpen=null;
const mobile=matchMedia('(max-width:640px)');reader.setCapacity(mobile.matches?5:3);
let fitKey='',touchActive=false,touchSettling=false,touchQuiet=null,touchTravel=0,pendingTouchStep=0,deferredRefresh=false;
// Message updates happen above the cards on phones. Preserve the card being
// read across the entire synchronous layout commit, including policy removal.
function preserveReading(mutate){return preserveCardViewport(document.querySelector('#basis-pane .bp-board'),mutate);}
function fitCards(force=false){
 if(mobileScrollGate.defer(fitCards,()=>fitCards(force)))return;
 if(touchActive||touchSettling||reader.paused&&!force||detailOpen)return;
 return preserveReading(()=>fitFeed(force));
}
function fitFeed(force){
 const footer=document.querySelector('.boundary');
 const footerHeight=getComputedStyle(footer).display==='none'?0:footer.getBoundingClientRect().height+8;
 const viewportBottom=Math.min(innerHeight,window.visualViewport?visualViewport.height+visualViewport.offsetTop:innerHeight);
 const safeBottom=parseFloat(getComputedStyle($('board-shell')).paddingBottom)||0;
 const pane=document.querySelector('.feed-pane');
 const bottom=pane?stablePaneBottom(pane.getBoundingClientRect().bottom,viewportBottom,matchMedia('(max-width:900px)').matches):viewportBottom;
 const height=Math.max(120,bottom-board.getBoundingClientRect().top-footerHeight-safeBottom-4);
 board.style.height=height+'px';
 const key=[lastWindowKey,lastPinKey,board.clientWidth,height].join('|');
 if(key===fitKey)return;fitKey=key;guardScroll();
 board.style.setProperty('--fit-font','13px');
 pin.style.position=mobile.matches?'relative':'sticky';
 for(const el of [...pin.children,...feed.children]){el.style.height='';el.style.minHeight='0';}
 const required=feed.offsetHeight;
 // At the latest position, fit whole rows between the fixed pin and footer.
 // A short trailing inset avoids showing only the tail of the first message.
 const available=board.clientHeight-(parseFloat(getComputedStyle(board).paddingTop)||0),end=feed.lastElementChild?.getBoundingClientRect().bottom;
 const first=[...feed.children].find(el=>end-el.getBoundingClientRect().top<=available);
 board.style.paddingBottom=required>available&&first?Math.max(0,available-(end-first.getBoundingClientRect().top))+'px':'0px';
 if(pin.offsetHeight>=board.clientHeight*.5)pin.style.position='relative';
 board.dataset.fitFont='13';board.dataset.fitPasses='1';board.dataset.fitRequired=String(required);board.dataset.fitAvailable=String(board.clientHeight);
 board.dataset.fitStatus=required<=board.clientHeight?'fully-fitted':'native-history';board.title='';updateProgress();
}

function render(anchor=null){
 if(mobileScrollGate.defer(render,()=>render(anchor)))return;
 if(touchActive||touchSettling||detailOpen){deferredRefresh=true;return;}
 return preserveReading(()=>renderFeed(anchor));
}
function renderFeed(anchor){
 // Both layouts mount the bounded history so natural-height rows fill the pane.
 if(!anchor&&lastWindowKey){const item=[...feed.children].find(el=>el.dataset.id===firstVisible());if(item)anchor={id:item.dataset.id,top:item.getBoundingClientRect().top,scroll:board.scrollTop,delta:0};}
 let layoutChanged=false;const ids=reader.ids,key=String(mobile.matches)+'|'+store.revision+'|'+ids.join('|');
 const pinKey=store.pinned?JSON.stringify(store.pinned):'';
 if(pinKey!==lastPinKey){layoutChanged=true;guardScroll();pinHistory.setCurrent(store.pinned);lastPinKey=pinKey;}
 if(key!==lastWindowKey){
  layoutChanged=true;guardScroll();
  const byId=new Map(store.messages.map(m=>[m.id,m]));
  feed.replaceChildren(...ids.map(id=>byId.get(id)).filter(Boolean).map(m=>card(m)));
  lastWindowKey=key;fitCards(true);
  if(anchor){const retained=[...feed.children].find(el=>el.dataset.id===anchor.id);if(retained)board.scrollTop=anchor.scroll+retained.getBoundingClientRect().top-anchor.top+anchor.delta;}else board.scrollTop=0;
 }
 for(const item of feed.children)item.dataset.reading=String(item.dataset.id===reader.current);
 $('empty').hidden=store.messages.length!==0||!!store.pinned;$('more').hidden=true;
 fitCards(layoutChanged);status();updateLatest();updateProgress();
}
function schedule(){
 clearTimeout(timer);timer=null;status();if(document.hidden||manualHeld||touchActive||touchSettling||detailOpen||railDrag)return;
 const delay=reader.nextDelay(Date.now());if(delay===null)return;
 timer=setTimeout(()=>{const admitted=reader.tick(Date.now(),!document.hidden);render();if(admitted){const item=[...feed.children].find(el=>el.dataset.id===admitted);if(item){guardScroll();board.scrollTop+=item.getBoundingClientRect().top-board.getBoundingClientRect().top;}}updateLatest();updateProgress();schedule();},Math.max(1,delay));
}
let initialPositionPending=true,initialScrollToken=0;
function accept(batch,{audible=[],emptyMessage='等待新的机器人消息'}={}){
 return preserveReading(()=>acceptFeed(batch,{audible,emptyMessage}));
}
function acceptFeed(batch,{audible,emptyMessage}){
 $('empty').textContent=emptyMessage;
 alertNew(audible);if(!batch)return;
 const previous=new Set(store.messages.map(message=>message.id)),added=batch.messages.filter(message=>!previous.has(message.id)).map(message=>message.id);
 store.messages=batch.messages;store.pinned=batch.pinned;store.revision++;
 // Rule revocation takes effect even during touch inertia or an open detail.
 // Remove only disallowed DOM now; normal layout/scroll work keeps its gate.
 const allowed=new Set(store.messages.map(message=>message.id));
 for(const node of [...feed.children])if(!allowed.has(node.dataset.id))node.remove();
 pinHistory.setCurrent(store.pinned);
 if(detailOpen&&!allowed.has(detailOpen.focus)&&!pinHistory.contains(detailOpen.focus)){detailOpen=null;$('detail-content').replaceChildren();$('message-detail').close();}
 reader.synchronize(store.messages.map(message=>message.id),Date.now());
 if(touchActive||touchSettling||detailOpen){deferredRefresh=true;return;}
 const initialJump=initialPositionPending&&reader.ids.length>0;
 if(initialJump){initialPositionPending=false;reader.show(reader.ids.at(-1));reader.focus(reader.window()[0],Date.now());}
 newCount+=added.length;render();
 if(initialJump){const token=++initialScrollToken;requestAnimationFrame(()=>requestAnimationFrame(()=>{if(token!==initialScrollToken||reader.paused||touchActive||touchSettling)return;fitCards();guardScroll();board.scrollTop=board.scrollHeight;updateLatest();updateProgress();}));}
 const remaining=Math.max(0,reader.ids.length-1-reader.ids.indexOf(reader.current));
 $('new-messages').hidden=false;$('new-messages').textContent='到最新';
 schedule();
}
function manual(id=firstVisible()) {initialPositionPending=false;initialScrollToken++;reader.show(id);reader.manual(id,Date.now());status();updateProgress(true);schedule();}
let programmaticScroll=false,scrollGuardToken=0,lastTop=0,touchY=null;
function guardScroll(){
 programmaticScroll=true;const token=++scrollGuardToken;
 requestAnimationFrame(()=>{if(token===scrollGuardToken){programmaticScroll=false;lastTop=board.scrollTop;}});
}
function moveWindow(delta,pixels=0){
 const start=reader.rangeIndex,next=Math.max(0,Math.min(start+Math.sign(delta),Math.max(0,reader.ids.length-reader.capacity)));
 if(next===start)return false;
 const nextIds=reader.ids.slice(next,next+reader.capacity),retained=[...feed.children].find(el=>nextIds.includes(el.dataset.id));
 const anchor=retained?{id:retained.dataset.id,top:retained.getBoundingClientRect().top,scroll:board.scrollTop,delta:pixels}:null;
 guardScroll();reader.show(reader.ids[next]);render(anchor);reader.focus(firstVisible(),Date.now());manual(firstVisible());
 lastTop=board.scrollTop;return true;
}
function edgeMove(){return false;}
function scrollByUser(delta){
 if(edgeMove(delta))return true;
 const before=board.scrollTop;board.scrollTop+=delta;
 if(Math.abs(board.scrollTop-before)<.5)return false;
 manual(firstVisible());lastTop=board.scrollTop;return true;
}
board.addEventListener('wheel',e=>{
 if(mobile.matches)return;
 if(e.ctrlKey||e.metaKey||!e.deltaY)return;
 e.preventDefault();scrollByUser(e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?board.clientHeight:1));
},{passive:false});
board.addEventListener('keydown',e=>{
 if(!['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(e.key)||e.target.closest('a,button,input')||e.key===' '&&e.target.closest('[role=button]'))return;
 e.preventDefault();
 if(e.key==='Home'||e.key==='End'){
  const before=reader.rangeStart,top=board.scrollTop,index=e.key==='Home'?0:Math.max(0,reader.ids.length-reader.capacity);
  guardScroll();reader.show(reader.ids[index]);render();board.scrollTop=e.key==='Home'?0:board.scrollHeight;
  if(before!==reader.rangeStart||Math.abs(top-board.scrollTop)>.5){reader.focus(firstVisible(),Date.now());manual(firstVisible());}
 }else{const delta=(['ArrowUp','PageUp'].includes(e.key)||e.key===' '&&e.shiftKey?-1:1)*(['PageUp','PageDown',' '].includes(e.key)?board.clientHeight*.8:60);scrollByUser(delta);}
});
board.addEventListener('pointerdown',e=>{
 if(e.pointerType==='touch'||e.target.closest('a,button'))return;
 const rect=board.getBoundingClientRect();
 // Only the scrollbar gutter can initiate thumb dragging. A body click is not reading activity.
 manualHeld=board.scrollHeight>board.clientHeight&&e.clientX>=rect.right-18&&e.clientX<=rect.right;
 if(manualHeld)lastTop=board.scrollTop;
});
window.addEventListener('pointerup',e=>{if(e.pointerType==='touch'||!manualHeld)return;manualHeld=false;schedule();});
window.addEventListener('pointercancel',()=>{manualHeld=false;schedule();});
function touchRest(){
 clearTimeout(touchQuiet);if(touchActive)return;
 touchQuiet=setTimeout(()=>{
  touchSettling=false;const step=pendingTouchStep;pendingTouchStep=0;
  if(deferredRefresh){deferredRefresh=false;reader.synchronize(store.messages.map(m=>m.id),Date.now());}
  render();
  lastTop=board.scrollTop;schedule();
 },200);
}
board.addEventListener('scroll',()=>{
 const delta=board.scrollTop-lastTop;
 if(!programmaticScroll&&Math.abs(delta)>.5&&(true)){
  manual(firstVisible());if(touchActive||touchSettling)touchRest();
 }
 lastTop=board.scrollTop;
},{passive:true});
board.addEventListener('touchstart',e=>{
 if(e.target.closest('button'))return;
 clearTimeout(touchQuiet);touchActive=true;touchSettling=true;touchTravel=0;pendingTouchStep=0;touchY=e.touches[0]?.clientY??null;lastTop=board.scrollTop;
 schedule();
},{passive:true});
board.addEventListener('touchmove',e=>{
 return; // Both layouts use native scrolling, never synthetic edge paging.
 const y=e.touches[0]?.clientY;if(!touchActive||y===undefined||touchY===null)return;
 const delta=touchY-y;touchY=y;
 const atEdge=delta<0&&board.scrollTop<=1||delta>0&&board.scrollTop+board.clientHeight>=board.scrollHeight-1;
 touchTravel=atEdge?(Math.sign(touchTravel)===Math.sign(delta)?touchTravel+delta:delta):0;
 pendingTouchStep=Math.abs(touchTravel)>=45?Math.sign(touchTravel):0;
},{passive:true});
function endTouch(){if(!touchActive)return;touchActive=false;touchY=null;touchRest();}
board.addEventListener('touchend',endTouch,{passive:true});
board.addEventListener('touchcancel',()=>{pendingTouchStep=0;endTouch();},{passive:true});
$('auto').addEventListener('change',()=>{reader.configure($('auto').checked,reader.seconds,Date.now());if(reader.enabled)reader.focus(firstVisible(),Date.now());save();render();schedule();});
$('seconds').addEventListener('click',()=>{
 const entered=prompt('每条停留秒数（1–300）',String(reader.seconds));if(entered===null)return;
 const n=Number(entered);if(!Number.isInteger(n)||n<1||n>300)return;
 reader.configure(reader.enabled,n,Date.now());$('seconds').textContent=n+'s';save();status();schedule();
});
function updateLatest(){
 const button=$('new-messages'),latest=reader.ids.at(-1),item=[...feed.children].find(e=>e.dataset.id===latest);
 let reached=!latest;
 if(item){const br=board.getBoundingClientRect(),ir=item.getBoundingClientRect(),top=br.top+(getComputedStyle(pin).position==='sticky'?pin.offsetHeight:0),height=br.bottom-top;
  reached=ir.bottom<=br.bottom+1&&(ir.top>=top-1||ir.height>height);}
 button.hidden=false;button.textContent='到最新';button.disabled=reached;button.setAttribute('aria-label',reached?'已到最新':'到最新');button.title=reached?'已到最新':'查看最新消息';
}
$('new-messages').addEventListener('click',()=>{const id=reader.ids.at(-1);if(id){guardScroll();reader.configure(reader.enabled,reader.seconds,Date.now());reader.focus(id,Date.now());reader.show(id);render();if(board.dataset.fitStatus!=='fully-fitted')board.scrollTop=board.scrollHeight;}newCount=0;updateLatest();schedule();});
board.addEventListener('scroll',updateLatest,{passive:true});

const historyRail=$('history-scroll'),historyThumb=$('history-thumb');let railQuiet=null,railDrag=null;
function progressGeometry(){
 const overflow=Math.max(0,board.scrollHeight-board.clientHeight);
 return {overflow,maxStart:0,domain:overflow>1?1:0,ratio:overflow>1?Math.min(1,Math.max(0,board.scrollTop/overflow)):0};
}

function updateProgress(active=false){
 const g=progressGeometry(),count=reader.ids.length;historyRail.hidden=(!count&&!store.pinned)||g.domain===0;
 historyRail.style.top=board.offsetTop+'px';historyRail.style.height=board.clientHeight+'px';historyRail.dataset.mobile=String(mobile.matches);
 historyRail.tabIndex=mobile.matches?-1:0;historyRail.setAttribute('role',mobile.matches?'progressbar':'scrollbar');
 historyRail.setAttribute('aria-valuenow',String(Math.round(g.ratio*100)));historyRail.setAttribute('aria-valuetext',`历史第${Math.max(0,reader.rangeIndex)+1}至${Math.max(0,reader.rangeIndex)+reader.window().length}条，共${count}条；当前范围滚动${Math.round(g.overflow?board.scrollTop/g.overflow*100:0)}%`);
 historyRail.setAttribute('aria-valuetext',`历史共${count}条；已滚动${Math.round(g.ratio*100)}%`);
 const track=board.clientHeight,portion=Math.min(1,board.clientHeight/Math.max(1,board.scrollHeight));
 const thumb=Math.max(20,Math.min(track,track*portion));historyThumb.style.height=thumb+'px';historyThumb.style.transform=`translateY(${g.ratio*Math.max(0,track-thumb)}px)`;
 historyRail.dataset.position=String(g.ratio);historyRail.dataset.range=reader.rangeStart||'';
 if(active){historyRail.dataset.active='true';clearTimeout(railQuiet);railQuiet=setTimeout(()=>{historyRail.dataset.active='false';},1000);}
}
function seekProgress(ratio){
 const top=board.scrollTop;guardScroll();board.scrollTop=Math.max(0,Math.min(1,ratio))*Math.max(0,board.scrollHeight-board.clientHeight);
 if(Math.abs(top-board.scrollTop)>.5){reader.focus(firstVisible(),Date.now());manual(firstVisible());}
 updateLatest();updateProgress();
}

historyRail.addEventListener('pointerdown',e=>{
 if(mobile.matches||e.button!==0)return;
 e.preventDefault();const rect=historyRail.getBoundingClientRect(),thumb=historyThumb.getBoundingClientRect();
 railDrag={pointer:e.pointerId,grab:e.target===historyThumb?e.clientY-thumb.top:thumb.height/2};historyRail.setPointerCapture(e.pointerId);
 seekProgress((e.clientY-rect.top-railDrag.grab)/Math.max(1,rect.height-thumb.height));
});
historyRail.addEventListener('pointermove',e=>{if(!railDrag||e.pointerId!==railDrag.pointer)return;const rect=historyRail.getBoundingClientRect(),height=historyThumb.getBoundingClientRect().height;seekProgress((e.clientY-rect.top-railDrag.grab)/Math.max(1,rect.height-height));});
function endRail(){railDrag=null;schedule();}historyRail.addEventListener('pointerup',endRail);historyRail.addEventListener('pointercancel',endRail);historyRail.addEventListener('lostpointercapture',endRail);
historyRail.addEventListener('keydown',e=>{if(mobile.matches)return;const g=progressGeometry();let ratio=g.ratio;if(e.key==='Home')ratio=0;else if(e.key==='End')ratio=1;else if(['ArrowUp','ArrowDown','PageUp','PageDown'].includes(e.key))ratio+=((e.key.endsWith('Up')?-1:1)*(e.key.startsWith('Page')?board.clientHeight*.8:60))/Math.max(1,g.overflow);else return;e.preventDefault();seekProgress(ratio);});
board.addEventListener('scroll',()=>updateProgress(true),{passive:true});

let latestFeed=null;
function receiveFeed(data){
 latestFeed=data;void feedPolicy.receive(data);refreshFeedConnection();
}
function refreshFeedConnection(){
 const data=latestFeed;if(!data)return;const age=Date.now()-Date.parse(data.updatedAt);const connected=data.sourceConnected===true&&Number.isFinite(age)&&age>=-30000&&age<45000;setConnection(connected?'connected':'offline',connected?'消息源已连接':'等待消息源');
}
document.addEventListener('visibilitychange',()=>{reader.setVisible(!document.hidden,Date.now(),firstVisible());if(document.hidden){stopSounds();clearTimeout(timer);clearTimeout(touchQuiet);timer=null;manualHeld=false;touchActive=false;touchSettling=false;pendingTouchStep=0;}else{render();schedule();}});
mobile.addEventListener('change',queueResize);
let resizeFrame=null;function queueResize(){if(resizeFrame!==null)return;resizeFrame=requestAnimationFrame(()=>{resizeFrame=null;const capacity=mobile.matches?5:3;if(reader.capacity!==capacity){reader.setCapacity(capacity,firstVisible());lastWindowKey=null;lastPinKey=null;render();schedule();}fitKey='';fitCards(true);updateLatest();updateProgress();});}
window.addEventListener('resize',queueResize);window.visualViewport?.addEventListener('resize',queueResize);
const feedPolicy=createFeedPolicy(accept,{publicOnly:demo});
if(demo){$('demo-note').hidden=false;void feedPolicy.receive(demoData());setConnection('offline','演示数据 · 未接入飞书');}else{$('demo-note').hidden=true;setConnection('connecting','连接中');subscribePush('feed',{data:receiveFeed,unchanged:refreshFeedConnection,error:()=>setConnection('error','暂时无法更新，保留已接收消息')});}
