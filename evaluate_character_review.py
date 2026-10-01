"""Development-only review recall against format-stripped numeric Excel labels."""
import json
from difflib import SequenceMatcher
from pathlib import Path
from PIL import Image
from rapidocr_onnxruntime import RapidOCR
from character_review import read_line
from extract_fields import number
ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'outputs/auto-field-review/fields.json').read_text(encoding='utf-8'))
engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,text_score=0)
rows=[]
for item in data['results']:
    if item['field'] not in (18,19,20,21,23,24) or not item['crop']:continue
    numeric=number(item['comparison_target'])
    if numeric is None:continue
    target=format(numeric,'f')
    if '.' in target:target=target.rstrip('0').rstrip('.')
    segments=read_line(engine,Image.open(ROOT/'outputs/auto-field-review'/item['crop']))
    prediction='';flagged=[]
    for s in segments:
        a=len(prediction);prediction+=s['text']
        if s['category']!='single':flagged.append((a,len(prediction)))
    errors=[]
    for tag,a,b,c,d in SequenceMatcher(None,prediction,target,autojunk=False).get_opcodes():
        if tag=='equal':continue
        caught=any((lo<b and hi>a) or (a==b and lo<=a<=hi) or (lo==hi and a<=lo<=b) for lo,hi in flagged)
        errors.append(dict(predicted=prediction[a:b],target=target[c:d],flagged=caught))
    rows.append(dict(record=item['record_id'],field=item['field'],prediction=prediction,target=target,flagged_regions=len(flagged),differences=errors))
summary=dict(fields=len(rows),exact_fields=sum(not r['differences'] for r in rows),
    difference_regions=sum(len(r['differences']) for r in rows),flagged_difference_regions=sum(e['flagged'] for r in rows for e in r['differences']),
    missed_difference_regions=sum(not e['flagged'] for r in rows for e in r['differences']),
    review_regions=sum(r['flagged_regions'] for r in rows))
out=ROOT/'outputs/character-review-evaluation.json'
out.write_text(json.dumps(dict(summary=summary,limitation='Same development pages and automatically estimated crops. Excel numeric display formatting stripped. Difference regions are alignment-dependent; this is not held-out character accuracy or calibrated confidence.',results=rows),indent=2),encoding='utf-8')
print(json.dumps(summary))
