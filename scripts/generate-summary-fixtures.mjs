// Reuse the web regression inputs as an independent desktop parity oracle.
import fs from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {mobileSummary} from '../web/robot-push/summary.mjs';
const cases=[];let name='';
const source=(await fs.readFile(new URL('../web/robot-push/summary.test.mjs',import.meta.url),'utf8')).replace(/^import .*;\r?\n/gm,'');
vm.runInNewContext(source,{test:(title,body)=>{name=title;body();},assert,mobileSummary:message=>{
 const result=mobileSummary(message);const {title,signals,spread,risk,warning}=result;
 cases.push({name,input:message,expected:{title,signals,spread,risk,warning}});return result;
}});
await fs.writeFile(new URL('../tests/Overlay.Core.Tests/summary-fixtures.json',import.meta.url),JSON.stringify(cases,null,2)+'\n');
console.log(`${cases.length} web summary fixtures generated`);
