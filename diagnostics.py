"""Local, bounded test reports. Never sends telemetry or records request bodies."""
import hashlib
import io
import json
import platform
import re
import subprocess
import sys
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

_LOCK = threading.RLock()
_PRIVATE_KEYS = {'token', 'password', 'authorization', 'cookie', 'pixeltoken', 'pixel_token', 'x-review-token'}


def now():
    return datetime.now(timezone.utc).isoformat()


def clean(value, token='', depth=0):
    if depth > 8:
        return '[depth limit]'
    if isinstance(value, dict):
        return {str(k)[:100]: clean(v, token, depth+1) for k, v in list(value.items())[:100]
                if str(k).lower() not in _PRIVATE_KEYS}
    if isinstance(value, list):
        return [clean(v, token, depth+1) for v in value[-200:]]
    if isinstance(value, str):
        return (value.replace(token, '[session token removed]') if token else value)[:6000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:200]


def build_info(root):
    files = {}
    for pattern in ('*.py', '*.js', '*.html', '*.mjs', 'field_rules.json', 'requirements*.txt'):
        for path in sorted(root.glob(pattern)):
            files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    git = {}
    try:
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            git['commit'] = result.stdout.strip()
            result = subprocess.run(['git', 'status', '--porcelain'], cwd=root, capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                git['has_local_changes'] = bool(result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass  # ZIP installs do not need Git.
    packages = {}
    for name in ('rapidocr-onnxruntime', 'onnxruntime', 'numpy', 'opencv-python', 'Pillow', 'openpyxl'):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = 'not found'
    return dict(source_fingerprint=digest[:16], source_files=files, git=git,
                python=sys.version, platform=platform.platform(), packages=packages, started_at=now())


def log_event(directory, kind, token='', **details):
    """Best effort only: diagnostics must not prevent scanning or saving."""
    try:
        event=clean(dict(time=now(), kind=kind, **details), token)
        with _LOCK:
            directory.mkdir(parents=True, exist_ok=True)
            path=directory/'events.jsonl'
            if path.exists() and path.stat().st_size > 2_000_000:
                path.replace(directory/'events.previous.jsonl')
            with path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(event, ensure_ascii=False)+'\n')
    except OSError:
        pass


def recent_events(directory, job):
    events=[]
    with _LOCK:
        for name in ('events.previous.jsonl', 'events.jsonl'):
            try:
                for line in (directory/name).read_text(encoding='utf-8').splitlines():
                    try:
                        event=json.loads(line)
                        if event.get('job') in (None, '', job):events.append(event)
                    except (ValueError, AttributeError):
                        pass
            except OSError:
                pass
    return events[-150:]


def report_bundle(root, data_root, request, state, progress, build, node_path, token='', state_error=None):
    report_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    job=request.get('job') or None
    if job and not re.fullmatch('[a-f0-9]{32}', job):raise ValueError('Invalid project ID')
    include=request.get('include_project') is True
    outcome=request.get('outcome', 'question')
    if outcome not in ('pass','fail','question'):raise ValueError('Choose pass, fail, or unsure')
    project=None
    if state:
        records=state.get('records', [])
        project=dict(id=job, name=state.get('project_name'), status=state.get('status'),
                     pages=state.get('pages', []), record_candidates=len(records),
                     fragments=sum(len(r.get('fragments', [])) for r in records),
                     saved_character_changes=len(state.get('decisions', {})),
                     saved_field_changes=len(state.get('field_decisions', {})),
                     saved_boundary_changes=len(state.get('field_regions', {})),
                     history_entries=len(state.get('history', [])), error=state.get('error'),
                     page_issues=state.get('page_issues', []))
    report=clean(dict(report_id=report_id, captured_at=now(), outcome=outcome,
                     test=request.get('test', ''), expected=request.get('expected', ''), actual=request.get('actual', ''),
                     build=build, export_runtime_present=node_path.exists(),
                     browser=request.get('browser', {}), context=request.get('context', {}),
                     client_events=request.get('events', []), project=project, live_progress=progress,
                     state_read_error=state_error, include_project=include,
                     server_events=recent_events(data_root/'_diagnostics', job)), token)
    included=[];omitted=[];stream=io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        if include and state:
            # Explicit opt-in preserves the FULL snapshot, including correction history.
            snapshot=json.dumps(state, ensure_ascii=False, indent=2)
            if token:snapshot=snapshot.replace(token, '[session token removed]')
            archive.writestr('project/state.json', snapshot)
            included.append('project/state.json')
            directory=(data_root/job).resolve();names={p.get('file', '') for p in state.get('pages', [])}
            for record in state.get('records', []):
                names.update(line.get('image', '') for line in record.get('lines', []))
            for selection in state.get('field_regions',{}).values():
                if selection.get('kind')=='rectangles':
                    names.update(l['image'] for l in selection.get('lines',[]))
                    names.update(r['crop_image'] for r in selection.get('regions',[]))
            names.add('converted.xlsx');size=0
            for name in sorted(names):
                if not re.fullmatch(r'(?:(?:page-\d+|line-\d+|crop-[a-f0-9]{32}-\d+|selection-[a-f0-9]{32}-\d+)\.png|converted\.xlsx)',name):
                    if name:omitted.append(dict(file=name, reason='Not a supported project asset'))
                    continue
                path=directory/name
                if not path.exists():
                    if name!='converted.xlsx':omitted.append(dict(file=name, reason='File missing'))
                    continue
                if path.resolve().parent!=directory:
                    omitted.append(dict(file=name, reason='Asset is outside the project'));continue
                length=path.stat().st_size
                if size+length>200_000_000:
                    omitted.append(dict(file=name, reason='200 MB project-asset limit'));continue
                archive.write(path, 'project/'+name);size+=length;included.append('project/'+name)
        elif include:
            omitted.append(dict(file='project',reason=state_error or 'No saved project selected'))
        report['included_files']=included;report['omitted_files']=omitted
        archive.writestr('report.json', json.dumps(report, ensure_ascii=False, indent=2))
        archive.writestr('READ-ME.txt',
            'Pixel test report '+report_id+'\n\n'
            'Share this ZIP with your description and a screenshot when appearance matters.\n'
            'report.json contains the test outcome, browser actions/errors, selected cell, runtime, and source fingerprint.\n'
            'A completed HTTP request does not prove that the UI, OCR, or downloaded workbook is correct.\n'
            'Client events are limited to the current browser tab session. Server events are bounded. This is not a screen recording.\n'
            'No source images or full OCR/corrections are included unless project inclusion was selected.\n'
            'Technical details include filenames and error messages; your written notes may contain data.\n'
            'When project data is included, it can contain sensitive information. Share deliberately.\n'
            'Unsaved field text is NOT captured. Save it or describe it in the actual-result box if needed.\n'
            'Missing/oversized assets are listed in report.json. A workbook, when included, may be an earlier export.\n'
            'Nothing is automatically sent anywhere. Reports are saved locally under outputs/review-app/_diagnostics/reports/.\n')
    payload=stream.getvalue();destination=data_root/'_diagnostics'/'reports'
    destination.mkdir(parents=True, exist_ok=True)
    filename='Pixel-test-'+report_id+'.zip'
    (destination/filename).write_bytes(payload)
    return filename,payload
