const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('review_sheet.js','utf8'),loads=[],elements={};
const el=id=>elements[id]??=( {disabled:false,scrollTop:300,scrollLeft:900,value:'AQ160',textContent:'',classList:{toggle(){}}} );
const state={id:'job',image_filter:'page-1.png',record_offset:50,record_total:60,project_record_total:120,
 records:[{project_row:102}],image_navigation:[{file:'page-0.png'},{file:'page-1.png'},{file:'page-2.png'}],status:'ready'};
const sandbox={state,rows:Array.from({length:10},()=>({})),URLSearchParams,RECORDS_PER_VIEW:50,
 busy:false,uploading:false,active:null,paint:0,dirty:false,$:el,discardDraft:()=>true,
 loadJob:async(...args)=>{loads.push(args);return true;},paintRecordPager(){}};
vm.createContext(sandbox);
function include(name){
 const start=source.search(new RegExp('^(?:async )?function '+name+'\\(','m'));
 assert(start>=0,name);
 const first=source.indexOf('\n',start),line=source.slice(start,first);
 const end=line.endsWith('}')?first:source.indexOf('\n}',start)+2;
 vm.runInContext(source.slice(start,end),sandbox);
}
include('workspaceURL');include('hasRecordPage');include('changeRecordPage');include('filterImageList');include('stepImage');
vm.runInContext(source.split('\n').find(line=>line.startsWith('const projectRow=')),sandbox);
(async()=>{
 assert.equal(vm.runInContext('projectRow(0)',sandbox),102);
 const url=vm.runInContext("workspaceURL('job',50,'page-1.png')",sandbox);
 assert.equal(new URL(url,'http://localhost').searchParams.get('image'),'page-1.png');
 assert.equal(new URL(url,'http://localhost').searchParams.get('offset'),'50');
 assert(!vm.runInContext("workspaceURL('job')",sandbox).includes('image='));
 await sandbox.changeRecordPage(-1);assert.deepEqual(loads.pop(),['job',0,'page-1.png']);
 assert.equal(el('sheetWrap').scrollTop,0);
 const selected=[];sandbox.chooseImage=async file=>selected.push(file);
 await sandbox.stepImage(1);assert.equal(selected.pop(),'page-2.png');
 await sandbox.stepImage(-1);assert.equal(selected.pop(),'page-0.png');
 sandbox.state.image_filter=null;await sandbox.stepImage(1);assert.equal(selected.pop(),'page-0.png');
 assert.equal(el('imageSearch').value,'');
 const cards=['1 aq159.jpg','2 aq160.jpg'].map(search=>({dataset:{search},classList:{toggle(_,v){this.hidden=v;}}}));
 elements.imageList={children:cards};el('imageSearch').value='160';sandbox.filterImageList();
 assert.equal(cards[0].classList.hidden,true);assert.equal(cards[1].classList.hidden,false);
 assert.equal(sandbox.state.image_filter,null,'Searching the sidebar must not change the record filter');
 el('imageSearch').value='';sandbox.filterImageList();assert(cards.every(c=>!c.classList.hidden));
 console.log('Image navigation UI passed: filter-preserving pagination, project row numbers, previous/next image, and search.');
})().catch(error=>{console.error(error);process.exitCode=1;});
