"""Provisional text boundaries from OCR only; Excel is loaded after extraction."""
import html
import json
import re
from pathlib import Path
from extract_dates_postal import locate as date_spans
from extract_remaining_fields import locate_remaining

ROOT=Path(__file__).resolve().parent
FIELDS=(4,5,6,7,10,11,12,14,16,17,22,26,27,28,31,32,33,34,35)
TIME=re.compile(r'night|evening|morning|afternoon',re.I)
TITLE=re.compile(r'^(?:mrs|miss|mis|mrr|mr|ms|maj|col|dr)(?:\.+|(?=\s|$))',re.I)

def split_person(text,offset):
    lead=len(text)-len(text.lstrip());text=text.strip();offset+=lead
    title=TITLE.match(text)
    if title:
        end=title.end()
    else:
        space=re.search(r'\s+',text)
        if not space:return None
        end=space.start()
    remainder=end
    while remainder<len(text) and text[remainder].isspace():remainder+=1
    if remainder==len(text):return None
    return ((offset,offset+end),(offset+remainder,offset+len(text)))

def locate(text):
    found={};issues={}
    phone=re.search(r'\d{11}-\d{4}',text)
    lid=re.search(r'L[i1]d/[A-Za-z0-9/]+-[A-Za-z0-9]+-\d+',text,re.I)
    if lid and phone:
        head=text[lid.end():phone.start()]
        address=re.search(r'(?:P[.\s]*[O0][.\s]*(?:Box|Bak|B\b)|\d{3,})',head,re.I)
        if address:
            person=split_person(head[:address.start()],lid.end())
            if person:found.update(zip((4,5),person))
    spans,_=date_spans(text)
    date=spans.get(9)
    if date and phone and date[1]<phone.start():
        between=text[date[1]:phone.start()]
        times=list(TIME.finditer(between))
        if len(times)==1:
            time=times[0];a=date[1]+time.start();b=date[1]+time.end()
            found[12]=(a,b)
            if text[b:phone.start()].strip():found[14]=(b,phone.start())
            person=split_person(text[date[1]:a],date[1])
            if person:found.update(zip((10,11),person))
    if phone:
        # Purpose word variants are locators only: return their original OCR spelling.
        tail=text[phone.end():]
        purpose=re.match(r'\s*(?:Debt|Debit|dect)\s*c[a-z]{3,22}?tionn?',tail,re.I)
        if purpose:
            start=phone.end()+purpose.start();end=phone.end()+purpose.end()
            found[16]=(start,end)
            amount=re.search(r'(?m)^\s*\d{5,}(?:\.\d+)?\s*$',text[end:])
            if amount:
                product_end=end+amount.start()
                if text[end:product_end].strip():found[17]=(end,product_end)
        secured=re.search(r'Secured\s*Loan',tail,re.I)
        if secured:found[22]=(phone.end()+secured.start(),phone.end()+secured.end())
    final=re.search(r'(?i)(G[a-z]{1,8})\s*$',text)
    if final and final.group(1).lower() in ('good','goood','giood','gclod','goog','gd'):
        found[35]=final.span(1)
    found.update(locate_remaining(text))
    for field in FIELDS:
        if field not in found:issues[field]='No unambiguous boundary under the current text rules'
    return found,issues

def extract(parts):
    text='';sources=[]
    for part in parts:
        for line in part['lines']:
            sources.append((len(text),len(text)+len(line['text']),part['image'],line['box']))
            text+=line['text']+'\n'
    spans,issues=locate(text);rows=[]
    for field in FIELDS:
        span=spans.get(field)
        original=text[slice(*span)] if span else None
        evidence=[dict(image=image,box=box,overlap=[max(lo,span[0]),min(hi,span[1])])
                  for lo,hi,image,box in sources if span and lo<span[1] and hi>span[0]]
        rows.append(dict(field=field,raw_ocr=' '.join(original.split()) if original else None,
                         source_text=original,source_regions=evidence,character_span=span,
                         issue=issues.get(field),boundary_status='provisional' if span else 'unresolved'))
    return rows

def main():
    data=json.loads((ROOT/'outputs/auto-records/results.json').read_text(encoding='utf-8'))
    predictions={}
    for rid in {r['record_id'] for r in data}:
        parts=sorted((r for r in data if r['record_id']==rid),key=lambda r:r['part'])
        predictions[rid]=extract(parts)
    # Comparison only, after every prediction has been generated.
    ref=json.loads((ROOT/'outputs/ocr-reference/reference.json').read_text(encoding='utf-8'))
    rows=[]
    for record in ref['records']:
        for row in predictions.get(record['record_id'],[dict(field=f,raw_ocr=None,issue='Record not detected') for f in FIELDS]):
            target=record['fields'][row['field']-1]['accepted_output']
            rows.append(dict(**row,record_id=record['record_id'],target=target,
                status='unresolved' if row['raw_ocr'] is None else ('exact_agreement' if row['raw_ocr']==target else 'different')))
    counts={s:sum(r['status']==s for r in rows) for s in ('exact_agreement','different','unresolved')}
    out=ROOT/'outputs/text-field-review';out.mkdir(parents=True,exist_ok=True)
    payload=dict(counts=counts,method='Provisional OCR text anchors and name splits. Whitespace collapsed for cell candidates; source_text preserves original characters. No spelling or case correction. No Excel text supplied to locators.',results=rows)
    (out/'text-fields.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    esc=lambda v:html.escape('' if v is None else str(v))
    body='<meta charset="utf-8"><title>Text field extraction</title><style>body{font:16px system-ui;margin:30px}td,th{padding:12px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}pre{white-space:pre-wrap}</style><h1>Text field extraction</h1><p>'+esc(payload['method'])+'</p><p>Excel is authoritative. Differences are development diagnostics; no confirmation is requested. Name boundaries remain provisional.</p><pre>'+esc(json.dumps(counts,indent=2))+'</pre><table><tr><th>Record / field</th><th>OCR candidate</th><th>Excel target</th><th>Result</th></tr>'
    for row in rows:body+=f'<tr><td>{row["record_id"]} / {row["field"]}</td><td>{esc(row["raw_ocr"])}</td><td>{esc(row["target"])}</td><td>{esc(row["status"])}<br>{esc(row.get("issue"))}</td></tr>'
    (out/'review.html').write_text(body+'</table>',encoding='utf-8')
    print(json.dumps(counts))

if __name__=='__main__':main()
