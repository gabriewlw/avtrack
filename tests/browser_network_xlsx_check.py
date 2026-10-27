from browser_helpers import open_workspace, open_import_settings, set_import_confirmation, open_import_matching, start_import_review, choose_new_inventory_import
"""IPTV and AV Device XLSX imports complete their shared batch review."""
import shutil,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from openpyxl import Workbook
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'test.sqlite3'
    with app.connect() as con:con.commit()
    files=[]
    for target in ('iptv','device'):
        book=Workbook();sheet=book.active;sheet.title='Import'
        if target=='iptv':
            sheet.append(['Channel Name','Multicast IP','Port','Venue','Notes'])
            sheet.append(['Crew TV','239.1.2.3',1234,'Broadcast Center','Test channel'])
            sheet.append(['News TV','239.1.2.4',1234,'Broadcast Center',''])
        else:
            sheet.append(['Device Name','IP Address','Venue','VLAN','Notes'])
            sheet.append(['Switcher','10.1.2.3','Broadcast Center',50,'Test device'])
        path=Path(tmp)/(target+'.xlsx');book.save(path);files.append((target,path))
    with app.connect() as connection:connection.commit()
    server = app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.wait_for_function("() => !document.getElementById('refresh').disabled")
            for target,path in files:
                open_workspace(page, 'iptv-tab' if target=='iptv' else 'device-tab')
                page.locator('#import').click();page.locator('#upload-paste-inventory').click()
                page.locator('#import-file').set_input_files(str(path))
                open_import_matching(page)
                page.locator('#spreadsheet-dialog:visible, #paste-layout-dialog:visible').first.wait_for()
                page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
                assert page.locator('#map-name').input_value()=='0'
                assert page.locator('#map-ip').input_value()=='1'
                start_import_review(page);page.locator('#inventory-import-review').wait_for(state='visible')
                expected=2 if target=='iptv' else 1
                assert page.locator('#inventory-import-review-rows tr').count()==expected
                page.locator('#inventory-import-review-save').click()
                page.locator('#inventory-import-review').wait_for(state='hidden',timeout=5000)
                page.locator('#import-summary-panel').wait_for(state='visible',timeout=5000)
                assert page.locator('#import-summary-title').inner_text()=='Import complete'
                page.locator('#close-import-summary').click()
            records=app.inventory()
            assert len([row for row in records if row['record_type']=='iptv'])==2
            assert len([row for row in records if row['record_type']=='device'])==1
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('IPTV and AV Device XLSX imports completed batch review without freezing.')
