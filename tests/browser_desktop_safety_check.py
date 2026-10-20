from browser_helpers import open_workspace
"""Desktop stock accuracy, reviewed updates, and equipment recovery metadata."""
import base64,json,shutil,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
 app.DB_PATH=Path(tmp)/'inventory.sqlite3'
 inventory=app.save_equipment_inventory({'name':'Parts'})
 for serial,quantity in [('S1',3),('S2',None)]:
  item=app.save_equipment(dict(inventory_id=inventory['id'],description='Camera',serial_number=serial,quantity=quantity,location='Locker'))
  app.set_equipment_confirmation(item['id'],dict(item,item_confirmed=True))
 device=app.save_device(dict(name='Camera',ip='10.20.1.1',venue='Studio',notes='Old note'))
 app.save_av_backup(dict(equipment_type='OBS profile',device_name='Camera',filename='profile.json',content=base64.b64encode(b'{}').decode(),notes='Test backup'))
 server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=shutil.which('chromium'));page=browser.new_page(viewport={'width':1440,'height':1000});page.set_default_timeout(10000);errors=[];page.on('pageerror',lambda error:errors.append(str(error)));origin=f'http://127.0.0.1:{server.server_port}'
   page.goto(origin+'/inventory');page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
   page.locator('#equipment-inventory-select').select_option(str(inventory['id']));page.wait_for_function("() => document.getElementById('equipment-records').textContent==='2'")
   assert page.locator('#equipment-locations').inner_text()=='1'
   assert page.locator('#equipment-found').inner_text()=='1'
   assert '1 record awaiting count' in page.locator('#equipment-unknown-count').inner_text()
   assert 'unknown counts' in page.locator('#equipment-found-percent').inner_text()
   open_workspace(page, 'device-tab');page.locator('#import').click();page.locator('#paste-inventory-text').fill('Device Name\tIP Address\tVenue\tNotes\nCamera\t10.20.1.1\tStudio\tUpdated source note');page.locator('#continue-paste-inventory').click();page.wait_for_function("() => !document.getElementById('paste-start-review').disabled")
   page.locator('#import-existing-mode').select_option('review');page.locator('#paste-start-review').click();page.locator('#inventory-import-review').wait_for(state='visible');assert app.inventory()[0]['notes']=='Old note'
   assert 'Updated source note' in page.locator('.review-differences').inner_text();assert page.locator('#inventory-import-review-save').is_disabled()
   page.locator('#inventory-import-review-rows input[type=checkbox]').check();page.locator('#inventory-import-review-save').click();page.locator('#import-summary-panel').wait_for(state='visible');assert app.inventory()[0]['notes']=='Updated source note';page.locator('#import-summary-close-action').click()
   open_workspace(page, 'backups-tab');page.locator('.backup-card').wait_for();page.get_by_role('button',name='Recovery details',exact=True).click();page.locator('#recovery-related').select_option('device:'+str(device['id']));page.locator('#recovery-firmware').fill('1.2.3');page.locator('#recovery-model').fill('Sony X / S1');page.locator('#recovery-captured').fill('2026-10-01');page.locator('#recovery-tested').fill('2026-10-10');page.locator('#recovery-state').select_option('known_good');page.locator('#save-recovery-details').click();page.locator('#backup-recovery-dialog').wait_for(state='hidden');page.locator('.backup-recovery-summary').get_by_text('Firmware 1.2.3',exact=False).wait_for()
   open_workspace(page, 'device-tab');page.locator('.device-name').click();page.locator('#desktop-record-body .record-added-via').get_by_text('Manually',exact=False).wait_for();assert 'Updated source note' in page.locator('#desktop-record-body').inner_text();assert 'Related equipment backups' not in page.locator('#desktop-record-body').inner_text();page.locator('[data-close="desktop-record-dialog"]').click()
   page.locator('#add-device').click();page.locator('#device-form [name=notes]').fill('Incomplete test');page.locator('#save-device').click();page.locator('#save-incomplete-device').wait_for(state='visible');assert len(app.inventory())==1;page.locator('#save-incomplete-device').click();page.locator('#device-dialog').wait_for(state='hidden');assert len(app.inventory())==2
   assert not errors,errors
   browser.close()
 finally:server.shutdown();server.server_close()
print('PASS: stock accuracy, unknown counts, explicitly reviewed updates, recovery metadata/links, and incomplete-record warning')
