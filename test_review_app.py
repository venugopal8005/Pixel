import unittest
from review_app import field_export,export_data,folder

class ReviewAppTests(unittest.TestCase):
    def record(self):
        return dict(key='record-1',record_id='1234567890',notes=[],lines=[dict(id='l1',page='page',box=[[0,0],[100,0],[100,20],[0,20]],segments=[dict(id='s1',text='1234567890',options=['1234567890'],category='single')])])
    def test_missing_fields_keep_question_marker(self):
        row,issues=field_export(self.record(),{})
        self.assertEqual(len(row),37);self.assertEqual(row[3],'[?]');self.assertIsNone(row[2]);self.assertIn(3,issues)
    def test_field_override_is_separate_and_wins(self):
        state=dict(records=[self.record()],decisions={},field_decisions={'record-1:3':'user value'})
        result=export_data(state)
        self.assertEqual(result['rows'][0][3],'user value')
        self.assertFalse(any(r[1]=='3' and r[-1]=='Unresolved' for r in result['review']))
        self.assertEqual(state['records'][0]['lines'][0]['segments'][0]['text'],'1234567890')
    def test_job_path_traversal_rejected(self):
        with self.assertRaises(ValueError):folder('../reference')

if __name__=='__main__':unittest.main()
