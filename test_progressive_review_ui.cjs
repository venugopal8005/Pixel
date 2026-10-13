/* Live scan publication must never replace an open editor or a newer save. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('review_sheet.js','utf8'),elements={},calls=[];
const el=id=>elements[id]??={textContent:'',scrollTop:240,scrollLeft:960,classList:{add(n){this[n]=true;},remove(n){this[n]=false;}}};
const initial={id:'job',status:'scanning',record_offset:50,image_filter:'page-1.png',review_revision:1};
const sandbox={state:initial,active:null,busy:false,dirty:false,cropPicker:{hasDraft:()=>false},previewCell:null,rows:[],loadEpoch:0,scanDisplay:null,
 $:el,workspaceURL:(...args)=>JSON.stringify(args),drawSheet(){calls.push('draw');},drawCoverage(){},paintScan(){},
 api:async url=>{calls.push(url);return {state:{...initial,review_revision:2,review_allowed:true},rows:[{key:'new'}]};}};
vm.createContext(sandbox);
const start=source.indexOf('let refreshSequence=0;'),end=source.indexOf('\nasync function saveCharacter',start);
vm.runInContext(source.slice(start,end),sandbox);
(async()=>{
 sandbox.active={row:0,field:6};assert.equal(await sandbox.sync(true),false);assert.equal(calls.length,0);
 sandbox.active=null;sandbox.dirty=true;assert.equal(await sandbox.sync(true),false);
 sandbox.dirty=false;sandbox.cropPicker.hasDraft=()=>true;assert.equal(await sandbox.sync(true),false);
 sandbox.cropPicker.hasDraft=()=>false;assert(await sandbox.sync(true));
 assert.equal(calls[0],JSON.stringify(['job',50,'page-1.png']));assert.equal(sandbox.state.review_revision,2);
 assert.equal(el('sheetWrap').scrollTop,240);assert.equal(el('sheetWrap').scrollLeft,960);
 assert.equal(el('newResults').classList.hidden,true);
 // User opens the editor while the background workspace request is in flight.
 let finish;sandbox.api=()=>new Promise(resolve=>finish=resolve);
 const waiting=sandbox.sync(true);sandbox.active={row:0,field:6};
 finish({state:{...initial,review_revision:3},rows:[]});assert.equal(await waiting,false);assert.equal(sandbox.state.review_revision,2);
 // User saves a correction: that explicit refresh is allowed with the editor open.
 sandbox.busy=true;sandbox.api=async()=>({state:{...initial,review_revision:3},rows:[{key:'saved'}]});
 assert(await sandbox.sync());assert.equal(sandbox.rows[0].key,'saved');assert.match(el('exportStatus').textContent,/Changes saved/);
 // Do not let an older response overwrite a later completed refresh.
 sandbox.active=null;sandbox.busy=false;sandbox.api=()=>new Promise(resolve=>finish=resolve);
 const older=sandbox.sync(true);const finishOlder=finish;
 const newer=sandbox.sync(true);finish({state:{...initial,review_revision:5},rows:[]});assert(await newer);
 finishOlder({state:{...initial,review_revision:4},rows:[]});assert.equal(await older,false);assert.equal(sandbox.state.review_revision,5);
 console.log('Progressive review UI passed: defers open/dirty editors and crop drafts, preserves view and scroll, ignores stale responses, permits explicit save refresh.');
})().catch(e=>{console.error(e);process.exitCode=1;});
