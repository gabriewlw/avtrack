from browser_helpers import open_workspace, open_import_settings, set_import_confirmation, open_import_matching, start_import_review, choose_new_inventory_import
"""Paste preview combines matching and table checks without repeated setup screens."""
import json,shutil,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'inventory.sqlite3'
    templates=json.loads((Path(app.__file__).parent/'static/inventory-templates.json').read_text())
    tv=app.save_equipment_inventory(dict(name='Quick TVs',layout=next(t['layout'] for t in templates if t['id']=='tv')))
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
            open_workspace(page, 'device-tab')
            def paste(text,equipment=False):
                page.locator('#equipment-import' if equipment else '#import').click()
                page.locator('#paste-inventory-text').fill(text);page.locator('#continue-paste-inventory').click()
                page.locator('#paste-layout-dialog').wait_for(state='visible')
                page.wait_for_function("() => !document.getElementById('paste-start-review').disabled")
                assert page.locator('#paste-confirmation-dialog').is_hidden()
                assert page.locator('#spreadsheet-dialog').is_hidden()
                assert page.locator('#paste-field-dialog').is_hidden()
                assert page.locator('#header-row').input_value()=='1'
                assert page.locator('#header-row').is_disabled()
                if not page.locator('.import-advanced').evaluate('(node)=>node.open'):
                    page.locator('.import-advanced > summary').click()
            paste('Device Name\tIP Address\tBackup IP\tVenue\tVLAN\tNotes\nSwitcher\t10.2.3.4\t10.2.3.5\tStudio\t50\tReady')
            page.locator('#paste-map-ip').select_option('2')
            assert '10.2.3.5' in page.locator('#paste-layout-rows').inner_text()
            assert page.locator('#map-ip').input_value()=='2'
            set_import_confirmation(page, 'none')
            assert page.locator('#paste-inventory-check-options').is_hidden()
            page.locator('#paste-start-review').click();page.locator('#inventory-import-review').wait_for(state='visible')
            assert page.get_by_label('IP address, row 2',exact=True).input_value()=='10.2.3.5'
            page.locator('#inventory-import-review-save').click();page.locator('#import-summary-panel').wait_for(state='visible')
            assert app.inventory()[0]['confirmation_required']==0
            page.locator('#close-import-summary').click()
            # Reordered headings, omitted fields and new data reuse names, not column indexes.
            paste('Notes\tVLAN\tVenue\tDevice Name\tBackup IP\tIP Address\nNew\t50\tStudio\tSecond\t10.2.3.7\t10.2.3.6')
            assert page.locator('#paste-map-ip').input_value()=='4'
            assert page.locator('#paste-map-name').input_value()=='3'
            assert page.locator('#paste-preview-confirmation').input_value()=='none'
            set_import_confirmation(page, 'ip')
            page.locator('#paste-start-review').click();page.locator('#inventory-import-review').wait_for(state='visible')
            page.locator('#inventory-import-review-save').click();page.locator('#import-summary-panel').wait_for(state='visible')
            assert next(r for r in app.inventory() if r['name']=='Second')['ip']=='10.2.3.7'
            assert next(r for r in app.inventory() if r['name']=='Second')['confirmation_required']==1
            page.locator('#close-import-summary').click();open_workspace(page, 'equipment-tab')
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            page.locator('#equipment-inventory-select').select_option(str(tv['id']))
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            text='Brand\tModel\tDeck 6 Locker\tDeck 2 Port\tDeck 2 Starboard\tNotes\nLG\t24LV760M-UA\t8\t0\t0\tNew'
            paste(text,True)
            assert page.locator('#paste-preview-stock').is_checked()
            assert not page.locator('#paste-preview-record').is_checked()
            # Calculated Total has no source selector; Notes still matches the correct heading.
            assert page.locator('th[data-field-key=notes] #paste-map-notes').count()==1
            before=next(i for i in app.equipment_inventories() if i['id']==tv['id'])
            assert not page.locator('#paste-inventory-check-options').is_visible()
            set_import_confirmation(page, 'storage')
            page.locator('#close-paste-layout').click()
            assert next(i for i in app.equipment_inventories() if i['id']==tv['id'])==before
            assert not app.equipment_inventory(tv['id'])
            paste(text,True)
            assert page.locator('#paste-preview-auto-label').is_hidden()
            assert not page.locator('#paste-inventory-check-options').is_visible()
            set_import_confirmation(page, 'storage')
            Path('work').mkdir(exist_ok=True);page.screenshot(path='work/paste-quick-preview.png')
            page.locator('#paste-start-review').click();page.locator('#inventory-import-review').wait_for(state='visible')
            page.locator('#inventory-import-review-save').click();page.locator('#import-summary-panel').wait_for(state='visible')
            saved=next(i for i in app.equipment_inventories() if i['id']==tv['id'])
            assert saved['layout']['confirmation_mode']=='storage'
            item=app.equipment_inventory(tv['id'])[0]
            assert item['last_checked_at'] is None and not item['item_confirmed']
            assert item['quantity']==8 and item['notes']=='New'
            page.locator('#close-import-summary').click()
            headers=page.locator('#equipment-table thead').inner_text().lower()
            assert 'stock check' not in headers
            assert 'status' in headers and 'last checked' not in headers
            assert page.locator('#equipment-table tbody tr').first.locator('td').count()==page.locator('#equipment-table thead th').count()
            assert not app.equipment_inventory(tv['id'])[0]['inventory_checked_at']
            page.locator('.equipment-status button').click()
            page.wait_for_function("()=>document.querySelector('.equipment-status button').getAttribute('aria-pressed')==='true'")
            assert app.equipment_inventory(tv['id'])[0]['item_confirmed']
            assert app.equipment_inventory(tv['id'])[0]['inventory_checked_at']
            assert not app.equipment_stock_history(item['id'])
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('Direct paste review, named mapping reuse, automatic status dates, cancelled drafts and aligned columns passed.')
