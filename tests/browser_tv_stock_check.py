"""TV stock checks save dates only after explicit confirmation."""
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
    row=app.save_equipment(dict(inventory_id=inventory['id'],brand='LG',model='X',notes='Long notes. '*60,custom_values=dict(deck_6='1',deck_2_port='2',deck_2_stbd='0')))
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
            check=page.get_by_role('button',name='Confirm stock check for X',exact=True)
            assert check.inner_text()=='Never checked'
            check.click();page.locator('#equipment-stock-check-dialog').wait_for(state='visible')
            assert 'Deck 6: 1' in page.locator('#equipment-stock-check-details').inner_text()
            page.locator('#cancel-equipment-stock-check').click()
            assert app.equipment_inventory(inventory['id'])[0]['last_checked_at'] is None
            check.click();page.locator('#save-equipment-stock-check').click()
            page.locator('#equipment-stock-check-dialog').wait_for(state='hidden')
            assert app.equipment_inventory(inventory['id'])[0]['last_checked_at'].endswith('Z')
            assert check.inner_text()!='Never checked'
            assert 'Last stock check:' in check.get_attribute('title')
            assert page.locator('#equipment-table tbody tr').bounding_box()['height']==47
            page.reload();page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            assert page.get_by_role('button',name='Confirm stock check for X',exact=True).inner_text()!='Never checked'
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('TV stock confirmation, cancellation, date persistence, no serial field and row alignment passed.')
