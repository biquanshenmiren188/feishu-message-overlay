/* Saved exclusions only. One-click writes use fresh server settings, never whole drafts. */
(()=>{
const $=s=>document.querySelector(s),bridge=window.RadarCoinSettings,R=window.RadarRules;
const names={desktop:'电脑消息',cards:'行情卡片',mobile:'手机推送',mute:'电脑仅静音'},channels=['desktop','cards','mobile'];
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
let rows=[],operations=[],busy=false,attempt=null,epoch=0,managerRule=null;
const key=r=>r.coin+'|'+r.exchange;
const rules=(p,r)=>p.coins.filter(x=>x.coin===r.coin&&(x.exchange==='all'||x.exchange===r.exchange));
const covered=(p,r)=>rules(p,r).some(x=>x.enabled);
function render(){
 const overview=$('#tab-coins').getAttribute('aria-selected')==='true';$('.settings').classList.toggle('coin-overview',overview);bridge.syncUI();
 if(overview){$('h1').textContent='消息设置';$('#channel-hint').textContent='三端币种规则统一查看。点击上方渠道，可继续单独配置规则。';}
 const s=bridge.snapshot(),all=new Map();
 for(const c of [...channels,'mute'])if((c==='mobile'?s.mobileLoaded:s.desktopLoaded))for(const r of s.profiles[c].coins)all.set(key(r),{coin:r.coin,exchange:r.exchange});
 rows=[...all.values()].sort((a,b)=>a.coin.localeCompare(b.coin)||a.exchange.localeCompare(b.exchange));
 const query=$('#blocked-search').value.trim().toUpperCase(),visible=rows.filter(r=>r.coin.includes(query));$('#blocked-count').textContent=rows.length;
 $('#blocked-list').innerHTML=visible.length?visible.map(r=>{
  const index=rows.indexOf(r),done=s.desktopLoaded&&s.mobileLoaded&&channels.every(c=>covered(s.profiles[c],r));
  return `<article class="blocked-coin-row"><div class="blocked-identity"><b>${esc(r.coin)}</b><small>${esc(r.exchange==='all'?'全部交易所':R.name(r.exchange))}</small></div><div class="coin-channels">${channels.map(c=>{const loaded=c==='mobile'?s.mobileLoaded:s.desktopLoaded,on=loaded&&covered(s.profiles[c],r);return `<span class="coin-chip ${on?'is-blocked':''}">${names[c]} · ${!loaded?'未连接':on?'已屏蔽':rules(s.profiles[c],r).length?'已停用':'未设置'}</span>`;}).join('')}${s.desktopLoaded&&covered(s.profiles.mute,r)?'<span class="coin-chip is-muted">另有仅静音规则</span>':''}</div><div class="blocked-actions"><button class="text-button" data-block-all="${index}" ${done||busy||!s.desktopLoaded||!s.mobileLoaded?'disabled':''}>${done?'已屏蔽三端':'屏蔽三端'}</button><button data-manage-coin="${index}" ${busy?'disabled':''}>管理</button></div></article>`;
 }).join(''):`<div class="empty">${query?'没有匹配的币种':s.mobileLoaded?'暂无已保存的币种规则，可添加币种并屏蔽三端。':'请先连接推送码。'}</div>`;
 $('#editor-all').disabled=busy||!s.desktopLoaded||!s.mobileLoaded;$('#refresh-coins').disabled=busy;
}
function renderOperations(){
 $('#operation-count').textContent=operations.length;
 $('#coin-operations').innerHTML=operations.length?operations.map(x=>`<article class="history-record"><b>${esc(x.coins.join('、'))} · ${esc(x.exchange==='all'?'全部交易所':R.name(x.exchange))}</b><small class="operation-time">${esc(new Date(x.at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}))} UTC+8</small><p>${channels.map(c=>`${names[c]}：${x.results[c].state==='saved'?'已保存':x.results[c].state==='failed'?'保存失败':'等待处理'}`).join(' · ')}</p>${channels.some(c=>x.results[c].state!=='saved')?`<button data-retry-operation="${esc(x.id)}">重试未完成渠道</button>`:''}</article>`).join(''):'<div class="empty">暂无一键屏蔽操作记录。</div>';
}
async function refresh(){
 if(!window.RadarCoinAPI||busy)return;const generation=epoch;
 try{const data=await window.RadarCoinAPI.load();if(generation!==epoch)return;bridge.receive(data);operations=data.operations||[];renderOperations();$('#coin-sync-status').textContent='已同步云端 · 列表显示已保存规则';}
 catch(e){if(generation===epoch)$('#coin-sync-status').textContent=e.message;}
 render();
}
async function block(coins,exchange,requestId){
 if(busy)return;const generation=epoch;
 if(!requestId&&attempt&&attempt.exchange===exchange&&JSON.stringify(attempt.coins)===JSON.stringify(coins))requestId=attempt.requestId;
 attempt={coins,exchange,requestId:requestId||crypto.randomUUID()};const request={...attempt};
 busy=true;$('#coin-sync-status').textContent='正在保存三端规则…';$('.settings').inert=true;$('#editor-form').inert=true;render();
 try{
  const data=await window.RadarCoinAPI.block(request);if(generation!==epoch)return;
  bridge.receive(data);operations=data.operations;renderOperations();
  const failed=channels.filter(c=>data.operation.results[c].state!=='saved');
  $('#coin-operation-result').innerHTML=`<div class="operation-result ${failed.length?'has-error':''}"><b>${failed.length?'部分渠道未完成':'已屏蔽三端'}</b><p>${channels.map(c=>`${names[c]}：${data.operation.results[c].state==='saved'?'已保存':esc(data.operation.results[c].error||'未完成')}`).join(' · ')}</p>${failed.length?'<button id="retry-coin-block">重试未完成渠道</button>':''}</div>`;
  if(!failed.length){attempt=null;$('#editor').close();bridge.toast('三端规则已保存，小窗下次同步后生效');}else bridge.toast('部分渠道保存失败，请查看结果并重试');
  $('#coin-sync-status').textContent='已同步云端 · 其他未保存修改仍保留为草稿';
 }catch(e){$('#coin-operation-result').innerHTML=`<div class="operation-result has-error">${esc(e.message)}<p>结果尚未确认，重试会复用同一次操作，不重复添加。</p><button id="retry-coin-block">重试并核对结果</button></div>`;$('#editor-error').textContent=e.message;}
 finally{busy=false;$('.settings').inert=false;$('#editor-form').inert=false;render();}
}
function manage(rule){
 managerRule=rule;const s=bridge.snapshot();$('#coin-manager-title').textContent=rule.coin+' · '+(rule.exchange==='all'?'全部交易所':R.name(rule.exchange));
 $('#coin-manager-body').innerHTML=[...channels,'mute'].map(c=>{const loaded=c==='mobile'?s.mobileLoaded:s.desktopLoaded,entries=loaded?rules(s.profiles[c],rule):[];return `<div class="coin-manager-channel"><b>${names[c]}</b>${entries.length?entries.map(r=>`<div class="coin-manager-rule"><span>${esc(r.exchange==='all'?'全部交易所':R.name(r.exchange))} · ${r.enabled?'已启用':'已停用'}</span><button data-coin-edit="${c}" data-exchange="${esc(r.exchange)}">编辑</button><button data-coin-remove="${c}" data-exchange="${esc(r.exchange)}">删除</button></div>`).join(''):`<small>${loaded?'未设置此币种规则':'未连接此渠道'}</small>`}</div>`;}).join('');$('#coin-manager').showModal();
}
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.channel){$('#tab-block').click();return;}
 if(b.dataset.tab)render();
 if(b.id==='add-blocked-coin')bridge.add();
 if(b.id==='refresh-coins'||b.id==='refresh-history')refresh();
 if(b.dataset.blockAll!==undefined){const r=rows[Number(b.dataset.blockAll)];block([r.coin],r.exchange);}
 if(b.dataset.manageCoin!==undefined)manage(rows[Number(b.dataset.manageCoin)]);
 if(b.id==='coin-manager-close')$('#coin-manager').close();
 if(b.dataset.coinEdit||b.dataset.coinRemove){$('#coin-manager').close();bridge.manage(b.dataset.coinEdit||b.dataset.coinRemove,{coin:managerRule.coin,exchange:b.dataset.exchange},!!b.dataset.coinRemove);}
 if(b.id==='editor-all'){
  const coins=[...new Set($('#rule-coin').value.split(/[\s,，、;；]+/).filter(Boolean).map(R.coin))];
  if(!coins.length||coins.length>30||coins.some(c=>! /^[\p{L}\p{N}._-]{1,32}$/u.test(c))){$('#editor-error').textContent='请输入有效币种，每次最多30个';return;}
  block(coins,$('#rule-exchange').value);
 }
 if(b.id==='retry-coin-block'&&attempt)block(attempt.coins,attempt.exchange,attempt.requestId);
 if(b.dataset.retryOperation){const op=operations.find(x=>x.id===b.dataset.retryOperation);if(op)block(op.coins,op.exchange,op.id);}
});
$('#blocked-search').addEventListener('input',render);
document.addEventListener('radar-coins-changed',render);
document.addEventListener('radar-desktop-loaded',()=>{render();refresh();});
document.addEventListener('radar-mobile-loaded',()=>{epoch++;attempt=null;operations=[];$('#coin-operation-result').textContent='';renderOperations();render();if(bridge.snapshot().desktopLoaded)refresh();});
document.addEventListener('radar-desktop-error',()=>{epoch++;operations=[];renderOperations();render();});
render();
})();
