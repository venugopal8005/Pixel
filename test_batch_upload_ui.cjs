/* Exercise the actual batch handler, including the 401 guard and interrupted retry. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('review_sheet.js','utf8');
const start=source.indexOf("$('scan').onclick=async()=>{"),end=source.indexOf("\n$('export').onclick=",start);
function element(){return {classList:{add(){},remove(){},toggle(){}},scrollIntoView(){},removeAttribute(){}};}
const elements={projectName:{value:'Large batch',removeAttribute(){},setAttribute(){},focus(){}}};
const el=id=>elements[id]??=element();
const calls=[],progress=[];let inflight=0,peak=0,failAt=-1;
const sandbox={MAX_UPLOAD_IMAGES:400,MAX_IMAGE_BYTES:25000000,uploadSession:null,state:null,cancelAvailable:true,
 uploadFiles:Array.from({length:400},(_,i)=>({name:'AQ'+(i+1)+'.png',size:200})),
 $:el,history:{replaceState(){}},setUploading(){},setInterval(){},showImageCount(){},
 paintImageStatuses(){throw Error('Upload progress must not render project image navigation');},
 paintReviewState(){throw Error('Upload progress must not render the spreadsheet');},
 readUploadFile:async file=>file.name,error:e=>{sandbox.errorMessage=e.message;},
 listJobs:async()=>{},loadJob:async id=>{sandbox.loaded=id;},
 api:async(route,data)=>{calls.push({route,data});inflight++;peak=Math.max(peak,inflight);await Promise.resolve();inflight--;
   if(route==='/api/upload/page'&&data.index===failAt)throw Error('Interrupted transfer');
   if(route.startsWith('/api/workspace'))return {state:{status:'uploading'}};
   return {id:'job',uploaded:(data.index||0)+1};}};
vm.createContext(sandbox);
// Use the real progress renderer: mocking it hid the fresh-project null crash.
vm.runInContext(source.slice(source.indexOf('let scanDisplay=null'),source.indexOf('async function loadJob(')),sandbox);
const paintScan=sandbox.paintScan;sandbox.paintScan=s=>{progress.push(s);paintScan(s);};
vm.runInContext(source.slice(start,end),sandbox);
(async()=>{
 await elements.scan.onclick();
 assert.equal(sandbox.errorMessage,undefined,'A fresh upload must work before a project is loaded');
 assert.equal(calls.filter(c=>c.route==='/api/upload/page').length,400);
 assert.equal(peak,1,'Only one image request may be in flight');
 assert(calls.filter(c=>c.route==='/api/upload/page').every((c,i)=>c.data.index===i&&!('pages' in c.data)));
 assert.equal(calls.at(-1).route,'/api/upload/finish');assert.equal(sandbox.loaded,'job');
 assert.equal(progress.at(-1).scan_stats.page,400);assert.equal(sandbox.uploadSession,null);
 // Resumed uploads can have a project shell, but still have no review workspace.
 sandbox.state={id:'job',status:'uploading',pages:[],records:[]};
 assert.doesNotThrow(()=>sandbox.paintScan({id:'job',status:'scanning',scan_stats:{stage:'uploading',page_count:4}}));
 sandbox.state=null;
 calls.length=0;sandbox.uploadFiles.push({name:'AQ401.png',size:200});
 await elements.scan.onclick();assert.equal(calls.length,0);assert(sandbox.errorMessage.includes('1–400'));
 sandbox.uploadFiles=sandbox.uploadFiles.slice(0,3);sandbox.loaded=null;failAt=1;calls.length=0;
 await elements.scan.onclick();assert(sandbox.uploadSession);assert.equal(sandbox.loaded,null);
 assert.equal(calls.filter(c=>c.route==='/api/upload/finish').length,0);
 assert.equal(elements.scan.textContent,'Resume upload & scan');
 failAt=-1;calls.length=0;await elements.scan.onclick();
 assert(!calls.some(c=>c.route==='/api/upload/create'),'Retry reuses saved project');
 assert.equal(sandbox.loaded,'job');assert.equal(sandbox.uploadSession,null);
 calls.length=0;elements.projectName.value='  ';await elements.scan.onclick();
 assert.equal(calls.length,0);assert.equal(sandbox.errorMessage,'Enter a project name.');
 const html=fs.readFileSync('review_sheet.html','utf8');
 assert(html.indexOf('id="notice"')<html.indexOf('id="projectBuilder"'));
 assert(html.indexOf('id="scanPanel"')<html.indexOf('id="projectBuilder"'));
 console.log('Batch UI passed: 400 ordered single-image requests, 401 rejection, progress, interrupted retry.');
})().catch(e=>{console.error(e);process.exitCode=1;});
