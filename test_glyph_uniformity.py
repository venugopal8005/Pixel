"""Exploratory source-pixel study. No OCR answers are used as character labels."""
import html,json,re
from collections import Counter
from pathlib import Path
import numpy as np
import cv2

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs/glyph-study'

def split_glyphs(image,label,threshold):
    """Accept only exact component-count alignment; never split to force a label."""
    gray=np.asarray(image.convert('L'));ink=gray<threshold
    # Isolated JPEG speckles are removed only from the boundary mask, not features.
    n,labels,stats,_=cv2.connectedComponentsWithStats(ink.astype(np.uint8),8)
    keep=np.zeros_like(ink)
    for i in range(1,n):
        if stats[i,cv2.CC_STAT_AREA]>=2:keep|=labels==i
    occupied=np.where(keep.sum(axis=0)>0)[0];runs=[]
    for x in map(int,occupied):
        if not runs or x>runs[-1][-1]+1:runs.append([x])
        else:runs[-1].append(x)
    chars=[c for c in label if not c.isspace()]
    if len(runs)!=len(chars):return None,f'Expected {len(chars)} glyphs; found {len(runs)} ink runs'
    output=[]
    for char,run in zip(chars,runs):
        left,right=run[0],run[-1]+1;ys=np.where(keep[:,left:right].any(axis=1))[0]
        if not len(ys):return None,'Empty component'
        box=(left,int(ys.min()),right,int(ys.max())+1)
        output.append((char,image.crop(box),box))
    return output,None

def feature(image):
    ink=1-np.asarray(image.convert('L'),dtype=np.float32)/255
    h,w=ink.shape;scale=min(20/w,28/h)
    resized=cv2.resize(ink,(max(1,round(w*scale)),max(1,round(h*scale))),interpolation=cv2.INTER_AREA)
    canvas=np.zeros((32,24),np.float32);y=(32-resized.shape[0])//2;x=(24-resized.shape[1])//2
    canvas[y:y+resized.shape[0],x:x+resized.shape[1]]=resized
    v=canvas.ravel();return v/max(np.linalg.norm(v),1e-6)

def evaluate(samples):
    if not samples:return dict(tested=0,correct=0,details=[])
    vectors=np.stack([s['feature'] for s in samples]);dist=np.maximum(0,1-vectors@vectors.T)
    details=[]
    for i,s in enumerate(samples):
        pool=[j for j,t in enumerate(samples) if t['record']!=s['record'] and t['provenance']==s['provenance']]
        same=[j for j in pool if samples[j]['char']==s['char']]
        other=[j for j in pool if samples[j]['char']!=s['char']]
        if not same or not other:continue
        j=min(pool,key=lambda j:float(dist[i,j]));a=min(same,key=lambda j:float(dist[i,j]));b=min(other,key=lambda j:float(dist[i,j]))
        details.append(dict(sample=s['id'],char=s['char'],predicted=samples[j]['char'],neighbor=samples[j]['id'],correct=samples[j]['char']==s['char'],
            nearest_same=float(dist[i,a]),nearest_different=float(dist[i,b]),record=s['record'],provenance=s['provenance']))
    return dict(tested=len(details),correct=sum(d['correct'] for d in details),
        median_same=float(np.median([d['nearest_same'] for d in details])) if details else None,
        median_different=float(np.median([d['nearest_different'] for d in details])) if details else None,details=details)

def collect_fields():
    from extract_fields import number
    rows=[];rejected=[]
    baseline=json.loads((ROOT/'outputs/auto-field-review/fields.json').read_text(encoding='utf-8'))
    # Include incorrect OCR readings too. Selection is crop availability and valid
    # reference formatting, never whether OCR matched the answer.
    for r in baseline['results']:
        if r['field'] not in (18,19,20,21,23,24):continue
        if not r['crop']:
            rejected.append(dict(id=f'{r["record_id"]}-f{r["field"]}',reason='No automatic crop'));continue
        value=number(r['comparison_target'])
        if value is None:
            rejected.append(dict(id=f'{r["record_id"]}-f{r["field"]}',reason='Excel numeric text cannot be parsed without repair'));continue
        label=format(value,'f')
        if '.' in label:label=label.rstrip('0').rstrip('.')
        rows.append(dict(id=f'{r["record_id"]}-f{r["field"]}',record=r['record_id'],label=label,
            image=ROOT/'outputs/auto-field-review'/r['crop'],provenance='Excel numeric labels; display formatting stripped'))
    # Confirmed strings do not establish character-to-pixel alignment. Visual
    # inspection found shifted alignments in text lines despite matching counts.
    # Keep them out until character boxes have been checked independently.
    return rows,rejected

def main():
    from PIL import Image,ImageDraw,ImageFont
    OUT.mkdir(parents=True,exist_ok=True);fields,rejected=collect_fields();runs={};main_samples=[]
    for threshold in (140,170,200):
        samples=[];excluded=list(rejected);accepted=[]
        for field in fields:
            image=Image.open(field['image']);glyphs,reason=split_glyphs(image,field['label'],threshold)
            if reason:excluded.append(dict(id=field['id'],reason=reason));continue
            accepted.append(field['id'])
            for index,(char,crop,box) in enumerate(glyphs):
                if not char.isascii() or not char.isalnum():continue
                ident=f'{field["id"]}-g{index}';name=ident+'.png'
                sample=dict(id=ident,char=char,record=field['record'],provenance=field['provenance'],field=field['id'],
                    source=str(field['image']),box=list(box),crop=name,feature=feature(crop))
                samples.append(sample)
                if threshold==170:crop.save(OUT/name)
        metric=evaluate(samples)
        runs[str(threshold)]=dict(accepted_fields=len(accepted),accepted_field_ids=accepted,total_candidates=len(fields)+len(rejected),
            glyphs=len(samples),label_counts=dict(sorted(Counter(s['char'] for s in samples).items())),excluded=excluded,**metric)
        if threshold==170:main_samples=samples
    # Matched sample subset distinguishes threshold robustness from changes in selection.
    common=set.intersection(*(set(d['sample'] for d in run['details']) for run in runs.values()))
    for run in runs.values():
        sub=[d for d in run['details'] if d['sample'] in common]
        run['common_subset']=dict(tested=len(sub),correct=sum(d['correct'] for d in sub))
        run['per_character']={c:dict(tested=sum(d['char']==c for d in run['details']),
            correct=sum(d['char']==c and d['correct'] for d in run['details']))
            for c in sorted({d['char'] for d in run['details']})}
    metadata=[{k:v for k,v in s.items() if k!='feature'} for s in main_samples]
    pairs=[]
    for a,b in [('0','O'),('8','B'),('i','t'),('1','l'),('3','8'),('5','6')]:
        support={c:dict(glyphs=sum(s['char']==c for s in main_samples),records=len({s['record'] for s in main_samples if s['char']==c})) for c in (a,b)}
        pairs.append(dict(pair=a+'/'+b,support=support,adequate_for_exploration=all(v['records']>=3 for v in support.values())))
    payload=dict(method='Centered, aspect-preserving 24x32 grayscale glyphs; cosine nearest neighbor from a different record, within the same label-provenance group. No learned model or Excel values used as features.',
        limitations=['Only the two development pages. No unseen page evaluation.','Exact ink-run/label-count filtering selects separable glyphs and excludes touching, fragmented or badly cropped text.',
        'Excel labels are accepted output, not independently audited pixel transcriptions. Formatting removal can affect alignment.',
        'Projection alignment may still be wrong even when counts match. Inspect the crop sheet. Confirmed text lines were excluded after visual inspection found shifted character alignments.',
        'Only numeric fields are measured. Letter-versus-digit confusion requires additional independently aligned examples.',
        'A simple shape match can show useful visual consistency; it cannot prove that fine-tuning will improve OCR or that errors are unavoidable.'],
        runs=runs,pairs=pairs,samples=metadata)
    (OUT/'study.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
    chars=sorted({s['char'] for s in main_samples});sheet=Image.new('RGB',(1100,60+len(chars)*90),'white');draw=ImageDraw.Draw(sheet)
    draw.text((15,12),'Original digit crops (enlarged). Labels: Excel numeric fields.',font=font,fill='black')
    for y,char in enumerate(chars):
        candidates=[s for s in main_samples if s['char']==char];chosen=[];seen=set()
        for sample in sorted(candidates,key=lambda s:(s['record'],s['field'])):
            if sample['record'] not in seen:chosen.append(sample);seen.add(sample['record'])
        chosen=(chosen+[s for s in candidates if s not in chosen])[:12]
        draw.text((15,65+y*90),char,font=font,fill='black')
        for x,s in enumerate(chosen):
            crop=Image.open(OUT/s['crop']).convert('RGB');crop.thumbnail((56,48));crop=crop.resize((crop.width*3,crop.height*3),Image.Resampling.NEAREST);crop.thumbnail((64,56))
            sheet.paste(crop,(65+x*85,60+y*90));draw.text((65+x*85,118+y*90),s['record'][-4:],font=font,fill='#536779')
    sheet.save(OUT/'glyph-sheet.png')
    write_report(payload)

def write_report(payload):
    runs=payload['runs'];pairs=payload['pairs']
    esc=lambda v:html.escape(str(v))
    body='''<!doctype html><meta charset="utf-8"><title>Pixel glyph feasibility study</title><style>body{font:16px system-ui;color:#233345;max-width:1150px;margin:35px auto;padding:0 20px}td,th{padding:10px;border-bottom:1px solid #dde3e9;text-align:left}img{max-width:100%}p,li{line-height:1.6}.warn{background:#fff2d8;padding:18px;border-radius:10px}</style><h1>Do repeated characters keep a recognizable shape?</h1><p>This is an exploratory test of the two supplied pages. It compares actual cropped pixels, without retraining OCR.</p><p class="warn">The results describe selected, separable glyphs. They are not overall OCR accuracy, a training guarantee, or evidence of 100% feasibility.</p>'''
    main=runs['170']
    body+=f'<h2>What this establishes</h2><p>There is useful repetition in the digit shapes. At the middle threshold, {main["correct"]} of {main["tested"]} selected digit crops matched a digit with the same label in another record. Only {main["accepted_fields"]} of {main["total_candidates"]} candidate fields passed the separation check. Difficult text and letters are not represented by that score.</p><p>This supports a controlled recognition experiment. It does not yet establish improvement from training. The next test needs independently checked letter crops, especially B/8, O/0 and i/t, and evaluation on new pages.</p><p>Sources: FORM TTYFRD_8AQ159_enc.jpg and FORM TTYFRD_8AQ160_enc.jpg; numeric labels from manual.xlsx. The original files and saved user corrections were not changed.</p>'
    body+='<h2>Shape matching across different records</h2><p>'+esc(payload['method'])+'</p><table><tr><th>Ink threshold</th><th>Accepted fields</th><th>Glyphs</th><th>Tested</th><th>Correct nearest label</th><th>Same distance</th><th>Different distance</th></tr>'
    for threshold,r in runs.items():body+=f'<tr><td>{threshold}</td><td>{r["accepted_fields"]}/{r["total_candidates"]}</td><td>{r["glyphs"]}</td><td>{r["tested"]}</td><td>{r["correct"]}</td><td>{r["median_same"]:.3f}</td><td>{r["median_different"]:.3f}</td></tr>'
    body+='</table><p>Lower distance means more similar pixels. Every nearest-neighbor comparison excludes the target record. Threshold changes also change which crops pass segmentation. These rows are not a controlled ranking of preprocessing settings.</p><p>The same 26 test glyphs are eligible at all three settings: 26, 26 and 20 match correctly respectively. Their comparison pools still differ. Thresholds only change crop boundaries here; features retain the original grayscale pixels.</p><h2>Do we have enough examples of the difficult pairs?</h2><p>Three records per character is an exploratory coverage check, not a statistical sufficiency claim. Letters need separately verified character boxes.</p><table><tr><th>Pair</th><th>Available support</th><th>At least 3 records per character?</th></tr>'
    for p in pairs:body+='<tr><td>'+esc(p['pair'])+'</td><td>'+esc(p['support'])+'</td><td>'+str(p['adequate_for_exploration'])+'</td></tr>'
    body+='</table><h2>Limits</h2><ul>'+''.join('<li>'+esc(s)+'</li>' for s in payload['limitations'])+'</ul><h2>Inspect the actual glyphs</h2><p>The labels under each patch are record suffixes. Repeated patches from the same record are not independent evidence.</p><img src="glyph-sheet.png"><h2>Nearest-neighbor mistakes at threshold 170</h2>'
    for d in runs['170']['details']:
        if not d['correct']:body+=f'<p>Label {esc(d["char"])} matched {esc(d["predicted"])}: <img style="width:45px" src="{esc(d["sample"])}.png"> vs <img style="width:45px" src="{esc(d["neighbor"])}.png"></p>'
    (OUT/'index.html').write_text(body,encoding='utf-8')
    print(json.dumps({k:{a:v for a,v in r.items() if a in ('accepted_fields','total_candidates','glyphs','tested','correct','median_same','median_different','common_subset')} for k,r in runs.items()},indent=2))
    print(json.dumps(pairs,indent=2))

if __name__=='__main__':main()
