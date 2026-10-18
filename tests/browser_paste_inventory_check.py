"""Paste a message table or Excel cells, match fields, review, and import."""
import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temporary:
    app.DB_PATH=Path(temporary)/'inventory.sqlite3'
    templates=json.loads((Path(app.__file__).parent/'static/inventory-templates.json').read_text())
    tv=app.save_equipment_inventory({'name':'Spare TVs','layout':next(t['layout'] for t in templates if t['id']=='tv')})
    parts=app.save_equipment_inventory({'name':'Spare parts','layout':next(t['layout'] for t in templates if t['id']=='spare_parts')})
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium') or None)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/inventory')
            def choose(inventory):
                page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
                page.locator('#equipment-inventory-select').select_option(str(inventory['id']))
                page.wait_for_function('(name)=>document.getElementById("equipment-inventory-title").textContent===name && !document.getElementById("equipment-inventory-select").disabled',arg=inventory['name'])
            def paste(text,location=''):
                page.locator('#equipment-import').click();page.locator('#paste-inventory-dialog').wait_for(state='visible')
                assert page.locator('#continue-paste-inventory').is_disabled()
                page.locator('#paste-inventory-text').fill(text)
                page.locator('#continue-paste-inventory').click()
                if location:
                    page.locator('#paste-location-dialog').wait_for(state='visible')
                    page.locator('#paste-batch-location').fill(location);page.locator('#continue-paste-location').click()
                page.wait_for_function("() => document.getElementById('paste-confirmation-dialog').open || document.getElementById('paste-layout-dialog').open")
                if page.locator('#paste-confirmation-dialog').is_visible():page.locator('#continue-paste-confirmation').click()
                page.locator('#paste-layout-dialog').wait_for(state='visible')
                page.wait_for_function("() => !document.getElementById('continue-paste-layout').disabled")
                assert page.locator('#spreadsheet-dialog').is_hidden()
                assert page.locator('#paste-layout-head th').count()>0
                assert page.locator('#paste-layout-rows tr').count()<=5
                page.locator('#keep-paste-layout').click()
                page.locator('#spreadsheet-dialog').wait_for(state='visible')
                page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            choose(tv)
            paste('''| Description | Model | Deck 6 Locker | Deck 2 Starboard | Deck 2 Port | Deck 4 Limelight | Total Count | Notes Reamarks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 24" TV LG | 24LV760M-UA | 8 | 0 | 0 | 0 | 8 | Brand New |
| 32" TV LED LG | 32LN662VBUC | 7 | 0 | 0 | 0 | 2 | Used |
| 32" TV LG | 32LN662VBUC | 1 | 0 | 0 | 0 | 22 | Brand New |
| 49" LG TV | 49US770NOUA | 0 | 0 | 0 | 0 | 0 | Used |
| 43" TV LG | 43UM782VOUC | 0 | 0 | 3 | 0 | 2 | Brand New |
| 43\'\' TV Samsung | HU8000F | 0 | 0 | 1 | 0 | 1 | Sent for testing |
| 75" TV LG | 75UN75MU6300 | 0 | `1 | 0 | 0 | 1 | Used / not in box |
| 32" SAMSUNG* | HJ69oF | 0 | 0 | 7 | 0 | 7 | Needs clone file |
''')
            assert len(app.equipment_inventory(tv['id']))==0
            assert page.locator('#map-model').input_value()=='1'
            assert page.locator('#map-deck_6').input_value()=='2'
            assert page.locator('#map-deck_2_stbd').input_value()=='3'
            assert page.locator('#map-deck_2_port').input_value()=='4'
            assert page.locator('#map-notes').input_value()=='7'
            assert '1 duplicate-model groups combined' in page.locator('#equipment-import-audit').inner_text()
            assert page.locator('#confirm-import').inner_text()=='Apply setup & review 7 rows'
            assert 'Brand: LG' in page.locator('#spreadsheet-preview').inner_text()
            assert 'Deck 6: 8' in page.locator('#spreadsheet-preview').inner_text()
            page.locator('#confirm-import').click();page.locator('#inventory-import-review').wait_for(state='visible')
            assert len(app.equipment_inventory(tv['id']))==4
            assert page.locator('#inventory-import-review-rows tr').count()==2
            combined=page.locator('tr[data-source-row="3, 4"]')
            assert combined.get_by_label('Deck 6, row 3, 4',exact=True).input_value()=='8'
            assert combined.get_by_label('Total, row 3, 4',exact=True).input_value()=='8'
            assert 'Source row 3: Original Total: 2' in combined.inner_text()
            assert 'Source row 4: Original Total: 22' in combined.inner_text()
            page.locator('#inventory-import-review-all').check();page.locator('#inventory-import-review-save').click()
            page.locator('#inventory-import-review').wait_for(state='hidden')
            page.wait_for_function("() => document.getElementById('equipment-records').textContent==='6'")
            saved=app.equipment_inventory(tv['id']);assert sum(row['quantity'] for row in saved)==28
            model=next(row for row in saved if row['model']=='32LN662VBUC')
            assert 'Used' in model['notes'] and 'Brand New' in model['notes'] and 'Deck 4 Limelight: 0' in model['notes']
            assert model['quantity']==8
            assert next(row for row in saved if row['model']=='HU8000F')['brand']=='Samsung'
            assert next(row for row in saved if row['model']=='75UN75MU6300')['quantity']==1
            assert next(row for row in saved if row['model']=='HJ69oF')['quantity']==7
            page.locator('#close-import-summary').click()
            # Excel tabs feed the same stages, including location deletion.
            choose(parts)
            paste('Description\tBrand\tModel\tSerial Number\tQuantity\tLocation\tNotes\nCable\tSony\tX\tS1\t1\tLocker A\tnote\nCable\tSony\tY\tS2\t1\tLocker B\tnote\n','Locker B')
            page.locator('#confirm-import').click();page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            page.wait_for_function("() => document.getElementById('equipment-records').textContent==='2'")
            assert {row['location'] for row in app.equipment_inventory(parts['id'])}=={'Locker B'}
            page.locator('#import-summary-panel').wait_for(state='visible');page.locator('#close-import-summary').click()
            # Another worksheet appends in the same inventory; its location fills blanks only.
            page.locator('#equipment-import').click();page.locator('#paste-inventory-dialog').wait_for(state='visible')
            page.locator('#paste-inventory-sheet').fill('Locker C worksheet')
            page.locator('#paste-inventory-text').fill('Description\tBrand\tModel\tSerial Number\tQuantity\tLocation\tNotes\nCable\tSony\tZ\tS3\t1\t\tnote\nCable\tSony\tZ\tS4\t1\tLocker D\tnote\n\t\t\t\t\t\t\n')
            page.locator('#continue-paste-inventory').click()
            page.locator('#paste-batch-location').fill('locker b');page.locator('#continue-paste-location').click()
            page.wait_for_function("() => document.getElementById('paste-confirmation-dialog').open || document.getElementById('paste-layout-dialog').open")
            if page.locator('#paste-confirmation-dialog').is_visible():page.locator('#continue-paste-confirmation').click()
            page.locator('#paste-layout-dialog').wait_for(state='visible')
            page.wait_for_function("() => !document.getElementById('continue-paste-layout').disabled")
            assert page.locator('#spreadsheet-dialog').is_hidden()
            assert page.locator('#paste-layout-head th').count()>0
            assert page.locator('#paste-layout-rows tr').count()<=5
            page.locator('#keep-paste-layout').click()
            page.locator('#spreadsheet-dialog').wait_for(state='visible')
            page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            assert page.locator('#confirm-import').inner_text()=='Apply setup & review 2 rows'
            assert 'Locker B' in page.locator('#spreadsheet-preview').inner_text()
            assert 'Locker D' not in page.locator('#spreadsheet-preview').inner_text()
            page.locator('#import-complete-rows').uncheck()
            page.locator('#confirm-import').click();page.locator('#inventory-import-review').wait_for(state='visible')
            assert page.locator('#inventory-import-review-title').inner_text()=='Review Locker B'
            assert page.locator('#inventory-import-review-rows tr').count()==2
            page.locator('#inventory-import-review-all').check();page.locator('#inventory-import-review-save').click()
            page.locator('#import-summary-panel').wait_for(state='visible')
            page.wait_for_function("() => document.getElementById('equipment-records').textContent==='4'")
            saved=app.equipment_inventory(parts['id'])
            assert {row['serial_number'] for row in saved}=={'S1','S2','S3','S4'}
            assert {row['location'] for row in saved}=={'Locker B'}
            assert page.locator('#equipment-location-buttons button').count()==1
            assert 'Source sheet:' not in next(row for row in saved if row['serial_number']=='S3')['notes']
            page.locator('#close-import-summary').click()
            # Repeated stock models can be merged deliberately; quantities with comments stay reviewable.
            page.locator('#equipment-import').click();page.locator('#paste-inventory-dialog').wait_for(state='visible')
            page.locator('#paste-inventory-text').fill('Description\tBrand\tModel\tSerial Number\tQuantity\tLocation\tNotes\nReceiver\tAtlona\tRX-1\t\t2 USED\tLocker E\tFirst\nReceiver\tAtlona\tRX-1\t\t3\tLocker E\tSecond\n')
            page.locator('#continue-paste-inventory').click();page.locator('#paste-batch-location').fill('Locker E');page.locator('#continue-paste-location').click();page.locator('#paste-layout-dialog').wait_for(state='visible')
            page.wait_for_function("() => !document.getElementById('paste-start-review').disabled")
            assert 'Numeric field · 1 value has extra text to review' in page.locator('#paste-field-analysis').inner_text()
            assert not page.locator('#paste-merge-models').is_checked()
            page.locator('#paste-merge-models').check()
            assert '1 item' in page.locator('#paste-preview-counts').inner_text()
            page.locator('#paste-preview-auto').uncheck();page.locator('#paste-start-review').click()
            page.locator('#inventory-import-review').wait_for(state='visible')
            assert page.locator('#inventory-import-review-rows tr').count()==1
            assert page.get_by_label('Qnt, row 2, 3',exact=True).input_value()=='5'
            notes=page.get_by_role('button',name='Edit notes for row 2, 3',exact=True)
            assert all(text in notes.get_attribute('title') for text in ['First','Second','Quantity detail: 2 USED'])
            page.locator('#inventory-import-review-all').check();page.locator('#inventory-import-review-save').click()
            page.locator('#import-summary-panel').wait_for(state='visible')
            merged=next(row for row in app.equipment_inventory(parts['id']) if row['model']=='RX-1')
            assert merged['quantity']==5 and not merged['serial_number']
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('Message tables, Excel tabs, field matching, inferred brands, combined TV models, discrepancies, zero stock and location skipping passed.')
