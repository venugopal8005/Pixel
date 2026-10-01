@echo off
cd /d "%~dp0"
set "PIXEL_PYTHON=C:\Users\Dwight\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PIXEL_PYTHON%" set "PIXEL_PYTHON=%~dp0.venv-ocr\Scripts\python.exe"
"%PIXEL_PYTHON%" launch_pixel.py --port 8767 --open
pause
