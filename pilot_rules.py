"""Conservative manual-derived validation and display; no reference answers."""
import re
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
    from client_rules import format_value
    text,validation=format_value(field,text)
    issues.extend(validation)
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
        value,validation=apply_rule(cell['field'],cell['value'],constrain_choices=False)
        # A period on the first token is valid when a last name follows; the
        # error examples reserve INVALID for the end of the full name.
        if cell['field'] in (4,10,27):
            last=cells[cell['field']+1]
            if last.get('value') not in (None,'','[?]','N.A','N.A.') and last.get('status')!='unmapped':
                validation=[v for v in validation if not v.startswith('Name ends')]
        if cell['manual'] and str(cell['value']).upper() in ('N.A','N.A.'):
            cell['source_status']='missing';validation=[];value='N.A'
        issues=validation
        issues=list(dict.fromkeys(cell.get('rule_conflicts',[])+issues))
        cell['value']=value;cell['rule_issues']=issues
        cell['validation_issues']=validation
        # Human confirmation and rule validity are separate facts. Keep the
        # confirmed status while retaining validation details for review/export.
        if issues and not cell['manual']:cell['status']='uncertain'
    # Derived remarks reflect actual issues, not example warnings in the manual.
    for remark,group in ((13,range(3,13)),(25,range(14,25)),(36,range(26,36))):
        if not cells[remark]['manual']:
            from client_rules import remarks
            cells[remark]['value']=remarks(cells,group)
            cells[remark]['plain']=cells[remark]['value']
    return cells

def adjacent_pages(previous,current):
    if previous==current:return True
    def number(name):
        m=re.search(r'(\d+)(?:_enc)?(?:\.(?:jpe?g|png))+$',name,re.I)
        return (name[:m.start()],int(m.group(1))) if m else None
    a,b=number(previous),number(current)
    return a is None or b is None or (a[0]==b[0] and b[1]==a[1]+1)
