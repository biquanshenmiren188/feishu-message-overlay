import {connection} from './session.js?v=20261111-smooth1';
import {patchHTML} from './dom.js?v=20261111-smooth1';
import {matchesInstrument,matchesAlarm} from './search.js?v=20261106-exact1';
const $=s=>document.querySelector(s),form=$('#alarm-form'),barkForm=$('#bark-form');
const field=n=>form.elements.namedItem(n),API='/radar/alarms-api/';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const venue={binance:'Binance',bybit:'Bybit',okx:'OKX',bitget:'Bitget',gate:'Gate',aster:'Aster'};
const conditions={above:'上穿',below:'下穿',enter:'进入区间',exit:'离开区间'};
const labels={watching:'监控中',waiting:'等待下次穿越',confirming:'持续确认中',paused:'已暂停',expired:'已到期',triggered:'已触发',stale:'行情中断',unavailable:'价格暂缺'};
const deliveries={queued:'等待发送',sending:'发送中',accepted:'接口接受',retry:'等待重试',failed:'发送失败',unknown:'结果未知',expired:'已过期',cancelled:'已取消',no_device:'未绑定设备'};
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
 for(const id of ['add-alarm','bind-device','master-enabled'])$('#'+id).disabled=!enabled||busy;
 const latest=current?.events.find(e=>e.ruleId==='test');
 const sending=latest&&['queued','sending','retry'].includes(latest.status);
 for(const id of ['test-bark-inline','test-bark']){
  const button=$('#'+id);button.disabled=!enabled||busy||!!pending||!current?.device||!!sending;
  button.textContent=busy&&testSubmitting?'提交中…':sending?'发送中…':'测试推送';
  button.setAttribute('aria-busy',String(!!sending||(busy&&testSubmitting)));
 }
}
let testSubmitting=false;
function renderTestResult(){
 const event=current?.events.find(e=>e.ruleId==='test'),output=$('#bark-test-result');
 output.hidden=!event;if(!event){output.textContent='';return;}
 const status={queued:'测试消息已加入后台队列，等待发送。',sending:'后台正在向 Bark 发送测试消息…',retry:'暂未发送成功，后台等待重试。',accepted:'Bark 已接受测试消息，请查看手机通知；接口接受不代表手机已显示。',failed:'测试推送失败。',unknown:'发送结果未知，请先查看手机和报警记录，避免重复发送。',expired:'测试消息已过期，未完成发送。',cancelled:'测试推送已取消。',no_device:'未绑定 Bark 设备，无法发送。'};
 output.dataset.state=event.status;
 output.textContent='最近测试 · '+new Date(event.at*1000).toLocaleTimeString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'})+' · '+(status[event.status]||'请查看报警记录。')+(event.error?' 原因：'+event.error:'');
}
function syncPlanLabel(){const code=window.RadarIdentity?.code();$('#plan-label').textContent=!token()?'未连接推送码':code?'当前推送码 · 尾号 '+code.slice(-2):'当前推送码 · 已连接';}
function safeStatus(r){if(!r.enabled)return 'paused';if(r.expiresAt&&r.expiresAt<Date.now()/1000)return 'expired';if(r.state?.status==='triggered')return 'triggered';if(r.state?.sampleAt&&Date.now()/1000-r.state.sampleAt>12)return 'stale';return r.state?.status||'waiting';}
function price(value){if(!value)return '—';const n=Number(value);return n>=1?n.toLocaleString('en-US',{maximumFractionDigits:10}):value;}
function description(r){return conditions[r.condition]+' '+price(r.target)+(r.upper?' ～ '+price(r.upper):'')+' USDT';}
function renderRules(){
 if(!current)return;
 const search=$('#alarm-search').value.trim().toLowerCase(),filter=$('#alarm-filter').value;
 const rows=current.rules.filter(r=>matchesAlarm(search,r)).filter(r=>filter==='all'||filter==='active'?! (filter==='active'&&['paused','expired','triggered'].includes(safeStatus(r))):safeStatus(r)===filter);
 $('#alarm-count').textContent=current.rules.length;
 const selected=new URLSearchParams(location.search).get('rule');
 const focused=document.activeElement?.closest('[data-action]');const restore=focused&&{action:focused.dataset.action,id:focused.dataset.id};
 const markup=rows.length?rows.map(r=>{
  const status=current.enabled?safeStatus(r):'paused',fresh=r.state?.sampleAt&&Date.now()/1000-r.state.sampleAt<=12;
  return `<article class="alarm-row ${r.id===selected?'is-highlighted':''}"><div><strong>${esc(r.symbol)}</strong><span class="alarm-badge ${['watching','confirming'].includes(status)?'is-live':['stale','unavailable'].includes(status)?'is-warning':''}">${labels[status]||'等待行情'}</span><small>${venue[r.exchange]} · ${r.market==='future'?'永续':'现货'} · ${r.priceType==='last'?'最新成交价':'标记价格'}</small><small>${r.repeat?'重复触发':'仅一次'}${r.hold?' · 持续 '+r.hold+' 秒':''}${r.note?' · '+esc(r.note):''}</small></div><div class="alarm-price-block"><div class="alarm-price">${fresh?esc(price(r.state.price)):'—'}</div><div class="alarm-condition">${esc(description(r))}</div><small>${fresh?'最近采样 '+new Date(r.state.sampleAt*1000).toLocaleTimeString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'}):'等待新鲜行情'}</small></div><div class="alarm-actions"><button data-action="edit" data-id="${r.id}">编辑</button><button data-action="toggle" data-id="${r.id}">${r.enabled?'暂停':'启用'}</button><button data-action="copy" data-id="${r.id}">复制</button><button data-action="delete" data-id="${r.id}" class="danger-text">删除</button></div></article>`;
 }).join(''):`<div class="alarm-empty"><strong>${current.rules.length?'没有匹配的报警':'还没有价格报警'}</strong><p>${current.rules.length?'尝试其他币种或切换状态筛选。':'选择交易所和币种，设置目标价格。保存后由云端持续监控。'}</p>${current.rules.length?'':'<button data-action="new">＋ 创建第一条报警</button>'}</div>`;
 patchHTML($('#alarm-list'),markup);
 if(restore)$('#alarm-list').querySelector(`[data-action="${restore.action}"][data-id="${restore.id}"]`)?.focus({preventScroll:true});
}
let renderedSignature='';
function render(){
 const signature=JSON.stringify([current,current.rules.map(safeStatus)]);if(signature===renderedSignature)return;renderedSignature=signature;
 connection(true);document.querySelector('main').classList.remove('is-loading');$('#alarm-list').setAttribute('aria-busy','false');
 syncPlanLabel();
 connected(true);renderTestResult();$('#master-enabled').checked=current.enabled;
 $('#alarm-status').textContent=current.enabled?'规则保存后生效，当前推送码独立运行。':'当前推送码的全部价格报警已暂停。';
 $('#device-label').textContent=current.device?current.device.label+' · 已绑定':'Bark 未绑定';$('#bind-device').classList.toggle('is-bound',!!current.device);
 if(!current.device)notice('先绑定 Bark 接收设备。未绑定时，触发事件只会记入报警记录。');else notice('');
 renderRules();
}

async function readState(showError=true){
 const auth=token(),generation=epoch,sequence=++loadSequence;if(!auth){current=null;connected(false);renderTestResult();connection(false);$('#plan-label').textContent='未连接推送码';$('#alarm-status').textContent='请先连接推送码';$('#device-label').textContent='未连接';$('#alarm-list').innerHTML='<div class="alarm-empty"><strong>请先连接推送码</strong><a href="/radar/push-center/">打开推送中心</a></div>';return;}
 try{const next=await api('state?events=latest-test',undefined,auth);if(auth!==token()||generation!==epoch||sequence<appliedSequence)return;appliedSequence=sequence;current=next;render();}
 catch(e){if(auth!==token()||generation!==epoch||sequence<appliedSequence)return;appliedSequence=sequence;if(e.status===401){current=null;renderedSignature='';connection(false);connected(false);}if(!current){connected(false);$('#alarm-status').textContent='暂时无法读取报警';$('#alarm-list').innerHTML='<div class="alarm-empty">读取失败，可点击刷新重试。</div>';}if(showError)notice(e.message);}
}
let reading=null;
async function load(showError=true,force=false){
 if(reading){await reading;if(!force)return;}
 const request=readState(showError);reading=request;try{await request;}finally{if(reading===request)reading=null;}
}
async function commit(data){
 if(busy)return false;
 if(pending&&data!==pending.data){toast('请先重试结果未确认的原操作');return false;}
 const auth=token(),generation=epoch;
 if(!current||!auth){toast('请先连接推送码并载入规则');return false;}
 const body=pending?.data||{...data,requestId:crypto.randomUUID().replaceAll('-',''),revision:current.revision};
 appliedSequence=++loadSequence;busy=true;connected(false);$('#save-alarm').disabled=true;$('#save-bark').disabled=true;
 try{await api('change',body,auth);if(auth!==token()||generation!==epoch)return false;pending=null;$('#pending-action').hidden=true;await load(true,true);return true;}
 catch(e){if(auth!==token()||generation!==epoch)return false;
  if(!e.status||e.status>=500){pending={data:body,auth};$('#pending-action').hidden=false;}
  else{pending=null;$('#pending-action').hidden=true;if(e.status===409)await load();}
  const id=$('#bark-editor').open?'#bark-form-error':$('#alarm-editor').open?'#alarm-form-error':null;if(id)$(id).textContent=e.message;else notice(e.message);return false;
 }finally{busy=false;connected(!!current);$('#save-alarm').disabled=false;$('#save-bark').disabled=false;}
}
$('#retry-action').onclick=async()=>{if(pending&&await commit(pending.data)){draft=false;$('#alarm-editor').close();$('#bark-editor').close();toast('原操作已确认完成');}};
function updateForm(){
 const repeat=field('repeat').value==='true',q=catalog.find(q=>q.symbol===field('symbol').value);
 $('#repeat-help').hidden=!repeat;
 $('#quote-preview').hidden=!q;$('#quote-preview').textContent=q?`当前价格：${price(q.last)} USDT / ${q.unit}`:'';
}
function renderCatalog(){
 const query=field('symbol').value.trim();
 const rows=query?catalog.filter(q=>matchesInstrument(query,q)):[];
 if(rows.length)field('symbol').setAttribute('list','alarm-symbols');else field('symbol').removeAttribute('list');
 $('#alarm-symbols').innerHTML=rows.map(q=>`<option value="${esc(q.symbol)}">${esc(q.base)} · ${esc(price(q.last))} USDT</option>`).join('');
}
const catalogCache=new Map();
async function loadCatalog(){
 const generation=++catalogEpoch,auth=token(),exchange=field('exchange').value,market='future';
 catalog=[];$('#alarm-symbols').replaceChildren();field('symbol').removeAttribute('list');$('#quote-preview').textContent='正在载入交易对…';
 try{const key=auth+':'+exchange,cached=catalogCache.get(key);const data=cached&&Date.now()-cached.at<60000?cached.data:await api(`catalog?exchange=${exchange}&market=${market}`,undefined,auth);if(auth===token())catalogCache.set(key,{at:Date.now(),data});if(generation!==catalogEpoch||auth!==token())return;catalog=data.items.sort((a,b)=>a.symbol.localeCompare(b.symbol));renderCatalog();updateForm();if(!catalog.length)$('#quote-preview').textContent='此市场行情暂未就绪，稍后重新选择交易所重试。';}catch(e){if(generation===catalogEpoch)$('#quote-preview').textContent=e.message;}
}
function openRule(rule=null,copy=false){
 if(!current)return;form.reset();editing=rule&&!copy?rule.id:null;draft=false;$('#alarm-form-error').textContent='';$('#alarm-editor-title').textContent=editing?'编辑报警':copy?'复制报警':'新增报警';
 let exchange='binance';try{exchange=localStorage.getItem('radar-alarm-exchange')||exchange;}catch{}
 const initial={exchange,condition:'above',repeat:false,...rule};
 for(const name of ['exchange','symbol','condition','target','repeat'])if(initial[name]!==undefined&&initial[name]!==null)field(name).value=String(initial[name]);
 if(!field('exchange').value)field('exchange').value='binance';
 if(!field('condition').value)field('condition').value='above';
 $('#legacy-rule-help').hidden=!rule;
 updateForm();$('#alarm-editor').showModal();loadCatalog();
}
$('#add-alarm').onclick=()=>openRule();
form.addEventListener('input',e=>{draft=true;if(e.target.name==='symbol')renderCatalog();updateForm();});
form.addEventListener('change',e=>{draft=true;if(e.target.name==='exchange'){field('symbol').value='';loadCatalog();}updateForm();});
form.onsubmit=async e=>{
 e.preventDefault();$('#alarm-form-error').textContent='';
 const q=catalog.find(q=>q.symbol===field('symbol').value);if(!q){$('#alarm-form-error').textContent='请选择当前交易所列表中的完整交易对';return;}
 const rule={exchange:field('exchange').value,market:'future',symbol:field('symbol').value,priceType:'last',condition:field('condition').value,target:field('target').value.trim(),upper:null,repeat:field('repeat').value==='true',hold:0,cooldown:300,hysteresis:'0',level:'critical',note:'',immediate:true,recovery:false,expiresAt:null,enabled:editing?(current.rules.find(r=>r.id===editing)?.enabled??true):true};
 if(await commit({action:'save',id:editing,rule})){try{localStorage.setItem('radar-alarm-exchange',rule.exchange);}catch{}draft=false;$('#alarm-editor').close();toast('强提醒报警已保存');}
};
function openDevice(){if(!current)return;barkForm.reset();draft=false;$('#bark-form-error').textContent='';$('#bark-existing').hidden=!current.device;barkForm.elements.label.value=current.device?.label||'我的 iPhone';$('#bark-current').textContent=current.device?`当前设备：${current.device.label}。如需更换，请填写新设备地址后保存。`:'绑定到当前推送码。切换网页方案不会转移此设备。';$('#bark-editor').showModal();}
$('#bind-device').onclick=openDevice;barkForm.oninput=()=>{draft=true;};
barkForm.onsubmit=async e=>{e.preventDefault();if(await commit({action:'bind',key:barkForm.elements.key.value,label:barkForm.elements.label.value})){barkForm.elements.key.value='';draft=false;$('#bark-editor').close();toast('Bark 已绑定，可发送一条测试通知检查手机');}};
async function testBark(){
 if(testSubmitting||busy||pending||!current?.device)return;
 testSubmitting=true;
 const auth=token(),generation=epoch;
 try{if(await commit({action:'test'})&&auth===token()&&generation===epoch){
  $('#bark-form-error').textContent='测试请求已提交，发送结果会显示在页面及报警记录中。';
  toast('测试请求已提交，请查看发送结果');
 }}finally{testSubmitting=false;connected(!!current);}
}
$('#test-bark').onclick=testBark;$('#test-bark-inline').onclick=testBark;
$('#unbind-bark').onclick=async()=>{if(confirm('解除当前 Bark 绑定？报警规则会保留，尚未发送的通知将取消。')&&await commit({action:'unbind'})){draft=false;$('#bark-editor').close();toast('已解除 Bark 绑定');}};
$('#master-enabled').onchange=async e=>{const enabled=e.target.checked;if(!await commit({action:'enabled',enabled}))e.target.checked=current?.enabled||false;else toast(enabled?'已恢复云端报警':'已暂停当前推送码的全部报警');};
$('#alarm-list').onclick=async e=>{const b=e.target.closest('[data-action]');if(!b||busy)return;const action=b.dataset.action;if(action==='new'){openRule();return;}const r=current?.rules.find(r=>r.id===b.dataset.id);if(!r)return;if(action==='edit'||action==='copy')openRule(r,action==='copy');else if(action==='toggle')await commit({action:'toggle',id:r.id,enabled:!r.enabled});else if(action==='delete'&&confirm('删除 '+r.symbol+' 的这条报警？已有触发记录将保留。'))await commit({action:'delete',id:r.id});};
for(const b of document.querySelectorAll('[data-close]'))b.onclick=()=>{if(busy)return;if(draft&&!confirm('放弃尚未保存的修改？'))return;draft=false;$('#'+b.dataset.close).close();};
for(const d of [$('#alarm-editor'),$('#bark-editor')])d.addEventListener('cancel',e=>{if(busy||(draft&&!confirm('放弃尚未保存的修改？')))e.preventDefault();else draft=false;});
$('#alarm-search').oninput=renderRules;$('#alarm-filter').onchange=renderRules;$('#refresh-alarms').onclick=()=>load();
document.addEventListener('radar-profile-changing',()=>{epoch++;catalogEpoch++;current=null;document.querySelector('main').classList.add('is-loading');renderedSignature='';catalogCache.clear();catalog=[];pending=null;draft=false;$('#plan-label').textContent=token()?'当前推送码 · 已连接':'未连接推送码';$('#pending-action').hidden=true;$('#alarm-editor').close();$('#bark-editor').close();barkForm.elements.key.value='';connected(false);renderTestResult();$('#alarm-list').innerHTML='<div class="alarm-empty"><strong>正在载入当前推送码…</strong></div>';});
document.addEventListener('radar-profile-ready',async e=>{lastToken=token();await load(true,true);if(new URLSearchParams(location.search).get('binding')==='1'&&current){history.replaceState(null,'',location.pathname);openDevice();}});
window.addEventListener('beforeunload',e=>{if(draft||pending){e.preventDefault();e.returnValue='';}});
let refreshTimer;
function scheduleRefresh(){clearTimeout(refreshTimer);if(document.visibilityState==='visible')refreshTimer=setTimeout(refreshLoop,5000);}
async function refreshLoop(){clearTimeout(refreshTimer);if(document.visibilityState!=='visible')return;await load(false);scheduleRefresh();}
document.addEventListener('visibilitychange',()=>{clearTimeout(refreshTimer);if(document.visibilityState==='visible')refreshLoop();});
load().then(()=>{if(new URLSearchParams(location.search).get('binding')==='1'&&current){history.replaceState(null,'',location.pathname);openDevice();}scheduleRefresh();});
