"""Provisional date/postal anchors from auto-detected records, without Excel cues."""
import html,json,re
from pathlib import Path
from client_rules import property_anchor
ROOT=Path(__file__).resolve().parent
DATE=re.compile(r'(?:[A-Za-z]{2,12}day[\s.,:]*)?(?:\d{1,2}/\d{1,2}/\d{4}|(?:[A-Za-z]{3,14}[\s.,:]*\d{1,2}|\d{1,2}[\s.,:]+[A-Za-z]{3,14})[\s.,:]*\d{4})(?!\d)',re.I)

def locate(text):
    # Stop before the account-like identifier to avoid loan data and trailing codes.
    phone=property_anchor(text)
    prefix=text[:phone.start()] if phone else text
    # Ignore the first ID/reference line. Dates belong in the following address block.
    first_newline=prefix.find('\n')
    offset=first_newline+1 if first_newline>=0 else 0
    candidates=[]
    for match in re.finditer(r'\d{1,2}[/.-]\d{1,2}[/.-](?:\d{4}|\d{2})(?!\d)',prefix[offset:]):
        candidates.append((offset+match.start(),offset+match.end()))
    for weekday in re.finditer(r'[A-Za-z]{2,12}da+y[\s.,:]*',prefix[offset:],re.I):
        a=offset+weekday.start();start=offset+weekday.end()
        year=re.search(r'(?:18|19|20)\d{2}(?!\d)',prefix[start:start+55])
        if year:candidates.append((a,start+year.end()))
        else:
            short=re.match(r'\d{1,2}[/.-]\d{1,2}[/.-]\d{2}(?!\d)',prefix[start:])
            if short:candidates.append((a,start+short.end()))
    # A weekday and slash date can describe the same source span.
    candidates=[span for span in candidates if not any(other!=span and other[0]<=span[0] and other[1]>=span[1] for other in candidates)]
    if len(candidates)!=1:return {},f'Expected one date-like source span; found {len(candidates)}'
    a,b=candidates[0];found={9:(a,b)}
    postal=re.search(r'(?<!\d)(\d{1,6})[\s.,:]*$',prefix[:a])
    if postal:found[8]=postal.span(1)
    return found,None

def main():
    out=ROOT/'outputs/date-postal-review';out.mkdir(parents=True,exist_ok=True)
    data=json.loads((ROOT/'outputs/auto-records/results.json').read_text(encoding='utf-8'))
    ref=json.loads((ROOT/'outputs/ocr-reference/reference.json').read_text(encoding='utf-8'))
    rows=[]
    for record in ref['records']:
        rid=record['record_id'];first=next((r for r in data if r['record_id']==rid and r['part']==1),None)
        text=first['text'] if first else '';spans,issue=locate(text)
        for field in (8,9):
            span=spans.get(field);raw=text[slice(*span)] if span else None
            target=record['fields'][field-1]['accepted_output']
            rows.append(dict(record_id=rid,field=field,raw_ocr=raw,target=target,
                status='unresolved' if raw is None else ('exact_agreement' if raw==target else 'different'),
                source_image=first['image'] if first else None,character_span=span,
                issue=(issue or 'No intact four/five digit run immediately before date') if raw is None else None))
    counts={s:sum(r['status']==s for r in rows) for s in ('exact_agreement','different','unresolved')}
    (out/'dates-postal.json').write_text(json.dumps(dict(counts=counts,method='Date-like pattern plus nearest preceding four/five digit run; provisional layout assumption. OCR strings preserved.',results=rows),indent=2,ensure_ascii=False),encoding='utf-8')
    esc=lambda x:html.escape(str(x or ''))
    body='''<!doctype html><meta charset="utf-8"><title>Date and postal extraction</title><style>body{font:16px system-ui;margin:30px}td,th{padding:12px;text-align:left;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}</style><h1>Date and postal extraction</h1><p>Automatically detected records. Excel is authoritative; differences are development diagnostics. Postal locations use a provisional nearest-number rule. Dates retain OCR spelling and punctuation; output date formatting is not implemented.</p>'''
    body+='<pre>'+esc(json.dumps(counts,indent=2))+'</pre><table><tr><th>Record</th><th>Field</th><th>Raw OCR</th><th>Excel target</th><th>Status</th></tr>'
    for r in rows:body+=f'<tr><td>{r["record_id"]}</td><td>{r["field"]}</td><td>{esc(r["raw_ocr"])}</td><td>{esc(r["target"])}</td><td>{r["status"]}</td></tr>'
    (out/'review.html').write_text(body+'</table>',encoding='utf-8');print(json.dumps(counts))
if __name__=='__main__':main()
