"""IPTV imports need main-field choices, never names for unused columns."""
import io
from pathlib import Path
import shutil
import sys
import tempfile
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from openpyxl import Workbook
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'inventory.sqlite3'
    with app.connect():pass
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000});page.set_default_timeout(15000);errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/#iptv');page.locator('#import').wait_for()
            for case,kind in enumerate(('paste','csv','xlsx')):
                rows=[['RADIANCE',str(index+1),name+' '+kind,model,'239.252.4.2','1234',f'239.252.2.{61+case*10+index}','1234',codec]
                      for index,(name,model,codec) in enumerate([('Forward Cam','Axis Q1755',''),('Lido Cam','AXIS P5655-E','H.265'),('CasinoBarTV','IRD DVS #1','H.264')])]
                page.locator('#import').click()
                if kind=='paste':
                    page.locator('#paste-inventory-text').fill('\n'.join('\t'.join(row) for row in rows));page.locator('#continue-paste-inventory').click()
                else:
                    path=Path(tmp)/('channels.'+kind)
                    if kind=='xlsx':
                        book=Workbook()
                        for row in rows:book.active.append(row)
                        book.save(path)
                    else:
                        import csv
                        output=io.StringIO();writer=csv.writer(output);writer.writerows(rows);path.write_text(output.getvalue())
                    with page.expect_file_chooser() as chooser:page.locator('#upload-paste-inventory').click()
                    chooser.value.set_files(str(path))
                page.locator('#iptv-main-columns').wait_for(state='visible')
                assert page.locator('#paste-missing-headings').is_hidden()
                assert page.locator('#paste-heading-inputs input').count()==0
                assert len(app.inventory())==case*3
                page.locator('#iptv-map-name').select_option('2')
                page.locator('#iptv-map-ip').select_option('6')
                page.locator('#iptv-map-port').select_option('7')
                page.locator('#iptv-map-notes').select_option('')
                page.wait_for_function("() => !document.getElementById('paste-start-review').disabled")
                assert rows[0][2] in page.locator('#paste-layout-rows').inner_text()
                if kind=='paste':page.screenshot(path='/tmp/avtrack-iptv-main-columns.png',full_page=True)
                page.locator('#paste-start-review').click();page.locator('#inventory-import-review').wait_for(state='visible')
                page.locator('#inventory-import-review-save').click();page.locator('#import-summary-panel').wait_for(state='visible')
                saved=app.inventory();assert len(saved)==(case+1)*3,saved
                first=next(row for row in saved if row['name']==rows[0][2])
                self_note=next(row for row in saved if row['name']==rows[1][2])
                assert first['ip']==rows[0][6] and first['port']==1234
                assert 'RADIANCE' in first['notes'] and 'Axis Q1755' in first['notes']
                assert 'H.265' in self_note['notes']
                page.locator('#close-import-summary').click()
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('PASS: headerless IPTV paste/CSV/XLSX, first channel retained, chosen main fields, and unnamed extras in Notes')
