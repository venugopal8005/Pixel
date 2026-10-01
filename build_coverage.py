"""All-field coverage report: missing extraction must never become a target copy."""
import json
import argparse
import html
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--automatic',action='store_true')
    args=parser.parse_args()
    ref=json.loads((OUT/'ocr-reference/reference.json').read_text(encoding='utf-8'))
    predictions={}
    files=('auto-field-review/fields.json','auto-code-review/codes.json','date-postal-review/dates-postal.json','text-field-review/text-fields.json') if args.automatic else ('field-review/fields.json','name-review/names.json','code-review/codes.json','date-postal-review/dates-postal.json')
    for file in files:
        data=json.loads((OUT/file).read_text(encoding='utf-8'))
        for item in data['results']:
            key=(item['record_id'],item['field'])
            assert key not in predictions
            predictions[key]=dict(raw_ocr=item['raw_ocr'],comparison_status=item['status'],evidence=file)
    rows=[]
    for record in ref['records']:
        for field in record['fields']:
            prediction=predictions.get((record['record_id'],field['field']))
            rows.append(dict(record_id=record['record_id'],field=field['field'],excel_target=field['accepted_output'],
                             coverage='not_implemented' if prediction is None else ('unresolved' if prediction['raw_ocr'] is None else 'candidate_extracted'),
                             prediction=prediction))
    counts={s:sum(r['coverage']==s for r in rows) for s in ('candidate_extracted','unresolved','not_implemented')}
    destination=OUT/'automatic-report' if args.automatic else OUT
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'coverage.json').write_text(json.dumps(dict(total_field_slots=len(rows),counts=counts,
        note='Candidate extraction does not establish correctness. Target labels are not OCR predictions. Blank and N.A. columns remain explicit slots.',results=rows),indent=2,ensure_ascii=False),encoding='utf-8')
    assert len(rows)==396 and sum(counts.values())==396
    if args.automatic:
        esc=lambda value:html.escape('' if value is None else str(value))
        body='''<!doctype html><meta charset="utf-8"><title>Pixel automatic extraction</title>
<style>body{font:16px system-ui;color:#193347;max-width:1250px;margin:32px auto;padding:0 20px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#edf3f7}code{white-space:pre-wrap}.summary{padding:20px;background:#edf3f7;border-radius:12px}</style>
<h1>Automatic extraction — development results</h1>
<p>Your Excel is the authoritative target. OCR readings below are independent predictions; differences do not need your confirmation.</p>
<div class="summary"><strong>Two supplied pages · 11 labelled records · 36 target fields per record</strong>
<p>32 image fields are attempted automatically, including provisional address, organization and name boundaries. Four blank/placeholder columns have no source mapping and remain empty in independent exports. Manually located prototype results are excluded. This is a development sample, not a test of unseen-image accuracy.</p>'''
        body+='<p>'+ ' · '.join(f'{count} {name.replace("_"," ")}' for name,count in counts.items())+'</p></div>'
        body+='''<p><a href="../auto-field-review/review.html">Numbers and IDs with crops</a> · <a href="../auto-code-review/review.html">Reference codes with crops</a> · <a href="../date-postal-review/review.html">Dates and postal codes</a> · <a href="../text-field-review/review.html">Names and text fields</a></p>
<p><a href="../page-detection/page-1-detected.png">Page 1 detected records</a> · <a href="../page-detection/page-2-detected.png">Page 2 detected records</a></p>
<p>Numeric agreement can ignore currency, percent and term formatting. Other comparisons retain the exact OCR string. Neither kind proves the pixels were read correctly. Missing fields stay unresolved; they are never filled with Excel answers to improve the score.</p>
<h2>All field slots</h2><table><tr><th>Record / field</th><th>Independent OCR</th><th>Excel target</th><th>Result</th></tr>'''
        for row in rows:
            p=row['prediction']
            body+=f'<tr><td>{esc(row["record_id"])} / {row["field"]}</td><td><code>{esc(p["raw_ocr"] if p else None)}</code></td><td><code>{esc(row["excel_target"])}</code></td><td>{esc(p["comparison_status"] if p else "not implemented")}</td></tr>'
        (destination/'index.html').write_text(body+'</table>',encoding='utf-8')
    print(json.dumps(counts))

if __name__=='__main__':main()
