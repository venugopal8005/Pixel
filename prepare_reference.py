"""Read-only workbook import for OCR evaluation. Does not certify manual labels."""
import json
from pathlib import Path
import openpyxl
from PIL import Image

ROOT = Path(__file__).resolve().parent
SOURCE = Path('D:/projects/piXeL/manual.xlsx')
IMAGE_DIR = Path('D:/projects/piXeL/manual')
OUT = ROOT / 'outputs' / 'ocr-reference'
REVIEWS = ROOT / 'outputs' / 'human-review' / 'pending-review.json'

# Record regions are approximate native-pixel boxes, not field bounding boxes.
# Multiple regions retain page/column continuations in reading order.
REGIONS = {
    '1802603502': [(159, [486, 772, 944, 984])],
    '1802603503': [(159, [486, 987, 944, 1120]), (160, [14, 34, 475, 124])],
    '1802603504': [(160, [14, 124, 475, 330])],
    '1802603505': [(160, [14, 330, 475, 537])],
    '1802603506': [(160, [14, 537, 475, 742])],
    '1802603507': [(160, [14, 742, 475, 966])],
    '1802603508': [(160, [14, 966, 475, 1110]), (160, [486, 34, 944, 136])],
    '1802603509': [(160, [486, 136, 944, 325])],
    '1802603510': [(160, [486, 325, 944, 534])],
    '1802603511': [(160, [486, 534, 944, 739])],
    '1802603512': [(160, [486, 739, 944, 944])],
}

def main():
    policy_path=ROOT/'reference-policy.json'
    policy=json.loads(policy_path.read_text(encoding='utf-8')) if policy_path.exists() else {}
    excel_authoritative=policy.get('authority')=='manual_excel'
    reviews = json.loads(REVIEWS.read_text(encoding='utf-8'))
    confirmed = {(r['record_id'], r['field']): r for r in reviews
                 if r['status'] == 'user_confirmed'}
    sheet = openpyxl.load_workbook(SOURCE, data_only=True).worksheets[0]
    images = {p: Image.open(IMAGE_DIR / f'FORM TTYFRD_8AQ{p}_enc.jpg')
              for p in (159, 160)}
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    for row in sheet.iter_rows(min_row=2):
        rid = str(row[0].value)
        regions = []
        for part, (page, box) in enumerate(REGIONS[rid], start=1):
            crop = f'{rid}-part-{part}.png'
            images[page].crop(tuple(box)).save(OUT / crop)
            regions.append(dict(image=str(IMAGE_DIR / f'FORM TTYFRD_8AQ{page}_enc.jpg'),
                                box_xyxy=box, crop=crop))
        fields = []
        for field in range(1, 37):
            cell = row[field]
            review = confirmed.get((rid, field))
            fields.append(dict(
                field=field, excel_cell=cell.coordinate, manual_value=cell.value,
                raw_source_text=None if excel_authoritative else (review['confirmed_source_reading'] if review else None),
                accepted_output=cell.value if excel_authoritative else (review['confirmed_output'] if review else None),
                status='excel_authoritative' if excel_authoritative else ('user_confirmed' if review else 'unverified'),
                confirmation_basis='User selected supplied Excel as authoritative output' if excel_authoritative else (review.get('confirmation_basis', 'User visual confirmation') if review else None),
                note='Excel output label; not independently verified literal source text.' if excel_authoritative else (review['review_note'] if review else None),
            ))
        records.append(dict(record_id=rid, regions=regions, fields=fields))
    confirmed_count = sum(f['status'] == 'user_confirmed' for r in records for f in r['fields'])
    result = dict(source_workbook=str(SOURCE), sheet=sheet.title,
                  purpose='Development reference; not independent test data',
                  policy='Null raw_source_text means unverified, not an empty source field.',
                  output_policy=policy,
                  records=records)
    (OUT / 'reference.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    expected_confirmed = 0 if excel_authoritative else sum((r['record_id'], f) in confirmed for r in records for f in range(1, 37))
    assert len(records) == 11 and confirmed_count == expected_confirmed
    assert all(len(r['fields']) == 36 for r in records)
    total = sum(len(r['fields']) for r in records)
    authoritative=sum(f['status']=='excel_authoritative' for r in records for f in r['fields'])
    print(f'{len(records)} records, {total} field slots, {authoritative} Excel-authoritative, {confirmed_count} visually confirmed; original files unchanged.')

if __name__ == '__main__':
    main()
