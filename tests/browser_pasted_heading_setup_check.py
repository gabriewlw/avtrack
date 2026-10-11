"""Each pasted heading gets an editable field and import confirmation settings."""
import sys,tempfile,threading,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'test.sqlite3'
    inventory=app.save_equipment_inventory({'name':'Custom signage','layout':{'columns':[dict(key='description',label='Description',type='text',filter='none',important=False,options=[]),dict(key='location',label='Location',type='text',filter='none',important=False,options=[])],'primary_search':'description','identifier':'','show_status':False}})
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/inventory')
            page.wait_for_function("() => !document.getElementById('refresh').disabled")
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            page.locator('#equipment-inventory-select').select_option(str(inventory['id']))
            page.wait_for_function("() => document.getElementById('equipment-inventory-title').textContent==='Custom signage' && !document.getElementById('equipment-inventory-select').disabled")
            text='Model\tOrientation\tLocation\nM1\tVertical\tLobby\nM2\tHorizontal\tLobby'
            page.locator('#equipment-paste').click();page.locator('#paste-inventory-text').fill(text)
            page.locator('#continue-paste-inventory').click()
            page.wait_for_function("() => !document.getElementById('continue-paste-layout').disabled")
            page.locator('#continue-paste-layout').click();page.locator('#paste-field-dialog').wait_for(state='visible')
            assert page.locator('#paste-field-title').inner_text()=='Model'
            assert page.locator('#paste-field-progress').inner_text()=='Heading 1 of 3'
            page.locator('#paste-field-type').select_option('select')
            assert page.locator('#paste-field-options').input_value()=='M1\nM2'
            page.locator('#paste-field-confirm').check();page.locator('#next-paste-field').click()
            assert page.locator('#paste-field-title').inner_text()=='Orientation'
            page.locator('#paste-field-type').select_option('buttons')
            page.locator('#next-paste-field').click()
            assert page.locator('#paste-field-title').inner_text()=='Location'
            page.locator('#back-paste-field').click()
            assert page.locator('#paste-field-type').input_value()=='buttons'
            page.locator('#next-paste-field').click();page.locator('#next-paste-field').click()
            page.locator('#spreadsheet-dialog').wait_for(state='visible')
            assert page.locator('#map-field_model').input_value()=='0'
            assert page.locator('#map-field_orientation').input_value()=='1'
            saved=next(row for row in app.equipment_inventories() if row['id']==inventory['id'])
            assert next(c for c in saved['layout']['columns'] if c['key']=='field_model')['require_confirmation']
            assert not app.equipment_inventory(inventory['id'])
            page.locator('#confirm-import').click();page.locator('#inventory-import-review').wait_for(state='visible')
            assert page.locator('#inventory-import-review-rows tr').count()==2
            page.locator('#inventory-import-review-all').check()
            assert page.locator('#inventory-import-review-save').is_disabled()
            page.get_by_label('Confirm Model, row 2',exact=True).check()
            page.get_by_label('Confirm Model, row 3',exact=True).check()
            assert page.locator('#inventory-import-review-save').is_enabled()
            page.get_by_label('Model, row 2',exact=True).select_option('M2')
            assert not page.get_by_label('Confirm Model, row 2',exact=True).is_checked()
            assert page.locator('#inventory-import-review-save').is_disabled()
            page.get_by_label('Model, row 2',exact=True).select_option('M1')
            page.get_by_label('Confirm Model, row 2',exact=True).check()
            page.locator('#inventory-import-review-save').click()
            page.locator('#inventory-import-review').wait_for(state='hidden')
            page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            assert len(app.equipment_inventory(inventory['id']))==2
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('Source headings one at a time, new dropdown/button fields, back navigation, mappings and mandatory per-cell review confirmation passed.')
