export const CHANNELS=['desktop','mute','cards','mobile'];
export const NAMES={desktop:'电脑屏蔽',mute:'电脑静音',cards:'行情卡片',mobile:'手机推送'};
export const VENUES=[['all','全部交易所'],['binance','Binance'],['okx','OKX'],['bybit','Bybit'],['bitget','Bitget'],['gate','Gate'],['aster','Aster'],['hyperliquid','Hyperliquid']];
const key=(channel,exchange)=>channel+'|'+exchange;
export function coinMap(data,coin){
 const policies={desktop:data.desktop.desktop.rules.hide,mute:data.desktop.desktop.rules.mute,cards:data.desktop.cards.settings,mobile:data.mobile.settings},out=new Map();
 for(const c of CHANNELS){const s=policies[c];for(const r of [...(s.excluded_coins||[]).map(coin=>({coin,exchange:'all',enabled:true})),...(s.advanced?.coins||[])])if(r.coin.toUpperCase()===coin){const k=key(c,r.exchange);out.set(k,out.get(k)===true||r.enabled);}}
 return out;
}
export function coinChanges(coin,before,rows){
 const after=new Map(),scopes=new Set();for(const row of rows){if(scopes.has(row.exchange))throw Error('交易所范围重复，请合并为一行');scopes.add(row.exchange);for(const c of CHANNELS)if(row[c]!==null)after.set(key(c,row.exchange),row[c]);}
 return [...new Set([...before.keys(),...after.keys()])].filter(k=>(before.get(k)??null)!==(after.get(k)??null)).map(k=>{const [channel,exchange]=k.split('|');return {channel,coin,exchange,before:before.get(k)??null,after:after.get(k)??null};});
}
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const currentToken=()=>localStorage.getItem('radar-settings-token')||localStorage.getItem('radar-test-token')||'';
let opened=null;
export function openCardManager(coin,{block=false,onSaved=()=>{}}={}){
 if(opened){opened.focus();return;}
 coin=coin.trim().toUpperCase();if(!/^[\p{L}\p{N}._-]{1,32}$/u.test(coin))return;
 const dialog=document.createElement('dialog');opened=dialog;dialog.className='bp-rule-dialog';dialog.setAttribute('aria-label',coin+' 币种规则');
 dialog.innerHTML=`<form><header><h2>${esc(coin)} · 币种规则</h2><button type="button" data-close aria-label="关闭币种规则">×</button></header><p class="bp-rule-help">电脑隐藏、电脑静音、行情卡片、手机推送分别设置。当前管理码的手机方案生效；隐藏优先于静音。</p><fieldset disabled><div class="bp-rule-rows"></div><button type="button" data-add>＋ 添加交易所范围</button></fieldset><p class="bp-rule-review"></p><p class="bp-rule-result" role="status"></p><footer><button type="button" data-block title="立即屏蔽此币种全部交易所的电脑消息、行情卡片和当前手机方案">屏蔽三端</button><button type="button" data-close>关闭</button><button type="button" data-retry hidden>重试未完成项</button><button type="submit" data-save>保存修改</button></footer></form>`;
 document.body.append(dialog);dialog.showModal();
 const $=s=>dialog.querySelector(s),auth=currentToken();let baseline=new Map(),busy=false,loaded=false,pending=null;
 function row(exchange,values={}){return `<div class="bp-rule-row"><label>交易所范围<select data-scope aria-label="交易所范围">${VENUES.map(([v,n])=>`<option value="${v}" ${v===exchange?'selected':''}>${n}</option>`).join('')}</select></label>${CHANNELS.map(c=>`<label>${NAMES[c]}<select data-channel="${c}" aria-label="${NAMES[c]}状态"><option value="none" ${values[c]==null?'selected':''}>未设置</option><option value="on" ${values[c]===true?'selected':''}>已启用</option><option value="off" ${values[c]===false?'selected':''}>已停用</option></select></label>`).join('')}<button type="button" data-remove>删除本行</button></div>`;}
 function fill(data){baseline=coinMap(data,coin);loaded=true;const scopes=[...new Set([...baseline.keys()].map(k=>k.split('|')[1]))];$('.bp-rule-rows').innerHTML=(scopes.length?scopes:['all']).map(e=>row(e,Object.fromEntries(CHANNELS.map(c=>[c,baseline.get(key(c,e))??null])))).join('');}
 function changes(){return coinChanges(coin,baseline,[...dialog.querySelectorAll('.bp-rule-row')].map(r=>({exchange:r.querySelector('[data-scope]').value,...Object.fromEntries([...r.querySelectorAll('[data-channel]')].map(s=>[s.dataset.channel,s.value==='none'?null:s.value==='on']))})));}
 function review(){let count=0,error='';try{count=changes().length;}catch(e){error=e.message;}$('.bp-rule-review').textContent=error||(count?`本次修改 ${count} 项，点击保存后同步生效。`:'未设置的渠道可直接选择“已启用”；删除只影响本币种所选范围。');$('fieldset').disabled=busy||!loaded||!!pending;$('[data-save]').disabled=busy||!loaded||!!pending||!!error||!count;$('[data-block]').disabled=busy||!!pending||count>0||!!error;for(const b of dialog.querySelectorAll('[data-close]'))b.disabled=busy;$('[data-retry]').hidden=!pending;$('[data-retry]').disabled=busy;}
 async function api(route,data){if(!auth||auth!==currentToken())throw Error('请连接原始管理推送码，再重新打开此弹窗');const r=await fetch('/radar/push-test/api/'+route,{method:data?'POST':'GET',headers:{Authorization:'Bearer '+auth,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined,cache:'no-store',redirect:'error',signal:AbortSignal.timeout(15000)});let value;try{value=await r.json();}catch{throw Error('登录或网络异常，请重新打开网站');}if(!r.ok)throw Error(value.error||'保存失败');if(auth!==currentToken())throw Error('连接码已切换，请在原方案操作记录中核对保存结果');return value;}
 async function perform(request){if(busy)return;pending=request;busy=true;review();$('.bp-rule-result').textContent='正在保存…';try{const data=await api(request.route,request.body);const failures=Object.values(data.operation.results).some(r=>r.state==='failed'||r.state==='pending');$('.bp-rule-result').textContent=Object.entries(data.operation.results).filter(([,r])=>r.state!=='skipped').map(([c,r])=>NAMES[c]+'：'+(r.state==='saved'?'已保存':r.error||'未完成')).join('；');if(!failures){pending=null;fill(data);}else $('.bp-rule-result').textContent+='。可重试未完成项；若有规则冲突，请关闭后重新管理。';onSaved();}catch(e){$('.bp-rule-result').textContent=e.message+'。结果未确认时请用“重试未完成项”核对。';}finally{busy=false;review();}}
 async function load(){busy=true;review();$('.bp-rule-result').textContent='正在加载已保存规则…';try{fill(await api('coin-blocks'));$('.bp-rule-result').textContent='已加载云端规则';}catch(e){$('.bp-rule-result').textContent=e.message;}finally{busy=false;review();}}
 const blockAll=()=>perform({route:'block-coins',body:{requestId:crypto.randomUUID(),coins:[coin],exchange:'all'}});
 dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();});dialog.addEventListener('close',()=>{dialog.remove();opened=null;});
 dialog.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.hasAttribute('data-close')&&!busy)dialog.close();if(b.hasAttribute('data-remove')){b.closest('.bp-rule-row').remove();review();}if(b.hasAttribute('data-add')){const used=[...dialog.querySelectorAll('[data-scope]')].map(s=>s.value),next=VENUES.find(([v])=>!used.includes(v));if(next){$('.bp-rule-rows').insertAdjacentHTML('beforeend',row(next[0]));review();}}if(b.hasAttribute('data-block'))blockAll();if(b.hasAttribute('data-retry')&&pending)perform(pending);});
 $('form').addEventListener('submit',e=>{e.preventDefault();if($('[data-save]').disabled)return;perform({route:'edit-coins',body:{requestId:crypto.randomUUID(),changes:changes()}});});dialog.addEventListener('change',review);
 if(block)blockAll();else load();
}
