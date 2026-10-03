"""Regression cases for financial field boundaries, independent of Excel targets."""
import copy
import unittest

from extract_fields import locate
from extract_text_fields import locate as text_fields
from review_app import export_data, locate_field_spans, sheet_data
from test_field_extraction import lines
from test_sheet_review import fixture


def financial_lines(*middle):
    return lines('1234567890', '95279148304-5863', 'Debt consolidation',
                 'Fannie Mae Mortgage', *middle, 'Secured Loan', '50000', '30000')


def state_for(values, alternatives=None, separators=None, unknown=None):
    state=fixture();state.update(schema_version=2,created_date='10/02/2026')
    record=state['records'][0];record['lines']=[]
    for n,line in enumerate(values):
        segments=[]
        for i,c in enumerate(line['text']):
            if (n,i) in (separators or set()):
                segments.append(dict(id=f'n{n}sep{i}',text='',options=['',' '],
                    category='ambiguous',x=i*8,reason='OCR space disagreement'))
            choices=(alternatives or {}).get((n,i),[c])
            category='unrecognized' if (n,i) in (unknown or set()) else ('ambiguous' if len(choices)>1 else 'single')
            segments.append(dict(id=f'n{n}s{i}',text=c,options=choices,
                category=category,x=i*8,reason='OCR evidence'))
        record['lines'].append(dict(id=f'n{n}',image=f'line-{n}.png',page='source.jpg',
            fragment='first' if n<6 else 'continuation',segments=segments,
            box=[[0,0],[len(line['text'])*8,0],[len(line['text'])*8,18],[0,18]]))
    return state


class FinancialMappingTests(unittest.TestCase):
    def test_punctuation_errors_do_not_change_field_count(self):
        values=financial_lines('240000','360','6:87','1567-89')
        boxes,_=locate(values)
        self.assertEqual([boxes[f]['locator_text'] for f in range(18,22)],
                         ['240000','360','6:87','1567-89'])

    def test_leading_unknown_decimal_is_located_without_filling_digit(self):
        values=financial_lines('240000','360','.6','1567.89')
        state=state_for(values,unknown={(6,0),(6,1)})
        cells=sheet_data(state)[0]['cells']
        self.assertEqual(cells[20]['value'],'[?][?]')
        self.assertEqual(cells[20]['status'],'uncertain')
        self.assertFalse(cells[20].get('candidate',False))
        self.assertEqual(cells[18]['value'],'$240,000.00')
        self.assertEqual(cells[21]['value'],'$1,567.89')

    def test_separator_alternative_maps_joined_product_amount_and_term(self):
        values=lines('1234567890','95279148304-5863','Debt consolidation',
                     'Mortgage240000360','6.87','1567.89','Secured Loan','50000','30000')
        state=state_for(values,separators={(3,8),(3,14)})
        before=copy.deepcopy(state)
        cells=sheet_data(state)[0]['cells']
        self.assertEqual(cells[17]['value'],'Mortgage')
        self.assertEqual(cells[18]['value'],'$240,000.00')
        self.assertEqual(cells[19]['value'],'360 Months')
        self.assertEqual(cells[18]['sources'][0]['line'],'n3')
        self.assertLess(cells[18]['sources'][0]['left'],cells[19]['sources'][0]['left'])
        self.assertFalse(set(s['id'] for s in cells[18]['segments']) & set(s['id'] for s in cells[19]['segments']))
        self.assertEqual(state,before)

    def test_joined_numbers_without_separator_evidence_are_not_split(self):
        boxes,_=locate(financial_lines('240000360','6.87','1567.89'))
        self.assertTrue(all(f not in boxes for f in range(18,22)))

    def test_unreadable_token_cannot_be_skipped_to_make_four_numbers(self):
        boxes,_=locate(financial_lines('240000','360','???','6.87','1567.89'))
        self.assertTrue(all(f not in boxes for f in range(18,22)))

    def test_extra_number_does_not_shift_financial_columns(self):
        boxes,_=locate(financial_lines('240000','360','12','6.87','1567.89'))
        self.assertTrue(all(f not in boxes for f in range(18,22)))

    def test_repeated_amount_keeps_distinct_source_offsets(self):
        values=lines('1234567890','95279148304-5863','Debt consolidation',
                     'Mortgage','30000','360','6.87','1567.89','Secured Loan','50000','30000')
        text=''.join(v['text']+'\n' for v in values)
        spans=locate_field_spans(text,values)
        self.assertEqual(text[slice(*spans[18])],'30000')
        self.assertEqual(text[slice(*spans[24])],'30000')
        self.assertNotEqual(spans[18],spans[24])
        cells=sheet_data(state_for(values))[0]['cells']
        self.assertEqual(cells[18]['sources'][0]['line'],'n4')
        self.assertEqual(cells[24]['sources'][0]['line'],'n10')

    def test_same_line_rate_and_payment_keep_separate_characters_and_crops(self):
        state=state_for(financial_lines('240000','360','6:87 1567.89'),
                        alternatives={(6,1):[':', '.', '：']})
        cells=sheet_data(state)[0]['cells']
        self.assertEqual(cells[20]['value'],'6.87%')
        self.assertEqual(cells[20]['raw_value'],'6[:/./：]87')
        self.assertEqual(cells[20]['status'],'read')
        self.assertFalse(cells[20]['manual'])
        self.assertEqual(cells[21]['value'],'$1,567.89')
        rate_ids={s['id'] for s in cells[20]['segments']}
        payment_ids={s['id'] for s in cells[21]['segments']}
        self.assertFalse(rate_ids & payment_ids)
        self.assertLess(cells[20]['sources'][0]['right'],cells[21]['sources'][0]['right'])
        data=export_data(state)
        self.assertEqual(data['rows'][0][20:22],['6.87%','$1,567.89'])
        self.assertTrue(any(r[2]=='Field-rule alternative filter' for r in data['review']))

    def test_unoffered_decimal_is_not_silently_repaired(self):
        cells=sheet_data(state_for(financial_lines('240000','360','6:87','1567.89')))[0]['cells']
        self.assertEqual(cells[20]['value'],'6:87')
        self.assertTrue(cells[20]['rule_issues'])

    def test_product_cannot_swallow_numbers_when_anchor_is_unreadable(self):
        text='95279148304-5863\nDebt consolidation\nMortgage240000360\n6.87\n1567.89\nSecorred Loan50000\n30000\nLender\n1234567\n'
        spans,_=text_fields(text)
        self.assertNotIn(17,spans)

    def test_missing_primary_amount_does_not_use_income_as_product_boundary(self):
        text='95279148304-5863\nDebt consolidation\nMortgage\n???\nSecured Loan\n50000\n30000\n'
        spans,_=text_fields(text)
        self.assertNotIn(17,spans)

    def test_saved_human_edit_remains_in_its_located_field(self):
        values=financial_lines('240000','360','6:87 1567.89')
        state=state_for(values,alternatives={(6,1):[':','.']})
        state['decisions']['n6s1']='??'
        cells=sheet_data(state)[0]['cells']
        self.assertEqual(cells[20]['value'],'6??87')
        self.assertEqual(cells[21]['value'],'$1,567.89')

    def test_mortgage_type_may_itself_be_secured_loan(self):
        values=lines('1234567890','95279148304-5863','Debt consolidation',
                     'Secured Loan','240000','360','6.87','1567.89','Secured Loan','50000','30000')
        cells=sheet_data(state_for(values))[0]['cells']
        self.assertEqual(cells[17]['plain'],'Secured Loan')
        self.assertEqual(cells[17]['sources'][0]['line'],'n3')
        self.assertEqual(cells[22]['sources'][0]['line'],'n8')
        self.assertEqual(cells[18]['value'],'$240,000.00')
        self.assertEqual(cells[23]['value'],'$50,000.00')
        self.assertEqual(cells[24]['value'],'$30,000.00')

    def test_only_readable_secured_label_cannot_relabel_loan_numbers_as_income(self):
        values=lines('1234567890','95279148304-5863','Debt consolidation',
                     'Secured Loan','240000','360','6.87','1567.89','Unclear label','50000','30000')
        boxes,_=locate(values)
        self.assertNotIn(23,boxes)
        self.assertNotIn(24,boxes)

    def test_label_ocr_zero_does_not_block_numeric_fields_or_rewrite_label(self):
        values=financial_lines('240000','360','6.87','1567.89')
        values[-3]['text']='SecuredL0an'
        cells=sheet_data(state_for(values))[0]['cells']
        self.assertEqual(cells[18]['value'],'$240,000.00')
        self.assertEqual(cells[22]['value'],'SecuredL0an')

    def test_unreadable_label_does_not_lose_clean_product_boundary(self):
        text='95279148304-5863\nDebt consolidation\nFannie Mae Mortgage\n240000\n360\n6.87\n1567.89\nSecueud Loan 50000\n30000\n'
        spans,_=text_fields(text)
        self.assertEqual(text[slice(*spans[17])].strip(),'Fannie Mae Mortgage')


if __name__=='__main__':unittest.main()
