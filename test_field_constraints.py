import copy
import unittest

import review_app as app
from field_constraints import RULES, constrain_segment
from pilot_rules import HEADERS, apply_rule
from test_sheet_review import fixture


def selected_field(field, text, options, index=0, category='ambiguous'):
    state = fixture()
    state.update(schema_version=2, created_date='10/02/2026')
    record = state['records'][0]
    segments = [dict(id=f't{i}', text=c, options=options if i == index else [c],
                     category=category if i == index else 'single', x=i*9,
                     reason='OCR alternatives') for i, c in enumerate(text)]
    record['lines'].append(dict(id='test-line', page='source.jpg', image='line-3.png',
        segments=segments, box=[[0,0],[len(text)*9,0],[len(text)*9,18],[0,18]]))
    state['field_regions'] = {f'record-1:{field}': {'first':'t0','last':f't{len(text)-1}'}}
    return state


class FieldConstraintTests(unittest.TestCase):
    def cell(self, state, field):
        return app.sheet_data(state)[0]['cells'][field]

    def test_rulebook_covers_all_columns_without_invented_lengths(self):
        self.assertEqual([r['name'] for r in RULES.values()], HEADERS)
        self.assertTrue(all(r['min_length'] is None and r['max_length'] is None for r in RULES.values()))

    def test_numeric_alternative_is_used_in_ui_and_export_without_changing_source(self):
        state=selected_field(8,'O0123',['O','0']);before=copy.deepcopy(state)
        cell=self.cell(state,8)
        self.assertEqual(cell['value'],'00123');self.assertEqual(cell['plain'],'00123')
        self.assertEqual(cell['pending'],0);self.assertEqual(cell['status'],'read')
        self.assertFalse(cell['manual']);self.assertEqual(cell['raw_value'],'[O/0]0123')
        self.assertEqual(cell['rule_segments']['t0']['options'],['0'])
        data=app.export_data(state)
        self.assertEqual(data['rows'][0][8],'00123')
        self.assertIn('[O/0]0123',[r[3] for r in data['lines']])
        self.assertTrue(any(r[2]=='Field-rule alternative filter' for r in data['review']))
        self.assertEqual(state,before)

    def test_two_valid_digits_stay_ambiguous_and_unknown_stays_unknown(self):
        for options,category,expected in ((['1','7'],'ambiguous','[1/7]0123'),(['O','0'],'unrecognized','[?]0123'),(['O','Q'],'ambiguous','[O/Q]0123')):
            state=selected_field(8,options[0]+'0123',options,category=category)
            cell=self.cell(state,8)
            self.assertEqual(cell['value'],expected);self.assertEqual(cell['pending'],1)
            self.assertEqual(cell['status'],'uncertain')

    def test_plain_wrong_letter_is_flagged_not_silently_replaced(self):
        cell=self.cell(selected_field(8,'O0123',['O'],category='single'),8)
        self.assertEqual(cell['value'],'O0123');self.assertTrue(cell['rule_issues'])

    def test_text_fields_filter_digits_but_mixed_identifiers_do_not(self):
        city=self.cell(selected_field(7,'0akland',['0','O']),7)
        self.assertEqual(city['value'],'Oakland');self.assertEqual(city['pending'],0)
        for field in (3,6,5,11,28,29,30):
            cell=self.cell(selected_field(field,'B123',['B','8']),field)
            self.assertIn('[B/8]',cell['value']);self.assertEqual(cell['pending'],1)

    def test_narrow_three_candidates_and_keep_deletion_alternative(self):
        cell=self.cell(selected_field(8,'10123',['1','7','I']),8)
        self.assertEqual(cell['value'],'[1/7]0123');self.assertEqual(cell['pending'],1)
        cell=self.cell(selected_field(8,'00123',['','0','O']),8)
        self.assertEqual(cell['value'],'[∅/0]0123');self.assertEqual(cell['pending'],1)
        cell=self.cell(selected_field(8,'O0123',['','O']),8)
        self.assertEqual(cell['value'],'[∅/O]0123');self.assertEqual(cell['pending'],1)

    def test_human_overrides_take_priority_and_reset_restores_rule_projection(self):
        state=selected_field(8,'O0123',['O','0']);state['decisions']['t0']='O'
        cell=self.cell(state,8)
        self.assertEqual(cell['value'],'O0123');self.assertFalse(cell['rule_actions']);self.assertTrue(cell['rule_issues'])
        state['field_decisions']={'record-1:8':'O0123'}
        self.assertEqual(self.cell(state,8)['status'],'confirmed')
        self.assertEqual(self.cell(state,8)['value'],'O0123')
        state['decisions'].clear();state['field_decisions'].clear()
        self.assertEqual(self.cell(state,8)['value'],'00123')

    def test_proposed_crop_cannot_become_a_mapped_value_via_a_rule(self):
        state=selected_field(8,'O0123',['O','0']);state['field_regions'].clear()
        row=app.sheet_data(state)[0];cell=row['cells'][8]
        self.assertEqual(cell['value'],'[?]');self.assertTrue(cell['candidate'])
        self.assertFalse(cell['rule_actions']);self.assertIn(8,row['field_coverage']['missing_fields'])

    def test_coverage_does_not_count_generated_or_manual_unlocated_values(self):
        state=fixture();state['schema_version']=2
        state['field_decisions']={'record-1:8':'12345'}
        coverage=app.sheet_data(state)[0]['field_coverage']
        self.assertEqual(coverage['expected'],32);self.assertFalse(coverage['all_located'])
        self.assertIn(8,coverage['missing_fields']);self.assertNotIn(0,coverage['missing_fields'])

    def test_currency_percent_months_and_numeric_date(self):
        for field,text,options,index,expected in (
            (18,'9O3210',['O','0'],1,'$903,210.00'),
            (19,'42O Months',['O','0'],2,'420 Months'),
            (20,'6.8I',['I','1'],3,'6.81%'),
            (9,'O1/08/1942',['O','0'],0,'01/08/1942')):
            cell=self.cell(selected_field(field,text,options,index),field)
            self.assertEqual(cell['value'],expected);self.assertEqual(cell['pending'],0)

    def test_literal_spelling_name_case_and_conflicting_property_length(self):
        self.assertEqual(apply_rule(4,'aLFRED bOB')[0],'Alfred bob')
        self.assertEqual(apply_rule(5,'swapna*GUDISI.2smith')[0],'Swapna*Gudisi.2Smith')
        self.assertEqual(apply_rule(16,'Debt consalidation')[0],'Debt consalidation')
        value,issues=apply_rule(15,'95279148317-2465')
        self.assertEqual(value,'95279148317-2465');self.assertTrue(issues)

    def test_segment_rule_does_not_convert_unknown_or_user_decision(self):
        seg=dict(id='s',text='O',options=['O','0'],category='unrecognized')
        self.assertIsNone(constrain_segment(8,seg,{}))
        seg['category']='ambiguous'
        self.assertIsNone(constrain_segment(8,seg,{'s':'O'}))


if __name__=='__main__':unittest.main()
