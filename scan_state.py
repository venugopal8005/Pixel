"""Stable review boundaries and page checkpoints for progressive OCR."""
import re

REVIEW_KEYS=('decisions','field_decisions','field_regions','field_crop_history','verified_lines','history')


def record_ready(state,record):
    return state['status'] in ('ready','cancelled','error') or (
        state['status']=='scanning' and state.get('progressive_scan') and record.get('review_ready',False))


def ready_records(state):
    return [r for r in state['records'] if record_ready(state,r)]


def completed_pages(state):
    return state.get('completed_pages',len(state['pages']) if state['status']=='ready' else 0)


def prepare_resume(state):
    """Keep completed pages; only legacy unpublished partial-page OCR is replayed."""
    if state.get('progressive_scan'):
        return state.get('completed_pages',0)
    pages={p['file']:i for i,p in enumerate(state['pages'])}
    fragments=[f for r in state['records'] for f in r.get('fragments',[])]
    last=max((pages[f['file']] for f in fragments),default=-1)
    stats=state.get('scan_stats',{})
    full=last>=0 and stats.get('page')==last+1 and stats.get('block')==stats.get('page_blocks') and bool(stats.get('page_blocks'))
    boundary=last+1 if full else max(0,last)
    retained=[]
    for record in state['records']:
        kept=[f for f in record.get('fragments',[]) if pages.get(f['file'],boundary)<boundary]
        if not kept:continue
        ids={f['id'] for f in kept}
        record['fragments']=kept;record['lines']=[l for l in record['lines'] if l.get('fragment') in ids]
        record['review_ready']=True;retained.append(record)
    if retained and retained[-1]['fragments'][-1].get('open_bottom'):retained[-1]['review_ready']=False
    state.update(records=retained,completed_pages=boundary,progressive_scan=True)
    return boundary


def line_counter(state):
    return max((int(m.group(1)) for r in state['records'] for l in r['lines']
                if (m:=re.fullmatch(r'l(\d+)',l['id']))),default=0)


def export_snapshot(state):
    records=ready_records(state)
    if not records:raise ValueError('No records are ready to export yet.')
    partial=state['status']!='ready'
    view=dict(state,records=records)
    if partial:
        message=(f'PARTIAL EXPORT: {len(records)} available records; {completed_pages(state)}/{len(state["pages"])} images fully scanned. '
                 f'{len(state["records"])-len(records)} unfinished record candidates excluded. Project status: {state["status"]}.')
        view['page_issues']=[message,*state.get('page_issues',[])]
        view['partial_export']=True
        view['export_scope']=message
    return view
