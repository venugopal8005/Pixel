/* Spreadsheet review over the existing OCR state; no model update occurs here. */
'use strict';
const $=id=>document.getElementById(id);
const MAX_UPLOAD_IMAGES=400,MAX_IMAGE_BYTES=25000000,RECORDS_PER_VIEW=50;
function showImageCount(count=null,selected=false){
 const badge=$('imageCount'),overLimit=selected&&count>MAX_UPLOAD_IMAGES;
 badge.textContent=count===null?'Up to '+MAX_UPLOAD_IMAGES+' images / batch':selected?count+' / '+MAX_UPLOAD_IMAGES+' images selected'+(overLimit?' · over limit':''):count+' image'+(count===1?'':'s')+' in project';
 badge.classList.toggle('overLimit',overLimit);
}
const legacyNames={0:'Record ID',1:'Printed ID',2:'Blank field',3:'Lid reference',4:'Name 1 prefix',5:'Name 1 remainder',6:'Address',7:'Locality',8:'Postal code',9:'Date',10:'Name 2 prefix',11:'Name 2 remainder',12:'Time of day',13:'Placeholder',14:'Property type',15:'Identifier',16:'Purpose',17:'Product',18:'Amount',19:'Term',20:'Rate',21:'Payment amount',22:'Secured Loan label',23:'Secured amount',24:'Following amount',25:'Placeholder',26:'Organization 1',27:'Name 3 prefix',28:'Name 3 remainder',29:'U.T.R. reference',30:'N.I. reference',31:'Occupation',32:'Response',33:'Organization 2',34:'Bank / card',35:'Final status',36:'Placeholder'};
let names=legacyNames,pilotHeaders=[],uploadFiles=[],uploadSession=null,uploading=false;
let previewCell=null,regionFirst=null,regionLast=null;
let state=null,rows=[],active=null,chosen=null,dirty=false,busy=false,poll=null,paint=0,scanAvailable=true,cancelAvailable=false;
const imageURL=name=>'/image?'+new URLSearchParams({job:state.id,name});
const has=(obj,key)=>Object.prototype.hasOwnProperty.call(obj,key);
const unsure=cell=>!cell.manual&&['uncertain','unmapped'].includes(cell.status);
const projectRow=index=>state.records[index]?.project_row??((state.record_offset||0)+index+1);
function workspaceURL(job,offset=0,image=null){const params=new URLSearchParams({job,offset});if(image)params.set('image',image);return '/api/workspace?'+params;}
async function api(url,data){
 const started=performance.now(),route=url.split('?')[0];let response;
 const details={route,method:data===undefined?'GET':'POST',job:data?.job||new URL(url,location.href).searchParams.get('job'),record:data?.record,field:data?.field,segment:data?.segment,reset:data?.reset,value_length:typeof data?.value==='string'?data.value.length:undefined};
 try{response=await fetch(url,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':window.PIXEL_TOKEN},body:JSON.stringify(data)});const body=await response.json();if(!response.ok)throw Error(body.error||'Request failed');
  if(route!=='/api/progress')window.PixelDiagnostics?.record('api_success',{...details,job:details.job||body.id,status:response.status,request_id:response.headers.get('X-Pixel-Request-ID'),duration_ms:Math.round(performance.now()-started)});return body;
 }catch(e){window.PixelDiagnostics?.record('api_error',{...details,status:response?.status,request_id:response?.headers.get('X-Pixel-Request-ID'),duration_ms:Math.round(performance.now()-started),message:e.message,stack:e.stack});throw e;}
}
window.PixelDiagnostics?.setContext(()=>{
 const rec=active?state?.records?.[active.row]:null,cell=active?rows[active.row]?.cells?.[active.field]:null;
 return {job:state?.id||new URLSearchParams(location.search).get('job'),project_name:state?.project_name,scan_available:scanAvailable,busy,unsaved_field_edit:dirty,
  image_filter:state?.image_filter,
  selected:active?{row_number:projectRow(active.row),column_number:active.field+1,field_index:active.field,field_name:names[active.field],record_key:rec?.key,record_id:rec?.record_id,segment:chosen,cell_status:cell?.status,pending:cell?.pending,sources:cell?.sources}:null,
  upload_order:uploadFiles.map(f=>({name:f.name,size:f.size,last_modified:f.lastModified})),scan:scanDisplay,
  visible_messages:['notice','dialogError','exportStatus','saveStatus'].map(id=>({area:id,message:$(id)?.textContent})).filter(v=>v.message)};
});
function error(e){window.PixelDiagnostics?.record('visible_error',{message:e.message||String(e),stack:e.stack});const target=$(active?'dialogError':'notice');target.textContent=e.message||String(e);if(!active)target.scrollIntoView({block:'nearest'});}
function setBusy(value){busy=value;for(const el of document.querySelectorAll('#reviewDialog button:not(#testReportCell),#reviewDialog input,#reviewDialog textarea'))el.disabled=value;if(!value&&active)applyAvailability();cropPicker.blocked=value;cropPicker.availability();}
function discardDraft(includeCrop=false){const crop=includeCrop&&cropPicker.hasDraft();if(!dirty&&!crop)return true;if(!window.confirm(crop?'Discard the unsaved field selection and any unsaved text edit? Saved corrections remain.':'Discard the unsaved whole-field edit? Saved character corrections will remain.'))return false;if(crop)cropPicker.clear();return true;}
function home(){if(uploading)return;if(active&&!discardDraft())return;uploadSession=null;loadEpoch++;$('jobs').disabled=false;clearTimeout(poll);scanDisplay=null;$('scanPanel').classList.add('hidden');state=null;rows=[];showImageCount();history.replaceState(null,'','/');for(const id of ['work','coverage','projectToolbar','projectBuilder'])$(id).classList.add('hidden');$('homePanel').classList.remove('hidden');$('empty').classList.remove('hidden');$('progress').textContent='';$('notice').textContent='';$('scan').disabled=!scanAvailable;listJobs().catch(error);}
async function listJobs(){const jobs=await api('/api/jobs');$('jobs').replaceChildren(new Option('Choose a saved project',''));$('projectGrid').replaceChildren();jobs.forEach(j=>{const label=j.name||j.id.slice(0,8);$('jobs').add(new Option(label+' · '+j.status,j.id));const box=document.createElement('article');box.className='projectCard';const h=document.createElement('h2');h.textContent=label;const info=document.createElement('p');info.className='muted';info.textContent=j.pages+' pages · '+j.records+' record candidates · '+j.status;const button=document.createElement('button');button.textContent=j.status==='scanning'?'View progress':j.status==='error'?'View scan error':'Open project';button.onclick=()=>loadJob(j.id);box.append(h,info,button);$('projectGrid').append(box);});if(state)$('jobs').value=state.id;return jobs;}
let scanDisplay=null,loadEpoch=0,scanQueue={job:null,checkedAt:0,pending:false};
function paintScanQueue(){
 const queued=scanDisplay?.status==='scanning'&&scanDisplay.scan_stats?.stage==='queued';
 $('scanQueue').classList.toggle('hidden',!queued);
 if(!queued)return;
 const info=scanQueue.job===state?.id?scanQueue:null,active=info?.active;
 $('scanQueueOpen').classList.toggle('hidden',!active);
 $('scanQueueOpen').removeAttribute('href');
 $('scanQueueDetail').textContent=active?.snapshot.progress||'';
 $('scanQueueOthers').textContent=info?.waiting?.length?'Also waiting: '+info.waiting.map(j=>j.name).join(', ')+'.':'';
 $('scanQueueText').textContent=active?'Currently scanning: '+active.name:info?.unavailable?'Unable to check the running project. Retrying…':info?.checked?'Waiting for the scanner to start this project.':'Checking which project is using the scanner…';
 if(active){$('scanQueueOpen').href='/?'+new URLSearchParams({job:active.id});$('scanQueueOpen').textContent='Open '+active.name;}
}
async function refreshScanQueue(job){
 if(state?.id!==job||scanDisplay?.scan_stats?.stage!=='queued')return;
 if(scanQueue.job!==job)scanQueue={job,checkedAt:0,pending:false};
 if(scanQueue.pending||Date.now()-scanQueue.checkedAt<5000)return;
 const lookup=scanQueue,epoch=loadEpoch;lookup.pending=true;lookup.checkedAt=Date.now();
 try{
  const jobs=await api('/api/jobs');
  const results=await Promise.allSettled(jobs.filter(j=>j.id!==job&&j.status==='scanning').map(async j=>({...j,snapshot:await api('/api/progress?job='+j.id)})));
  if(scanQueue!==lookup||state?.id!==job||epoch!==loadEpoch||scanDisplay?.scan_stats?.stage!=='queued')return;
  const others=results.filter(r=>r.status==='fulfilled').map(r=>r.value).filter(j=>j.snapshot.status==='scanning');
  lookup.active=others.find(j=>['loading','reading','saving'].includes(j.snapshot.scan_stats?.stage));
  lookup.waiting=others.filter(j=>j.snapshot.scan_stats?.stage==='queued');
  lookup.unavailable=results.some(r=>r.status==='rejected');lookup.checked=true;paintScanQueue();
 }catch(e){
  if(scanQueue===lookup&&state?.id===job&&epoch===loadEpoch){lookup.active=null;lookup.waiting=[];lookup.unavailable=true;lookup.checked=true;paintScanQueue();}
 }finally{lookup.pending=false;}
}
function paintScan(snapshot){
 scanDisplay=snapshot;const stats=snapshot.scan_stats||{},failed=snapshot.status==='error',cancelled=snapshot.status==='cancelled',stage=stats.stage||'queued';
 showImageCount(stats.page_count??state?.pages?.length??uploadFiles.length,stage==='uploading');
 $('scanPanel').classList.toggle('hidden',snapshot.status==='ready');$('empty').classList.add('hidden');$('scanFailure').classList.toggle('hidden',!failed&&!cancelled);
 $('scanTitle').textContent=failed?'Scan stopped':({queued:'Waiting for the scanner',loading:'Preparing local OCR',reading:'Scanning your images',saving:'Saving your results',uploading:'Preparing your images',complete:'Scan complete',cancelling:'Cancelling scan',cancelled:'Scan cancelled'}[stage]||'Scanning your images');
 $('cancelScan').classList.toggle('hidden',!cancelAvailable||snapshot.status!=='scanning'||stage==='uploading');$('cancelScan').disabled=stage==='cancelling';$('cancelScan').textContent=stage==='queued'?'Cancel queued scan':stage==='cancelling'?'Cancelling…':'Cancel scan';
 if(snapshot.status!=='scanning'||stage==='cancelling')$('cancelPrompt').classList.add('hidden');
 $('scanDetail').textContent=failed?'This scan did not finish. Retry the saved images below.':snapshot.progress||'Preparing the scan…';
 if(Number.isFinite(stats.percent)){$('scanBar').value=stats.percent;$('scanPercent').textContent=Math.floor(stats.percent)+(stage==='uploading'?'% of images uploaded':'% of scan processed (estimate)');}
 else{$('scanBar').removeAttribute('value');$('scanPercent').textContent=stage==='queued'?'This project has not started. Pixel scans one project at a time.':'Preparing…';}
 $('scanBar').classList.toggle('hidden',stage==='queued'&&!failed);$('scanMetrics').classList.toggle('hidden',stage==='queued'&&!failed);paintScanQueue();
 if(failed){$('scanBar').value=stats.percent||0;$('scanPercent').textContent='Scan stopped after an error';$('scanDetail').textContent=snapshot.progress||'This scan did not finish.';}
 if(cancelled){$('scanBar').value=stats.percent||0;$('scanPercent').textContent='Stopped · '+(stats.completed_pages||0)+' of '+(stats.page_count||state?.pages?.length||0)+' images fully scanned';}
 $('scanPages').textContent=(stats.page||'—')+' / '+(stats.page_count||state?.pages?.length||'—');
 $('scanRecords').textContent=stats.record_candidates??state?.records?.length??0;$('scanRegions').textContent=stats.text_regions??state?.records?.reduce((n,r)=>n+r.lines.length,0)??0;
 $('scanDiagnostic').textContent=snapshot.error||'';$('progress').textContent='';updateScanClock();
}
function updateScanClock(){if(!scanDisplay)return;const st=scanDisplay.scan_stats||{},queued=scanDisplay.status==='scanning'&&st.stage==='queued';const elapsed=queued&&st.queued_at?Date.now()/1000-st.queued_at:scanDisplay.status==='scanning'&&st.started_at?Date.now()/1000-st.started_at:st.elapsed_seconds;
 $('scanElapsed').textContent=Number.isFinite(elapsed)?(queued?'Waiting ':'Elapsed ')+Math.floor(Math.max(0,elapsed)/60)+'m '+String(Math.floor(Math.max(0,elapsed)%60)).padStart(2,'0')+'s':'';}
setInterval(updateScanClock,1000);
async function pollProgress(job){
 if(state?.id!==job)return;
 try{const snapshot=await api('/api/progress?job='+job);if(state?.id!==job)return;paintScan(snapshot);if(snapshot.status==='scanning'&&snapshot.scan_stats?.stage==='queued')void refreshScanQueue(job);
 const changed=(snapshot.scan_stats?.review_revision||0)>(state.review_revision||0)||snapshot.status!==state.status;
 if(changed){$('newResults').classList.remove('hidden');await sync(true);}
 if(state?.id!==job)return;
 if(snapshot.status!=='scanning'&&state.status===snapshot.status&&(state.review_revision||0)>=(snapshot.scan_stats?.review_revision||0)){await listJobs();return;}
 poll=setTimeout(()=>pollProgress(job),1000);
 }catch(e){if(state?.id!==job)return;$('scanDetail').textContent='Waiting for the local app to reconnect. The last scan progress is shown below.';poll=setTimeout(()=>pollProgress(job),2500);}
}
async function loadJob(job,offset=0,image=null){
 const epoch=++loadEpoch;$('newResults').classList.add('hidden');clearTimeout(poll);scanDisplay=null;scanQueue={job:null,checkedAt:0,pending:false};$('exportStatus').textContent='';$('notice').textContent=scanAvailable?'':'New scans are unavailable. Saved projects can still be reviewed and exported.';$('jobs').disabled=true;
 $('work').inert=true;$('work').setAttribute('aria-busy','true');$('coverage').inert=true;$('progress').textContent='Loading records…';
 try{
 const workspace=await api(workspaceURL(job,offset,image));if(epoch!==loadEpoch)return;state=workspace.state;rows=workspace.rows;names=state.schema_version===2?Object.fromEntries(pilotHeaders.map((v,i)=>[i,v])):legacyNames;
 $('jobs').value=job;$('projectTitle').textContent=state.project_name||'Saved scan '+job.slice(0,8);
 showImageCount(state.pages.length);
 for(const id of ['homePanel','projectBuilder','work','coverage','empty','scanPanel'])$(id).classList.add('hidden');
 $('projectToolbar').classList.remove('hidden');$('progress').textContent=state.progress;const viewURL=new URLSearchParams({job});if(state.image_filter)viewURL.set('image',state.image_filter);if(state.record_offset)viewURL.set('offset',state.record_offset);history.replaceState(null,'','?'+viewURL);$('scan').disabled=!scanAvailable||state.status==='scanning';
 if(state.status==='uploading'){uploadSession={id:job,files:state.upload_manifest};$('projectName').value=state.project_name;$('projectBuilder').classList.remove('hidden');$('scan').textContent='Resume upload & scan';$('notice').textContent=state.progress+'. Select the same images in the same order to resume; saved images will not be duplicated.';showImageCount(state.upload_manifest.length,true);return;}
 if(['scanning','error','cancelled'].includes(state.status)){
  paintScan(state);if(state.review_allowed){$('work').classList.remove('hidden');drawSheet();drawCoverage();}
  if(state.status==='scanning')poll=setTimeout(()=>pollProgress(job),100);return true;
 }
 $('work').classList.remove('hidden');drawSheet();drawCoverage();
 $('progress').textContent=state.progress+(state.scan_stats?.elapsed_seconds?' · scanned locally in '+Math.round(state.scan_stats.elapsed_seconds)+' seconds':'');
 return true;
 }catch(e){if(epoch===loadEpoch){error(e);$('progress').textContent='Records could not be loaded. Try again.';}}finally{if(epoch===loadEpoch){$('jobs').disabled=false;$('work').inert=false;$('work').setAttribute('aria-busy','false');$('coverage').inert=false;}}
}
$('retryScan').onclick=async()=>{if(!state)return;$('retryScan').disabled=true;try{const result=await api('/api/retry',{job:state.id});await listJobs();await loadJob(result.id);}catch(e){error(e);}finally{$('retryScan').disabled=false;}};
$('cancelScan').onclick=()=>{
 if(!state||state.status!=='scanning'||!cancelAvailable)return;
 $('cancelPrompt').classList.remove('hidden');$('keepScanning').focus();
};
$('keepScanning').onclick=()=>$('cancelPrompt').classList.add('hidden');
$('confirmCancel').onclick=async()=>{
 if(!state||state.status!=='scanning'||!cancelAvailable)return;
 const job=state.id;$('cancelScan').disabled=true;$('confirmCancel').disabled=true;
 try{const snapshot=await api('/api/cancel',{job});if(state?.id===job){paintScan(snapshot);clearTimeout(poll);poll=setTimeout(()=>pollProgress(job),100);}}
 catch(e){error(e);if(state?.id===job)$('cancelScan').disabled=false;}
 finally{$('confirmCancel').disabled=false;}
};
$('newResults').onclick=()=>sync(true).catch(error);
function reviewAvailability(){
 const partial=state.status!=='ready',available=state.ready_record_total??state.project_record_total??rows.length;
 $('reviewAvailability').classList.toggle('hidden',!partial);
 $('reviewAvailabilityText').textContent=(state.status==='scanning'?'Scanning continues. ':state.status==='cancelled'?'Scan cancelled. ':'Scan stopped. ')+
  available+' records available · '+(state.completed_pages||0)+' / '+state.pages.length+' images fully scanned. '+
  (state.status==='scanning'?'You can review the available records now. ':'Saved results remain editable. ')+
  (state.pending_record_total?state.pending_record_total+' unfinished record candidates are held until their continuation is resolved.':'');
 $('export').textContent=partial?'Export available':'Export all';$('export').disabled=!available;
 $('export').title=partial?'Export the available records; the workbook will be labelled as a partial export':'Export every record in the project to Excel';
 $('exportScope').textContent=partial?'Export includes available records and saved corrections, with a partial-export notice. Unscanned pages and unfinished records are not included.':'Export includes every record in the project, with your saved corrections. Unreviewed alternatives export as [i/t]; unreadable or unlocated text exports as [?].';
}

let sidebarSignature='',sidebarJob=null;
function filterImageList(){
 const query=$('imageSearch').value.trim().toLowerCase();let visible=0;
 for(const button of $('imageList').children){const match=!query||button.dataset.search.includes(query);button.classList.toggle('hidden',!match);if(match)visible++;}
 $('imageSearchEmpty').classList.toggle('hidden',visible>0);
}
function drawImageNavigation(){
 const images=state.image_navigation||[],selected=images.find(p=>p.file===state.image_filter),index=images.indexOf(selected);
 if(sidebarJob!==state.id){$('imageSearch').value='';sidebarJob=state.id;}
 const signature=JSON.stringify([state.id,images]);
 if(signature!==sidebarSignature){
  sidebarSignature=signature;const sidebarTop=$('imageList').scrollTop,sidebarLeft=$('imageList').scrollLeft;$('imageList').replaceChildren();
  for(const page of images){
   const button=document.createElement('button');button.className='imageCard';button.dataset.file=page.file;button.dataset.search=(page.number+' '+page.name).toLowerCase();
   button.setAttribute('aria-label','Image '+page.number+': '+page.name);button.onclick=()=>chooseImage(page.file);
   const img=document.createElement('img');img.src='/thumbnail?'+new URLSearchParams({job:state.id,name:page.file});img.alt='';img.loading='lazy';img.decoding='async';img.width=48;img.height=64;
   const text=document.createElement('span'),title=document.createElement('strong'),filename=document.createElement('span'),count=document.createElement('small');
   title.textContent='Image '+page.number;filename.textContent=page.name;count.textContent=({ready:'Ready',continuation:'Ready · continuation pending',scanning:'Scanning',waiting:'Waiting',partial:'Partly scanned',not_scanned:'Not scanned'}[page.status]||'')+' · '+page.records+' record'+(page.records===1?'':'s')+(page.shared?' · '+page.shared+' shared':'');
   text.append(title,filename,count);button.append(img,text);$('imageList').append(button);
  }
  $('imageList').scrollTop=sidebarTop;$('imageList').scrollLeft=sidebarLeft;
 }
 for(const button of $('imageList').children)button.setAttribute('aria-pressed',String(button.dataset.file===state.image_filter));
 $('imageNavCount').textContent=images.length;
 $('allImages').textContent='All images · '+(state.ready_record_total??state.project_record_total??rows.length)+' records';$('allImages').setAttribute('aria-pressed',String(!selected));
 $('viewTitle').textContent=selected?'Image '+selected.number+' · '+selected.name:'All images';
 $('viewContext').textContent=selected?selected.records+' records linked to this image'+(selected.shared?' · '+selected.shared+' also appear on another image':'')+'. Corrections update the project.':(state.ready_record_total??state.project_record_total??rows.length)+' available records across '+images.length+' images. Select an image to focus your review.';
 $('imagePosition').textContent=selected?'Image '+selected.number+' of '+images.length:'Viewing all '+images.length+' images';
 $('previousImage').disabled=index<=0;$('nextImage').disabled=!images.length||index===images.length-1;
 $('openSelectedImage').classList.toggle('hidden',!selected);if(selected)$('openSelectedImage').href=imageURL(selected.file);
 filterImageList();
}
async function chooseImage(image){
 if(busy||uploading||!state||(!state.review_allowed&&state.status!=='ready')||!discardDraft(true))return;
 if(active){$('reviewDialog').close();active=null;paint++;dirty=false;}
 if(image===state.image_filter&&!(state.record_offset||0))return;
 if(await loadJob(state.id,0,image)){
  $('sheetWrap').scrollTop=0;$('sheetWrap').scrollLeft=0;
  [...$('imageList').children].find(button=>button.dataset.file===image)?.scrollIntoView({block:'nearest',inline:'nearest'});
 }
}
function stepImage(direction){
 if(!state)return;const images=state.image_navigation||[],index=images.findIndex(p=>p.file===state.image_filter),next=index<0?0:index+direction;
 if(next>=0&&next<images.length){$('imageSearch').value='';return chooseImage(images[next].file);}
}
$('imageSearch').oninput=filterImageList;$('allImages').onclick=()=>chooseImage(null);
$('previousImage').onclick=()=>stepImage(-1);$('nextImage').onclick=()=>stepImage(1);

function hasRecordPage(direction){return !!state&&(direction<0?(state.record_offset||0)>0:(state.record_offset||0)+rows.length<(state.record_total??rows.length));}
function paintRecordPager(){
 const offset=state.record_offset||0,total=state.record_total??rows.length;
 $('recordRange').textContent=total?'Showing '+(offset+1)+'–'+(offset+rows.length)+' of '+total+(state.image_filter?' image records':' project records'):'No records';
 $('previousRecords').disabled=!hasRecordPage(-1);$('nextRecords').disabled=!hasRecordPage(1);
 $('recordPager').classList.toggle('hidden',total<=RECORDS_PER_VIEW);
}
async function changeRecordPage(direction){
 if(busy||!hasRecordPage(direction))return;
 $('previousRecords').disabled=true;$('nextRecords').disabled=true;
 const job=state.id,result=await loadJob(job,(state.record_offset||0)+direction*RECORDS_PER_VIEW,state.image_filter);
 if(state?.id!==job)return false;
 paintRecordPager();if(result)$('sheetWrap').scrollTop=0;
 return result;
}
$('previousRecords').onclick=()=>changeRecordPage(-1);$('nextRecords').onclick=()=>changeRecordPage(1);
async function navigateCell(direction,nextGroupOnly=false){
 if(busy||!discardDraft(true))return;
 const next=!nextGroupOnly&&active?candidate(direction):null;
 if(next)return openCell(next.row,next.field);
 const onlyUnsure=nextGroupOnly||$('onlyUnsure').checked;
 if(!hasRecordPage(direction)){if(nextGroupOnly)$('notice').textContent=state.image_filter?'No more unsure cells in this image. You can inspect any cell or choose another image.':'No more unsure cells in this direction. You can still inspect any cell.';return;}
 $('reviewDialog').close();active=null;paint++;dirty=false;
 while(hasRecordPage(direction)){
  if(!await changeRecordPage(direction))return;
  const order=rows.map((_,i)=>i);if(direction<0)order.reverse();
  for(const row of order){
   const fields=rows[row].cells.map((_,i)=>i);if(direction<0)fields.reverse();
   const field=fields.find(i=>!onlyUnsure||unsure(rows[row].cells[i]));
   if(field!==undefined)return openCell(row,field);
  }
 }
 $('notice').textContent=state.image_filter?'No more unsure cells in this image. You can inspect any cell or choose another image.':'No more unsure cells in this direction. You can still inspect any cell.';
}

function drawCoverage(){const fragments=state.records.flatMap(r=>(r.fragments||[]).map(f=>({...f,record:r})));$('coverage').classList.remove('hidden');$('coverageSummary').textContent=fragments.length?fragments.length+' fragments · '+fragments.filter(f=>f.status==='continuation_inferred').length+' inferred continuations · '+fragments.filter(f=>f.status==='unassigned').length+' unassigned fragments':'This older scan has no saved fragment ledger. Source lines and full pages remain available.';$('coverageList').replaceChildren();for(const warning of state.page_issues||[]){const p=document.createElement('p');p.className='error';p.textContent=warning;$('coverageList').append(p);}for(const f of fragments){const box=document.createElement('div');box.className='coverageItem';const label=document.createElement('p');label.textContent=f.record.record_id+' · '+f.status.replaceAll('_',' ')+' · '+f.page+' · column '+(f.column+1);const link=document.createElement('a');link.href=imageURL(f.file);link.target='_blank';link.rel='noopener';link.textContent='Open source page';const note=document.createElement('p');note.className='muted';note.textContent=f.record.notes.join(' ');box.append(label,link,note);$('coverageList').append(box);}}
function drawSheet(){const table=$('sheet');table.replaceChildren();const head=table.createTHead().insertRow();for(let f=0;f<=36;f++){const th=document.createElement('th');th.scope='col';th.textContent=state.schema_version===2?names[f]:(f===0?'ID':'Field '+f);const small=document.createElement('small');small.textContent=state.schema_version===2?'Column '+(f+1):names[f];th.append(small);head.append(th);}const body=table.createTBody();let pending=0,confirmed=0,ruleWarnings=0;rows.forEach((r,ri)=>{const tr=body.insertRow();r.cells.forEach((c,fi)=>{pending+=unsure(c)?1:0;confirmed+=c.manual?1:0;ruleWarnings+=c.rule_issues?.length?1:0;const td=document.createElement(fi===0?'th':'td');if(fi===0)td.scope='row';const b=document.createElement('button');b.className='cell '+(c.manual?'confirmed':c.status);b.dataset.row=ri;b.dataset.field=fi;b.setAttribute('aria-label','Row '+projectRow(ri)+', '+names[fi]+': '+(c.value??'blank'));b.textContent=c.value===null?'—':(c.value===''?'(empty)':c.value);const small=document.createElement('small');small.textContent=c.manual?(c.rule_issues?.length?'Confirmed · rule warning':'Confirmed'):c.rule_issues?.length?'Rule needs review':c.status==='unmapped'?(c.candidate&&c.sources.length?'Locate field / review crop':'Draw field area'):c.pending?c.pending+' unsure region'+(c.pending===1?'':'s'):c.rule_actions?.length?'Rule-assisted · unverified':c.status==='blank'?'Blank placeholder':c.status==='generated'?'Generated':'Unreviewed reading';b.append(small);if(fi===0&&state.records[ri].source_images?.length>1){const tag=document.createElement('small');tag.className='sourceTag';tag.textContent='Continued · images '+state.records[ri].source_images.map(file=>state.image_navigation.find(p=>p.file===file)?.number).filter(Boolean).join(' + ');b.append(tag);}b.onclick=()=>openCell(ri,fi);td.append(b);tr.append(td);});});if(!rows.length){const td=body.insertRow().insertCell();td.colSpan=37;td.className='emptySheet';td.textContent=state.status==='scanning'?'No records are ready for review here yet. Completed records will appear automatically; unfinished continuations are held until the adjoining image is read.':state.status==='cancelled'?'No records are available here. This scan was cancelled; unscanned images remain in the project.':state.image_filter?'No records were detected for this image. Open the source image to check it; all project records remain available under All images.':'No records were detected in this project. Inspect the source images and page warnings.';} $('summary').textContent=rows.length+' records shown of '+(state.record_total??rows.length)+(state.image_filter?' in this image':' in the project')+' · '+pending+' cells need review · '+confirmed+' fields confirmed'+(ruleWarnings?' · '+ruleWarnings+' rule warnings':'');const located=rows.reduce((n,r)=>n+(r.field_coverage?.located||0),0),expected=rows.reduce((n,r)=>n+(r.field_coverage?.expected||0),0);if(expected)$('summary').textContent+=' · '+located+'/'+expected+' printed field locations found';$('reviewNext').disabled=!pending&&!hasRecordPage(1);paintRecordPager();drawImageNavigation();reviewAvailability();$('sources').textContent=state.image_filter?'Full continued records are included, even when part of a record is on another image.':'Each row is one record. Use the image sidebar to find its source.';}
function current(){return previewCell||rows[active.row].cells[active.field];}
function record(){return state.records[active.row];}
function entry(ref){const line=record().lines.find(l=>l.id===ref.line),source=line.segments.find(s=>s.id===ref.id),rule=current().candidate?null:current().rule_segments?.[ref.id];return {...ref,line,seg:rule?{...source,...rule}:source,rule};}
function entries(){return current().segments.map(entry);}
function pendingEntry(e){return e.editable&&e.seg.category!=='single'&&!has(state.decisions,e.id);}
function candidate(direction,from=active){let index=from.row*37+from.field+direction;while(index>=0&&index<rows.length*37){const row=Math.floor(index/37),field=index%37;if(!$('onlyUnsure').checked||unsure(rows[row].cells[field]))return {row,field};index+=direction;}return null;}
async function openCell(row,field){if(busy||!discardDraft(true))return;active={row,field};previewCell=null;regionFirst=null;regionLast=null;chosen=null;dirty=false;$('regionTools').open=false;$('saveStatus').textContent='';$('dialogError').textContent='';if(!$('reviewDialog').open)$('reviewDialog').showModal();renderCell();}
function renderCell(){const cell=current();dirty=false;$('cellTitle').textContent=(active.field===0?'ID':'Field '+active.field)+' · '+names[active.field];$('cellMeta').textContent='Project record '+projectRow(active.row)+' of '+(state.project_record_total??state.record_total??rows.length)+' · ID '+record().record_id+(record().source_images?.length?' · image'+(record().source_images.length>1?'s ':' ')+record().source_images.map(file=>state.image_navigation.find(p=>p.file===file)?.number).filter(Boolean).join(' + '):'');const coverage=rows[active.row].field_coverage;if(coverage)$('cellMeta').textContent+=' · '+coverage.located+'/'+coverage.expected+' printed field locations found';$('fieldInput').value=cell.manual?cell.value:cell.plain||((cell.value==='[?]'||cell.value===null)?'':cell.value);$('cellNotice').textContent=cell.manual?'This whole-field correction controls the exported value. Reset it to return to character-level editing.':!cell.sources.length?(cell.status==='generated'||cell.status==='blank'?'This field is generated or reserved and has no printed source crop.':'Draw this field on the record image below, check the selection preview, then confirm it to read its characters.'):'Review the cropped field below. Crops and character markers are approximate; full source pages remain available.';const list=entries();if(!list.some(e=>e.id===chosen))chosen=(list.find(pendingEntry)||list[0])?.id??null;$('characters').replaceChildren();if(!list.length)$('characters').textContent='No characters mapped to this cell.';for(const e of list){const b=document.createElement('button');b.dataset.segment=e.id;b.className='glyph '+e.seg.category+(has(state.decisions,e.id)?' confirmed':e.rule?.resolved?' ruleAssisted':'')+(chosen===e.id?' selected':'');b.textContent=(state.decisions[e.id]??e.seg.text)||'∅';b.title=e.editable?'Inspect character':'Segment crosses a field boundary; edit the whole field';b.onclick=()=>{if(!discardDraft())return;chosen=e.id;renderCell();};$('characters').append(b);}$('recordNotes').textContent=record().notes.join('\n');if(cell.field_rule)$('cellNotice').textContent+=' Field rule: '+cell.field_rule.description+' '+cell.field_rule.instruction;if(cell.rule_actions?.length)$('cellNotice').textContent+=' '+cell.rule_actions.length+' OCR alternatives filtered by this field rule; source evidence is retained.';if(cell.rule_issues?.length)$('cellNotice').textContent+=' '+cell.rule_issues.join(' ');$('pageImages').replaceChildren();for(const name of new Set([...record().lines.map(l=>l.page),...(record().fragments||[]).map(f=>f.page)])){const p=state.pages.find(p=>p.name===name);if(p){const a=document.createElement('a');a.href=imageURL(p.file);a.target='_blank';a.rel='noopener';a.textContent='Open '+name;const img=document.createElement('img');img.src=a.href;img.alt=name;img.loading='lazy';$('pageImages').append(a,img);}}if(cell.candidate)$('cellNotice').textContent='This field has not been located. Draw its area on the record above and confirm the selection to read it. The suggested crop below is only a starting point.';renderCharacter();renderRegionTools();renderCrops();configureCropPicker();applyAvailability();}
function renderCharacter(){const e=entries().find(e=>e.id===chosen);$('charEditor').classList.toggle('hidden',!e);$('options').replaceChildren();if(!e)return;$('charInput').value=state.decisions[e.id]??e.seg.text;$('charReason').textContent=!e.editable?'This segment overlaps a neighboring field. Use the whole-field editor to avoid changing both cells.':has(state.decisions,e.id)?'This character is confirmed. '+(entries().some(pendingEntry)?'Choose Next unsure character to continue.':'No editable unsure characters remain in this cell. Use Next cell to continue, or inspect other characters.'):e.seg.reason;if(e.rule)$('charReason').textContent+=' Original OCR alternatives: '+e.rule.original_options.map(v=>v||'∅').join(' / ');for(const value of e.seg.options){const b=document.createElement('button');b.textContent=value||'∅';b.onclick=()=>saveCharacter(value);b.disabled=current().manual||!e.editable;$('options').append(b);}}
function applyAvailability(){if(!active)return;const cell=current(),e=entries().find(e=>e.id===chosen);$('saveCharacter').disabled=!e||!e.editable||cell.manual;$('resetCharacter').disabled=!e||!e.editable||cell.manual||!has(state.decisions,e.id);$('charInput').disabled=!e||!e.editable||cell.manual;$('resetField').disabled=!cell.manual;$('previousCell').disabled=!candidate(-1)&&!hasRecordPage(-1);$('nextCell').disabled=!candidate(1)&&!hasRecordPage(1);$('nextCharacter').disabled=cell.manual||!entries().some(pendingEntry);for(const b of $('options').children)b.disabled=!e||!e.editable||cell.manual;}
async function renderCrops(){const generation=++paint,cell=current(),rec=record();$('crops').replaceChildren();const refs=cell.sources;if(!refs.length)$('crops').textContent='No saved text crop for this field. Use Draw field area above for printed fields; generated fields have no source crop.';for(const ref of refs){if(!ref.image)continue;const box=document.createElement('div');box.className='cropBox';const caption=document.createElement('p');caption.className='muted';caption.textContent=ref.page+(cell.candidate?' · proposed field crop':' · field crop');box.append(caption);$('crops').append(box);const img=new Image();img.onload=()=>{if(generation!==paint)return;const source=ref.context?ref.box:[Math.max(0,Math.min(ref.left,img.width-1)),0,Math.min(ref.right,img.width),img.height];const [x,y,r,b]=source,w=Math.max(1,r-x),h=Math.max(1,b-y),scale=ref.context?Math.min(1.5,850/w):Math.min(5,100/h);const canvas=document.createElement('canvas');canvas.width=Math.ceil(w*scale);canvas.height=Math.ceil(h*scale);canvas.setAttribute('role','img');canvas.setAttribute('aria-label',caption.textContent);const ctx=canvas.getContext('2d');ctx.drawImage(img,x,y,w,h,0,0,canvas.width,canvas.height);const e=entries().find(e=>e.id===chosen);if(!ref.context&&e&&e.line.id===ref.line){ctx.strokeStyle='#e57025';ctx.lineWidth=2;ctx.strokeRect(Math.max(0,(e.seg.x-x-2)*scale),1,Math.min(24,Math.max(8,7*scale)),canvas.height-2);}box.append(canvas);};img.onerror=()=>{if(generation===paint)caption.textContent+=' · image could not be loaded';};img.src=imageURL(ref.image);}}
let refreshSequence=0;
function deferBackgroundRefresh(){return !!active||busy||dirty||cropPicker.hasDraft();}
async function sync(automatic=false){
 if(!state||(automatic&&deferBackgroundRefresh()))return false;
 const id=state.id,epoch=loadEpoch,sequence=++refreshSequence;
 const workspace=await api(workspaceURL(id,state.record_offset||0,state.image_filter));
 // A response can arrive after the user opens a cell or changes the image.
 if(state?.id!==id||loadEpoch!==epoch||sequence!==refreshSequence||(automatic&&deferBackgroundRefresh()))return false;
 const scroll={top:$('sheetWrap').scrollTop,left:$('sheetWrap').scrollLeft};
 state=workspace.state;rows=workspace.rows;
 if(previewCell){const groups=new Map();for(const ref of previewCell.segments){const e=entry(ref);if(!groups.has(ref.line))groups.set(ref.line,[]);groups.get(ref.line).push(state.decisions[e.id]??e.seg.text);}previewCell.plain=[...groups.values()].map(chars=>chars.join('')).join(' ');}
 if(state.review_allowed||state.status==='ready')$('work').classList.remove('hidden');
 drawSheet();drawCoverage();
 $('sheetWrap').scrollTop=scroll.top;$('sheetWrap').scrollLeft=scroll.left;
 $('newResults').classList.add('hidden');
 if(automatic){if(scanDisplay)paintScan(scanDisplay);}
 else $('exportStatus').textContent='Changes saved. Export to download the updated workbook.';
 return true;
}

async function saveCharacter(value,reset=false){if(busy||!discardDraft())return;const e=entries().find(e=>e.id===chosen);if(!e?.editable||current().manual)return;setBusy(true);try{await api('/api/confirm',{job:state.id,segment:e.id,value,reset});await sync();const list=entries(),index=list.findIndex(v=>v.id===e.id);chosen=reset?e.id:([...list.slice(index+1),...list.slice(0,index)].find(pendingEntry)?.id??e.id);renderCell();$('saveStatus').textContent='Character saved.';}catch(e){error(e);}finally{setBusy(false);}}
async function saveField(reset=false){if(busy)return;setBusy(true);try{await api('/api/field',{job:state.id,record:record().key,field:active.field,value:$('fieldInput').value,reset});dirty=false;await sync();renderCell();$('saveStatus').textContent=reset?'Field confirmation reset.':'Field confirmed and saved.';}catch(e){error(e);}finally{setBusy(false);}}
function closeDialog(){if(busy||!discardDraft(true))return;const prior=active;$('reviewDialog').close();active=null;paint++;dirty=false;document.querySelector(`.cell[data-row="${prior.row}"][data-field="${prior.field}"]`)?.focus();}
$('closeDialog').onclick=closeDialog;$('reviewDialog').addEventListener('cancel',e=>{e.preventDefault();closeDialog();});$('fieldInput').oninput=()=>{dirty=true;$('saveStatus').textContent='Unsaved whole-field edit';};$('saveCharacter').onclick=()=>saveCharacter($('charInput').value);$('resetCharacter').onclick=()=>saveCharacter('',true);$('charInput').onkeydown=e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();saveCharacter(e.target.value);}};$('confirmField').onclick=()=>saveField();$('resetField').onclick=()=>{if(discardDraft())saveField(true);};$('nextCharacter').onclick=()=>{if(!discardDraft())return;const list=entries(),i=list.findIndex(e=>e.id===chosen);chosen=[...list.slice(i+1),...list.slice(0,i+1)].find(pendingEntry)?.id??chosen;renderCell();};for(const [id,direction] of [['previousCell',-1],['nextCell',1]])$(id).onclick=()=>{navigateCell(direction);};$('onlyUnsure').onchange=applyAvailability;
$('reviewNext').onclick=()=>{for(let row=0;row<rows.length;row++){const field=rows[row].cells.findIndex(unsure);if(field>=0){openCell(row,field);return;}}navigateCell(1,true);};$('jobs').onchange=()=>{if($('jobs').value)loadJob($('jobs').value);};function showFiles(){showImageCount(uploadFiles.length,true);$('pageList').replaceChildren();$('fileOrder').textContent=uploadFiles.length+' images selected';uploadFiles.forEach((f,i)=>{const li=document.createElement('li');li.append(document.createTextNode(f.name));for(const [label,d] of [['↑',-1],['↓',1]]){const b=document.createElement('button');b.textContent=label;b.setAttribute('aria-label',(d<0?'Move up ':'Move down ')+f.name);b.disabled=i+d<0||i+d>=uploadFiles.length;b.onclick=()=>{[uploadFiles[i],uploadFiles[i+d]]=[uploadFiles[i+d],uploadFiles[i]];showFiles();};li.append(b);}$('pageList').append(li);});}
$('files').onchange=()=>{uploadFiles=Array.from($('files').files).sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true}));showFiles();};
$('newProject').onclick=()=>{if(uploading)return;state=null;rows=[];clearTimeout(poll);loadEpoch++;uploadSession=null;$('work').classList.add('hidden');$('coverage').classList.add('hidden');$('scan').textContent='Create project & scan';history.replaceState(null,'','/');$('scanPanel').classList.add('hidden');$('homePanel').classList.add('hidden');$('projectToolbar').classList.remove('hidden');$('projectTitle').textContent='New project';showImageCount(uploadFiles.length,true);$('jobs').value='';$('projectBuilder').classList.remove('hidden');$('empty').classList.add('hidden');$('upload').open=true;$('projectName').focus();};$('backProjects').onclick=home;
function setUploading(value){
 uploading=value;
 for(const id of ['scan','files','projectName','backProjects','newProject','jobs'])$(id).disabled=value;
 for(const button of $('pageList').querySelectorAll('button'))button.disabled=value;
 if(!value){$('scan').disabled=!scanAvailable;showFiles();}
}
function readUploadFile(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(Error('Cannot read '+file.name));r.readAsDataURL(file);});}
$('scan').onclick=async()=>{
 try{
  const name=$('projectName').value.trim();
  if(!name){$('projectName').setAttribute('aria-invalid','true');$('projectName').focus();throw Error('Enter a project name.');}
  $('projectName').removeAttribute('aria-invalid');
  const files=[...uploadFiles];
  if(!files.length||files.length>MAX_UPLOAD_IMAGES)throw Error('Select 1–'+MAX_UPLOAD_IMAGES+' images first.');
  for(const file of files)if(!file.size||file.size>MAX_IMAGE_BYTES)throw Error('Each image must be at most 25 MB: '+file.name);
  const manifest=files.map(file=>({name:file.name,size:file.size}));
  if(uploadSession&&JSON.stringify(manifest)!==JSON.stringify(uploadSession.files))throw Error('To resume, select the same images in the same order. Use New project for a different batch.');
  setUploading(true);$('notice').textContent='';
  paintScan({status:'scanning',progress:'Preparing your upload…',scan_stats:{stage:'uploading',page_count:files.length,percent:0}});
  $('scanPanel').scrollIntoView({block:'start',behavior:'smooth'});
  if(!uploadSession){const created=await api('/api/upload/create',{name,files:manifest});uploadSession={id:created.id,files:manifest};history.replaceState(null,'','?job='+created.id);}
  else{const saved=await api('/api/workspace?job='+uploadSession.id);if(saved.state.upload_complete){const id=uploadSession.id;uploadSession=null;setUploading(false);await listJobs();await loadJob(id);return;}}
  for(let i=0;i<files.length;i++){
   paintScan({status:'scanning',progress:'Uploading image '+(i+1)+' of '+files.length+' · '+files[i].name,scan_stats:{stage:'uploading',page:i+1,page_count:files.length,percent:100*i/files.length}});
   await api('/api/upload/page',{job:uploadSession.id,index:i,data:await readUploadFile(files[i])});
  }
  const job=await api('/api/upload/finish',{job:uploadSession.id});uploadSession=null;setUploading(false);
  await listJobs();await loadJob(job.id);
 }catch(e){error(e);$('scanPanel').classList.add('hidden');scanDisplay=null;$('progress').textContent=uploadSession?'Uploaded images are saved. Fix the issue and retry to resume this batch.':'';setUploading(false);$('scan').textContent=uploadSession?'Resume upload & scan':'Create project & scan';}
};
$('export').onclick=async()=>{const job=state.id;try{$('export').disabled=true;$('exportStatus').textContent='Preparing Excel with saved corrections and uncertainty markers…';const result=await api('/api/export',{job});if(state?.id!==job)return;const link=document.createElement('a');link.href=result.url;link.download=result.partial?'Pixel-partial.xlsx':'Pixel-converted.xlsx';link.textContent='Download Excel';$('exportStatus').replaceChildren(document.createTextNode(result.partial?'Partial workbook ready · '+result.records+' available records. ':'Workbook ready. '),link);link.click();}catch(e){if(state?.id===job)$('exportStatus').textContent='Export failed: '+e.message;}finally{if(state?.id===job)reviewAvailability();}};
function renderRegionTools(){
 const cell=current(),printed=![0,2,13,25,36].includes(active.field),rectangle=state.field_regions?.[record().key+':'+active.field]?.kind==='rectangles';$('regionTools').classList.toggle('hidden',!printed||rectangle);if(!printed||rectangle)return;
 const refs=cell.segments;regionFirst??=refs[0]?.id??null;regionLast??=refs[refs.length-1]?.id??null;
 for(const id of ['regionStartLine','regionEndLine']){$(id).replaceChildren();record().lines.filter(l=>!l.id.startsWith('crop-')).forEach((line,i)=>{const text=line.segments.map(s=>state.decisions[s.id]??s.text).join('');$(id).add(new Option((i+1)+'. '+text.slice(0,85),line.id));});}
 const lineOf=id=>record().lines.find(l=>l.segments.some(s=>s.id===id));
 if(lineOf(regionFirst))$('regionStartLine').value=lineOf(regionFirst).id;if(lineOf(regionLast))$('regionEndLine').value=lineOf(regionLast).id;
 $('regionStatus').textContent=cell.candidate?'Field boundary needs confirmation.':'Adjust only if this crop includes too much or misses text.';
 const first=entries().find(e=>e.id===regionFirst),last=entries().find(e=>e.id===regionLast);
 $('regionStatus').textContent+=' Start: '+(first?.seg.text||'—')+'; end: '+(last?.seg.text||'—')+'. Select a character and use the start/end buttons to trim precisely.';
 $('regionUse').disabled=cell.manual||!regionFirst||!regionLast;$('regionStart').disabled=cell.manual||!chosen;$('regionEnd').disabled=cell.manual||!chosen;
 $('regionReset').disabled=cell.manual||!state.field_regions?.[record().key+':'+active.field];
}
function previewRegionLines(){
 const lines=record().lines.filter(l=>!l.id.startsWith('crop-')),a=lines.findIndex(l=>l.id===$('regionStartLine').value),b=lines.findIndex(l=>l.id===$('regionEndLine').value);if(a<0||b<a){$('dialogError').textContent='Choose an ending line at or after the starting line.';return;}
 const chosenLines=lines.slice(a,b+1),refs=chosenLines.flatMap(l=>l.segments.map(s=>({id:s.id,line:l.id,editable:true})));
 previewCell={...rows[active.row].cells[active.field],candidate:true,segments:refs,sources:chosenLines.map(l=>({line:l.id,image:l.image,page:l.page,left:0,right:Math.max(...l.box.map(p=>p[0]))-Math.min(...l.box.map(p=>p[0]))})),plain:chosenLines.map(l=>l.segments.map(s=>state.decisions[s.id]??s.text).join('')).join(' ')};
 regionFirst=refs[0]?.id;regionLast=refs[refs.length-1]?.id;chosen=regionFirst;renderCell();
}
$('regionPreview').onclick=()=>{if(discardDraft())previewRegionLines();};
$('regionStart').onclick=()=>{regionFirst=chosen;renderRegionTools();};$('regionEnd').onclick=()=>{regionLast=chosen;renderRegionTools();};
async function saveRegion(reset=false){if(busy||!discardDraft())return;setBusy(true);try{await api('/api/field-region',{job:state.id,record:record().key,field:active.field,first:regionFirst,last:regionLast,reset});previewCell=null;regionFirst=null;regionLast=null;await sync();renderCell();$('saveStatus').textContent=reset?'Field boundary reset.':'Field region saved. Continue correcting individual characters.';}catch(e){error(e);}finally{setBusy(false);renderRegionTools();}}
$('regionUse').onclick=()=>saveRegion();$('regionReset').onclick=()=>saveRegion(true);
const cropPicker=new PixelCropPicker({api,imageURL:(job,name)=>'/image?'+new URLSearchParams({job,name}),
 beforeSubmit:()=>{if(busy||!discardDraft())return false;dirty=false;return true;},
 onReset:()=>saveRegion(true),
 onAvailability:()=>{if(active&&!busy)applyAvailability();},
 onComplete:async task=>{
  if(state?.id!==task.job)return;
  await sync();
  if(state?.id!==task.job)return;
  if(active&&record().key===task.record&&active.field===task.field){previewCell=null;regionFirst=null;regionLast=null;chosen=null;renderCell();$('saveStatus').textContent=task.message;}
 }
});
function configureCropPicker(){const cell=current();cropPicker.configure({job:state.id,record:record().key,field:active.field,fieldName:names[active.field],frames:record().crop_frames||[],saved:state.field_regions?.[record().key+':'+active.field],manual:cell.manual,unmapped:cell.status==='unmapped',printed:![0,2,13,25,36].includes(active.field)});}
const availabilityBase=applyAvailability;
applyAvailability=function(){availabilityBase();if(!active)return;const reading=cropPicker.running({job:state.id,record:record().key,field:active.field});$('confirmField').disabled=!!reading;$('fieldInput').disabled=!!reading;if(reading){for(const id of ['saveCharacter','resetCharacter','charInput','resetField','regionUse','regionReset','regionPreview','regionStart','regionEnd'])$(id).disabled=true;for(const b of $('options').children)b.disabled=true;}cropPicker.availability();};
window.addEventListener('beforeunload',e=>{if(uploading||dirty||cropPicker.hasDraft()){e.preventDefault();e.returnValue='';}});
const drawCoverageBase=drawCoverage;
drawCoverage=function(){drawCoverageBase();const boxes=[...$('coverageList').querySelectorAll('.coverageItem')];let i=0;state.records.forEach((r,ri)=>(r.fragments||[]).forEach((f,fi)=>{const box=boxes[i++];if(!box||(!fi&&projectRow(ri)===1))return;const b=document.createElement('button');b.textContent=fi?'Start a separate record here':'Join this record to the previous one';b.disabled=state.status==='scanning';if(b.disabled)b.title='Record boundaries can be changed after scanning finishes or is cancelled.';b.onclick=async()=>{const question=fi?'Split this continuation into a separate record? Source text and saved character corrections will be retained.':'Join this record to the previous record in the project, which may be on another image? Only do this if the source shows it is a continuation.';if(!window.confirm(question))return;b.disabled=true;try{await api('/api/boundary',{job:state.id,record:r.key,fragment:f.id,action:fi?'split_here':'join_previous'});await loadJob(state.id,state.record_offset||0,state.image_filter);}catch(e){error(e);b.disabled=false;}};box.append(b);}));};
(async()=>{const [schema,capability]=await Promise.all([api('/api/schema'),api('/api/capabilities')]);pilotHeaders=schema.headers;scanAvailable=capability.scan;cancelAvailable=!!capability.cancel_scan;if(!scanAvailable){$('scan').disabled=true;$('files').disabled=true;$('notice').textContent=capability.message;}const jobs=await listJobs();const params=new URLSearchParams(location.search),id=params.get('job'),offset=Number(params.get('offset')||0);if(jobs.some(j=>j.id===id))await loadJob(id,Number.isInteger(offset)&&offset>=0?offset:0,params.get('image'));})().catch(error);
