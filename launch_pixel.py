"""Use the desktop's bundled libraries, with project OCR packages as extras."""
import runpy
import sys
from pathlib import Path

root=Path(__file__).resolve().parent
extras=root/'.venv-ocr/Lib/site-packages'
if extras.is_dir():sys.path.append(str(extras))
runpy.run_path(str(root/'review_app.py'),run_name='__main__')
