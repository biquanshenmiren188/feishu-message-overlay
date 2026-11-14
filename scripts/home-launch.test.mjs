import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const code=readFileSync(new URL('../web/robot-push/home-launch.js',import.meta.url),'utf8');
function run({path='/radar/push-test/',standalone=true,display=false,largeTouch=true,search='',hash=''}={}) {
 const calls=[];
 vm.runInNewContext(code,{URL,document:{addEventListener(){}},navigator:{standalone},matchMedia:q=>({matches:q.includes('display-mode')?display:largeTouch}),location:{pathname:path,origin:'https://leida.shenmiren.work',search,hash,replace:u=>calls.push(u)}});
 return calls;
}
test('large touch installed legacy entry navigates to the canonical BOT once',()=>assert.deepEqual(run(),['https://leida.shenmiren.work/radar/robot-push/']));
test('canonical destination cannot redirect again',()=>assert.deepEqual(run({path:'/radar/robot-push/'}),[]));
test('legacy entry without slash is supported',()=>assert.equal(run({path:'/radar/push-test'})[0],'https://leida.shenmiren.work/radar/robot-push/'));
test('display-mode fallback identifies an installed app',()=>assert.equal(run({standalone:false,display:true}).length,1));
test('normal browser entry remains unchanged',()=>assert.deepEqual(run({standalone:false}),[]));
test('ordinary phone and desktop input mode stay unchanged',()=>assert.deepEqual(run({largeTouch:false}),[]));
test('settings and other routes remain unchanged',()=>{for(const path of ['/radar/push-test/settings/','/radar/robot-push/alarms/','/radar/'])assert.deepEqual(run({path}),[]);});
test('query and fragment are preserved without changing the destination origin',()=>assert.equal(run({search:'?tab=BOT&next=https%3A%2F%2Fexample.org',hash:'#latest'})[0],'https://leida.shenmiren.work/radar/robot-push/?tab=BOT&next=https%3A%2F%2Fexample.org#latest'));

function click({standalone=true,href='https://leida.shenmiren.work/radar/?combo=test',target='_blank',download=false,...event}={}) {
 let handler;const link={href,target,hasAttribute:()=>download};
 vm.runInNewContext(code,{URL,document:{addEventListener:(type,fn)=>{handler=fn;}},navigator:{standalone},matchMedia:()=>({matches:false}),location:{pathname:'/radar/robot-push/',origin:'https://leida.shenmiren.work',href:'https://leida.shenmiren.work/radar/robot-push/'}});
 handler({button:0,target:{closest:()=>link},...event});return link.target;
}
test('installed internal radar links open in the same app',()=>assert.equal(click(),'_self'));
test('external and lookalike routes retain their targets',()=>{for(const href of ['https://example.org/radar/','https://leida.shenmiren.work/radar-evil/','mailto:test@example.org'])assert.equal(click({href}),'_blank');});
test('ordinary browsers and explicit modified clicks keep original behavior',()=>{for(const opt of [{standalone:false},{ctrlKey:true},{metaKey:true},{shiftKey:true},{altKey:true},{button:1},{defaultPrevented:true},{download:true}])assert.equal(click(opt),'_blank');});
test('existing self links stay self',()=>assert.equal(click({target:'_self'}),'_self'));
