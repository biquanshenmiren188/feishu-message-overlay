// Bounded incremental patch of the audited live graph; keep summary/clipboard overlays.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
const [baselineDir,outDir,esbuildPath]=process.argv.slice(2);
const {transform}=await import(pathToFileURL(path.resolve(esbuildPath)));
const {default:ts}=await import(pathToFileURL(path.resolve(path.dirname(esbuildPath),'../../typescript/lib/typescript.js')));
const baseline=JSON.parse(await fs.readFile(path.join(baselineDir,'manifest.json'),'utf8'));
const sourceCommit=execFileSync('git',['rev-parse','HEAD'],{cwd:new URL('.',import.meta.url),encoding:'utf8'}).trim();
const html=await fs.readFile(path.join(baselineDir,'robot-push/index.html'),'utf8');
const asset=html.match(/src="\/radar\/([^\"]+\/bot-[^\"]+\.js)"/)[1];
const sha=s=>crypto.createHash('sha256').update(s).digest('hex');
let js=await fs.readFile(path.join(baselineDir,asset),'utf8');
// This mapping is valid only for the inspected pre-native-history bundle.
if(sha(js)!=='a268e9d1a6990dd52d28681377966b848bf39e66d55f5f5d5299d16ed6a4a3ec'||sha(js)!==baseline.files[asset]?.sha256)throw Error('Inspect and remap changed production bundle');
const source=await fs.readFile(new URL('./page.js',import.meta.url),'utf8');
const sourceTree=ts.createSourceFile('page.js',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);
const names={fitKey:'ct',stablePaneBottom:'__radarBottom',seekProgress:'yt',card:'lt',render:'q',schedule:'L',accept:'fn',manual:'ke',edgeMove:'Zn',touchRest:'mn',updateLatest:'oe',progressGeometry:'mt',updateProgress:'ge',fitCards:'qe',mobile:'P',reader:'d',board:'o',feed:'Y',pin:'H',store:'N',lastWindowKey:'Ie',lastPinKey:'Oe',status:'Ke',guardScroll:'G',firstVisible:'R',touchActive:'O',touchSettling:'j',detailOpen:'z',deferredRefresh:'Te',mobileScrollGate:'__radarScroll',timer:'se',manualHeld:'ee',railDrag:'re',initialPositionPending:'dt',initialScrollToken:'ut',alertNew:'Xn',newCount:'cn',touchQuiet:'Pe',pendingTouchStep:'fe',moveWindow:'pt',lastTop:'te',historyRail:'k',historyThumb:'Ce',railQuiet:'ln',$:'y'};
const functions=['status','fitCards','seekProgress','render','schedule','accept','manual','edgeMove','touchRest','updateLatest','progressGeometry','updateProgress'];
for(const name of functions){
 const found=sourceTree.statements.filter(n=>ts.isFunctionDeclaration(n)&&n.name?.text===name);if(found.length!==1)throw Error('Source function changed: '+name);
 const result=ts.transform(found[0],[context=>{const visit=node=>{
  // Rename bindings/references, never property keys such as reader.manual.
  if(ts.isIdentifier(node)&&names[node.text]&&!(ts.isPropertyAccessExpression(node.parent)&&node.parent.name===node)&&!(ts.isPropertyAssignment(node.parent)&&node.parent.name===node))return ts.factory.createIdentifier(names[node.text]);
  return ts.visitEachChild(node,visit,context);
 };return node=>ts.visitNode(node,visit);}]);
 const replacement=(await transform(ts.createPrinter().printNode(ts.EmitHint.Unspecified,result.transformed[0],sourceTree),{minifyWhitespace:true,charset:'ascii',target:['safari16','chrome109']})).code.trim();result.dispose();
 const tree=ts.createSourceFile('live.js',js,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS),matches=tree.statements.filter(n=>ts.isFunctionDeclaration(n)&&n.name?.text===names[name]);
 if(matches.length!==1)throw Error('Live function changed: '+name);const node=matches[0];js=js.slice(0,node.getStart(tree))+replacement+js.slice(node.end);
}
function replace(before,after){if(js.split(before).length!==2)throw Error('Unexpected live fragment: '+before);js=js.replace(before,after);}
replace('f>n+3e4||n-f>18e5||this.seen.has(l.id)', 'f>n+3e4||this.seen.has(l.id)');
replace('.slice(-100);for(let[c,l]of this.seen)', '.slice(-30);for(let[c,l]of this.seen)');
replace('this.seen.size>200', 'this.seen.size>60');
replace('!ht&&Math.abs(e)>.5&&(P.matches||O||j||ee)', '!ht&&Math.abs(e)>.5');
replace('o.addEventListener("touchmove",e=>{if(P.matches)return;', 'o.addEventListener("touchmove",e=>{return;');
replace('(e.key.startsWith("Page")?d.capacity:1)/Math.max(1,t.domain)', '(e.key.startsWith("Page")?o.clientHeight*.8:60)/Math.max(1,t.overflow)');
if(!js.includes('__radarScroll.defer')||!js.includes('dexSpread'))throw Error('Existing overlays missing');
const jsName=`performance-20261017/bot-summary-${sha(js).slice(0,12)}.js`;
const entry=html.replace('/radar/'+asset,'/radar/'+jsName).replace('本页面保留最近100条普通消息','保留最近30条普通消息').replace('刷新后重新载入','按接收顺序保留');
const files={[jsName]:js,'robot-push/index.html':entry};
await fs.mkdir(outDir,{recursive:true});
for(const [name,text] of Object.entries(files)){const dest=path.join(outDir,name);await fs.mkdir(path.dirname(dest),{recursive:true});await fs.writeFile(dest,text);}
await fs.writeFile(path.join(outDir,'manifest.json'),JSON.stringify({sourceCommit,sourceRelease:baseline.release,originalSha256:sha(await fs.readFile(path.join(baselineDir,asset))),sourceHashes:{},layoutVersion:'full-history-20261018',files:Object.fromEntries(Object.entries(files).map(([n,s])=>[n,{sha256:sha(s),bytes:Buffer.byteLength(s)}]))},null,2));
// Private synthetic replay only. Never include it in the deployment manifest.
const replay=path.join(outDir,'replay','radar');await fs.cp(baselineDir,replay,{recursive:true});
for(const [name,text] of Object.entries(files)){const dest=path.join(replay,name);await fs.mkdir(path.dirname(dest),{recursive:true});await fs.writeFile(dest,text);}
const tree=ts.createSourceFile('live.js',js,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS),demo=tree.statements.filter(n=>ts.isFunctionDeclaration(n)&&n.getText(tree).includes('fictional-'));
if(demo.length!==1)throw Error('Demo function changed');const node=demo[0];
const sample=Array.from({length:100},(_,i)=>({id:'swipe-'+i,groupId:'synthetic',senderType:'bot',title:`TOKEN${i}｜FF｜V2收敛｜R0 +0.30%`,body:`买 Binance 永续 → 卖 Aster 永续\n盘口差+0.3759%\n警告：合成测试警告，检查长消息和连续滚动`,actions:[]}));
const fixture=js.slice(0,node.getStart(tree))+`function ${node.name.text}(){const messages=${JSON.stringify(sample)};messages.forEach((m,i)=>m.sentAt=new Date(Date.now()-(messages.length-i)*10000).toISOString());return{messages,pinned:null}}`+js.slice(node.end);
await fs.writeFile(path.join(replay,jsName),fixture);console.log(JSON.stringify({files:Object.keys(files),replay:path.resolve(replay)}));
