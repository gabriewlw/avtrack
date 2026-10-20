"""TV inventory Last checked updates when missing required details are completed."""
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
    row=app.save_equipment(dict(inventory_id=inventory['id'],brand='',model='X',notes='Long notes. '*60,custom_values=dict(deck_6='1',deck_2_port='2',deck_2_stbd='0')))
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
            assert 'Serial number' not in page.locator('#equipment-table thead').inner_text()
            assert 'record check' not in page.locator('#equipment-table thead').inner_text().lower()
            assert 'last checked' in page.locator('#equipment-table thead').inner_text().lower()
            assert page.locator('#equipment-table tbody tr').first.locator('td').count()==page.locator('#equipment-table thead th').count()
            check=page.locator('.equipment-last-checked')
            assert check.inner_text()=='Not checked'
            assert check.locator('button').count()==0
            page.locator('.equipment-edit-action').click()
            page.locator('#equipment-form [name=brand]').select_option('LG')
            page.locator('#save-equipment').click()
            page.locator('#equipment-dialog').wait_for(state='hidden')
            assert app.equipment_inventory(inventory['id'])[0]['inventory_checked_at'].endswith('Z')
            assert app.equipment_inventory(inventory['id'])[0]['last_checked_at'] is None
            assert check.inner_text()!='Not checked'
            assert 'Last checked:' in check.get_attribute('title')
            page.reload();page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            assert page.locator('.equipment-last-checked').inner_text()!='Not checked'
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('TV automatic completion date, date persistence, no serial field and row alignment passed.')
