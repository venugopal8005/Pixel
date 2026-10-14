"""Reference-code prototype using OCR anchors across record continuation regions."""
import html
import argparse
import json
import re
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'outputs/ocr-baseline'
OUT=ROOT/'outputs/code-review'
ANCHORS={29:re.compile(r'[UD]\.T\.R\.N[o0][._:#]*',re.I),30:re.compile(r'N\.I\.N[o0][._:#]*',re.I)}

def find_span(text,field):
    anchor=ANCHORS[field].search(text)
    if not anchor:return None
    stop=len(text)
    other=ANCHORS[30 if field==29 else 29].search(text,anchor.end())
    if other:stop=other.start()
    # Seven trailing digits are an observed candidate pattern, not a validated universal rule.
    ending=re.search(r'(?<!\d)\d{7}(?!\d)',text[anchor.end():stop])
    if not ending:
        # Short identifiers in the new manual have no fixed digit count. A
        # self-contained non-whitespace code is safe to locate; never swallow
        # following occupation/name tokens to invent a complete identifier.
        token=re.match(r'[^\s]+',text[anchor.end():stop])
        if not token or not re.search(r'\d',token.group()):return None
        return anchor.start(),anchor.end()+token.end()
    return anchor.start(),anchor.end()+ending.end()

def main():
    from rapidocr_onnxruntime import RapidOCR
    global BASE, OUT
    parser=argparse.ArgumentParser()
    parser.add_argument('--automatic',action='store_true')
    args=parser.parse_args()
    if args.automatic:
        BASE=ROOT/'outputs/auto-records'
        OUT=ROOT/'outputs/auto-code-review'
    OUT.mkdir(parents=True,exist_ok=True)
    baseline=json.loads((BASE/'results.json').read_text(encoding='utf-8'))
    reference=json.loads((ROOT/'outputs/ocr-reference/reference.json').read_text(encoding='utf-8'))
    engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,text_score=0)
    rows=[]
    for record in reference['records']:
        rid=record['record_id'];text='';indexed=[]
        parts=sorted((r for r in baseline if r['key'].startswith(f'{rid}-part-') and r.get('variant','original')=='original'),key=lambda r:int(r['key'].rsplit('-',1)[1]))
        for result in parts:
            for line in result['lines']:
                indexed.append((len(text),len(text)+len(line['text']),line,result['image']))
                text+=line['text']+'\n'
        for field in (29,30):
            span=find_span(text,field);crops=[];readings=[];locations=[]
            if span:
                a,b=span
                for lo,hi,line,image_name in indexed:
                    if hi<=a or lo>=b:continue
                    p,q=max(a,lo),min(b,hi);points=line['box'];x0=min(v[0] for v in points);x1=max(v[0] for v in points)
                    y0=min(v[1] for v in points);y1=max(v[1] for v in points)
                    left=int(x0+(x1-x0)*(p-lo)/max(hi-lo,1))-2;right=int(x0+(x1-x0)*(q-lo)/max(hi-lo,1))+3
                    image=Image.open(BASE/image_name);box=(max(0,left),max(0,int(y0)-2),min(image.width,right),min(image.height,int(y1)+3))
                    name=f'{rid}-field-{field}-part-{len(crops)+1}.png';image.crop(box).save(OUT/name);crops.append(name)
                    result,_=engine(str(OUT/name),use_det=False,use_cls=False)
                    readings.extend(r[0] for r in (result or []));locations.append(dict(source_crop=image_name,box=list(box)))
            raw=''.join(readings) if span else None;expected=record['fields'][field-1]['accepted_output']
            rows.append(dict(record_id=rid,field=field,raw_ocr=raw,target=expected,
                             status='unresolved' if raw is None else ('exact_agreement' if raw==expected else 'different'),
                             source_regions=locations,crops=crops,locator_text=text[slice(*span)] if span else None))
    counts={s:sum(r['status']==s for r in rows) for s in ('exact_agreement','different','unresolved')}
    method=('Automatically detected page records and OCR-anchor field locations.' if args.automatic else 'Automatic OCR-anchor locations within manually supplied record regions.')+' Wrap fragments joined in reading order. Excel used only for comparison.'
    payload=dict(counts=counts,method=method,results=rows)
    (OUT/'codes.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    esc=lambda x:html.escape(str(x or ''))
    body='''<!doctype html><meta charset="utf-8"><title>Reference-code extraction</title><style>body{font:16px system-ui;margin:28px;color:#172b3a}td,th{padding:14px;border-bottom:1px solid #ddd;vertical-align:top;text-align:left}img{max-width:450px}code{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>Reference-code extraction</h1><p>Excel is authoritative. Differences are diagnostics for development, not confirmation requests. Locations are estimated automatically within the existing record crops; this is not an unseen-page test.</p>'''
    body+='<p>'+esc(method)+'</p><pre>'+esc(json.dumps(counts,indent=2))+'</pre><table><tr><th>Record / field</th><th>Source crops</th><th>Raw OCR</th><th>Excel target</th><th>Status</th></tr>'
    for r in rows:
        imgs=''.join(f'<img src="{c}"><br>' for c in r['crops'])
        body+=f'<tr><td>{r["record_id"]}<br>{r["field"]}</td><td>{imgs}</td><td><code>{esc(r["raw_ocr"])}</code></td><td><code>{esc(r["target"])}</code></td><td>{r["status"]}</td></tr>'
    (OUT/'review.html').write_text(body+'</table>',encoding='utf-8');print(json.dumps(counts))

if __name__=='__main__':main()
