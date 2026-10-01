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
from field_regions import candidate_for,selected_region
import diagnostics

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'outputs/review-app';DATA.mkdir(parents=True,exist_ok=True)
LOCK=threading.RLock();SCAN_LOCK=threading.Lock();TOKEN=secrets.token_urlsafe(32)
LIVE_PROGRESS={}
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
            try:tmp.replace(target);return
            except PermissionError:
                if attempt==8:raise
                time.sleep(min(.025*2**attempt,.4))

def load(job):
    with LOCK:return json.loads((folder(job)/'state.json').read_text(encoding='utf-8'))

def list_jobs():
    with LOCK:
        states=[load(p.parent.name) for p in sorted(DATA.glob('*/state.json'),key=lambda p:p.stat().st_mtime,reverse=True)]
    return [dict(id=s['id'],name=s.get('project_name','Saved scan '+s['id'][:8]),status=s['status'],progress=s['progress'],pages=len(s['pages']),records=len(s['records']),created=s.get('created_at','')) for s in states]

def progress_snapshot(state):
    return dict(id=state['id'],status=state['status'],progress=state.get('progress',''),
        error=state.get('error'),scan_stats=dict(state.get('scan_stats',{})))

def publish_progress(state,stage,**values):
    stats=state.setdefault('scan_stats',{})
    stats.update(stage=stage,**values)
    if 'started_at' in stats:stats['elapsed_seconds']=round(time.time()-stats['started_at'],1)
    stats['updated_at']=time.time()
    with LOCK:LIVE_PROGRESS[state['id']]=progress_snapshot(state)

def get_progress(job):
    folder(job) # Validate even when using an in-memory snapshot.
    with LOCK:return LIVE_PROGRESS.get(job) or progress_snapshot(load(job))

def retry_scan(source):
    if source['status']!='error':raise ValueError('Only a failed scan can be retried')
    job=uuid.uuid4().hex;directory=folder(job);directory.mkdir()
    now=datetime.now().astimezone()
    state=dict(id=job,project_name=source.get('project_name','Saved scan')+' · retry',schema_version=source.get('schema_version',2),
        created_at=now.isoformat(),created_date=now.strftime('%m/%d/%Y'),status='scanning',progress='Waiting for the local scanner',
        pages=[dict(p) for p in source['pages']],records=[],decisions={},history=[],page_issues=[],recovery_of=source['id'])
    for page in state['pages']:shutil.copy2(folder(source['id'])/page['file'],directory/page['file'])
    save(state);publish_progress(state,'queued',page_count=len(state['pages']),queued_at=time.time())
    threading.Thread(target=scan,args=(state,),daemon=True).start()
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
    try:
        from rapidocr_onnxruntime import RapidOCR
        from detect_records import blocks
        with SCAN_LOCK:
            state['progress']='Loading the local OCR model'
            publish_progress(state,'loading',started_at=time.time(),page_count=len(state['pages']),text_regions=0,record_candidates=0,completed_blocks=0)
            engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,text_score=0)
            previous=None;counter=0;seen=set();state.setdefault('page_issues',[])
            # Determine the amount of actual layout work before showing a percent.
            layouts=[]
            for page in state['pages']:
                with Image.open(folder(state['id'])/page['file']) as source:image=source.convert('RGB')
                try:page_blocks=blocks(image)
                except ValueError as error:
                    state['page_issues'].append(page['name']+': '+str(error))
                    page_blocks=[dict(column=0,block=0,box=[0,0,image.width,image.height],first_in_column=False,open_bottom=False,layout_failed=True)]
                layouts.append(page_blocks)
            total_blocks=sum(map(len,layouts));completed_blocks=0;last_update=0
            for page_index,page in enumerate(state['pages']):
                with Image.open(folder(state['id'])/page['file']) as source:image=source.convert('RGB')
                if previous and not adjacent_pages(previous['page'],page['name']):
                    previous['record']['notes'].append('Page order has a gap or reversal; continuation was not joined.')
                    state['page_issues'].append(page['name']+': page gap/reversal before this image; inspect boundary records.')
                    previous=None
                page_blocks=layouts[page_index]
                for block_index,block in enumerate(page_blocks):
                    state['progress']=f'Page {page_index+1}/{len(state["pages"])} · record region {block_index+1}/{len(page_blocks)} · {counter} text regions read'
                    publish_progress(state,'reading',page=page_index+1,filename=page['name'],block=block_index+1,page_blocks=len(page_blocks),
                        completed_blocks=completed_blocks,total_blocks=total_blocks,percent=round(100*completed_blocks/max(1,total_blocks),1))
                    crop=image.crop(block['box']);record_id,raw=read_header(engine,crop)
                    if block.get('layout_failed'):record_id=None
                    joined=False
                    if record_id:
                        record=dict(key=f'record-{len(state["records"])+1}',record_id=record_id,lines=[],notes=['Record ID and field boundaries are provisional.'])
                        if record_id in seen:record['notes'].append('Duplicate printed ID; both records retained for review.')
                        seen.add(record_id)
                        state['records'].append(record)
                    elif block['first_in_column'] and previous and previous['open_bottom'] and not re.match(r'\s*[A-Z0-9]{10}(?![A-Z0-9])',raw):
                        record=previous['record'];record['notes'].append('Continuation joined from layout; inspect source.');joined=True
                    else:
                        record=dict(key=f'record-{len(state["records"])+1}',record_id='[?]',lines=[],notes=['Unassigned fragment or unreadable record ID; retained for review.'])
                        state['records'].append(record)
                    fragment=dict(id=f'p{page_index}-b{block_index}',page=page['name'],file=page['file'],box=block['box'],
                        column=block['column'],header_ocr=raw,status='continuation_inferred' if joined else ('record_start' if record_id else 'unassigned'),
                        open_bottom=block['open_bottom'])
                    record.setdefault('fragments',[]).append(fragment)
                    if block.get('layout_failed'):record['notes'].append('Page layout was not recognized. Entire page retained as an unassigned fragment; it may contain several records.')
                    if block.get('short_fragment'):record['notes'].append('Short text-bearing fragment retained; inspect its record assignment.')
                    previous=dict(record=record,open_bottom=block['open_bottom'],page=page['name'])
                    # Only locate lines here. read_line performs both recognition
                    # passes; the previous third recognition pass was discarded.
                    reading,_=engine(np.asarray(crop)[:,:,::-1].copy(),use_cls=False,use_rec=False)
                    regions=[] if reading is None else list(reading)
                    if not regions:record['notes'].append('No text detected in this block.')
                    for line_index,points in enumerate(regions):
                        counter+=1
                        pts=np.asarray(points);x0=max(0,int(pts[:,0].min())-2);y0=max(0,int(pts[:,1].min())-2)
                        x1=min(crop.width,int(pts[:,0].max())+3);y1=min(crop.height,int(pts[:,1].max())+3)
                        line_image=crop.crop((x0,y0,x1,y1));name=f'line-{counter}.png';line_image.save(folder(state['id'])/name)
                        segments=read_line(engine,line_image)
                        for i,seg in enumerate(segments):seg['id']=f'l{counter}-s{i}'
                        record['lines'].append(dict(id=f'l{counter}',image=name,page=page['name'],fragment=fragment['id'],segments=segments,
                            box=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]],source_box=[block['box'][0]+x0,block['box'][1]+y0,block['box'][0]+x1,block['box'][1]+y1]))
                        if time.monotonic()-last_update>=1:
                            state['progress']=f'Page {page_index+1}/{len(state["pages"])} · record region {block_index+1}/{len(page_blocks)} · {counter} text regions read'
                            publish_progress(state,'reading',text_regions=counter,record_candidates=len(state['records']),
                                percent=round(min(99,100*(completed_blocks+(line_index+1)/max(1,len(regions)))/max(1,total_blocks)),1))
                            last_update=time.monotonic()
                    completed_blocks+=1
                    publish_progress(state,'reading',text_regions=counter,record_candidates=len(state['records']),completed_blocks=completed_blocks,
                        percent=round(min(99,100*completed_blocks/max(1,total_blocks)),1))
                    with LOCK:save(state)
            if previous and previous['open_bottom']:previous['record']['notes'].append('Open bottom: record may continue on a missing page.')
            state['progress']='Saving the completed scan'
            publish_progress(state,'saving',text_regions=counter,record_candidates=len(state['records']),percent=99)
            state['status']='ready';state['progress']=f'{counter} text regions ready for review'
            state['scan_stats'].update(stage='complete',percent=100)
            save(state)
            publish_progress(state,'complete',percent=100)
    except Exception as error:
        diagnostic_event('scan_error',job=state['id'],error=str(error),traceback=traceback.format_exc())
        state['status']='error';state['error']=str(error)
        publish_progress(state,'error',percent=min(99,state.get('scan_stats',{}).get('percent',0)))
        try:save(state)
        except OSError:pass # The live error remains accessible if storage is locked.

def locate_field_spans(text,lines):
    spans,_=text_fields(text);dates,_=date_fields(text);spans.update(dates)
    for field in (29,30):
        span=find_span(text,field)
        if span:spans[field]=span
    nums,_=numeric_fields(lines)
    for field,region in nums.items():
        value=region['locator_text'];matches=list(re.finditer(re.escape(value),text))
        if len(matches)==1:spans[field]=matches[0].span()
    # Product ends at the first amount, even when OCR puts both on one line.
    if 16 in spans and 18 in spans and spans[16][1]<spans[18][0]:
        spans[17]=(spans[16][1],spans[18][0])
    return spans

def field_analysis(record,decisions):
    text='';original='';pieces=[];lines=[];original_lines=[];positions=[]
    for line in record['lines']:
        line_text='';original_line=''
        for seg in line['segments']:
            raw=decisions.get(seg['id'],seg['text']);a=len(text)+len(line_text);oa=len(original)+len(original_line)
            pieces.append((a,a+len(raw),render_segments([seg],decisions),raw))
            positions.append(dict(start=a,end=a+len(raw),original_start=oa,original_end=oa+len(seg['text']),line=line,segment=seg))
            line_text+=raw;original_line+=seg['text']
        lines.append(dict(text=line_text,box=line['box']));original_lines.append(dict(text=original_line,box=line['box']))
        text+=line_text+'\n';original+=original_line+'\n';pieces.append((len(text)-1,len(text),' ','\n'))
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
    values=[];issues=[]
    for field in range(1,37):
        if field in (2,13,25,36):values.append(None);continue
        span=spans.get(field)
        if not span:values.append('[?]');issues.append(field);continue
        a,b=span;parts=[]
        for lo,hi,marked,raw in pieces:
            # Include insertion-only disagreements at their source position.
            if hi==lo and a<=lo<b and marked:parts.append(marked);continue
            if hi<=a or lo>=b:continue
            if marked==raw:parts.append(raw[max(a-lo,0):min(b-lo,len(raw))])
            elif lo>=a and hi<=b:parts.append(marked)
            else:parts.append('[?]')
        values.append(' '.join(''.join(parts).split()) or '[?]')
    evidence={}
    # Field zero is the displayed record ID; share the printed ID's evidence.
    if 1 in spans:spans[0]=spans[1]
    for field,(a,b) in spans.items():
        selected=[p for p in positions if (p['end']>a and p['start']<b) or (p['start']==p['end'] and a<=p['start']<b)]
        evidence[field]=dict(plain=' '.join(text[a:b].split()),segments=[dict(id=p['segment']['id'],line=p['line']['id'],
            editable=p['start']>=a and p['end']<=b) for p in selected],sources=[])
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
        for field in range(1,36):
            if field in (2,13,25):continue
            selection=state.get('field_regions',{}).get(record['key']+':'+str(field))
            if selection:
                evidence[field]=selected_region(record,selection,state['decisions'])
                row[field]=evidence[field]['marked'] or '[?]'
                if field in issues:issues.remove(field)
        mapped=dict(evidence)
        for field in range(1,36):
            if field not in (2,13,25) and not evidence.get(field,{}).get('sources'):
                evidence[field]=candidate_for(record,field,mapped,state['decisions'])
        segments={s['id']:s for line in record['lines'] for s in line['segments']}
        for field,value in enumerate(row):
            key=record['key']+':'+str(field);manual=key in state.get('field_decisions',{})
            info=evidence.get(field,dict(plain='',segments=[],sources=[]))
            pending=sum(segments[s['id']]['category']!='single' and s['id'] not in state['decisions'] for s in info['segments'])
            if manual:value=state['field_decisions'][key]
            status='confirmed' if manual else ('unmapped' if field in issues else ('uncertain' if pending else 'read'))
            if value is None:status='blank'
            cells.append(dict(field=field,value=value,manual=manual,status=status,pending=pending,**info))
        cells=decorate(state,record,cells)
        result.append(dict(key=record['key'],record_id=record['record_id'],cells=cells,notes=record['notes'],fragments=record.get('fragments',[])))
    return result

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
        for line in record['lines']:
            raw.append([record['key'],line['page'],line['id'],render_segments(line['segments'],decisions)])
            for seg in line['segments']:
                if seg['category']!='single' or seg['id'] in decisions:
                    review.append([record['key'],seg['id'],seg['category'],seg['text'],decisions.get(seg['id'],''),'Confirmed' if seg['id'] in decisions else 'Unresolved'])
    if state.get('field_regions'):
        rows=[[c['value'] for c in r['cells']] for r in sheet_data(state)]
        for key,selection in state['field_regions'].items():
            review.append([key.rsplit(':',1)[0],key.rsplit(':',1)[1],'User-selected field boundary',selection['first'],selection['last'],'Boundary confirmed; text still needs review'])
    result=dict(rows=rows,review=review,lines=raw)
    if state.get('schema_version')==2:
        sheet=sheet_data(state)
        result.update(headers=HEADERS,rows=[[c['value'] for c in r['cells']] for r in sheet],
            statuses=[[c['status'] for c in r['cells']] for r in sheet],schema_version=2,
            fragments=[[r['key'],f['page'],f['id'],f['status'],json.dumps(f['box']),' | '.join(r['notes'])] for r in state['records'] for f in r.get('fragments',[])])
        for r in sheet:
            for c in r['cells']:
                for issue in c.get('rule_issues',[]):review.append([r['key'],HEADERS[c['field']],'Field rule',str(c.get('raw_value') or ''),issue,'Confirmed value; rule warning retained' if c['manual'] else 'Needs review'])
        for issue in state.get('page_issues',[]):review.append(['','','Page review',issue,'','Needs review'])
    return result

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
            if u.path=='/review_queue.js':return self.respond((ROOT/'review_queue.js').read_bytes(),mime='text/javascript; charset=utf-8')
            if u.path=='/review_diagnostics.js':return self.respond((ROOT/'review_diagnostics.js').read_bytes(),mime='text/javascript; charset=utf-8')
            if u.path=='/api/capabilities':
                try:
                    from rapidocr_onnxruntime import RapidOCR
                    return self.respond({'scan':True})
                except (ImportError,OSError) as error:
                    return self.respond({'scan':False,'message':'New scans are unavailable because an OCR component cannot load. Saved scans can still be reviewed and exported.','detail':str(error)})
            if u.path=='/api/jobs':return self.respond(list_jobs())
            if u.path=='/api/schema':return self.respond({'headers':HEADERS,'version':2})
            job=q.get('job',[''])[0]
            if u.path=='/api/progress':return self.respond(get_progress(job))
            if u.path=='/api/state':return self.respond(load(job))
            if u.path=='/api/sheet':return self.respond(sheet_data(load(job)))
            if u.path=='/api/learning':
                with LOCK:return self.respond(write_examples(load(job),folder(job)))
            if u.path=='/api/fields':
                state=load(job);return self.respond(export_data(state)['rows'])
            if u.path=='/image':
                name=q.get('name',[''])[0]
                if not re.fullmatch(r'(?:line-\d+|page-\d+)\.png',name):raise ValueError('Invalid image')
                return self.respond((folder(job)/name).read_bytes(),mime='image/png')
            if u.path=='/download':return self.respond((folder(job)/'converted.xlsx').read_bytes(),mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',filename='Pixel-converted.xlsx')
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
                save(state);publish_progress(state,'queued',page_count=len(state['pages']),queued_at=time.time())
                threading.Thread(target=scan,args=(state,),daemon=True).start();return self.respond({'id':job})
            if route=='/api/retry':
                with LOCK:state=retry_scan(load(data['job']))
                return self.respond({'id':state['id']})
            with LOCK:
                state=load(data['job'])
                if state['status']!='ready':raise ValueError('Scan is not ready')
                if route=='/api/boundary':
                    change_boundary(state,data['record'],data['action'],data.get('fragment'))
                    save(state);return self.respond({'saved':True})
                if route=='/api/field-region':
                    record=next((r for r in state['records'] if r['key']==data['record']),None)
                    field=data['field']
                    if record is None or not isinstance(field,int) or field not in set(range(1,36))-{2,13,25}:raise ValueError('Not a printed field')
                    key=record['key']+':'+str(field)
                    if key in state.get('field_decisions',{}):raise ValueError('Reset the whole-field confirmation before adjusting its source region')
                    if data.get('reset'):
                        state.setdefault('field_regions',{}).pop(key,None)
                        state['history'].append(dict(reset_field_region=key));save(state);return self.respond({'saved':True})
                    selection=dict(first=data['first'],last=data['last'])
                    selected_region(record,selection,state['decisions'])
                    state.setdefault('field_regions',{})[key]=selection
                    state['history'].append(dict(field_region=key,selection=selection))
                    save(state);return self.respond({'saved':True})
                if route=='/api/confirm':
                    segments={s['id']:s for r in state['records'] for l in r['lines'] for s in l['segments']}
                    key=data['segment'];value=data['value']
                    if key not in segments or not isinstance(value,str) or len(value)>200:raise ValueError('Invalid correction')
                    for r in state['records']:
                        for line in r['lines']:
                            if any(s['id']==key for s in line['segments']):state.get('verified_lines',{}).pop(line['id'],None)
                    state['history'].append(dict(segment=key,previous=state['decisions'].get(key),value=value))
                    if data.get('reset'):state['decisions'].pop(key,None)
                    else:state['decisions'][key]=value
                    save(state);summary=write_examples(state,folder(state['id']));return self.respond({'saved':True,'learning':summary})
                if route=='/api/verify-line':
                    lines={l['id']:l for r in state['records'] for l in r['lines']}
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
                    save(state);return self.respond({'saved':True})
                if route=='/api/export':
                    payload=folder(state['id'])/'export.json';payload.write_text(json.dumps(export_data(state),ensure_ascii=False),encoding='utf-8')
                    result=subprocess.run([str(NODE),str(ROOT/'app_export.mjs'),str(payload)],capture_output=True,text=True,timeout=90)
                    if result.returncode:raise RuntimeError('Excel export failed: '+result.stderr[-500:])
                    return self.respond({'url':'/download?job='+state['id']})
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
    # Interrupted scans are explicit failures after a restart; saved reviews survive.
    for p in DATA.glob('*/state.json'):
        s=json.loads(p.read_text(encoding='utf-8'))
        if s['status']=='scanning':s.update(status='error',error='Scan interrupted. Upload again to rescan.');save(s)
    print('Pixel review: '+url,flush=True)
    if '--open' in sys.argv:threading.Timer(1,lambda:webbrowser.open(url)).start()
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
