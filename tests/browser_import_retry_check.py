from browser_helpers import open_workspace
"""A failed row write or final checkpoint stays retryable instead of freezing."""
import shutil,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from openpyxl import Workbook
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'test.sqlite3'
    with app.connect() as con:con.commit()
    book=Workbook();sheet=book.active;sheet.append(['Channel Name','Multicast IP','Port','Venue']);sheet.append(['Retry channel','239.30.0.1',1301,'Headend'])
    path=Path(tmp)/'retry.xlsx';book.save(path)
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            failures={'row':True,'checkpoint':True}
            def interrupt(route):
                request=route.request
                if request.method=='POST' and request.url.endswith('/rows') and failures['row']:
                    failures['row']=False;route.abort('failed');return
                if request.method=='PUT' and '/api/import-sessions/' in request.url and not request.url.endswith('/reconciliation') and failures['checkpoint'] and not failures['row']:
                    failures['checkpoint']=False;route.abort('failed');return
                route.continue_()
            page.route('**/api/import-sessions/**',interrupt)
            page.goto(f'http://127.0.0.1:{server.server_port}/');page.wait_for_function("() => !document.getElementById('refresh').disabled")
            open_workspace(page, 'iptv-tab');page.locator('#import').click();page.locator('#upload-paste-inventory').click();page.locator('#import-file').set_input_files(str(path))
            page.locator('#spreadsheet-dialog').wait_for(state='visible');page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            page.locator('#confirm-import').click();page.locator('#inventory-import-review').wait_for(state='visible')
            page.locator('#inventory-import-review-save').click()
            page.wait_for_function("() => document.querySelector('#inventory-import-review-rows .batch-row-result').classList.contains('error')")
            assert not page.locator('#inventory-import-review-save').is_disabled()
            assert page.locator('#inventory-import-review-close').is_enabled()
            assert not app.inventory()
            page.locator('#inventory-import-review-save').click()
            page.locator('#inventory-import-review').wait_for(state='hidden',timeout=5000)
            page.locator('#spreadsheet-dialog').wait_for(state='visible',timeout=5000)
            assert not page.locator('#spreadsheet-error').is_hidden()
            assert len(app.inventory())==1
            page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            page.locator('#confirm-import').click();page.locator('#import-summary-panel').wait_for(state='visible',timeout=5000)
            assert page.locator('#import-summary-title').inner_text()=='Import complete'
            assert len(app.inventory())==1
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('Interrupted row writes and final checkpoints remained safe and retryable.')
