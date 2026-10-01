"""Prepare name-field review samples. Field locations are manually annotated."""
import html
import json
from pathlib import Path
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs/name-review'
BOXES={
 ('1802603502',4):[(159,(790,773,925,795))],
 ('1802603502',5):[(159,(541,791,639,811))],
 ('1802603503',4):[(159,(793,992,828,1014))],
 ('1802603503',5):[(159,(840,992,932,1014)),(159,(490,1010,599,1030))],
 ('1802603504',4):[(160,(321,124,349,144))],
 ('1802603504',5):[(160,(374,124,436,144)),(160,(22,143,119,162))],
 ('1802603505',4):[(160,(320,332,359,353))],
 ('1802603505',5):[(160,(373,332,458,353)),(160,(22,349,96,372))],
 ('1802603506',4):[(160,(319,538,355,557))],
 ('1802603506',5):[(160,(374,538,466,557)),(160,(23,555,83,575))],
 ('1802603507',4):[(160,(320,742,456,762))],
 ('1802603507',5):[(160,(71,759,161,781))],
 ('1802603508',4):[(160,(321,966,359,986))],
 ('1802603508',5):[(160,(70,983,241,1005))],
 ('1802603509',4):[(160,(791,136,832,158))],
 ('1802603509',5):[(160,(841,136,928,158)),(160,(490,153,598,175))],
 ('1802603510',4):[(160,(790,327,837,348))],
 ('1802603510',5):[(160,(843,327,934,348)),(160,(490,344,575,366))],
 ('1802603511',4):[(160,(790,531,894,553))],
 ('1802603511',5):[(160,(895,531,921,553)),(160,(490,550,588,572))],
 ('1802603512',4):[(160,(791,739,832,759))],
 ('1802603512',5):[(160,(839,739,935,759)),(160,(490,756,608,778))],
}

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 ref=json.loads((ROOT/'outputs/ocr-reference/reference.json').read_text(encoding='utf-8'))
 records={r['record_id']:r for r in ref['records']}
 engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,text_score=0.0)
 images={p:Image.open(f'D:/projects/piXeL/manual/FORM TTYFRD_8AQ{p}_enc.jpg') for p in (159,160)}
 rows=[]
 for (rid,field),regions in BOXES.items():
  parts=[];paths=[];crops=[]
  for i,(page,box) in enumerate(regions):
   crop=images[page].crop(box);name=f'{rid}-{field}-{i}.png';crop.save(OUT/name);paths.append(name);crops.append(crop)
   result,_=engine(str(OUT/name),use_det=False,use_cls=False)
   parts.append(' '.join(r[0] for r in (result or [])))
  raw=' '.join(parts);f=records[rid]['fields'][field-1];manual=f['manual_value'];target=f['raw_source_text'] if f['status']=='user_confirmed' else manual
  status='exact_agreement' if raw==target else ('case_only' if raw.casefold()==target.casefold() else 'reading_or_boundary_review')
  rows.append(dict(record_id=rid,field=field,regions=regions,crops=paths,raw_ocr=raw,manual=manual,comparison_target=target,status=status,reference_status=f['status'],accepted_output=f['accepted_output']))
  canvas=Image.new('RGB',(max(c.width for c in crops),sum(c.height for c in crops)+4*(len(crops)-1)),'white');y=0
  for crop in crops:canvas.paste(crop,(0,y));y+=crop.height+4
  canvas.save(OUT/f'{rid}-field-{field}-context.png')
 counts={s:sum(r['status']==s for r in rows) for s in ('exact_agreement','case_only','reading_or_boundary_review')}
 (OUT/'names.json').write_text(json.dumps(dict(location_method='Manual annotations; not automatic field detection',counts=counts,results=rows),indent=2,ensure_ascii=False),encoding='utf-8')
 esc=lambda s:html.escape(str(s or ''))
 body='''<!doctype html><meta charset="utf-8"><title>Name review</title><style>body{font:16px system-ui;margin:30px;color:#172b3a}table{border-collapse:collapse;width:100%}td,th{padding:14px;border-bottom:1px solid #ddd;text-align:left}img{max-width:450px;min-width:120px}code{white-space:pre-wrap}.reading_or_boundary_review{background:#fff3cd}</style><h1>Primary-name review</h1><p>Two fields across 11 records, manually located. Multiple crops follow printed order. Spelling and case remain unchanged by OCR postprocessing. Manual entries remain unverified unless labelled user-confirmed. A disagreement can be an OCR error, crop error, or manual-entry error.</p><table><tr><th>Record / field</th><th>Image</th><th>OCR</th><th>Manual reference</th><th>Status</th></tr>'''
 for r in rows:
  imgs=''.join(f'<img src="{p}"><br>' for p in r['crops'])
  body+=f'<tr class="{r["status"]}"><td>{r["record_id"]}<br>Field {r["field"]}</td><td>{imgs}</td><td><code>{esc(r["raw_ocr"])}</code></td><td><code>{esc(r["comparison_target"])}</code></td><td>{r["status"]}<br>{r["reference_status"]}</td></tr>'
 (OUT/'review.html').write_text(body+'</table>',encoding='utf-8')
 print(json.dumps(counts));print(json.dumps([(r['record_id'],r['field'],r['raw_ocr'],r['manual']) for r in rows],ensure_ascii=True))

if __name__=='__main__':main()
