/* Unread images show their scan state, then become editable without navigation. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('review_sheet.js','utf8'),elements={};
function element(){return {textContent:'',children:[],dataset:{},scrollTop:0,scrollLeft:0,
 classList:{toggle(name,value){this[name]=value;},add(name){this[name]=true;},remove(name){this[name]=false;}},
 append(...items){this.children.push(...items);},replaceChildren(){this.children=[];},setAttribute(){},
 insertRow(){const row=element();this.append(row);return row;},createTHead(){return this.insertRow();},createTBody(){return this.insertRow();}};}
const el=id=>elements[id]??=element();
const pages=[1,2,3].map(number=>({number,file:`page-${number}.png`,name:`AQ${number}.jpg`,records:0,shared:0,status:'waiting'}));
const sandbox={state:{id:'job',status:'scanning',pages,image_navigation:pages,image_filter:null,records:[],record_total:0,
 ready_record_total:0,completed_pages:0,review_allowed:true,review_revision:1,scan_stats:{stage:'queued'}},
 rows:[],scanDisplay:null,$:el,document:{createElement:element},names:{},drawImageNavigation(){},paintRecordPager(){},
 unsure:()=>true,projectRow:i=>i+1,hasRecordPage:()=>false,drawCoverage(){},paintScan(){},
 active:null,busy:false,dirty:false,cropPicker:{hasDraft:()=>false},loadEpoch:0,previewCell:null,
 workspaceURL:()=>'/workspace',api:async()=>{throw Error('Unexpected request');}};
vm.createContext(sandbox);
function include(name){
 const start=source.search(new RegExp('^function '+name+'\\(','m')),end=source.indexOf('\n}',start)+2;
 assert(start>=0&&end>start,name);vm.runInContext(source.slice(start,end),sandbox);
}
for(const name of ['reviewAvailability','imageReviewPhase','emptyReviewStatus','paintReviewState','paintImageStatuses','drawSheet'])include(name);
const syncStart=source.indexOf('let refreshSequence=0;'),syncEnd=source.indexOf('\nasync function saveCharacter',syncStart);
vm.runInContext(source.slice(syncStart,syncEnd),sandbox);
function noGrid(title){
 sandbox.drawSheet();assert.equal(el('sheetContent').classList.hidden,true);
 assert.equal(el('sheetStatus').classList.hidden,false);assert.equal(el('sheet').children.length,0,'No column headers before records arrive');
 assert.equal(el('reviewNext').classList.hidden,true);assert.match(el('sheetStatusTitle').textContent,title);
}
(async()=>{
 noGrid(/Waiting for the scanner/);assert.equal(el('export').disabled,true);
 sandbox.state.scan_stats={stage:'loading'};noGrid(/Preparing the local scanner/);
 sandbox.state.scan_stats={stage:'reading',page:1};noGrid(/Scanning image 1 of 3/);
 // A future image stays queued even though another image is actively scanning.
 sandbox.state.image_filter=pages[2].file;noGrid(/Waiting to scan image 3/);
 sandbox.state.image_filter=pages[1].file;sandbox.state.completed_pages=1;sandbox.state.ready_record_total=1;
 pages[0].status='ready';pages[0].records=1;sandbox.state.scan_stats.page=2;
 noGrid(/Scanning image 2 of 3/);assert.equal(el('reviewAvailable').classList.hidden,false);
 assert.equal(el('export').disabled,false,'Existing project records remain exportable while viewing an unread image');
 // Live progress can precede the workspace checkpoint or come from another job.
 sandbox.scanDisplay={id:'other-job',status:'ready'};noGrid(/Scanning image 2 of 3/);
 sandbox.scanDisplay={id:'job',status:'scanning',scan_stats:{stage:'reading',page:3,completed_pages:2}};
 noGrid(/Preparing the spreadsheet/);
 const badge=element();el('imageList').children=[{dataset:{file:pages[2].file},querySelector:()=>badge}];
 sandbox.paintImageStatuses();assert.match(badge.textContent,/Scanning/);
 // The ordinary background refresh fills the selected image, with no reload.
 const selectedFile=sandbox.state.image_filter;
 sandbox.api=async()=>({state:{...sandbox.state,records:[{source_images:[selectedFile]}],record_total:1,review_revision:2,
 completed_pages:2,image_navigation:pages.map(p=>({...p,status:p.number<=2?'ready':'scanning'}))},
 rows:[{cells:[{status:'uncertain',value:'[i/t]',pending:1,sources:[]}]}]});
 assert.equal(await sandbox.sync(true),true);assert.equal(sandbox.state.image_filter,selectedFile);
 assert.equal(el('sheetContent').classList.hidden,false);assert.equal(el('sheetStatus').classList.hidden,true);
 assert.equal(el('sheet').children[0].children[0].children.length,37);assert.equal(el('sheet').children[1].children.length,1);
 assert.equal(el('reviewNext').classList.hidden,false);
 // Moving from a populated sheet to an unread image clears the old cells.
 sandbox.rows=[];sandbox.state.image_filter=pages[2].file;sandbox.scanDisplay=null;
 sandbox.state.scan_stats={stage:'reading',page:3};noGrid(/Scanning image 3 of 3/);
 // Completed empty pages and continuation-only pages must not spin forever.
 sandbox.state.image_navigation[2].status='continuation';noGrid(/Waiting for a continued record/);
 sandbox.state.image_navigation[2].status='ready';noGrid(/No records detected/);
 sandbox.state.image_navigation[2].status='waiting';sandbox.state.status='cancelled';noGrid(/No results available/);
 assert.equal(el('sheetStatusBadge').textContent,'Scan cancelled');
 sandbox.state.status='error';noGrid(/No results available/);assert.equal(el('sheetStatusBadge').textContent,'Scan stopped');
 console.log('Loading review UI passed: first-image gating, queued/scanning images, live status, automatic sheet handoff, export access, and terminal/empty/continuation states.');
})().catch(error=>{console.error(error);process.exitCode=1;});
