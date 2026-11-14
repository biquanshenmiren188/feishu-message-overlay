// Full keys are fetched only while managing devices; never included in page snapshots.
export function createDeviceManager({api,commit,getState,isReady,toast,onDraft,onTest}){
 const $=s=>document.querySelector(s),dialog=$('#bark-editor'),form=$('#bark-form'),list=$('#bark-devices');
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
 let devices=[],editing=null,generation=0,ready=false,working=false,revision=null;
 function feedback(text){$('#bark-device-feedback').textContent=text;$('#bark-device-feedback').hidden=!text;}
 function controls(){for(const button of dialog.querySelectorAll('button')){if(button.matches('[data-close]'))continue;button.disabled=working||!ready||!isReady();}$('#test-bark').disabled=working||!ready||!isReady()||!devices.length;}
 function render(){
  $('#bark-count').textContent='已绑定 '+devices.length+' 台设备';
  list.innerHTML=devices.map(d=>`<article class="bark-device" data-device="${esc(d.id)}"><div class="bark-device-heading"><strong>${esc(d.label)}</strong><span class="bark-bound">已绑定</span></div><div class="bark-key-label">Bark Key</div><div class="bark-key"><code>${esc(d.key)}</code><button type="button" data-device-action="copy" data-id="${esc(d.id)}" aria-label="复制 ${esc(d.label)} 的 Key">复制</button></div><div class="bark-device-actions"><button type="button" data-device-action="test" data-id="${esc(d.id)}">测试推送</button><button type="button" data-device-action="edit" data-id="${esc(d.id)}">编辑</button><button type="button" class="danger-text" data-device-action="remove" data-id="${esc(d.id)}">解绑</button></div></article>`).join('')||'<p class="helper">尚未绑定设备</p>';
  controls();
 }
 async function refresh(){
  const seq=++generation;ready=false;controls();
  try{const data=await api('devices');if(seq!==generation||!dialog.open)return;devices=data.devices;revision=data.revision;ready=true;render();}
  catch(e){if(seq!==generation)return;$('#bark-count').textContent='设备读取失败';$('#bark-form-error').textContent=e.message;}
 }
 function clear(){generation++;devices=[];ready=false;editing=null;revision=null;list.replaceChildren();form.reset();form.elements.key.value='';form.hidden=true;feedback('');onDraft(false);}
 function edit(device=null){
  if(!ready||!isReady()||working)return;
  editing=device?.id||null;form.reset();form.elements.label.value=device?.label||'我的 iPhone';form.elements.key.value=device?.key||'';
  $('#bark-edit-title').textContent=device?'编辑设备':'添加设备';$('#bark-form-error').textContent='';form.hidden=false;onDraft(false);form.elements.label.focus();
 }
 function cancel(){form.reset();form.elements.key.value='';form.hidden=true;editing=null;onDraft(false);$('#add-bark').focus();}
 // The list may have changed in another tab. Never silently overwrite stale device data.
 function currentRevision(){if(getState()?.revision===revision)return true;$('#bark-form-error').textContent='设置已更新，请重新打开设备管理后操作';return false;}
 async function mutate(data){
  if(!isReady()||working||!currentRevision())return false;
  working=true;controls();
  try{const ok=await commit(data);if(ok&&dialog.open){cancel();await refresh();}return ok;}
  finally{working=false;if(dialog.open)controls();}
 }
 $('#add-bark').onclick=()=>edit();$('#cancel-bark-edit').onclick=cancel;
 form.oninput=()=>onDraft(true);
 form.onsubmit=async e=>{e.preventDefault();$('#bark-form-error').textContent='';if(await mutate({action:'bind',...(editing?{deviceId:editing}:{}),key:form.elements.key.value,label:form.elements.label.value}))toast('设备绑定已保存');};
 list.onclick=async e=>{
  const button=e.target.closest('[data-device-action]');if(!button||!ready||working||!isReady())return;
  const device=devices.find(d=>d.id===button.dataset.id);if(!device)return;
  const action=button.dataset.deviceAction;
  if(action==='edit')return edit(device);
  if(action==='copy'){try{await navigator.clipboard.writeText(device.key);toast('Key 已复制');}catch{feedback('复制失败，可长按 Key 复制');}return;}
  if(action==='remove'){if(confirm('解除「'+device.label+'」的绑定？其他设备和报警规则保留。')&&await mutate({action:'unbind',deviceId:device.id}))toast('设备已解绑');return;}
  if(action==='test'){working=true;controls();try{await onTest(device.id);}finally{working=false;if(dialog.open)controls();}}
 };
 return {open(){clear();$('#bark-form-error').textContent='';$('#bark-count').textContent='正在读取设备…';dialog.showModal();refresh();},clear,feedback,async sync(){if(dialog.open&&form.hidden)await refresh();}};
}
