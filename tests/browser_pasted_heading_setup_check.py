from browser_helpers import open_workspace, open_import_settings, set_import_confirmation, open_import_matching, start_import_review, choose_new_inventory_import
"""Each pasted heading gets an editable field and import confirmation settings."""
import sys,tempfile,threading,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'test.sqlite3'
    with app.connect() as connection:connection.commit()
    server = app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/inventory')
            page.wait_for_function("() => !document.getElementById('refresh').disabled")
            page.wait_for_function("() => !document.getElementById('new-equipment-inventory').disabled")
            page.locator('#new-equipment-inventory').click()
            page.locator('#equipment-inventory-name').fill('Custom signage')
            page.locator('#equipment-template').select_option('custom')
            page.locator('#save-equipment-inventory').click()
            choose_new_inventory_import(page)
            assert page.locator('#inventory-columns-dialog').is_hidden()
            inventory=next(row for row in app.equipment_inventories() if row['name']=='Custom signage')
            text='Model\tOrientation\tLocation\nM1\tVertical\tLobby\nM2\tHorizontal\tLobby'
            page.locator('#paste-inventory-text').fill(text)
            page.locator('#continue-paste-inventory').click()
            page.wait_for_function("() => document.getElementById('paste-location-dialog').open || document.getElementById('paste-layout-dialog').open")
            if page.locator('#paste-location-dialog').is_visible():
                page.locator('#paste-batch-location').fill('Lobby');page.locator('#continue-paste-location').click()
            page.wait_for_function("() => !document.getElementById('continue-paste-layout').disabled")
            assert all(label in page.locator('#paste-layout-head').inner_text() for label in ['Model','Orientation','Location']), page.locator('#paste-layout-head').inner_text()
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
            page.locator('#paste-layout-dialog').wait_for(state='visible')
            page.wait_for_function("() => !document.getElementById('paste-start-review').disabled")
            assert page.locator('#spreadsheet-dialog').is_hidden()
            assert page.locator('#map-model').input_value()=='0'
            orientation_key=page.evaluate("()=>spreadsheetInventory.layout.columns.find(column=>column.label==='Orientation').key")
            assert page.locator('#map-'+orientation_key).input_value()=='1'
            saved=next(row for row in app.equipment_inventories() if row['id']==inventory['id'])
            assert not next(c for c in saved['layout']['columns'] if c['key']=='model').get('require_confirmation',False)
            assert saved['layout']==inventory['layout']
            assert not app.equipment_inventory(inventory['id'])
            page.locator('#paste-start-review').click();page.locator('#inventory-import-review').wait_for(state='visible')
            saved=next(row for row in app.equipment_inventories() if row['id']==inventory['id'])
            assert saved['layout']==inventory['layout']  # Review is still a draft.
            assert page.evaluate("()=>spreadsheetInventory.layout.columns.find(c=>c.key==='model').require_confirmation")
            assert page.evaluate("()=>spreadsheetInventory.layout.columns.map(c=>c.label)")==['Model','Orientation','Location']
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
            saved=app.equipment_inventory(inventory['id'])
            layout=next(row for row in app.equipment_inventories() if row['id']==inventory['id'])['layout']
            assert next(c for c in layout['columns'] if c['key']=='model')['require_confirmation']
            assert [c['label'] for c in layout['columns']]==['Model','Orientation','Location','Status','Notes']
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('Source headings one at a time, new dropdown/button fields, back navigation, mappings and mandatory per-cell review confirmation passed.')
