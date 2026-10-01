import unittest
import numpy as np
from pathlib import Path
from PIL import Image,ImageDraw
from detect_records import blocks,header_crop
from extract_dates_postal import locate

class DetectionTests(unittest.TestCase):
    def test_header_can_start_below_fixed_window(self):
        im=Image.new('RGB',(120,50),'white');ImageDraw.Draw(im).rectangle((5,20,80,29),fill='black')
        result=header_crop(im)
        self.assertLess(result.height,20)
        self.assertLess(result.convert('L').getextrema()[0],10)

    def test_continuation_page_has_six_blocks_per_column(self):
        path=Path('D:/projects/piXeL/manual/FORM TTYFRD_8AQ159_enc.jpg')
        if not path.exists():self.skipTest('Local sample not present')
        result=blocks(Image.open(path))
        self.assertEqual(len(result),12)
        self.assertTrue(result[-1]['open_bottom'])
        self.assertGreater(result[-1]['box'][3],1100)

    def test_postal_and_numeric_date(self):
        text='1802603504 Lid/B888/6677-e6-10088346\nTown16258 03/14/1950\n95279148344-7282'
        spans,_=locate(text)
        self.assertEqual(text[slice(*spans[8])],'16258')
        self.assertEqual(text[slice(*spans[9])],'03/14/1950')

    def test_open_bottom_preserves_final_text_row(self):
        # Borders end before the final text row, as in the continuation sample.
        image=Image.new('RGB',(600,300),'white');draw=ImageDraw.Draw(image)
        for left,right in ((10,290),(310,590)):
            draw.line((left,10,left,250),fill='black',width=2)
            draw.line((right,10,right,250),fill='black',width=2)
            draw.line((left,10,right,10),fill='black',width=2)
            draw.rectangle((left+20,250,left+40,260),fill='black')
        detected=blocks(image)
        self.assertEqual(len(detected),2)
        for block in detected:
            self.assertTrue(block['open_bottom'])
            self.assertGreater(block['box'][3],260)
            crop=np.asarray(image.crop(block['box']).convert('L'))
            self.assertEqual(int((crop<160).sum()),231)

    def test_ambiguous_dates_stay_unresolved(self):
        spans,_=locate('1802603504\n03/14/1950 04/15/1951\n95279148344-7282')
        self.assertFalse(spans)

if __name__=='__main__':unittest.main()
