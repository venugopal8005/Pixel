"""CTC character evidence plus aligned second readings; scores are not accuracy probabilities."""
from difflib import SequenceMatcher
import math
import numpy as np
from PIL import ImageOps

def decode_scores(preds,alphabet,width,content_fraction=1):
    best=preds.argmax(axis=1);result=[];previous=None
    for t,index in enumerate(best):
        index=int(index)
        if index and index!=previous:
            ranked=np.argsort(preds[t])[::-1]
            options=[alphabet[int(i)] for i in ranked if int(i)!=0][:3]
            score=float(preds[t,index])
            alternatives=[alphabet[int(i)] for i in ranked if int(i)!=0 and float(preds[t,i])>=max(.03,score*.12)][:3]
            result.append(dict(char=alphabet[index],score=score,alternatives=alternatives,
                x=max(0,min(width-1,int(t/len(best)/content_fraction*width))),step=t))
        previous=index
    return result

def align_readings(tokens,other):
    base=''.join(t['char'] for t in tokens)
    output=[]
    for tag,a,b,c,d in SequenceMatcher(None,base,other,autojunk=False).get_opcodes():
        if tag=='equal':
            for token in tokens[a:b]:
                options=list(dict.fromkeys([token['char'],*token['alternatives']]))
                category='unrecognized' if token['score']<.45 or (token['score']<.9 and len(options)<2) else ('ambiguous' if len(options)>1 else 'single')
                output.append(dict(token,text=token['char'],options=options,category=category,reason='Low model score' if category!='single' else 'One reading; not verified'))
        else:
            first=base[a:b];second=other[c:d]
            output.append(dict(text=first,options=list(dict.fromkeys([first,second])),category='ambiguous',
                reason='Readings disagree; may include inserted/deleted characters',x=tokens[a]['x'] if a<len(tokens) else (tokens[-1]['x'] if tokens else 0)))
    return output

def read_line(engine,image):
    array=np.asarray(image.convert('RGB'))[:,:,::-1].copy();rec=engine.text_rec
    _,height,width=rec.rec_image_shape
    ratio=max(width/height,image.width/image.height)
    norm=rec.resize_norm_img(array,ratio)
    scores=rec.session(norm[None].astype(np.float32))[0][0]
    fraction=min(1,math.ceil(height*image.width/image.height)/norm.shape[2])
    tokens=decode_scores(scores,rec.postprocess_op.character,image.width,fraction)
    variant=ImageOps.autocontrast(image.convert('L'),cutoff=1).convert('RGB').resize((image.width*2,image.height*2))
    second,_=engine(np.asarray(variant)[:,:,::-1].copy(),use_det=False,use_cls=False)
    alternative=''.join(r[0] for r in (second or []))
    segments=align_readings(tokens,alternative)
    if not segments:segments=[dict(text='',options=[],category='unrecognized',reason='No characters recognized',x=0)]
    return segments

def render_segments(segments,decisions,marked=True):
    result=''
    for segment in segments:
        if segment['id'] in decisions:result+=decisions[segment['id']]
        elif not marked or segment['category']=='single':result+=segment['text']
        elif segment['category']=='unrecognized':result+='[?]'
        else:result+='['+'/'.join(v if v else '∅' for v in segment['options'])+']'
    return result
