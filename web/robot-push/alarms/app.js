import {readSnapshot,saveSnapshot,clearSnapshots} from './snapshot.js?v=20261111-cache1';
import {connection} from './session.js?v=20261111-smooth1';
import {patchHTML} from './dom.js?v=20261111-smooth1';
import {matchesInstrument,matchesAlarm,instrumentLabel,resolveInstrument} from './search.js?v=20261112-picker1';
import {presentRule} from './presentation.js?v=20261113-routing1';
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
 const latest=current?.events.find(e=>e.ruleId==='test');
 const sending=latest&&['queued','sending','retry'].includes(latest.status);
 for(const id of ['test-bark-inline','test-bark']){
  const button=$('#'+id);button.disabled=!enabled||busy||!!pending||!current?.device||!!sending;
  button.textContent=busy&&testSubmitting?'提交中…':sending?'发送中…':'测试推送';
  button.setAttribute('aria-busy',String(!!sending||(busy&&testSubmitting)));
 }
}
let testSubmitting=false,showTestResult=false,testFeedbackTimer;
function renderTestResult(){
 const event=current?.events.find(e=>e.ruleId==='test'),output=$('#bark-test-result');
 clearTimeout(testFeedbackTimer);output.hidden=!event||!showTestResult;if(output.hidden){output.textContent='';return;}
 const status={queued:'等待发送',sending:'发送中…',retry:'等待重试',accepted:'Bark 已接受',failed:'发送失败',unknown:'结果未知，请查看手机或报警记录',expired:'已过期',cancelled:'已取消',no_device:'请先绑定设备'};
 output.dataset.state=event.status;
 output.textContent=(status[event.status]||'请查看报警记录')+(event.error?' · '+event.error:'');
 if(event.status==='accepted')testFeedbackTimer=setTimeout(()=>{showTestResult=false;renderTestResult();},8000);
}
function syncPlanLabel(){const code=window.RadarIdentity?.code();$('#plan-label').textContent=!token()?'未连接推送码':!verified?'正在核对当前推送码':code?'当前推送码 · 尾号 '+code.slice(-2):'当前推送码 · 已连接';}
function presentation(r){return presentRule(r,{serverTime:current?.serverTime,elapsed:Math.max(0,performance.now()-snapshotStartedAt)/1000,verified:verified&&!snapshotError});}
function price(value){if(!value)return '—';const n=Number(value);return n>=1?n.toLocaleString('en-US',{maximumFractionDigits:10}):value;}
function description(r){return conditions[r.condition]+' '+price(r.target)+(r.upper?' ～ '+price(r.upper):'')+' USDT';}
function renderRules(){
 if(!current)return;
 const search=$('#alarm-search').value.trim().toLowerCase();
 const rows=current.rules.filter(r=>matchesAlarm(search,r));
 $('#alarm-count').textContent=current.rules.length;
 const selected=new URLSearchParams(location.search).get('rule');
 const focused=document.activeElement?.closest('[data-action]');const restore=focused&&{action:focused.dataset.action,id:focused.dataset.id};
 const markup=rows.length?rows.map(r=>{
  const {status,fresh}=presentation(r);
  return `<article class="alarm-row ${r.id===selected?'is-highlighted':''} ${status==='alarming'?'is-alarming':''}"><div class="alarm-identity"><div class="alarm-rule-title"><strong>${esc(r.state?.asset?.pair||r.symbol)}</strong><span class="alarm-badge ${status==='alarming'?'is-alarming':['watching','confirming'].includes(status)?'is-live':['stale','unavailable'].includes(status)?'is-warning':''}">${labels[status]||'等待行情'}</span></div><small>${venue[r.exchange]} · ${r.market==='future'?'永续':'现货'}${r.priceType==='last'?'':' · 标记价格'}</small><small class="alarm-repeat">${r.repeat?'每 30 秒提醒':'仅一次'}${!r.repeat&&r.hold?' · 持续 '+r.hold+' 秒':''}${r.note?' · '+esc(r.note):''}</small></div><div class="alarm-price-block"><div class="alarm-condition">${esc(description(r))}</div><div class="alarm-current">当前价 <span class="alarm-price">${fresh?esc(price(r.state.price)):'—'}</span></div>${fresh&&r.state?.source?.fallback?`<small>备用行情：${esc(venue[r.state.source.exchange]||r.state.source.exchange)} · 现货 · 最新成交价</small>`:fresh?'':'<small>等待新鲜行情</small>'}</div><div class="alarm-actions"><button data-action="edit" data-id="${r.id}">编辑</button><button data-action="delete" data-id="${r.id}" class="danger-text">删除</button></div></article>`;
 }).join(''):`<div class="alarm-empty"><strong>${current.rules.length?'没有匹配的报警':'还没有价格报警'}</strong><p>${current.rules.length?'尝试输入完整币种或备注。':'选择交易所和币种，设置目标价格。保存后由云端持续监控。'}</p>${current.rules.length?'':'<button data-action="new">＋ 创建第一条报警</button>'}</div>`;
 patchHTML($('#alarm-list'),verified?markup:markup.replaceAll('<button','<button disabled'));
 if(restore)$('#alarm-list').querySelector(`[data-action="${restore.action}"][data-id="${restore.id}"]`)?.focus({preventScroll:true});
}
let renderedSignature='',renderedTestEvents='';
function render(){
 const signature=JSON.stringify([verified,snapshotError,current,current.rules.map(r=>presentation(r))]);if(signature===renderedSignature)return;renderedSignature=signature;
 connection(verified&&!snapshotError);document.querySelector('main').classList.remove('is-loading');$('#alarm-list').setAttribute('aria-busy','false');
 syncPlanLabel();
 connected(true);
 const testEvents=JSON.stringify(current.events);
 if(testEvents!==renderedTestEvents){renderedTestEvents=testEvents;renderTestResult();}
 $('#alarm-status').textContent=snapshotError?'网页状态更新失败，请刷新重试；云端监控独立运行。':!verified?'显示上次数据（'+new Date(cachedAt).toLocaleTimeString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'})+'），正在更新…':'';
 $('#device-label').textContent=current.device?current.device.label+' · 已绑定':'Bark 未绑定';$('#bind-device').classList.toggle('is-bound',!!current.device);
 if(!current.device)notice('先绑定 Bark 接收设备。未绑定时，触发事件只会记入报警记录。');else notice('');
 renderRules();
 for(const button of $('#alarm-list').querySelectorAll('button'))button.disabled=!verified;
}

async function readState(showError=true){
 const auth=token(),generation=epoch,sequence=++loadSequence;if(!auth){clearSnapshots();verified=false;current=null;connected(false);renderTestResult();connection(false);$('#plan-label').textContent='未连接推送码';$('#alarm-status').textContent='请先连接推送码';$('#device-label').textContent='未连接';$('#alarm-list').innerHTML='<div class="alarm-empty"><strong>请先连接推送码</strong><a href="/radar/push-center/">打开推送中心</a></div>';return;}
 const requestStartedAt=performance.now();
 try{const next=await api('state?events=latest-test',undefined,auth);if(auth!==token()||generation!==epoch||sequence<appliedSequence)return;appliedSequence=sequence;verified=true;current=next;snapshotStartedAt=requestStartedAt;snapshotError='';render();saveSnapshot(auth,next);}
 catch(e){if(auth!==token()||generation!==epoch||sequence<appliedSequence)return;appliedSequence=sequence;snapshotError=e.message;if(e.status===401){clearSnapshots();verified=false;current=null;renderedSignature='';connection(false);connected(false);}if(!current){connected(false);$('#alarm-status').textContent='暂时无法读取报警';$('#alarm-list').innerHTML='<div class="alarm-empty">读取失败，可点击刷新重试。</div>';}else render();if(showError||!verified)notice(e.message);if(current&&!verified)$('#alarm-status').textContent='上次数据，更新失败；修改暂不可用，请重试刷新。';}
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
 appliedSequence=++loadSequence;busy=true;connected(false);$('#save-alarm').disabled=true;$('#save-bark').disabled=true;
 try{await api('change',body,auth);if(auth!==token()||generation!==epoch)return false;pending=null;$('#pending-action').hidden=true;await load(true,true);return true;}
 catch(e){if(auth!==token()||generation!==epoch)return false;
  if(!e.status||e.status>=500){pending={data:body,auth};$('#pending-action').hidden=false;}
  else{pending=null;$('#pending-action').hidden=true;if(e.status===409)await load();}
  const id=$('#bark-editor').open?'#bark-form-error':$('#alarm-editor').open?'#alarm-form-error':null;if(id)$(id).textContent=e.message;else notice(e.message);return false;
 }finally{busy=false;connected(!!current);$('#save-alarm').disabled=false;$('#save-bark').disabled=false;}
}
$('#retry-action').onclick=async()=>{const testing=pending?.data.action==='test';if(pending&&await commit(pending.data)){if(testing){showTestResult=true;renderTestResult();}draft=false;$('#alarm-editor').close();$('#bark-editor').close();toast('原操作已确认完成');}};
function updateForm(){
 const q=resolveInstrument(field('symbol').value,catalog);
 $('#quote-preview').hidden=!q;$('#quote-preview').textContent=q?`当前价格：${price(q.last)} USDT / ${q.unit}`:'';
}
function renderFallbackOptions(selected=field('fallbackExchange').value||'auto'){
 const main=field('exchange').value;
 field('fallbackExchange').innerHTML='<option value="auto">自动选择</option><option value="off">关闭备用切换</option>'+Object.entries(venue).filter(([key])=>key!==main).map(([key,name])=>`<option value="${key}">${name} · 现货</option>`).join('');
 field('fallbackExchange').value=selected===main?'auto':selected;
 if(!field('fallbackExchange').value)field('fallbackExchange').value='auto';
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
 renderFallbackOptions(rule?.fallbackExchange||'auto');
 updateForm();$('#alarm-editor').showModal();loadCatalog();
}
$('#add-alarm').onclick=()=>openRule();
form.addEventListener('input',e=>{draft=true;if(e.target.name==='symbol')renderCatalog();updateForm();});
form.addEventListener('change',e=>{draft=true;if(e.target.name==='exchange'){field('symbol').value='';renderFallbackOptions();loadCatalog();}updateForm();});
form.onsubmit=async e=>{
 e.preventDefault();$('#alarm-form-error').textContent='';
 const q=resolveInstrument(field('symbol').value,catalog);if(!q){$('#alarm-form-error').textContent='请选择当前交易所列表中的完整交易对';return;}
 const rule={exchange:field('exchange').value,market:'future',symbol:q.symbol,fallbackExchange:field('fallbackExchange').value,priceType:'last',condition:field('condition').value,target:field('target').value.trim(),upper:null,repeat:field('repeat').value==='true',hold:0,cooldown:30,hysteresis:'0',level:'critical',note:'',immediate:true,recovery:false,expiresAt:null,enabled:true};
 if(await commit({action:'save',id:editing,rule})){try{localStorage.setItem('radar-alarm-exchange',rule.exchange);}catch{}draft=false;$('#alarm-editor').close();toast('强提醒报警已保存');}
};
function openDevice(){if(!verified||!current)return;barkForm.reset();draft=false;$('#bark-form-error').textContent='';$('#bark-existing').hidden=!current.device;barkForm.elements.label.value=current.device?.label||'我的 iPhone';$('#bark-current').textContent=current.device?`当前设备：${current.device.label}。如需更换，请填写新设备地址后保存。`:'绑定到当前推送码。切换网页方案不会转移此设备。';$('#bark-editor').showModal();}
$('#bind-device').onclick=openDevice;barkForm.oninput=()=>{draft=true;};
barkForm.onsubmit=async e=>{e.preventDefault();if(await commit({action:'bind',key:barkForm.elements.key.value,label:barkForm.elements.label.value})){barkForm.elements.key.value='';draft=false;$('#bark-editor').close();toast('Bark 已绑定，可发送一条测试通知检查手机');}};
async function testBark(){
 if(!verified||testSubmitting||busy||pending||!current?.device)return;
 testSubmitting=true;
 const auth=token(),generation=epoch;
 try{if(await commit({action:'test'})&&auth===token()&&generation===epoch){
  showTestResult=true;renderTestResult();
  $('#bark-form-error').textContent='测试请求已提交，发送结果会显示在页面及报警记录中。';
  toast('测试请求已提交，请查看发送结果');
 }}finally{testSubmitting=false;connected(!!current);}
}
$('#test-bark').onclick=testBark;$('#test-bark-inline').onclick=testBark;
$('#unbind-bark').onclick=async()=>{if(confirm('解除当前 Bark 绑定？报警规则会保留，尚未发送的通知将取消。')&&await commit({action:'unbind'})){draft=false;$('#bark-editor').close();toast('已解除 Bark 绑定');}};
$('#alarm-list').onclick=async e=>{const b=e.target.closest('[data-action]');if(!b||busy||!verified)return;const action=b.dataset.action;if(action==='new'){openRule();return;}const r=current?.rules.find(r=>r.id===b.dataset.id);if(!r)return;if(action==='edit')openRule(r);else if(action==='delete'&&confirm('删除 '+r.symbol+' 的这条报警？已有触发记录将保留。'))await commit({action:'delete',id:r.id});};
for(const b of document.querySelectorAll('[data-close]'))b.onclick=()=>{if(busy)return;draft=false;$('#'+b.dataset.close).close();};
for(const d of [$('#alarm-editor'),$('#bark-editor')])d.addEventListener('cancel',e=>{if(busy)e.preventDefault();else draft=false;});
$('#alarm-search').oninput=renderRules;$('#refresh-alarms').onclick=()=>load();
document.addEventListener('radar-profile-changing',()=>{showTestResult=false;clearTimeout(testFeedbackTimer);epoch++;catalogEpoch++;clearSnapshots();verified=false;current=null;document.querySelector('main').classList.add('is-loading');renderedSignature='';catalogCache.clear();catalog=[];pending=null;draft=false;$('#plan-label').textContent=token()?'当前推送码 · 已连接':'未连接推送码';$('#pending-action').hidden=true;$('#alarm-editor').close();$('#bark-editor').close();barkForm.elements.key.value='';connected(false);renderTestResult();$('#alarm-list').innerHTML='<div class="alarm-empty"><strong>正在载入当前推送码…</strong></div>';});
document.addEventListener('radar-profile-ready',async e=>{lastToken=token();await load(true,true);if(new URLSearchParams(location.search).get('binding')==='1'&&current){history.replaceState(null,'',location.pathname);openDevice();}});
window.addEventListener('beforeunload',e=>{if(draft||pending){e.preventDefault();e.returnValue='';}});
let refreshTimer;
function scheduleRefresh(){clearTimeout(refreshTimer);if(document.visibilityState==='visible')refreshTimer=setTimeout(refreshLoop,2000);}
async function refreshLoop(){clearTimeout(refreshTimer);if(document.visibilityState!=='visible')return;await load(false);scheduleRefresh();}
document.addEventListener('visibilitychange',()=>{clearTimeout(refreshTimer);if(document.visibilityState==='visible')refreshLoop();});
setInterval(()=>{if(document.visibilityState==='visible'&&current)render();},1000);
async function start(){
 const auth=token(),generation=epoch;const snapshot=await readSnapshot(auth);
 if(snapshot&&auth===token()&&generation===epoch&&!verified){try{cachedAt=snapshot.at;current=snapshot.data;render();}catch{current=null;renderedSignature='';clearSnapshots();}}
 await load();if(new URLSearchParams(location.search).get('binding')==='1'&&current&&verified){history.replaceState(null,'',location.pathname);openDevice();}scheduleRefresh();
}
start();
