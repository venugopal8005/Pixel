/* Queue feedback must follow live status and ignore replies after navigation. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('review_sheet.js','utf8');
const start=source.indexOf('let scanDisplay=null'),end=source.indexOf('async function loadJob(',start);
const elements={},calls=[];
let now=1_000_000;
function el(id){return elements[id]??={textContent:'',classList:{toggle(name,value){this[name]=value;},add(name){this[name]=true;},remove(name){this[name]=false;}},removeAttribute(name){delete this[name];}};}
const queued={id:'waiting',status:'scanning',progress:'Waiting for the local scanner',scan_stats:{stage:'queued',queued_at:875,page_count:398}};
const jobs=[{id:'waiting',name:'New batch',status:'scanning'},{id:'runner',name:'Running batch',status:'scanning'},{id:'other',name:'Other waiting batch',status:'scanning'}];
const live={runner:{status:'scanning',progress:'Page 54/398',scan_stats:{stage:'reading',page:54}},other:{status:'scanning',scan_stats:{stage:'queued'}}};
const sandbox={cancelAvailable:true,state:{id:'waiting',pages:Array(398),records:[]},URLSearchParams,Date:{now:()=>now},$:el,
 showImageCount(){},paintImageStatuses(){},paintReviewState(){},setInterval(){},api:async url=>{calls.push(url);return url==='/api/jobs'?jobs:live[new URLSearchParams(url.split('?')[1]).get('job')];}};
vm.createContext(sandbox);vm.runInContext(source.slice(start,end),sandbox);
(async()=>{
 sandbox.paintScan(queued);await sandbox.refreshScanQueue('waiting');
 assert.equal(el('scanQueueText').textContent,'Currently scanning: Running batch');
 assert.equal(el('scanQueueDetail').textContent,'Page 54/398');
 assert.equal(el('scanQueueOthers').textContent,'Also waiting: Other waiting batch.');
 assert.equal(el('scanQueueOpen').href,'/?job=runner');
 assert.equal(el('scanElapsed').textContent,'Waiting 2m 05s');
 assert.equal(el('scanBar').classList.hidden,true);
 assert.equal(el('scanMetrics').classList.hidden,true);
 const requests=calls.length;await sandbox.refreshScanQueue('waiting');assert.equal(calls.length,requests,'Do not refetch all projects every progress tick');
 now+=6000;live.runner.progress='Page 55/398';await sandbox.refreshScanQueue('waiting');
 assert.equal(el('scanQueueDetail').textContent,'Page 55/398');
 sandbox.paintScan({id:'waiting',status:'scanning',scan_stats:{stage:'reading',page:1,page_count:398,percent:1,started_at:now/1000}});
 assert.equal(el('scanQueue').classList.hidden,true);assert.equal(el('scanBar').classList.hidden,false);assert.equal(el('scanMetrics').classList.hidden,false);

 // A queued-project lookup must not overwrite a different project after navigation.
 now+=6000;sandbox.paintScan(queued);
 const api=sandbox.api;let finishLookup;
 sandbox.api=async url=>url==='/api/jobs'?await new Promise(resolve=>finishLookup=resolve):api(url);
 const request=sandbox.refreshScanQueue('waiting');
 sandbox.state={id:'new-view',pages:[],records:[]};vm.runInContext('loadEpoch++',sandbox);
 sandbox.paintScan({...queued,id:'new-view'});const message=el('scanQueueText').textContent;
 finishLookup(jobs);await request;assert.equal(el('scanQueueText').textContent,message);
 assert.equal(el('scanQueueOpen').classList.hidden,true);

 // Lost queue metadata does not break the main scan progress display.
 sandbox.state={id:'waiting',pages:[],records:[]};now+=6000;sandbox.api=async()=>{throw Error('Connection unavailable');};
 sandbox.paintScan(queued);await sandbox.refreshScanQueue('waiting');
 assert.match(el('scanQueueText').textContent,/Unable to check/);assert.equal(el('scanQueueOpen').classList.hidden,true);
 console.log('Scan queue UI passed: live blocker and waiting projects, waiting clock, throttling, scan handoff, stale-response protection, and reconnect handling.');
})().catch(error=>{console.error(error);process.exitCode=1;});
