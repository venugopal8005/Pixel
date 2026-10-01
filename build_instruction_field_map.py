"""Build a read-only, reference-assisted field map; never change OCR decisions."""
import base64
import hashlib
import html
import json
from pathlib import Path

import openpyxl
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/field-map-v1'
MANUAL = Path('D:/projects/piXeL/INSTRUCTIONS.xlsx')
REFERENCE = Path('D:/projects/piXeL/manual.xlsx')
SOURCES = [Path(f'D:/projects/piXeL/manual/FORM TTYFRD_8AQ{n}_enc.jpg') for n in (159,160)]
FRAMES = [(484,980,945,1130),(15,34,475,124)]
PALETTE = ['#2563eb','#047857','#a21caf','#b45309','#6941c6','#be123c']

# Coordinates are manually reviewed candidates for THIS record, in original
# page pixels, with exclusive right/bottom edges. They are not global rules.
BOXES = {
    4: [(0,590,996,780,1015)],
    5: [(0,841,996,918,1015)], 6: [(0,491,1014,581,1032)],
    7: [(0,590,1014,888,1032)], 8: [(0,539,1031,655,1049)],
    9: [(0,692,1031,737,1049)], 10: [(0,742,1031,935,1049)],
    11: [(0,540,1048,617,1066)], 12: [(0,635,1048,718,1066)],
    13: [(0,741,1048,804,1067)],
    15: [(0,841,1048,887,1066),(0,491,1065,553,1083)],
    16: [(0,590,1065,720,1083)], 17: [(0,741,1065,885,1083)],
    18: [(0,540,1082,700,1100)], 19: [(0,741,1082,803,1100)],
    20: [(0,841,1082,873,1100)], 21: [(0,892,1082,936,1100)],
    22: [(0,540,1099,609,1115)], 23: [(0,637,1099,740,1115)],
    24: [(0,741,1099,792,1115)], 25: [(0,792,1099,842,1115)],
    27: [(0,842,1099,922,1115),(1,23,39,120,56)],
    28: [(1,121,39,229,56)], 29: [(1,229,39,306,56)],
    30: [(1,71,56,299,75)],
    31: [(1,322,56,451,75),(1,21,74,105,93)],
    32: [(1,119,74,183,93)], 33: [(1,221,74,246,93)],
    34: [(1,270,74,425,93)], 35: [(1,71,92,211,111)],
    36: [(1,221,92,262,111)],
}

NOTES = {
    1: 'Generated metadata: retain BOTH source image names for a joined record.',
    2: 'Manual conflicts: example says manually enter; instruction says auto generated. Printed source ID is retained separately until the output meaning is agreed.',
    3: 'Generated at export; use an explicitly selected business timezone.',
    4: 'Reference reads Lid/B888/6677-e6-9786795. Image/OCR can resemble 8888. Retain alternatives until resolved; no fixed prefix is specified by this manual.',
    5: 'Proposed semantic split: Clilnton / Diblrmagli. Existing Excel instead puts Mr. in its first-name slot and the full name in the next slot. Title is retained as extra source text.',
    6: 'Surname wraps onto the next line. Proposed mapping requires agreement on the same title/name conflict as field 5.',
    9: 'Numeric constraint, but preserve leading zeros as text. No exact digit count supplied.',
    10: 'Reference contains Turcday, Satmber 16 1952. Do not guess a month to force MM/DD/YYYY. Keep the literal text and flag normalization as unresolved.',
    14: 'Derived remark, no printed source region. Do not apply the example DOB/ALN/CALN warning to every record.',
    15: 'One value in two source regions: semi- / datache. Preserve spelling; record line-break removal separately.',
    16: 'Printed/reference identifier is 95279148317-2465. Manual suggests 10018-25789 and also lists 1001 245. Keep all digits; do not truncate to fit an example.',
    19: 'Detail sheet requests currency formatting; Fields Only says literal entry. Preserve raw digits and make currency formatting a separate export policy.',
    21: 'Manual calls this INTEREST TYPE but asks for a percent suffix. Keep the supplied column name.',
    22: 'Currency formatting conflict: retain 11800.72 as raw numeric text.',
    24: 'Mapped by the supplied reference order. Do not reclassify this amount based on its apparent financial meaning.',
    25: 'Mapped by the supplied reference order. Currency formatting is separate from character recognition.',
    26: 'Derived remark. A property-value format conflict is a review reason, not permission to erase or shorten it.',
    27: 'GREYSTONE ends AQ159; FUNDING CORP starts AQ160. Join both fragments as one lender name.',
    28: 'Source concatenates GOPALKRISHANSDELVACCHID. The split is assisted by the reference Excel; it is not an independently detected boundary.',
    29: 'Same joined source token as field 28. Boundary is approximate and reference-assisted.',
    30: 'Punctuation and letter/digit positions are literal. Manual gives no universal positional pattern.',
    31: 'N.I. reference wraps onto the following line. Both source regions belong to this field.',
    35: 'Append Credit Card only once in formatted export; preserve printed Amnerican Express spelling.',
    37: 'Derived remark. Manual differs between N.A. examples and Not Applicable instructions.',
}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    book = openpyxl.load_workbook(MANUAL,data_only=True,read_only=True)
    detail = {}
    for row, values in enumerate(book['Mortgage Instructions'].values,1):
        name, example, instruction, kind = values
        if row>1 and name:
            detail.setdefault(name,[]).append(dict(row=row,example=example,instruction=instruction,data_type=kind))
    refbook = openpyxl.load_workbook(REFERENCE,data_only=True,read_only=True)
    ref = next(list(row) for row in refbook.active.values if str(row[0])=='1802603503')
    fields=[]
    for number, values in enumerate(list(book['Fields Only'].values)[1:],1):
        section,name,example,instruction=values
        reference = None
        if number>=4: reference=ref[number-1]
        if number==5: reference='Clilnton (proposed split; original Excel: Mr.)'
        if number==6: reference='Diblrmagli (proposed split; original Excel: Clilnton Diblrmagli)'
        fields.append(dict(number=number,name=name,section=section,reference_value=reference,
            status=('mapping_review' if number in (5,6,28,29) else 'source_mapped') if number in BOXES else ('metadata' if number<=3 else 'derived_remark'),
            color=PALETTE[(number-1)%len(PALETTE)],
            regions=[dict(page=p,box=[x0,y0,x1,y1]) for p,x0,y0,x1,y1 in BOXES.get(number,[])],
            manual=dict(fields_only_row=number+1,example=example,instruction=instruction,detail_rows=detail.get(name,[])),
            note=NOTES.get(number,'Use the source spelling. Formatting does not establish that an OCR reading is correct.')))
    extra=[dict(key='ID',name='Printed source record ID',value='1802603503',page=0,box=[491,996,577,1015]),
           dict(key='T',name='Applicant title (retained extra)',value='Mr.',page=0,box=[787,996,824,1015])]
    pages=[dict(index=i,name=p.name,path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),frame=FRAMES[i]) for i,p in enumerate(SOURCES)]
    state=json.loads((ROOT/'outputs/review-app/44285fad34074a818204f8e791978c44/state.json').read_text(encoding='utf-8'))
    record=next(r for r in state['records'] if r['record_id']=='1802603503')
    # Box-intersection audit is evidence of map coverage, NOT an OCR recall score.
    coverage=[]
    for line in record['lines']:
        p=next(i for i,s in enumerate(SOURCES) if s.name==line['page'])
        a,b,c,d=line['source_box']; matches=[]
        for f in fields:
            for r in f['regions']:
                x,y,z,t=r['box']
                if r['page']==p and min(c,z)>max(a,x) and min(d,t)>max(b,y):
                    matches.append(str(f['number'])); break
        for e in extra:
            x,y,z,t=e['box']
            if e['page']==p and min(c,z)>max(a,x) and min(d,t)>max(b,y):matches.append(e['key'])
        coverage.append(dict(line=line['id'],page=p,box=line['source_box'],intersecting_fields=matches))
    assert len(fields)==37 and len(BOXES)==31
    assert all(c['intersecting_fields'] for c in coverage),coverage
    for f in fields:
        for r in f['regions']:
            a,b,c,d=FRAMES[r['page']];x,y,z,t=r['box']
            assert a<=x<z<=c and b<=y<t<=d,(f['number'],r)
    manifest=dict(record_id='1802603503',mapping_method='Manual source-coordinate annotation, assisted by user-supplied reference Excel. Not automatic extraction or verified glyph labels.',
        manual=dict(path=str(MANUAL),sha256=hashlib.sha256(MANUAL.read_bytes()).hexdigest()),reference_path=str(REFERENCE),
        coordinate_system='Original image pixels, x/y origin top-left, exclusive right/bottom. Specific to this example only.',
        pages=pages,fields=fields,retained_extra_fields=extra,existing_ocr_line_coverage=coverage,
        limitations=['All 37 manual fields represented: 31 source fields, 3 metadata fields, 3 remarks.',
          'Both record fragments and title/source ID retained. Every existing OCR line intersects a field or retained extra; this is not proof that OCR found all source text.',
          'Word wrapping and cross-page names require multiple regions per field, not one fixed rectangle.',
          'No universal field lengths or per-character templates have been inferred from this single record.',
          'Current numeric/name/date formatting conflicts remain pending; no existing workbook or user decision was edited.'])
    (OUT/'field-map.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    build_views(manifest)
    print(json.dumps(dict(output=str(OUT/'index.html'),fields=len(fields),source_fields=len(BOXES),ocr_lines_accounted=len(coverage))))

def build_views(data):
    images=[Image.open(p).convert('RGB').crop(FRAMES[i]) for i,p in enumerate(SOURCES)]
    for i,im in enumerate(images):im.save(OUT/f'fragment-{i+1}.png')
    # Keep the actual source pixels separate from all labels and overlays.
    font=lambda size: ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
    canvas=Image.new('RGB',(1500,1720),'#f4f7fb');draw=ImageDraw.Draw(canvas)
    draw.text((48,28),'PIXEL / A record across two pages',font=font(35),fill='#102f48')
    draw.text((48,79),'1802603503  |  37 manual fields  |  numbered source regions',font=font(21),fill='#486174')
    draw.text((48,111),'Reference-assisted map for review. Positions apply to this record only.',font=font(19),fill='#486174')
    cursor=157
    for p,im in enumerate(images):
        draw.text((48,cursor),f'PART {p+1}  /  AQ{159+p} '+('right column, bottom' if p==0 else 'left column, top'),font=font(21),fill='#102f48')
        ybase=cursor+38;xbase=48;scale=3
        canvas.paste(im.resize((im.width*scale,im.height*scale),Image.Resampling.NEAREST),(xbase,ybase))
        regions=[dict(label=str(f['number']),color=f['color'],**r) for f in data['fields'] for r in f['regions'] if r['page']==p]
        regions += [dict(label=e['key'],color='#334155',**e) for e in data['retained_extra_fields'] if e['page']==p]
        for r in regions:
            x,y,z,t=r['box'];a,b,_,_=FRAMES[p]
            x=xbase+(x-a)*scale;z=xbase+(z-a)*scale;y=ybase+(y-b)*scale;t=ybase+(t-b)*scale
            draw.rectangle((x,y,z,t),outline=r['color'],width=2)
            label=r['label'];w=draw.textlength(label,font=font(13))+7
            draw.rectangle((x,y-14,x+w,y),fill=r['color']);draw.text((x+3,y-14),label,font=font(13),fill='white')
        cursor=ybase+im.height*scale+24
    draw.text((48,cursor),'FIELD KEY  /  Click any field in the HTML map to isolate its source.',font=font(21),fill='#102f48');cursor+=40
    for index,f in enumerate(data['fields']):
        col=index//13;row=index%13;x=48+col*475;y=cursor+row*30
        label=f"{f['number']:02}  {f['name']}"+(' *' if not f['regions'] else '')
        draw.text((x,y),label,font=font(17),fill=f['color'] if f['regions'] else '#64748b')
    cursor+=13*30+17
    draw.text((48,cursor),'* Metadata / remarks have no printed region. ID = source record ID; T = retained title.',font=font(18),fill='#486174')
    draw.text((48,cursor+31),'Review: applicant name split, joined officer name, date, property-value format and output rules.',font=font(18),fill='#92400e')
    canvas.crop((0,0,1500,cursor+83)).save(OUT/'record-1802603503-field-map.png')
    frames=[]
    for p,im in enumerate(images):
        encoded=base64.b64encode((OUT/f'fragment-{p+1}.png').read_bytes()).decode()
        rects=[]
        for f in data['fields']:
            for r in f['regions']:
                if r['page']!=p:continue
                a,b,_,_=FRAMES[p];x,y,z,t=r['box']
                rects.append(f'<g data-n="{f["number"]}" role="button" tabindex="0" aria-label="{html.escape(f["name"])}"><title>{f["number"]} {html.escape(f["name"])}</title><rect x="{x-a}" y="{y-b}" width="{z-x}" height="{t-y}" stroke="{f["color"]}"/><text x="{x-a+1}" y="{y-b-1}" fill="{f["color"]}">{f["number"]}</text></g>')
        for e in data['retained_extra_fields']:
            if e['page']!=p:continue
            a,b,_,_=FRAMES[p];x,y,z,t=e['box']
            rects.append(f'<g class="extra"><title>{html.escape(e["name"])}: {e["value"]}</title><rect x="{x-a}" y="{y-b}" width="{z-x}" height="{t-y}" stroke="#475569"/><text x="{x-a}" y="{y-b-1}">{e["key"]}</text></g>')
        frames.append(f'<h3>Part {p+1} · {SOURCES[p].name} · '+('right bottom' if p==0 else 'left top')+f'</h3><div class="frame"><img src="data:image/png;base64,{encoded}" alt="Original source fragment {p+1}"><svg viewBox="0 0 {im.width} {im.height}">'+''.join(rects)+'</svg></div>')
    buttons=''.join(f'<button data-n="{f["number"]}"><b>{f["number"]:02}</b> {html.escape(f["name"])}<small>'+('Source regions' if f['regions'] else 'No printed region')+'</small></button>' for f in data['fields'])
    template='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pixel · Instruction field map</title>
<style>body{margin:0;background:#f4f7fb;color:#173348;font:15px system-ui}main{max-width:1450px;margin:auto;padding:24px}h1{font-size:30px;margin:6px 0}h2{font-size:20px}h3{font-size:14px;color:#476275}p{line-height:1.5}.eyebrow{letter-spacing:.12em;font-size:12px;font-weight:750;color:#2563eb}.intro{max-width:1000px}.layout{display:grid;grid-template-columns:minmax(0,1fr) 350px;gap:18px}.card{border:1px solid #d7e2ea;background:white;border-radius:12px;padding:20px;margin:12px 0}.source{position:sticky;top:12px}.frame{position:relative;line-height:0}.frame img{width:100%;image-rendering:pixelated}.frame svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}svg g{cursor:pointer}svg rect{fill:transparent;stroke-width:.6}svg text{font:bold 4.5px system-ui;paint-order:stroke;stroke:white;stroke-width:.7px}svg g.selected rect{fill:#f59e0b30;stroke:#df6b00;stroke-width:1.2}svg g.dim{opacity:.08}.plain svg{display:none}.buttons{display:grid;grid-template-columns:1fr;gap:6px;max-height:580px;overflow:auto}button{font:inherit;text-align:left;border:1px solid #d6e1e9;background:white;color:#234156;padding:9px;border-radius:6px;cursor:pointer}button b{color:#2563eb;margin-right:8px}button.active{border-color:#2563eb;background:#eff6ff}small{display:block;color:#688093;font-size:11px;margin-left:29px}.bar{display:flex;flex-wrap:wrap;gap:14px;align-items:center}#detail{overflow-wrap:anywhere;min-height:210px}#detail p{margin:8px 0}.muted{color:#597386;font-size:13px}.warning{background:#fffbeb;border-left:4px solid #d97706;padding:12px;line-height:1.5}.pill{display:inline-block;padding:5px 9px;border-radius:20px;background:#e9f0f6;font-size:12px;margin-right:5px}a{color:#1d4ed8}.factgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.factgrid p{margin:4px 0}.factgrid strong{display:block;font-size:27px}@media(max-width:1000px){.layout{grid-template-columns:1fr}.source{position:static}.buttons{grid-template-columns:repeat(2,1fr);max-height:300px}.factgrid{grid-template-columns:1fr}}</style>
<main><div class="eyebrow">PIXEL / V1 FIELD MAPPING</div><h1>One record. Two page fragments.</h1><p class="intro">Record <b>1802603503</b> is shown below using the original image pixels. Select a field to see exactly which source regions belong to it, the supplied Excel value, and the manual’s rule. This is a <b>reference-assisted mapping proposal</b>, not a new OCR accuracy result.</p>
<div class="factgrid"><div class="card"><strong>37</strong><p>Manual fields: 31 source fields, 3 metadata, 3 remarks.</p></div><div class="card"><strong>2 source fragments</strong><p>Lender name crosses the page boundary. Wrapped fields keep multiple regions.</p></div><div class="card"><strong>2 retained extras</strong><p>Printed record ID and “Mr.” title stay visible while their output mapping is agreed.</p></div></div>
<div class="layout"><section><div class="card source"><div class="bar"><button id="all">Show all fields</button><label><input id="plain" type="checkbox"> Original pixels only</label><a href="record-1802603503-field-map.png">Numbered map image</a></div>FRAMES<p class="muted">Coordinates refer to each original page. Outlines are manually placed candidates. They must adapt to wrapping and page continuations on future images.</p></div></section><aside><section class="card" id="detail" aria-live="polite"></section><div class="buttons">BUTTONS</div></aside></div>
<section class="card"><h2>Rules that need agreement before they become automatic</h2><div class="warning"><b>Applicant fields:</b> the old Excel contains “Mr.” followed by a full name; this manual requests first and last name. The proposed map separates the name and retains the title.<br><b>Property value:</b> the source identifier is longer than the example format, and the manual itself gives two formats. Preserve the entire identifier.<br><b>Date:</b> “Satmber” is not an unambiguous month. Keep the source text and request review before producing a numeric date.<br><b>Export conventions:</b> resolve auto/manual record numbering, literal/currency presentation, and N.A./Not Applicable without changing the stored source text.</div></section>
<section class="card"><h2>How V1 should prevent silent omissions</h2><p>Keep every uploaded page and its order. Track each detected fragment as a new record, a continuation, or a fragment needing review. Join only supported continuations, keep both source links, and flag missing adjacent pages. Preserve unassigned source text alongside the mapped fields.</p><p>Export unresolved characters as <b>[i/l]</b> or <b>[?]</b>. An uncertain field boundary or continuation needs its own review status; character brackets alone cannot describe a possibly misassigned record.</p><p class="muted">This sample accounts for all EXISTING_LINES existing OCR line boxes, using field/extra-region intersections. That is a mapping check, not proof that the OCR detected every character. The full fragment images remain available for inspection. No existing Excel values or saved review decisions were changed.</p><a href="field-map.json">Download field coordinates and workbook rules</a></section></main>
<script>const data=PAYLOAD;
const detail=document.getElementById('detail');function paragraph(label,value){const p=document.createElement('p');const b=document.createElement('b');b.textContent=label+': ';p.append(b,document.createTextNode(value));detail.append(p)}
function select(n){const f=data.fields.find(x=>String(x.number)===String(n));if(!f)return;document.querySelectorAll('[data-n]').forEach(e=>{const same=e.dataset.n===String(n);e.classList.toggle('selected',same);e.classList.toggle('active',same);e.classList.toggle('dim',e.tagName.toLowerCase()==='g'&&!same)});document.getElementById('plain').checked=false;document.querySelectorAll('.frame').forEach(e=>e.classList.remove('plain'));detail.replaceChildren();const h=document.createElement('h2');h.textContent=f.number+' · '+f.name;detail.append(h);paragraph('Location',f.regions.length?f.regions.map(r=>'AQ'+(159+r.page)+' ['+r.box.join(', ')+']').join(' + '):'No printed region — '+f.status.replaceAll('_',' '));paragraph('Reference / proposed value',f.reference_value??'Not sourced from printed text');paragraph('Fields Only rule',f.manual.instruction);f.manual.detail_rows.forEach(r=>paragraph('Detail sheet row '+r.row,(r.instruction??'(no instruction)')+' | Type: '+(r.data_type??'unspecified')));paragraph('Mapping note',f.note);paragraph('Rule source','INSTRUCTIONS.xlsx · Fields Only row '+f.manual.fields_only_row)}
document.querySelectorAll('[data-n]').forEach(e=>{e.onclick=()=>select(e.dataset.n);if(e.tagName.toLowerCase()==='g')e.onkeydown=k=>{if(k.key==='Enter'||k.key===' '){k.preventDefault();select(e.dataset.n)}}});document.getElementById('plain').onchange=e=>document.querySelectorAll('.frame').forEach(f=>f.classList.toggle('plain',e.target.checked));document.getElementById('all').onclick=()=>{document.querySelectorAll('[data-n]').forEach(e=>e.classList.remove('dim','selected','active'));document.getElementById('plain').checked=false;document.querySelectorAll('.frame').forEach(e=>e.classList.remove('plain'));detail.textContent='All source regions shown. Select a field for its rule and reference value.'};select(27);
</script></html>'''
    doc=template.replace('FRAMES',''.join(frames)).replace('BUTTONS',buttons).replace('EXISTING_LINES',str(len(data['existing_ocr_line_coverage']))).replace('PAYLOAD',json.dumps(data,ensure_ascii=False).replace('<','\\u003c'))
    (OUT/'index.html').write_text(doc,encoding='utf-8')

if __name__=='__main__':main()
