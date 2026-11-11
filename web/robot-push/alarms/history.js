import {token,connection} from './session.js?v=20261111-smooth1';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const status={queued:'等待发送',sending:'发送中',accepted:'接口接受',retry:'等待重试',failed:'发送失败',unknown:'结果未知',expired:'已过期',cancelled:'已取消',no_device:'未绑定设备'};
let page=1,before='',controller,sequence=0,total=0;
async function api(route,signal){const r=await fetch('/radar/alarms-api/'+route,{headers:{Authorization:'Bearer '+token()},cache:'no-store',redirect:'error',signal});const data=await r.json();if(!r.ok)throw Error(data.error||'读取失败');return data;}
function controls(busy){$('#history-prev').disabled=busy||page<=1;$('#history-next').disabled=busy||page*20>=total;$('#history-refresh').disabled=busy;}
async function load(reset=false){
 if(reset){page=1;before='';}controller?.abort();controller=new AbortController();const n=++sequence,auth=token();
 if(!auth){connection(false);$('#history-message').textContent='请先在推送中心连接推送码。';$('#event-list').replaceChildren();total=0;controls(false);return;}
 controls(true);$('#history-message').textContent='正在读取记录…';
 const query=new URLSearchParams({page:String(page),q:$('#history-search').value.trim(),status:$('#history-status').value,days:$('#history-days').value});if(before)query.set('before',before);
 try{const data=await api('history?'+query,AbortSignal.any([controller.signal,AbortSignal.timeout(15000)]));if(n!==sequence||auth!==token())return;
  before=String(data.before);total=data.total;connection(true);$('#history-message').textContent=total?`共 ${total} 条记录`:'没有匹配的报警记录';$('#history-page').textContent=`第 ${page} / ${Math.max(1,Math.ceil(total/20))} 页`;
  $('#event-list').innerHTML=data.items.map(e=>`<details data-id="${esc(e.id)}"><summary><span>${esc(e.title)}<time>${new Date(e.at*1000).toLocaleString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'})} 北京时间</time></span><span class="alarm-badge">${status[e.status]||esc(e.status)}</span></summary><div class="history-body"></div></details>`).join('');
 }catch(e){if(e.name!=='AbortError'&&n===sequence){$('#history-message').textContent=e.message+'，可点击刷新重试。';}}
 finally{if(n===sequence)controls(false);}
}
$('#history-form').onsubmit=e=>{e.preventDefault();load(true);};$('#history-refresh').onclick=()=>load(true);
$('#history-prev').onclick=()=>{page--;load();};$('#history-next').onclick=()=>{page++;load();};
$('#event-list').addEventListener('toggle',async e=>{
 const d=e.target;if(d.tagName!=='DETAILS'||!d.open||d.dataset.loading||d.dataset.loaded)return;
 const auth=token(),box=d.querySelector('.history-body');d.dataset.loading='1';box.textContent='正在读取详情…';
 try{const result=await api('event?id='+encodeURIComponent(d.dataset.id),AbortSignal.timeout(15000));if(auth!==token()||!d.isConnected)return;box.textContent=result.body+(result.error?'\n原因：'+result.error:'')+'\n发送尝试 '+result.attempts+' 次';d.dataset.loaded='1';}
 catch(e){box.textContent='详情读取失败，请收起后重新展开。';}finally{delete d.dataset.loading;}
},true);
document.addEventListener('radar-profile-changing',()=>{controller?.abort();sequence++;$('#event-list').replaceChildren();$('#history-message').textContent='正在切换推送码…';});
document.addEventListener('radar-profile-ready',()=>load(true));
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&page===1&&!$('#event-list details[open]'))load(true);});
load(true);
