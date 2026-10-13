"""Local v1: ordered image upload, character evidence, persisted review and Excel export."""
import base64,io,json,re,secrets,subprocess,threading,uuid,hashlib,time,shutil
from datetime import datetime
import sys,webbrowser,traceback
import urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import numpy as np
from PIL import Image
from character_review import read_line,render_segments
from learning_data import write_examples
from extract_text_fields import locate as text_fields
from extract_dates_postal import locate as date_fields
from extract_reference_codes import find_span
from extract_fields import locate as numeric_fields
from pilot_rules import HEADERS,decorate,adjacent_pages
from field_constraints import field_coverage
from field_regions import candidate_for,selected_region,review_record
from field_crop import CropService,frames as crop_frames,archive_selection,ASSET
import diagnostics
from batch_upload import BatchUpload
from scan_state import REVIEW_KEYS,record_ready,ready_records,completed_pages,export_snapshot

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'outputs/review-app';DATA.mkdir(parents=True,exist_ok=True)
LOCK=threading.RLock();SCAN_LOCK=threading.Lock();TOKEN=secrets.token_urlsafe(32)
LIVE_PROGRESS={}
SCAN_CANCEL=set();EXPORT_LOCKS={}
NODE=Path('C:/Users/Dwight/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
BUILD=diagnostics.build_info(ROOT)

def diagnostic_event(kind,**details):
    diagnostics.log_event(DATA/'_diagnostics',kind,token=TOKEN,**details)

def folder(job):
    if not re.fullmatch('[a-f0-9]{32}',job):raise ValueError('Invalid job')
    return DATA/job

def save(state):
    # Windows readers can prevent replacement. Serialize our own reads/writes and
    # retry brief external locks without truncating the last good checkpoint.
    with LOCK:
        target=folder(state['id'])/'state.json';tmp=target.with_name('state-'+uuid.uuid4().hex+'.tmp')
        tmp.write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8')
        for attempt in range(9):
            try:tmp.replace(target);break
            except PermissionError:
                if attempt==8:raise
                time.sleep(min(.025*2**attempt,.4))
        summary=job_summary(state)
        meta=target.with_name('summary-'+uuid.uuid4().hex+'.tmp')
        try:
            meta.write_text(json.dumps(summary),encoding='utf-8')
            meta.replace(target.with_name('summary.json'))
        except OSError:
            # A cache failure must not invalidate the saved OCR/corrections.
            try:meta.unlink(missing_ok=True)
            except OSError:pass

def load(job):
    with LOCK:return json.loads((folder(job)/'state.json').read_text(encoding='utf-8'))

def review_state(state):
    return dict(state,records=[dict(review_record(state,r),crop_frames=crop_frames(state,r)) for r in state['records']])

def job_summary(s):
    return dict(id=s['id'],name=s.get('project_name','Saved scan '+s['id'][:8]),status=s['status'],progress=s.get('progress',''),
        pages=len(s['pages']),records=len(s['records']),created=s.get('created_at',''))

def list_jobs():
    with LOCK:
        summaries=[]
        for p in sorted(DATA.glob('*/state.json'),key=lambda p:p.stat().st_mtime,reverse=True):
            meta=p.with_name('summary.json')
            try:
                if meta.stat().st_mtime_ns<p.stat().st_mtime_ns:raise ValueError('Stale summary')
                summaries.append(json.loads(meta.read_text(encoding='utf-8')))
            except (OSError,ValueError):summaries.append(job_summary(load(p.parent.name)))
        return summaries

def enqueue_scan(state):
    if not state['records']:state.update(progressive_scan=True,completed_pages=0)
    publish_progress(state,'queued',page_count=len(state['pages']),queued_at=state.get('scan_stats',{}).get('queued_at',time.time()))
    save(state)
    threading.Thread(target=scan,args=(state,),daemon=True).start()

def save_scan_state(state):
    """The scanner owns OCR, while reviewers own corrections and crop selections."""
    with LOCK:
        try:latest=load(state['id'])
        except FileNotFoundError:latest={}
        for key in REVIEW_KEYS:
            if key in latest:state[key]=latest[key]
        if latest.get('cancel_requested'):state['cancel_requested']=True
        state['review_revision']=max(state.get('review_revision',0),latest.get('review_revision',0))+1
        stats=state.setdefault('scan_stats',{})
        stats.update(ready_records=len(ready_records(state)),completed_pages=completed_pages(state),review_revision=state['review_revision'])
        if state['status'] in ('ready','cancelled','error'):
            stats['stage']='complete' if state['status']=='ready' else state['status']
            if state['status']=='ready':stats['percent']=100
            else:stats['percent']=min(99,stats.get('percent',0))
        if stats.get('started_at'):stats['elapsed_seconds']=round(time.time()-stats['started_at'],1)
        save(state)

def check_scan_cancel(state):
    from scan_pipeline import ScanCancelled
    if state['id'] in SCAN_CANCEL or state.get('cancel_requested'):raise ScanCancelled()

def cancel_scan(job):
    with LOCK:
        state=load(job)
        if state['status']!='scanning':return progress_snapshot(state)
        SCAN_CANCEL.add(job);state['cancel_requested']=True
        state['scan_stats']=dict(get_progress(job).get('scan_stats',{}))
        state['progress']='Cancelling the scan; finishing the current OCR operation. Saved results will be kept.'
        save(state);publish_progress(state,'cancelling')
        return progress_snapshot(state)

def progress_snapshot(state):
    return dict(id=state['id'],status=state['status'],progress=state.get('progress',''),
        error=state.get('error'),scan_stats=dict(state.get('scan_stats',{})))

def publish_progress(state,stage,**values):
    stats=state.setdefault('scan_stats',{})
    stats.update(stage=stage,**values)
    if 'started_at' in stats:stats['elapsed_seconds']=round(time.time()-stats['started_at'],1)
    stats['updated_at']=time.time()
    with LOCK:
        snapshot=progress_snapshot(state)
        if state['id'] in SCAN_CANCEL and state['status']=='scanning':
            snapshot['scan_stats']['stage']='cancelling'
            snapshot['progress']='Cancelling the scan; finishing the current OCR operation. Saved results will be kept.'
        LIVE_PROGRESS[state['id']]=snapshot

def get_progress(job):
    folder(job) # Validate even when using an in-memory snapshot.
    with LOCK:return LIVE_PROGRESS.get(job) or progress_snapshot(load(job))

def retry_scan(source):
    if source['status'] not in ('error','cancelled'):raise ValueError('Only a stopped scan can be retried')
    job=uuid.uuid4().hex;directory=folder(job);directory.mkdir()
    now=datetime.now().astimezone()
    state=dict(id=job,project_name=source.get('project_name','Saved scan')+' · retry',schema_version=source.get('schema_version',2),
        created_at=now.isoformat(),created_date=now.strftime('%m/%d/%Y'),status='scanning',progress='Waiting for the local scanner',
        pages=[dict(p) for p in source['pages']],records=[],decisions={},history=[],page_issues=[],recovery_of=source['id'])
    for page in state['pages']:shutil.copy2(folder(source['id'])/page['file'],directory/page['file'])
    save(state);enqueue_scan(state)
    return state

def change_boundary(state,key,action,fragment_id=None):
    index=next((i for i,r in enumerate(state['records']) if r['key']==key),None)
    if index is None:raise ValueError('Unknown record')
    record=state['records'][index]
    affected=[record]
    if action=='join_previous':
        if index==0:raise ValueError('This is the first record')
        affected.insert(0,state['records'][index-1])
    elif action!='split_here':raise ValueError('Unknown boundary action')
    if any(k.startswith(r['key']+':') for k in state.get('field_decisions',{}) for r in affected):
        raise ValueError('These records have whole-field corrections. Reset those confirmations before changing their boundary; character corrections are retained.')
    if any(k.startswith(r['key']+':') for k in state.get('field_regions',{}) for r in affected):
        raise ValueError('These records have selected field regions. Reset those regions before changing the record boundary; character corrections are retained.')
    if not all(r.get('fragments') for r in affected):raise ValueError('This older scan has no fragment boundaries; rescan to adjust records.')
    if action=='join_previous':
        previous=affected[0];record['fragments'][0]['status']='continuation_confirmed_by_user'
        previous['fragments'].extend(record['fragments']);previous['lines'].extend(record['lines'])
        previous['notes'].extend(record['notes']);previous['notes'].append('Record boundary joined by user.')
        state['records'].pop(index)
    else:
        cut=next((i for i,f in enumerate(record['fragments']) if f['id']==fragment_id),None)
        if cut is None or cut==0:raise ValueError('Choose a continuation fragment inside this record')
        trailing=record['fragments'][cut:];ids={f['id'] for f in trailing}
        header=re.match(r'\s*(\d{10})(?!\d)',trailing[0].get('header_ocr',''))
        new=dict(key='record-'+uuid.uuid4().hex[:12],record_id=header.group(1) if header else '[?]',
            fragments=trailing,lines=[l for l in record['lines'] if l.get('fragment') in ids],notes=['Record split by user; verify its printed ID and fields.'])
        trailing[0]['status']='record_start_confirmed_by_user';record['fragments']=record['fragments'][:cut]
        record['lines']=[l for l in record['lines'] if l.get('fragment') not in ids]
        record['notes'].append('Record boundary split by user.');state['records'].insert(index+1,new)
    state['history'].append(dict(boundary_action=action,record=key,fragment=fragment_id))

def read_header(engine,crop):
    from detect_records import header_crop
    head=header_crop(crop);raw=''
    for candidate in (head,head.resize((head.width*3,head.height*3)),crop.crop((0,0,min(crop.width,100),min(crop.height,17)))):
        reading,_=engine(np.asarray(candidate.convert('RGB'))[:,:,::-1].copy(),use_det=False,use_cls=False)
        value=''.join(r[0] for r in reading or [])
        if not raw:raw=value
        match=re.match(r'\s*(\d{10})(?!\d)',value)
        if match:return match.group(1),raw
    return None,raw

def scan(state):
    from scan_pipeline import scan_project
    scan_project(state,sys.modules[__name__])


def locate_field_spans(text,lines):
    spans,_=text_fields(text);dates,_=date_fields(text);spans.update(dates)
    for field in (29,30):
        span=find_span(text,field)
        if span:spans[field]=span
    nums,_=numeric_fields(lines)
    for field,region in nums.items():
        # The locator already knows which occurrence belongs to the field.
        # Searching by its value loses repeated amounts or short numbers.
        spans[field]=tuple(region['character_span'])
    if 18 in nums:spans[22]=tuple(nums[18]['following_label_span'])
    # Product ends at the first amount, even when OCR puts both on one line.
    if 16 in spans and 18 in spans and spans[16][1]<spans[18][0]:
        spans[17]=(spans[16][1],spans[18][0])
    return spans

def field_analysis(record,decisions):
    text='';original='';pieces=[];lines=[];original_lines=[];positions=[]
    for line in record['lines']:
        line_text='';original_line='';separators=[];original_separators=[]
        for seg in line['segments']:
            raw=decisions.get(seg['id'],seg['text']);a=len(text)+len(line_text);oa=len(original)+len(original_line)
            if seg['text']=='' and seg['category']=='ambiguous' and ' ' in seg.get('options',[]):
                original_separators.append(len(original_line))
                if seg['id'] not in decisions:separators.append(len(line_text))
            pieces.append((a,a+len(raw),render_segments([seg],decisions),raw,seg['id']))
            positions.append(dict(start=a,end=a+len(raw),original_start=oa,original_end=oa+len(seg['text']),line=line,segment=seg))
            line_text+=raw;original_line+=seg['text']
        lines.append(dict(text=line_text,box=line['box'],separator_offsets=separators))
        original_lines.append(dict(text=original_line,box=line['box'],separator_offsets=original_separators))
        text+=line_text+'\n';original+=original_line+'\n';pieces.append((len(text)-1,len(text),' ','\n',None))
    spans=locate_field_spans(text,lines)
    # An edit to an anchor or identifier must not make a previously located cell
    # disappear. Retain original boundaries, translating offsets after edits.
    def translated(offset):
        shift=0
        for p in positions:
            if offset<p['original_start']:return offset+shift
            if p['original_start']<=offset<p['original_end']:
                fraction=(offset-p['original_start'])/(p['original_end']-p['original_start'])
                return p['start']+round(fraction*(p['end']-p['start']))
            shift=p['end']-p['original_end']
        return offset+shift
    for field,(a,b) in locate_field_spans(original,original_lines).items():spans[field]=(translated(a),translated(b))
    values=[];issues=[];field_parts={}
    for field in range(1,37):
        if field in (2,13,25,36):values.append(None);continue
        span=spans.get(field)
        if not span:values.append('[?]');issues.append(field);continue
        a,b=span;parts=[];field_parts[field]=[]
        for lo,hi,marked,raw,segment_id in pieces:
            # An optional space at the start of a field is a separator, not a
            # character inside its value. Missing-digit alternatives stay in it.
            if field in (18,19,20,21) and lo==hi==a and segment_id:
                seg=next(p['segment'] for p in positions if p['segment']['id']==segment_id)
                if seg.get('options') and all(not v.strip() for v in seg['options']):continue
            # Include insertion-only disagreements at their source position.
            if hi==lo and a<=lo<b and marked:
                parts.append(marked);field_parts[field].append(dict(marked=marked,raw=raw,id=segment_id));continue
            if hi<=a or lo>=b:continue
            clipped=raw[max(a-lo,0):min(b-lo,len(raw))]
            complete=lo>=a and hi<=b
            shown=clipped if marked==raw else marked if complete else '[?]'
            parts.append(shown)
            field_parts[field].append(dict(marked=shown,raw=clipped,id=segment_id if complete else None))
        values.append(' '.join(''.join(parts).split()) or '[?]')
    evidence={}
    # Field zero is the displayed record ID; share the printed ID's evidence.
    if 1 in spans:spans[0]=spans[1]
    for field,(a,b) in spans.items():
        selected=[p for p in positions if (p['end']>a and p['start']<b) or (p['start']==p['end'] and a<=p['start']<b)]
        selected=[p for p in selected if not (field in (18,19,20,21) and p['start']==p['end']==a and p['segment'].get('options') and
            all(not v.strip() for v in p['segment']['options']))]
        evidence[field]=dict(plain=' '.join(text[a:b].split()),segments=[dict(id=p['segment']['id'],line=p['line']['id'],
            editable=p['start']>=a and p['end']<=b) for p in selected],sources=[],parts=field_parts.get(field,[]))
        for line in record['lines']:
            matches=[p for p in selected if p['line']['id']==line['id']]
            if not matches:continue
            source_segments=line['segments'];start=min(source_segments.index(p['segment']) for p in matches);end=max(source_segments.index(p['segment']) for p in matches)
            width=max(pt[0] for pt in line['box'])-min(pt[0] for pt in line['box'])
            # CTC positions are estimates. Include neighboring pixels and retain full-line context.
            left=max(0,source_segments[start].get('x',0)-5)
            right=source_segments[end+1].get('x',width)+5 if end+1<len(source_segments) else width
            evidence[field]['sources'].append(dict(line=line['id'],image=line.get('image'),page=line['page'],left=left,right=max(left+1,right)))
    identifier=values[0] if 1 in spans else record['record_id']
    if identifier=='[?]':issues.append(0)
    return [identifier,*values],issues,evidence

def field_export(record,decisions):
    row,issues,_=field_analysis(record,decisions)
    return row,issues

def sheet_data(state):
    result=[]
    for record in state['records']:
        row,issues,evidence=field_analysis(record,state['decisions']);cells=[]
        editable_record=review_record(state,record)
        for field in range(1,36):
            if field in (2,13,25):continue
            selection=state.get('field_regions',{}).get(record['key']+':'+str(field))
            if selection:
                evidence[field]=selected_region(editable_record,selection,state['decisions'])
                row[field]=evidence[field]['marked'] or '[?]'
                if field in issues:issues.remove(field)
        mapped=dict(evidence)
        for field in range(1,36):
            if field not in (2,13,25) and not evidence.get(field,{}).get('sources'):
                evidence[field]=candidate_for(record,field,mapped,state['decisions'])
        segments={s['id']:s for line in editable_record['lines'] for s in line['segments']}
        for field,value in enumerate(row):
            key=record['key']+':'+str(field);manual=key in state.get('field_decisions',{})
            info=evidence.get(field,dict(plain='',segments=[],sources=[]))
            pending=sum(segments[s['id']]['category']!='single' and s['id'] not in state['decisions'] for s in info['segments'])
            if manual:value=state['field_decisions'][key]
            status='confirmed' if manual else ('unmapped' if field in issues else ('uncertain' if pending else 'read'))
            if value is None:status='blank'
            cells.append(dict(field=field,value=value,manual=manual,status=status,pending=pending,**info))
        cells=decorate(state,editable_record,cells)
        result.append(dict(key=record['key'],record_id=record['record_id'],cells=cells,notes=record['notes'],fragments=record.get('fragments',[]),field_coverage=field_coverage(cells)))
    return result

def record_image_files(record,pages):
    """Keep a continued record associated with every original source image."""
    by_name={p['name']:p['file'] for p in pages}
    known={p['file'] for p in pages};found=set()
    for fragment in record.get('fragments',[]):
        filename=fragment.get('file')
        if filename in known:found.add(filename)
        elif fragment.get('page') in by_name:found.add(by_name[fragment['page']])
    for line in record.get('lines',[]):
        if line.get('page') in by_name:found.add(by_name[line['page']])
    return [p['file'] for p in pages if p['file'] in found]

def workspace_page(state,offset=0,limit=50,image=None):
    """Return bounded source evidence and cells; export still uses every record."""
    if offset<0 or not 1<=limit<=50:raise ValueError('Invalid record window')
    pages=state['pages']
    if image is not None and image not in {p['file'] for p in pages}:raise ValueError('Unknown source image')
    image_records={p['file']:dict(records=0,shared=0,pending=0) for p in pages}
    matching=[]
    for index,record in enumerate(state['records']):
        sources=record_image_files(record,pages)
        available=record_ready(state,record)
        for filename in sources:
            image_records[filename]['records']+=int(available)
            image_records[filename]['pending']+=int(not available)
            image_records[filename]['shared']+=int(available and len(sources)>1)
        if available and (image is None or image in sources):matching.append((index,record,sources))
    total=len(matching)
    offset=min(offset,max(0,((total-1)//limit)*limit))
    window=matching[offset:offset+limit]
    selected=[r for _,r,_ in window]
    keys={r['key'] for r in selected}
    available=len(ready_records(state));done=completed_pages(state)
    def image_status(i,p):
        if state['status']=='ready' or i<done:return 'continuation' if image_records[p['file']]['pending'] else 'ready'
        if state['status'] in ('cancelled','error'):return 'partial' if image_records[p['file']]['records'] else 'not_scanned'
        return 'scanning' if i==done and state.get('scan_stats',{}).get('stage') in ('loading','reading','saving','cancelling') else 'waiting'
    view=dict(state,records=selected,history=[],record_offset=offset,record_total=total,
        project_record_total=len(state['records']),ready_record_total=available,pending_record_total=len(state['records'])-available,
        completed_pages=done,review_allowed=state['status'] in ('ready','cancelled','error') or state.get('progressive_scan',False),image_filter=image,
        image_navigation=[dict(file=p['file'],name=p['name'],number=i+1,status=image_status(i,p),**image_records[p['file']]) for i,p in enumerate(pages)])
    for field in ('field_regions','field_decisions'):
        view[field]={k:v for k,v in state.get(field,{}).items() if k.rsplit(':',1)[0] in keys}
    reviewed=review_state(view)
    for record,(index,_,sources) in zip(reviewed['records'],window):
        record.update(project_row=index+1,source_images=sources)
    ids={s['id'] for r in reviewed['records'] for line in r['lines'] for s in line['segments']}
    reviewed['decisions']={k:v for k,v in state['decisions'].items() if k in ids}
    reviewed.pop('field_crop_history',None)
    return dict(state=reviewed,rows=sheet_data(view) if selected else [])

def page_thumbnail(job,name):
    if not re.fullmatch(r'page-\d+\.png',name):raise ValueError('Invalid source image')
    directory=folder(job);source=directory/name;cached=directory/('thumb-'+name[:-4]+'.jpg')
    if not cached.exists() or cached.stat().st_mtime_ns<source.stat().st_mtime_ns:
        with Image.open(source) as image:
            image.thumbnail((120,160))
            with image.convert('RGB') as thumbnail:
                data=io.BytesIO();thumbnail.save(data,format='JPEG',quality=75)
        temporary=directory/('thumb-'+uuid.uuid4().hex+'.tmp')
        try:
            temporary.write_bytes(data.getvalue());temporary.replace(cached)
        finally:temporary.unlink(missing_ok=True)
    return cached.read_bytes()

def export_data(state):
    decisions=state['decisions'];rows=[];review=[];raw=[]
    for record in state['records']:
        row,issues=field_export(record,decisions)
        issues=[f for f in issues if record['key']+':'+str(f) not in state.get('field_regions',{})]
        for field in range(37):
            key=record['key']+':'+str(field)
            if key in state.get('field_decisions',{}):
                row[field]=state['field_decisions'][key]
                if field in issues:issues.remove(field)
                review.append([record['key'],str(field),'Manual field correction','',row[field],'Confirmed'])
        rows.append(row)
        for field in issues:review.append([record['key'],str(field),'Missing field boundary','[?]','', 'Unresolved'])
        for note in record['notes']:review.append([record['key'],'','Layout review',note,'','Inspect source'])
        for line in review_record(state,record)['lines']:
            raw.append([record['key'],line['page'],line['id'],render_segments(line['segments'],decisions)])
            for seg in line['segments']:
                if seg['category']!='single' or seg['id'] in decisions:
                    review.append([record['key'],seg['id'],seg['category'],seg['text'],decisions.get(seg['id'],''),'Confirmed' if seg['id'] in decisions else 'Unresolved'])
    if state.get('field_regions'):
        if state.get('schema_version')!=2:rows=[[c['value'] for c in r['cells']] for r in sheet_data(state)]
        for key,selection in state['field_regions'].items():
            review.append([key.rsplit(':',1)[0],key.rsplit(':',1)[1],'User-selected field boundary',selection['first'],selection['last'],'Boundary confirmed; text still needs review'])
            if selection.get('kind')=='rectangles':
                review.append([key.rsplit(':',1)[0],key.rsplit(':',1)[1],'User-drawn source areas',
                    json.dumps([{k:r[k] for k in ('page','box','fragment')} for r in selection['regions']]),selection['id'],
                    'Selection confirmed before OCR; model not retrained'])
    result=dict(rows=rows,review=review,lines=raw)
    if state.get('schema_version')==2:
        result.update(headers=HEADERS,rows=[],statuses=[],schema_version=2,
            fragments=[[r['key'],f['page'],f['id'],f['status'],json.dumps(f['box']),' | '.join(r['notes'])] for r in state['records'] for f in r.get('fragments',[])])
        for record in state['records']:
            r=sheet_data(dict(state,records=[record]))[0]
            result['rows'].append([c['value'] for c in r['cells']])
            result['statuses'].append([c['status'] for c in r['cells']])
            for c in r['cells']:
                for action in c.get('rule_actions',[]):
                    review.append([r['key'],HEADERS[c['field']],'Field-rule alternative filter',
                        ' / '.join(v or '∅' for v in action['original_options']),
                        ' / '.join(v or '∅' for v in action['options']),
                        'Rule-assisted; not human-confirmed' if action['resolved'] else 'Alternatives narrowed; unresolved'])
                for issue in c.get('rule_issues',[]):review.append([r['key'],HEADERS[c['field']],'Field rule',str(c.get('raw_value') or ''),issue,'Confirmed value; rule warning retained' if c['manual'] else 'Needs review'])
            coverage=r['field_coverage']
            review.append([r['key'],'','Field mapping coverage',f"{coverage['located']}/{coverage['expected']} printed fields located",
                ', '.join(HEADERS[f] for f in coverage['missing_fields']),coverage['note']])
        for issue in state.get('page_issues',[]):review.append(['','','Page review',issue,'','Needs review'])
    return result

def export_project(job):
    # Snapshot corrections and stable records, then release the shared state lock
    # before generating Excel so OCR and other reviewers can keep saving.
    with LOCK:
        state=export_snapshot(load(job));export_lock=EXPORT_LOCKS.setdefault(job,threading.Lock())
    with export_lock:
        if (len(state['pages'])>20 or state.get('partial_export')) and state.get('schema_version')==2:
            from batch_export import write_workbook
            write_workbook(folder(job)/'converted.xlsx',state,export_data,HEADERS)
        else:
            payload=folder(job)/'export.json';payload.write_text(json.dumps(export_data(state),ensure_ascii=False),encoding='utf-8')
            result=subprocess.run([str(NODE),str(ROOT/'app_export.mjs'),str(payload)],capture_output=True,text=True,timeout=max(90,3*len(state['pages'])))
            if result.returncode:raise RuntimeError('Excel export failed: '+result.stderr[-500:])
    return dict(url='/download?job='+job+('&partial=1' if state.get('partial_export') else ''),partial=state.get('partial_export',False),records=len(state['records']),
                completed_pages=completed_pages(state),pages=len(state['pages']))

CROPS=CropService(load,save,folder,LOCK,write_examples)
UPLOADS=BatchUpload(load,save,folder,LOCK,enqueue_scan)

class Handler(BaseHTTPRequestHandler):
    def respond(self,value,status=200,mime='application/json',filename=None):
        request_id=getattr(self,'request_id',None) or uuid.uuid4().hex[:12]
        route=urlparse(self.path).path
        if (route.startswith('/api/') or route=='/download' or (route=='/image' and status>=400)) and (route!='/api/progress' or status>=400):
            diagnostic_event('request',job=getattr(self,'diagnostic_job',None),request_id=request_id,
                method=self.command,route=route,status=status,
                duration_ms=round(1000*(time.monotonic()-getattr(self,'request_started',time.monotonic()))),
                error=value.get('error') if isinstance(value,dict) else None,
                traceback=traceback.format_exc() if status>=400 and sys.exc_info()[0] else None)
        data=json.dumps(value).encode() if mime=='application/json' else value
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Pixel-Request-ID',request_id)
        if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        self.request_id=uuid.uuid4().hex[:12];self.request_started=time.monotonic();self.diagnostic_job=None
        try:
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):return self.respond({'error':'Local access only'},403)
            u=urlparse(self.path);q=parse_qs(u.query)
            self.diagnostic_job=q.get('job',[None])[0]
            if u.path=='/':return self.respond((ROOT/'review_sheet.html').read_bytes().replace(b'__TOKEN__',TOKEN.encode()),mime='text/html; charset=utf-8')
            if u.path=='/legacy':return self.respond((ROOT/'review_app.html').read_bytes().replace(b'__TOKEN__',TOKEN.encode()),mime='text/html; charset=utf-8')
            if u.path=='/review_sheet.js':return self.respond((ROOT/'review_sheet.js').read_bytes(),mime='text/javascript; charset=utf-8')
            if u.path=='/field_crop_picker.js':return self.respond((ROOT/'field_crop_picker.js').read_bytes(),mime='text/javascript; charset=utf-8')
            if u.path=='/review_queue.js':return self.respond((ROOT/'review_queue.js').read_bytes(),mime='text/javascript; charset=utf-8')
            if u.path=='/review_diagnostics.js':return self.respond((ROOT/'review_diagnostics.js').read_bytes(),mime='text/javascript; charset=utf-8')
            if u.path=='/api/capabilities':
                try:
                    from rapidocr_onnxruntime import RapidOCR
                    return self.respond({'scan':True,'cancel_scan':True,'progressive_review':True})
                except (ImportError,OSError) as error:
                    return self.respond({'scan':False,'message':'New scans are unavailable because an OCR component cannot load. Saved scans can still be reviewed and exported.','detail':str(error)})
            if u.path=='/api/jobs':return self.respond(list_jobs())
            if u.path=='/api/schema':return self.respond({'headers':HEADERS,'version':2})
            job=q.get('job',[''])[0]
            if u.path=='/api/workspace':return self.respond(workspace_page(load(job),int(q.get('offset',['0'])[0]),image=q.get('image',[None])[0]))
            if u.path=='/thumbnail':return self.respond(page_thumbnail(job,q.get('name',[''])[0]),mime='image/jpeg')
            if u.path=='/api/progress':return self.respond(get_progress(job))
            if u.path=='/api/state':return self.respond(review_state(load(job)))
            if u.path=='/api/field-crop-status':return self.respond(CROPS.status(job,q.get('operation',[''])[0]))
            if u.path=='/api/sheet':
                state=load(job);return self.respond(sheet_data(dict(state,records=ready_records(state))))
            if u.path=='/api/learning':
                with LOCK:return self.respond(write_examples(load(job),folder(job)))
            if u.path=='/api/fields':
                state=load(job);return self.respond(export_data(state)['rows'])
            if u.path=='/image':
                name=q.get('name',[''])[0]
                if not ASSET.fullmatch(name):raise ValueError('Invalid image')
                return self.respond((folder(job)/name).read_bytes(),mime='image/png')
            if u.path=='/download':return self.respond((folder(job)/'converted.xlsx').read_bytes(),mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',filename='Pixel-partial.xlsx' if parse_qs(u.query).get('partial')==['1'] else 'Pixel-converted.xlsx')
            self.respond({'error':'Not found'},404)
        except Exception as e:self.respond({'error':str(e)},400)
    def do_POST(self):
        self.request_id=uuid.uuid4().hex[:12];self.request_started=time.monotonic();self.diagnostic_job=None
        try:
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):return self.respond({'error':'Local access only'},403)
            if self.headers.get('X-Review-Token')!=TOKEN:return self.respond({'error':'Invalid local session'},403)
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<40_000_000:raise ValueError('Upload limit is 40 MB per request')
            data=json.loads(self.rfile.read(size));route=urlparse(self.path).path
            self.diagnostic_job=data.get('job')
            if route=='/api/upload/create':return self.respond(UPLOADS.create(data))
            if route=='/api/upload/page':return self.respond(UPLOADS.page(data))
            if route=='/api/upload/finish':return self.respond(UPLOADS.finish(data.get('job')))
            if route=='/api/test-report':
                job=data.get('job');snapshot=None;live=None;state_error=None
                if job:
                    folder(job) # Validate even when the saved state is missing/corrupt.
                    try:snapshot=load(job)
                    except (OSError,ValueError) as error:state_error=str(error)
                    try:live=get_progress(job)
                    except (OSError,ValueError):pass
                filename,payload=diagnostics.report_bundle(ROOT,DATA,data,snapshot,live,BUILD,NODE,TOKEN,state_error)
                return self.respond(payload,mime='application/zip',filename=filename)
            if route=='/api/scan':
                pages=data.get('pages',[])
                if not 1<=len(pages)<=20:raise ValueError('Select 1–20 images')
                project_name=str(data.get('name','Untitled project')).strip()
                if not 1<=len(project_name)<=100:raise ValueError('Project name must be 1–100 characters')
                # Decode/validate every page BEFORE creating the project.
                decoded=[];hashes=set();names=set()
                for i,page in enumerate(pages):
                    image=Image.open(io.BytesIO(base64.b64decode(page['data'],validate=True)))
                    if image.width*image.height>20_000_000:raise ValueError('Image exceeds 20 million pixels')
                    image.load()
                    image=image.convert('RGB');digest=hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest()
                    source_name=str(page['name'])[:200]
                    if digest in hashes or source_name in names:raise ValueError('Duplicate image or filename in upload: '+source_name)
                    hashes.add(digest);names.add(source_name);decoded.append((image,source_name,digest))
                job=uuid.uuid4().hex;folder(job).mkdir()
                self.diagnostic_job=job
                now=datetime.now().astimezone()
                state=dict(id=job,project_name=project_name,schema_version=2,created_at=now.isoformat(),created_date=now.strftime('%m/%d/%Y'),
                    status='scanning',progress='Queued for scan',pages=[],records=[],decisions={},history=[],page_issues=[])
                for i,(image,source_name,digest) in enumerate(decoded):
                    name=f'page-{i}.png';image.save(folder(job)/name)
                    state['pages'].append(dict(name=source_name,file=name,sha256=digest))
                save(state);enqueue_scan(state);return self.respond({'id':job})
            if route=='/api/cancel':return self.respond(cancel_scan(data['job']),202)
            if route=='/api/retry':
                with LOCK:state=retry_scan(load(data['job']))
                return self.respond({'id':state['id']})
            if route=='/api/field-crop':return self.respond(CROPS.submit(data),202)
            if route=='/api/export':return self.respond(export_project(data['job']))
            with LOCK:
                state=load(data['job'])
                editable=ready_records(state)
                if not editable:raise ValueError('No records are ready for review yet.')
                if 'record' in data and data['record'] not in {r['key'] for r in editable}:
                    raise ValueError('This record is still being scanned or waiting for its continuation.')
                if route=='/api/boundary':
                    if state['status']=='scanning':raise ValueError('Finish or cancel scanning before changing record boundaries.')
                    change_boundary(state,data['record'],data['action'],data.get('fragment'))
                    save(state);return self.respond({'saved':True})
                if route=='/api/field-region':
                    record=next((r for r in state['records'] if r['key']==data['record']),None)
                    field=data['field']
                    if record is None or not isinstance(field,int) or field not in set(range(1,36))-{2,13,25}:raise ValueError('Not a printed field')
                    key=record['key']+':'+str(field)
                    if key in state.get('field_decisions',{}):raise ValueError('Reset the whole-field confirmation before adjusting its source region')
                    if data.get('reset'):
                        archive_selection(state,key)
                        state.setdefault('field_regions',{}).pop(key,None)
                        state['history'].append(dict(reset_field_region=key));save(state)
                        write_examples(state,folder(state['id']));return self.respond({'saved':True})
                    selection=dict(first=data['first'],last=data['last'])
                    selected_region(record,selection,state['decisions'])
                    if state.get('field_regions',{}).get(key,{}).get('kind')=='rectangles':
                        raise ValueError('Use Draw field area to change a rectangle selection.')
                    state.setdefault('field_regions',{})[key]=selection
                    state['history'].append(dict(field_region=key,selection=selection))
                    save(state);return self.respond({'saved':True})
                if route=='/api/confirm':
                    segments={s['id']:s for r in editable for l in review_record(state,r)['lines'] for s in l['segments']}
                    key=data['segment'];value=data['value']
                    if key not in segments or not isinstance(value,str) or len(value)>200:raise ValueError('Invalid correction')
                    for r in state['records']:
                        for line in review_record(state,r)['lines']:
                            if any(s['id']==key for s in line['segments']):state.get('verified_lines',{}).pop(line['id'],None)
                    state['history'].append(dict(segment=key,previous=state['decisions'].get(key),value=value))
                    if data.get('reset'):state['decisions'].pop(key,None)
                    else:state['decisions'][key]=value
                    save(state);summary=write_examples(state,folder(state['id']));return self.respond({'saved':True,'learning':summary})
                if route=='/api/verify-line':
                    lines={l['id']:l for r in editable for l in review_record(state,r)['lines']}
                    if data['line'] not in lines:raise ValueError('Unknown text region')
                    line=lines[data['line']]
                    current_text=render_segments(line['segments'],state['decisions'],marked=False)
                    if data.get('text')!=current_text:raise ValueError('This line changed. Reload it before confirming.')
                    for segment in line['segments']:state['decisions'].setdefault(segment['id'],segment['text'])
                    state.setdefault('verified_lines',{})[line['id']]=dict(text=render_segments(line['segments'],state['decisions'],marked=False))
                    state['history'].append(dict(verified_line=line['id']))
                    save(state);summary=write_examples(state,folder(state['id']));return self.respond({'saved':True,'learning':summary})
                if route=='/api/field':
                    record=data['record'];field=data['field'];value=data['value']
                    if record not in {r['key'] for r in state['records']} or not isinstance(field,int) or not 0<=field<=36 or not isinstance(value,str) or len(value)>5000:raise ValueError('Invalid field correction')
                    key=record+':'+str(field);state.setdefault('field_decisions',{})
                    state['history'].append(dict(field=key,previous=state['field_decisions'].get(key),value=value))
                    if data.get('reset'):state['field_decisions'].pop(key,None)
                    else:state['field_decisions'][key]=value
                    save(state)
                    if state.get('field_regions',{}).get(key,{}).get('kind')=='rectangles':write_examples(state,folder(state['id']))
                    return self.respond({'saved':True})
            raise ValueError('Unknown action')
        except Exception as e:self.respond({'error':str(e)},400)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--open',action='store_true')
    args=parser.parse_args();url=f'http://127.0.0.1:{args.port}'
    if '--open' in sys.argv:
        try:
            if b'Pixel' in urllib.request.urlopen(url,timeout=1).read():
                webbrowser.open(url);sys.exit(0)
        except (OSError,urllib.error.URLError):pass
    # New checkpoints are complete pages. Legacy partial pages are replayed by
    # prepare_resume; finalized pages and human corrections are preserved.
    recovering=[]
    for p in DATA.glob('*/state.json'):
        s=json.loads(p.read_text(encoding='utf-8'))
        if s['status']=='scanning':recovering.append(s)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    # A previously active batch keeps priority over batches that never started.
    for s in sorted(recovering,key=lambda s:(not bool((s.get('scan_stats') or {}).get('started_at')),(s.get('scan_stats') or {}).get('queued_at',0))):
        enqueue_scan(s)
    print('Pixel review: '+url,flush=True)
    if '--open' in sys.argv:threading.Timer(1,lambda:webbrowser.open(url)).start()
    server.serve_forever()
