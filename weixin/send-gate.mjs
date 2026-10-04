// No payload, credential, storage or transport access. Uncertain sends never retry.
export class SendGate {
  paused=false;
  failed(){this.paused=true;}
  verifiedEcho(){this.paused=false;}
  canSend(){return !this.paused;}
}
export function safeSendError(error){
  const message=String(error?.message??'');const result={};
  for(const key of ['ret','errcode']){const found=message.match(new RegExp('\\b'+key+'=(-?\\d+)'));if(found)result[key]=Number(found[1]);}
  const http=message.match(/\bHTTP\s+(\d{3})/);if(http)result.httpStatus=Number(http[1]);
  // Only fixed known categories: never emit arbitrary upstream errmsg or payload.
  result.category=/rate limited/i.test(message)?'RATE_LIMITED':/prepare failed/i.test(message)?'PREPARE_FAILED':'UNCLASSIFIED';
  return result;
}
