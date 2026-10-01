"""Reproduce the automatic development benchmark on the supplied labelled pages."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-page-ocr',action='store_true',help='Explicitly reuse existing detection and page OCR; use only when source images have not changed.')
    args=parser.parse_args()
    steps=[]
    if args.reuse_page_ocr:
        for name in ('page-detection/records.json','auto-records/results.json','ocr-reference/reference.json'):
            if not (ROOT/'outputs'/name).is_file():
                parser.error(f'Missing cached input: {name}. Run without --reuse-page-ocr.')
    else:
        steps.extend([['prepare_reference.py'],['detect_records.py'],['ocr_detected_records.py']])
    steps.extend([['extract_fields.py','--automatic'],['extract_reference_codes.py','--automatic'],
                  ['extract_dates_postal.py'],['extract_text_fields.py'],['build_coverage.py','--automatic']])
    for step in steps:
        print('Running '+step[0],flush=True)
        subprocess.run([sys.executable,*step],cwd=ROOT,check=True)
    print('Report: '+str(ROOT/'outputs/automatic-report/index.html'))

if __name__=='__main__':
    main()
