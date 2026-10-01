"""Collect image-linked corrections, without treating unreviewed OCR as training truth."""
import hashlib,json
from character_review import render_segments

def build_examples(state,directory):
    examples=[];decisions=state['decisions']
    for record in state['records']:
        for line in record['lines']:
            corrected=[dict(id=s['id'],original=s['text'],confirmed=decisions[s['id']],approximate_x=s.get('x'))
                       for s in line['segments'] if s['id'] in decisions]
            text=render_segments(line['segments'],decisions,marked=False)
            verified=state.get('verified_lines',{}).get(line['id'])
            complete=bool(line['segments']) and all(s['id'] in decisions for s in line['segments'])
            verified_current=verified is not None and verified['text']==text
            if not corrected and not verified_current:continue
            image=directory/line['image']
            examples.append(dict(id=state['id']+':'+line['id'],record=record['key'],image=str(image.resolve()),
                image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),source_page=line['page'],source_box=line.get('source_box'),
                original_ocr=''.join(s['text'] for s in line['segments']),proposed_text=text,
                training_text=text if complete or verified_current else None,
                status='ready_for_dataset_validation' if complete or verified_current else 'partial_corrections_only',
                confirmed_segments=corrected,
                note='Line crop is exact; individual character positions are approximate. No automatic model update.'))
    return dict(schema_version=1,job=state['id'],model_updated=False,
        examples=examples,summary=dict(saved_lines=len(examples),validated_line_candidates=sum(e['training_text'] is not None for e in examples),
        confirmed_segments=sum(len(e['confirmed_segments']) for e in examples)))

def write_examples(state,directory):
    result=build_examples(state,directory)
    target=directory/'learning.json';tmp=target.with_suffix('.tmp')
    tmp.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(target)
    return result['summary']
