// Owner settings are stored on the server. Never store an integration key here.
const endpoint = '/radar/api/pushward';
const css = document.createElement('link');
css.rel = 'stylesheet'; css.href = new URL('./pushward-settings.css?v=20261016', import.meta.url);
document.head.append(css);
const trigger = document.createElement('button');
trigger.type = 'button'; trigger.className = 'push-settings-open'; trigger.textContent = '推送设置';
document.querySelector('.feed-tools')?.append(trigger);
const dialog = document.createElement('dialog');
dialog.id = 'push-settings'; dialog.setAttribute('aria-labelledby', 'push-settings-title');
dialog.innerHTML = `
<header class="ps-head"><div><h2 id="push-settings-title">手机推送设置</h2><p>保存到服务器，电脑和手机共用。</p></div><button type="button" data-close aria-label="关闭推送设置">关闭</button></header>
<div class="ps-content">
<p id="ps-feedback" role="status" aria-live="polite"></p>
<form id="ps-login" hidden>
  <label for="ps-password">管理口令</label>
  <input id="ps-password" type="password" autocomplete="current-password" required maxlength="128">
  <p class="ps-hint">首次设置时输入专用管理口令。不是 PushWard 集成密钥。</p>
  <button class="ps-primary" type="submit">解锁设置</button>
</form>
<form id="ps-form" hidden>
 <fieldset class="ps-section"><legend>锁屏列表</legend>
  <label for="ps-rows">显示条数</label><select id="ps-rows">${[1,2,3,4,5,6].map(n=>`<option value="${n}">${n} 条</option>`).join('')}</select>
  <p class="ps-hint">显示最近符合条件的消息，最新在下；不足时按实际条数显示。</p>
 </fieldset>
 <fieldset class="ps-section"><legend>屏蔽条件</legend>
  <p class="ps-hint">默认全部接收。下面勾选或填写的才会被屏蔽；未列出的等级也正常接收。</p>
  <fieldset class="ps-options"><legend>屏蔽等级（勾选即屏蔽）</legend>${['R0','R1','R2','R3','R4'].map(v=>`<label><input type="checkbox" name="excluded_ranks" value="${v}">${v}</label>`).join('')}</fieldset>
  <label for="ps-ranks">其他屏蔽等级</label><input id="ps-ranks" type="text" maxlength="2800" placeholder="例如 R5, R6, R1000+" autocapitalize="characters" autocomplete="off">
  <p class="ps-hint">无需逐个开启等级。多个屏蔽等级用逗号或空格分隔；R5 屏蔽 R5 和 R5+，单填 R5+ 只屏蔽原文中的 R5+。</p>
  <fieldset class="ps-options"><legend>屏蔽组合类型</legend>${['SF','FS','FF'].map(v=>`<label><input type="checkbox" name="excluded_modes" value="${v}">${v}</label>`).join('')}</fieldset>
  <label for="ps-min">最低百分比（%）</label><input id="ps-min" type="number" min="-100" max="100" step="any" inputmode="decimal" placeholder="不限">
  <p class="ps-hint">只比较标题中紧跟 R 等级的百分比。例如填 0.3，表示至少 +0.30%。留空不限。</p>
  <label for="ps-coins">屏蔽币种</label><input id="ps-coins" type="text" maxlength="1300" placeholder="不屏蔽，例如 BTC, ETH" autocapitalize="characters" autocomplete="off">
  <p class="ps-hint">多个币种用逗号或空格分隔，留空不屏蔽。</p>
  <fieldset class="ps-options"><legend>屏蔽交易所</legend>${['BINANCE','BITGET','BYBIT','OKX','GATE','ASTER','HL'].map(v=>`<label><input type="checkbox" name="excluded_exchanges" value="${v}">${v}</label>`).join('')}</fieldset>
  <p class="ps-hint">不选表示不屏蔽；买卖任意一端包含所选交易所，该消息就不推送。</p>
 </fieldset>
 <fieldset class="ps-section"><legend>新消息提醒</legend>
  <label class="ps-switch"><input id="ps-notify" type="checkbox">开启通知提醒</label>
  <label for="ps-interval">两次提醒至少间隔</label><select id="ps-interval"><option value="30">30 秒</option><option value="60">1 分钟</option><option value="180">3 分钟</option><option value="300">5 分钟</option><option value="600">10 分钟</option><option value="1800">30 分钟</option></select>
  <p class="ps-hint">间隔内的新消息合并提醒，没有新消息不提醒。关闭提醒后锁屏列表仍更新；修改筛选不会补发旧消息。</p>
 </fieldset>
 <p id="ps-health" class="ps-health"></p>
 <div class="ps-actions"><button type="button" data-close>取消</button><button id="ps-save" class="ps-primary" type="submit">保存设置</button></div>
 <button id="ps-logout" type="button" class="ps-logout">退出设置登录</button>
</form>
</div>`;
document.body.append(dialog);
const $ = id => dialog.querySelector('#'+id);
let revision, busy = false, pollTimer;
const feedback = (text, error=false) => { $('ps-feedback').textContent=text; $('ps-feedback').classList.toggle('ps-error', error); };
async function request(path, body) {
  const res = await fetch(endpoint+path, {method:body===undefined?'GET':'POST', credentials:'same-origin', cache:'no-store',
    headers:body===undefined?{}:{'Content-Type':'application/json'}, body:body===undefined?undefined:JSON.stringify(body), signal:AbortSignal.timeout(10000)});
  const data = await res.json().catch(()=>({error:'服务暂时不可用，请稍后重试'}));
  if (!res.ok) { const e=new Error(data.error||'请求失败'); e.status=res.status; throw e; }
  return data;
}
function health(data) {
  const s=data.status||{};
  if (!s.checkedAt || Date.now()/1000-s.checkedAt>90) return '推送服务状态暂未更新；设置保存在服务器。';
  if (s.settingsRevision!==data.revision) return '设置已保存，等待推送服务应用…';
  if (!s.sourceConnected) return '设置已生效；消息源暂时断线。';
  if (s.activityError) return '设置已生效；锁屏更新暂时受阻，稍后自动重试。';
  return `设置已生效 · 当前 ${s.rows??0} 条符合条件的消息`;
}
function fill(data) {
  revision=data.revision; const s=data.settings;
  $('ps-rows').value=s.rows; $('ps-min').value=s.min_percent??''; $('ps-coins').value=s.excluded_coins.join(', ');
  $('ps-ranks').value=s.excluded_ranks.filter(v=>!['R0','R1','R2','R3','R4'].includes(v)).join(', ');
  for (const key of ['excluded_ranks','excluded_modes','excluded_exchanges']) for (const node of dialog.querySelectorAll(`[name="${key}"]`)) node.checked=s[key].includes(node.value);
  $('ps-notify').checked=s.notify_enabled; $('ps-interval').value=s.notify_interval_seconds;
  $('ps-interval').disabled=!s.notify_enabled; $('ps-health').textContent=health(data);
  $('ps-form').hidden=false; $('ps-login').hidden=true;
}
function showLogin() { $('ps-form').hidden=true; $('ps-login').hidden=false; $('ps-password').focus(); }
function failure(e) { feedback(e.name==='TimeoutError'?'请求超时，请重新打开确认保存结果。':e.message||'网络异常，请稍后重试', true); if(e.status===401)showLogin(); }
async function load() { feedback('正在读取设置…'); try {fill(await request('/settings')); feedback('');} catch(e){ if(e.status===401){showLogin();feedback('请先解锁设置。');}else failure(e);} }
trigger.onclick=()=>{dialog.showModal();load();};
for(const button of dialog.querySelectorAll('[data-close]')) button.onclick=()=>dialog.close();
dialog.addEventListener('close',()=>{clearTimeout(pollTimer);$('ps-password').value='';trigger.focus();});
$('ps-notify').onchange=()=>{$('ps-interval').disabled=!$('ps-notify').checked;};
$('ps-login').onsubmit=async event=>{
  event.preventDefault(); if(busy)return; busy=true; const button=event.submitter; button.disabled=true; feedback('正在验证…');
  try {await request('/login',{password:$('ps-password').value});$('ps-password').value='';await load();}catch(e){failure(e);}finally{busy=false;button.disabled=false;}
};
async function confirmApplied(savedRevision, attempts=0) {
  if(!dialog.open)return;
  try { const data=await request('/settings'); $('ps-health').textContent=health(data);
    if(data.revision!==savedRevision){feedback('设置已在另一台设备更新，重新打开可读取最新设置。');return;}
    if(data.status?.settingsRevision===savedRevision){feedback('已保存并生效。');return;}
    if(attempts<8)pollTimer=setTimeout(()=>confirmApplied(savedRevision,attempts+1),2000);
  }catch(e){$('ps-health').textContent='设置已保存，暂时无法确认服务状态。';}
}
$('ps-form').onsubmit=async event=>{
  event.preventDefault(); if(busy)return;
  const checked=name=>[...dialog.querySelectorAll(`[name="${name}"]:checked`)].map(n=>n.value);
  const settings={rows:Number($('ps-rows').value),excluded_ranks:[...checked('excluded_ranks'),...$('ps-ranks').value.trim().toUpperCase().split(/[,，\s]+/).filter(Boolean)],excluded_modes:checked('excluded_modes'),excluded_exchanges:checked('excluded_exchanges'),
    min_percent:$('ps-min').value.trim()===''?null:Number($('ps-min').value),excluded_coins:$('ps-coins').value.trim().toUpperCase().split(/[,，\s]+/).filter(Boolean),
    notify_enabled:$('ps-notify').checked,notify_interval_seconds:Number($('ps-interval').value)};
  if(settings.excluded_ranks.length>100||settings.excluded_ranks.some(v=>! /^R\d{1,24}\+?$/.test(v))){feedback('屏蔽等级格式错误，例如 R5、R1000+；最多 100 个。',true);$('ps-ranks').focus();return;}
  if(settings.excluded_coins.length>50||settings.excluded_coins.some(v=>! /^[A-Z0-9][A-Z0-9._-]{0,23}$/.test(v))){feedback('请填有效币种代码，最多 50 个，用逗号或空格分隔。',true);$('ps-coins').focus();return;}
  busy=true; $('ps-save').disabled=true; feedback('正在保存…'); clearTimeout(pollTimer);
  try {const data=await request('/settings',{revision,settings});revision=data.revision;feedback('已保存，正在确认生效…');await confirmApplied(revision);}
  catch(e){failure(e);}finally{busy=false;$('ps-save').disabled=false;}
};
$('ps-logout').onclick=async()=>{try{await request('/logout',{});showLogin();feedback('已退出设置登录，推送继续按已保存的设置运行。');}catch(e){failure(e);}};
