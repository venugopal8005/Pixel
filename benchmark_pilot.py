"""Exercise real scans and compare to reference only AFTER prediction."""
import sys,json,uuid,time
from pathlib import Path
import PIL,numpy
sys.path.append(str(Path(__file__).resolve().parent/'.venv-ocr/Lib/site-packages'))
from PIL import Image
import review_app as app
from detect_records import blocks
from pilot_rules import apply_rule
import openpyxl

root=Path('D:/projects/piXeL/FORM TTYFRD_8AQ');out=app.ROOT/'outputs/pilot-testing';out.mkdir(exist_ok=True)
layout=[]
for p in sorted(root.glob('*.jpg')):
    try:
        found=blocks(Image.open(p));layout.append(dict(page=p.name,blocks=len(found),short=sum(b.get('short_fragment',False) for b in found)))
    except Exception as e:layout.append(dict(page=p.name,error=str(e)))
(out/'layout-audit.json').write_text(json.dumps(layout,indent=2),encoding='utf-8')
print(json.dumps(dict(layout_pages=len(layout),layout_failures=sum('error' in x for x in layout),blocks=sum(x.get('blocks',0) for x in layout))),flush=True)
jobs=[]
for batch in ((1,2),(64,65),(159,160)):
    job=uuid.uuid4().hex;app.folder(job).mkdir()
    state=dict(id=job,project_name='Pilot validation AQ'+str(batch[0])+'–'+str(batch[-1]),schema_version=2,created_date='09/29/2026',
        status='scanning',progress='Benchmark',pages=[],records=[],decisions={},history=[],page_issues=[])
    for i,n in enumerate(batch):
        p=root/f'FORM TTYFRD_8AQ{n}_enc.jpg';name=f'page-{i}.png';Image.open(p).convert('RGB').save(app.folder(job)/name)
        state['pages'].append(dict(name=p.name,file=name))
    app.save(state);start=time.time();app.scan(state)
    payload=app.export_data(state);(app.folder(job)/'benchmark-predictions.json').write_text(json.dumps(payload),encoding='utf-8')
    jobs.append(dict(id=job,batch=batch,status=state['status'],seconds=round(time.time()-start),records=len(state['records']),fragments=sum(len(r.get('fragments',[])) for r in state['records'])))
    print(json.dumps(jobs[-1]),flush=True)
    (out/'benchmark-jobs.json').write_text(json.dumps(jobs,indent=2),encoding='utf-8')
# Keep the reference out of all prediction calls.
wb=openpyxl.load_workbook('D:/projects/piXeL/8AQ 1802601902-1802605901.xlsx',read_only=True,data_only=True)
targets={str(row[0]):list(row) for row in wb.active.values if str(row[0]).isdigit()}
summary=[]
for item in jobs:
    state=app.load(item['id']);sheets=app.sheet_data(state);counts=dict(compared=0,exact=0,unresolved=0,different=0,unflagged_different=0);byfield={}
    matched=[]
    for record,row in zip(state['records'],sheets):
        target=targets.get(record['record_id'])
        if target is None:continue
        matched.append(record['record_id'])
        for f in range(3,36):
            if f in (13,25):continue
            cell=row['cells'][f];expected,_=apply_rule(f,target[f]);got=cell['value']
            counts['compared']+=1
            status='unresolved' if got is None or '[' in str(got) else ('exact' if got==expected else 'different')
            counts[status]+=1;byfield.setdefault(str(f),dict(exact=0,different=0,unresolved=0))[status]+=1
            if status=='different' and cell['status'] not in ('uncertain','unmapped'):counts['unflagged_different']+=1
    ids=sorted(set(matched));missing=[]
    if ids:missing=[str(n) for n in range(int(ids[0]),int(ids[-1])+1) if str(n) in targets and str(n) not in ids]
    summary.append(dict(**item,matched_reference_records=len(matched),missing_ids_between_detected_bounds=missing,counts=counts,by_field=byfield,
        continuation_records=[r['record_id'] for r in state['records'] if len(r.get('fragments',[]))>1],
        limitation='Agreement with provided Excel, not verified image truth; page-edge records can be incomplete. Names reflect known schema disagreement. No speed comparison against manual work yet.'))
(out/'benchmark.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps([{k:v for k,v in r.items() if k!='by_field'} for r in summary]),flush=True)
