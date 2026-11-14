import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const manifest=JSON.parse(await readFile(new URL('./manifest.webmanifest',import.meta.url),'utf8'));
const origin='https://leida.shenmiren.work';
const scope=new URL(manifest.scope,origin);
const within=path=>{const u=new URL(path,origin);return u.origin===scope.origin&&u.pathname.startsWith(scope.pathname);};
test('keep existing installed app and notification identity',()=>{
 assert.equal(manifest.id,'/radar/push-test/');assert.equal(manifest.start_url,'/radar/push-test/');assert.equal(manifest.display,'standalone');
});
test('all seven radar navigation destinations stay inside the app',()=>{
 for(const path of ['/radar/?tab=market','/radar/?tab=FF&mode=FF','/radar/?panel=transfer','/radar/position-limits/','/radar/robot-push/','/radar/robot-push/settings/','/radar/robot-push/alarms/','/radar/push-center/','/radar/push-test/'])assert(within(path),path);
});
test('other sites and unrelated paths remain outside the app',()=>{
 for(const path of ['https://basispulse.yielding.pro/trader','https://github.com/','/','/radar-other/'])assert(!within(path),path);
});
