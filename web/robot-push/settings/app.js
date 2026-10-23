(()=>{
const R=window.RadarRules,$=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)],key='radar-rules-independent-preview-v2';
let profiles={desktop:R.defaults(),cards:R.defaults(),mobile:R.defaults()},active='mobile',state=profiles.mobile,saved=false,edit=null,toastTimer,history=[],mobileLoaded=false,mobileHistory=[],mobileBusy=false;
try{const data=JSON.parse(localStorage.getItem(key));if(data&&data.version===2&&data.profiles&&['desktop','mobile'].every(c=>Array.isArray(data.profiles[c]?.coins)&&Array.isArray(data.profiles[c]?.legRules)&&Array.isArray(data.profiles[c]?.coinOI))){profiles=data.profiles;active='mobile';profiles.mobile=R.defaults();state=profiles[active];saved=true;}const h=JSON.parse(localStorage.getItem(key+'-history'));if(Array.isArray(h))history=h.slice(0,200);}catch{}
profiles.desktop=R.defaults();profiles.cards=R.defaults();state=profiles[active];
let desktopLoaded=false,desktopRevision=0,desktopHistory=[],desktopConnected=false,desktopError='正在连接电脑规则…';
let desktopAction='mute',desktopSets={mute:{...R.defaults(),desktopAction:'mute'},hide:{...R.defaults(),desktopAction:'hide'}},desktopSaved=JSON.parse(JSON.stringify(desktopSets));
let savedSnapshot=JSON.stringify(profiles);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const number=v=>v.trim()===''?null:Number(v);
const options=(all=false)=>`${all?'<option value="all">全部交易所</option>':''}${R.exchanges.map(e=>`<option value="${e[0]}">${e[1]}${e[2]?' · '+e[2]:''}</option>`).join('')}`;
const coinValid=c=>/^[\p{L}\p{N}._-]{1,32}$/u.test(c);
function toast(t){$('#toast').textContent=t;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,3000);}
const actionText=()=>active==='desktop'&&state.desktopAction==='mute'?'仅静音，消息仍接收并显示':'不推送';
function changed(){ $('#save-status').textContent='有未保存的更改';renderPhone(); }
function renderRules(kind,selector){const a=state[kind];const empty=kind==='coins'?'尚未屏蔽币种，所有币种都可接收':kind==='legRules'?'尚未添加定向屏蔽规则':'尚未添加特殊门槛';$(selector).innerHTML=a.length?a.map((r,i)=>{let title,sub;if(kind==='coins'){title=r.coin;sub=r.exchange==='all'?'全部交易所':R.name(r.exchange);}else if(kind==='legRules'){title=R.name(r.exchange);sub=`${R.sideName(r.side)} · ${R.marketName(r.market)}`;}else{title=`${r.coin} · ${R.name(r.exchange)}`;sub=r.value===null?'OI 不限制':`最低 OI ${r.value} 万 USDT`;}return `<div class="rule ${r.enabled?'':'rule-paused'}"><div class="rule-top"><div class="rule-text"><b>${esc(title)}</b><small>${esc(sub)}</small></div><label class="rule-enabled"><input type="checkbox" data-rule-toggle="${kind}" data-index="${i}" ${r.enabled?'checked':''}>启用</label></div><div class="rule-actions"><button data-edit="${kind}" data-index="${i}">编辑</button><button data-delete="${kind}" data-index="${i}">删除</button></div></div>`;}).join(''):`<div class="empty">${empty}</div>`;}
function renderLists(){renderRules('coins','#coin-list');renderRules('legRules','#leg-list');renderRules('coinOI','#oi-list');$('#coin-count').textContent=state.coins.length;$('#leg-count').textContent=state.legRules.length;$('#oi-count').textContent=state.coinOI.length;document.dispatchEvent(new Event('radar-coins-changed'));}
function renderExchanges(){
$('#exchange-grid').innerHTML=R.exchanges.map(e=>`<label class="exchange-choice"><input type="checkbox" data-block-ex="${e[0]}" ${state.blockedExchanges.includes(e[0])?'checked':''}><span>${e[1]} ${e[2]?'<small>'+e[2]+'</small>':''}</span></label>`).join('');
$('#oi-exchanges').innerHTML=R.exchanges.map(e=>{const rule=state.exchangeOI[e[0]]||{mode:'inherit',value:null};return `<div class="oi-row"><div><b>${e[1]}</b><small id="oi-label-${e[0]}"></small></div><select aria-label="${e[1]} OI 设置" data-oi-mode="${e[0]}"><option value="inherit" ${rule.mode==='inherit'?'selected':''}>跟随统一</option><option value="custom" ${rule.mode==='custom'?'selected':''}>单独设置</option><option value="none" ${rule.mode==='none'?'selected':''}>不限制</option></select><div class="oi-custom unit-input" id="oi-custom-${e[0]}" ${rule.mode==='custom'?'':'hidden'}><input type="number" min="0" step="any" inputmode="decimal" data-oi-value="${e[0]}" aria-label="${e[1]} 最低 OI" value="${rule.value??''}" placeholder="输入最低持仓金额"><span>万 USDT</span></div></div>`;}).join('');updateOILabels();}
function updateOILabels(){for(const e of R.exchanges){const r=state.exchangeOI[e[0]]||{mode:'inherit'};const n=r.mode==='none'?null:r.mode==='custom'?r.value:state.globalOI;$('#oi-label-'+e[0]).textContent=r.mode==='custom'&&n===null?'请填写门槛':n===null?'当前不限':`当前最低 ${n} 万 USDT`;}}
function initialize(){
$('#enabled').checked=state.enabled;$('#receive-label').textContent=state.enabled?'接收消息已开启':'接收消息已暂停';$('#global-oi').value=state.globalOI??'';$('#oi-conversion').textContent=state.globalOI===null?'留空不限制 OI':`相当于 ${(state.globalOI*10000).toLocaleString()} USDT`;$('#rows').value=state.rows;$('#interval').value=state.interval;$('#r-percent').value=state.rPercent??'';$('#r-ranks').value=state.ranks.join('、');$$('[name=missing]').forEach(x=>x.checked=x.value===state.missing);$('#mode-options').innerHTML=['SF','FS','FF'].map(m=>`<label><input type="checkbox" data-mode="${m}" ${state.modes.includes(m)?'checked':''}>${m}</label>`).join('');renderLists();renderExchanges();renderPhone();$('#save-status').textContent=JSON.stringify(state)!==JSON.stringify(active==='desktop'?desktopSaved[desktopAction]:JSON.parse(savedSnapshot)[active])?'有未保存的更改':active==='mobile'?(mobileLoaded?'已载入云端手机规则':'等待连接推送码'):(desktopLoaded?'已载入云端规则':desktopError);updateChannelUI();}
function openEditor(kind,index=null,preset=null){delete $('#editor').dataset.allChannels;$('#editor-confirm').hidden=false;edit={kind,index};const r=index===null?null:state[kind][index];$('#editor-title').textContent=(r?'编辑':'添加')+({coins:'币种屏蔽',legRules:'定向屏蔽',coinOI:'币种 OI 门槛'})[kind];$('#editor-error').textContent='';let fields='';if(kind!=='legRules')fields+=`<label class="stack-label">${kind==='coins'&&!r?'币种（可批量输入）':'币种'}<input id="rule-coin" placeholder="${kind==='coins'&&!r?'例如 MITO、PTB':'例如 MITO'}" value="${esc(r?.coin||'')}" autocomplete="off" required></label>`;fields+=`<label class="stack-label">交易所<select id="rule-exchange">${options(kind==='coins')}</select></label>`;
if(kind==='legRules')fields+='<div class="two-col"><label>腿的位置<select id="rule-side"><option value="all">任意一侧</option><option value="left">左腿（买入）</option><option value="right">右腿（卖出）</option></select></label><label>市场类型<select id="rule-market"><option value="all">现货和永续</option><option value="spot">仅现货</option><option value="perp">仅永续</option></select></label></div>';
if(kind==='coinOI')fields+='<label class="stack-label">最低 OI（万 USDT）<input id="rule-oi" type="number" min="0" step="any" inputmode="decimal" placeholder="例如 500"></label><label class="form-check"><input id="rule-no-limit" type="checkbox">此币种在该交易所不限制 OI</label>';
fields+='<div class="live-description" id="rule-description"></div>';$('#editor-fields').innerHTML=fields;$('#rule-exchange').value=r?.exchange||(kind==='coins'?'all':'gate');if(kind==='legRules'){$('#rule-side').value=r?.side||(preset==='left'||preset==='right'?preset:'all');$('#rule-market').value=r?.market||(preset==='spot'?'spot':'all');}if(kind==='coinOI'){$('#rule-oi').value=r?.value??'';$('#rule-no-limit').checked=!!r&&r.value===null;}$('#editor-all').hidden=kind!=='coins'||index!==null;$('#editor-confirm').textContent=kind==='coins'&&index===null?'仅添加到当前渠道':'确定';describeRule();$('#editor').showModal();}
function describeRule(){const e=$('#rule-exchange').value;if(edit.kind==='legRules')$('#rule-description').textContent=`只屏蔽 ${R.name(e)} 的${R.sideName($('#rule-side').value)}、${R.marketName($('#rule-market').value)}；命中后${actionText()}。`;else if(edit.kind==='coins')$('#rule-description').textContent=`该币种${e==='all'?'在全部交易所':'在 '+R.name(e)}出现时，命中后${$('#editor').dataset.allChannels?'隐藏电脑消息和行情卡片，并停止当前手机方案推送':actionText()}。`;else{$('#rule-oi').disabled=$('#rule-no-limit').checked;$('#rule-description').textContent='此规则优先于交易所和统一 OI 门槛；仅检查对应永续腿。';}}
function validate(){const errors=[];if(state.globalOI!==null&&(!Number.isFinite(state.globalOI)||state.globalOI<0))errors.push('统一 OI 门槛必须是非负数');for(const [e,r] of Object.entries(state.exchangeOI))if(r.mode==='custom'&&(r.value===null||!Number.isFinite(r.value)||r.value<0))errors.push(R.name(e)+' 请填写有效 OI 门槛');if(state.rPercent!==null&&!Number.isFinite(state.rPercent))errors.push('请填写有效 R 百分比');if(state.ranks.some(r=>!/^R\d+\+?$/.test(r)))errors.push('屏蔽等级请使用 R0、R5+ 等格式');return errors;}
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.channel){active=b.dataset.channel;state=profiles[active];initialize();}if(b.dataset.tab){$$('.tabs [data-tab]').forEach(x=>x.setAttribute('aria-selected',x===b));$$('#panel-coins,[role=tabpanel]').forEach(p=>p.hidden=p.id!=='panel-'+b.dataset.tab);updateChannelUI();}if(b.id==='add-coin')openEditor('coins');if(b.id==='add-oi')openEditor('coinOI');if(b.dataset.preset)openEditor('legRules',null,b.dataset.preset);if(b.dataset.edit)openEditor(b.dataset.edit,Number(b.dataset.index));if(b.dataset.delete){state[b.dataset.delete].splice(Number(b.dataset.index),1);renderLists();changed();toast('已移除规则，保存后保留此更改');}if(b.id==='editor-close'||b.id==='editor-cancel')$('#editor').close();});
$('#editor-fields').addEventListener('input',describeRule);
$('#editor-form').addEventListener('submit',e=>{e.preventDefault();if($('#editor').dataset.allChannels){$('#editor-all').click();return;}const kind=edit.kind,exchange=$('#rule-exchange').value;const enabled=edit.index===null?true:state[kind][edit.index].enabled;let added=[];if(kind==='coins'){const coins=[...new Set($('#rule-coin').value.split(/[\s,，、;；]+/).filter(Boolean).map(R.coin))];if(!coins.length||coins.some(c=>!coinValid(c))){$('#editor-error').textContent='请输入有效币种，多个币种用逗号或空格分隔';return;}if(edit.index!==null&&coins.length!==1){$('#editor-error').textContent='编辑时请保留一个币种';return;}added=coins.map(c=>({coin:c,exchange,enabled}));}else if(kind==='legRules')added=[{exchange,side:$('#rule-side').value,market:$('#rule-market').value,enabled}];else{const c=R.coin($('#rule-coin').value),value=$('#rule-no-limit').checked?null:number($('#rule-oi').value);if(!coinValid(c)||(!$('#rule-no-limit').checked&&(value===null||!Number.isFinite(value)||value<0))){$('#editor-error').textContent='请填写有效币种和非负 OI 门槛';return;}added=[{coin:c,exchange,value,enabled}];}
const duplicate=(a,b)=>a.exchange===b.exchange&&(kind==='legRules'?a.side===b.side&&a.market===b.market:a.coin===b.coin);if(added.some(a=>state[kind].some((b,i)=>i!==edit.index&&duplicate(a,b)))){$('#editor-error').textContent='已存在相同范围的规则，请编辑已有规则';return;}if(edit.index===null)state[kind].push(...added);else state[kind].splice(edit.index,1,...added);renderLists();changed();$('#editor').close();});
document.addEventListener('change',e=>{const t=e.target;if(t.dataset.blockEx){state.blockedExchanges=$$('[data-block-ex]:checked').map(x=>x.dataset.blockEx);changed();}if(t.dataset.ruleToggle){state[t.dataset.ruleToggle][Number(t.dataset.index)].enabled=t.checked;renderLists();changed();}if(t.dataset.oiMode){const id=t.dataset.oiMode;state.exchangeOI[id]={mode:t.value,value:number($(`[data-oi-value="${id}"]`).value)};$('#oi-custom-'+id).hidden=t.value!=='custom';updateOILabels();changed();}if(t.dataset.mode){state.modes=$$('[data-mode]:checked').map(x=>x.dataset.mode);changed();}if(t.name==='desktop-action'){desktopAction=t.value;profiles.desktop=desktopSets[desktopAction];state=profiles.desktop;initialize();}if(t.name==='missing'){state.missing=t.value;changed();}if(t.id==='enabled'){state.enabled=t.checked;if(active==='desktop')for(const draft of Object.values(desktopSets))draft.enabled=t.checked;$('#receive-label').textContent=t.checked?'接收消息已开启':'接收消息已暂停';changed();}if(t.id==='rows'||t.id==='interval'){state[t.id]=Number(t.value);changed();}});
document.addEventListener('input',e=>{const t=e.target;if(t.id==='global-oi'){state.globalOI=number(t.value);$('#oi-conversion').textContent=state.globalOI===null?'留空不限制 OI':`相当于 ${(state.globalOI*10000).toLocaleString()} USDT`;updateOILabels();changed();}if(t.dataset.oiValue){const id=t.dataset.oiValue;state.exchangeOI[id]={mode:'custom',value:number(t.value)};updateOILabels();changed();}if(t.id==='r-percent'){state.rPercent=number(t.value);changed();}if(t.id==='r-ranks'){state.ranks=t.value.split(/[\s,，、;；]+/).filter(Boolean).map(x=>x.toUpperCase().replace(/^R0+(?=\d)/,'R'));changed();}});
$('#save').addEventListener('click',async()=>{
 const errors=validate();if(errors.length){toast(errors[0]);return;}
 if(active==='mobile'){
  if(!mobileLoaded||mobileBusy){toast('请先连接推送码并载入设置');return;}
  mobileBusy=true;$('.settings').inert=true;$('#save').disabled=true;
  try{await window.RadarMobileSettings.save(toServer(state));$('#save-status').textContent='手机规则已保存到云端';toast('已保存，后续新消息按手机规则推送');}
  catch(e){$('#save-status').textContent='保存失败，草稿已保留';toast(e.message);}
  finally{mobileBusy=false;$('.settings').inert=false;updateChannelUI();}return;
 }
 if(!desktopLoaded||mobileBusy){toast(desktopError);return;}
 mobileBusy=true;$('.settings').inert=true;$('#save').disabled=true;
 try{const channel=active;const result=await window.RadarDesktopSettings.save({revision:desktopRevision,channel,settings:toServer(state),action:channel==='cards'?'hide':state.desktopAction});applyDesktop(result,channel,desktopAction);toast('已保存，小窗下次同步后生效');}
 catch(e){$('#save-status').textContent='保存失败，草稿已保留';toast(e.message);}
 finally{mobileBusy=false;$('.settings').inert=false;updateChannelUI();}

});
const exchangeOut=e=>e==='hyperliquid'?'HL':e.toUpperCase();
const exchangeIn=e=>e==='HL'?'hyperliquid':e.toLowerCase();
function toServer(s){return {notify_enabled:s.enabled,rows:s.rows,notify_interval_seconds:s.interval,min_percent:s.rPercent,excluded_ranks:s.ranks,excluded_coins:[],excluded_modes:s.modes,excluded_exchanges:s.blockedExchanges.map(exchangeOut),advanced:{coins:s.coins,legRules:s.legRules,globalOI:s.globalOI,exchangeOI:s.exchangeOI,coinOI:s.coinOI,missing:s.missing}};}
function fromServer(s){const a=s.advanced||{};return {...R.defaults(),...a,enabled:s.notify_enabled,rows:s.rows,interval:s.notify_interval_seconds,rPercent:s.min_percent,ranks:s.excluded_ranks,modes:s.excluded_modes,blockedExchanges:s.excluded_exchanges.map(exchangeIn),coins:[...s.excluded_coins.map(coin=>({coin,exchange:'all',enabled:true})),...(a.coins||[])]};}
document.addEventListener('radar-mobile-loaded',e=>{profiles.mobile=fromServer(e.detail.settings);mobileHistory=e.detail.blockedHistory||[];mobileLoaded=true;const snap=JSON.parse(savedSnapshot);snap.mobile=JSON.parse(JSON.stringify(profiles.mobile));savedSnapshot=JSON.stringify(snap);state=profiles[active];initialize();$('#mobile-status').textContent=e.detail.subscribed?'已连接云端 · 订阅已连接':'已连接云端 · 待开启通知';if(active==='mobile')$('#save-status').textContent='已载入云端手机规则';});

function applyDesktop(data,channel=null,action=null){
 desktopLoaded=true;desktopRevision=data.revision;desktopHistory=data.history||[];desktopConnected=data.connected;
 const snapshot=JSON.parse(savedSnapshot);
 for(const c of channel?[channel]:['desktop','cards']){
  if(c==='desktop'){
   if(!action)desktopAction=data.desktop.action||'mute';
   for(const a of action?[action]:['mute','hide']){const settings=data.desktop.rules?.[a]||(data.desktop.action===a?data.desktop.settings:toServer(R.defaults()));desktopSets[a]={...fromServer(settings),desktopAction:a};desktopSaved[a]=JSON.parse(JSON.stringify(desktopSets[a]));}
   for(const a of ['mute','hide']){desktopSets[a].enabled=data.desktop.settings.notify_enabled;desktopSaved[a].enabled=data.desktop.settings.notify_enabled;}
   profiles.desktop=desktopSets[desktopAction];
  }else profiles[c]={...fromServer(data[c].settings),desktopAction:data[c].action};
  snapshot[c]=JSON.parse(JSON.stringify(profiles[c]));
 }
 savedSnapshot=JSON.stringify(snapshot);state=profiles[active];initialize();
}
document.addEventListener('radar-desktop-loaded',e=>applyDesktop(e.detail));
document.addEventListener('radar-desktop-error',e=>{desktopLoaded=false;desktopError=e.detail;updateChannelUI();});
function updateChannelUI(){
 const mobile=active==='mobile',label=mobile?'手机推送':active==='cards'?'行情卡片':'电脑消息';
 const overview=!$('#panel-coins').hidden;$('.settings').classList.toggle('coin-overview',overview);$('#tab-coins').setAttribute('aria-pressed',overview);$('h1').textContent=overview?'已屏蔽币种':label+'设置';$('.title-row p').textContent=overview?'统一查看三端规则，按币种与交易所范围管理。':'屏蔽币种 / '+label+' · 独立保存';$('#tab-other').textContent=mobile?'推送与预览':'其他设置';$('#refresh-history').hidden=false;$('#refresh-history').disabled=mobile?!mobileLoaded:!desktopLoaded;
 $$('[data-channel]').forEach(b=>b.setAttribute('aria-pressed',!overview&&b.dataset.channel===active));
 $('#channel-hint').textContent=overview?'选择下方币种可一键屏蔽三端；单独设置请进入上方子菜单。':mobile?(mobileLoaded?'正在编辑云端手机规则，保存后生效。':'请连接推送码载入规则。'):desktopLoaded?(active==='cards'?'只控制左侧行情卡片，不改变右侧消息和手机推送。':'静音与屏蔽消息分别配置、同时生效；同时命中时优先屏蔽消息。'):desktopError;
 $('#mobile-cadence').hidden=!mobile;$('#mobile-account').hidden=false;$('#desktop-action').hidden=active!=='desktop';
 $$('[name=desktop-action]').forEach(x=>x.checked=x.value===desktopAction);$('#desktop-editing').textContent=desktopAction==='mute'?'正在编辑：仅屏蔽声音。下方币种、交易所、左右腿、OI 和等级条件只用于静音，消息照常显示。':'正在编辑：屏蔽消息。下方条件命中后不显示消息，也不响铃。';
 $('#save').disabled=mobileBusy||(mobile?!mobileLoaded:!desktopLoaded);$('#save-help').textContent=mobile?'保存到当前推送码':'保存到云端 · 约 3 秒同步';
 $('#history-note').textContent=mobile?'最近 200 条云端手机屏蔽记录。':'仅记录真实桌面请求中的命中，标明静音或隐藏；重复同步不重复记。电脑两类记录合计保留最近 200 条。';
 $('#save').textContent=active==='desktop'?'保存'+(desktopAction==='mute'?'仅静音':'屏蔽消息')+'规则':'保存'+label+'规则';$('#history-caption').textContent=label+'被屏蔽的原因、时间和处理方式。';
 $('#desktop-status').textContent=desktopLoaded?(desktopConnected?'小窗在线 · 规则已接入':'等待小窗连接'):'等待原始管理码连接';renderHistory();
}
function renderPhone(){
  const mobile=profiles.mobile;
  const items=[{coin:'MITO',left:{exchange:'gate',market:'perp',oi:120},right:{exchange:'binance',market:'perp',oi:320},rank:'R1',percent:.6,time:'20:45:08'}, {coin:'BTC',left:{exchange:'binance',market:'spot',oi:null},right:{exchange:'okx',market:'perp',oi:18000},rank:'R2',percent:1.12,time:'20:44:51'}, {coin:'ETH',left:{exchange:'bybit',market:'perp',oi:6500},right:{exchange:'bitget',market:'perp',oi:5400},rank:'R1',percent:.72,time:'20:44:36'}, {coin:'SOL',left:{exchange:'gate',market:'perp',oi:1800},right:{exchange:'aster',market:'spot',oi:null},rank:'R0',percent:.35,time:'20:44:10'}];
  const valid=items.filter(x=>coinValid(R.coin(x.coin))&&/^R\d+\+?$/i.test(x.rank)&&x.percent!==null&&Number.isFinite(x.percent));
  const allowed=valid.filter(x=>R.evaluate(mobile,x).allowed).slice(0,mobile.rows);
  const abbreviations={binance:'BN',okx:'OK',bybit:'BY',bitget:'BG',gate:'GT',aster:'AS',hyperliquid:'HY'};
  $('#phone-notification').innerHTML=allowed.length?'<div class="notification-head"><span class="notification-icon">雷</span><b>雷达</b><span>现在</span></div>'+allowed.map(x=>{const mode=R.evaluate(mobile,x).mode;return '<div class="notification-line">'+esc(x.time.slice(0,5)+' '+(x.percent>=0?'+':'')+x.percent.toFixed(2)+'% '+x.rank.toUpperCase()+' '+mode+' '+abbreviations[x.left.exchange]+'→'+abbreviations[x.right.exchange]+' '+x.coin)+'</div>';}).join(''):'<div class="notification-empty">'+(!mobile.enabled?'手机接收消息已关闭':'没有符合手机规则的样例')+'<small>本轮不产生通知</small></div>';
  $('#phone-preview-meta').textContent='最多 '+mobile.rows+' 条 · '+(mobile.interval<60?mobile.interval+' 秒':mobile.interval/60+' 分钟')+'合并一次 · 当前 '+allowed.length+' 条通过 · 当前草稿';
}
function renderHistory(){
 const records=active==='mobile'?mobileHistory:desktopHistory.filter(x=>x.channel===active);
 $('#history-count').textContent=records.length;
 $('#history-list').innerHTML=records.length?records.map(x=>'<article class="history-record"><div class="history-top"><b>'+esc(x.coin)+' · '+esc(x.mode)+'</b><span>'+esc(x.action==='mute'?'仅静音 · 消息照常显示':x.action==='hide'?'已隐藏':'未推送')+'</span></div><small>'+esc(new Date(x.at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}))+' UTC+8 · 规则版本 '+esc(x.revision)+'</small><p>'+esc(x.buy+' → '+x.sell+' · '+x.rank+' '+x.value)+'</p><ul>'+x.reasons.map(r=>'<li>'+esc(r)+'</li>').join('')+'</ul></article>').join(''):'<div class="empty">暂无屏蔽记录，后续命中将在这里显示。</div>';
}
$('#refresh-history').addEventListener('click',async()=>{const b=$('#refresh-history');b.disabled=true;try{if(active==='mobile')mobileHistory=await window.RadarMobileSettings.history();else{const result=await window.RadarDesktopSettings.status();desktopHistory=result.history||[];desktopConnected=result.connected;}renderHistory();}catch(e){toast(e.message);}finally{b.disabled=false;}});

const clone=x=>JSON.parse(JSON.stringify(x));
function mergeDraft(draft,old,next){
 const result=clone(next);
 for(const k of Object.keys(draft))if(JSON.stringify(draft[k])!==JSON.stringify(old[k]))result[k]=clone(draft[k]);
 const id=r=>r.coin+'|'+r.exchange,base=new Map(old.coins.map(r=>[id(r),r])),local=new Map(draft.coins.map(r=>[id(r),r])),merged=new Map(next.coins.map(r=>[id(r),clone(r)]));
 for(const [k,r] of base)if(!local.has(k))merged.delete(k);else if(JSON.stringify(local.get(k))!==JSON.stringify(r))merged.set(k,clone(local.get(k)));
 for(const [k,r] of local)if(!base.has(k))merged.set(k,clone(r));
 result.coins=[...merged.values()];return result;
}
window.RadarCoinSettings={
 syncUI:updateChannelUI,
 snapshot:()=>({profiles:{desktop:clone(desktopSaved.hide),mute:clone(desktopSaved.mute),cards:JSON.parse(savedSnapshot).cards,mobile:JSON.parse(savedSnapshot).mobile},desktopLoaded,mobileLoaded}),
 receive(data){
  const snap=JSON.parse(savedSnapshot);
  for(const action of ['mute','hide']){const next={...fromServer(data.desktop.desktop.rules[action]),desktopAction:action};desktopSets[action]=mergeDraft(desktopSets[action],desktopSaved[action],next);desktopSaved[action]=clone(next);}
  for(const channel of ['cards','mobile']){const next={...fromServer(channel==='cards'?data.desktop.cards.settings:data.mobile.settings),...(channel==='cards'?{desktopAction:'hide'}:{})};profiles[channel]=mergeDraft(profiles[channel],snap[channel],next);snap[channel]=clone(next);}
  // The explicit operation wins only for its successful target coins; all other drafts stay intact.
  if(data.operation&&data.operation.kind!=='edit')for(const channel of ['desktop','cards','mobile'])if(data.operation.results[channel].state==='saved'){
   const target=channel==='desktop'?desktopSets.hide:profiles[channel];
   for(const coin of data.operation.coins){const rule=target.coins.find(r=>r.coin===coin&&r.exchange===data.operation.exchange);if(rule)rule.enabled=true;else if(!target.coins.some(r=>r.enabled&&r.coin===coin&&r.exchange==='all'))target.coins.push({coin,exchange:data.operation.exchange,enabled:true});}
  }
  if(data.operation?.kind==='edit')for(const change of data.operation.changes)if(data.operation.results[change.channel].state==='saved'){
   const c=change.channel,draft=c==='desktop'?desktopSets.hide:c==='mute'?desktopSets.mute:profiles[c],latest=c==='desktop'?desktopSaved.hide:c==='mute'?desktopSaved.mute:snap[c];
   draft.coins=draft.coins.filter(r=>r.coin!==change.coin||r.exchange!==change.exchange);
   draft.coins.push(...clone(latest.coins.filter(r=>r.coin===change.coin&&r.exchange===change.exchange)));
  }
  profiles.desktop=desktopSets[desktopAction];snap.desktop=clone(desktopSaved[desktopAction]);savedSnapshot=JSON.stringify(snap);desktopRevision=data.desktop.revision;desktopHistory=data.desktop.history||[];desktopConnected=data.desktop.connected;desktopLoaded=true;state=profiles[active];window.RadarCoinAPI.adopt(data.mobile);initialize();
 },
 manage(channel,rule,remove=false){
  active=channel==='mute'?'desktop':channel;if(active==='desktop'){desktopAction=channel==='mute'?'mute':'hide';profiles.desktop=desktopSets[desktopAction];}state=profiles[active];initialize();$('#tab-block').click();
  const index=state.coins.findIndex(r=>r.coin===rule.coin&&r.exchange===rule.exchange);
  if(index<0){toast('这条规则在当前草稿中已移除，请保存或刷新后再操作');return;}
  if(remove){state.coins.splice(index,1);renderLists();changed();toast('已移除当前渠道规则，请点击底部保存');}else openEditor('coins',index);
 },
 add:()=>openEditor('coins'),toast
};
initialize();
})();
