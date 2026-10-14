"""Locate a bounded set of fields from OCR anchors, reread crops, expose failures.

Manual Excel values are used only after extraction for comparison, never location.
"""
import html
import argparse
import json
import re
import numpy as np
from decimal import Decimal, InvalidOperation
from pathlib import Path
from PIL import Image
from client_rules import property_anchor

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'outputs/ocr-baseline'
OUT=ROOT/'outputs/field-review'
FIELDS=(1,3,15,18,19,20,21,23,24)
# Explicit development fallbacks, chosen visually from the source, not automatic locations.
MANUAL_REGIONS={
    ('1802603504',24):(160,(170,228,226,246)),
    ('1802603505',24):(160,(274,434,326,452)),
    ('1802603511',24):(160,(642,636,700,655)),
    ('1802603506',3):(160,(123,538,312,557)),
    ('1802603509',3):(160,(591,136,786,156)),
    ('1802603512',3):(160,(591,739,786,759)),
}
NUM=re.compile(r'(?<![A-Za-z0-9.])\d+(?:\.\d+)?(?![A-Za-z0-9]|\.\d)')
# These are location candidates, not corrected numbers. OCR punctuation such as
# 6:87 or 35896-08 must remain attached to its digits so a bad glyph does not
# change the number of fields. Field rules/review decide the actual reading.
FINANCIAL_NUMBER = r'(?:\d+(?:,\d{3})*(?:[.:：-]\d+)?|[.:：-]\d+)'
FINANCIAL_TOKEN = re.compile(r'(?<![\w.,:：-])' + FINANCIAL_NUMBER + r'(?![\w.,:：-])')
SECURED_LOAN = re.compile(r'Secured\s*L[o0]an',re.I)


def separated_text(text, separators):
    """Insert evidence-backed spaces for location, retaining original offsets.

    A missing-space OCR alternative can separate e.g. 680000 and 480. No
    character count, expected value or reference Excel data supplies a split.
    """
    characters=[]; boundaries=[0]
    for i,c in enumerate(text):
        if i in separators and i and not text[i-1].isspace() and not c.isspace():
            characters.append(' ');boundaries.append(i)
        characters.append(c);boundaries.append(i+1)
    return ''.join(characters),boundaries


def loan_section(text, separators=()):
    """Locate the financial run and its following label, preserving spelling.

    'Secured Loan' can itself be a mortgage type. Prefer the label after the
    four financial values; a repeated label without that evidence is ambiguous.
    """
    phone=property_anchor(text)
    if not phone:return None,[]
    labels=list(SECURED_LOAN.finditer(text,phone.end()))
    # A misspelled Existing Loan label is still literal source text. Only use a
    # broader label candidate when four separate financial values support it.
    candidates={m.span():m for m in labels}
    for candidate in re.finditer(r'\b[A-Za-z]{3,14}\s+L[o0]an\b',text[phone.end():],re.I):
        start=phone.end()+candidate.start()
        match=re.compile(r'\b[A-Za-z]{3,14}\s+L[o0]an\b',re.I).match(text,start)
        candidates[match.span()]=match
    supported=[]
    for label in candidates.values():
        start,end=phone.end(),label.start()
        window,boundaries=separated_text(text[start:end],{i-start for i in separators if start<i<end})
        tokens=list(FINANCIAL_TOKEN.finditer(window))
        consecutive=len(tokens)==4 and all(not window[a.end():b.start()].strip() for a,b in zip(tokens,tokens[1:]))
        if consecutive:consecutive=not window[tokens[-1].end():].strip()
        if consecutive:
            supported.append((label,[(start+boundaries[m.start()],start+boundaries[m.end()]) for m in tokens]))
    if len(supported)==1:return supported[0]
    if not supported and len(labels)==1:
        # If four numbers FOLLOW the only readable label, it can be the
        # mortgage type with an unreadable later Existing Loan label. Do not
        # relabel the loan amount and term as income and down payment.
        following=re.match(r'\s*'+r'\s+'.join([FINANCIAL_NUMBER]*4)+r'(?=\s|$)',text[labels[0].end():])
        if not following:return labels[0],[]
    return None,[]

def split_wide_gaps(lines,image,engine):
    refined=[]
    for line in lines:
        # Only split numeric runs / secured-loan boxes. Keep other text intact.
        text=line['text']
        if not ((re.fullmatch(r'[0-9.\s]+',text) and text.count('.')>1) or re.search(r'Secured.*\d',text,re.I)):
            refined.append(line);continue
        pts=line['box']; x0=max(0,int(min(p[0] for p in pts))); x1=min(image.width,int(max(p[0] for p in pts))+1)
        y0=max(0,int(min(p[1] for p in pts))); y1=min(image.height,int(max(p[1] for p in pts))+1)
        region=image.crop((x0,y0,x1,y1)); ink=np.asarray(region.convert('L'))<150
        occupied=np.sum(ink,axis=0)>=2
        runs=[]; start=None;last=None
        for x,active in enumerate(occupied):
            if active:
                if start is None:start=x
                elif last is not None and x-last>8:
                    runs.append((start,last+1));start=x
                last=x
        if start is not None:runs.append((start,last+1))
        if len(runs)<2:
            refined.append(line);continue
        for left,right in runs:
            box=(max(0,x0+left-2),max(0,y0-1),min(image.width,x0+right+2),min(image.height,y1+1))
            crop=image.crop(box); arr=np.asarray(crop.convert('RGB'))[:,:,::-1].copy()
            result,_=engine(arr,use_det=False,use_cls=False)
            new=' '.join(r[0] for r in (result or []))
            refined.append(dict(text=new,box=[[box[0],box[1]],[box[2],box[1]],[box[2],box[3]],[box[0],box[3]]],score=0))
    return refined

def locate(lines):
    text=''; offsets=[];separators=set()
    for line in lines:
        separators.update(len(text)+i for i in line.get('separator_offsets',[]) if 0<i<len(line['text']))
        offsets.append((len(text),len(text)+len(line['text']),line))
        text+=line['text']+'\n'
    found={}; issues={}
    ident=re.search(r'\b\d{10}\b',text[:50])
    lid=re.search(r'L[i1]d/[A-Za-z0-9/]+-[A-Za-z0-9]+-\d+',text)
    phone=property_anchor(text)
    for field,match in ((1,ident),(3,lid),(15,phone)):
        if match: found[field]=match.span()
        else: issues[field]='Anchor not recognized'
    secured,numeric_spans=loan_section(text,separators)
    if phone and secured and secured.start()>phone.end():
        # Four candidates must form a continuous run immediately before the
        # Secured Loan anchor. Never skip an unreadable token to shift columns.
        if numeric_spans:
            found.update(zip((18,19,20,21),numeric_spans))
        else:
            for field in (18,19,20,21): issues[field]='No continuous sequence of four separate numeric candidates before Secured Loan'
        tail=text[secured.end():]
        first=re.match(r'\s*[:：]?\s*(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)(?=\s|$)',tail)
        if first:
            for field,group in ((23,1),(24,2)):
                a,b=first.span(group); found[field]=(secured.end()+a,secured.end()+b)
        else:
            issues[23]=issues[24]='Two amounts after Secured Loan are not clearly separated'
            first_only=re.match(r'\s*[:：]?\s*(\d+(?:\.\d+)?)(?=\s|$)',tail)
            if first_only:
                a,b=first_only.span(1);found[23]=(secured.end()+a,secured.end()+b);issues.pop(23,None)
    else:
        for field in (18,19,20,21,23,24): issues[field]='Missing or out-of-order identifier / Secured Loan anchors'
    boxes={}
    for field,(a,b) in found.items():
        line=next(((lo,hi,obj) for lo,hi,obj in offsets if lo<=a and b<=hi),None)
        if line is None:
            issues[field]='Candidate spans multiple OCR boxes'; continue
        lo,hi,obj=line; pts=obj['box']; x0=min(p[0] for p in pts); x1=max(p[0] for p in pts)
        y0=min(p[1] for p in pts); y1=max(p[1] for p in pts)
        # Approximate within-box position from OCR character offsets. Must be reviewed.
        left=x0+(x1-x0)*(a-lo)/max(hi-lo,1); right=x0+(x1-x0)*(b-lo)/max(hi-lo,1)
        boxes[field]=dict(box=[int(left)-2,int(y0)-2,int(right)+3,int(y1)+3],
                          locator_text=text[a:b],character_span=[a,b],approximate_boundary=(a!=lo or b!=hi))
    if 18 in boxes and secured:boxes[18]['following_label_span']=list(secured.span())
    return boxes,issues

def number(value):
    if value is None:return None
    value=str(value).strip().removesuffix(' Months').removesuffix('%').removeprefix('$')
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?',value): return None
    try:return Decimal(value.replace(',',''))
    except InvalidOperation:return None

def main():
    from rapidocr_onnxruntime import RapidOCR
    global OUT
    parser=argparse.ArgumentParser();parser.add_argument('--automatic',action='store_true');args=parser.parse_args()
    if args.automatic:OUT=ROOT/'outputs/auto-field-review'
    OUT.mkdir(parents=True,exist_ok=True)
    input_file=ROOT/'outputs/auto-records/results.json' if args.automatic else BASE/'results.json'
    baseline=json.loads(input_file.read_text(encoding='utf-8'))
    reference=json.loads((ROOT/'outputs/ocr-reference/reference.json').read_text(encoding='utf-8'))
    engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,text_score=0.0)
    output=[]
    for record in reference['records']:
        rid=record['record_id']; entry=next(r for r in baseline if r['key']==rid+'-part-1' and r.get('variant','original')=='original')
        image=Image.open(BASE/entry['image'])
        refined=split_wide_gaps(entry['lines'],image,engine)
        boxes,issues=locate(refined)
        for field in FIELDS:
            ref=record['fields'][field-1]; region=boxes.get(field); raw=None; crop=None
            if region:
                x0,y0,x1,y1=region['box']; box=(max(0,x0),max(0,y0),min(image.width,x1),min(image.height,y1))
                crop=f'{rid}-field-{field}.png'; image.crop(box).save(OUT/crop)
                result,_=engine(str(OUT/crop),use_det=False,use_cls=False)
                raw='\n'.join(r[0] for r in (result or []))
            if not args.automatic and (rid,field) in MANUAL_REGIONS:
                page,box=MANUAL_REGIONS[(rid,field)]
                source=Path(f'D:/projects/piXeL/manual/FORM TTYFRD_8AQ{page}_enc.jpg')
                crop=f'{rid}-field-{field}.png';Image.open(source).crop(box).save(OUT/crop)
                result,_=engine(str(OUT/crop),use_det=False,use_cls=False)
                raw='\n'.join(r[0] for r in (result or []))
                region=dict(source_image=str(source),box=list(box),method='Manually selected development fallback')
                issues.pop(field,None)
            target=ref['raw_source_text'] if ref['status']=='user_confirmed' else ref['manual_value']
            if raw is None:status='unresolved'
            elif field in (1,3,15):status='agrees' if raw==target else 'disagrees'
            else:
                actual,expected=number(raw),number(target)
                status='needs_review' if actual is None or expected is None else ('agrees' if actual==expected else 'disagrees')
            output.append(dict(record_id=rid,field=field,excel_cell=ref['excel_cell'],manual_value=ref['manual_value'],
                reference_status=ref['status'],comparison_target=target,raw_ocr=raw,status=status,crop=crop,
                accepted_output=ref['accepted_output'],confirmation_basis=ref.get('confirmation_basis'),
                location=region,issue=issues.get(field),comparison='literal' if field in (1,3,15) else 'numeric value after removing display formatting'))
        print(rid,flush=True)
    counts={s:sum(r['status']==s for r in output) for s in ('agrees','disagrees','needs_review','unresolved')}
    payload=dict(target_fields=list(FIELDS),total_slots=len(output),counts=counts,
                 mode='Automatic page and field locations; no manual fallbacks' if args.automatic else 'Prototype with supplied record regions and manual field fallbacks',
                 limitation='Agrees measures numeric or literal agreement with the authoritative Excel target, not proven source transcription accuracy. Field locations are estimated from OCR anchors; mode records whether manual regions or fallbacks were used.',results=output)
    (OUT/'fields.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    esc=lambda x:html.escape('' if x is None else str(x))
    body='''<!doctype html><meta charset="utf-8"><title>Field extraction review</title><style>body{font:16px system-ui;margin:28px;color:#172b3a}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}img{max-width:430px;min-height:25px}code{white-space:pre-wrap;overflow-wrap:anywhere}.disagrees,.needs_review,.unresolved{background:#fff3da}button{padding:8px;margin:12px 0}</style><h1>Field extraction review</h1><p>Nine fields across 11 records. Raw OCR is never replaced by the manual values. Crops use automatically estimated field positions within preselected record regions.</p><p>Agreement with manual Excel is not verified accuracy. Amber rows need review. Missing fields remain unresolved.</p><button onclick="document.querySelectorAll('tr.agrees').forEach(r=>r.hidden=!r.hidden)">Show / hide agreements</button>'''
    body+='<pre>'+esc(json.dumps(counts,indent=2))+'</pre><p>User-confirmed output below is retained even if OCR still disagrees. Manually located fallback crops are labelled; their recognition is not automatic-location performance.</p><table><tr><th>Record / field</th><th>Image crop</th><th>OCR</th><th>Comparison value</th><th>Status / notes</th><th>Accepted output</th></tr>'
    if args.automatic:
        body=body.replace('within preselected record regions','within automatically detected record regions').replace('Manually located fallback crops are labelled; their recognition is not automatic-location performance.','This run uses automatic page and field locations; manual fallbacks are disabled.')
    body=body.replace('Amber rows need review.','Amber rows are development diagnostics, not requests for your confirmation.').replace('User-confirmed output below','Excel-authoritative output below')
    for r in sorted(output,key=lambda r:(r['status']=='agrees',r['record_id'],r['field'])):
        img=f'<img src="{r["crop"]}">' if r['crop'] else 'No reliable field region'
        method=(r['location'] or {}).get('method','Automatic estimate')
        body+=f'<tr class="{r["status"]}"><td>{r["record_id"]}<br>Field {r["field"]} ({r["excel_cell"]})</td><td>{img}<br>{esc(method)}</td><td><code>{esc(r["raw_ocr"])}</code></td><td><code>{esc(r["comparison_target"])}</code><br>{r["reference_status"]}</td><td>{r["status"]}<br>{esc(r["issue"])}<br>{r["comparison"]}</td><td>{esc(r["accepted_output"])}<br>{esc(r["confirmation_basis"])}</td></tr>'
    (OUT/'review.html').write_text(body+'</table>',encoding='utf-8')
    assert len(output)==99 and sum(counts.values())==99
    print(json.dumps(counts))

if __name__=='__main__':main()
