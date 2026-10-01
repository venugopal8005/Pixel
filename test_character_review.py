import unittest
import numpy as np
from character_review import decode_scores,align_readings,render_segments

class CharacterReviewTests(unittest.TestCase):
    def test_ctc_blank_separates_repeated_characters(self):
        scores=np.array([[.01,.98,.01],[.01,.98,.01],[.98,.01,.01],[.01,.98,.01]])
        self.assertEqual(''.join(r['char'] for r in decode_scores(scores,['blank','i','t'],100)),'ii')
    def test_alternatives_are_from_scores(self):
        result=decode_scores(np.array([[.01,.53,.46]]),['blank','i','t'],100)
        self.assertEqual(result[0]['alternatives'],['i','t'])
    def test_disagreement_is_specific(self):
        tokens=[dict(char=c,score=.99,alternatives=[c],x=i) for i,c in enumerate('Clinton')]
        out=align_readings(tokens,'Cltnton')
        flagged=[s for s in out if s['category']!='single']
        self.assertEqual(len(flagged),1);self.assertEqual(flagged[0]['options'],['i','t'])
    def test_insertion_is_retained(self):
        tokens=[dict(char='a',score=.99,alternatives=['a'],x=0)]
        out=align_readings(tokens,'ab');self.assertEqual(out[-1]['options'],['','b'])
    def test_weak_single_option_is_unknown_not_fake_alternatives(self):
        out=align_readings([dict(char='i',score=.8,alternatives=['i'],x=0)],'i')
        self.assertEqual(out[0]['category'],'unrecognized')
    def test_unknown_and_decision_export(self):
        s=[dict(id='x',text='i',category='ambiguous',options=['i','t']),dict(id='y',text='x',category='unrecognized',options=[])]
        self.assertEqual(render_segments(s,{}),'[i/t][?]')
        self.assertEqual(render_segments(s,{'x':'t','y':''}),'t')

if __name__=='__main__':unittest.main()
