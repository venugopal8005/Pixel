"""Conservative manual-derived validation and display; no reference answers."""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from field_constraints import RULES, project_cell, allowed

HEADERS=['IMAGE NO','RECORD NO','TODAY’S DATE','LEAD ID','APPLICANT FIRST NAME','APPLICANT LAST NAME','STREET ADDRESS','CITY','ZIP CODE','APPLICANT D.O.B','CO-APPLICANT FIRST NAME','CO-APPLICANT LAST NAME','BEST TIME TO CALL','REMARK 1','TYPE OF PROPERTY','PROPERTY VALUE','PURPOSE OF LOAN','MORTGAGE TYPE','LOAN AMOUNT','LOAN TERM','INTEREST TYPE','MONTHLY INSTALLMENT','EXISTING LOAN','ANNUAL INCOME','DOWN PAYMENT','REMARKS2','LENDER NAME','LOAN OFFICER FIRST NAME','LOAN OFFICER LAST NAME','T.R. #','N.I. #','OCCUPATION','OTHER INCOME','CREDIT CARD ISSUER','CREDIT CARD TYPE','CREDIT SCORE','REMARKS3']
NUMERIC={1,8,15,18,19,20,21,23,24}
CURRENCY={18,21,23,24}
NAMES={4,5,10,11,27,28}
REMARKS={13,25,36}
TITLE=re.compile(r'^(?:mrs|miss|mis|mrr|mr|ms|maj|col|dr)\.*$',re.I)

def apply_rule(field,value,constrain_choices=True):
    """Return display and reasons; never rewrite the stored OCR or decisions."""
    if value is None:return value,[]
    text=str(value);issues=[]
    if field in NUMERIC and constrain_choices:
        def constrain(match):
            choices=match.group(1).split('/')
            if len(choices)<2:return match.group()
            permitted=[v for v in choices if v=='∅' or allowed(RULES[field]['kind'],v)]
            if len(permitted)==1 and permitted[0]!='∅':
                issues.append('Numeric rule selected '+permitted[0]+' from '+match.group()+'. Source review remains required.')
                return permitted[0]
            return match.group()
        text=re.sub(r'\[([^\]]+)\]',constrain,text)
    if '[' in text or ']' in text:return text,issues
    if not text:return text,issues
    kind=RULES[field]['kind']
    if kind=='text' and not allowed(kind,text):
        issues.append('This field is specified as text but contains digits. Source retained; check the reading or boundary.')
    if field in (1,8):
        if not re.fullmatch(r'[0-9]+',text):issues.append(('Record ID' if field==1 else 'ZIP')+' must contain digits. Preserve the source until corrected.')
    elif field in CURRENCY or field in (19,20):
        raw=text.removeprefix('$').removesuffix(' Months').removesuffix('%').strip()
        if re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?',raw):
            number=Decimal(raw.replace(',',''))
            if field in CURRENCY:
                if number.as_tuple().exponent < -2:
                    issues.append('More than two decimal places; value was not rounded.')
                else:text=f'${number:,.2f}'
            elif field==19:
                if number!=number.to_integral_value():issues.append('Loan term is not a whole number of months.')
                else:text=str(int(number))+' Months'
            else:text=raw+'%'
        else:issues.append('Expected a numeric value; no letter-to-digit guess was applied.')
    elif field==9:
        # Only exact calendar spellings or explicit US numeric dates, not fuzzy dates.
        candidate=re.sub(r'^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+','',text,flags=re.I)
        result=None
        for fmt in ('%m/%d/%Y','%B %d %Y','%B %d, %Y','%d %B %Y','%d %B, %Y'):
            try:result=datetime.strptime(candidate,fmt).strftime('%m/%d/%Y');break
            except ValueError:pass
        if result:text=result
        else:issues.append('Date cannot be safely formatted as MM/DD/YYYY; source spelling retained.')
    elif field in NAMES:
        if TITLE.fullmatch(text):issues.append('This appears to be a title. First/last name boundary needs review.')
        else:text=text.capitalize() if field in (4,10,27) else text.title()
    elif field==15:
        if not re.fullmatch(r'\d{5}-\d{5}',text):issues.append('Property-value example conflicts with this source. Full value retained; format needs agreement.')
    elif field==34:
        if not text.lower().endswith('credit card'):text+=' Credit Card'
    return text,issues

def decorate(state,record,cells):
    if state.get('schema_version')!=2:return cells
    pages=list(dict.fromkeys([f['page'] for f in record.get('fragments',[])]+[l['page'] for l in record['lines']]))
    for field,value in ((0,' + '.join(pages)),(2,state.get('created_date',''))):
        if not cells[field]['manual']:
            cells[field].update(value=value,plain=value,status='generated',sources=[],segments=[],pending=0)
    for field in REMARKS:
        if not cells[field]['manual']:cells[field].update(value='Not Applicable',plain='Not Applicable',status='generated')
    for cell in cells:
        project_cell(cell,record,state.get('decisions',{}))
        value,issues=apply_rule(cell['field'],cell['value'],constrain_choices=False)
        issues=list(dict.fromkeys(cell.get('rule_conflicts',[])+issues))
        cell['value']=value;cell['rule_issues']=issues
        if cell['field']==5 and TITLE.fullmatch(str(cells[4].get('raw_value',''))):
            issues.append('Full name follows a title in the first-name cell. Split requires review.')
        # Human confirmation and rule validity are separate facts. Keep the
        # confirmed status while retaining validation details for review/export.
        if issues and not cell['manual']:cell['status']='uncertain'
    # Derived remarks reflect actual issues, not example warnings in the manual.
    for remark,group in ((13,range(3,13)),(25,range(14,25)),(36,range(26,36))):
        if not cells[remark]['manual']:
            flagged=[HEADERS[f] for f in group if cells[f]['status'] in ('uncertain','unmapped') or cells[f].get('rule_issues')]
            cells[remark]['value']='Review: '+', '.join(flagged) if flagged else 'Not Applicable'
            cells[remark]['plain']=cells[remark]['value']
    return cells

def adjacent_pages(previous,current):
    if previous==current:return True
    def number(name):
        m=re.search(r'(\d+)(?:_enc)?(?:\.(?:jpe?g|png))+$',name,re.I)
        return (name[:m.start()],int(m.group(1))) if m else None
    a,b=number(previous),number(current)
    return a is None or b is None or (a[0]==b[0] and b[1]==a[1]+1)
