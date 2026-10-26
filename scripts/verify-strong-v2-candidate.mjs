import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {execFileSync,spawnSync} from 'node:child_process';

const [baselineArg,candidateArg]=process.argv.slice(2);
assert(baselineArg&&candidateArg,'Usage: node verify-strong-v2-candidate.mjs BASELINE_DIR CANDIDATE_DIR');
const baseline=path.resolve(baselineArg),candidate=path.resolve(candidateArg);
const plan=JSON.parse(fs.readFileSync(path.join(candidate,'strong-v2-plan.json'),'utf8'));
const sha=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const read=(root,name)=>fs.readFileSync(path.join(root,name));
for(const [name,expected] of Object.entries(plan.candidateFiles))assert.equal(sha(read(candidate,name)),expected,'Candidate changed: '+name);
for(const [name,meta] of Object.entries(plan.sourceFiles))assert.equal(sha(read(candidate,plan.sourceArtifacts[name])),meta.sha256,'Source snapshot changed: '+name);
for(const [name,expected] of Object.entries(plan.baseline.staticFiles))assert.equal(sha(read(baseline,'static/'+name)),expected,'Baseline changed: '+name);
assert.equal(sha(read(baseline,'backend/signals.py')),plan.baseline.backendSha256);
assert.equal(sha(read(baseline,'fallback/index.html')),plan.baseline.fallbackSha256);
const old=read(baseline,'static/'+plan.previousBundle).toString('utf8'),next=read(candidate,'static/'+plan.bundle).toString('utf8');
const oldExpression=String.raw`value=(line+`+'`\n`'+String.raw`+(/^净均/u.test(next)?next:"")).match(/净均\s*([+−-]?\d+(?:\.\d+)?%)/u)?.[1]`;
assert.equal(old.split(oldExpression).length,2,'Expected one known production expression');
assert.equal(next,old.replace(oldExpression,()=>plan.summaryExpression),'Unexpected change outside strong-signal expression');
for(const name of ['static/robot-push/index.html','fallback/index.html']){
 const before=read(baseline,name).toString('utf8'),after=read(candidate,name).toString('utf8');
 const from='/radar/'+plan.previousBundle,to='/radar/'+plan.bundle;
 assert.equal(before.split(from).length,2);
 assert.equal(after,before.replace(from,to),'Unexpected HTML change: '+name);
}
assert.deepEqual([...next.matchAll(/\bimport\s*\{[^}]*\}\s*from\s*(["'])(.*?)\1/g)].map(m=>m[2]),[...old.matchAll(/\bimport\s*\{[^}]*\}\s*from\s*(["'])(.*?)\1/g)].map(m=>m[2]),'Imports changed');
// This boundary is from the hash-locked live module. Only Xt is evaluated by
// the summary tests; the document/bootstrap/network code is never executed.
const start=next.indexOf('function Xt(message){'),end=next.indexOf('var Qt=M(()=>{});function Zt(',start);
assert(start>=0&&end>start);
const fn=next.slice(start,end),module='export const mobileSummary='+fn+';';
const url='data:text/javascript;base64,'+Buffer.from(module).toString('base64');
const source=read(candidate,'verification/summary.test.mjs').toString('utf8');
assert.equal(source.split("'./summary.mjs'").length,2);
const test=source.replace("'./summary.mjs'",JSON.stringify(url));
const temporary=path.join(os.tmpdir(),'radar-strong-v2-'+crypto.randomUUID()+'.test.mjs');
let output;
try{fs.writeFileSync(temporary,test);output=execFileSync(process.execPath,['--test',temporary],{encoding:'utf8'});}finally{fs.rmSync(temporary,{force:true});}
const count=Number(output.match(/^# tests (\d+)$/m)?.[1]);assert(count>=28,'Expected the full summary regression suite');assert.match(output,/^# fail 0$/m);
assert.equal(sha(read(candidate,'verification/backend/signals.py')),plan.backendFiles['signals.py'],'Backend tests must use the deployed candidate');
const py=spawnSync(process.env.RADAR_PYTHON||(process.platform==='win32'?'python':'python3'),['-m','unittest','discover','-s',path.join(candidate,'verification/backend'),'-p','*_test.py'],{encoding:'utf8'});
assert.equal(py.status,0,'Candidate backend suite failed: '+py.stdout+py.stderr);
const backendTests=Number((py.stdout+py.stderr).match(/Ran (\d+) tests?/)?.[1]);assert(backendTests>=140,'Expected the full candidate backend suite');
const result={sourceCommit:plan.sourceCommit,hashes:plan.candidateFiles,productionSummaryTests:count,backendTests,
 checks:['raw baseline and candidate hashes','only one expression changed in bundled Xt','live module imports unchanged','BOT/PWA only change bundle URL','entire summary suite runs against the actual candidate production Xt','full Python suite uses the exact staged signals.py']};
fs.writeFileSync(path.join(candidate,'strong-v2-validation.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result));
