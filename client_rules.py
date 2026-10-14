"""Client transcription conventions (October 2026), independent of OCR evidence.

Detailed examples override general formatting instructions. Unknown OCR and
unlocated fields are never converted to assertions that printed data is missing.
"""
import calendar
import re
from datetime import date
from decimal import Decimal, ROUND_DOWN, localcontext

NAMES={4,5,10,11,27,28}
CURRENCY={18,21,23,24}
NO_BREAK_SPACE={3,8,15,18,21,23,24,29,30}
INVALID_FIELDS=NAMES|{8,9,15,29,30}
ABBREVIATIONS=dict(zip(
    [3,4,5,6,7,8,9,10,11,12,14,15,16,17,18,19,20,21,22,23,24,26,27,28,29,30,31,32,33,34,35],
    'LI AFN ALN ST CT ZC DOB CAFN CALN BTC TP PV PL MT LA LT IT MI EL AI DP LN LOFN LOLN TR NI OC OI CCI CCT CS'.split()))


def property_anchor(text):
    # Variable digit-group lengths require a following purpose label; otherwise
    # a date or reference code could be mistaken for the property identifier.
    matches=list(re.finditer(r'(?<![\w/-])\d+\s*-\s*\d+(?![\d/-])(?=\s*(?:Debt|Debit|dect)\s*c[a-z]{3,22}tion)',text,re.I))
    if len(matches)==1:return matches[0]
    return re.search(r'\d{11}-\d{4}',text)


def name_boundary(text):
    """First token, with the explicit DavidThomas / AlfredY convention."""
    camel=re.match(r'[A-Z][a-z]+(?=[A-Z])',text)
    if camel:return camel.end()
    space=re.search(r'\s+',text)
    return space.start() if space else None


def physical_break(previous,current):
    if not previous:return False
    if previous.get('page')!=current.get('page') or previous.get('fragment')!=current.get('fragment'):return True
    def bounds(line):
        if line.get('source_box'):return line['source_box']
        points=line['box'];return [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
    a,b=bounds(previous),bounds(current)
    return min(a[3],b[3])-max(a[1],b[1]) < min(a[3]-a[1],b[3]-b[1])*.4


def join_parts(field,parts):
    """Only real physical line breaks invoke the client's joining rules."""
    result=''
    for i,part in enumerate(parts):
        text=part['text']
        if part.get('line_break'):
            before=result.rstrip()
            sep=' '
            if field in NO_BREAK_SPACE:sep=''
            elif field in (6,9) and before:
                char=before[-1]
                # A displayed [?] or [i/t] is not a printed punctuation mark.
                if not char.isalnum() and char not in '&]':sep=''
            result=before+sep
        else:result+=text
    return ' '.join(result.split())


def format_date(text):
    original=text
    # Retain weekday spelling (and flag misspellings), rather than inventing it.
    prefix='';weekday_valid=True
    weekday=re.match(r'^([A-Za-z]+)([.,]?)(\s*)',text,re.I)
    month_words={m.lower() for m in [*calendar.month_name,*calendar.month_abbr] if m}
    if weekday and weekday.group(1).lower() in month_words:weekday=None
    if weekday:
        name,punctuation,space=weekday.groups()
        weekday_valid=name.lower() in {d.lower() for d in calendar.day_name}
        prefix=name+(',' if punctuation else '')+space
        text=text[weekday.end():]
    months={name.lower():i for i,name in enumerate(calendar.month_name) if name}
    months.update({name.lower():i for i,name in enumerate(calendar.month_abbr) if name})
    tokens=re.split(r'[^A-Za-z0-9]+',text.strip())
    # Repeated separators and malformed grouping are evidence, not noise to erase.
    if re.search(r'[/.:\-]{2,}',text) or len(tokens)!=3:return original,False
    a,b,year=tokens
    if a.lower() in months:month,day=months[a.lower()],b
    elif b.lower() in months:month,day=months[b.lower()],a
    elif a.isdigit() and b.isdigit():
        if len(a)>2 or len(b)>3:return original,False
        month,day=int(a),b
        if month>12 and len(a)<=2 and int(b)<=12:month,day=int(b),a
    else:return original,False
    if not day.isdigit() or not year.isdigit():return original,False
    formatted=prefix+f'{int(month):02d}/{int(day):02d}/{year}'
    if len(year) not in (2,4):return formatted,False
    if len(day)>2 and not (len(day)==3 and day[0]=='0'):return formatted,False
    try:date(int(year) if len(year)==4 else 2000+int(year),int(month),int(day))
    except ValueError:return formatted,False
    return formatted,weekday_valid


def format_value(field,text):
    """Format literal text; return validation reasons without guessing spelling."""
    issues=[]
    if field in NAMES:
        if field in (5,11,28):text=re.sub(r'\b([A-Z][a-z]+)(?=[A-Z])',r'\1 ',text)
        text=re.sub(r'[A-Za-z]+',lambda m:m.group().capitalize(),text)
        if text.endswith('.'):issues.append('Name ends with a period; client instructions mark this invalid.')
    elif field==8:
        if not re.fullmatch(r'\d{1,6}',text) or not any(c in '123456789' for c in text):
            issues.append('ZIP must contain 1–6 digits and cannot be all zeros; source retained.')
    elif field==15:
        if not re.fullmatch(r'\d+-\d+',text):issues.append('Property value requires digit groups on both sides of one hyphen; source retained.')
    elif field in CURRENCY:
        raw=text.removeprefix('$').replace(',','').strip()
        if re.fullmatch(r'\d+(?:\.\d+)?',raw):
            with localcontext() as context:
                context.prec=max(28,len(raw)+4)
                text=f'${Decimal(raw).quantize(Decimal("0.01"),rounding=ROUND_DOWN):,.2f}'
        elif text not in ('-','@','#'):
            issues.append('Amount is not numeric; source retained. Client documents disagree about an INVALID remark for amounts.')
    elif field in (19,20):
        raw=re.sub(r'\s+Months$','',text,flags=re.I) if field==19 else text.removesuffix('%')
        if re.fullmatch(r'\d+' if field==19 else r'\d+(?:\.\d+)?',raw):text=raw+(' Months' if field==19 else '%')
        else:issues.append('Expected '+('whole months' if field==19 else 'a numeric percentage')+'; source retained.')
    elif field==9:
        text,valid=format_date(text)
        if not valid:issues.append('Date is invalid or spelling is unrecognized; source spelling retained.')
    elif field==29:
        if '#' not in text or '/' not in text:issues.append('TR requires both # and /; missing symbols were not inserted.')
    elif field==30:
        if '#' not in text:issues.append('NI requires #; missing symbol was not inserted.')
    elif field==34:
        if not text.lower().endswith(' credit card'):text+=' Credit Card'
    elif field==1 and not re.fullmatch(r'\d+',text):issues.append('Record ID must contain digits; source retained.')
    return text,issues


def remarks(cells,group):
    categories={k:[] for k in ('INVALID','MISSING','MERGE')}
    for field in group:
        cell=cells[field]
        # Only an explicit source-status decision can assert missing/merged data.
        status=cell.get('source_status')
        if status in ('missing','merge'):categories[status.upper()].append(ABBREVIATIONS[field])
        elif field in INVALID_FIELDS and cell.get('validation_issues') and cell.get('status')!='unmapped' and (cell.get('manual') or not cell.get('pending')):
            categories['INVALID'].append(ABBREVIATIONS[field])
    clauses=[]
    for label,fields in categories.items():
        if not fields:continue
        names=fields[0] if len(fields)==1 else ', '.join(fields[:-1])+' AND '+fields[-1]
        clauses.append(names+(' IS ' if len(fields)==1 else ' ARE ')+label)
    return ' AND '.join(clauses)+'.' if clauses else 'Not Applicable'
