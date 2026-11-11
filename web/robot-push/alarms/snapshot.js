const prefix='radar-alarm-snapshot-v1:',maxAge=30*60*1000;
async function key(auth){return prefix+Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(auth))),b=>b.toString(16).padStart(2,'0')).join('');}
function valid(s){return s&&Number.isInteger(s.revision)&&typeof s.enabled==='boolean'&&Array.isArray(s.rules)&&s.rules.length<=100&&Array.isArray(s.events)&&s.events.length<=1&&s.rules.every(r=>r&&typeof r.id==='string'&&typeof r.symbol==='string')&&(!s.device||typeof s.device.label==='string');}
export async function readSnapshot(auth){if(!auth)return null;try{const entry=JSON.parse(sessionStorage.getItem(await key(auth)));return entry&&entry.at<=Date.now()&&Date.now()-entry.at<maxAge&&valid(entry.data)?entry:null;}catch{return null;}}
export async function saveSnapshot(auth,data){if(!auth||!valid(data))return;try{sessionStorage.setItem(await key(auth),JSON.stringify({at:Date.now(),data}));}catch{}}
export async function clearSnapshots(){try{for(const name of Object.keys(sessionStorage))if(name.startsWith(prefix))sessionStorage.removeItem(name);}catch{}}
