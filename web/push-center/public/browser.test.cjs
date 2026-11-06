// All accounts, devices and messages are synthetic. No real endpoint is contacted.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(process.env.RADAR_TASK_ROOT||'C:/Users/Admin/Documents/Codex/2026-11-06/bark');
const origin='https://radar-center.test',candidate=path.join(root,'work/center-candidate/static');
const settings={notify_enabled:true,rows:4,notify_interval_seconds:60,min_percent:null,excluded_ranks:[],excluded_coins:[],excluded_modes:[],excluded_exchanges:[]};
const token=id=>'synthetic_token_'+id+'_123456789';
const init=(name,code)=>({profileId:code,name,pushCode:code,revision:0,history:[],desktop:{available:true,connected:false},phone:{subscribed:true,enabled:true},bark:{available:true,revision:0,device:null,enabled:true}});
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{for(const width of [1440,393,320]){
  const context=await browser.newContext({viewport:{width,height:852}}),page=await context.newPage(),errors=[],writes=[];
  const states={a:init('主推送码','12345678'),b:init('观察方案','24681357'),c:init('我的推送码','36901234')};let failNext=false,delay=null,releaseInitial;const initialGate=new Promise(r=>releaseInitial=r);let initial=true;
  page.on('pageerror',e=>errors.push(e.message));
  await context.addInitScript(auth=>localStorage.setItem('radar-settings-token',auth),token('a'));
  await context.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname;
   if(url.origin!==origin)return route.abort();
   const id=req.headers().authorization?.includes('_b_')?'b':req.headers().authorization?.includes('_c_')?'c':'a',s=states[id];
   const json=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
   if(p.startsWith('/radar/push-center-api/')){
    const kind=p.split('/').at(-1),b=req.postData()?req.postDataJSON():null;
    if(kind==='state'){const snapshot=JSON.parse(JSON.stringify(s));if(delay){const d=delay;delay=null;await d;}return json(snapshot);}
    if(kind==='pair')return b.code==='bad'?json({error:'码无效'},400):json({token:token(b.code==='12345678'?'a':'b')});
    if(kind==='create-code')return json({token:token('c'),pushCode:states.c.pushCode});
    writes.push({id,kind,body:b});if(failNext){failNext=false;return route.abort('failed');}
    if(kind==='rename'){if(b.revision!==s.revision)return json({error:'名称已修改'},409);s.name=b.name;s.revision++;s.history.push({at:Date.now()/1000,action:'修改推送码名称'});return json(s);}
    if(kind==='bark'){if(b.revision!==s.bark.revision)return json({error:'设备已修改'},409);if(b.action==='bind')s.bark.device={label:b.label};if(b.action==='unbind')s.bark.device=null;s.bark.revision++;return json({ok:true});}
    return json({ok:true});
   }
   if(p.startsWith('/radar/push-test/api/')){
    const kind=p.split('/').at(-1);
    if(kind==='status'&&initial)await initialGate;if(kind==='status')return json({profileId:s.profileId,revision:0,settings,subscribed:true,source:{connected:true},publicKey:'synthetic'});
    if(kind==='binding')return json({pushCode:s.pushCode});
    if(kind==='desktop-settings')return json({revision:0,connected:false,desktop:{action:'mute',settings,rules:{mute:settings,hide:settings}},cards:{action:'hide',settings},history:[]});
    return json({});
   }
   let relative=p.replace(/^\/radar\//,'');if(p.endsWith('/'))relative+='index.html';
   const paths=[path.join(candidate,relative),path.join(root,'work/push/web',relative.startsWith('push-center/')?relative.replace('push-center/','push-center/public/'):relative),path.join(root,'work/radar/public',relative),path.join(root,'work/baseline',path.basename(relative))];
   for(const file of paths){try{const body=await fs.readFile(file);return route.fulfill({contentType:({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'})[path.extname(file)]||'text/plain',body});}catch{}}
   return route.fulfill({status:404,body:''});
  });
  await page.goto(origin+'/radar/push-center/',{waitUntil:'domcontentloaded'});await page.locator('.ra-entry-status').waitFor();assert.equal(await page.locator('.ra-entry-status').innerText(),'已连接');initial=false;releaseInitial();await page.waitForFunction(()=>document.querySelector('#pc-code').textContent==='12345678');
  assert.equal(await page.locator('nav.site-nav a').allTextContents().then(x=>x.join(',')),'全市场费率,机会筛选,充提查询,HY限额查询,BOT,消息设置,报警设置');
  async function fits(){assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'horizontal overflow '+width);const bad=await page.evaluate(()=>[...document.querySelectorAll('dialog[open] button,dialog[open] input')].filter(e=>e.getClientRects().length).some(e=>{const r=e.getBoundingClientRect();return r.left<0||r.right>innerWidth;}));assert.equal(bad,false,'dialog overflow '+width);}
  assert.equal(await page.locator('nav.site-nav [aria-current=page]').count(),0,'center must not select BOT');await fits();await fs.mkdir(path.join(root,'outputs/push-center'),{recursive:true});await page.screenshot({path:path.join(root,`outputs/push-center/center-${width}.png`),fullPage:true});
  // A refresh started before saving must not overwrite the confirmed new revision.
  let releaseOld;delay=new Promise(r=>releaseOld=r);await page.click('#pc-refresh');await page.waitForTimeout(80);
  await page.click('#pc-rename');await page.fill('[name=name]','测试主方案');await page.click('#pc-submit');await page.waitForFunction(()=>!document.querySelector('#pc-editor').open);assert.equal(states.a.name,'测试主方案');assert.equal(states.b.name,'观察方案');
  releaseOld();await page.waitForTimeout(100);assert.equal(await page.locator('#pc-name').innerText(),'测试主方案','late refresh must not roll back saved name');
  await page.click('#pc-bark-manage');await page.fill('[name=label]','测试 iPhone');await page.fill('[name=key]','synthetic_bark_key');await fits();
  failNext=true;await page.click('#pc-submit');await page.waitForFunction(()=>document.querySelector('#pc-submit').textContent==='重试原操作');await page.click('#pc-submit');await page.waitForFunction(()=>!document.querySelector('#pc-editor').open);assert.deepEqual(writes.at(-1),writes.at(-2));assert.equal(states.a.bark.device.label,'测试 iPhone');
  await page.click('#pc-switch');await page.fill('[name=code]','24681357');await page.click('#pc-submit');await page.waitForFunction(()=>document.querySelector('#pc-code').textContent==='24681357');assert.equal(await page.locator('#pc-bark-status').innerText(),'待绑定');assert.equal(states.a.bark.device.label,'测试 iPhone');
  // Old in-flight state cannot repaint a newly selected identity.
  let release;delay=new Promise(r=>release=r);await page.click('#pc-refresh');await page.waitForTimeout(80);await page.click('#pc-switch');await page.fill('[name=code]','12345678');await page.click('#pc-submit');await page.waitForFunction(()=>document.querySelector('#pc-code').textContent==='12345678');release();await page.waitForTimeout(100);assert.equal(await page.locator('#pc-code').innerText(),'12345678');
  await page.click('#pc-tab-business');assert.equal(await page.locator('#pc-business').isVisible(),true);await page.click('#pc-tab-history');assert.match(await page.locator('#pc-history-list').innerText(),/修改/);
  await page.locator('.radar-account-entry').click();await page.waitForFunction(()=>document.querySelector('#pc-code')?.textContent==='12345678');assert.equal(await page.locator('#radar-account-dialog').evaluate(e=>e.open),false);await page.click('#pc-phone-manage');await fits();assert.equal(await page.locator('#ns-bound-code').innerText(),'12345678');assert.match(await page.locator('#ra-center-link').getAttribute('href'),/center/);await page.click('.ra-close');
  await page.click('#pc-create');await page.click('#pc-submit');await page.waitForFunction(()=>document.querySelector('#pc-code').textContent==='36901234');assert.equal(states.a.name,'测试主方案');
  assert.equal(writes.some(x=>x.kind==='verify-phone'||x.body.action==='test'),false,'no automatic real-world sends');
  assert.deepEqual(errors,[]);console.log(JSON.stringify({width,passed:true,writes:writes.length}));await context.close();
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
