/* Explicitly downloaded, local test reports. No automatic uploads or input-value logging. */
(() => {
  'use strict';
  const key='pixel-test-events-v1', maxEvents=150;
  let contextProvider=null, contextAtOpen=null, events=[], startedAt=new Date().toISOString();
  function clean(value,depth=0){
    if(depth>7)return '[depth limit]';
    if(typeof value==='string')return (window.PIXEL_TOKEN?value.split(window.PIXEL_TOKEN).join('[session token removed]'):value).slice(0,6000);
    if(Array.isArray(value))return value.slice(-200).map(v=>clean(v,depth+1));
    if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).slice(0,100).filter(([k])=>!['token','password','authorization','cookie','pixel_token','x-review-token'].includes(k.toLowerCase())).map(([k,v])=>[k,clean(v,depth+1)]));
    return value;
  }
  try{const saved=JSON.parse(sessionStorage.getItem(key));if(Array.isArray(saved?.events)){events=saved.events.slice(-maxEvents);startedAt=saved.startedAt||startedAt;}}catch{}
  function context(){try{return clean(contextProvider?contextProvider():{job:new URLSearchParams(location.search).get('job')});}catch(e){return {context_error:String(e),job:new URLSearchParams(location.search).get('job')};}}
  function record(kind,details={}){
    events.push(clean({time:new Date().toISOString(),kind,...details}));events=events.slice(-maxEvents);
    try{sessionStorage.setItem(key,JSON.stringify({startedAt,events}));}catch{}
  }
  window.PixelDiagnostics={record,setContext:provider=>{contextProvider=provider;},snapshot:()=>({events:clean(events),context:context()})};
  record('page_loaded',{path:location.pathname,job:new URLSearchParams(location.search).get('job')});
  window.addEventListener('error',event=>{
    if(event.error||event.message)record('browser_error',{message:event.message,stack:event.error?.stack,line:event.lineno,column:event.colno});
    else if(event.target!==window)record('resource_error',{tag:event.target.tagName,source:String(event.target.src||'').split('?')[0]});
  },true);
  window.addEventListener('unhandledrejection',event=>record('unhandled_rejection',{message:String(event.reason?.message||event.reason),stack:event.reason?.stack}));
  document.addEventListener('click',event=>{
    const el=event.target.closest?.('button,a');if(!el||el.closest('#testReportDialog'))return;
    const current=context();
    record('click',{control:el.id||el.parentElement?.id||el.tagName.toLowerCase(),
      row:el.dataset.row,field:el.dataset.field,segment:el.dataset.segment,
      option_index:el.parentElement?.id==='options'?[...el.parentElement.children].indexOf(el):undefined,
      job:current.job,selected:current.selected});
  },true);
  document.addEventListener('change',event=>{
    const el=event.target;if(!el.id||el.closest('#testReportDialog'))return;
    // Record control identity only. Never log typed field/character text or file bytes.
    record('control_changed',{control:el.id,checked:el.type==='checkbox'?el.checked:undefined});
  });
  const style=document.createElement('style');style.textContent=`
    #testReportButton{margin-left:auto;white-space:nowrap}#testReportDialog{width:min(740px,95vw)}
    #testReportDialog label{display:block;margin:15px 0 6px}#testReportDialog textarea{min-height:65px}
    #testReportDialog select{max-width:100%}#testReportStatus{overflow-wrap:anywhere;white-space:pre-wrap}
    #testReportIncludeLabel{display:flex!important;align-items:flex-start;gap:8px;font-size:13px}
    @media(max-width:700px){header{flex-wrap:wrap}#testReportButton{margin-left:0}}
  `;document.head.append(style);
  const dialog=document.createElement('dialog');dialog.id='testReportDialog';dialog.setAttribute('aria-labelledby','testReportTitle');
  dialog.innerHTML=`<div class="dialogHead"><div class="row between"><h2 id="testReportTitle">Test report</h2><button id="testReportClose" class="close" aria-label="Close test report">×</button></div></div>
    <div class="dialogBody"><p>Record a pass, a failure, or something you are unsure about. Download the report and attach it in our chat.</p>
    <p id="testReportContext" class="muted"></p>
    <label for="testReportFeature">What were you testing?</label><select id="testReportFeature">
      <option>Project creation / upload</option><option>Scan / progress / retry</option><option>Record boundaries / continuation</option>
      <option>Field mapping / source crop</option><option>Character correction</option><option>Save / reload / navigation</option>
      <option>Excel export</option><option>Layout / appearance</option><option>Other</option></select>
    <label for="testReportOutcome">Result</label><select id="testReportOutcome"><option value="question">Unsure / question</option><option value="pass">Pass</option><option value="fail">Fail</option></select>
    <label for="testReportExpected">What did you expect?</label><textarea id="testReportExpected" maxlength="4000" placeholder="For example: show only the ZIP-code crop."></textarea>
    <label for="testReportActual">What happened? Include any steps needed to repeat it.</label><textarea id="testReportActual" maxlength="4000" placeholder="For example: I opened row 3, ZIP CODE, but the crop showed the full record."></textarea>
    <label id="testReportIncludeLabel"><input id="testReportInclude" type="checkbox"><span>Include this project's source images, OCR, saved corrections, and any existing Excel export. These can contain client data.</span></label>
    <p class="muted">The basic report includes filenames, selected cell, recent actions/errors, browser details, and app version. It does not record your screen or unsaved text. Add a screenshot for visual problems. Nothing is sent automatically.</p>
    <p id="testReportStatus" role="status" aria-live="polite"></p></div>
    <div class="dialogFoot row between"><span class="muted">Saved locally when the server is reachable.</span><button id="testReportDownload" class="primary">Download test report</button></div>`;
  document.body.append(dialog);
  const byId=id=>document.getElementById(id);
  function openReport(){
    contextAtOpen=context();byId('testReportInclude').checked=false;byId('testReportInclude').disabled=!contextAtOpen.job;
    byId('testReportOutcome').value='question';byId('testReportExpected').value='';byId('testReportActual').value='';
    byId('testReportContext').textContent=(contextAtOpen.project_name?'Project: '+contextAtOpen.project_name:contextAtOpen.job?'Project: '+contextAtOpen.job:'No saved project selected')+
      (contextAtOpen.selected?' · Row '+contextAtOpen.selected.row_number+' · Column '+contextAtOpen.selected.column_number+' · '+(contextAtOpen.selected.field_name||''):'');
    byId('testReportStatus').textContent='';
    if(contextAtOpen.selected)byId('testReportFeature').value='Field mapping / source crop';
    if(!dialog.open)dialog.showModal();
  }
  const mainButton=document.createElement('button');mainButton.id='testReportButton';mainButton.textContent='Test report';mainButton.onclick=openReport;document.querySelector('header').append(mainButton);
  const cellButton=document.createElement('button');cellButton.id='testReportCell';cellButton.textContent='Report this cell';cellButton.onclick=openReport;document.querySelector('#reviewDialog .dialogFoot')?.prepend(cellButton);
  byId('testReportClose').onclick=()=>dialog.close();
  function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.textContent='Download again';byId('testReportStatus').append(document.createTextNode(' '),a);a.click();setTimeout(()=>URL.revokeObjectURL(url),300000);}
  byId('testReportDownload').onclick=async()=>{
    const button=byId('testReportDownload');button.disabled=true;byId('testReportStatus').textContent='Preparing the local report…';
    const request=clean({job:contextAtOpen?.job||null,test:byId('testReportFeature').value,outcome:byId('testReportOutcome').value,
      expected:byId('testReportExpected').value,actual:byId('testReportActual').value,include_project:byId('testReportInclude').checked,
      browser:{user_agent:navigator.userAgent,language:navigator.language,viewport:{width:innerWidth,height:innerHeight},device_pixel_ratio:devicePixelRatio,online:navigator.onLine,tab_session_started:startedAt},
      context:contextAtOpen,events:events.slice(-maxEvents)});
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),60000);
    try{
      const response=await fetch('/api/test-report',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':window.PIXEL_TOKEN},body:JSON.stringify(request),signal:controller.signal});
      if(!response.ok){let reason='Report service returned HTTP '+response.status;try{reason=(await response.json()).error||reason;}catch{}throw Error(reason);}
      const blob=await response.blob(),name=response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]||'Pixel-test-report.zip';
      byId('testReportStatus').textContent='Report prepared: '+name+'. Attach this file in our chat. A copy is saved in outputs/review-app/_diagnostics/reports.';
      download(blob,name);record('test_report_created',{file:name,outcome:request.outcome,test:request.test});
    }catch(error){
      const fallback={...request,browser_only:true,captured_at:new Date().toISOString(),report_service_error:String(error.message||error),project_data_included:false};
      byId('testReportStatus').textContent='The server report could not be created. Downloading browser-only details instead; images, saved project data, and server logs are not included. '+fallback.report_service_error;
      download(new Blob([JSON.stringify(clean(fallback),null,2)],{type:'application/json'}),'Pixel-browser-report-'+Date.now()+'.json');
    }finally{clearTimeout(timeout);button.disabled=false;}
  };
})();
