import unittest,copy
from field_regions import selected_region
from test_sheet_review import fixture
import review_app as app

class RegionTests(unittest.TestCase):
    def test_missing_field_has_focused_characters_but_no_invented_export(self):
        state=fixture();before=copy.deepcopy(state)
        cell=app.sheet_data(state)[0]['cells'][6]
        self.assertTrue(cell['candidate']);self.assertTrue(cell['sources']);self.assertTrue(cell['segments'])
        self.assertLessEqual(len(cell['sources']),2)
        self.assertEqual(cell['value'],'[?]');self.assertEqual(cell['status'],'unmapped')
        self.assertEqual(app.export_data(state)['rows'][0][6],'[?]');self.assertEqual(state,before)
    def test_selected_characters_drive_cell_crop_and_export(self):
        state=fixture();state['field_regions']={'record-1:6':{'first':'l2s4','last':'l2s7'}}
        cell=app.sheet_data(state)[0]['cells'][6]
        self.assertFalse(cell['candidate']);self.assertEqual(cell['plain'],'B888')
        self.assertEqual(len(cell['segments']),4);self.assertEqual(cell['sources'][0]['image'],'line-2.png')
        state['decisions']['l2s4']='B'
        self.assertEqual(app.export_data(state)['rows'][0][6],'B888')
        self.assertNotIn('Missing field boundary',[r[2] for r in app.export_data(state)['review'] if r[1]=='6'])
    def test_reversed_or_foreign_range_rejected(self):
        record=fixture()['records'][0]
        with self.assertRaises(ValueError):selected_region(record,{'first':'l2s7','last':'l2s4'}, {})
        with self.assertRaises(ValueError):selected_region(record,{'first':'other','last':'l2s4'}, {})
    def test_selected_boundary_does_not_claim_character_confirmation(self):
        state=fixture();state['field_regions']={'record-1:3':{'first':'l2s0','last':'l2s21'}}
        cell=app.sheet_data(state)[0]['cells'][3]
        self.assertEqual(cell['status'],'uncertain');self.assertFalse(cell['manual']);self.assertIn('[B/O]',cell['value'])

if __name__=='__main__':unittest.main()
