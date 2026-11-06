const $=s=>document.querySelector(s),form=$('#alarm-form'),barkForm=$('#bark-form');
const field=n=>form.elements.namedItem(n),API='/radar/alarms-api/';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const venue={binance:'Binance',bybit:'Bybit',okx:'OKX',bitget:'Bitget',gate:'Gate',aster:'Aster'};
const conditions={above:'上穿',below:'下穿',enter:'进入区间',exit:'离开区间'};
const labels={watching:'监控中',waiting:'等待下次穿越',confirming:'持续确认中',paused:'已暂停',expired:'已到期',triggered:'已触发',stale:'行情中断',unavailable:'价格暂缺'};
const deliveries={queued:'等待发送',sending:'发送中',accepted:'接口接受',retry:'等待重试',failed:'发送失败',unknown:'结果未知',expired:'已过期',cancelled:'已取消',no_device:'未绑定设备'};
let current=null,catalog=[],editing=null,busy=false,epoch=0,lastToken='',pending=null,draft=false,toastTimer,catalogEpoch=0;
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
function connected(enabled){for(const id of ['add-alarm','bind-device','master-enabled'])$('#'+id).disabled=!enabled||busy;}
function safeStatus(r){if(!r.enabled)return 'paused';if(r.expiresAt&&r.expiresAt<Date.now()/1000)return 'expired';if(r.state?.status==='triggered')return 'triggered';if(r.state?.sampleAt&&Date.now()/1000-r.state.sampleAt>12)return 'stale';return r.state?.status||'waiting';}
function price(value){if(!value)return '—';const n=Number(value);return n>=1?n.toLocaleString('en-US',{maximumFractionDigits:10}):value;}
function description(r){return conditions[r.condition]+' '+price(r.target)+(r.upper?' ～ '+price(r.upper):'')+' USDT';}
function renderRules(){
 if(!current)return;
 const search=$('#alarm-search').value.trim().toLowerCase(),filter=$('#alarm-filter').value;
 const rows=current.rules.filter(r=>(r.symbol+' '+r.note+' '+r.exchange).toLowerCase().includes(search)).filter(r=>filter==='all'||filter==='active'?! (filter==='active'&&['paused','expired','triggered'].includes(safeStatus(r))):safeStatus(r)===filter);
 $('#alarm-count').textContent=current.rules.length;
 const selected=new URLSearchParams(location.search).get('rule');
 const focused=document.activeElement?.closest('[data-action]');const restore=focused&&{action:focused.dataset.action,id:focused.dataset.id};
 $('#alarm-list').innerHTML=rows.length?rows.map(r=>{
  const status=current.enabled?safeStatus(r):'paused',fresh=r.state?.sampleAt&&Date.now()/1000-r.state.sampleAt<=12;
  return `<article class="alarm-row ${r.id===selected?'is-highlighted':''}"><div><strong>${esc(r.symbol)}</strong><span class="alarm-badge ${['watching','confirming'].includes(status)?'is-live':['stale','unavailable'].includes(status)?'is-warning':''}">${labels[status]||'等待行情'}</span><small>${venue[r.exchange]} · ${r.market==='future'?'永续':'现货'} · ${r.priceType==='last'?'最新成交价':'标记价格'}</small><small>${r.repeat?'重复触发':'仅一次'}${r.hold?' · 持续 '+r.hold+' 秒':''}${r.note?' · '+esc(r.note):''}</small></div><div class="alarm-price-block"><div class="alarm-price">${fresh?esc(price(r.state.price)):'—'}</div><div class="alarm-condition">${esc(description(r))}</div><small>${fresh?'最近采样 '+new Date(r.state.sampleAt*1000).toLocaleTimeString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'}):'等待新鲜行情'}</small></div><div class="alarm-actions"><button data-action="edit" data-id="${r.id}">编辑</button><button data-action="toggle" data-id="${r.id}">${r.enabled?'暂停':'启用'}</button><button data-action="copy" data-id="${r.id}">复制</button><button data-action="delete" data-id="${r.id}" class="danger-text">删除</button></div></article>`;
 }).join(''):`<div class="alarm-empty"><strong>${current.rules.length?'没有匹配的报警':'还没有价格报警'}</strong><p>${current.rules.length?'尝试其他币种或切换状态筛选。':'选择交易所和币种，设置目标价格。保存后由云端持续监控。'}</p>${current.rules.length?'':'<button data-action="new">＋ 创建第一条报警</button>'}</div>`;
 if(restore)$('#alarm-list').querySelector(`[data-action="${restore.action}"][data-id="${restore.id}"]`)?.focus({preventScroll:true});
}
function render(){
 connected(true);$('#master-enabled').checked=current.enabled;
 $('#alarm-status').textContent=current.enabled?'规则保存后生效，当前推送码独立运行。':'当前推送码的全部价格报警已暂停。';
 $('#device-label').textContent=current.device?current.device.label+' · 已绑定':'Bark 未绑定';$('#bind-device').classList.toggle('is-bound',!!current.device);
 if(!current.device)notice('先绑定 Bark 接收设备。未绑定时，触发事件只会记入报警记录。');else notice('');
 renderRules();$('#event-count').textContent=current.events.length;
 const opened=new Set([...$('#event-list').querySelectorAll('details[open]')].map(d=>d.dataset.id));
 $('#event-list').innerHTML=current.events.length?current.events.map(e=>`<details data-id="${e.id}" ${opened.has(e.id)?'open':''}><summary><span>${esc(e.title)}<time>${new Date(e.at*1000).toLocaleString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'})} 北京时间</time></span><span class="alarm-badge ${e.status==='accepted'?'is-live':['unknown','failed','no_device'].includes(e.status)?'is-warning':''}">${deliveries[e.status]||e.status}</span></summary><pre>${esc(e.body)}</pre>${e.error?'<p class="event-error">'+esc(e.error)+'</p>':''}<p class="event-error">发送尝试 ${e.attempts} 次 · ${esc(e.id.slice(-8))}</p></details>`).join(''):'<p class="alarm-empty-small">暂无触发记录。达到条件后，会在这里显示触发价格和发送结果。</p>';
}
async function load(showError=true){
 const auth=token(),generation=epoch;if(!auth){current=null;connected(false);return;}
 try{const next=await api('state',undefined,auth);if(auth!==token()||generation!==epoch)return;current=next;render();}
 catch(e){if(auth!==token()||generation!==epoch)return;connected(false);if(showError)notice(e.message);}
}
async function commit(data){
 if(busy)return false;
 if(pending&&data!==pending.data){toast('请先重试结果未确认的原操作');return false;}
 const auth=token(),generation=epoch;
 if(!current||!auth){toast('请先连接推送码并载入规则');return false;}
 const body=pending?.data||{...data,requestId:crypto.randomUUID().replaceAll('-',''),revision:current.revision};
 busy=true;connected(false);$('#save-alarm').disabled=true;$('#save-bark').disabled=true;
 try{await api('change',body,auth);if(auth!==token()||generation!==epoch)return false;pending=null;$('#pending-action').hidden=true;await load();return true;}
 catch(e){if(auth!==token()||generation!==epoch)return false;
  if(!e.status||e.status>=500){pending={data:body,auth};$('#pending-action').hidden=false;}
  else{pending=null;$('#pending-action').hidden=true;if(e.status===409)await load();}
  const id=$('#bark-editor').open?'#bark-form-error':$('#alarm-editor').open?'#alarm-form-error':null;if(id)$(id).textContent=e.message;else notice(e.message);return false;
 }finally{busy=false;connected(!!current);$('#save-alarm').disabled=false;$('#save-bark').disabled=false;}
}
$('#retry-action').onclick=async()=>{if(pending&&await commit(pending.data)){draft=false;$('#alarm-editor').close();$('#bark-editor').close();toast('原操作已确认完成');}};
function updateForm(){
 const range=['enter','exit'].includes(field('condition').value),repeat=field('repeat').value==='true',spot=field('market').value==='spot';
 $('#upper-field').hidden=!range;field('upper').required=range;$('#target-label').textContent=range?'区间下限（USDT）':'目标价格（USDT）';
 $('#repeat-fields').hidden=!repeat;$('#repeat-help').hidden=!repeat;$('#expiry-field').hidden=field('validity').value!=='until';field('expiresAt').required=field('validity').value==='until';
 field('priceType').options[1].disabled=spot;if(spot)field('priceType').value='last';
 const q=catalog.find(q=>q.symbol===field('symbol').value);
 $('#quote-preview').textContent=q?`当前${field('priceType').value==='last'?'最新成交价':'标记价格'}：${price(q[field('priceType').value])} USDT / ${q.unit}。按交易对原始报价，不自动缩放。`:'请选择列表中的完整交易对；不同交易所、千倍合约分别设置。';
 $('#rule-preview').textContent=field('symbol').value&&field('target').value?`${venue[field('exchange').value]} ${field('symbol').value} ${field('market').value==='future'?'永续':'现货'}的${field('priceType').value==='last'?'最新成交价':'标记价格'}${conditions[field('condition').value]} ${field('target').value}${range?' ～ '+field('upper').value:''} USDT${field('hold').value!=='0'?'，连续采样确认 '+field('hold').value+' 秒':''}，通过 Bark ${repeat?'重复报警':'报警一次'}。`:'填写条件后预览报警规则。';
}
async function loadCatalog(){
 const generation=++catalogEpoch,auth=token(),exchange=field('exchange').value,market=field('market').value;
 catalog=[];$('#alarm-symbols').replaceChildren();$('#quote-preview').textContent='正在载入交易对…';
 try{const data=await api(`catalog?exchange=${exchange}&market=${market}`,undefined,auth);if(generation!==catalogEpoch||auth!==token())return;catalog=data.items;$('#alarm-symbols').innerHTML=catalog.sort((a,b)=>a.symbol.localeCompare(b.symbol)).map(q=>`<option value="${esc(q.symbol)}">${esc(q.base)} · ${esc(price(q.last))} USDT</option>`).join('');updateForm();if(!catalog.length)$('#quote-preview').textContent='此市场行情暂未就绪，稍后重新选择交易所重试。';}catch(e){if(generation===catalogEpoch)$('#quote-preview').textContent=e.message;}
}
function openRule(rule=null,copy=false){
 if(!current)return;form.reset();editing=rule&&!copy?rule.id:null;draft=false;$('#alarm-form-error').textContent='';$('#alarm-editor-title').textContent=editing?'编辑报警':copy?'复制报警':'新增报警';
 const initial={exchange:'binance',market:'future',priceType:'last',condition:'above',hold:0,cooldown:300,hysteresis:'0.2',repeat:false,level:'active',...rule};
 for(const name of ['exchange','market','symbol','priceType','condition','target','upper','repeat','hold','cooldown','hysteresis','level','note'])if(initial[name]!==undefined&&initial[name]!==null)field(name).value=String(initial[name]);
 for(const name of ['immediate','recovery'])field(name).checked=!!initial[name];
 if(initial.expiresAt){field('validity').value='until';const d=new Date(initial.expiresAt*1000);field('expiresAt').value=new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);}
 updateForm();$('#alarm-editor').showModal();loadCatalog();
}
$('#add-alarm').onclick=()=>openRule();
form.addEventListener('input',()=>{draft=true;updateForm();});
form.addEventListener('change',e=>{draft=true;if(['exchange','market'].includes(e.target.name)){field('symbol').value='';loadCatalog();}updateForm();});
form.onsubmit=async e=>{
 e.preventDefault();$('#alarm-form-error').textContent='';
 const q=catalog.find(q=>q.symbol===field('symbol').value);if(!q){$('#alarm-form-error').textContent='请选择当前交易所列表中的完整交易对';return;}
 const rule={};for(const n of ['exchange','market','symbol','priceType','condition','target','upper','hysteresis','level','note'])rule[n]=field(n).value.trim();
 for(const n of ['hold','cooldown'])rule[n]=Number(field(n).value);
 rule.repeat=field('repeat').value==='true';for(const n of ['immediate','recovery'])rule[n]=field(n).checked;
 rule.enabled=editing?(current.rules.find(r=>r.id===editing)?.enabled??true):true;rule.expiresAt=field('validity').value==='until'?new Date(field('expiresAt').value).getTime()/1000:null;
 if(await commit({action:'save',id:editing,rule})){draft=false;$('#alarm-editor').close();toast('报警已保存到当前推送码');}
};
function openDevice(){if(!current)return;barkForm.reset();draft=false;$('#bark-form-error').textContent='';$('#bark-existing').hidden=!current.device;barkForm.elements.label.value=current.device?.label||'我的 iPhone';$('#bark-current').textContent=current.device?`当前设备：${current.device.label}。如需更换，请填写新设备地址后保存。`:'绑定到当前推送码。切换网页方案不会转移此设备。';$('#bark-editor').showModal();}
$('#bind-device').onclick=openDevice;barkForm.oninput=()=>{draft=true;};
barkForm.onsubmit=async e=>{e.preventDefault();if(await commit({action:'bind',key:barkForm.elements.key.value,label:barkForm.elements.label.value})){barkForm.elements.key.value='';draft=false;$('#bark-editor').close();toast('Bark 已绑定，可发送一条测试通知检查手机');}};
$('#test-bark').onclick=async()=>{if(await commit({action:'test'})){$('#bark-form-error').textContent='测试通知已加入发送队列，请查看报警记录及手机。';toast('已创建一条测试通知');}};
$('#unbind-bark').onclick=async()=>{if(confirm('解除当前 Bark 绑定？报警规则会保留，尚未发送的通知将取消。')&&await commit({action:'unbind'})){draft=false;$('#bark-editor').close();toast('已解除 Bark 绑定');}};
$('#master-enabled').onchange=async e=>{const enabled=e.target.checked;if(!await commit({action:'enabled',enabled}))e.target.checked=current?.enabled||false;else toast(enabled?'已恢复云端报警':'已暂停当前推送码的全部报警');};
$('#alarm-list').onclick=async e=>{const b=e.target.closest('[data-action]');if(!b||busy)return;const action=b.dataset.action;if(action==='new'){openRule();return;}const r=current?.rules.find(r=>r.id===b.dataset.id);if(!r)return;if(action==='edit'||action==='copy')openRule(r,action==='copy');else if(action==='toggle')await commit({action:'toggle',id:r.id,enabled:!r.enabled});else if(action==='delete'&&confirm('删除 '+r.symbol+' 的这条报警？已有触发记录将保留。'))await commit({action:'delete',id:r.id});};
for(const b of document.querySelectorAll('[data-close]'))b.onclick=()=>{if(busy)return;if(draft&&!confirm('放弃尚未保存的修改？'))return;draft=false;$('#'+b.dataset.close).close();};
for(const d of [$('#alarm-editor'),$('#bark-editor')])d.addEventListener('cancel',e=>{if(busy||(draft&&!confirm('放弃尚未保存的修改？')))e.preventDefault();else draft=false;});
$('#alarm-search').oninput=renderRules;$('#alarm-filter').onchange=renderRules;$('#refresh-alarms').onclick=()=>load();$('#empty-connect').onclick=()=>window.RadarAccount?.open();
document.addEventListener('radar-profile-changing',()=>{epoch++;catalogEpoch++;current=null;catalog=[];pending=null;draft=false;$('#pending-action').hidden=true;$('#alarm-editor').close();$('#bark-editor').close();barkForm.elements.key.value='';connected(false);$('#alarm-list').innerHTML='<div class="alarm-empty"><strong>正在载入当前推送码…</strong></div>';$('#event-list').innerHTML='<p class="alarm-empty-small">正在载入记录…</p>';});
document.addEventListener('radar-profile-ready',async e=>{$('#plan-label').textContent='当前推送码 · 尾号 '+e.detail.suffix;lastToken=token();await load();if(new URLSearchParams(location.search).get('binding')==='1'&&current){history.replaceState(null,'',location.pathname);openDevice();}});
window.addEventListener('beforeunload',e=>{if(draft||pending){e.preventDefault();e.returnValue='';}});
setInterval(()=>{if(document.visibilityState==='visible'&&token()&&!busy){if(token()!==lastToken){lastToken=token();epoch++;}load(false);}},5000);
if(token())load();
