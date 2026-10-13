"""Ordered, resumable uploads: keep only one decoded page in memory."""
import base64
import hashlib
import io
import shutil
import uuid
from datetime import datetime

from PIL import Image

MAX_IMAGES = 400
MAX_IMAGE_BYTES = 25_000_000
MAX_IMAGE_PIXELS = 20_000_000


class BatchUpload:
    def __init__(self, load, save, folder, lock, enqueue):
        self.load, self.save, self.folder = load, save, folder
        self.lock, self.enqueue = lock, enqueue

    def create(self, data):
        name = str(data.get('name', '')).strip()
        if not 1 <= len(name) <= 100:
            raise ValueError('Project name must be 1–100 characters')
        files = data.get('files')
        if not isinstance(files, list) or not 1 <= len(files) <= MAX_IMAGES:
            raise ValueError(f'Select 1–{MAX_IMAGES} images')
        manifest, names = [], set()
        for item in files:
            filename, size = item.get('name'), item.get('size')
            if not isinstance(filename, str) or not 1 <= len(filename) <= 200:
                raise ValueError('Image filenames must be 1–200 characters')
            if filename in names:
                raise ValueError('Duplicate filename: ' + filename)
            if type(size) is not int or not 0 < size <= MAX_IMAGE_BYTES:
                raise ValueError('Each image must be at most 25 MB: ' + filename)
            names.add(filename)
            manifest.append(dict(name=filename, size=size))
        job = uuid.uuid4().hex
        self.folder(job).mkdir()
        now = datetime.now().astimezone()
        state = dict(id=job, project_name=name, schema_version=2,
                     created_at=now.isoformat(), created_date=now.strftime('%m/%d/%Y'),
                     status='uploading', progress=f'Uploaded 0/{len(files)} images',
                     upload_manifest=manifest, pages=[], records=[], decisions={}, history=[], page_issues=[])
        self.save(state)
        return dict(id=job, uploaded=0, total=len(files))

    def page(self, data):
        job, index = data.get('job'), data.get('index')
        with self.lock:
            state = self.load(job)
            if state['status'] != 'uploading':
                raise ValueError('This project is no longer accepting images')
            manifest = state['upload_manifest']
            if type(index) is not int or not 0 <= index < len(manifest):
                raise ValueError('Invalid image position')
            if index > len(state['pages']):
                raise ValueError('Upload images in their selected order')
            raw = base64.b64decode(data['data'], validate=True)
            if len(raw) != manifest[index]['size'] or len(raw) > MAX_IMAGE_BYTES:
                raise ValueError('Image size differs from the selected file')
            file_hash = hashlib.sha256(raw).hexdigest()
            # A lost HTTP response can safely repeat the same upload.
            if index < len(state['pages']):
                if state['pages'][index]['upload_sha256'] != file_hash:
                    raise ValueError('This position already contains a different image')
                return dict(id=job, uploaded=len(state['pages']), total=len(manifest))
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('JPEG', 'PNG'):
                    raise ValueError('Select JPEG or PNG images')
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ValueError('Image exceeds 20 million pixels')
                if shutil.disk_usage(self.folder(job)).free < source.width * source.height * 3 + 100_000_000:
                    raise ValueError('Not enough free disk space to save this image')
                with source.convert('RGB') as image:
                    digest = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
                    if any(p['sha256'] == digest for p in state['pages']):
                        raise ValueError('Duplicate image: ' + manifest[index]['name'])
                    filename = f'page-{index}.png'
                    temporary = self.folder(job) / f'upload-{uuid.uuid4().hex}.tmp'
                    try:
                        image.save(temporary, format='PNG')
                        temporary.replace(self.folder(job) / filename)
                    finally:
                        temporary.unlink(missing_ok=True)
            state['pages'].append(dict(name=manifest[index]['name'], file=filename,
                                       sha256=digest, upload_sha256=file_hash))
            state['progress'] = f'Uploaded {len(state["pages"])}/{len(manifest)} images'
            self.save(state)
            return dict(id=job, uploaded=len(state['pages']), total=len(manifest))

    def finish(self, job):
        with self.lock:
            state = self.load(job)
            # Retrying the final request must never start two scanners.
            if state['status'] in ('scanning', 'ready', 'error', 'cancelled') and state.get('upload_complete'):
                return dict(id=job)
            if state['status'] != 'uploading':
                raise ValueError('This project is not awaiting an upload')
            if len(state['pages']) != len(state['upload_manifest']):
                raise ValueError('All selected images must arrive before scanning starts')
            state.update(status='scanning', progress='Waiting for the local scanner', upload_complete=True)
            self.save(state)
            self.enqueue(state)
            return dict(id=job)
