// Patch the actual BOT module without replacing independent rule/clipboard work.
import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';import assert from 'node:assert/strict';import ts from 'typescript';import {execFileSync} from 'node:child_process';
const [baseline,out]=process.argv.slice(2),sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
assert(baseline&&out&&!fs.existsSync(out),'Use a new candidate directory');
const baselineRaw=fs.readFileSync(path.join(baseline,'manifest.json')),base=JSON.parse(baselineRaw),inventoryRaw=fs.readFileSync(path.join(baseline,base.inventory.file));
assert.equal(base.release,'/opt/funding-radar-web/releases/20261101-ss-book-cache-1793505553745329896','Reinspect production');assert.equal(sha(inventoryRaw),base.inventory.sha256);
const original='performance-20261017/bot-feed-filter-8558edfdc4f12595.js',oldModule='mobile-reading-20261024/mobile-scroll-40aa04c470ae.js';
for(const[name,item]of Object.entries(base.files))assert.equal(sha(fs.readFileSync(path.join(baseline,name))),item.sha256,name);
let code=fs.readFileSync(path.join(baseline,original),'utf8');assert.equal(sha(code),'8558edfdc4f12595cdacb4ea02ef6d13a01ad2ef0cc38444c75091d02f866467');
const helper=fs.readFileSync('web/robot-push/mobile-scroll.js','utf8').replaceAll('\r\n','\n'),module='mobile-reading-20261101/mobile-scroll-'+sha(helper).slice(0,16)+'.js',edits=[];
function one(before,after,label){assert.equal(code.split(before).length-1,1,label);code=code.replace(before,after);edits.push({label,before,after});}
one('"/radar/'+oldModule+'"','"/radar/'+module+'"','version reading helper');
one('preserveCardViewport as __radarPreserve}','preserveCardViewport as __radarPreserve,retireCardNode as __radarRetire,clearCardPlaceholders as __radarClearPlaceholders}','import bounded removal helpers');
function wrap(name,skip){
 const sf=ts.createSourceFile('bot.js',code,99,true,ts.ScriptKind.JS),nodes=sf.statements.filter(n=>ts.isFunctionDeclaration(n)&&n.name?.text===name);assert.equal(nodes.length,1,name);const node=nodes[0],body=node.body;
 if(skip){assert.equal(skip,2);assert(body.statements[0].getText(sf).includes('__radarScroll.defer'));assert(ts.isIfStatement(body.statements[1]));}
 const at=skip?body.statements[skip-1].end:body.getStart(sf)+1,before=node.getText(sf),relative=at-node.getStart(sf),last=before.length-1;
 const after=before.slice(0,relative)+'return __radarPreserve(Xe,()=>{'+before.slice(relative,last)+'});'+before.slice(last);
 one(before,after,'preserve '+name+' DOM transaction');
}
wrap('q',2);wrap('qe',2);wrap('fn',0);
one('return __radarPreserve(Xe,()=>{let e=Date.now(),t=Rn.tick(e)','return __radarPreserve(Xe,()=>{!__defer&&__radarClearPlaceholders(Xe);let e=Date.now(),t=Rn.tick(e)','clear deferred card geometry at quiet commit');
one('Ve.get(l.data.id)?.card.remove();Ve.delete(l.data.id);','__radarRetire(Ve.get(l.data.id)?.card,__defer);Ve.delete(l.data.id);','redact blocked card immediately without collapsing a gesture');
one('for(let[l,f]of Ve)if(!r.has(l)){f.card.remove();Ve.delete(l);}','for(let[l,f]of Ve)if(!r.has(l)){__radarRetire(f.card,__defer);Ve.delete(l);}','retire expired card without collapsing a gesture');
one('u.age.textContent!==x&&(u.age.textContent=x)','!__defer&&u.age.textContent!==x&&(u.age.textContent=x)','defer age-label layout during native motion');
one('Ne.textContent=`${a} ACTIVE`,!__defer&&(kt.hidden=c>0),kt.textContent=','!__defer&&(Ne.textContent=`${a} ACTIVE`,kt.hidden=c>0,kt.textContent=','defer card count and empty-state layout');
one(';__cardPolicy.summary(t)})}var __cardPolicy,',',__cardPolicy.summary(t))})}var __cardPolicy,','defer summary layout with card transaction');
for(const name of ['retireCardNode','clearCardPlaceholders','preserveCardViewport'])assert(new RegExp('export function '+name+'\\(').test(helper),'Required reviewed helper '+name);
assert.equal(ts.createSourceFile('bot.js',code,99,true,ts.ScriptKind.JS).parseDiagnostics.length,0);
const bundle='performance-20261017/bot-reading-'+sha(code).slice(0,16)+'.js',files=new Map([[module,helper],[bundle,code]]);
for(const entry of ['robot-push/index.html','pwa-index.html']){const html=fs.readFileSync(path.join(baseline,entry),'utf8'),before='/radar/'+original;assert.equal(html.split(before).length-1,1,entry);files.set(entry,html.replace(before,'/radar/'+bundle));}
const sourceNames=['web/robot-push/mobile-scroll.js','web/robot-push/mobile-scroll.test.mjs','web/robot-push/page.js','web/robot-push/basispulse.js','scripts/prepare-mobile-reading.mjs','scripts/verify-mobile-reading.mjs','scripts/deploy-mobile-reading.py'];
const git=(args,options={})=>execFileSync('git',['-c','safe.directory='+path.resolve('.').replaceAll('\\','/'),...args],options),sourceFiles={};let sourceCommitted=true;
for(const n of sourceNames){sourceFiles[n]=sha(fs.readFileSync(n,'utf8').replaceAll('\r\n','\n'));try{if(sourceFiles[n]!==sha(git(['show','HEAD:'+n],{stdio:['ignore','pipe','ignore']}).toString().replaceAll('\r\n','\n')))sourceCommitted=false;}catch{sourceCommitted=false;}}
const plan={schema:1,kind:'mobile-reading-static',sourceCommit:git(['rev-parse','HEAD'],{encoding:'utf8'}).trim(),sourceCommitted,sourceFiles,sourceRelease:base.release,baselineHash:sha(baselineRaw),inventoryHash:sha(inventoryRaw),original,oldModule,bundle,module,changes:edits.map(e=>({label:e.label,beforeSha:sha(e.before),afterSha:sha(e.after)})),files:{}};
fs.mkdirSync(out,{recursive:true});for(const[n,c]of files){const p=path.join(out,n);fs.mkdirSync(path.dirname(p),{recursive:true});fs.writeFileSync(p,c);plan.files[n]={sha256:sha(c),bytes:Buffer.byteLength(c)};}
fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify(plan,null,2));fs.writeFileSync(path.join(out,'baseline.json'),baselineRaw);fs.writeFileSync(path.join(out,'all-files.json'),inventoryRaw);fs.writeFileSync(path.join(out,'patches.json'),JSON.stringify(edits,null,2));fs.copyFileSync('scripts/deploy-mobile-reading.py',path.join(out,'deploy-mobile-reading.py'));
console.log(JSON.stringify({bundle,module,files:files.size,patches:edits.length,sourceCommitted}));
