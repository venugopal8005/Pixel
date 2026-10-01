"""Read automatically detected records. Target IDs select scope, never OCR text."""
import argparse,json,time
from pathlib import Path
import numpy as np
from rapidocr_onnxruntime import RapidOCR

ROOT=Path(__file__).resolve().parent
def main():
 p=argparse.ArgumentParser();p.add_argument('--all-records',action='store_true');args=p.parse_args()
 detected=ROOT/'outputs/page-detection';out=ROOT/'outputs/auto-records';out.mkdir(parents=True,exist_ok=True)
 data=json.loads((detected/'records.json').read_text(encoding='utf-8'))
 refs=json.loads((ROOT/'outputs/ocr-reference/reference.json').read_text(encoding='utf-8'))
 targets={r['record_id'] for r in refs['records']}
 engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,text_score=0)
 result=[]
 for record in data['records']:
  if not args.all_records and record['record_id'] not in targets:continue
  for part,fragment in enumerate(record['parts'],start=1):
   start=time.perf_counter();raw,_=engine(str(detected/fragment['crop']),use_cls=False)
   lines=[dict(box=np.asarray(r[0]).tolist(),text=r[1],score=float(r[2])) for r in (raw or [])]
   result.append(dict(key=f'{record["record_id"]}-part-{part}',record_id=record['record_id'],part=part,
     source=fragment,image=str(detected/fragment['crop']),lines=lines,text='\n'.join(r['text'] for r in lines),seconds=round(time.perf_counter()-start,3)))
   (out/'results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
   print(result[-1]['key'],flush=True)
 print(f'Finished {len(result)} automatically located record fragments.',flush=True)
if __name__=='__main__':main()
