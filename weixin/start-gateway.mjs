import fs from 'node:fs';
import path from 'node:path';
import {randomBytes} from 'node:crypto';
import {spawn} from 'node:child_process';
import {fileURLToPath,pathToFileURL} from 'node:url';
const folder=path.dirname(fileURLToPath(import.meta.url)),root=process.argv[2];
if(!root||!path.isAbsolute(root))process.exit(2);
for(const key of Object.keys(process.env))if(/OPENAI|ANTHROPIC|CLAUDE|CODEX|GEMINI|AZURE|AWS|API_KEY|AUTH_TOKEN|^OPENCLAW_|^CLAWDBOT_/.test(key))delete process.env[key];
Object.assign(process.env,{OPENCLAW_HOME:root,OPENCLAW_STATE_DIR:path.join(root,'state'),OPENCLAW_CONFIG_PATH:path.join(root,'gateway.json'),OPENCLAW_CONFIG:path.join(root,'gateway.json'),OPENCLAW_LOG_LEVEL:'FATAL',DO_NOT_TRACK:'1',OPENCLAW_DISABLE_BONJOUR:'1'});
const statusPath=path.join(folder,'gateway-safe-status.json');
const status=value=>fs.writeFileSync(statusPath,JSON.stringify(value));
try{
 fs.mkdirSync(root,{recursive:true});
 const file=path.join(root,'gateway.json');let token;
 if(fs.existsSync(file))token=JSON.parse(fs.readFileSync(file,'utf8')).gateway?.auth?.token;
 token||=randomBytes(32).toString('hex');
 const config={gateway:{mode:'local',bind:'loopback',port:18881,auth:{mode:'token',token},controlUi:{enabled:false},terminal:{enabled:false},cliAgents:{enabled:false},tailscale:{mode:'off'},reload:{mode:'off'}},logging:{level:'silent',consoleLevel:'silent',audit:{enabled:false,messages:'off'}},update:{checkOnStart:false,auto:{enabled:false}},telemetry:{enabled:false},browser:{enabled:false},tools:{deny:['*']},plugins:{allow:['openclaw-weixin'],load:{paths:[path.join(folder,'node_modules','@tencent-weixin','openclaw-weixin')]},slots:{memory:'none'},entries:{'openclaw-weixin':{enabled:true}}},channels:{'openclaw-weixin':{enabled:true,quoteCache:{enabled:false},replyProgressMessages:false}}};
 const {t:Schema}=await import('./node_modules/openclaw/dist/zod-schema-D-8T4ion.js');
 const validated=Schema.safeParse(config);if(!validated.success){status({running:false,stage:'config',issues:validated.error.issues.map(i=>({path:i.path.join('.'),code:i.code}))});process.exit(2);}
 fs.writeFileSync(file,JSON.stringify(config,null,2),{mode:0o600});
 const child=spawn(process.execPath,['--import',pathToFileURL(path.join(folder,'gateway-preload.mjs')).href,path.join(folder,'node_modules','openclaw','openclaw.mjs'),'gateway','run'],{cwd:folder,env:process.env,windowsHide:true,stdio:['ignore','pipe','pipe']});
 status({running:true,stage:'starting',pid:child.pid,forwarding:false});
 let hints=new Set();function inspect(chunk){const s=String(chunk);for(const tag of ['EADDRINUSE','Cannot find','Invalid config','channelRuntime missing','plugin not found','Failed to load','SyntaxError','Error','gateway.mode','blocked','Missing config','BINDING_INCOMPLETE','UNIQUE_BINDING_REQUIRED','ERR_MODULE_NOT_FOUND','ERR_PACKAGE_PATH_NOT_EXPORTED','Node.js','unsupported','pairing','untrusted','plugins.load','gateway.auth','permission','failed','not found','ENOENT','EPERM','EACCES'])if(s.includes(tag))hints.add(tag);for(const match of s.matchAll(/(?:Error|TypeError|ReferenceError): ([A-Z][A-Z0-9_]{3,60})\b/g))hints.add(match[1]);}
 child.stdout.on('data',inspect);child.stderr.on('data',chunk=>{inspect(chunk);for(const m of String(chunk).matchAll(/\b([A-Za-z0-9_.-]+\.(?:m?js)):(\d+)(?::(\d+))?/g))hints.add(m[1]+':'+m[2]);for(const name of ['TypeError','ReferenceError','RangeError','ENOENT','ERR_INVALID_ARG_TYPE','ERR_INVALID_URL','ERR_UNKNOWN_FILE_EXTENSION'])if(String(chunk).includes(name))hints.add(name);});
 child.on('exit',code=>status({running:false,stage:'exited',exitCode:code,hints:[...hints],forwarding:false}));
 child.on('error',()=>status({running:false,stage:'spawn_failed',forwarding:false}));
}catch{status({running:false,stage:'setup_failed',forwarding:false});process.exitCode=1;}
