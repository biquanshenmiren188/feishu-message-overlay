import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {DEFAULT_TEMPLATE} from './content-template.js';
import {previewContext,renderPreviewBody} from './content-preview.js';

const rule={exchange:'binance',market:'future',symbol:'1000PEPEUSDT',priceType:'last',condition:'below',target:'0.004',repeat:true,note:'检查仓位',state:{asset:{pair:'1000PEPE/USDT'},price:'0.0039',status:'alarming',source:{exchange:'okx',market:'spot',symbol:'PEPE-USDT',priceType:'last',fallback:true,conversionFactor:'1000',targetUnit:'1000PEPE'}}};
test('preview uses routed source and converted price, never multiplies twice',()=>{
 const c=previewContext(rule,{fresh:true,now:Date.UTC(2026,10,14,4,19,36)});
 assert.equal(c.title,'1000PEPE/USDT 跌到 0.004');
 assert.equal(c.values['触发价格'],'0.0039');
 assert.equal(c.values['时间'],'11-14 12:19:36');
 assert.ok(c.values['行情来源'].includes('备用行情：OKX'));
 assert.ok(c.values['行情来源'].includes('×1000'));
 const body=renderPreviewBody(DEFAULT_TEMPLATE,rule,c.values);
 assert.ok(body.includes('触发价格：0.0039 USDT'));assert.ok(body.includes('每 30 秒提醒'));assert.ok(!body.includes('{{'));
});
test('unavailable quote uses clearly labelled target example instead of stale data',()=>{
 const c=previewContext(rule,{fresh:false});
 assert.equal(c.values['触发价格'],'0.004');assert.ok(c.caption.includes('按设定价示例'));
 assert.ok(c.values['行情来源'].startsWith('BINANCE'));assert.ok(!c.values['行情来源'].includes('备用'));
 assert.throws(()=>renderPreviewBody('{{拼错字段}}',rule,c.values),/无法识别/);
});
test('preview body matches deployed Python sender rendering across drafts',()=>{
 const values=previewContext(rule,{fresh:true,now:Date.UTC(2026,10,14,4,19,36)}).values;
 const cases=['',DEFAULT_TEMPLATE,'检查风险\n'+DEFAULT_TEMPLATE,'仅提醒自己', '{{币种}} {{触发条件}}\n价格 {{触发价格}}', '<b>纯文本</b>\n{{备注}}',DEFAULT_TEMPLATE+'\n{{备注}}'].map(text=>({rule:{...rule,alarmContentMode:'template',alarmContent:text.trim()},values,text}));
 const script='import json,sys;from content import render_content;print(json.dumps([render_content(c["rule"],c["values"]) for c in json.load(sys.stdin.buffer)],ensure_ascii=True))';
 const python=spawnSync('python',['-c',script],{cwd:fileURLToPath(new URL('../../alarms/',import.meta.url)),input:JSON.stringify(cases),encoding:'utf8'});
 assert.equal(python.status,0,python.stderr);
 assert.deepEqual(cases.map(c=>renderPreviewBody(c.text,c.rule,c.values)),JSON.parse(python.stdout));
});
