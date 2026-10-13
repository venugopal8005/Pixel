"""Page-at-a-time publication, cooperative cancellation, and resumable checkpoints."""
import re
import time
import traceback
import numpy as np
from PIL import Image
from scan_state import prepare_resume,line_counter


class ScanCancelled(Exception):
    pass


def scan_project(state,app):
    acquired=False
    try:
        while not app.SCAN_LOCK.acquire(timeout=.25):app.check_scan_cancel(state)
        acquired=True;app.check_scan_cancel(state)
        from rapidocr_onnxruntime import RapidOCR
        from detect_records import blocks
        start_page=prepare_resume(state)
        state['status']='scanning';state['progress']='Loading the local OCR model'
        counter=line_counter(state);seen={r['record_id'] for r in state['records'] if r['record_id']!='[?]'}
        state.setdefault('page_issues',[])
        app.save_scan_state(state)
        app.publish_progress(state,'loading',started_at=time.time(),page_count=len(state['pages']),text_regions=counter,
                             record_candidates=len(state['records']),completed_pages=start_page)
        engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,text_score=0)
        app.check_scan_cancel(state)
        previous=None
        if state['records']:
            record=state['records'][-1];fragment=record['fragments'][-1]
            previous=dict(record=record,open_bottom=fragment['open_bottom'],page=fragment['page'])
        last_update=0
        for page_index in range(start_page,len(state['pages'])):
            app.check_scan_cancel(state);page=state['pages'][page_index]
            state['progress']=f'Checking page layout {page_index+1}/{len(state["pages"])}'
            app.publish_progress(state,'reading',page=page_index+1,filename=page['name'],page_blocks=0,block=0,
                                 percent=round(100*page_index/max(1,len(state['pages'])),1))
            with Image.open(app.folder(state['id'])/page['file']) as source:image=source.convert('RGB')
            try:page_blocks=blocks(image)
            except ValueError as error:
                state['page_issues'].append(page['name']+': '+str(error))
                page_blocks=[dict(column=0,block=0,box=[0,0,image.width,image.height],first_in_column=False,open_bottom=False,layout_failed=True)]
            if previous and not app.adjacent_pages(previous['page'],page['name']):
                previous['record']['notes'].append('Page order has a gap or reversal; continuation was not joined.')
                previous['record']['review_ready']=True
                state['page_issues'].append(page['name']+': page gap/reversal before this image; inspect boundary records.')
                previous=None
            for block_index,block in enumerate(page_blocks):
                app.check_scan_cancel(state)
                state['progress']=f'Page {page_index+1}/{len(state["pages"])} · record region {block_index+1}/{len(page_blocks)} · {counter} text regions read'
                app.publish_progress(state,'reading',page=page_index+1,filename=page['name'],block=block_index+1,page_blocks=len(page_blocks))
                crop=image.crop(block['box']);record_id,raw=app.read_header(engine,crop)
                app.check_scan_cancel(state)
                if block.get('layout_failed'):record_id=None
                joined=bool(not record_id and block['first_in_column'] and previous and previous['open_bottom']
                            and not re.match(r'\s*[A-Z0-9]{10}(?![A-Z0-9])',raw))
                if joined:
                    record=previous['record'];record['notes'].append('Continuation joined from layout; inspect source.')
                else:
                    if previous:previous['record']['review_ready']=True
                    record=dict(key=f'record-{len(state["records"])+1}',record_id=record_id or '[?]',lines=[],review_ready=False,
                                notes=['Record ID and field boundaries are provisional.' if record_id else 'Unassigned fragment or unreadable record ID; retained for review.'])
                    if record_id in seen:record['notes'].append('Duplicate printed ID; both records retained for review.')
                    if record_id:seen.add(record_id)
                    state['records'].append(record)
                record['review_ready']=False;record['scan_partial']=True
                fragment=dict(id=f'p{page_index}-b{block_index}',page=page['name'],file=page['file'],box=block['box'],
                    column=block['column'],header_ocr=raw,status='continuation_inferred' if joined else ('record_start' if record_id else 'unassigned'),
                    open_bottom=block['open_bottom'])
                if block.get('layout_method'):fragment['layout_method']=block['layout_method']
                record.setdefault('fragments',[]).append(fragment)
                if block.get('layout_failed'):record['notes'].append('Page layout was not recognized. Entire page retained as an unassigned fragment; it may contain several records.')
                if block.get('short_fragment'):record['notes'].append('Short text-bearing fragment retained; inspect its record assignment.')
                if block.get('layout_method')=='faint_rules_and_spacing':
                    note='Faint borders: record boundary inferred from ruled columns and text spacing; inspect the source crop.'
                    if note not in record['notes']:record['notes'].append(note)
                previous=dict(record=record,open_bottom=block['open_bottom'],page=page['name'])
                reading,_=engine(np.asarray(crop)[:,:,::-1].copy(),use_cls=False,use_rec=False)
                regions=[] if reading is None else list(reading)
                if not regions:record['notes'].append('No text detected in this block.')
                for line_index,points in enumerate(regions):
                    app.check_scan_cancel(state);counter+=1
                    pts=np.asarray(points);x0=max(0,int(pts[:,0].min())-2);y0=max(0,int(pts[:,1].min())-2)
                    x1=min(crop.width,int(pts[:,0].max())+3);y1=min(crop.height,int(pts[:,1].max())+3)
                    line_image=crop.crop((x0,y0,x1,y1));name=f'line-{counter}.png';line_image.save(app.folder(state['id'])/name)
                    segments=app.read_line(engine,line_image)
                    for i,seg in enumerate(segments):seg['id']=f'l{counter}-s{i}'
                    record['lines'].append(dict(id=f'l{counter}',image=name,page=page['name'],fragment=fragment['id'],segments=segments,
                        box=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]],source_box=[block['box'][0]+x0,block['box'][1]+y0,block['box'][0]+x1,block['box'][1]+y1]))
                    app.check_scan_cancel(state)
                    if time.monotonic()-last_update>=1:
                        fraction=(block_index+(line_index+1)/max(1,len(regions)))/max(1,len(page_blocks))
                        state['progress']=f'Page {page_index+1}/{len(state["pages"])} · record region {block_index+1}/{len(page_blocks)} · {counter} text regions read'
                        app.publish_progress(state,'reading',text_regions=counter,record_candidates=len(state['records']),
                                             percent=round(min(99,100*(page_index+fraction)/max(1,len(state['pages']))),1))
                        last_update=time.monotonic()
                record['scan_partial']=False;record['review_ready']=not block['open_bottom']
            # Publish only at page boundaries. Previously published records never
            # change during OCR; the unfinished continuation remains unavailable.
            state['completed_pages']=page_index+1
            app.save_scan_state(state)
            app.publish_progress(state,'reading',completed_pages=page_index+1,text_regions=counter,record_candidates=len(state['records']),
                                 percent=round(min(99,100*(page_index+1)/max(1,len(state['pages']))),1))
        app.check_scan_cancel(state)
        if previous and previous['open_bottom']:previous['record']['notes'].append('Open bottom: record may continue on a missing page.')
        for record in state['records']:record['review_ready']=True
        state.update(status='ready',progress=f'{counter} text regions ready for review')
        app.save_scan_state(state);app.publish_progress(state,'complete',percent=100,text_regions=counter,record_candidates=len(state['records']))
    except ScanCancelled:
        state.update(status='cancelled',progress='Scan cancelled. Saved results and uploaded images are kept.')
        for record in state['records']:
            if not record.get('review_ready',False):record['notes'].append('Scan cancelled before this record was finalized; check its fields and continuation.')
        app.save_scan_state(state);app.publish_progress(state,'cancelled')
    except Exception as error:
        app.diagnostic_event('scan_error',job=state['id'],error=str(error),traceback=traceback.format_exc())
        state.update(status='error',error=str(error))
        try:app.save_scan_state(state)
        except OSError:pass
        app.publish_progress(state,'error',percent=min(99,state.get('scan_stats',{}).get('percent',0)))
    finally:
        app.SCAN_CANCEL.discard(state['id'])
        if acquired:app.SCAN_LOCK.release()
