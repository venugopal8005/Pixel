"""Confirmed image regions and a bounded local OCR worker for field recovery."""
import copy
import hashlib
import json
import math
import queue
import re
import threading
import time
import uuid
from datetime import datetime,timezone

import numpy as np
from PIL import Image
from character_review import read_line
from field_constraints import PRINTED
from scan_state import record_ready

MAX_REGIONS=8
ASSET=re.compile(r'(?:line-\d+|page-\d+|crop-[a-f0-9]{32}-\d+|selection-[a-f0-9]{32}-\d+)\.png')


def frames(state,record):
    pages={p['name']:p['file'] for p in state['pages']}
    result=[dict(id=f['id'],page=f['page'],file=pages[f['page']],box=list(f['box']))
            for f in record.get('fragments',[]) if f['page'] in pages]
    if not result:
        # Older scans sometimes retain page coordinates but no fragment objects.
        for page,file in pages.items():
            boxes=[l['source_box'] for l in record['lines'] if l['page']==page and l.get('source_box')]
            if boxes:result.append(dict(id='legacy-'+str(len(result)),page=page,file=file,
                box=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]))
    return result


def target(state,record_key,field):
    if type(field) is not int or field not in PRINTED:raise ValueError('Select a printed field.')
    record=next((r for r in state['records'] if r['key']==record_key),None)
    if record is None:raise ValueError('This record no longer exists. Reopen the project.')
    if not record_ready(state,record):raise ValueError('This record is still being scanned or waiting for its continuation.')
    key=record_key+':'+str(field)
    if key in state.get('field_decisions',{}):raise ValueError('Reset the whole-field confirmation before changing its image selection.')
    return record,key


def validate_regions(state,record,regions,directory):
    if not isinstance(regions,list) or not 1<=len(regions)<=MAX_REGIONS:
        raise ValueError(f'Draw between 1 and {MAX_REGIONS} areas for this field.')
    available={f['id']:f for f in frames(state,record)};result=[];pixels=0
    for region in regions:
        frame=available.get(region.get('fragment')) if isinstance(region,dict) else None
        if not frame:raise ValueError('The selected area does not belong to this record.')
        box=region.get('box')
        if not isinstance(box,list) or len(box)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in box):
            raise ValueError('Invalid selection coordinates. Draw the area again.')
        x,y,r,b=box;fx,fy,fr,fb=frame['box']
        if x<fx or y<fy or r>fr or b>fb or r-x<4 or b-y<4:
            raise ValueError('Keep each selection inside the record and at least 4 pixels wide and high.')
        box=[math.floor(x),math.floor(y),math.ceil(r),math.ceil(b)];x,y,r,b=box
        if not ASSET.fullmatch(frame['file']):raise ValueError('Invalid source image.')
        with Image.open(directory/frame['file']) as image:
            if x<0 or y<0 or r>image.width or b>image.height:raise ValueError('Selection exceeds the original image.')
        pixels+=(r-x)*(b-y)
        if pixels>2_000_000:raise ValueError('Select only the field. The combined area is too large.')
        for prior in result:
            px,py,pr,pb=prior['box']
            if prior['page']==frame['page'] and min(pr,r)>max(px,x) and min(pb,b)>max(py,y):
                raise ValueError('Selected areas overlap. Remove the duplicate area to avoid repeated text.')
        result.append(dict(fragment=frame['id'],page=frame['page'],file=frame['file'],box=box,record_box=frame['box']))
    return result


def revision(state,record,field):
    """Reject stale results instead of overwriting a concurrent human edit."""
    key=record['key']+':'+str(field)
    ids={s['id'] for l in record['lines'] for s in l['segments']}
    selection=state.get('field_regions',{}).get(key)
    ids.update(s['id'] for l in (selection or {}).get('lines',[]) for s in l['segments'])
    payload=[frames(state,record),selection,state.get('field_decisions',{}).get(key),
             {k:v for k,v in state['decisions'].items() if k in ids}]
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def archive_selection(state,key):
    previous=state.get('field_regions',{}).get(key)
    if previous and previous.get('kind')=='rectangles':
        state.setdefault('field_crop_history',[]).append(dict(field=key,selection=copy.deepcopy(previous)))


def text_rows(boxes):
    """Merge same-row detections, including overlapping duplicate word boxes."""
    rows=[]
    for box in sorted(boxes,key=lambda b:((b[1]+b[3])/2,b[0])):
        x,y,r,b=box
        matches=[row for row in rows if min(b,row[3])-max(y,row[1])>=.6*min(b-y,row[3]-row[1])
                 and abs((y+b)-(row[1]+row[3]))/2<=.45*max(b-y,row[3]-row[1])]
        if matches:
            row=matches[0];row[:]=[min(x,row[0]),min(y,row[1]),max(r,row[2]),max(b,row[3])]
        else:rows.append(list(box))
    return sorted(rows,key=lambda b:(b[1],b[0]))


def recognize_regions(engine,directory,operation,regions,progress):
    result=[];annotated=[]
    for index,region in enumerate(regions):
        progress(stage='reading',message=f'Reading selected area {index+1} of {len(regions)}',completed=index,total=len(regions))
        with Image.open(directory/region['file']) as source:
            width,height=source.size;crop=source.crop(region['box']).convert('RGB')
        name=f'selection-{operation}-{index}.png';crop.save(directory/name)
        fx,fy,fr,fb=region['record_box'];x,y,r,b=region['box']
        annotated.append(dict(region,crop_image=name,
            normalized_box=[region['box'][0]/width,region['box'][1]/height,region['box'][2]/width,region['box'][3]/height],
            record_normalized_box=[(x-fx)/(fr-fx),(y-fy)/(fb-fy),(r-fx)/(fr-fx),(b-fy)/(fb-fy)],
            image_sha256=hashlib.sha256((directory/name).read_bytes()).hexdigest()))
        detected,_=engine(np.asarray(crop)[:,:,::-1].copy(),use_rec=False,use_cls=False)
        boxes=[]
        for points in ([] if detected is None else list(detected)):
            pts=np.asarray(points)
            box=[max(0,int(pts[:,0].min())-2),max(0,int(pts[:,1].min())-2),
                 min(crop.width,int(pts[:,0].max())+3),min(crop.height,int(pts[:,1].max())+3)]
            if box[2]>box[0] and box[3]>box[1]:boxes.append(box)
        boxes=text_rows(boxes)
        # Read a single selected line once in full. A detector can split a short
        # number into overlapping words, which would otherwise duplicate digits.
        # No detections still get a recognition attempt (and an [?] on failure).
        if len(boxes)<=1:boxes=[[0,0,crop.width,crop.height]]
        if len(boxes)>80:raise ValueError('Too many text regions. Select only this field and try again.')
        for box in boxes:
            line_image=crop.crop(box);line_index=len(result);line_id=f'crop-{operation}-{line_index}'
            line_image.save(directory/(line_id+'.png'));segments=read_line(engine,line_image)
            for i,segment in enumerate(segments):segment['id']=line_id+'-s'+str(i)
            x,y,r,b=box;ox,oy=region['box'][:2]
            result.append(dict(id=line_id,image=line_id+'.png',page=region['page'],fragment=region['fragment'],
                selection_index=index,segments=segments,box=[[x,y],[r,y],[r,b],[x,b]],source_box=[ox+x,oy+y,ox+r,oy+b]))
    return dict(kind='rectangles',id=operation,regions=annotated,lines=result,
                first=result[0]['segments'][0]['id'],last=result[-1]['segments'][-1]['id'],
                confirmed_at=datetime.now(timezone.utc).isoformat(),text_confirmed=False)


class CropService:
    """One warm OCR engine; no page-scan queue or state lock held during OCR."""
    def __init__(self,load,save,folder,lock,write_examples,engine_factory=None,recognizer=recognize_regions):
        self.load,self.save,self.folder,self.state_lock,self.write_examples=load,save,folder,lock,write_examples
        self.engine_factory=engine_factory or self.create_engine;self.recognizer=recognizer
        self.lock=threading.Lock();self.queue=queue.Queue(maxsize=8);self.tasks={};self.worker=None

    @staticmethod
    def create_engine():
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,text_score=0)

    def submit(self,data):
        if data.get('confirmed') is not True:raise ValueError('Confirm the selected areas for this field before running OCR.')
        job=data['job'];field=data['field'];record_key=data['record']
        with self.state_lock:
            state=self.load(job);record,key=target(state,record_key,field)
            regions=validate_regions(state,record,data.get('regions'),self.folder(job));version=revision(state,record,field)
        with self.lock:
            self.tasks={k:v for k,v in self.tasks.items() if v['status']=='running' or time.time()-v['updated']<3600}
            for task in self.tasks.values():
                if (task['job'],task['record'],task['field'])==(job,record_key,field) and task['status']=='running':
                    if task['regions']==regions:return self.public(task)
                    raise ValueError('This field already has a crop scan in progress.')
            operation=uuid.uuid4().hex
            task=dict(operation=operation,job=job,record=record_key,field=field,status='running',stage='queued',
                message='Waiting for the field reader',regions=regions,revision=version,updated=time.time(),completed=0,total=len(regions))
            try:self.queue.put_nowait(task)
            except queue.Full:raise ValueError('The field reader is busy. Please try again when a selection finishes.')
            self.tasks[operation]=task
            if self.worker is None or not self.worker.is_alive():
                self.worker=threading.Thread(target=self.run,daemon=True,name='pixel-field-crops');self.worker.start()
            return self.public(task)

    @staticmethod
    def public(task):
        return {k:task[k] for k in ('operation','job','record','field','status','stage','message','completed','total')}

    def status(self,job,operation):
        with self.lock:
            task=self.tasks.get(operation)
            if not task or task['job']!=job:raise ValueError('This crop scan is no longer available. Reopen the field; if its selection was not saved, draw it again.')
            return self.public(task)

    def run(self):
        engine=None
        while True:
            task=self.queue.get()
            if task is None:self.queue.task_done();return
            def progress(**values):
                with self.lock:task.update(values,updated=time.time())
            try:
                if engine is None:
                    progress(stage='loading',message='Loading the local field reader')
                    engine=self.engine_factory()
                selection=self.recognizer(engine,self.folder(task['job']),task['operation'],task['regions'],progress)
                progress(stage='saving',message='Saving field crop and character readings')
                warning=''
                with self.state_lock:
                    state=self.load(task['job']);record,key=target(state,task['record'],task['field'])
                    if revision(state,record,task['field'])!=task['revision']:
                        raise ValueError('This record was edited while OCR ran. Your saved edits were kept. Reopen the field and try the selection again.')
                    archive_selection(state,key)
                    state.setdefault('field_regions',{})[key]=selection
                    state['history'].append(dict(field_crop=key,selection=selection['id'],regions=task['regions']))
                    self.save(state)
                    try:self.write_examples(state,self.folder(task['job']))
                    except OSError:
                        # The confirmed region and OCR are already durable in state.
                        warning=' Learning-data summary could not be written; the saved mapping is retained in the project.'
                progress(status='complete',stage='complete',message='Selection saved. Review the recognized characters.'+warning,completed=task['total'])
            except Exception as error:
                progress(status='error',stage='error',message=str(error))
            finally:self.queue.task_done()
