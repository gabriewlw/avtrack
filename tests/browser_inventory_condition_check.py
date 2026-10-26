"""Optional status on import, post-import edits, separate counts, shelf notes and screenshots."""
import json
import base64
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
    tv=app.save_equipment_inventory(dict(name='TV replacement stock',layout=next(t['layout'] for t in templates if t['id']=='tv')))
    def row(brand,model,count,status,note):
        return dict(inventory_id=tv['id'],brand=brand,model=model,notes=note,custom_values=dict(deck_6=str(count),deck_2_port='0',deck_2_stbd='0',unit_status=status))
    seed=[row('LG','43UN7300',8,'New','Sealed boxes · Shelf B2'),
          row('LG','43UN7300',3,'Used','Tested and working · Shelf C1'),
          row('Samsung','55AU7000',5,'New','Original packaging · Shelf A1'),
          row('Samsung','55AU7000',2,'Broken','Panel damage · Shelf D3')]
    app.import_equipment(dict(version=1,inventory_id=tv['id'],equipment=seed))
    generic=app.save_equipment_inventory(dict(name='AV spare parts',layout=next(t['layout'] for t in templates if t['id']=='spare_parts')))
    app.save_equipment(dict(inventory_id=generic['id'],brand='Blackmagic',model='Micro Converter',quantity=6,location='AV locker',notes='With power supplies'))
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium') or None)
            page=browser.new_page(viewport={'width':1600,'height':1250});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            origin=f'http://127.0.0.1:{server.server_port}'
            page.goto(origin+'/inventory')
            page.wait_for_function("()=>!document.getElementById('equipment-inventory-select').disabled")
            page.locator('#equipment-inventory-select').select_option(str(tv['id']))
            page.wait_for_function("()=>document.getElementById('equipment-inventory-title').textContent==='TV replacement stock'")
            assert page.locator('#equipment-new-tv-units').inner_text()=='13'
            headers=page.locator('#equipment-table thead').inner_text().lower()
            assert 'status' in headers and 'last checked' not in headers,headers
            # A real CSV import with no Status column remains optional.
            page.locator('#equipment-import').click()
            with page.expect_file_chooser():page.locator('#upload-paste-inventory').click()
            page.locator('#import-file').set_input_files({'name':'tv-batches.csv','mimeType':'text/csv','buffer':b'Brand,Model,Deck 6,Deck 2 Port,Deck 2 Stbd,Notes\nLG,32LM6300,4,0,0,Awaiting inspection\nLG,32LM6300,1,0,0,Separate batch\n'})
            page.locator('#paste-layout-dialog:visible, #spreadsheet-dialog:visible').first.wait_for()
            if page.locator('#paste-layout-dialog').is_visible():
                page.wait_for_function("()=>!document.getElementById('keep-paste-layout').disabled")
                page.locator('#keep-paste-layout').click()
            page.locator('#spreadsheet-dialog').wait_for(state='visible')
            page.wait_for_function("()=>!document.getElementById('confirm-import').disabled")
            assert page.locator('#map-unit_status').input_value()==''
            page.locator('#import-complete-rows').uncheck()
            page.locator('#confirm-import').click()
            page.locator('#inventory-import-review').wait_for(state='visible')
            assert page.locator('#inventory-import-review-rows tr').count()==2
            assert page.locator('#inventory-import-review button[data-value="New"]').count()==2
            page.locator('#inventory-import-review-save').click()
            page.locator('#import-summary-panel').wait_for(state='visible')
            page.locator('#close-import-summary').click()
            page.wait_for_function("()=>document.getElementById('equipment-records').textContent==='6'")
            assert page.locator('#equipment-new-tv-units').inner_text()=='13'
            unknown=page.locator('#equipment-rows tr').filter(has_text='32LM6300').first
            unknown.get_by_role('button',name='New',exact=True).click()
            page.wait_for_function("()=>document.getElementById('equipment-new-tv-units').textContent!=='13'")
            assert sum(r['quantity'] for r in app.equipment_inventory(tv['id']) if r.get('custom_values',{}).get('unit_status')=='New') in (14,17)
            # TVs have no row-level Count shortcut; Add equipment still creates a separate batch.
            assert page.locator('.equipment-add-count').count() == 0
            existing=next(r for r in app.equipment_inventory(tv['id']) if r['model']=='43UN7300' and r['custom_values']['unit_status']=='New')
            page.locator('#add-device').click()
            page.locator('#equipment-dialog').wait_for(state='visible')
            page.locator('#equipment-brand').select_option('LG')
            page.locator('#equipment-model').fill('43UN7300')
            page.locator('#equipment-form').get_by_label('Deck 6',exact=True).select_option('2')
            page.locator('#equipment-form').get_by_role('button',name='New',exact=True).click()
            page.locator('#equipment-notes').fill('Additional sealed stock')
            page.locator('#equipment-shelf').fill('B4')
            page.locator('#save-equipment').click();page.locator('#equipment-dialog').wait_for(state='hidden')
            page.wait_for_function("()=>document.getElementById('equipment-records').textContent==='7'")
            assert len([r for r in app.equipment_inventory(tv['id']) if r['model']=='43UN7300'])==3
            assert any(r['notes']=='Additional sealed stock\nShelf: B4' for r in app.equipment_inventory(tv['id']))
            # New/used/broken stay editable after import and survive reload.
            page.reload();page.wait_for_function("()=>!document.getElementById('equipment-inventory-select').disabled")
            current=next(r for r in app.equipment_inventory(tv['id']) if r['model']=='55AU7000' and r['custom_values']['unit_status']=='New')
            target=page.locator(f'#equipment-rows tr[data-item-id="{current["id"]}"]')
            before=int(page.locator('#equipment-new-tv-units').inner_text())
            target.get_by_role('button',name='Used',exact=True).click()
            page.wait_for_function("(n)=>document.getElementById('equipment-new-tv-units').textContent===String(n)",arg=before-5)
            target.get_by_role('button',name='New',exact=True).click()
            page.wait_for_function("(n)=>document.getElementById('equipment-new-tv-units').textContent===String(n)",arg=before)
            page.locator('#equipment-show-new').click()
            page.wait_for_function("()=>document.getElementById('equipment-show-new').getAttribute('aria-pressed')==='true'")
            expected=len([r for r in app.equipment_inventory(tv['id']) if r.get('custom_values',{}).get('unit_status')=='New'])
            assert page.locator('#equipment-rows tr').count()==expected
            assert page.locator('#equipment-rows [data-value="New"][aria-pressed="true"]').count()==expected
            page.locator('#equipment-show-new').click()
            assert page.locator('#equipment-rows tr').count()==7
            page.evaluate('document.fonts.ready')
            page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
            page.wait_for_timeout(120)
            out=Path('work/screenshots');out.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(out/'avtrack-inventory-status.png'),full_page=True)
            print('AVTRACK_PREVIEW_JPEG:'+base64.b64encode(page.screenshot(type='jpeg',quality=60,full_page=True)).decode(),flush=True)
            # Manual shelf capture is offered in other inventories too.
            page.locator('#equipment-inventory-select').select_option(str(generic['id']))
            page.wait_for_function("()=>document.getElementById('equipment-inventory-title').textContent==='AV spare parts'")
            page.locator('#add-device').click()
            page.locator('#equipment-model').fill('HDMI cable')
            page.locator('#equipment-quantity').fill('7')
            page.locator('#equipment-shelf').fill('A3')
            page.locator('#save-equipment').click();page.locator('#equipment-dialog').wait_for(state='hidden')
            assert any(r['notes']=='Shelf: A3' for r in app.equipment_inventory(generic['id']))
            assert page.locator('#equipment-new-tv-stat').is_hidden()
            page.goto(origin)
            page.wait_for_function("()=>document.getElementById('overview-inventory-total').textContent!=='—'")
            assert page.locator('#overview-inventory-total').inner_text()==str(app.workspace_overview()['inventory_units'])
            assert page.locator('#overview-inventory-locations').inner_text()=='units across all inventories'
            page.goto(origin+'/inventory')
            page.wait_for_function("()=>!document.getElementById('equipment-inventory-select').disabled")
            page.locator('#equipment-inventory-select').select_option(str(tv['id']))
            page.set_viewport_size({'width':390,'height':844})
            page.wait_for_timeout(250)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert page.locator('#equipment-new-tv-stat').is_visible()
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('PASS: optional CSV status, distinct batches, New TV counts, shelf notes, home units, desktop/mobile')
