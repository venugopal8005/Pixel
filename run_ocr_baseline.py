"""Local OCR experiment. No spelling corrections or reference-guided decoding."""
import hashlib
import html
import importlib.metadata
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from rapidocr_onnxruntime import RapidOCR

ROOT = Path(__file__).resolve().parent
REF = ROOT / 'outputs' / 'ocr-reference'
OUT = ROOT / 'outputs' / 'ocr-baseline'
VARIANTS = ('original', 'enlarged_3x', 'contrast_3x')
# Independent, manually located field regions; not inferred using the expected text.
FIELD_BOXES = {
    ('1802603502', 3): (159, (589, 774, 785, 794)),
    ('1802603502', 15): (159, (693, 839, 819, 860)),
    ('1802603508', 24): (160, (269, 1085, 326, 1105)),
    ('1802603512', 19): (160, (539, 824, 576, 845)),
}

def variant_image(image, variant):
    if variant == 'original':
        return image.convert('RGB')
    if variant == 'contrast_3x':
        image = ImageOps.autocontrast(ImageOps.grayscale(image), cutoff=1)
    return image.resize((image.width * 3, image.height * 3), Image.Resampling.LANCZOS).convert('RGB')

def normalize_spaces(text):
    return ''.join(text.split())

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ref = json.loads((REF / 'reference.json').read_text(encoding='utf-8'))
    engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1, text_score=0.0)
    results = []
    tasks = []
    for record in ref['records']:
        for index, region in enumerate(record['regions'], start=1):
            tasks.append(dict(key=f"{record['record_id']}-part-{index}", kind='record',
                              record_id=record['record_id'], image=Image.open(REF / region['crop']),
                              source=region, expected=None))
        for field in record['fields']:
            key = (record['record_id'], field['field'])
            if key not in FIELD_BOXES:
                continue
            page, box = FIELD_BOXES[key]
            path = Path(f'D:/projects/piXeL/manual/FORM TTYFRD_8AQ{page}_enc.jpg')
            tasks.append(dict(key=f'{key[0]}-field-{key[1]}', kind='confirmed_field',
                              record_id=key[0], field=key[1], image=Image.open(path).crop(box),
                              source=dict(image=str(path), box_xyxy=box),
                              expected=field['raw_source_text']))
    for number, task in enumerate(tasks, start=1):
        print(f"{number}/{len(tasks)} {task['key']}", flush=True)
        for variant in VARIANTS:
            image = variant_image(task['image'], variant)
            filename = f"{task['key']}-{variant}.png"
            image.save(OUT / filename)
            start = time.perf_counter()
            # Pass path to avoid RGB/BGR array ambiguities. No external image service.
            result, _ = engine(str(OUT / filename), use_cls=False)
            lines = [dict(box=np.asarray(r[0]).tolist(), text=r[1], score=float(r[2])) for r in (result or [])]
            text = '\n'.join(line['text'] for line in lines)
            results.append(dict(key=task['key'], kind=task['kind'], record_id=task['record_id'],
                                variant=variant, image=filename, source=task['source'],
                                expected=task['expected'], text=text, lines=lines,
                                seconds=round(time.perf_counter()-start, 3),
                                exact_text_match=(text == task['expected']) if task['expected'] is not None else None,
                                whitespace_ignored_match=(normalize_spaces(text) == normalize_spaces(task['expected']))
                                if task['expected'] is not None else None))
        # Retain progress if a subsequent image fails.
        (OUT / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    summaries = {}
    for variant in VARIANTS:
        checks = [r for r in results if r['kind'] == 'confirmed_field' and r['variant'] == variant and r['expected'] is not None]
        summaries[variant] = dict(confirmed_fields=len(checks), exact_matches=sum(r['exact_text_match'] for r in checks),
                                  whitespace_ignored_matches=sum(r['whitespace_ignored_match'] for r in checks))
    metadata = dict(engine='rapidocr-onnxruntime', version=importlib.metadata.version('rapidocr-onnxruntime'),
                    variants={'original':'Unchanged crop', 'enlarged_3x':'3x Lanczos resize',
                              'contrast_3x':'Grayscale, autocontrast cutoff=1%, 3x Lanczos resize'},
                    reference_sha256=hashlib.sha256((REF/'reference.json').read_bytes()).hexdigest(),
                    summary=summaries,
                    limitation='Four selected user-confirmed fields, with known field locations. Development diagnostic, not end-to-end or held-out accuracy.')
    (OUT / 'summary.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    esc = lambda value: html.escape(str(value))
    sections = []
    for task in tasks:
        rows = [r for r in results if r['key'] == task['key']]
        cards = ''.join(f'<article><h3>{esc(r["variant"])}</h3><img src="{r["image"]}"><pre>{esc(r["text"])}</pre>'
                        + (f'<p>Exact match: {r["exact_text_match"]}; ignoring whitespace: {r["whitespace_ignored_match"]}</p>'
                           if r['expected'] is not None else '') + '</article>' for r in rows)
        expectation = f'<p>User-confirmed source: <code>{esc(task["expected"])}</code></p>' if task['expected'] is not None else '<p>Uncorrected OCR. Record text has not been fully verified.</p>'
        sections.append(f'<section><h2>{esc(task["key"])}</h2>{expectation}<div class="cards">{cards}</div></section>')
    # Show the small confirmed test first; preserve record part order below it.
    pairs = list(zip(tasks, sections))
    pairs.sort(key=lambda p: p[0]['kind'] != 'confirmed_field')
    report = '''<!doctype html><meta charset="utf-8"><title>OCR baseline comparison</title>
<style>body{font:16px system-ui;background:#f4f6f8;color:#172b3a;margin:32px}h1{margin-bottom:8px}
section{margin:28px 0;padding:20px;background:white;border-radius:10px}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}
article{min-width:0}img{max-width:100%;border:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.55;background:#f4f6f8;padding:12px}
code{font-size:16px}@media(max-width:900px){.cards{grid-template-columns:1fr}}</style>
<h1>OCR baseline comparison</h1><p>Original, enlarged, and contrast-adjusted crops. No spelling correction or reference-guided repair.</p>
<p>Only four fields are user-confirmed. These results do not measure whole-record accuracy. OCR scores are not calibrated accuracy percentages.</p>'''
    report += '<pre>' + esc(json.dumps(summaries, indent=2)) + '</pre>' + ''.join(section for _, section in pairs)
    (OUT / 'report.html').write_text(report, encoding='utf-8')
    print(json.dumps(metadata, indent=2), flush=True)

if __name__ == '__main__':
    main()
