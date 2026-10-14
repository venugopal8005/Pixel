"""Focused character-backed field candidates and persisted region selections."""
from character_review import render_segments

def review_record(state,record):
    """Expose active crop OCR for editing without feeding it back to the mapper."""
    added=[line for key,selection in state.get('field_regions',{}).items()
           if key.startswith(record['key']+':') and selection.get('kind')=='rectangles'
           for line in selection.get('lines',[])]
    return dict(record,lines=[*record['lines'],*added])

def entries(record):
    return [(line,seg) for line in record['lines'] for seg in line['segments']]

def evidence(record,selected,decisions,candidate=False):
    from client_rules import physical_break
    refs=[];sources=[];plain=[];marked=[];parts=[]
    previous=None
    for line in record['lines']:
        picked=[s for l,s in selected if l['id']==line['id']]
        if not picked:continue
        if parts:parts.append(dict(id=None,raw=' ',marked=' ',line_break=physical_break(previous,line)))
        previous=line
        parts.extend(dict(id=s['id'],raw=decisions.get(s['id'],s['text']),marked=render_segments([s],decisions)) for s in picked)
        refs.extend(dict(id=s['id'],line=line['id'],editable=True) for s in picked)
        plain.append(render_segments(picked,decisions,marked=False));marked.append(render_segments(picked,decisions))
        indexes=[line['segments'].index(s) for s in picked];first,last=min(indexes),max(indexes)
        width=max(p[0] for p in line['box'])-min(p[0] for p in line['box'])
        left=max(0,line['segments'][first].get('x',0)-4)
        right=line['segments'][last+1].get('x',width)+4 if last+1<len(line['segments']) else width
        sources.append(dict(line=line['id'],image=line.get('image'),page=line['page'],left=left,right=max(left+1,min(width,right))))
    return dict(plain=' '.join(plain),marked=' '.join(marked),segments=refs,sources=sources,candidate=candidate,parts=parts)

def selected_region(record,selection,decisions):
    all_entries=entries(record);ids=[s['id'] for _,s in all_entries]
    first,last=selection['first'],selection['last']
    if first not in ids or last not in ids:raise ValueError('Selected characters no longer exist')
    a,b=ids.index(first),ids.index(last)
    if a>b:raise ValueError('Field start must precede its end')
    return evidence(record,all_entries[a:b+1],decisions)

def candidate_for(record,field,mapped,decisions):
    all_entries=entries(record)
    if not all_entries:return dict(plain='',segments=[],sources=[],candidate=True)
    ids=[s['id'] for _,s in all_entries]
    limits={f:[ids.index(s['id']) for s in item['segments'] if s['id'] in ids] for f,item in mapped.items()}
    limits={f:v for f,v in limits.items() if v and f not in (0,2,13,25,36)}
    before=[f for f in limits if f<field];after=[f for f in limits if f>field]
    previous=max(before) if before else None;following=min(after) if after else None
    a=max(limits[previous])+1 if previous is not None else 0
    b=min(limits[following]) if following is not None else len(all_entries)
    if a>=b:
        # Overlapping automatic spans: show a focused nearby line, not the record.
        pivot=min(a,len(all_entries)-1);line=all_entries[pivot][0]['id']
        chosen=[item for item in all_entries if item[0]['id']==line]
    else:
        available=all_entries[a:b];line_ids=list(dict.fromkeys(l['id'] for l,s in available))
        # Rank missing fields within the gap only to propose a place to inspect.
        # This proposal is NEVER exported as a located field until accepted.
        fraction=(field-(previous or 1))/max(1,(following or 36)-(previous or 1))
        center=min(len(line_ids)-1,max(0,int(fraction*len(line_ids))))
        chosen_lines=line_ids[max(0,center-1):center+1]
        chosen=[item for item in available if item[0]['id'] in chosen_lines]
    return evidence(record,chosen,decisions,candidate=True)
