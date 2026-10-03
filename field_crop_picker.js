/* Drawing is a draft. Only the explicit field confirmation submits OCR. */
(function(root){
 'use strict';
 const key=c=>[c.job,c.record,c.field].join(':');
 const rectangle=(a,b,frame)=>{
  const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
  const [x,y,r,d]=frame.box;
  const box=[clamp(Math.floor(Math.min(a.x,b.x)),x,r),clamp(Math.floor(Math.min(a.y,b.y)),y,d),clamp(Math.ceil(Math.max(a.x,b.x)),x,r),clamp(Math.ceil(Math.max(a.y,b.y)),y,d)];
  return box[2]-box[0]>=4&&box[3]-box[1]>=4?{fragment:frame.id,box}:null;
 };
 class PixelCropPicker {
  constructor(options){
   Object.assign(this,options);this.context=null;this.drafts=[];this.views=[];this.tasks=new Map();this.generation=0;this.blocked=false;
   this.el=id=>document.getElementById(id);
   this.el('rectConfirm').onclick=()=>this.submit();
   this.el('rectClear').onclick=()=>this.clear();
   this.el('rectReset').onclick=()=>this.onReset();
   this.el('rectEditSaved').onclick=()=>{this.drafts=(this.context.saved?.regions||[]).map(r=>({fragment:r.fragment,box:[...r.box]}));this.message='Saved areas copied to the preview. Remove and redraw any area that needs changing, then confirm.';this.renderDrafts();};
   this.el('rectZoom').onchange=()=>{for(const v of this.views)this.paint(v);};
   this.el('rectTools').ontoggle=()=>{if(this.el('rectTools').open)for(const v of this.views)this.paint(v);};
   let saved=[];try{saved=JSON.parse(sessionStorage.getItem('pixel-field-crops')||'[]');}catch{}
   for(const task of saved){if(task.operation&&task.job){this.tasks.set(key(task),task);this.poll(task);}}
  }
  remember(){try{sessionStorage.setItem('pixel-field-crops',JSON.stringify([...this.tasks.values()].filter(t=>t.status==='running')));}catch{}}
  running(c=this.context){return c&&this.tasks.get(key(c))?.status==='running';}
  hasDraft(){return this.drafts.length>0&&!this.running();}
  clear(){this.drafts=[];this.message='';this.drag=null;this.renderDrafts();}
  configure(c){
   const changed=!this.context||key(c)!==key(this.context);this.context=c;
   this.el('rectTools').classList.toggle('hidden',!c.printed);
   if(changed){
    this.generation++;this.drafts=[];this.views=[];this.drag=null;this.message='';
    this.el('rectFrames').replaceChildren();this.el('rectTools').open=!!c.unmapped;
    this.el('rectHeading').textContent='Draw field area · '+c.fieldName;
    if(c.printed)this.loadFrames(c,this.generation);
   }
   this.el('rectHint').textContent=c.manual?'Reset the whole-field confirmation to change its image area.':!c.frames.length?'This older scan has no record image coordinates. Rescan its original pages to use rectangle selection.':'Draw around only this field. For wrapped text, add separate areas in reading order. Drawing does not save or run OCR.';
   this.el('rectSaved').textContent=c.saved?.kind==='rectangles'?c.saved.regions.length+' saved area(s). The boundary is confirmed; the recognized text still needs review.': '';
   this.renderDrafts();
  }
  loadFrames(c,generation){
   for(const frame of c.frames){
    const wrap=document.createElement('div');wrap.className='rectFrame';
    const caption=document.createElement('p');caption.className='muted';caption.textContent=frame.page+' · record fragment';
    const scroll=document.createElement('div');scroll.className='rectScroll';
    const canvas=document.createElement('canvas');canvas.setAttribute('aria-label','Draw an area for '+c.fieldName+' on '+frame.page);
    const image=new Image(),view={frame,canvas,image,ready:false,caption};this.views.push(view);
    scroll.append(canvas);wrap.append(caption,scroll);this.el('rectFrames').append(wrap);
    image.onload=()=>{if(generation!==this.generation)return;view.ready=true;this.paint(view);this.availability();};
    image.onerror=()=>{if(generation!==this.generation)return;caption.textContent+=' · image unavailable; reopen this cell to retry';};
    image.src=this.imageURL(c.job,frame.file);
    canvas.onpointerdown=e=>{
     if(e.button!==0||!view.ready||this.blocked||this.context.manual||this.running())return;
     if(this.drafts.length>=8){this.message='Up to 8 areas per field. Remove an area before drawing another.';this.renderDrafts();return;}
     e.preventDefault();canvas.setPointerCapture(e.pointerId);this.drag={view,start:this.point(e,view),end:this.point(e,view)};this.paint(view);
    };
    canvas.onpointermove=e=>{if(this.drag?.view!==view)return;this.drag.end=this.point(e,view);this.paint(view);};
    canvas.onpointerup=e=>{
     if(this.drag?.view!==view)return;
     const selected=rectangle(this.drag.start,this.point(e,view),frame);this.drag=null;
     if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);
     if(selected)this.addDraft(selected);else{this.message='That area is too small. Draw around the complete field text.';this.renderDrafts();}
    };
    canvas.onpointercancel=()=>{this.drag=null;this.paint(view);};
   }
  }
  point(e,v){const b=v.canvas.getBoundingClientRect(),f=v.frame.box;return {x:f[0]+(e.clientX-b.left)/b.width*(f[2]-f[0]),y:f[1]+(e.clientY-b.top)/b.height*(f[3]-f[1])};}
  addDraft(selected){
   const frame=this.context.frames.find(f=>f.id===selected.fragment),[x,y,r,b]=selected.box;
   if(this.drafts.some(d=>{const f=this.context.frames.find(v=>v.id===d.fragment),[dx,dy,dr,db]=d.box;return f.page===frame.page&&Math.min(dr,r)>Math.max(dx,x)&&Math.min(db,b)>Math.max(dy,y);})){this.message='Areas overlap. Remove the earlier area before replacing it.';}
   else{this.drafts.push(selected);this.message='Selection preview only. Check the areas below, then confirm for '+this.context.fieldName+'.';}
   this.renderDrafts();
  }
  paint(v){
   if(!v.ready)return;
   const [x,y,r,b]=v.frame.box,w=r-x,h=b-y,scale=Number(this.el('rectZoom').value)||Math.min(2,Math.max(.25,((v.canvas.parentElement?.clientWidth||860)-2)/w));
   v.canvas.width=Math.round(w*scale);v.canvas.height=Math.round(h*scale);
   const ctx=v.canvas.getContext('2d');ctx.drawImage(v.image,x,y,w,h,0,0,v.canvas.width,v.canvas.height);
   const draw=(box,label,color)=>{const [a,c,d,e]=box;ctx.strokeStyle=color;ctx.lineWidth=2;ctx.fillStyle=color+'22';ctx.fillRect((a-x)*scale,(c-y)*scale,(d-a)*scale,(e-c)*scale);ctx.strokeRect((a-x)*scale,(c-y)*scale,(d-a)*scale,(e-c)*scale);ctx.fillStyle=color;ctx.font='bold 15px system-ui';ctx.fillText(label,(a-x)*scale+3,Math.max(16,(c-y)*scale-4));};
   if(!this.drafts.length)for(const d of this.context.saved?.regions||[])if(d.fragment===v.frame.id)draw(d.box,'Saved','#309274');
   this.drafts.forEach((d,i)=>{if(d.fragment===v.frame.id)draw(d.box,String(i+1),'#245edb');});
   if(this.drag?.view===v){const d=rectangle(this.drag.start,this.drag.end,v.frame);if(d)draw(d.box,'Preview','#dc7c16');}
  }
  renderDrafts(){
   if(!this.context)return;
   for(const v of this.views)this.paint(v);
   const list=this.el('rectDrafts');list.replaceChildren();
   this.drafts.forEach((d,i)=>{
    const item=document.createElement('li'),v=this.views.find(v=>v.frame.id===d.fragment);
    const label=document.createElement('p');label.textContent=(i+1)+'. '+v.frame.page+' · '+d.box.join(', ');label.className='muted';item.append(label);
    if(v.ready){const preview=document.createElement('canvas'),[x,y,r,b]=d.box,scale=Math.min(4,90/(b-y));preview.width=Math.ceil((r-x)*scale);preview.height=Math.ceil((b-y)*scale);preview.getContext('2d').drawImage(v.image,x,y,r-x,b-y,0,0,preview.width,preview.height);item.append(preview);}
    const controls=document.createElement('div');controls.className='row';
    for(const [label,action,disabled] of [['Move earlier',()=>{[this.drafts[i-1],this.drafts[i]]=[d,this.drafts[i-1]];},i===0],['Move later',()=>{[this.drafts[i],this.drafts[i+1]]=[this.drafts[i+1],d];},i===this.drafts.length-1],['Remove',()=>this.drafts.splice(i,1),false]]){
     const button=document.createElement('button');button.textContent=label;button.disabled=disabled||this.running()||this.blocked;button.onclick=()=>{action();this.renderDrafts();};controls.append(button);
    }
    item.append(controls);list.append(item);
   });
   const task=this.tasks.get(key(this.context));
   this.el('rectStatus').textContent=task?.status==='running'?task.message:this.message|| (task?.status==='error'?task.message:'');
   this.el('rectStatus').classList.toggle('error',task?.status==='error');
   const progress=this.el('rectProgress');progress.classList.toggle('hidden',!this.running());progress.max=task?.total||1;
   if(task?.stage==='reading')progress.value=task.completed;else progress.removeAttribute('value');
   this.availability();
  }
  availability(){
   if(!this.context)return;const stopped=this.blocked||this.running()||this.context.manual;
   this.el('rectConfirm').textContent='Confirm selection for '+this.context.fieldName+' & read text';
   this.el('rectConfirm').disabled=!!stopped||!this.drafts.length;
   this.el('rectClear').disabled=!!stopped||!this.drafts.length;
   this.el('rectReset').disabled=!!stopped||this.context.saved?.kind!=='rectangles';
   this.el('rectReset').classList.toggle('hidden',this.context.saved?.kind!=='rectangles');
   this.el('rectEditSaved').disabled=!!stopped||!!this.drafts.length;
   this.el('rectEditSaved').classList.toggle('hidden',this.context.saved?.kind!=='rectangles');
  }
  async submit(){
   if(this.blocked||this.running()||!this.drafts.length||this.context.manual||!this.beforeSubmit())return;
   const c={...this.context},regions=this.drafts.map(d=>({...d,box:[...d.box]}));
   // Reserve before the request returns: double clicks never launch two scans.
   const pending={job:c.job,record:c.record,field:c.field,status:'running',message:'Sending confirmed selection…',total:regions.length};
   this.tasks.set(key(c),pending);this.renderDrafts();this.onAvailability();
   try{const task=await this.api('/api/field-crop',{job:c.job,record:c.record,field:c.field,regions,confirmed:true});this.tasks.set(key(c),task);this.remember();this.poll(task);}
   catch(e){this.tasks.set(key(c),{...pending,status:'error',message:e.message});this.remember();if(key(this.context)===key(c))this.renderDrafts();this.onAvailability();}
  }
  async poll(task){
   try{
    const updated=await this.api('/api/field-crop-status?'+new URLSearchParams({job:task.job,operation:task.operation}));
    this.tasks.set(key(task),updated);this.remember();
    if(this.context&&key(this.context)===key(task))this.renderDrafts();
    if(updated.status==='running'){setTimeout(()=>this.poll(updated),800);return;}
    if(updated.status==='complete'){
     if(this.context&&key(this.context)===key(task)){this.drafts=[];this.message=updated.message;this.el('rectTools').open=false;}
     await this.onComplete(updated);
    }
    this.onAvailability();
   }catch(e){
    if(e.message.startsWith('This crop scan is no longer available')){this.tasks.set(key(task),{...task,status:'error',message:e.message});this.remember();this.onAvailability();}
    else{task.message='Waiting for the local field reader to reconnect…';setTimeout(()=>this.poll(task),2500);}
    if(this.context&&key(this.context)===key(task))this.renderDrafts();
   }
  }
 }
 root.PixelCropPicker=PixelCropPicker;
 if(typeof module!=='undefined')module.exports={PixelCropPicker,rectangle};
})(typeof window!=='undefined'?window:globalThis);
