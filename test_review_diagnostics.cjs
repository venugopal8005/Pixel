/* In-memory component checks: no browser, network, or background service. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

async function main(){
 const elements=new Map(),listeners={},windowListeners={},downloads=[],requests=[],storage=new Map();
 class Element{
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.value='';this.checked=false;this.disabled=false;this.open=false;this.style={};this.textContent='';}
  set id(value){this._id=value;elements.set(value,this);}get id(){return this._id||'';}
  setAttribute(name,value){this[name]=value;}
  append(...children){for(const child of children){this.children.push(child);if(child&&typeof child==='object')child.parentElement=this;}}
  prepend(...children){this.children.unshift(...children);}
  set innerHTML(value){for(const match of value.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"[^>]*>/g)){const child=new Element(match[1]);child.id=match[2];this.append(child);}}
  closest(selector){if(selector==='#testReportDialog')return this.id==='testReportDialog'?this:this.parentElement?.closest(selector)||null;if(selector==='button,a')return ['BUTTON','A'].includes(this.tagName)?this:null;return null;}
  showModal(){this.open=true;}close(){this.open=false;}
  click(){return this.onclick?.();}
 }
 const header=new Element('header'),foot=new Element(),body=new Element('body'),head=new Element('head');
 const document={head,body,createElement:tag=>new Element(tag),createTextNode:text=>({textContent:text}),getElementById:id=>elements.get(id),
   querySelector:selector=>selector==='header'?header:selector==='#reviewDialog .dialogFoot'?foot:null,
   addEventListener:(type,fn)=>{listeners[type]=fn;}};
 const window={PIXEL_TOKEN:'test-session-secret',addEventListener:(type,fn)=>{windowListeners[type]=fn;}};
 const URLshim={createObjectURL:blob=>{downloads.push(blob);return 'blob:local-test';},revokeObjectURL:()=>{}};
 let failFetch=false;
 const sandbox={window,document,URL:URLshim,URLSearchParams,Blob,Date,JSON,Set,Map,Array,Object,String,Math,
   location:{pathname:'/',search:'?job='+'a'.repeat(32)},navigator:{userAgent:'Unit test browser',language:'en',onLine:true},innerWidth:1200,innerHeight:800,devicePixelRatio:1,
   sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},setTimeout:()=>1,clearTimeout:()=>{},AbortController,
   fetch:async(url,options)=>{requests.push({url,options});if(failFetch)throw Error('Server offline');return {ok:true,headers:{get:()=> 'attachment; filename="Pixel-test-example.zip"'},blob:async()=>new Blob(['zip fixture'])};}};
 vm.runInNewContext(fs.readFileSync('review_diagnostics.js','utf8'),sandbox);
 assert.equal(requests.length,0,'Instrumentation must never automatically upload diagnostics');
 const diag=window.PixelDiagnostics;let selected={row_number:3,column_number:9,field_name:'ZIP CODE',segment:'l1-s2'};
 diag.setContext(()=>({job:'a'.repeat(32),project_name:'Test project',selected}));
 const input=new Element('textarea');input.id='fieldInput';input.value='PRIVATE UNSAVED INPUT';listeners.change({target:input});
 windowListeners.unhandledrejection({reason:Error('Example '+window.PIXEL_TOKEN)});
 const snapshot=JSON.stringify(diag.snapshot());
 assert(!snapshot.includes('PRIVATE UNSAVED INPUT'));assert(!snapshot.includes(window.PIXEL_TOKEN));
 assert(snapshot.includes('unhandled_rejection'));
 for(let i=0;i<170;i++)diag.record('test',{index:i});
 assert.equal(diag.snapshot().events.length,150,'Browser history must remain bounded');
 elements.get('testReportButton').click();
 assert(elements.get('testReportDialog').open);assert.equal(elements.get('testReportInclude').checked,false);
 elements.get('testReportFeature').value='Field mapping / source crop';elements.get('testReportOutcome').value='fail';
 elements.get('testReportExpected').value='A ZIP code crop';elements.get('testReportActual').value='The wrong crop';
 selected={row_number:8,column_number:4};
 await elements.get('testReportDownload').click();
 assert.equal(requests.length,1);assert.equal(requests[0].url,'/api/test-report');
 const request=JSON.parse(requests[0].options.body);
 assert.equal(request.context.selected.row_number,3,'Capture the cell where the report was opened');
 assert.equal(request.include_project,false);assert.equal(request.outcome,'fail');
 assert(!requests[0].options.body.includes(window.PIXEL_TOKEN));
 assert.equal(requests[0].options.headers['X-Review-Token'],window.PIXEL_TOKEN);
 assert.equal(downloads.length,1);assert.equal(elements.get('testReportDownload').disabled,false);
 elements.get('testReportClose').click();elements.get('testReportCell').click();
 assert.equal(elements.get('testReportActual').value,'','Do not carry a previous issue into another cell');
 assert.equal(elements.get('testReportOutcome').value,'question');
 failFetch=true;elements.get('testReportInclude').checked=true;
 await elements.get('testReportDownload').click();
 const fallback=JSON.parse(await downloads.at(-1).text());
 assert.equal(fallback.browser_only,true);assert.equal(fallback.project_data_included,false);
 assert.equal(fallback.report_service_error,'Server offline');assert.equal(fallback.context.selected.row_number,8);
 assert.equal(elements.get('testReportDownload').disabled,false);
 assert(elements.get('testReportStatus').textContent.includes('browser-only'));
 console.log('Diagnostic UI component checks passed: no automatic upload, no typed-value/token capture, bounded history, selected-cell snapshot, opt-in attachments, server-offline fallback.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
