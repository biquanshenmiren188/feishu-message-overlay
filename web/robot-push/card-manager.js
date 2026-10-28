import {notifyRulesChanged} from './rule-events.js?v=20261028-1';
export const CHANNELS=['desktop','mute','cards','mobile'];
export const NAMES={desktop:'电脑屏蔽',mute:'仅静音',cards:'行情卡片',mobile:'手机推送'};
export const VENUES=[['all','全部交易所'],['binance','Binance'],['okx','OKX'],['bybit','Bybit'],['bitget','Bitget'],['gate','Gate'],['aster','Aster'],['hyperliquid','Hyperliquid']];
const key=(channel,exchange)=>channel+'|'+exchange;
const stateName=(channel,value)=>value===true?(channel==='mute'?'仅静音':'屏蔽'):'正常推送';
const scopeName=exchange=>VENUES.find(([v])=>v===exchange)?.[1]||exchange;
const desktopName=(map,exchange)=>map.get(key('desktop',exchange))===true?'屏蔽':map.get(key('mute',exchange))===true?'仅静音':'正常推送';
function summarizeChanges(items,before,after=null,results=null){
 if(!after){after=new Map(before);for(const c of items){const k=key(c.channel,c.exchange);if(c.after===null)after.delete(k);else after.set(k,c.after);}}
 const groups=new Map();for(const c of items){const channel=['desktop','mute'].includes(c.channel)?'computer':c.channel,k=key(channel,c.exchange);if(!groups.has(k))groups.set(k,{channel,exchange:c.exchange,channels:new Set()});groups.get(k).channels.add(c.channel);}
 return [...groups.values()].map(g=>{
  const name=map=>g.channel==='computer'?desktopName(map,g.exchange):stateName(g.channel,map.get(key(g.channel,g.exchange))),label=g.channel==='computer'?'电脑推送':NAMES[g.channel];
  let text=scopeName(g.exchange)+' · '+label+'：';
  if(!results)return text+name(before)+' → '+name(after);
  const incomplete=[...g.channels].filter(c=>results[c]?.state!=='saved');
  return text+name(after)+(incomplete.length?'（当前已保存；未完成：'+incomplete.map(c=>NAMES[c]+' '+(results[c]?.error||'等待处理')).join('，')+'）':'（已保存）');
 });
}

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
const currentToken=()=>{try{return localStorage.getItem('radar-settings-token')||localStorage.getItem('radar-test-token')||'';}catch{return '';}};
let opened=null;
export function openCardManager(coin,{onSaved=()=>{}}={}){
 if(opened){opened.focus();return;}
 coin=coin.trim().toUpperCase();if(!/^[\p{L}\p{N}._-]{1,32}$/u.test(coin))return;
 const dialog=document.createElement('dialog');opened=dialog;dialog.className='bp-rule-dialog';dialog.setAttribute('aria-label',coin+' 币种规则');
 dialog.innerHTML=`<form><header><h2>${esc(coin)} · 币种规则</h2><button type="button" data-close aria-label="关闭币种规则">×</button></header><p class="bp-rule-help">仅静音保留消息、不播放声音；屏蔽后该渠道不再显示或推送。设置仅针对本币种所选交易所，其他筛选仍按原设置。修改后点击“保存修改”生效。</p><fieldset disabled><div class="bp-rule-rows"></div><button type="button" data-add>＋ 添加交易所范围</button></fieldset><p class="bp-rule-review"></p><p class="bp-rule-result" role="status"></p><footer><button type="button" data-block title="勾选此币种全部交易所的三端屏蔽，点击“保存修改”后生效">屏蔽三端</button><button type="button" data-close>关闭</button><button type="button" data-retry hidden>重试未完成项</button><button type="submit" data-save>保存修改</button></footer></form>`;
 document.body.append(dialog);dialog.showModal();
 const $=s=>dialog.querySelector(s),auth=currentToken();let baseline=new Map(),busy=false,loaded=false,pending=null,identityChanged=false;
 function row(exchange,values={}){
  const desktopMode=values.desktop===true?'hide':values.mute===true?'mute':'none';
  return `<div class="bp-rule-row"><label>交易所范围<select data-scope aria-label="交易所范围">${VENUES.map(([v,n])=>`<option value="${v}" ${v===exchange?'selected':''}>${n}</option>`).join('')}</select></label><label>电脑推送<select data-desktop-mode aria-label="电脑推送">${[['none','正常推送'],['mute','仅静音'],['hide','屏蔽']].map(([v,n])=>`<option value="${v}" ${v===desktopMode?'selected':''}>${n}</option>`).join('')}</select>${['desktop','mute'].map(c=>`<input type="hidden" data-channel="${c}" value="${values[c]==null?'none':values[c]?'on':'off'}">`).join('')}</label>${['cards','mobile'].map(c=>`<label>${NAMES[c]}<select data-block-mode="${c}" aria-label="${NAMES[c]}状态"><option value="none" ${values[c]!==true?'selected':''}>正常推送</option><option value="on" ${values[c]===true?'selected':''}>屏蔽</option></select><input type="hidden" data-channel="${c}" value="${values[c]==null?'none':values[c]?'on':'off'}"></label>`).join('')}<button type="button" data-remove>删除本行</button></div>`;
 }
 function setDesktopMode(row,mode){row.querySelector('[data-desktop-mode]').value=mode;row.querySelector('[data-channel="desktop"]').value=mode==='hide'?'on':'none';row.querySelector('[data-channel="mute"]').value=mode==='mute'?'on':'none';}
 function setBlockMode(row,channel,value){row.querySelector(`[data-block-mode="${channel}"]`).value=value;row.querySelector(`[data-channel="${channel}"]`).value=value;}
 function fill(data){baseline=coinMap(data,coin);loaded=true;const scopes=[...new Set([...baseline.keys()].map(k=>k.split('|')[1]))];$('.bp-rule-rows').innerHTML=(scopes.length?scopes:['all']).map(e=>row(e,Object.fromEntries(CHANNELS.map(c=>[c,baseline.get(key(c,e))??null])))).join('');}
 function changes(){return coinChanges(coin,baseline,[...dialog.querySelectorAll('.bp-rule-row')].map(r=>({exchange:r.querySelector('[data-scope]').value,...Object.fromEntries([...r.querySelectorAll('[data-channel]')].map(s=>[s.dataset.channel,s.value==='none'?null:s.value==='on']))})));}
 function review(draftChange=false){
  if(auth!==currentToken())identityChanged=true;let count=0,error='',summary=[];try{const edits=changes();count=edits.length;summary=summarizeChanges(edits,baseline);}catch(e){error=e.message;}
  $('.bp-rule-review').textContent=error||(count?`本范围草稿有 ${summary.length} 项修改，尚未保存。${summary.join('；')}。点击“保存修改”后生效。`:'当前显示本范围已保存设置；修改后需要保存。');
  $('fieldset').disabled=busy||!loaded||identityChanged||!!pending;$('[data-save]').disabled=busy||!loaded||identityChanged||!!pending||!!error||!count;$('[data-block]').disabled=busy||!loaded||identityChanged||!!pending||!!error;for(const b of dialog.querySelectorAll('[data-close]'))b.disabled=busy;$('[data-retry]').hidden=!pending;$('[data-retry]').disabled=busy||identityChanged;
  if(draftChange&&loaded&&!busy&&!pending&&!identityChanged)$('.bp-rule-result').textContent=count?'本范围草稿尚未保存。点击“保存修改”后生效。':'当前选项与本范围已保存设置一致。';
 }
 async function api(route,data){if(!auth||identityChanged||auth!==currentToken())throw Error('请连接自己的推送码，再重新打开此弹窗');const r=await fetch('/radar/push-test/api/'+route,{method:data?'POST':'GET',headers:{Authorization:'Bearer '+auth,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined,cache:'no-store',redirect:'error',signal:AbortSignal.timeout(15000)});let value;try{value=await r.json();}catch{throw Error('登录或网络异常，请重新打开网站');}if(!r.ok)throw Error(value.error||'保存失败');if(identityChanged||auth!==currentToken())throw Error('连接码已切换，请在原方案操作记录中核对保存结果');return value;}
 async function perform(request){if(busy||!loaded||identityChanged)return;pending=request;busy=true;review();$('.bp-rule-result').textContent='正在保存…';try{const data=await api(request.route,request.body);const failures=Object.values(data.operation.results).some(r=>r.state==='failed'||r.state==='pending');$('.bp-rule-result').textContent=summarizeChanges(request.body.changes,baseline,coinMap(data,coin),data.operation.results).join('；');if(!failures){pending=null;fill(data);}else $('.bp-rule-result').textContent+='。可重试未完成项；若有规则冲突，请关闭后重新管理。';notifyRulesChanged();onSaved();}catch(e){$('.bp-rule-result').textContent=e.message+'。结果未确认时请用“重试未完成项”核对。';}finally{busy=false;review();}}
 async function load(){busy=true;review();$('.bp-rule-result').textContent='正在加载已保存规则…';try{fill(await api('coin-blocks'));$('.bp-rule-result').textContent='已加载云端规则，以下选项为本范围已保存状态。';}catch(e){$('.bp-rule-result').textContent=e.message;}finally{busy=false;review();}}
 const blockAll=()=>{
  review();if($('[data-block]').disabled)return;
  let all=[...dialog.querySelectorAll('.bp-rule-row')].find(r=>r.querySelector('[data-scope]').value==='all');
  if(!all){$('.bp-rule-rows').insertAdjacentHTML('beforeend',row('all'));all=$('.bp-rule-rows').lastElementChild;}
  setDesktopMode(all,'hide');for(const channel of ['cards','mobile'])setBlockMode(all,channel,'on');
  review();$('.bp-rule-result').textContent=changes().length?'本币种全部交易所的三端屏蔽已加入草稿，尚未保存。点击“保存修改”后生效。':'当前已保存三端屏蔽，无需重复保存。';
 };
 const identityEvent=()=>{if(auth!==currentToken()){identityChanged=true;loaded=false;$('.bp-rule-result').textContent='推送码已切换，请关闭后重新打开本方案规则。';review();}};window.addEventListener('storage',identityEvent);window.addEventListener('focus',identityEvent);
 dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();});dialog.addEventListener('close',()=>{window.removeEventListener('storage',identityEvent);window.removeEventListener('focus',identityEvent);dialog.remove();opened=null;});
 dialog.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.hasAttribute('data-close')&&!busy)dialog.close();if(b.hasAttribute('data-remove')){b.closest('.bp-rule-row').remove();review(true);}if(b.hasAttribute('data-add')){const used=[...dialog.querySelectorAll('[data-scope]')].map(s=>s.value),next=VENUES.find(([v])=>!used.includes(v));if(next){$('.bp-rule-rows').insertAdjacentHTML('beforeend',row(next[0]));review(true);}}if(b.hasAttribute('data-block'))blockAll();if(b.hasAttribute('data-retry')&&pending)perform(pending);});
 $('form').addEventListener('submit',e=>{e.preventDefault();if($('[data-save]').disabled)return;perform({route:'edit-coins',body:{requestId:crypto.randomUUID(),changes:changes()}});});dialog.addEventListener('change',e=>{if(e.target.matches('[data-desktop-mode]'))setDesktopMode(e.target.closest('.bp-rule-row'),e.target.value);if(e.target.matches('[data-block-mode]'))setBlockMode(e.target.closest('.bp-rule-row'),e.target.dataset.blockMode,e.target.value);review(true);});
 load();
}
