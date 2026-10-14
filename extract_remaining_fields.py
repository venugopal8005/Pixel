"""Conservative, provisional address/organization boundaries without reference labels."""
import re
from extract_dates_postal import locate as date_spans
from extract_reference_codes import find_span
from client_rules import property_anchor,name_boundary

def nonempty_lines(text,start,end):
    return [(start+m.start(),start+m.end()) for m in re.finditer(r'[^\n]+',text[start:end]) if m.group().strip()]

def split_name(text,start,end):
    s=text[start:end];lead=len(s)-len(s.lstrip());s=s.strip();start+=lead
    match=re.match(r'(?:Mrs|Miss|Mrr|Mr|Ms|Maj|Col|Dr)(?:\.+|(?=\s))',s,re.I)
    if match:cut=match.end()
    else:
        cut=name_boundary(s)
        if cut is None:return {}
    rest=cut
    while rest<len(s) and s[rest].isspace():rest+=1
    if rest>=len(s):return {}
    return {27:(start,start+cut),28:(start+rest,start+len(s))}

def locate_remaining(text):
    found={};dates,_=date_spans(text);postal=dates.get(8)
    lid=re.search(r'L[i1]d/[A-Za-z0-9/]+-[A-Za-z0-9]+-\d+',text,re.I)
    if lid and postal:
        head=text[lid.end():postal[0]]
        address=re.search(r'P[.\s]*[O0][.\s]*(?:Box|Bak|B\b)|\d{3,}',head,re.I)
        if address:
            start=lid.end()+address.start()
            lines=nonempty_lines(text,start,postal[0])
            # Only a separate final text line supports a locality boundary.
            if len(lines)>=2:
                locality=lines[-1]
                if not re.search(r'\d',text[slice(*locality)]):
                    if len(lines)>=3 and re.fullmatch(r'\s*[A-Za-z]{2,20}\s*',text[slice(*lines[-2])]):
                        locality=(lines[-2][0],locality[1])
                    found[6]=(start,locality[0]);found[7]=locality
    utr=find_span(text,29)
    phone=property_anchor(text)
    secured=re.search(r'Secured\s*Loan',text,re.I)
    if utr and phone and secured and phone.end()<secured.start()<utr[0]:
        amounts=re.match(r'[\s.:]*(\d+(?:\.\d+)?)[\s]+(\d+(?:\.\d+)?)(?!\d)(?=$|[\s.]|[A-Z]{3})',text[secured.end():utr[0]])
        if amounts:
            start=secured.end()+amounts.end();end=utr[0]
            region=text[start:end]
            # Capitalized legal/organization endings anchor only the boundary;
            # original spelling and punctuation are retained in the extracted span.
            suffixes=list(re.finditer(r'(?:LLC|CORP(?:ORATION)?|CAPITAL|MORTGAGE|MORTGEG|HSAUTH|INC)(?![A-Z])',region))
            if suffixes:
                cut=start+suffixes[-1].end()
                person=split_name(text,cut,end)
                if person:
                    found[26]=(start,cut);found.update(person)
    ni=find_span(text,30)
    if ni:
        tail_start=ni[1]
        # Responses must end before whitespace, an uppercase organization start, or EOF.
        responses=list(re.finditer(r'(?:Yes|Yeas|Ye|NoNE|NONE|NOne|None|No|Mono)(?=\s|[A-Z]|$)',text[tail_start:]))
        if len(responses)==1:
            response=responses[0];a=tail_start+response.start();b=tail_start+response.end()
            if text[tail_start:a].strip():found[31]=(tail_start,a)
            found[32]=(a,b)
            final=re.search(r'(?:Good|Goood|Giood|Gclod|Goog|Gd)\s*$',text,re.I)
            if final and final.start()>b:
                lines=nonempty_lines(text,b,final.start())
                bank_start=None
                # A distinct bank/card line is required; a merged organization/bank
                # line remains unresolved instead of guessing a split from semantics.
                for i,(lo,hi) in enumerate(lines):
                    line=text[lo:hi].strip()
                    if i>0 and re.match(r'(?:Barclays|Bank\s*Of|American|Amercla|Amnerican|AmeTrcan|Mastercard|Capital|Capitak|U\.S\.Bank|Miliard)',line,re.I):
                        bank_start=lo;break
                if bank_start:
                    found[33]=(b,bank_start);found[34]=(bank_start,final.start())
    return found
