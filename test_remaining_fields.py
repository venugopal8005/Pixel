import unittest
from extract_remaining_fields import locate_remaining

class RemainingFieldsTests(unittest.TestCase):
    def test_multiword_locality_keeps_separate_short_line(self):
        text='1802603506\nLid/B888/6677-e6-10025466Mrs\nName\n42884 Street\nSouth\nLebanon\n45065 Thursday,29 September,1960\n95279148326-0122'
        spans=locate_remaining(text)
        self.assertEqual(text[slice(*spans[7])],'South\nLebanon')
        self.assertEqual(text[slice(*spans[6])].strip(),'42884 Street')

    def test_merged_address_locality_is_unresolved(self):
        text='1802603506\nLid/B888/6677-e6-10025466\n42884 StreetTown45065 Thursday,29 September,1960\n95279148326-0122'
        self.assertNotIn(7,locate_remaining(text))

    def test_occupation_does_not_normalize_response(self):
        text='N.I.No#IX0/k368-T4-8554715\nOddSpelt Job\nYeas\nEXAMPLE CORP\nMastercard\nGiood'
        spans=locate_remaining(text)
        self.assertEqual(text[slice(*spans[32])],'Yeas')
        self.assertEqual(text[slice(*spans[31])].strip(),'OddSpelt Job')
        self.assertEqual(text[slice(*spans[33])].strip(),'EXAMPLE CORP')

    def test_multiple_response_candidates_remain_unresolved(self):
        text='N.I.No#IX0/k368-T4-8554715 Job No Yes BANK Good'
        self.assertNotIn(32,locate_remaining(text))

    def test_corrupt_amount_is_not_partial_number_boundary(self):
        text='95279148344-7282 Secured Loan 1030660 77Z99S EXAMPLE LLC Mr Smith U.T.R.No.#202/UGdR-VI-3661562'
        self.assertNotIn(26,locate_remaining(text))

    def test_organization_and_person_are_separated(self):
        text='95279148344-7282 Secured Loan 1030660 772995 EXAMPLE LLC Mr Smith U.T.R.No.#202/UGdR-VI-3661562'
        spans=locate_remaining(text)
        self.assertEqual(text[slice(*spans[26])].strip(),'EXAMPLE LLC')
        self.assertEqual(text[slice(*spans[27])],'Mr')
        self.assertEqual(text[slice(*spans[28])],'Smith')

if __name__=='__main__':unittest.main()
