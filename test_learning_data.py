import tempfile,unittest
from pathlib import Path
from learning_data import build_examples

class LearningDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name)
        (self.directory/'line.png').write_bytes(b'test image evidence')
        self.state=dict(id='job',decisions={'a':'t'},records=[dict(key='r',lines=[dict(id='l',image='line.png',page='source',segments=[dict(id='a',text='i',category='ambiguous'),dict(id='b',text='n',category='single')])])])
    def tearDown(self):self.tmp.cleanup()
    def test_partial_correction_does_not_label_unreviewed_text(self):
        result=build_examples(self.state,self.directory)
        self.assertIsNone(result['examples'][0]['training_text'])
        self.assertEqual(result['examples'][0]['proposed_text'],'tn')
        self.assertEqual(result['summary']['confirmed_segments'],1)
        self.assertFalse(result['model_updated'])
    def test_fully_reviewed_line_is_candidate(self):
        self.state['decisions']['b']='n'
        result=build_examples(self.state,self.directory)
        self.assertEqual(result['examples'][0]['training_text'],'tn')
        self.assertEqual(len(result['examples'][0]['image_sha256']),64)
    def test_reset_withdraws_example(self):
        self.state['decisions']={}
        self.assertEqual(build_examples(self.state,self.directory)['examples'],[])
    def test_changed_line_invalidates_old_verification(self):
        self.state['verified_lines']={'l':{'text':'old'}}
        self.assertIsNone(build_examples(self.state,self.directory)['examples'][0]['training_text'])

if __name__=='__main__':unittest.main()
