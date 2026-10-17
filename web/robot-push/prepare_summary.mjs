// Patch only the inspected summary function and card presentation.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [baselineDir,outDir,esbuildPath]=process.argv.slice(2);
const {transform}=await import(pathToFileURL(path.resolve(esbuildPath)));
const {default:ts}=await import(pathToFileURL(path.resolve(path.dirname(esbuildPath),'../../typescript/lib/typescript.js')));
const baseline=JSON.parse(await fs.readFile(path.join(baselineDir,'manifest.json'),'utf8'));
const sha=s=>crypto.createHash('sha256').update(s).digest('hex');
const baselineHtml=await fs.readFile(path.join(baselineDir,'robot-push/index.html'),'utf8');
const originalAsset=baselineHtml.match(/src="\/radar\/([^"]+\/bot-[^"]+\.js)"/)[1];
const summaryName='web/robot-push/summary.js';
const original=await fs.readFile(path.join(baselineDir,originalAsset),'utf8');
if(sha(original)!==baseline.files[originalAsset]?.sha256)throw Error('Active bundle changed');
const summary=await fs.readFile(new URL('./summary.js',import.meta.url),'utf8');
const css=await fs.readFile(new URL('./summary-risk.css',import.meta.url),'utf8');
function replaceFunction(code,name,replacement){
 const parsed=ts.createSourceFile('bundle.js',code,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);
 const matches=parsed.statements.filter(n=>ts.isFunctionDeclaration(n)&&n.name?.text===name);
 if(matches.length!==1)throw Error('Expected one function '+name);
 const node=matches[0];return code.slice(0,node.getStart(parsed))+replacement+code.slice(node.end);
}
let js=replaceFunction(original,'Xt',(await transform(summary.replace('export function mobileSummary','function Xt'),{minifyWhitespace:true,minifySyntax:true,charset:'ascii',target:['safari16','chrome109']})).code.trim());
const patches=[];
function replace(before,after){if(js.split(after).length===2)return;if(js.split(before).length!==2)throw Error('Inspect changed bundle: '+before);js=js.replace(before,after);patches.push(before);}
replace('if(i.append(c),!n&&P.matches){','if(i.append(c),!n){');
replace('f.className="mobile-summary";','r.textContent=l.title||r.textContent,f.className="mobile-summary";');
replace('{direction:l.direction,metrics:l.metrics,fees:l.fees,preview:l.preview,risk:l.risk}','{signals:l.signals,risk:l.warning?l.risk:""}');
replace('function an(e,t){if(!P.matches||z)return;','function an(e,t){if(z)return;');
// Retain the concurrently released scroll stability module and its identity.
if(js.includes('from "./mobile-scroll.js"'))replace('from "./mobile-scroll.js"','from "/radar/scroll-stability-20261017/mobile-scroll.js"');
if(!js.includes('__radarScroll.defer'))throw Error('Expected current scroll stability patch');
const jsName=`performance-20261017/bot-summary-${sha(js).slice(0,12)}.js`;
const cssName=`performance-20261017/summary-risk-${sha(css).slice(0,12)}.css`;
let html=baselineHtml;
if(!html.includes('/radar/'+originalAsset))throw Error('Active entry changed');
html=html.replace('/radar/'+originalAsset,'/radar/'+jsName);
if(!html.includes('/radar/'+cssName))html=html.replace(/<link rel="stylesheet" href="\/radar\/performance-20261017\/summary-risk-[^"]+">\s*/g,'').replace('</head>',`<link rel="stylesheet" href="/radar/${cssName}">\n</head>`);
const files={[jsName]:js,'robot-push/index.html':html};
if(baseline.files[cssName]?.sha256!==sha(css))files[cssName]=css;
for(const [name,text] of Object.entries(files)){const p=path.join(outDir,name);await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,text);}
await fs.writeFile(path.join(outDir,'manifest.json'),JSON.stringify({sourceRelease:baseline.release,originalSha256:sha(original),summarySource:summaryName,sourceHashes:{},patches,files:Object.fromEntries(Object.entries(files).map(([n,s])=>[n,{sha256:sha(s),bytes:Buffer.byteLength(s)}]))},null,2));
console.log(JSON.stringify({originalVerified:true,scrollFixPreserved:true,files:Object.keys(files)}));

// Isolated local replay; never publish fixtures or send notifications.
const fixtureDir=path.join(outDir,'replay');
await fs.mkdir(path.join(fixtureDir,'radar'),{recursive:true});
await fs.cp(baselineDir,path.join(fixtureDir,'radar'),{recursive:true});
for(const [name,text] of Object.entries(files)){const p=path.join(fixtureDir,'radar',name);await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,text);}
const messages=[
 {title:'🚨🚨 强信号聚集｜EPIC｜3 组同时 ACTIVE',body:'涉及 4 所 · 已持续 0s\n最近180秒净收益均值最高 +0.28%\nR1｜SF｜买 GATE → 卖 BITGET\n净均 +0.28% · ACTIVE 1s\nR0｜FF｜买 BYBIT → 卖 BITGET\n净均 +0.17% · ACTIVE 59s\nR0｜FF｜买 BYBIT → 卖 BINANCE\n净均 +0.24% · ACTIVE 22s\n⚠ 警告：BITGET EPICUSDT 将下架合约及相关服务 · 10/20 15:00 UTC+8\n官方原文：https://www.bitget.com/en/support/articles/12560603897724\n⚠ 警告：BITGET EPICUSDT 将下架合约及相关服务 · 10/20 15:00 UTC+8\n⚠ 警告：Bybit 4h 成本：资金费计算方式不同'},
 {title:'SPACE｜FF｜V2收敛｜R0 +0.36%',body:'买 OKX 永续 → 卖 Binance 永续\n均值：净收益0.158%｜盘口差+0.333%\nOKX：资费+0.005%\nBinance：资费+0.005%\n最长未知4秒\nOKX：充开提开\nBinance：该平台无现货，暂无充提数据'},
 {title:'EPIC｜SF｜V2收敛｜R0 +0.37%',body:'买 Gate 现货 → 卖 Bitget 永续\n⚠ 警告：BITGET EPICUSDT 将下架合约及相关服务 · 10/20 15:00 UTC+8\n官方原文：https://www.bitget.com/en/support/articles/12560603897724\n180秒：有效179/180｜最长未知1秒\n均值：净收益0.120%｜盘口差+0.316%\nBitget：资费+0.049%\nBitget：该平台无现货，暂无充提数据'},
 {title:'BITGET｜公告风险',body:'BITGET ILY 在 BASE 网络将暂停充值 · 10/17 16:55 UTC+8'},
 {title:'无有效注意项',body:'买 OKX 永续 → 卖 Binance 永续\n注意：没有.暂无'}
].map((m,i)=>({...m,id:'replay-'+i,groupId:'replay',senderType:'bot',sentAt:new Date(Date.UTC(2026,9,17,8,53+i)).toISOString(),actions:[]}));
const parsed=ts.createSourceFile('bundle.js',js,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);
const demoFunctions=parsed.statements.filter(n=>ts.isFunctionDeclaration(n)&&n.getText(parsed).includes('fictional-'));
if(demoFunctions.length!==1)throw Error('Demo function changed');
const demoFunctionName=demoFunctions[0].name.text;
const fixture=replaceFunction(js,demoFunctionName,`function ${demoFunctionName}(){const data=${JSON.stringify({messages,pinned:null})};data.messages.forEach((m,i)=>m.sentAt=new Date(Date.now()-(data.messages.length-i)*60000).toISOString());return data}`);
await fs.writeFile(path.join(fixtureDir,'radar',jsName),fixture);
console.log(JSON.stringify({replay:path.resolve(fixtureDir)}));
