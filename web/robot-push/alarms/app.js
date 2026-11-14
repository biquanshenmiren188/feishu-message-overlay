import {createDeviceManager} from './devices.js?v=20261114-devices1';
import {readSnapshot,saveSnapshot,clearSnapshots} from './snapshot.js?v=20261114-devices1';
import {connection} from './session.js?v=20261111-smooth1';
import {patchHTML} from './dom.js?v=20261111-smooth1';
import {matchesInstrument,matchesAlarm,instrumentLabel,resolveInstrument} from './search.js?v=20261112-picker1';
import {presentRule} from './presentation.js?v=20261113-stable1';
import {fallbackChoices,FALLBACK_ORDER} from './fallback.js?v=20261113-multi1';
import {createQuoteDisplay} from './quote-display.js?v=20261113-stable1';
const quoteDisplay=createQuoteDisplay();
const $=s=>document.querySelector(s),form=$('#alarm-form'),barkForm=$('#bark-form');
const field=n=>form.elements.namedItem(n),API='/radar/alarms-api/';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const venue={binance:'Binance',bybit:'Bybit',okx:'OKX',bitget:'Bitget',gate:'Gate',aster:'Aster'};
const conditions={above:'涨到',below:'跌到',enter:'进入区间',exit:'离开区间'};
const labels={watching:'监控中',alarming:'持续报警中',waiting:'等待触发',confirming:'持续确认中',paused:'已暂停',expired:'已到期',triggered:'已触发',stale:'行情中断',unavailable:'价格暂缺'};
const deliveries={queued:'等待发送',sending:'发送中',accepted:'接口接受',retry:'等待重试',failed:'发送失败',unknown:'结果未知',expired:'已过期',cancelled:'已取消',no_device:'未绑定设备'};
let verified=false,cachedAt=0;
let snapshotStartedAt=0,snapshotError='';
let current=null,catalog=[],editing=null,busy=false,epoch=0,lastToken='',pending=null,draft=false,toastTimer,catalogEpoch=0,loadSequence=0,appliedSequence=0;
const token=()=>window.RadarAccount?.token()||'';
window.RadarAlarmHasDraft=()=>draft||!!pending;
function toast(text){$('#alarm-toast').textContent=text;$('#alarm-toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#alarm-toast').hidden=true,3500);}
function notice(text){$('#alarm-notice').textContent=text;$('#alarm-notice').hidden=!text;}
async function api(route,data,auth=token()){
 if(!auth)throw Error('请先连接推送码');
 const response=await fetch(API+route,{method:data?'POST':'GET',headers:{Authorization:'Bearer '+auth,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined,cache:'no-store',redirect:'error',signal:AbortSignal.timeout(15000)});
 let result;try{result=await response.json();}catch{throw Error('未取得服务响应，请检查网站登录状态后重试');}
 if(!response.ok){const e=Error(result.error||'操作失败');e.status=response.status;throw e;}return result;
}
function connected(enabled){
 enabled=enabled&&verified;
 for(const id of ['add-alarm','bind-device'])$('#'+id).disabled=!enabled||busy;
 const sending=current?.events.some(e=>e.ruleId==='test'&&['queued','sending','retry'].includes(e.status));
 for(const id of ['test-bark-inline','test-bark']){
  const button=$('#'+id);button.disabled=!enabled||busy||!!pending||!current?.device||!!sending;
  button.textContent=busy&&testSubmitting?'提交中…':sending?'发送中…':id==='test-bark'?'测试全部':'测试推送';
  button.setAttribute('aria-busy',String(!!sending||(busy&&testSubmitting)));
 }
}
let testSubmitting=false,showTestResult=false,testFeedbackTimer;
function renderTestResult(){
 const events=current?.events.filter(e=>e.ruleId==='test')||[],output=$('#bark-test-result');
 clearTimeout(testFeedbackTimer);output.hidden=!events.length||!showTestResult;if(output.hidden){output.textContent='';return;}
 const status={queued:'等待发送',sending:'发送中…',retry:'等待重试',accepted:'Bark 已接受',failed:'发送失败',unknown:'结果未知，请查看手机',expired:'已过期',cancelled:'已取消',no_device:'请先绑定设备'};
 output.dataset.state=events.every(e=>e.status==='accepted')?'accepted':events.some(e=>['failed','unknown'].includes(e.status))?'failed':'queued';
 output.textContent=events.map(e=>(e.deviceLabel?e.deviceLabel+'：':'')+(status[e.status]||'请查看报警记录')).join('；');
 deviceManager.feedback(output.textContent);
 if(output.dataset.state==='accepted')testFeedbackTimer=setTimeout(()=>{showTestResult=false;renderTestResult();},8000);
}
function syncPlanLabel(){const code=window.RadarIdentity?.code();$('#plan-label').textContent=!token()?'未连接推送码':!verified?'正在核对当前推送码':code?'当前推送码 · 尾号 '+code.slice(-2):'当前推送码 · 已连接';}
function presentation(r){return presentRule(r,{serverTime:current?.serverTime,elapsed:Math.max(0,performance.now()-snapshotStartedAt)/1000,verified:verified&&!snapshotError});}
function price(value){if(!value)return '—';const n=Number(value);return n>=1?n.toLocaleString('en-US',{maximumFractionDigits:10}):value;}
function description(r){return conditions[r.condition]+' '+price(r.target)+(r.upper?' ～ '+price(r.upper):'');}
let statusFilter='all';
const outageStatus=status=>['stale','unavailable'].includes(status);
function matchStatus(r){const {status}=presentation(r);return statusFilter==='all'||(statusFilter==='alarming'?status==='alarming':outageStatus(status));}
function renderRules(){
 if(!current)return;
 quoteDisplay.prune(current.rules.map(r=>r.id));
 const search=$('#alarm-search').value.trim().toLowerCase();
 const rows=current.rules.filter(r=>matchesAlarm(search,r)&&matchStatus(r));
 $('#alarm-count').textContent=current.rules.length;
 $('#alarming-count').textContent=current.rules.filter(r=>presentation(r).status==='alarming').length;
 $('#outage-count').textContent=current.rules.filter(r=>outageStatus(presentation(r).status)).length;
 for(const button of document.querySelectorAll('[data-filter]'))button.setAttribute('aria-pressed',String(button.dataset.filter===statusFilter));
 const selected=new URLSearchParams(location.search).get('rule');
 const focused=document.activeElement?.closest('[data-action]');const restore=focused&&{action:focused.dataset.action,id:focused.dataset.id};
 const markup=rows.length?rows.map(r=>{
  const {status,fresh}=presentation(r);
  const shown=quoteDisplay.read(r,{fresh},performance.now());
  const fallback=fresh&&shown.source?.fallback;
  const lastQuote=shown.last&&(verified||!!snapshotError||outageStatus(status));
  const sourceText=shown.source?.fallback?'备用：'+(venue[shown.source.exchange]||shown.source.exchange)+' · 现货':'';
  const badgeClass=status==='alarming'?'is-alarming':outageStatus(status)?'is-warning':fallback?'is-backup':['watching','confirming'].includes(status)?'is-live':'';
  const badge=labels[status]||'等待行情';
  return `<article class="alarm-row ${r.id===selected?'is-highlighted':''} ${status==='alarming'?'is-alarming':''}">
   <div class="alarm-identity"><strong>${esc(r.state?.asset?.pair||r.symbol)}</strong>${r.note?`<small>${esc(r.note)}</small>`:''}</div>
   <div class="alarm-origin-cell"><span class="alarm-origin">${venue[r.exchange]} · ${r.market==='future'?'永续':'现货'}${r.priceType==='last'?'':' · 标记价格'}</span><small class="alarm-source">${esc(sourceText)||'&nbsp;'}</small></div>
   <div class="alarm-current-cell"><span class="alarm-mobile-label">当前价</span><span class="alarm-price" title="${shown.last?'上次报价，尚未更新':''}">${esc(price(shown.value))}</span><small class="alarm-quote-note">${lastQuote?(shown.value?'末次报价 · 等待更新':'等待行情'):'&nbsp;'}</small></div>
   <div class="alarm-target-cell"><span class="alarm-mobile-label">触发条件</span><div class="alarm-condition">${esc(description(r))}</div></div>
   <div class="alarm-state"><span class="alarm-badge ${badgeClass}">${esc(badge)}</span></div>
   <div class="alarm-reminder-cell"><small class="alarm-repeat">${r.repeat?'每 30 秒提醒':'仅一次'}${!r.repeat&&r.hold?' · 持续 '+r.hold+' 秒':''}</small></div>
   <div class="alarm-actions"><button data-action="edit" data-id="${r.id}" aria-label="编辑 ${esc(r.state?.asset?.pair||r.symbol)} ${venue[r.exchange]} 报警">编辑</button><button data-action="content" data-id="${r.id}" class="alarm-content-action" aria-label="报警内容 ${esc(r.state?.asset?.pair||r.symbol)} ${venue[r.exchange]}">报警内容</button><button data-action="delete" data-id="${r.id}" class="danger-text" aria-label="删除 ${esc(r.state?.asset?.pair||r.symbol)} ${venue[r.exchange]} 报警">删除</button></div>
  </article>`;
 }).join(''):`<div class="alarm-empty"><strong>${current.rules.length?'没有匹配的报警':'还没有价格报警'}</strong><p>${current.rules.length?'可调整币种搜索或状态筛选。':'选择交易所和币种，设置目标价格。保存后由云端持续监控。'}</p>${current.rules.length?'':'<button data-action="new">＋ 创建第一条报警</button>'}</div>`;
 patchHTML($('#alarm-list'),verified?markup:markup.replaceAll('<button','<button disabled'));
 if(restore)$('#alarm-list').querySelector(`[data-action="${restore.action}"][data-id="${restore.id}"]`)?.focus({preventScroll:true});
}
let renderedSignature='',renderedTestEvents='';
function render(){
 const signature=JSON.stringify([Math.floor(performance.now()/5000),verified,snapshotError,current,current.rules.map(r=>presentation(r))]);if(signature===renderedSignature)return;renderedSignature=signature;
 connection(verified&&!snapshotError);document.querySelector('main').classList.remove('is-loading');$('#alarm-list').setAttribute('aria-busy','false');
 syncPlanLabel();
 connected(true);
 const testEvents=JSON.stringify(current.events);
 if(testEvents!==renderedTestEvents){renderedTestEvents=testEvents;renderTestResult();}
 $('#alarm-status').textContent=snapshotError?'同步失败 · 请刷新':!verified?'上次数据 · 同步中':'';
 $('#alarm-status').title=snapshotError?'网页状态更新失败；云端监控独立运行。':!verified?'正在核对服务器上的最新规则和报价':'';
 document.querySelector('main').dataset.syncing=String(!verified&&!snapshotError);
 $('#device-label').textContent=current.device?(current.devices?.length>1?'已绑定 '+current.devices.length+' 台设备':current.device.label+' · 已绑定'):'Bark 未绑定';$('#bind-device').classList.toggle('is-bound',!!current.device);
 if(!current.device)notice('先绑定 Bark 接收设备。未绑定时，触发事件只会记入报警记录。');else notice('');
 renderRules();
 for(const button of $('#alarm-list').querySelectorAll('button'))button.disabled=!verified;
}

async function readState(showError=true){
 const auth=token(),generation=epoch,sequence=++loadSequence;if(!auth){clearSnapshots();quoteDisplay.clear();verified=false;current=null;connected(false);renderTestResult();connection(false);$('#plan-label').textContent='未连接推送码';$('#alarm-status').textContent='请先连接推送码';$('#device-label').textContent='未连接';$('#alarm-list').innerHTML='<div class="alarm-empty"><strong>请先连接推送码</strong><a href="/radar/push-center/">打开推送中心</a></div>';return;}
 const requestStartedAt=performance.now();
 try{const next=await api('state?events=latest-test',undefined,auth);if(auth!==token()||generation!==epoch||sequence<appliedSequence)return;appliedSequence=sequence;verified=true;current=next;snapshotStartedAt=requestStartedAt;snapshotError='';render();saveSnapshot(auth,next);}
 catch(e){if(auth!==token()||generation!==epoch||sequence<appliedSequence)return;appliedSequence=sequence;snapshotError=e.message;if(e.status===401){clearSnapshots();quoteDisplay.clear();verified=false;current=null;renderedSignature='';connection(false);connected(false);}if(!current){connected(false);$('#alarm-status').textContent='暂时无法读取报警';$('#alarm-list').innerHTML='<div class="alarm-empty">读取失败，可点击刷新重试。</div>';}else render();if(showError||!verified)notice(e.message);if(current&&!verified)$('#alarm-status').textContent='上次数据，更新失败；修改暂不可用，请重试刷新。';}
}
let reading=null;
async function load(showError=true,force=false){
 while(reading){await reading;if(!force)return;}
 const request=readState(showError);reading=request;try{await request;}finally{if(reading===request)reading=null;}
}
async function commit(data){
 if(busy)return false;
 if(pending&&data!==pending.data){toast('请先重试结果未确认的原操作');return false;}
 const auth=token(),generation=epoch;
 if(!verified||!current||!auth){toast('请先连接推送码并载入规则');return false;}
 const body=pending?.data||{...data,requestId:crypto.randomUUID().replaceAll('-',''),revision:current.revision};
 appliedSequence=++loadSequence;busy=true;connected(false);$('#save-alarm').disabled=true;$('#save-bark').disabled=true;$('#save-content').disabled=true;
 try{await api('change',body,auth);if(auth!==token()||generation!==epoch)return false;pending=null;$('#pending-action').hidden=true;await load(true,true);return true;}
 catch(e){if(auth!==token()||generation!==epoch)return false;
  if(!e.status||e.status>=500){pending={data:body,auth};$('#pending-action').hidden=false;}
  else{pending=null;$('#pending-action').hidden=true;if(e.status===409)await load();}
  const id=$('#content-editor').open?'#content-form-error':$('#bark-editor').open?'#bark-form-error':$('#alarm-editor').open?'#alarm-form-error':null;if(id)$(id).textContent=e.message;else notice(e.message);return false;
 }finally{busy=false;connected(!!current);$('#save-alarm').disabled=false;$('#save-bark').disabled=false;$('#save-content').disabled=false;}
}
$('#retry-action').onclick=async()=>{const testing=pending?.data.action==='test';if(pending&&await commit(pending.data)){if(testing){showTestResult=true;renderTestResult();}draft=false;$('#alarm-editor').close();$('#bark-editor').close();$('#content-editor').close();toast('原操作已确认完成');}};
function updateForm(){
 const q=resolveInstrument(field('symbol').value,catalog);
 $('#quote-preview').hidden=!q;$('#quote-preview').textContent=q?`当前价格：${price(q.last)} USDT / ${q.unit}`:'';
}
function checkedFallbacks(){return [...form.querySelectorAll('[name=fallbackExchanges]:checked')].map(input=>input.value);}
function renderFallbackOptions(selected=checkedFallbacks()){
 const main=field('exchange').value;
 $('#fallback-options').innerHTML=FALLBACK_ORDER.filter(key=>key!==main).map(key=>`<label><input type="checkbox" name="fallbackExchanges" value="${key}"${selected.includes(key)?' checked':''}><span>${venue[key]}</span></label>`).join('');
}
function renderCatalog(){
 const query=field('symbol').value.trim();
 const rows=query?catalog.filter(q=>matchesInstrument(query,q)):[];
 if(rows.length)field('symbol').setAttribute('list','alarm-symbols');else field('symbol').removeAttribute('list');
 $('#alarm-symbols').innerHTML=rows.map(q=>`<option value="${esc(instrumentLabel(q))}">${esc(q.base)} · ${esc(price(q.last))} USDT</option>`).join('');
}
const catalogCache=new Map();
async function loadCatalog(){
 const generation=++catalogEpoch,auth=token(),exchange=field('exchange').value,market='future',inputBefore=field('symbol').value;
 catalog=[];$('#alarm-symbols').replaceChildren();field('symbol').removeAttribute('list');$('#quote-preview').textContent='正在载入交易对…';
 try{const key=auth+':'+exchange,cached=catalogCache.get(key);const data=cached&&Date.now()-cached.at<60000?cached.data:await api(`catalog?exchange=${exchange}&market=${market}`,undefined,auth);if(auth===token())catalogCache.set(key,{at:Date.now(),data});if(generation!==catalogEpoch||auth!==token())return;catalog=data.items.sort((a,b)=>instrumentLabel(a).localeCompare(instrumentLabel(b)));const selected=resolveInstrument(inputBefore,catalog);if(editing&&field('symbol').value===inputBefore&&selected)field('symbol').value=instrumentLabel(selected);renderCatalog();updateForm();if(!catalog.length)$('#quote-preview').textContent='此市场行情暂未就绪，稍后重新选择交易所重试。';}catch(e){if(generation===catalogEpoch)$('#quote-preview').textContent=e.message;}
}
function openRule(rule=null){
 if(!verified||!current)return;form.reset();editing=rule?rule.id:null;draft=false;$('#alarm-form-error').textContent='';$('#alarm-editor-title').textContent=editing?'编辑报警':'新增报警';
 let exchange='binance';try{exchange=localStorage.getItem('radar-alarm-exchange')||exchange;}catch{}
 const initial={exchange,condition:'above',repeat:false,...rule};
 for(const name of ['exchange','symbol','condition','target','repeat'])if(initial[name]!==undefined&&initial[name]!==null)field(name).value=String(initial[name]);
 if(rule?.state?.asset?.pair)field('symbol').value=rule.state.asset.pair;
 if(!field('exchange').value)field('exchange').value='binance';
 if(!field('condition').value)field('condition').value='above';
 renderFallbackOptions(fallbackChoices(rule,field('exchange').value));
 updateForm();$('#alarm-editor').showModal();loadCatalog();
}
$('#add-alarm').onclick=()=>openRule();
form.addEventListener('input',e=>{draft=true;if(e.target.name==='symbol')renderCatalog();updateForm();});
form.addEventListener('change',e=>{draft=true;if(e.target.name==='exchange'){field('symbol').value='';renderFallbackOptions();loadCatalog();}updateForm();});
form.onsubmit=async e=>{
 e.preventDefault();$('#alarm-form-error').textContent='';
 const q=resolveInstrument(field('symbol').value,catalog);if(!q){$('#alarm-form-error').textContent='请选择当前交易所列表中的完整交易对';return;}
 const rule={exchange:field('exchange').value,market:'future',symbol:q.symbol,fallbackExchanges:checkedFallbacks(),priceType:'last',condition:field('condition').value,target:field('target').value.trim(),upper:null,repeat:field('repeat').value==='true',hold:0,cooldown:30,hysteresis:'0',level:'critical',note:'',immediate:true,recovery:false,expiresAt:null,enabled:true};
 if(await commit({action:'save',id:editing,rule})){try{localStorage.setItem('radar-alarm-exchange',rule.exchange);}catch{}draft=false;$('#alarm-editor').close();toast('强提醒报警已保存');}
};
let contentRuleId=null;
function openContent(rule){
 contentRuleId=rule.id;draft=false;
 $('#content-context').textContent=(rule.state?.asset?.pair||rule.symbol)+' · '+venue[rule.exchange];
 $('#alarm-content').value=rule.alarmContent||'';$('#content-form-error').textContent='';
 $('#content-editor').showModal();
}
$('#alarm-content').addEventListener('input',()=>{draft=true;});
$('#content-form').onsubmit=async e=>{
 e.preventDefault();$('#content-form-error').textContent='';
 if(await commit({action:'content',id:contentRuleId,alarmContent:$('#alarm-content').value})){
  draft=false;$('#content-editor').close();toast('报警内容已保存，从下一轮生效');
 }
};
const deviceManager=createDeviceManager({api,commit,getState:()=>current,isReady:()=>verified&&!busy&&!pending,toast,onDraft:value=>{draft=value;},onTest:testBark});
function openDevice(){if(verified&&current)deviceManager.open();}
$('#bind-device').onclick=openDevice;
async function testBark(deviceId){
 if(!verified||testSubmitting||busy||pending||!current?.device)return;
 testSubmitting=true;const auth=token(),generation=epoch;
 try{if(await commit({action:'test',...(typeof deviceId==='string'?{deviceId}:{})})&&auth===token()&&generation===epoch){showTestResult=true;renderTestResult();toast('测试请求已提交，请查看发送结果');}}
 finally{testSubmitting=false;connected(!!current);await deviceManager.sync();}
}
$('#test-bark').onclick=()=>testBark();$('#test-bark-inline').onclick=()=>testBark();
$('#bark-editor').addEventListener('close',()=>deviceManager.clear());
$('#alarm-list').onclick=async e=>{const b=e.target.closest('[data-action]');if(!b||busy||!verified)return;const action=b.dataset.action;if(action==='new'){openRule();return;}const r=current?.rules.find(r=>r.id===b.dataset.id);if(!r)return;if(action==='edit')openRule(r);else if(action==='content')openContent(r);else if(action==='delete'&&confirm('删除 '+r.symbol+' 的这条报警？已有触发记录将保留。'))await commit({action:'delete',id:r.id});};
for(const b of document.querySelectorAll('[data-close]'))b.onclick=()=>{if(busy)return;draft=false;$('#'+b.dataset.close).close();};
for(const d of [$('#alarm-editor'),$('#bark-editor'),$('#content-editor')])d.addEventListener('cancel',e=>{if(busy)e.preventDefault();else draft=false;});
for(const button of document.querySelectorAll('[data-filter]'))button.onclick=()=>{statusFilter=button.dataset.filter;renderRules();};
$('#alarm-search').oninput=renderRules;$('#refresh-alarms').onclick=()=>load();
document.addEventListener('radar-profile-changing',()=>{showTestResult=false;clearTimeout(testFeedbackTimer);epoch++;catalogEpoch++;statusFilter='all';clearSnapshots();quoteDisplay.clear();verified=false;current=null;document.querySelector('main').classList.add('is-loading');renderedSignature='';catalogCache.clear();catalog=[];pending=null;draft=false;$('#plan-label').textContent=token()?'当前推送码 · 已连接':'未连接推送码';$('#pending-action').hidden=true;$('#alarm-editor').close();$('#bark-editor').close();$('#content-editor').close();deviceManager.clear();connected(false);renderTestResult();$('#alarm-list').innerHTML='<div class="alarm-empty"><strong>正在载入当前推送码…</strong></div>';});
document.addEventListener('radar-profile-ready',async e=>{lastToken=token();await load(true,true);if(new URLSearchParams(location.search).get('binding')==='1'&&current){history.replaceState(null,'',location.pathname);openDevice();}});
window.addEventListener('beforeunload',e=>{if(draft||pending){e.preventDefault();e.returnValue='';}});
let refreshTimer;
function scheduleRefresh(){clearTimeout(refreshTimer);if(document.visibilityState==='visible')refreshTimer=setTimeout(refreshLoop,2000);}
async function refreshLoop(){clearTimeout(refreshTimer);if(document.visibilityState!=='visible')return;await load(false);scheduleRefresh();}
document.addEventListener('visibilitychange',()=>{clearTimeout(refreshTimer);if(document.visibilityState==='visible')refreshLoop();});
setInterval(()=>{if(document.visibilityState==='visible'&&current)render();},1000);
async function start(){
 const auth=token(),generation=epoch;const firstLoad=load();const snapshot=await readSnapshot(auth);
 if(snapshot&&auth===token()&&generation===epoch&&!verified){try{cachedAt=snapshot.at;current=snapshot.data;render();}catch{current=null;renderedSignature='';clearSnapshots();}}
 await firstLoad;if(new URLSearchParams(location.search).get('new')==='1'&&current&&verified){history.replaceState(null,'',location.pathname);openRule();}if(new URLSearchParams(location.search).get('binding')==='1'&&current&&verified){history.replaceState(null,'',location.pathname);openDevice();}scheduleRefresh();
}
start();
