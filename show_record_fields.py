"""Read-only, source-pixel record crop with inspectable field overlays."""
import html
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from review_app import load,folder,field_analysis,ROOT

state=load('44285fad34074a818204f8e791978c44')
record=next(r for r in state['records'] if r['record_id']=='1802603500')
values,missing,evidence=field_analysis(record,state['decisions'])
out=ROOT/'outputs/record-fields';out.mkdir(parents=True,exist_ok=True)
page=next(p for p in state['pages'] if p['name']==record['lines'][0]['page'])
image=Image.open(folder(state['id'])/page['file']).convert('RGB')
boxes=[l['source_box'] for l in record['lines']]
frame=(max(0,min(b[0] for b in boxes)-6),max(0,min(b[1] for b in boxes)-6),min(image.width,max(b[2] for b in boxes)+6),min(image.height,max(b[3] for b in boxes)+6))
crop=image.crop(frame);crop.save(out/'record-1802603500.png')
names={1:'Printed ID',3:'Lid reference',4:'Name 1 prefix',5:'Name 1 remainder',6:'Address',7:'Locality',8:'Postal code',9:'Date',10:'Name 2 prefix',11:'Name 2 remainder',12:'Time of day',14:'Property type',15:'Identifier',16:'Purpose',17:'Product',18:'Amount',19:'Term',20:'Rate',21:'Payment amount',22:'Secured Loan label',23:'Secured amount',24:'Following amount',26:'Organization 1',27:'Name 3 prefix',28:'Name 3 remainder',29:'U.T.R. reference',30:'N.I. reference',31:'Occupation',32:'Response',33:'Organization 2',34:'Bank / card',35:'Final status'}
palette=['#1760ca','#ae3088','#187453','#c26b00','#663aca']
regions=[]
for field,item in sorted(evidence.items()):
    if field==0:continue
    for src in item['sources']:
        line=next(l for l in record['lines'] if l['id']==src['line']);b=line['source_box']
        left=min(max(0,src['left']),b[2]-b[0]-1);right=min(src['right'],b[2]-b[0])
        regions.append(dict(field=field,x=b[0]+left-frame[0],y=b[1]-frame[1],w=max(1,right-left),h=b[3]-b[1],color=palette[field%len(palette)]))
scale=3
annot=crop.resize((crop.width*scale,crop.height*scale),Image.Resampling.NEAREST)
draw=ImageDraw.Draw(annot);font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',13)
for r in regions:
    x,y,w,h=[r[k]*scale for k in ('x','y','w','h')]
    draw.rectangle((x,y,x+w,y+h),outline=r['color'],width=2)
    label=str(r['field']);tw=draw.textlength(label,font=font)+6
    draw.rectangle((x,y,x+tw,y+15),fill=r['color']);draw.text((x+3,y),label,font=font,fill='white')
annot.save(out/'record-1802603500-highlighted.png')
esc=lambda value:html.escape(str(value))
svg=''.join(f'<g class="field" data-field="{r["field"]}" tabindex="0" role="button" aria-label="Field {r["field"]}: {esc(names[r["field"]])}"><title>Field {r["field"]}: {esc(names[r["field"]])}</title><rect x="{r["x"]}" y="{r["y"]}" width="{r["w"]}" height="{r["h"]}" stroke="{r["color"]}"/><text x="{r["x"]+1}" y="{r["y"]+5}" fill="{r["color"]}">{r["field"]}</text></g>' for r in regions)
buttons=''.join(f'<button data-field="{f}" {"disabled" if f in missing else ""}>{f} · {esc(name)}{" — not located" if f in missing else ""}</button>' for f,name in names.items())
payload={str(f):dict(name=names[f],text=evidence[f]['plain']) for f in evidence if f in names}
doc='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pixel · Record 1802603500 fields</title><style>
body{font:15px system-ui;background:#f3f6fa;color:#23374c;margin:0;padding:24px}main{max-width:1150px;margin:auto}h1{font-size:24px}p{line-height:1.5}.muted{color:#617187;font-size:13px}.card{padding:18px;background:white;border:1px solid #dce3ec;border-radius:12px;margin:16px 0}.frame{position:relative;width:100%;overflow:hidden}.frame img{display:block;width:100%}.frame svg{position:absolute;inset:0;width:100%;height:100%}.field{cursor:pointer}.field rect{fill:transparent;stroke-width:.8}.field text{font:bold 5px system-ui;paint-order:stroke;stroke:white;stroke-width:.7px}.field.selected rect{fill:#ffbf393b;stroke:#e06416;stroke-width:1.3}.field.dim{opacity:.12}.field:hover rect{fill:#ffc94335}.plain svg{display:none}.buttons{display:flex;flex-wrap:wrap;gap:7px}button,a{font:inherit;color:#2458bb}button{background:white;border:1px solid #bacbdd;border-radius:7px;padding:8px 11px;cursor:pointer}button.active{background:#2458bb;color:white}button:disabled{color:#8b5760;background:#fff3f1;cursor:default}.bar{display:flex;justify-content:space-between;gap:15px;align-items:center;flex-wrap:wrap}#reading{min-height:48px;overflow-wrap:anywhere}</style>
<main><div class="bar"><h1>Record 1802603500 · Field map</h1><a href="http://127.0.0.1:8767/?job=44285fad34074a818204f8e791978c44">Open Pixel spreadsheet</a></div><p>Click a numbered outline or a field below to isolate it. These are the current OCR mappings, not verified boundaries.</p><div class="bar"><button id="all">Show all fields</button><label><input id="plain" type="checkbox"> Show original without highlights</label><a href="record-1802603500-highlighted.png" download>Download highlighted crop</a></div><section class="card"><div class="frame"><img src="record-1802603500.png" alt="Single original record 1802603500"><svg viewBox="0 0 WIDTH HEIGHT" aria-label="Detected field boundaries">SVG</svg></div></section><section class="card" id="reading" aria-live="polite">Select a field to see its number, name and underlying reading.</section><div class="buttons">BUTTONS</div><p class="muted">Red disabled buttons have no reliable mapped field. Columns 2, 13, 25 and 36 are unmapped placeholders and have no outline. ID and field 1 share the same printed identifier.</p><p class="muted">Source: SOURCE. This read-only view does not change your text or corrections. Positions are approximate; overlapping boxes can reveal a field-mapping error.</p></main><script>
const data=DATA;
function select(field){document.querySelectorAll('[data-field]').forEach(el=>{const match=el.dataset.field===field;el.classList.toggle('selected',match);el.classList.toggle('active',match);el.classList.toggle('dim',el.classList.contains('field')&&!match)});const item=data[field];if(item)document.getElementById('reading').textContent='Field '+field+' · '+item.name+' — '+item.text;document.getElementById('plain').checked=false;document.querySelector('.frame').classList.remove('plain')}
document.querySelectorAll('[data-field]').forEach(el=>{el.onclick=()=>select(el.dataset.field);el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(el.dataset.field)}}});document.getElementById('all').onclick=()=>{document.querySelectorAll('[data-field]').forEach(el=>el.classList.remove('selected','active','dim'));document.getElementById('plain').checked=false;document.querySelector('.frame').classList.remove('plain');document.getElementById('reading').textContent='All detected field outlines shown.'};document.getElementById('plain').onchange=e=>document.querySelector('.frame').classList.toggle('plain',e.target.checked);
</script></html>'''
doc=doc.replace('WIDTH',str(crop.width)).replace('HEIGHT',str(crop.height)).replace('SVG',svg).replace('BUTTONS',buttons).replace('SOURCE',esc(page['name'])).replace('DATA',json.dumps(payload).replace('<','\\u003c'))
(out/'index.html').write_text(doc,encoding='utf-8')
(out/'regions.json').write_text(json.dumps(dict(record=record['record_id'],source=page['name'],frame=frame,regions=regions,missing=missing),indent=2),encoding='utf-8')
print(out/'index.html')
