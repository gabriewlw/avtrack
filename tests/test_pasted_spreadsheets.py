"""Clipboard tables preserve blank cells, quoted notes and readable headers."""
import base64
import unittest
from spreadsheets import preview


def pasted(text,**extra):
    return preview(dict(filename='Pasted spreadsheet.csv',content=base64.b64encode(text.encode()).decode(),pasted=True,**extra))

class PastedSpreadsheetTests(unittest.TestCase):
    def test_iptv_headerless_source_keeps_first_channel_without_naming_unused_columns(self):
        text='RADIANCE\t1\tForward Cam\tAxis Q1755\t239.252.4.2\t1234\t239.252.2.61\t1234\t\nRADIANCE\t2\tLido Cam\tAXIS P5655-E\t239.252.4.34\t1234\t239.252.2.62\t1234\tH.265'
        result=pasted(text,delimiter='\t',allow_headerless=True)
        self.assertTrue(result['generated_headers'])
        self.assertEqual(result['headers'],[f'Column {index}' for index in range(1,10)])
        self.assertEqual(result['rows'][0][2],'Forward Cam')
        self.assertEqual(result['rows'][1][8],'H.265')
        self.assertEqual(result['row_numbers'],[1,2])

    def test_iptv_header_mode_can_be_chosen_explicitly(self):
        text='Service\tAddress\tNumber\nBBC News\t239.1.1.1\t1234'
        result=pasted(text,delimiter='\t',allow_headerless=True,header_mode='present')
        self.assertFalse(result['generated_headers'])
        self.assertEqual(len(result['rows']),1)
        result=pasted(text,delimiter='\t',allow_headerless=True,header_mode='absent')
        self.assertTrue(result['generated_headers'])
        self.assertEqual(result['rows'][0],['Service','Address','Number'])

    def test_pasted_headings_are_all_available_for_setup(self):
        result=pasted('Device ID\tModel\tO.O\nABC-1\tX\tYes',delimiter='\t')
        self.assertEqual(result['headers'],['Device ID','Model','O.O'])
        self.assertEqual(result['ignored_columns'],[])

    def test_first_pasted_row_is_always_headings_and_multiword_titles_stay_together(self):
        result=pasted('Asset Reference\tMonitor Model\tSerial Number\tDeck 6 Locker\nModel\tSerial Number\tLocation\tNotes\nA001\tLG 24LV760M-UA\t000123\t8',delimiter='\t',detect_header=True,header_row=2)
        self.assertEqual(result['header_row'],1)
        self.assertEqual(result['headers'],['Asset Reference','Monitor Model','Serial Number','Deck 6 Locker'])
        self.assertEqual(result['rows'][0],['Model','Serial Number','Location','Notes'])
        self.assertEqual(result['rows'][1][2],'000123')

    def test_blank_first_pasted_row_requires_headings(self):
        with self.assertRaisesRegex(ValueError,'first pasted row'):
            pasted('\nModel\tNotes\nX\tTest',delimiter='\t')

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
