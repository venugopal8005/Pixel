import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from client_rules import format_value,join_parts,physical_break,remarks,property_anchor
from extract_text_fields import split_person
from extract_dates_postal import locate
from detect_records import record_id_blocks
from test_field_constraints import selected_field
import review_app as app


class ClientRulesTests(unittest.TestCase):
    def test_manual_examples(self):
        cases=[(18,'324,57,89,64','$324,578,964.00'),(21,'7898.2589','$7,898.25'),
            (24,'0','$0.00'),(23,'-','-'),(18,'@','@'),(19,'125','125 Months'),
            (20,'2.39875','2.39875%'),(34,'amricn exprss','amricn exprss Credit Card'),
            (34,'CREDIT CARD','CREDIT CARD Credit Card'),(4,'Da,vid','Da,Vid'),
            (5,'Tho2mas','Tho2Mas'),(5,'AlfredY Brunner','Alfred Y Brunner'),
            (4,'davidM','Davidm'),(35,'Godo','Godo'),(8,'000008','000008'),
            (15,'2575-78552','2575-78552'),(29,'U.T.R.No#LN5/005-19624','U.T.R.No#LN5/005-19624'),
            (30,'N.I.No#Kr2VdT54876','N.I.No#Kr2VdT54876')]
        for field,raw,expected in cases:
            with self.subTest(field=field,raw=raw):self.assertEqual(format_value(field,raw),(expected,[]))
    def test_date_examples_preserve_weekdays_years_and_spelling(self):
        for raw,expected,valid in [
            ('Sunday,23/06/1954','Sunday,06/23/1954',True),
            ('Sunday, Jul,21,1972','Sunday, 07/21/1972',True),
            ('Sunday. 05/13/1938','Sunday, 05/13/1938',True),
            ('Sunday 05/13/1938','Sunday 05/13/1938',True),
            ('Sunday,08/24/78','Sunday,08/24/78',True),
            ('sunday,12/30/2058','sunday,12/30/2058',True),
            ('Sudnay,10,24,1948','Sudnay,10/24/1948',False),
            ('Sunday,Augst,12,1978','Sunday,Augst,12,1978',False),
            ('Sunday,04-204-1965','Sunday,04/204/1965',False),
            ('Sunday 05/13//1938','Sunday 05/13//1938',False),
            ('Sunday,11-022-1961','Sunday,11/22/1961',True),
            ('Sunday,015-22-1961','Sunday,015-22-1961',False),
            ('Sunday,08/24/196','Sunday,08/24/196',False),
            ('02*28@1960','02/28/1960',True),
            ('02/30/1960','02/30/1960',False)]:
            value,issues=format_value(9,raw)
            with self.subTest(raw=raw):self.assertEqual(value,expected);self.assertEqual(not issues,valid)
    def test_invalid_values_are_retained(self):
        for field,value in [(8,'000'),(8,'1234567'),(8,'54,87'),(15,'225486654'),
            (15,'45--78'),(29,'U.T.R.NoLN5/005-19624'),(30,'N.I.NoKr2VdT54876')]:
            with self.subTest(value=value):self.assertEqual(format_value(field,value)[0],value);self.assertTrue(format_value(field,value)[1])
    def test_real_line_breaks_not_ocr_box_separators(self):
        def joined(field,a,b,physical=True):return join_parts(field,[dict(text=a),dict(text=' ',line_break=physical),dict(text=b)])
        self.assertEqual(joined(18,'123','456'),'123456')
        self.assertEqual(joined(18,'123','456',False),'123 456')
        self.assertEqual(joined(29,'U.T.R.No#ABC/','1234'),'U.T.R.No#ABC/1234')
        self.assertEqual(joined(6,'Loop-','Avi'),'Loop-Avi')
        self.assertEqual(joined(6,'Loop&','Avi'),'Loop& Avi')
        self.assertEqual(joined(6,'Loop','-Avi'),'Loop -Avi')
        self.assertEqual(joined(6,'Loop[?]','Avi'),'Loop[?] Avi')
        self.assertEqual(joined(4,'Alfred-','Brunner'),'Alfred- Brunner')
        a=dict(page='p',source_box=[0,10,50,25]);b=dict(page='p',source_box=[60,11,100,26])
        self.assertFalse(physical_break(a,b));b['source_box']=[0,30,50,45];self.assertTrue(physical_break(a,b))
    def test_rules_apply_after_manual_crop_without_mutating_evidence(self):
        state=selected_field(18,'9O3210',['O','0'],1);before=copy.deepcopy(state)
        self.assertEqual(app.sheet_data(state)[0]['cells'][18]['value'],'$903,210.00')
        self.assertEqual(app.export_data(state)['rows'][0][18],'$903,210.00');self.assertEqual(state,before)
    def test_remarks_do_not_claim_unmapped_or_unknown_fields_missing(self):
        cells=[dict(field=i,status='unmapped',pending=1) for i in range(37)]
        self.assertEqual(remarks(cells,range(3,13)),'Not Applicable')
        for i in (5,9,11):cells[i].update(status='read',pending=0,validation_issues=['invalid'])
        self.assertEqual(remarks(cells,range(3,13)),'ALN, DOB AND CALN ARE INVALID.')
        cells[11]['validation_issues']=[];cells[12]['source_status']='missing'
        self.assertEqual(remarks(cells,range(3,13)),'ALN AND DOB ARE INVALID AND BTC IS MISSING.')
        cells[11]['source_status']='merge';cells[12]['source_status']='merge'
        self.assertIn('CALN AND BTC ARE MERGE.',remarks(cells,range(3,13)))
    def test_confirmed_na_generates_missing_remark_but_unknown_does_not(self):
        state=selected_field(8,'000',['0'],category='single')
        state['field_decisions']={'record-1:5':'N.A'}
        cells=app.sheet_data(state)[0]['cells']
        self.assertEqual(cells[13]['value'],'ZC IS INVALID AND ALN IS MISSING.')
    def test_variable_property_anchor_and_name_boundaries(self):
        self.assertEqual(property_anchor('Lid/888-1234 text 2575-78552 Debt consolidation loan').group(),'2575-78552')
        for raw,expected in [('DavidThomas',('David','Thomas')),('AlfredY Brunner',('Alfred','Y Brunner')),
                             ('davidM Brunner',('davidM','Brunner')),('Mr AlfredY Brunner',('Mr','AlfredY Brunner'))]:
            spans=split_person(raw,0);self.assertEqual(tuple(raw[slice(*span)] for span in spans),expected)
        self.assertIsNone(split_person('ALFREDBRUNNER',0));self.assertIsNone(split_person('Annie&Jupiter',0))
        spans,_=locate('1802381902 Lid/888\nCity 027 Sunday,08/24/78\n2575-78552 Debt consolidation')
        self.assertIn(8,spans);self.assertIn(9,spans)

    def test_misspelled_existing_loan_requires_four_values_and_stays_literal(self):
        from extract_fields import loan_section
        text='2575-78552 Debt consolidation QGKR\n21660000\n504\n5.05\n103634.97\nSeuredc Loan\nn12274000\n3682200'
        label,values=loan_section(text)
        self.assertEqual(label.group(),'Seuredc Loan');self.assertEqual(len(values),4)
        label,values=loan_section('2575-78552 Debt consolidation 21660000\n504\nSeuredc Loan')
        self.assertIsNone(label);self.assertFalse(values)


class BorderlessTests(unittest.TestCase):
    def fixture(self,columns=1,leading=False,duplicate=False,unknown=False):
        image=Image.new('RGB',(600*columns,500),'white');draw=ImageDraw.Draw(image);ocr=[]
        def add(x,y,text,w=95):
            for gx in range(x,x+w,9):draw.rectangle([gx,y,min(gx+4,x+w),y+12],fill='black')
            ocr.append(([[x,y],[x+w,y],[x+w,y+12],[x,y+12]],text,.99))
        for c in range(columns):
            x=c*600+20
            if leading:add(x,10,'continuation',300)
            for i,y in enumerate((60,280)):
                token='1802381902' if duplicate else str(1802381902+c*2+i)
                if unknown and i==1:token='18O2381903'
                add(x,y,token);add(x+130,y,'Lid/8888/6677-e6-12345678',300)
                add(x,y+40,'1234567890',100) # an amount is not a header
                add(x,y+60,'Secured Loan',200)
                add(x,y+110,'Good',400)
        return image,lambda *a,**k:(ocr,0)
    def test_single_column_two_records_and_all_pixels_preserved(self):
        im,e=self.fixture();found=record_id_blocks(im,e)
        self.assertEqual([b['detected_record_id'] for b in found],['1802381902','1802381903'])
        self.assertEqual(found[0]['box'][1],0);self.assertEqual(found[-1]['box'][3],500)
        self.assertEqual(found[0]['box'][3],found[1]['box'][1])
    def test_two_columns_and_leading_fragments_in_reading_order(self):
        im,e=self.fixture(2,True);found=record_id_blocks(im,e)
        self.assertEqual([b['detected_record_id'] for b in found],[None,'1802381902','1802381903',None,'1802381904','1802381905'])
        self.assertEqual([b['column'] for b in found],[0,0,0,1,1,1])
    def test_duplicate_and_unreadable_ids_retained(self):
        im,e=self.fixture(duplicate=True);self.assertEqual(len(record_id_blocks(im,e)),2)
        im,e=self.fixture(unknown=True);found=record_id_blocks(im,e)
        self.assertEqual(len(found),2);self.assertIsNone(found[1]['detected_record_id'])
    def test_no_anchor_does_not_invent_records_and_cancel_is_checked(self):
        im=Image.new('RGB',(300,300),'white')
        with self.assertRaises(ValueError):record_id_blocks(im,lambda *a,**k:([],0))
        def cancel():raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):record_id_blocks(im,None,cancel)

    def test_outer_frames_do_not_merge_multiple_record_starts(self):
        image,engine=self.fixture(columns=2)
        draw=ImageDraw.Draw(image)
        for left,right in ((2,590),(602,1190)):draw.rectangle([left,2,right,498],outline='black',width=2)
        from detect_records import blocks
        self.assertEqual(len(blocks(image)),2)
        self.assertTrue(all(b['internal_record_rules'] is False for b in blocks(image)))
        def scanner(*args,**kwargs):
            return ([],0) if kwargs.get('use_rec') is False else engine(*args,**kwargs)
        with tempfile.TemporaryDirectory(prefix='pixel-outer-frame-') as directory,patch.object(app,'DATA',Path(directory)):
            state=dict(id='f'*32,status='scanning',records=[],decisions={},history=[],pages=[dict(name='test.jpg',file='page-0.png')])
            app.folder(state['id']).mkdir();image.save(app.folder(state['id'])/'page-0.png')
            with patch('rapidocr_onnxruntime.RapidOCR',return_value=scanner),patch.object(app,'read_header',return_value=(None,'')):
                app.scan(state)
            self.assertEqual(state['status'],'ready')
            self.assertEqual(len(state['records']),4)
            ids=[r['record_id'] for r in state['records'] if r['record_id']!='[?]']
            self.assertEqual(ids,['1802381902','1802381903','1802381904','1802381905'])

if __name__=='__main__':unittest.main()
