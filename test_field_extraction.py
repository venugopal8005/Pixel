import unittest
from extract_fields import locate, number
from extract_reference_codes import find_span

def lines(*values):
    return [dict(text=text,box=[[0,i*20],[400,i*20],[400,i*20+16],[0,i*20+16]]) for i,text in enumerate(values)]

class FieldExtractionTests(unittest.TestCase):
    def test_reference_code_joins_wrapped_suffix(self):
        text='U.T.R.No.#202/UGdR-VI-\n3661562\nN.I.No#IX0/k368-T4-8554715'
        span=find_span(text,29)
        self.assertEqual(text[slice(*span)],'U.T.R.No.#202/UGdR-VI-\n3661562')

    def test_broken_reference_does_not_steal_next_identifier(self):
        text='U.T.R.No.#bad\nN.I.No#IX0/k368-T4-8554715'
        self.assertIsNone(find_span(text,29))

    def test_amount_formatting_is_not_character_repair(self):
        self.assertEqual(number('$903,210.00'),number('903210'))
        self.assertIsNone(number('$9,032,10 .00'))
        self.assertIsNone(number('9O3210'))

    def test_merged_decimals_do_not_create_plausible_fields(self):
        boxes,issues=locate(lines('1802603502','95279148304-5863','24134800','426','5.8624155.88','Secured Loan','6033700','3620220'))
        self.assertTrue(all(f not in boxes for f in (18,19,20,21)))
        self.assertTrue(all(f in issues for f in (18,19,20,21)))

    def test_partial_amount_before_letter_is_not_accepted(self):
        boxes,issues=locate(lines('1802603504','95279148344-7282','5153300','354','3.95','24671.29','Secured Loan','1030660','77Z99SBANK'))
        self.assertIn(23,boxes)
        self.assertNotIn(24,boxes)
        self.assertIn(24,issues)

    def test_separate_numeric_fields_and_id_are_located(self):
        boxes,_=locate(lines('1802603502','Lid/8888/6677-e6-10101738','95279148304-5863','24134800','426','5.8','133807.82','Secured Loan','6033700','3620220'))
        self.assertEqual(set(boxes),{1,3,15,18,19,20,21,23,24})

    def test_missing_anchor_does_not_shift_fields(self):
        boxes,issues=locate(lines('1802603502','24134800','426','5.8','133807.82','Secured Loan','6033700','3620220'))
        self.assertNotIn(18,boxes)
        self.assertIn(18,issues)

if __name__=='__main__':unittest.main()
