import unittest
from extract_text_fields import locate, split_person, extract

class TextFieldTests(unittest.TestCase):
    def test_merged_postbox_does_not_become_name(self):
        text='1802603504\nLid/B888/6677-e6-10088346MS\nLEOPARD\nIRIKAURINITIpo box 2068 Rd\n95279148344-7282'
        spans,_=locate(text)
        self.assertEqual(text[slice(*spans[5])],'LEOPARD\nIRIKAURINITI')

    def test_title_attached_to_name(self):
        text='Mis..Arachtinggt\nGeraredmvenerx'
        spans=split_person(text,0)
        self.assertEqual(text[slice(*spans[0])],'Mis..')
        self.assertEqual(text[slice(*spans[1])],'Arachtinggt\nGeraredmvenerx')

    def test_unknown_single_name_is_not_invented_split(self):
        self.assertIsNone(split_person('Mergedname',0))

    def test_misspelled_purpose_is_preserved_and_product_separated(self):
        text='95279148344-7282\nDebitcnsoTidationFreddie\nMcec\n5153300\n354\nSecured Loan'
        spans,_=locate(text)
        self.assertEqual(text[slice(*spans[16])].strip(),'DebitcnsoTidation')
        self.assertEqual(text[slice(*spans[17])].strip(),'Freddie\nMcec')

    def test_ambiguous_time_does_not_assign_person_or_property(self):
        text='1802603504\nLid/B888/6677-e6-10088346\n16258 03/14/1950\nJoe night evening detached\n95279148344-7282'
        spans,_=locate(text)
        self.assertTrue(all(f not in spans for f in (10,11,12,14)))

    def test_raw_source_keeps_whitespace(self):
        parts=[dict(image='source.png',lines=[dict(text=t,box=[[0,0],[1,0],[1,1],[0,1]]) for t in ('95279148344-7282','Secured','Loan','Good')])]
        row=next(r for r in extract(parts) if r['field']==22)
        self.assertEqual(row['source_text'],'Secured\nLoan')
        self.assertEqual(row['raw_ocr'],'Secured Loan')
        self.assertEqual(len(row['source_regions']),2)

if __name__=='__main__':unittest.main()
