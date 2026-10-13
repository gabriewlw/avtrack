"""Import location deletion skips complete/flagged rows with undo and session reset."""
import shutil
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from inventory_profiles import DEFAULT_PROFILE
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temporary:
    app.DB_PATH=Path(temporary)/'inventory.sqlite3'
    inventory=app.save_equipment_inventory({'name':'Spare stock','layout':DEFAULT_PROFILE})
    existing=app.save_equipment({'inventory_id':inventory['id'],'description':'Previously saved','serial_number':'OLD','location':'Locker A'})
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium') or None)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/inventory')
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            page.locator('#equipment-inventory-select').select_option(str(inventory['id']))
            page.wait_for_function("() => document.getElementById('equipment-inventory-title').textContent==='Spare stock' && !document.getElementById('equipment-inventory-select').disabled")
            data=b'Item,Brand,Model,Serial number,Quantity,Location,Notes\nDeleted,Sony,X,DUP,1,Locker A,note\nDeleted,,X,A2,,Locker A,note\nKept,Sony,X,DUP,1,Locker B,note\nKept,,X,B2,2,Locker B,note\nKept,Sony,X,C1,3,Locker C,note\n,,,,,,\n'
            def upload(content=data):
                page.locator('#import-file').set_input_files({'name':'locations.csv','mimeType':'text/csv','buffer':content})
                page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            def delete(name):page.get_by_role('button',name=f'Exclude location {name} and skip its items',exact=True).first.click()
            upload()
            delete('Locker A')
            assert '2 items skipped from excluded locations' in page.locator('#equipment-import-audit').inner_text()
            assert page.locator('#confirm-import').inner_text()=='Apply setup & review 3 rows'
            assert page.locator('#spreadsheet-preview strong').all_text_contents()==['Row 4','Row 5','Row 6']
            assert page.locator('#import-venue-list .choice-button').count()==2
            page.get_by_role('button',name='Restore location Locker A',exact=True).click()
            assert page.locator('#confirm-import').inner_text()=='Apply setup & review 5 rows'
            delete('Locker A')
            page.locator('#confirm-import').click();page.locator('#inventory-import-review').wait_for(state='visible')
            assert page.locator('#inventory-import-review-rows tr').count()==1
            assert page.locator('#inventory-import-review-rows tr').get_attribute('data-source-row')=='5'
            assert 'Locker B' in page.locator('#inventory-import-review-title').inner_text()
            page.get_by_label('Brand, row 5',exact=True).fill('Sony')
            page.get_by_role('checkbox',name='Select row 5',exact=True).check()
            page.locator('#inventory-import-review-save').click()
            page.wait_for_function("() => document.getElementById('inventory-import-review-title').textContent==='Review Locker C'")
            assert 'Unusual location' in page.locator('#inventory-import-review-rows').inner_text()
            page.locator('#inventory-import-review-all').check();page.locator('#inventory-import-review-save').click()
            page.locator('#import-summary-panel').wait_for(state='visible')
            page.wait_for_function("() => document.getElementById('equipment-records').textContent==='4'")
            saved=app.equipment_inventory(inventory['id'])
            assert next(row for row in saved if row['id']==existing['id'])['location']=='Locker A'
            assert {row['serial_number'] for row in saved}=={'OLD','DUP','B2','C1'}
            assert next(row for row in saved if row['serial_number']=='DUP')['location']=='Locker B'
            report=page.locator('#import-summary-groups').inner_text()
            assert 'Locker A' in report and '2 excluded' in report
            page.locator('#close-import-summary').click()
            # Renamed aliases are removed together; all-deleted imports finish without review.
            upload(b'Item,Brand,Model,Serial number,Quantity,Location,Notes\nNew,Sony,X,N1,1,Locker A,note\nNew,Sony,X,N2,1,Locker B,note\n')
            assert page.get_by_role('button',name='Restore location Locker A',exact=True).count()==0
            page.locator('[data-source-location="Locker B"] input').fill('Locker A')
            delete('Locker A')
            assert page.locator('#confirm-import').inner_text()=='Apply setup & review 0 rows'
            page.get_by_role('button',name='Restore location Locker A',exact=True).first.click()
            assert page.locator('#confirm-import').inner_text()=='Apply setup & review 2 rows'
            delete('Locker A')
            page.locator('#confirm-import').click();page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            page.locator('#import-summary-panel').wait_for(state='visible');page.locator('#close-import-summary').click()
            assert len(app.equipment_inventory(inventory['id']))==4
            # A fresh file restores the locations and their items automatically.
            upload(b'Item,Brand,Model,Serial number,Quantity,Location,Notes\nNew,Sony,X,N1,1,Locker A,note\n')
            assert page.locator('#confirm-import').inner_text()=='Apply setup & review 1 rows'
            page.locator('#confirm-import').click();page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            page.wait_for_function("() => document.getElementById('equipment-records').textContent==='5'")
            assert 'N1' in {row['serial_number'] for row in app.equipment_inventory(inventory['id'])}
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('Location deletion, flagged/complete skipping, restore, aliases, row numbers, blank rows, reports and new-file reset passed.')
