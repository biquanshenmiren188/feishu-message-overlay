import test from 'node:test';import assert from 'node:assert/strict';
import {coinMap,coinChanges} from './card-manager.js';
const settings=()=>({excluded_coins:[],advanced:{coins:[]}});
function fixture(){return {desktop:{desktop:{rules:{hide:settings(),mute:settings()}},cards:{settings:settings()}},mobile:{settings:settings()}};}
test('legacy and advanced scopes combine without erasing enabled rules',()=>{const data=fixture();data.desktop.cards.settings.excluded_coins=['PTB'];data.desktop.cards.settings.advanced.coins=[{coin:'PTB',exchange:'all',enabled:false},{coin:'PTB',exchange:'gate',enabled:true}];const map=coinMap(data,'PTB');assert.equal(map.get('cards|all'),true);assert.equal(map.get('cards|gate'),true);assert.equal(coinMap(data,'MITO').size,0);});
test('exact scope changes retain other channels and handle disabled vs absent',()=>{const before=new Map([['mute|all',true],['cards|gate',false]]);const changes=coinChanges('PTB',before,[{exchange:'all',desktop:null,mute:true,cards:true,mobile:null}]);assert.deepEqual(changes,[{channel:'cards',coin:'PTB',exchange:'gate',before:false,after:null},{channel:'cards',coin:'PTB',exchange:'all',before:null,after:true}]);});
test('duplicate scopes cannot silently replace a row',()=>assert.throws(()=>coinChanges('PTB',new Map(),[{exchange:'all'},{exchange:'all'}]),/重复/));
