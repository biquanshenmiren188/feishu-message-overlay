import {createInterface} from 'node:readline';
const input=createInterface({input:process.stdin});
input.once('line',line=>{
 const config=JSON.parse(line.replace(/^\uFEFF/,''));const mode=config.mode;
 const good=JSON.stringify({kind:'bot_info',appId:'cli_synthetic',code:0,botName:'测试机器人',activateStatus:2,appSecret:'synthetic-only'});
 if(mode==='stall'){setTimeout(()=>process.exit(0),10000);return;}
 if(mode==='crash'){process.stderr.write('synthetic-only');process.exit(7);return;}
 if(mode==='invalid'){process.stdout.write('invalid\n',()=>process.exit(0));return;}
 if(mode==='oversized'){process.stdout.write('x'.repeat(40000)+'\n',()=>process.exit(0));return;}
 if(mode==='chatter')process.stdout.write('SDK chatter\n{\"kind\":17}\n{\"kind\":\"bot_info\",\"appId\":\"cli_synthetic\",\"code\":{}}\n');
 if(mode==='split'){process.stdout.write(good.slice(0,19));setTimeout(()=>process.stdout.write(good.slice(19)+'\n',()=>process.exit(0)),30);return;}
 process.stdout.write('\uFEFF  '+good+'\n',()=>process.exit(0));
});
