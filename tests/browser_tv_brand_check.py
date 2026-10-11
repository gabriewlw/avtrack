"""TV brand dropdowns allow LG, Samsung and editable other brands."""
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
    inventory=app.save_equipment_inventory({'name':'Spare TVs','layout':next(t['layout'] for t in templates if t['id']=='tv')})
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
            page.wait_for_function("() => document.getElementById('equipment-inventory-title').textContent==='Spare TVs' && !document.getElementById('equipment-inventory-select').disabled")
            page.locator('#equipment-import').click()
            page.locator('#paste-inventory-text').fill('Brand\tModel\tDeck 6\tDeck 2 Port\tDeck 2 Stbd\tNotes\nLG\tX\t1\t\t0\tSample')
            page.locator('#continue-paste-inventory').click()
            page.locator('#continue-paste-confirmation').click()
            page.wait_for_function("() => !document.getElementById('continue-paste-layout').disabled")
            page.locator('#keep-paste-layout').click();page.locator('#confirm-import').click()
            page.locator('#inventory-import-review').wait_for(state='visible')
            brand=page.get_by_label('Brand, row 2',exact=True)
            assert brand.evaluate('e=>e.tagName')=='SELECT'
            assert 'LG' in brand.locator('option').all_text_contents()
            assert 'Samsung' in brand.locator('option').all_text_contents()
            brand.select_option('__avtrack_other_choice__')
            assert brand.input_value()=='LG'
            page.get_by_label('Other brand',exact=True).fill('Philips')
            page.get_by_role('button',name='Use brand for row 2',exact=True).click()
            assert brand.input_value()=='Philips'
            page.get_by_label('Deck 2 Port, row 2',exact=True).select_option('0')
            page.locator('#inventory-import-review-all').check();page.locator('#inventory-import-review-save').click()
            page.locator('#inventory-import-review').wait_for(state='hidden')
            assert app.equipment_inventory(inventory['id'])[0]['brand']=='Philips'
            page.locator('#equipment-rows .inventory-cell-controls select').first.select_option('Samsung')
            page.wait_for_function("() => document.querySelector('#equipment-rows .inventory-cell-controls select')?.value==='Samsung' && !document.querySelector('#equipment-rows .inventory-cell-controls select').disabled")
            assert app.equipment_inventory(inventory['id'])[0]['brand']=='Samsung'
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('TV import LG/Samsung dropdown, other brand editor, saved custom brand and post-import changes passed.')
