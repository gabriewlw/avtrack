"""Compact inventory notes open a floating editor with Apply, Cancel and conflict handling."""
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
            notes=page.get_by_role('button',name='Edit notes for X',exact=True)
            assert notes.inner_text()=='View'
            assert 'Long notes.' not in page.locator('#equipment-rows').inner_text()
            assert page.evaluate("() => document.querySelector('#equipment-table').getBoundingClientRect().width<=document.querySelector('.equipment-table-wrap').clientWidth+1")
            assert notes.locator('..').locator('..').bounding_box()['width']<85
            notes.click();page.locator('#equipment-notes-dialog').wait_for(state='visible')
            assert page.locator('#equipment-notes-text').input_value()==row['notes']
            page.locator('#equipment-notes-text').fill('Discard this');page.locator('#cancel-equipment-notes').click()
            assert app.equipment_inventory(inventory['id'])[0]['notes']==row['notes']
            notes.click();page.locator('#equipment-notes-text').fill('Edited notes\nSecond line')
            page.locator('#apply-equipment-notes').click();page.locator('#equipment-notes-dialog').wait_for(state='hidden')
            assert app.equipment_inventory(inventory['id'])[0]['notes']=='Edited notes\nSecond line'
            assert app.equipment_inventory(inventory['id'])[0]['quantity']==3
            page.locator('#equipment-search').fill('Second line');assert page.locator('#equipment-rows tr').count()==1
            page.locator('#equipment-search').fill('');notes.click()
            app.set_equipment_notes(row['id'],dict(inventory_id=inventory['id'],notes='Changed elsewhere',original_notes='Edited notes\nSecond line'))
            page.locator('#equipment-notes-text').fill('My draft');page.locator('#apply-equipment-notes').click()
            page.locator('#equipment-notes-error').wait_for(state='visible')
            page.wait_for_function("() => !document.getElementById('apply-equipment-notes').disabled")
            assert 'Notes changed' in page.locator('#equipment-notes-error').inner_text()
            assert page.locator('#equipment-notes-text').input_value()=='My draft'
            assert app.equipment_inventory(inventory['id'])[0]['notes']=='Changed elsewhere'
            page.locator('#cancel-equipment-notes').click();notes.click()
            assert page.locator('#equipment-notes-text').input_value()=='Changed elsewhere'
            page.locator('#equipment-notes-text').fill('');page.locator('#apply-equipment-notes').click()
            page.locator('#equipment-notes-dialog').wait_for(state='hidden')
            assert page.get_by_role('button',name='Add notes for X',exact=True).inner_text()=='Add'
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('Compact notes, floating editor, Apply/Cancel, search, multiline preservation and conflict handling passed.')
