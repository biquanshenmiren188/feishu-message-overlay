import {createPushBroker} from './push-broker.js';
import {readPushSnapshot,pushMetrics} from './push-reader.js';
const broker=createPushBroker(readPushSnapshot);
self.onconnect=event=>{
  const port=event.ports[0];
  port.onmessage=({data})=>{if(Array.isArray(data?.channels))broker.update(port,data.channels,message=>port.postMessage({...message,metrics:pushMetrics()}));};
  port.start();port.postMessage({type:'ready'});
};
