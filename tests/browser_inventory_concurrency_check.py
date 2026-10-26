"""Two open inventory tabs cannot silently overwrite each other's saved units."""
import json, shutil, sys, tempfile, threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright, expect

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'concurrent.sqlite3'
    templates=json.loads((Path(app.__file__).parent/'static/inventory-templates.json').read_text())
    tv=app.save_equipment_inventory(dict(name='Replacement stock',layout=next(t['layout'] for t in templates if t['id']=='tv')))
    item=app.save_equipment(dict(inventory_id=tv['id'],brand='LG',model='Test TV',notes='Sealed box',
        custom_values={'deck_6':'4','deck_2_port':'0','deck_2_stbd':'0','unit_status':'New'}))
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium') or None)
            context=browser.new_context(viewport={'width':1440,'height':1000})
            first=context.new_page();second=context.new_page()
            for page in (first,second):
                page.goto(f'http://127.0.0.1:{server.server_port}/inventory')
                page.wait_for_function("()=>!document.getElementById('equipment-inventory-select').disabled")
                page.locator('#equipment-inventory-select').select_option(str(tv['id']))
                page.wait_for_function("()=>document.getElementById('equipment-inventory-title').textContent==='Replacement stock'")
                page.locator(f'#equipment-rows tr[data-item-id="{item["id"]}"]').wait_for()
            first.locator(f'#equipment-rows tr[data-item-id="{item["id"]}"]').get_by_role('button',name='Edit',exact=True).click()
            first.locator('#equipment-dialog').wait_for(state='visible')
            second.locator(f'#equipment-rows tr[data-item-id="{item["id"]}"]').get_by_role('button',name='Used',exact=True).click()
            second.wait_for_function("()=>document.getElementById('equipment-new-tv-units').textContent==='0'")
            first.locator('#equipment-notes').fill('Edit from old tab')
            first.locator('#save-equipment').click()
            expect(first.locator('#equipment-form-error')).to_contain_text('changed in another tab')
            assert first.locator('#equipment-dialog').is_visible()
            saved=app.equipment_inventory(tv['id'])[0]
            assert saved['custom_values']['unit_status']=='Used'
            assert saved['quantity']==4 and saved['notes']=='Sealed box'
            browser.close()
    finally:
        server.shutdown();server.server_close()
print('PASS: stale editor cannot overwrite newer condition, quantity or notes.')
