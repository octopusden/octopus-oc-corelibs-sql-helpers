# -*- coding: utf-8-*-
# unit-tests for str_decoder

import unittest
from oc_sql_helpers import str_decoder


class StrDecoderTest(unittest.TestCase):
    def test_decode_to_str(self):
        self.assertEqual("Ивпаф\nЖЭä", str_decoder.decode_to_str("Ивпаф\nЖЭä"))
        self.assertEqual("Ивпаф\nЖЭä", str_decoder.decode_to_str(
            b'\xd0\x98\xd0\xb2\xd0\xbf\xd0\xb0\xd1\x84\n\xd0\x96\xd0\xad\xc3\xa4'))  # encoded "Ивпаф\nЖЭä"
        self.assertEqual("Tässä\n\tYhteydessä", str_decoder.decode_to_str("Tässä\n\tYhteydessä"))
        self.assertEqual("Tässä\n\tYhteydessä", str_decoder.decode_to_str(
            b'T\xe4ss\xe4\n\tYhteydess\xe4')) # encoded "Tässä\n\tYhteydessä"
