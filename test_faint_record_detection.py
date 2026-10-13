"""Faint layouts must retain text and continuations without inventing records."""
import unittest
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw
from detect_records import blocks,header_crop
from pilot_rules import adjacent_pages


def faint_page(border=248,ruled=True):
    image=Image.new('RGB',(600,410),'white');draw=ImageDraw.Draw(image)
    if ruled:
        for x in (10,300,590):draw.line((x,10,x,390),fill=(border,)*3)
        for left,right in ((10,300),(300,590)):
            for y in (10,120,270):draw.line((left,y,right,y),fill=(border,)*3)
        draw.line((300,365,590,365),fill=(border,)*3)
    for left in (10,300):
        for y in (25,43,61,155,173,191,320,338):
            for x in range(left+16,left+230,11):draw.rectangle((x,y,x+5,y+10),fill='black')
    return image


class FaintRecordTests(unittest.TestCase):
    def assert_text_retained(self,image,regions):
        dark=np.asarray(image.convert('L'))<160
        retained=np.zeros_like(dark)
        for region in regions:
            x0,y0,x1,y1=region['box'];retained[y0:y1,x0:x1]=True
        self.assertEqual(int((dark&~retained).sum()),0,'Record crops must keep all printed dark pixels')

    def test_faint_borders_keep_variable_height_records_and_open_edges(self):
        for border in (235,248,252):
            with self.subTest(border=border):
                image=faint_page(border);regions=blocks(image)
                self.assertEqual(len(regions),6)
                self.assertEqual([b['column'] for b in regions],[0,0,0,1,1,1])
                self.assertEqual([b['first_in_column'] for b in regions],[True,False,False,True,False,False])
                self.assertEqual([b['open_bottom'] for b in regions],[False,False,True,False,False,False])
                self.assert_text_retained(image,regions)

    def test_unruled_text_and_blank_pages_do_not_get_invented_columns(self):
        for image in (faint_page(ruled=False),Image.new('RGB',(600,410),'white')):
            with self.assertRaises(ValueError):blocks(image)

    def test_id_crop_retains_last_digit_and_excludes_neighboring_field(self):
        image=Image.new('RGB',(180,40),'white');draw=ImageDraw.Draw(image)
        for i in range(10):draw.rectangle((17+i*9,8,22+i*9,17),fill='black')
        draw.rectangle((123,8,127,17),fill='black')
        head=header_crop(image)
        self.assertEqual(int((np.asarray(head.convert('L'))<160).sum()),600)

    def test_double_image_extensions_still_guard_page_order(self):
        self.assertTrue(adjacent_pages('FORM TTYFRD_7AE1_enc.jpg.jpeg','FORM TTYFRD_7AE2_enc.jpg.jpeg'))
        self.assertFalse(adjacent_pages('FORM TTYFRD_7AE1_enc.jpg.jpeg','FORM TTYFRD_7AE3_enc.jpg.jpeg'))
        self.assertFalse(adjacent_pages('FORM TTYFRD_7AE2_enc.jpg.jpeg','FORM TTYFRD_7AE1_enc.jpg.jpeg'))
        self.assertFalse(adjacent_pages('FORM TTYFRD_7AE1_enc.jpg.jpeg','FORM TTYFRD_8AQ2_enc.jpg.jpeg'))

    def test_supplied_faint_pages_keep_all_35_fragments(self):
        paths=[Path.home()/'Downloads'/f'FORM TTYFRD_7AE{i}_enc.jpg.jpeg' for i in (1,2,3)]
        if not all(p.exists() for p in paths):self.skipTest('Local faint-border examples not present')
        for path,count,open_columns in zip(paths,(12,12,11),([0,1],[0,1],[0])):
            with self.subTest(page=path.name):
                with Image.open(path) as image:
                    regions=blocks(image)
                    self.assertEqual(len(regions),count)
                    self.assertEqual([b['column'] for b in regions if b['open_bottom']],open_columns)
                    self.assert_text_retained(image,regions)


if __name__=='__main__':unittest.main()
