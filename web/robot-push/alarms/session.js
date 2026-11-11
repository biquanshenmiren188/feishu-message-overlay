// Alarm pages only need the existing bearer, not the Web Push settings UI.
export function token(){try{return localStorage.getItem('radar-settings-signed-out')?'':localStorage.getItem('radar-settings-token')||localStorage.getItem('radar-test-token')||'';}catch{return '';}}
const center=location.pathname.startsWith('/radar/push-test/')?'/radar/push-test/center/':'/radar/push-center/';
window.RadarAccount={token,open:()=>{location.href=center;}};
const entry=document.querySelector('.radar-account-entry');if(entry)entry.href=center;
export function connection(ready){const el=document.querySelector('.ra-entry-status');if(el)el.textContent=ready?'已连接':token()?'正在读取':'未连接';}
connection(false);
let previous=token();
window.addEventListener('storage',()=>{const next=token();if(next===previous)return;previous=next;connection(false);document.dispatchEvent(new Event('radar-profile-changing'));document.dispatchEvent(new CustomEvent('radar-profile-ready',{detail:{suffix:''}}));});
