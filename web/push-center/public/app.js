const $=s=>document.querySelector(s),apiBase='/radar/push-center-api/';
const token=()=>window.RadarAccount?.token()||'';
let state=null,epoch=0,busy=false,mode='',pending=null,loadedToken='';
const dialog=$('#pc-editor'),form=$('#pc-form');
window.RadarHasUnsavedChanges=()=>busy||!!pending;
const note=(text,error=false)=>{$('#pc-message').textContent=text;$('#pc-message').classList.toggle('is-error',error);};
async function api(route,data,auth=token()){
 const response=await fetch(apiBase+route,{method:data===undefined?'GET':'POST',headers:{Authorization:'Bearer '+auth,'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),cache:'no-store',redirect:'error',signal:AbortSignal.timeout(25000)});
 let value;try{value=await response.json();}catch{throw Error('未取得服务响应，请检查网站登录后重试');}
 if(!response.ok){const e=Error(value.error||'操作失败');e.status=response.status;throw e;}return value;
}
function badge(id,text,kind=''){$(id).textContent=text;$(id).className='pc-badge '+kind;}
function render(waiting=false){
 const ready=!!state;$('#pc-disconnected').hidden=ready||waiting;$('#pc-profile').hidden=!ready;$('#pc-management').hidden=!ready;$('#pc-exit').hidden=!token();
 if(!ready)return;
 $('#pc-name').textContent=state.name;$('#pc-code').textContent=state.pushCode;
 const d=state.desktop,p=state.phone,b=state.bark;
 badge('#pc-desktop-status',!d.available?'暂不可用':d.connected?'在线':'暂无在线客户端',!d.available?'is-warning':d.connected?'':'is-off');
 $('#pc-desktop-detail').textContent=!d.available?d.error:d.connected?'已收到当前推送码的桌面连接心跳。':'在桌面客户端输入同一个推送码即可连接。';
 badge('#pc-phone-status',p.subscribed?'已绑定':'待绑定',p.subscribed?'':'is-off');
 $('#pc-phone-detail').textContent=p.subscribed?(p.enabled?'消息接收已开启；最终显示取决于手机通知权限。':'设备已绑定，消息接收已关闭。'):'在安卓浏览器或 iPhone 主屏幕雷达中开启通知。';
 $('#pc-phone-test').disabled=!p.subscribed;
 badge('#pc-bark-status',!b.available?'暂不可用':b.device?'已绑定':'待绑定',!b.available?'is-warning':b.device?'':'is-off');
 $('#pc-bark-detail').textContent=!b.available?b.error:b.device?b.device.label+(b.enabled?' · 接收币种价格报警':' · 云端报警已暂停'):'绑定后接收币种价格报警。';
 $('#pc-bark-manage').disabled=!b.available;$('#pc-bark-manage').textContent=b.device?'管理设备':'绑定设备';$('#pc-bark-test').hidden=!b.device;$('#pc-bark-test').disabled=!b.available;
 const logs=$('#pc-history-list');logs.replaceChildren();
 if(!state.history.length){const p=document.createElement('p');p.textContent='暂无中心操作记录；原有消息和报警记录仍在各自页面。';p.style.padding='16px 0';logs.append(p);}
 for(const item of state.history){const row=document.createElement('div'),at=document.createElement('time'),action=document.createElement('span');row.className='pc-log';at.textContent=new Date(item.at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});action.textContent=item.action;row.append(at,action);logs.append(row);}
}
async function load(){
 const auth=token(),generation=epoch;
 if(!auth){state=null;loadedToken='';render();note('连接后查看当前推送码的设备与设置。');return;}
 try{const next=await api('state',undefined,auth);if(auth!==token()||generation!==epoch)return;state=next;loadedToken=auth;render();note('已同步当前推送码。');}
 catch(e){if(auth!==token()||generation!==epoch)return;if(loadedToken!==auth)state=null;render();note(e.message,true);}
}
function close(){if(busy)return;if(pending){$('#pc-form-error').textContent='操作结果待确认，请先重试原操作。';return;}dialog.close();}
function editor(next){
 if(busy)return;
 if(pending){dialog.showModal();$('#pc-form-error').textContent='请先重试结果未确认的原操作。';return;}
 mode=next;const fields=$('#pc-fields');fields.replaceChildren();$('#pc-form-error').textContent='';$('#pc-submit').hidden=false;$('#pc-submit').textContent='保存';
 const field=(label,name,value='',type='text')=>{const l=document.createElement('label'),input=document.createElement('input');l.htmlFor='pc-field-'+name;l.textContent=label;input.id=l.htmlFor;input.name=name;input.value=value;input.type=type;input.required=true;input.maxLength=name==='code'?8:name==='key'?180:30;if(name==='code'){input.inputMode='numeric';input.pattern='[0-9]{8}';input.autocomplete='off';}fields.append(l,input);};
 const text=t=>{const p=document.createElement('p');p.textContent=t;fields.append(p);};
 const titles={rename:'修改推送码名称',switch:'切换推送码',create:'新建推送码',bark:'Bark 接收设备',desktop:'连接桌面客户端',unbind:'解除 Bark 绑定','test-bark':'发送 Bark 测试提醒','test-phone':'发送手机测试提醒'};
 $('#pc-editor-title').textContent=titles[next];
 if(next==='rename')field('推送码名称','name',state.name);
 if(next==='switch'){field('推送码','code');text('连接后载入该码已保存的规则；手机端切换会沿用既有本机通知切换流程。');$('#pc-submit').textContent='连接此码';}
 if(next==='create'){text('创建一个独立推送码并连接，新码的设备和规则为空。原推送码及其云端推送保持。创建后可以改名。');$('#pc-submit').textContent='创建并连接';}
 if(next==='desktop'){text('在桌面客户端设置中输入当前完整推送码。连接成功后，桌面消息与行情卡片会读取此码的规则。');text('解除桌面连接请在对应客户端操作；此处不会远程关闭客户端。');$('#pc-submit').hidden=true;}
 if(next==='bark'){field('设备名称','label',state.bark.device?.label||'我的 iPhone');field('Bark 推送地址或 Key','key','','password');text('粘贴 Bark App 首页的 https://api.day.app/… 地址。更换绑定会取消待发送的旧设备队列。');if(state.bark.device){const b=document.createElement('button');b.type='button';b.className='pc-destructive';b.textContent='解除当前绑定';b.onclick=()=>editor('unbind');fields.append(b);}$('#pc-submit').textContent='保存绑定';}
 if(next==='unbind'){text('解除当前推送码的 Bark 接收设备。价格规则保留，后续触发只记入报警记录，直到再次绑定设备。');$('#pc-submit').textContent='确认解除';}
 if(next.startsWith('test-')){text('将向当前推送码绑定的手机发送一条测试通知。接口接受不代表手机已经显示。');$('#pc-submit').textContent='发送一条测试通知';}
 if(!dialog.open)dialog.showModal();
}
async function submit(){
 if(busy)return;
 const auth=token(),generation=epoch,data=new FormData(form);busy=true;$('#pc-submit').disabled=true;
 try{
  if(mode==='switch'||mode==='create'){
   // Identity's own guard must not mistake this explicit form submission for an unrelated write.
   busy=false;
   if(!window.RadarIdentity)throw Error('连接组件尚未就绪，请稍后重试');
   if(mode==='switch')await window.RadarIdentity.connect(String(data.get('code')).trim());else await window.RadarIdentity.create();
   dialog.close();await load();return;
  }
  const route=mode==='rename'?'rename':mode==='test-phone'?'verify-phone':'bark';
  const body=pending?.body||{requestId:crypto.randomUUID().replaceAll('-',''),...(mode==='rename'?{name:String(data.get('name')).trim(),revision:state.revision}:mode==='test-phone'?{}:{revision:state.bark.revision,action:mode==='bark'?'bind':mode==='unbind'?'unbind':'test',...(mode==='bark'?{label:String(data.get('label')).trim(),key:String(data.get('key')).trim()}:{})})};
  form._request={body,route,auth};
  await api(route,body,auth);
  if(auth!==token()||generation!==epoch)return;
  pending=null;form._request=null;form.reset();dialog.close();await load();note(mode.startsWith('test-')?'测试请求已提交，请查看手机；接口接受不代表已显示。':'已保存。');
 }catch(e){
  if(auth!==token()&&mode!=='switch'&&mode!=='create')return;
  $('#pc-form-error').textContent=e.message;
  // Bark and rename are idempotent. Keep the exact request on uncertain responses.
  // Phone verification is rate-limited by the legacy service; never auto-repeat it.
  if(!['switch','create','test-phone'].includes(mode)&&(!e.status||e.status>=500)){
   // body is captured before the request below via the form's request snapshot.
   pending=form._request;$('#pc-submit').textContent='重试原操作';
  }else{pending=null;if(e.status===409)await load();}
 }finally{busy=false;$('#pc-submit').disabled=false;}
}
form.onsubmit=e=>{e.preventDefault();submit();};
dialog.querySelectorAll('[data-close]').forEach(b=>b.onclick=close);dialog.oncancel=e=>{e.preventDefault();close();};
for(const name of ['devices','business','history'])$('#pc-tab-'+name).onclick=()=>{for(const n of ['devices','business','history']){$('#pc-tab-'+n).setAttribute('aria-selected',String(n===name));$('#pc-'+n).hidden=n!==name;}};
$('#pc-refresh').onclick=load;$('#pc-connect').onclick=()=>editor('switch');$('#pc-switch').onclick=()=>editor('switch');$('#pc-create').onclick=$('#pc-create-empty').onclick=()=>editor('create');$('#pc-rename').onclick=()=>editor('rename');
$('#pc-copy').onclick=async()=>{try{await navigator.clipboard.writeText(state.pushCode);note('推送码已复制。');}catch{note('复制失败，请选中完整推送码手动复制。',true);}};
$('#pc-desktop-manage').onclick=()=>editor('desktop');$('#pc-phone-manage').onclick=()=>window.RadarAccount?.open('phone');$('#pc-bark-manage').onclick=()=>editor('bark');$('#pc-bark-test').onclick=()=>editor('test-bark');$('#pc-phone-test').onclick=()=>editor('test-phone');
$('#pc-exit').onclick=()=>document.getElementById('ra-exit')?.click();
document.addEventListener('radar-profile-changing',()=>{epoch++;state=null;loadedToken='';pending=null;form._request=null;dialog.close();render(!!token());note(token()?'正在切换推送码…':'请重新连接推送码。');});
document.addEventListener('radar-profile-ready',load);
window.addEventListener('focus',()=>{if(!dialog.open)load();});
if(location.pathname.startsWith('/radar/push-test/')||matchMedia('(display-mode: standalone)').matches||navigator.standalone===true){for(const a of document.querySelectorAll('.pc-layout a')){if(a.pathname==='/radar/robot-push/')a.href='/radar/push-test/';if(a.pathname==='/radar/robot-push/settings/')a.href='/radar/push-test/settings/';}}
render(true);setTimeout(load,250);
