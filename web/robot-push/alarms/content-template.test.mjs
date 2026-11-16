import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {DEFAULT_TEMPLATE,contentDraft} from './content-template.js';
test('first open and clearing show the complete editable default, without frozen quotes',()=>{
  assert.equal(contentDraft({}),DEFAULT_TEMPLATE);
  assert.equal(contentDraft({alarmContentMode:'template',alarmContent:''}),DEFAULT_TEMPLATE);
  for(const field of ['行情来源','触发价格','触发原因','时间']) assert.ok(DEFAULT_TEMPLATE.includes('{{'+field+'}}'));
});
test('legacy text and notes survive, saved templates reopen verbatim',()=>{
  assert.equal(contentDraft({alarmContent:'检查仓位',note:'备注'}),'检查仓位\n\n'+DEFAULT_TEMPLATE+'\n{{备注}}');
  const text='我的提醒\n'+DEFAULT_TEMPLATE;
  assert.equal(contentDraft({alarmContent:text,alarmContentMode:'template'}),text);
  assert.ok(contentDraft({alarmContent:'a'.repeat(1000)}).length<2000);
});
test('editor fills a value and saves the explicit template format',()=>{
  const app=readFileSync(new URL('./app.js',import.meta.url),'utf8');
  assert.ok(app.includes("$('#alarm-content').value=contentDraft(rule)"));
  assert.ok(app.includes("alarmContentMode:'template'"));
});
