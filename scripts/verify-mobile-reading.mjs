// Artifact integrity and surgical-patch verification; browser acceptance is separate.
import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';import assert from 'node:assert/strict';import ts from 'typescript';
const[candidate,baseline,reportPath]=process.argv.slice(2);assert(candidate&&baseline&&reportPath);
const sha=v=>crypto.createHash('sha256').update(v).digest('hex'),plan=JSON.parse(fs.readFileSync(path.join(candidate,'manifest.json'))),base=JSON.parse(fs.readFileSync(path.join(baseline,'manifest.json')));
assert.equal(plan.kind,'mobile-reading-static');assert.equal(plan.baselineHash,sha(fs.readFileSync(path.join(baseline,'manifest.json'))));assert.equal(plan.inventoryHash,sha(fs.readFileSync(path.join(baseline,'all-files.json'))));
for(const[dir,manifest]of [[candidate,plan],[baseline,base]])for(const[n,item]of Object.entries(manifest.files)){const raw=fs.readFileSync(path.join(dir,n));assert.equal(sha(raw),item.sha256,n);assert.equal(raw.length,item.bytes,n);}
assert.deepEqual(Object.keys(plan.files).sort(),[plan.bundle,plan.module,'robot-push/index.html','pwa-index.html'].sort());
const old=fs.readFileSync(path.join(baseline,plan.original),'utf8'),code=fs.readFileSync(path.join(candidate,plan.bundle),'utf8'),edits=JSON.parse(fs.readFileSync(path.join(candidate,'patches.json')));
let restored=code;for(const e of [...edits].reverse()){assert.equal(restored.split(e.after).length-1,1,e.label);restored=restored.replace(e.after,e.before);}assert.equal(restored,old,'All unrelated BOT bytes must remain identical');
function declarations(text){const sf=ts.createSourceFile('module.js',text,99,true,ts.ScriptKind.JS),map=new Map();assert.equal(sf.parseDiagnostics.length,0);for(const n of sf.statements)if(ts.isFunctionDeclaration(n))map.set(n.name.text,n.getText(sf));else if(ts.isVariableStatement(n))for(const d of n.declarationList.declarations)if(ts.isIdentifier(d.name))map.set(d.name.text,d.getText(sf));return map;}
const before=declarations(old),after=declarations(code),changed=[];for(const[n,text]of before)if(after.get(n)!==text)changed.push(n);assert.deepEqual(changed.sort(),['Nt','fn','q','qe']);
for(const n of ['fn','q','qe'])assert(after.get(n).includes('return __radarPreserve(Xe,()=>{'),'Wrap '+n);
assert(after.get('Nt').includes('!__defer&&__radarClearPlaceholders(Xe)'));assert.equal(after.get('Nt').split('__radarRetire(').length-1,2);
assert(after.get('Nt').includes('!__defer&&u.age.textContent!==x'));assert(after.get('Nt').includes('!__defer&&(Ne.textContent='));assert(after.get('Nt').includes(',__cardPolicy.summary(t))'));
assert.equal(fs.readFileSync(path.join(candidate,plan.module),'utf8'),fs.readFileSync('web/robot-push/mobile-scroll.js','utf8').replaceAll('\r\n','\n'));
for(const entry of ['robot-push/index.html','pwa-index.html'])assert.equal(fs.readFileSync(path.join(candidate,entry),'utf8').replace('/radar/'+plan.bundle,'/radar/'+plan.original),fs.readFileSync(path.join(baseline,entry),'utf8'));
const report={schema:1,passed:true,sourceCommit:plan.sourceCommit,files:plan.files,baselineHash:plan.baselineHash,inventoryHash:plan.inventoryHash,changedFunctions:changed,protectedDeclarations:before.size-changed.length,originalFeedRulesPreserved:true,cssAndPwaWorkerUnchanged:true,frontendMainUntouched:true,browserAcceptanceRequired:true,serverPreflightRequired:true};
fs.writeFileSync(reportPath,JSON.stringify(report,null,2));console.log(JSON.stringify({passed:true,changedFunctions:changed,protectedDeclarations:report.protectedDeclarations,report:reportPath}));
