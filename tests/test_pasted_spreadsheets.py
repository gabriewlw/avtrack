"""Clipboard tables preserve blank cells, quoted notes and readable headers."""
import base64
import unittest
from spreadsheets import preview


def pasted(text,**extra):
    return preview(dict(filename='Pasted spreadsheet.csv',content=base64.b64encode(text.encode()).decode(),pasted=True,**extra))

class PastedSpreadsheetTests(unittest.TestCase):
    def test_pasted_headings_are_all_available_for_setup(self):
        result=pasted('Device ID\tModel\tO.O\nABC-1\tX\tYes',delimiter='\t')
        self.assertEqual(result['headers'],['Device ID','Model','O.O'])
        self.assertEqual(result['ignored_columns'],[])

    def test_exact_message_table(self):
        result=pasted('''| Description | Model | Deck 6 Locker | Deck 2 Starboard | Deck 2 Port | Total Count | Notes Reamarks |
| --- | --- | --- | --- | --- | --- | --- |
| 24" TV LG | 24LV760M-UA | 8 | 0 | 0 | 8 | Brand New |
| 32" SAMSUNG\\* | HJ69oF | 0 | 0 | 7 | 7 | Needs clone file |
| | | | | | | |
| 43" TV LG | 43UM782VOUC | 0 | 0 | 3 | 2 | Brand New |
''')
        self.assertEqual(result['headers'][0],'Description')
        self.assertEqual(len(result['rows']),3)
        self.assertEqual(result['rows'][1][0],'32" SAMSUNG*')
        self.assertEqual(result['rows'][-1][4:6],['3','2'])
        self.assertEqual(result['row_numbers'],[2,3,5])

    def test_escaped_pipe_and_optional_outer_pipes(self):
        result=pasted('Model | Notes\n:--- | ---:\nX | Used \\| tested\n')
        self.assertEqual(result['rows'],[['X','Used | tested']])

    def test_excel_tabs_quoted_multiline_and_empty_cells(self):
        result=pasted('Model\tBrand\tNotes\nX\t\t"Used, tested\nand ready"\n',delimiter='\t')
        self.assertEqual(result['rows'],[['X','','Used, tested\nand ready']])

    def test_csv_quotes_and_untrusted_separator(self):
        self.assertEqual(pasted('Model,Notes\nX,"Used, tested"\n')['rows'],[['X','Used, tested']])
        with self.assertRaises(ValueError):pasted('Model,Notes\nX,Used\n',delimiter='bad')
