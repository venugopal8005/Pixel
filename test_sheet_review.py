import copy
import unittest
from review_app import field_analysis, sheet_data, export_data


def fixture():
    def line(n,text,ambiguous=None):
        segs=[dict(id=f'l{n}s{i}',text=c,options=[c,'O'] if i==ambiguous else [c],
                   category='ambiguous' if i==ambiguous else 'single',x=i*9,reason='Test evidence') for i,c in enumerate(text)]
        return dict(id=f'l{n}',page='source.jpg',image=f'line-{n}.png',segments=segs,
                    box=[[0,0],[len(text)*9,0],[len(text)*9,18],[0,18]],source_box=[0,n*20,len(text)*9,n*20+18])
    record=dict(key='record-1',record_id='1234567890',notes=[],lines=[line(1,'1234567890',9),line(2,'Lid/B888/6677-e6-1234567',4)])
    return dict(id='a'*32,status='ready',records=[record],decisions={},history=[],pages=[dict(name='source.jpg',file='page-0.png')])


class SheetReviewTests(unittest.TestCase):
    def test_sheet_export_markers_and_source_agree(self):
        state=fixture();cells=sheet_data(state)[0]['cells'];row=export_data(state)['rows'][0]
        self.assertEqual(len(cells),37)
        self.assertEqual([c['value'] for c in cells],row)
        self.assertIn('[0/O]',cells[1]['value'])
        self.assertEqual(cells[3]['sources'][0]['image'],'line-2.png')
        self.assertEqual(cells[3]['pending'],1)
        self.assertEqual(cells[6]['status'],'unmapped')
        self.assertIsNone(cells[2]['value'])

    def test_character_edit_keeps_field_even_if_anchor_changes(self):
        state=fixture();state['decisions']['l2s0']='X'
        cell=sheet_data(state)[0]['cells'][3]
        self.assertTrue(cell['value'].startswith('Xid/'))
        self.assertTrue(cell['sources'])

    def test_longer_replacement_does_not_shift_next_field(self):
        state=fixture();state['decisions']['l1s0']='XX'
        row=export_data(state)['rows'][0]
        self.assertTrue(row[1].startswith('XX234'))
        self.assertTrue(row[3].startswith('Lid/'))
        self.assertEqual(row[0],row[1])

    def test_field_override_and_reset_leave_character_decisions(self):
        state=fixture();state['decisions']['l2s4']='B'
        state['field_decisions']={'record-1:3':'Verified whole field'}
        cell=sheet_data(state)[0]['cells'][3]
        self.assertEqual(cell['value'],'Verified whole field')
        self.assertEqual(cell['status'],'confirmed')
        self.assertTrue(cell['sources'])
        state['field_decisions'].clear()
        self.assertEqual(sheet_data(state)[0]['cells'][3]['value'],'Lid/B888/6677-e6-1234567')

    def test_cross_field_segment_is_not_individually_editable(self):
        state=fixture();line=state['records'][0]['lines'][1]
        line['segments']=[dict(id='span',text='Lid/B888/6677-e6-1234567 Col.',category='single',options=[],x=0)]
        cell=sheet_data(state)[0]['cells'][3]
        self.assertFalse(cell['segments'][0]['editable'])

    def test_reading_sheet_does_not_mutate_saved_state(self):
        state=fixture();before=copy.deepcopy(state);sheet_data(state)
        self.assertEqual(before,state)


if __name__=='__main__':unittest.main()
