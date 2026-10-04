import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const root=process.argv[2];
if(!root||!path.isAbsolute(root))process.exit(2);
for(const key of Object.keys(process.env))if(/OPENAI|ANTHROPIC|CLAUDE|CODEX|GEMINI|AZURE|AWS|API_KEY|AUTH_TOKEN|^OPENCLAW_|^CLAWDBOT_/.test(key))delete process.env[key];
process.env.OPENCLAW_HOME=root;
process.env.OPENCLAW_STATE_DIR=path.join(root,'state');
process.env.OPENCLAW_CONFIG_PATH=path.join(root,'gateway.json');
process.env.OPENCLAW_LOG_LEVEL='FATAL';
const write=process.stdout.write.bind(process.stdout);
const emit=o=>write(JSON.stringify(o)+'\n');
const resume=process.stdin.resume.bind(process.stdin);
process.stdin.resume=()=>{emit({kind:'verify'});return resume();};
const require=createRequire(import.meta.url);
const QRCode=require('./node_modules/qrcode-terminal/vendor/QRCode');
const level=require('./node_modules/qrcode-terminal/vendor/QRCode/QRErrorCorrectLevel');
function qr(url){const q=new QRCode(-1,level.L);q.addData(url);q.make();emit({kind:'qr',modules:q.modules});}
// SDK terminal rendering is intercepted. Only QR modules/status cross the private UI pipe.
process.stdout.write=(chunk,...args)=>{const text=String(chunk);const urls=text.match(/https:\/\/[^\s\u001b]+/g);if(urls)for(const url of urls)if(url.includes('weixin')||url.includes('wechat'))qr(url);if(text.includes('验证')||text.includes('verification'))emit({kind:'verify'});return true;};
process.stderr.write=()=>true;
console.log=()=>{};console.warn=()=>{};console.error=()=>{};
try {
 const {startWeixinLoginWithQr,waitForWeixinLogin}=await import('./node_modules/@tencent-weixin/openclaw-weixin/dist/src/auth/login-qr.js');
 const {saveWeixinAccount,registerWeixinAccountId,listIndexedWeixinAccountIds,loadWeixinAccount}=await import('./node_modules/@tencent-weixin/openclaw-weixin/dist/src/auth/accounts.js');
 const {normalizeAccountId}=await import('openclaw/plugin-sdk/account-id');
 const ids=listIndexedWeixinAccountIds();
 if(ids.length===1&&loadWeixinAccount(ids[0])?.token){emit({kind:'bound'});process.exit(0);}
 if(ids.length>1){emit({kind:'error',code:'MULTIPLE_BINDINGS'});process.exit(2);}
 emit({kind:'starting'});
 const start=await startWeixinLoginWithQr({force:true});
 if(!start.qrcodeUrl||!start.sessionKey)throw Error('QR_NOT_READY');
 qr(start.qrcodeUrl);
 const result=await waitForWeixinLogin({sessionKey:start.sessionKey,timeoutMs:480000});
 if(result.connected&&result.botToken&&result.accountId&&result.userId){
  fs.mkdirSync(root,{recursive:true});
  const id=normalizeAccountId(result.accountId);
  saveWeixinAccount(id,{token:result.botToken,baseUrl:result.baseUrl,userId:result.userId});
  registerWeixinAccountId(id);
  emit({kind:'bound'});
 }else emit({kind:'error',code:'LOGIN_NOT_COMPLETED'});
}catch{emit({kind:'error',code:'LOGIN_FAILED'});process.exitCode=1;}
