import assert from 'node:assert/strict';
import {SendGate,safeSendError} from './send-gate.mjs';
const gate=new SendGate();assert.equal(gate.canSend(),true);
gate.failed();for(let n=0;n<100;n++)assert.equal(gate.canSend(),false);
gate.verifiedEcho();assert.equal(gate.canSend(),true);gate.failed();assert.equal(gate.canSend(),false);
assert.deepEqual(safeSendError(Error('ret=-2 errcode=0 errmsg=rate limited')),{ret:-2,errcode:0,category:'RATE_LIMITED'});
assert.deepEqual(safeSendError(Error('HTTP 503 ret=-2 prepare failed')),{ret:-2,httpStatus:503,category:'PREPARE_FAILED'});
assert.deepEqual(safeSendError(Error('private payload must never escape')),{category:'UNCLASSIFIED'});
console.log(JSON.stringify({passed:true,requests:0,pausedUntilVerifiedEcho:true,rawErrorsExcluded:true}));
