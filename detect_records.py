"""Detect ruled two-column record blocks from images without consulting Excel."""
import argparse
import json
import re
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parent

def groups(indices):
    groups=[]
    for n in map(int,indices):
        if not groups or n>groups[-1][-1]+1:groups.append([n])
        else:groups[-1].append(n)
    return groups

def blocks(image):
    gray=np.asarray(image.convert('L'));height,width=gray.shape
    ink=(gray<160).astype(np.uint8)*255
    vertical=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((max(50,height//8),1),np.uint8))
    horizontal=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(80,width//5)),np.uint8))
    edges=[int(round(np.mean(g))) for g in groups(np.where((vertical>0).sum(axis=0)>height*.12)[0])]
    columns=[(a,b) for a,b in zip(edges,edges[1:]) if width*.3<b-a<width*.6]
    if len(columns)==1:
        left,right=columns[0];outside=ink.copy();outside[:,max(0,left-5):min(width,right+6)]=0
        if (outside>0).sum()>max(40,(ink>0).sum()*.01):
            raise ValueError('One ruled column found but text exists outside it; inspect page layout.')
    elif len(columns)!=2:raise ValueError(f'Expected one or two ruled columns; found {len(columns)}. No fallback to invented layout.')
    result=[]
    for col,(left,right) in enumerate(columns):
        border=np.where(np.any(vertical[:,max(0,left-2):left+3]>0,axis=1))[0]
        if len(border)==0:raise ValueError('Missing vertical bounds')
        top,bottom=int(border.min()),int(border.max())+1
        content=np.where((ink[:,left+4:right-4]>0).sum(axis=1)>5)[0]
        if len(content):bottom=max(bottom,int(content.max())+2)
        line_groups=groups(np.where((horizontal[:,left+3:right-3]>0).sum(axis=1)>(right-left)*.45)[0])
        boundaries=[int(round(np.mean(g))) for g in line_groups if top<=np.mean(g)<=bottom]
        if not boundaries or boundaries[0]>top+5:boundaries.insert(0,top)
        bottom_ruled=bool(boundaries and bottom-boundaries[-1]<6)
        if not bottom_ruled:boundaries.append(bottom)
        for index,(y0,y1) in enumerate(zip(boundaries,boundaries[1:])):
            if y1-y0<35:
                # A short continuation can still contain real text. Discard only
                # rule/noise bands; retain text-bearing short regions for review.
                interior=(ink[y0+3:y1-2,left+4:right-4]>0) & (horizontal[y0+3:y1-2,left+4:right-4]==0) & (vertical[y0+3:y1-2,left+4:right-4]==0)
                if interior.sum()<10:continue
            open_bottom=index==len(boundaries)-2 and not bottom_ruled
            # Only inset a ruled bottom. At an open edge y1 comes from the last
            # occupied row (+2), so subtracting 2 clips source text pixels.
            crop_bottom=min(height,y1) if open_bottom else y1-2
            result.append(dict(column=col,block=index,box=[left+3,y0+3,right-2,crop_bottom],
                               first_in_column=index==0,open_bottom=open_bottom,short_fragment=y1-y0<35))
    return result

def header_crop(crop):
    area=crop.crop((0,0,min(crop.width,100),min(crop.height,45)))
    occupied=np.where((np.asarray(area.convert('L'))<160).sum(axis=1)>=4)[0]
    bands=[]
    for y in map(int,occupied):
        if not bands or y>bands[-1][-1]+3:bands.append([y])
        else:bands[-1].append(y)
    bands=[b for b in bands if b[-1]-b[0]>=5]
    if not bands:return area.crop((0,0,area.width,min(22,area.height)))
    band=bands[0]
    return area.crop((0,max(0,band[0]-2),area.width,min(area.height,band[-1]+3)))

def main():
    from rapidocr_onnxruntime import RapidOCR
    parser=argparse.ArgumentParser();parser.add_argument('images',nargs='*');parser.add_argument('--out',default=str(ROOT/'outputs/page-detection'));args=parser.parse_args()
    paths=[Path(p) for p in args.images] or [Path(f'D:/projects/piXeL/manual/FORM TTYFRD_8AQ{p}_enc.jpg') for p in (159,160)]
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,text_score=0)
    records=[];fragments=[];previous=None;seen=set()
    for page_index,path in enumerate(paths):
        image=Image.open(path).convert('RGB');overlay=image.copy();draw=ImageDraw.Draw(overlay)
        for block_index,block in enumerate(blocks(image)):
            left,top,right,bottom=block['box'];crop=image.crop((left,top,right,bottom))
            filename=f'page-{page_index+1}-block-{block_index+1}.png';crop.save(out/filename)
            header=header_crop(crop)
            header_name=f'page-{page_index+1}-block-{block_index+1}-header.png';header.save(out/header_name)
            result,_=engine(str(out/header_name),use_det=False,use_cls=False)
            raw=' '.join(r[0] for r in (result or []));match=re.match(r'^\s*(\d{10})(?!\d)',raw)
            alternatives=[raw]
            if match is None:
                enlarged=header.resize((header.width*3,header.height*3),Image.Resampling.LANCZOS)
                alt,_=engine(np.asarray(enlarged)[:,:,::-1].copy(),use_det=False,use_cls=False)
                alt_text=' '.join(r[0] for r in (alt or []));alternatives.append(alt_text)
                match=re.match(r'^\s*(\d{10})(?!\d)',alt_text)
            if match is None:
                fixed=crop.crop((0,0,min(crop.width,100),min(crop.height,17)))
                alt,_=engine(np.asarray(fixed)[:,:,::-1].copy(),use_det=False,use_cls=False)
                alt_text=' '.join(r[0] for r in (alt or []));alternatives.append(alt_text)
                match=re.match(r'^\s*(\d{10})(?!\d)',alt_text)
            fragment=dict(source_image=str(path),crop=filename,header_ocr=raw,header_readings=alternatives,**block)
            if match:
                rid=match.group(1);fragment['record_id']=rid
                if rid in seen:
                    fragment['status']='duplicate_id_needs_resolution';previous=None
                else:
                    seen.add(rid);record=dict(record_id=rid,parts=[fragment],status='detected');records.append(record);previous=record
                    fragment['status']='record_start'
            elif block['first_in_column'] and previous and previous['parts'][-1]['open_bottom'] and not re.match(r'^\s*[0-9A-Z]{10}(?![0-9A-Z])',raw):
                # Layout-based join only. Retain evidence and mark it as inferred.
                fragment.update(record_id=previous['record_id'],status='continuation_inferred_from_layout')
                previous['parts'].append(fragment)
            else:
                fragment['status']='unassigned_fragment';previous=None
            fragments.append(fragment)
            draw.rectangle(tuple(block['box']),outline='#d00000',width=2)
            draw.text((left+2,top+22),fragment.get('record_id','UNASSIGNED'),fill='#d00000')
        overlay.save(out/f'page-{page_index+1}-detected.png')
    payload=dict(method='Ruled-column geometry and isolated header OCR; no workbook used',
                 limitations='Two-column ruled template only. IDs and continuation joins are predictions, not verified source facts.',
                 records=records,fragments=fragments)
    (out/'records.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(dict(blocks=len(fragments),record_ids=[r['record_id'] for r in records],
                         continuations=[f.get('record_id') for f in fragments if f['status']=='continuation_inferred_from_layout'],
                         unassigned=sum(f['status']=='unassigned_fragment' for f in fragments)),indent=2))

if __name__=='__main__':main()
