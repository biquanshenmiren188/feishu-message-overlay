/* Saved exclusions only. One-click writes use fresh server settings, never whole drafts. */
(()=>{
const $=s=>document.querySelector(s),bridge=window.RadarCoinSettings,R=window.RadarRules;
const names={desktop:'电脑消息',cards:'行情卡片',mobile:'手机推送',mute:'仅静音'},channels=['desktop','cards','mobile'];
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
let rows=[],visibleRows=[],operations=[],busy=false,batchBusy=false,attempt=null,epoch=0;
const selected=new Set();
const key=r=>r.coin+'|'+r.exchange;
const stateName=(channel,value)=>value===true?(channel==='mute'?'仅静音':'屏蔽'):'正常推送';
const historyChange=c=>['desktop','mute'].includes(c.channel)?(c.after===true?'设置':c.after===null?'移除':'取消')+(c.channel==='desktop'?'电脑屏蔽规则':'仅静音规则'):names[c.channel]+'：'+stateName(c.channel,c.before)+' → '+stateName(c.channel,c.after)+(c.after===null?'（删除本范围规则）':'');
const rules=(p,r)=>p.coins.filter(x=>x.coin===r.coin&&(x.exchange==='all'||x.exchange===r.exchange));
const covered=(p,r)=>rules(p,r).some(x=>x.enabled);
function render(){
 bridge.syncUI();
 const s=bridge.snapshot(),all=new Map();
 for(const c of [...channels,'mute'])if((c==='mobile'?s.mobileLoaded:s.desktopLoaded))for(const r of s.profiles[c].coins)all.set(key(r),{coin:r.coin,exchange:r.exchange});
 rows=[...all.values()].sort((a,b)=>a.coin.localeCompare(b.coin)||a.exchange.localeCompare(b.exchange));
 const query=$('#blocked-search').value.trim().toUpperCase(),filter=$('#blocked-filter').value;
 for(const k of selected)if(!rows.some(r=>key(r)===k))selected.delete(k);
 const visible=visibleRows=rows.filter(r=>{const count=channels.filter(c=>(c==='mobile'?s.mobileLoaded:s.desktopLoaded)&&covered(s.profiles[c],r)).length;return (!query||r.coin.toUpperCase()===query)&&(filter==='all'||filter==='all-blocked'&&count===3||filter==='partial'&&count>0&&count<3||filter==='mute'&&s.desktopLoaded&&covered(s.profiles.mute,r)&&!covered(s.profiles.desktop,r));});$('#blocked-count').textContent=rows.length;
 $('#selected-count').textContent='已选 '+selected.size+' 项';$('.batch-tools').hidden=!selected.size;$('#coin-plan-label').textContent='三端方案：'+(window.RadarCoinAPI?.planLabel()||'正在连接');for(const id of ['batch-mute','batch-pause','batch-delete'])$('#'+id).disabled=!selected.size||busy||!s.desktopLoaded||!s.mobileLoaded;$('#batch-block').disabled=!selected.size||busy||batchBusy||!s.desktopLoaded||!s.mobileLoaded;$('#clear-selected').hidden=!selected.size;
 const chosen=visible.filter(r=>selected.has(key(r))).length;$('#select-visible').checked=!!visible.length&&chosen===visible.length;$('#select-visible').indeterminate=chosen>0&&chosen<visible.length;$('#select-visible').disabled=!visible.length||busy||batchBusy;
 $('#blocked-list').innerHTML=visible.length?visible.map(r=>{
  const index=rows.indexOf(r),done=s.desktopLoaded&&s.mobileLoaded&&channels.every(c=>covered(s.profiles[c],r));
  return `<article class="blocked-coin-row"><label class="coin-select"><input type="checkbox" data-select-coin="${index}" aria-label="选择 ${esc(r.coin)} ${esc(r.exchange==='all'?'全部交易所':R.name(r.exchange))}" ${selected.has(key(r))?'checked':''} ${busy||batchBusy?'disabled':''}></label><div class="blocked-identity"><b>${esc(r.coin)}</b><small>${esc(r.exchange==='all'?'全部交易所':R.name(r.exchange))}</small></div><div class="coin-channels">${channels.map(c=>{const loaded=c==='mobile'?s.mobileLoaded:s.desktopLoaded,on=loaded&&covered(s.profiles[c],r);return `<span class="coin-chip ${on?'is-blocked':''}">${names[c]} · ${!loaded?'未连接':on?'屏蔽':c==='desktop'&&covered(s.profiles.mute,r)?'仅静音':'正常推送'}</span>`;}).join('')}${s.desktopLoaded&&covered(s.profiles.desktop,r)&&covered(s.profiles.mute,r)?'<span class="coin-chip is-muted">另有仅静音规则（屏蔽优先）</span>':''}</div><div class="blocked-actions"><button data-manage-coin="${index}" ${busy?'disabled':''}>管理</button><button class="danger-text" data-remove-coin="${index}" ${busy||!s.desktopLoaded||!s.mobileLoaded?'disabled':''}>删除</button></div></article>`;
 }).join(''):`<div class="empty">${query||filter!=='all'?'没有匹配的币种':s.mobileLoaded?'暂无已保存的币种规则，可添加币种并屏蔽三端。':'请先连接推送码。'}</div>`;
 $('#editor-all').disabled=busy||!s.desktopLoaded||!s.mobileLoaded;$('#refresh-coins').disabled=busy;
}
function renderOperations(){
 $('#operation-count').textContent=operations.length;
 $('#coin-operations').innerHTML=operations.length?operations.map((x,i)=>{
  const edited=x.kind==='edit',entries=Object.entries(x.results).filter(([,r])=>r.state!=='skipped'),failed=entries.some(([,r])=>r.state!=='saved'),canUndo=edited&&x.changes.some(c=>c.after===null&&x.results[c.channel].state==='saved')&&!operations.some(o=>o.undoOf===x.id);
  return `<article class="history-record"><b>${esc(x.coins.join('、'))} · ${edited?(x.undoOf?'撤销删除':'规则修改'):esc(x.exchange==='all'?'全部交易所':R.name(x.exchange))}</b><small class="operation-time">${esc(new Date(x.at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}))} UTC+8</small><p>${entries.map(([c,r])=>`${names[c]}：${r.state==='saved'?(edited?'已保存本范围修改':'屏蔽（已保存）'):esc(r.error||'等待处理')}`).join(' · ')}</p>${edited?`<details><summary>查看 ${x.changes.length} 项变更</summary><ul>${x.changes.map(c=>`<li>${esc(c.coin)} / ${esc(c.exchange==='all'?'全部交易所':R.name(c.exchange))} / ${esc(historyChange(c))} · ${x.results[c.channel].state==='saved'?'已保存':esc(x.results[c.channel].error||'未完成')}</li>`).join('')}</ul></details>`:''}<div class="history-actions">${failed?`<button data-retry-operation="${esc(x.id)}">重试未完成渠道</button>`:''}${canUndo?`<button data-undo-operation="${i}">撤销本次删除</button>`:''}</div></article>`;
 }).join(''):'<div class="empty">暂无规则操作记录。</div>';
}
async function refresh(){
 if(!window.RadarCoinAPI||busy||batchBusy)return;const generation=epoch;
 try{const data=await window.RadarCoinAPI.load();if(generation!==epoch)return;bridge.receive(data);operations=data.operations||[];renderOperations();$('#coin-sync-status').textContent='已同步云端 · 列表为本币种所选范围的已保存状态，其他筛选仍按原设置';}
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
  $('#coin-operation-result').innerHTML=`<div class="operation-result ${failed.length?'has-error':''}"><b>${failed.length?'部分渠道未完成':'已屏蔽三端'}</b><p>${channels.map(c=>`${names[c]}：${data.operation.results[c].state==='saved'?'屏蔽（已保存）':esc(data.operation.results[c].error||'未完成')}`).join(' · ')}</p>${failed.length?'<button id="retry-coin-block">重试未完成渠道</button>':''}</div>`;
  if(!failed.length){for(const coin of coins)selected.delete(key({coin,exchange}));attempt=null;$('#editor').close();bridge.toast('三端规则已保存，小窗下次同步后生效');}else bridge.toast('部分渠道保存失败，请查看结果并重试');
  $('#coin-sync-status').textContent='已同步云端 · 其他未保存修改仍保留为草稿';return !failed.length;
 }catch(e){if(generation!==epoch)return;$('#coin-operation-result').innerHTML=`<div class="operation-result has-error">${esc(e.message)}<p>结果尚未确认，重试会复用同一次操作，不重复添加。</p><button id="retry-coin-block">重试并核对结果</button></div>`;$('#editor-error').textContent=e.message;}
 finally{busy=false;$('.settings').inert=batchBusy;$('#editor-form').inert=batchBusy;render();}
}
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.channel){$('#tab-block').click();return;}
 if(b.dataset.tab)render();
 if(b.id==='add-blocked-coin')window.RadarCoinCenter.matrix('');
 if(['batch-block','batch-mute','batch-pause','batch-delete'].includes(b.id))window.RadarCoinCenter.batch(rows.filter(r=>selected.has(key(r))),b.id.slice(6));
 if(b.id==='clear-selected'){selected.clear();render();}
 if(b.id==='refresh-coins'||b.id==='refresh-history')refresh();
 if(b.dataset.blockAll!==undefined){const r=rows[Number(b.dataset.blockAll)];block([r.coin],r.exchange);}
 if(b.dataset.manageCoin!==undefined)window.RadarCoinCenter.matrix(rows[Number(b.dataset.manageCoin)].coin);
 if(b.dataset.removeCoin!==undefined)window.RadarCoinCenter.batch([rows[Number(b.dataset.removeCoin)]],'delete');
 if(b.dataset.undoOperation!==undefined)window.RadarCoinCenter.undo(operations[Number(b.dataset.undoOperation)]);

 if(b.id==='editor-all'){
  const coins=[...new Set($('#rule-coin').value.split(/[\s,，、;；]+/).filter(Boolean).map(R.coin))];
  if(!coins.length||coins.length>30||coins.some(c=>! /^[\p{L}\p{N}._-]{1,32}$/u.test(c))){$('#editor-error').textContent='请输入有效币种，每次最多30个';return;}
  block(coins,$('#rule-exchange').value);
 }
 if(b.id==='retry-coin-block'&&attempt)block(attempt.coins,attempt.exchange,attempt.requestId);
 if(b.dataset.retryOperation){const op=operations.find(x=>x.id===b.dataset.retryOperation);if(op?.kind==='edit')window.RadarCoinCenter.retryOperation(op);else if(op)block(op.coins,op.exchange,op.id);}
});
$('#blocked-search').addEventListener('input',render);
$('#blocked-filter').addEventListener('change',render);
$('#select-visible').addEventListener('change',e=>{for(const r of visibleRows)if(e.target.checked)selected.add(key(r));else selected.delete(key(r));render();});
$('#blocked-list').addEventListener('change',e=>{const i=e.target.dataset.selectCoin;if(i===undefined)return;const k=key(rows[Number(i)]);if(e.target.checked)selected.add(k);else selected.delete(k);render();});
document.addEventListener('radar-coins-changed',render);
document.addEventListener('radar-coin-center-updated',e=>{operations=e.detail.operations||[];renderOperations();render();});
document.addEventListener('radar-desktop-loaded',()=>{render();refresh();});
document.addEventListener('radar-profile-changing',()=>{epoch++;selected.clear();attempt=null;operations=[];$('#coin-operation-result').textContent='';renderOperations();render();});
document.addEventListener('radar-mobile-loaded',()=>{epoch++;selected.clear();attempt=null;operations=[];$('#coin-operation-result').textContent='';renderOperations();render();if(bridge.snapshot().desktopLoaded)refresh();});
document.addEventListener('radar-desktop-error',()=>{epoch++;operations=[];renderOperations();render();});
render();
})();
