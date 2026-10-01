"""Test recognition-only on the four field crops with user-confirmed labels."""
import html
import json
from pathlib import Path
from rapidocr_onnxruntime import RapidOCR

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'outputs' / 'ocr-baseline'

def main():
    baseline = json.loads((OUT / 'results.json').read_text(encoding='utf-8'))
    policy=json.loads((ROOT/'reference-policy.json').read_text(encoding='utf-8')) if (ROOT/'reference-policy.json').exists() else {}
    if policy.get('authority')=='manual_excel':
        raise SystemExit('Historical visual-label benchmark disabled: use extract_fields.py for current Excel-target comparisons. Original benchmark labels were superseded.')
    engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1, text_score=0.0)
    rows = []
    for item in baseline:
        if item['kind'] != 'confirmed_field':
            continue
        result, _ = engine(str(OUT / item['image']), use_det=False, use_cls=False)
        text = '\n'.join(r[0] for r in (result or []))
        rows.append(dict(key=item['key'], variant=item['variant'], image=item['image'],
                         expected=item['expected'], text=text, exact_match=text == item['expected'],
                         model_scores=[float(r[1]) for r in (result or [])]))
    summary = {v: dict(total=4, exact_matches=sum(r['exact_match'] for r in rows if r['variant']==v))
               for v in ('original', 'enlarged_3x', 'contrast_3x')}
    payload = dict(mode='Recognition only; manually located fields; no detection or spelling repair',
                   limitation='Four selected development examples. Not whole-document accuracy or independent evaluation.',
                   summary=summary, results=rows)
    (OUT / 'known-fields.json').write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    body = '<!doctype html><meta charset="utf-8"><title>Known-field OCR checks</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;color:#172b3a}td,th{padding:12px;text-align:left;border-bottom:1px solid #ddd}img{max-width:300px}code{white-space:pre-wrap}table{width:100%}</style><h1>Known-field OCR checks</h1><p>Recognition only: field locations are supplied manually. No spell correction. Four user-confirmed development examples only.</p><p>Model scores are not accuracy probabilities. These results do not measure record splitting or 36-field extraction.</p><table><tr><th>Field / variant</th><th>Source</th><th>OCR reading</th><th>Confirmed value</th><th>Exact match</th></tr>'
    for r in rows:
        body += f'<tr><td>{html.escape(r["key"])}<br>{html.escape(r["variant"])}</td><td><img src="{r["image"]}"></td><td><code>{html.escape(r["text"])}</code></td><td><code>{html.escape(r["expected"])}</code></td><td>{r["exact_match"]}</td></tr>'
    body += '</table><p><a href="report.html">Full baseline report</a></p>'
    (OUT / 'known-fields.html').write_text(body, encoding='utf-8')
    assert len(rows)==12 and len({r['key'] for r in rows})==4
    print(json.dumps(payload, indent=2, ensure_ascii=True))

if __name__=='__main__':
    main()
