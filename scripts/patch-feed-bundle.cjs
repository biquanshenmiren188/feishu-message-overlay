/* Patch only the inspected reader hooks; preserve every other production byte. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const runtime=path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/lib/transform/babelBundle.js');
const {babelParse,traverse}=require(runtime);
const [baseline,source,target]=process.argv.slice(2);
let code=fs.readFileSync(baseline,'utf8');
assert.equal(crypto.createHash('sha256').update(code).digest('hex'),'02bef2ee68f717ebaa52e4e1e9b63240834263c989741fcf566e110c9694ddc6','Reinspect changed production bundle');
const page=fs.readFileSync(source,'utf8'),ast=babelParse(code,'bundle.js',true),pageAst=babelParse(page,'page.js',true);
const aliases={$:'y',store:'N',reader:'d',board:'o',feed:'Y',pin:'H',newCount:'cn',lastPinKey:'Oe',lastWindowKey:'Ie',detailOpen:'z',touchActive:'O',touchSettling:'j',deferredRefresh:'Te',initialPositionPending:'dt',initialScrollToken:'ut',mobile:'P',mobileScrollGate:'__radarScroll',alertNew:'Xn',render:'q',accept:'fn',firstVisible:'R',guardScroll:'G',fitCards:'qe',status:'Ke',updateLatest:'oe',updateProgress:'ge',schedule:'L',card:'lt',latestFeed:'bn',receiveFeed:'ei',feedPolicy:'__webFeedPolicy',refreshFeedConnection:'wn'};
const changes=[];
for(const name of ['render','accept','receiveFeed']){
 const original=ast.program.body.find(n=>n.type==='FunctionDeclaration'&&n.id.name===aliases[name]);
 const replacement=pageAst.program.body.find(n=>n.type==='FunctionDeclaration'&&n.id.name===name);
 assert(original&&replacement,name);
 let text=page.slice(replacement.start,replacement.end),tree=babelParse(text,'hook.js',true),edits=[];
 const root=tree.program.body[0];edits.push([root.id.start,root.id.end,aliases[name]]);
 traverse(tree,{Identifier(p){
  const key=p.node.name;if(!aliases[key])return;
  const parent=p.parentPath;
  const written=(parent.isAssignmentExpression()&&p.key==='left')||(parent.isUpdateExpression()&&p.key==='argument');
  if(!p.isReferencedIdentifier()&&!written)return;
  const binding=p.scope.getBinding(key);
  if(!binding||binding.path.node===root)edits.push([p.node.start,p.node.end,aliases[key]]);
 }});
 for(const [start,end,value]of edits.sort((a,b)=>b[0]-a[0]))text=text.slice(0,start)+value+text.slice(end);
 changes.push([original.start,original.end,text]);
}
for(const [start,end,text]of changes.sort((a,b)=>b[0]-a[0]))code=code.slice(0,start)+text+code.slice(end);
function once(before,after){assert.equal(code.split(before).length-1,1,before);code=code.replace(before,after);}
once('window.visualViewport?.addEventListener("resize",wt);Jn?', 'window.visualViewport?.addEventListener("resize",wt);__webFeedPolicy=createFeedPolicy(fn,{publicOnly:Jn});Jn?');
once('fn(Zt())','__webFeedPolicy.receive(Zt())');
code='import {createFeedPolicy} from "/radar/robot-push/feed-policy.js?v=20261028-1";\nlet __webFeedPolicy;\n'+code;
// Parse the final production artifact, not just the source module.
babelParse(code,'patched-bundle.js',true);
fs.writeFileSync(target,code);
console.log(JSON.stringify({replacedFunctions:changes.length,sha256:crypto.createHash('sha256').update(code).digest('hex')}));
