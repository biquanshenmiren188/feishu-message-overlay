/* Unified coin administration. Edits are exact-scope deltas, not full settings. */
(()=>{
const $=s=>document.querySelector(s),R=window.RadarRules,B=window.RadarCoinSettings;
const channels=['desktop','mute','cards','mobile'],names={desktop:'电脑屏蔽',mute:'电脑静音',cards:'行情卡片',mobile:'手机推送'};
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const key=(c,coin,exchange)=>[c,coin,exchange].join('|'),stateName=v=>v===null?'未设置':v?'已启用':'已停用';
const scope=e=>e==='all'?'全部交易所':R.name(e),validCoin=c=>/^[\p{L}\p{N}._-]{1,32}$/u.test(c);
let base=new Map(),mode='matrix',originalCoin='',targets=[],action='',changes=[],queue=null,saving=false,generation=0;
function snapshot(){const s=B.snapshot(),map=new Map();for(const c of channels)for(const r of s.profiles[c].coins){const k=key(c,r.coin,r.exchange);map.set(k,map.get(k)===true||r.enabled);}return map;}
function decode(k,value){const [channel,coin,exchange]=k.split('|');return {channel,coin,exchange,before:value};}
function rowMarkup(exchange,states={}){return `<div class="matrix-row"><label class="matrix-scope"><span>交易所范围</span><select data-matrix-scope>${[['all','全部交易所'],...R.exchanges.map(e=>[e[0],e[1]])].map(([v,n])=>`<option value="${v}" ${v===exchange?'selected':''}>${esc(n)}</option>`).join('')}</select></label>${channels.map(c=>`<label><span>${names[c]}</span><select data-matrix-channel="${c}" aria-label="${names[c]}状态"><option value="none" ${states[c]==null?'selected':''}>未设置</option><option value="on" ${states[c]===true?'selected':''}>已启用</option><option value="off" ${states[c]===false?'selected':''}>已停用</option></select></label>`).join('')}<button type="button" data-center-remove class="danger-text">删除本行</button></div>`;}
function setup(title){
 if(saving)return false;queue=null;changes=[];$('#center-fields').disabled=false;$('#center-save').hidden=false;$('#center-retry').hidden=true;$('#center-cancel').textContent='取消';$('#center-error').textContent='';$('#center-results').textContent='';$('#coin-manager-title').textContent=title;$('#center-context').textContent=(window.RadarCoinAPI?.planLabel()||'当前推送码方案')+' · 保存后同步生效';
 if(!$('#coin-manager').open)$('#coin-manager').showModal();return true;
}
function matrix(coin){
 if(!setup(coin?'管理 '+coin+' 的规则':'添加币种规则'))return;
 mode='matrix';originalCoin=coin||'';base=snapshot();const scopes=[...new Set([...base.keys()].map(k=>k.split('|')).filter(x=>x[1]===originalCoin).map(x=>x[2]))];
 $('#coin-manager-body').innerHTML=`<label class="stack-label center-symbol">币种<input id="center-coin" value="${esc(originalCoin)}" placeholder="例如 PTB" autocomplete="off" maxlength="32" required></label><p class="helper">四类规则独立设置；电脑屏蔽优先于静音。未设置的渠道可直接选择“已启用”。</p><div id="matrix-rows">${(scopes.length?scopes:['all']).map(e=>rowMarkup(e,Object.fromEntries(channels.map(c=>[c,base.get(key(c,originalCoin,e))??null])))).join('')}</div><button type="button" id="center-add-scope">＋ 添加交易所范围</button>`;review();
}
function batch(rows,kind){
 if(!rows.length)return;const label={block:'屏蔽三端',mute:'仅静音',pause:'停用规则',delete:'删除规则'}[kind];if(!setup(label+' · '+rows.length+' 项'))return;
 mode='batch';targets=rows.map(r=>({...r}));action=kind;base=snapshot();
 $('#coin-manager-body').innerHTML=`<div class="batch-targets">${targets.map(r=>`<span>${esc(r.coin)} / ${esc(scope(r.exchange))}</span>`).join('')}</div><p class="helper">仅处理上面列出的币种与交易所范围。${kind==='mute'?'只启用电脑静音，现有电脑屏蔽保持；若命中屏蔽规则，消息仍会隐藏。':kind==='delete'?'删除后可从操作记录撤销；其他范围的规则仍可能生效。':kind==='pause'?'停用后保留规则，之后可重新启用。':'启用电脑屏蔽、行情卡片和当前推送码方案屏蔽，静音规则保持。'}</p>${['delete','pause'].includes(kind)?'<div class="center-channel-options">'+channels.map(c=>`<label><input type="checkbox" data-center-target="${c}" checked>${names[c]}</label>`).join('')+'</div>':''}`;review();
}
function compile(){
 const next=new Map(base);
 if(mode==='matrix'){
  const coin=$('#center-coin').value.trim().toUpperCase();if(!validCoin(coin))throw Error('请输入有效的币种代码');
  if(coin!==originalCoin&&[...base.keys()].some(k=>k.split('|')[1]===coin))throw Error('目标币种已有规则，请打开该币种管理，避免覆盖现有设置');
  for(const k of base.keys())if(k.split('|')[1]===originalCoin)next.delete(k);
  const seen=new Set();for(const row of document.querySelectorAll('.matrix-row')){const exchange=row.querySelector('[data-matrix-scope]').value;if(seen.has(exchange))throw Error('交易所范围重复，请合并到同一行');seen.add(exchange);for(const s of row.querySelectorAll('[data-matrix-channel]'))if(s.value!=='none')next.set(key(s.dataset.matrixChannel,coin,exchange),s.value==='on');}
 }else if(mode==='batch'){
  const selected=action==='block'?['desktop','cards','mobile']:action==='mute'?['mute']:[...document.querySelectorAll('[data-center-target]:checked')].map(x=>x.dataset.centerTarget);
  for(const r of targets)for(const c of selected){const k=key(c,r.coin,r.exchange);if(action==='delete')next.delete(k);else if(action==='pause'){if(next.has(k))next.set(k,false);}else next.set(k,true);}
 }
 return [...new Set([...base.keys(),...next.keys()])].filter(k=>(base.get(k)??null)!==(next.get(k)??null)).map(k=>({...decode(k,base.get(k)??null),after:next.get(k)??null}));
}
function describe(c){return `${c.coin} / ${scope(c.exchange)} / ${names[c.channel]}：${stateName(c.before)} → ${c.after===null?'删除':stateName(c.after)}`;}
function review(){
 if(queue||saving)return;let error='';try{changes=compile();}catch(e){changes=[];error=e.message;}
 $('#center-change-count').textContent=changes.length;$('#center-changes').innerHTML=changes.length?'<ul>'+changes.map(c=>'<li>'+esc(describe(c))+'</li>').join('')+'</ul>':'<p class="helper">尚无改动</p>';
 const loaded=B.snapshot();$('#center-error').textContent=error||(!loaded.desktopLoaded||!loaded.mobileLoaded?'请先连接自己的推送码并加载本方案三端规则':'');$('#center-save').disabled=!!error||!changes.length||!loaded.desktopLoaded||!loaded.mobileLoaded;$('#center-save').textContent='保存 '+changes.length+' 项修改';
}
function resultUpdate(data){B.receive(data);document.dispatchEvent(new CustomEvent('radar-coin-center-updated',{detail:data}));}
async function execute(){
 if(saving||!queue)return;const epoch=generation;saving=true;$('.settings').inert=true;$('#center-fields').disabled=true;$('#center-save').disabled=true;$('#center-retry').hidden=true;$('#center-cancel').disabled=true;$('#coin-manager-close').disabled=true;$('#center-error').textContent='';
 let completed=true;
 try{for(const request of queue){const data=await window.RadarCoinAPI.edit(request);if(epoch!==generation)return;resultUpdate(data);const failed=Object.entries(data.operation.results).filter(([,r])=>r.state==='failed');
   $('#center-results').textContent=Object.entries(data.operation.results).filter(([,r])=>r.state!=='skipped').map(([c,r])=>names[c]+'：'+(r.state==='saved'?'已保存':r.error||'未完成')).join('；');
   if(failed.length){completed=false;$('#center-error').textContent='部分规则未保存。其他页面修改引起的冲突，请关闭后重新打开管理；临时失败可重试。';break;}
  }
  if(completed){const newCoin=mode==='matrix'?$('#center-coin').value.trim().toUpperCase():null;queue=null;$('#center-fields').disabled=true;$('#center-save').hidden=true;$('#center-cancel').textContent='完成';$('#center-results').textContent='本次修改已全部保存。电脑小窗下次同步后生效，手机应用于后续新消息。';$('#center-change-count').textContent=0;$('#center-changes').innerHTML='<p class="helper">保存完成，可关闭后继续管理。</p>';B.toast('规则已保存');if(newCoin)$('#coin-manager-title').textContent=newCoin+' · 已保存';}
 }catch(e){if(epoch!==generation)return;completed=false;$('#center-error').textContent=e.message+'。结果尚未确认，可使用原操作重试核对。';}
 finally{if(!completed)$('#center-cancel').textContent='关闭';saving=false;$('.settings').inert=false;$('#center-cancel').disabled=false;$('#coin-manager-close').disabled=false;$('#center-retry').hidden=completed||!queue;}
}
function retryOperation(op){
 if(!setup('重试未完成的规则修改'))return;mode='operation';changes=op.changes;queue=[{requestId:op.id,changes:op.changes,...(op.undoOf?{undoOf:op.undoOf}:{})}];$('#coin-manager-body').innerHTML='<p>只重试未完成的渠道；已保存的渠道不重复修改。</p>';$('#center-changes').innerHTML='<ul>'+changes.map(c=>'<li>'+esc(describe(c))+'</li>').join('')+'</ul>';$('#center-change-count').textContent=changes.length;$('#center-save').hidden=true;$('#center-retry').hidden=false;
}
function undo(op){
 if(!setup('撤销本次删除'))return;mode='operation';changes=op.changes.filter(c=>c.after===null&&op.results[c.channel].state==='saved').map(c=>({...c,before:null,after:c.before}));
 queue=[{requestId:crypto.randomUUID(),changes,undoOf:op.id}];$('#coin-manager-body').innerHTML='<p>仅恢复本次已删除的规则。若规则已重新设置，将提示冲突，不覆盖新设置。</p>';$('#center-changes').innerHTML='<ul>'+changes.map(c=>'<li>'+esc(describe(c))+'</li>').join('')+'</ul>';$('#center-change-count').textContent=changes.length;$('#center-save').disabled=!changes.length;$('#center-save').textContent='恢复 '+changes.length+' 项规则';
}
$('#center-form').addEventListener('submit',e=>{e.preventDefault();if(!queue){review();if(!changes.length||$('#center-save').disabled)return;queue=[];for(let i=0;i<changes.length;i+=40)queue.push({requestId:crypto.randomUUID(),changes:changes.slice(i,i+40)});}execute();});
$('#center-fields').addEventListener('input',review);$('#center-fields').addEventListener('change',review);
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.id==='center-add-scope'){const used=[...document.querySelectorAll('[data-matrix-scope]')].map(s=>s.value),next=['all',...R.exchanges.map(e=>e[0])].find(x=>!used.includes(x));if(!next)return B.toast('所有交易所范围都已列出');$('#matrix-rows').insertAdjacentHTML('beforeend',rowMarkup(next));review();}if(b.hasAttribute('data-center-remove')){b.closest('.matrix-row').remove();review();}if(['coin-manager-close','center-cancel'].includes(b.id)&&!saving)$('#coin-manager').close();if(b.id==='center-retry')execute();});
$('#coin-manager').addEventListener('cancel',e=>{if(saving)e.preventDefault();});
for(const event of ['radar-profile-changing','radar-mobile-loaded'])document.addEventListener(event,()=>{generation++;if($('#coin-manager').open)$('#coin-manager').close();queue=null;});
window.RadarCoinCenter={matrix,batch,retryOperation,undo,describe};
// Card-page links open a fully loaded matrix; a URL never writes a rule.
const entry=new URLSearchParams(location.search),entryCoin=(entry.get('coin')||'').trim().toUpperCase();
let entryOpened=false;
function openEntry(){
 if(entryOpened)return;
 if(validCoin(entryCoin)){
  const s=B.snapshot();if(!s.desktopLoaded||!s.mobileLoaded)return;
  entryOpened=true;$('#tab-coins').click();matrix(entryCoin);
 }else if(entry.get('channel')==='cards'){entryOpened=true;$('[data-channel="cards"]').click();}
}
document.addEventListener('radar-desktop-loaded',()=>queueMicrotask(openEntry));
document.addEventListener('radar-mobile-loaded',()=>queueMicrotask(openEntry));
openEntry();
})();
