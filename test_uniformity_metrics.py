import unittest
import numpy as np
from test_glyph_uniformity import evaluate, split_glyphs


class UniformityChecks(unittest.TestCase):
    def test_excludes_same_record_even_when_identical(self):
        def s(name, record, char, vector):
            return dict(id=name, record=record, char=char, provenance='checked', feature=np.array(vector,dtype=np.float32))
        result=evaluate([s('target','a','1',[1,0]),s('same-record','a','1',[1,0]),
                         s('external-same','b','1',[0,1]),s('external-other','c','2',[1,0])])
        target=next(d for d in result['details'] if d['sample']=='target')
        self.assertEqual(target['neighbor'],'external-other')
        self.assertFalse(target['correct'])

    def test_no_independent_same_class_is_not_scored(self):
        samples=[dict(id=str(i),record=str(i),char=str(i),provenance='checked',feature=np.array([1.,0.])) for i in range(2)]
        self.assertEqual(evaluate(samples)['tested'],0)

    def test_count_mismatch_rejected_instead_of_forced(self):
        class ArrayImage:
            def convert(self, mode):return pixels
        pixels=np.full((10,20),255,dtype=np.uint8)
        pixels[2:8,2:5]=0
        img=ArrayImage()
        glyphs, reason=split_glyphs(img,'12',170)
        self.assertIsNone(glyphs)
        self.assertIn('found 1',reason)


if __name__=='__main__':unittest.main()
