"""Desktop regression for the simplified import and recovery release."""
import json,sys,shutil,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
 app.DB_PATH=Path(tmp)/'inventory.sqlite3'
 # Match app.py startup: finish database upgrades before accepting concurrent browser requests.
 with app.connect():pass
 server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=shutil.which('chromium'))
   page=browser.new_page(viewport={'width':1440,'height':1000});page.set_default_timeout(10000);errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
   origin=f'http://127.0.0.1:{server.server_port}'
   page.goto(origin+'/');page.locator('#home-empty-state').wait_for(state='visible')
   assert not errors,errors
   page.get_by_role('button',name='＋ Add device',exact=True).click();page.locator('#device-form [name=name]').fill('Draft camera');page.locator('#close-dialog').click()
   page.locator('#add-device').click();assert page.locator('#device-form [name=name]').input_value()=='Draft camera'
   page.locator('#device-form [name=ip]').fill('10.20.1.1');page.locator('#device-form [name=venue]').fill('Studio');page.locator('#save-device').click();page.locator('#device-dialog').wait_for(state='hidden')
   page.locator('.device-name').click();page.locator('#desktop-record-dialog').wait_for(state='visible');page.locator('#desktop-record-body').get_by_text('10.20.1.1',exact=False).wait_for();page.locator('[data-close="desktop-record-dialog"]').click()
   page.locator('#import').click();page.locator('#paste-inventory-text').fill('Device Name\tIP Address\tVenue\tVLAN\tSubnet\nImported camera\t10.20.1.2\tStudio\t100\t255.255.255.0')
   page.locator('#continue-paste-inventory').click();page.locator('#paste-layout-dialog').wait_for(state='visible');page.wait_for_function("() => !document.getElementById('paste-start-review').disabled")
   assert len(app.inventory())==1
   page.locator('#paste-start-review').click();page.locator('#inventory-import-review').wait_for(state='visible');assert len(app.inventory())==1
   page.locator('#inventory-import-review-save').click();page.locator('#import-summary-panel').wait_for(state='visible');assert len(app.inventory())==2
   assert app.inventory()[1]['notes']=='Subnet 255.255.255.0' or any(row['notes']=='Subnet 255.255.255.0' for row in app.inventory())
   page.once('dialog',lambda dialog:dialog.accept());page.locator('#undo-current-import').click();page.locator('#import-summary-panel').wait_for(state='hidden');assert len(app.inventory())==1
   page.locator('#equipment-tab').click();page.wait_for_function("() => !document.getElementById('new-equipment-inventory').disabled")
   page.locator('#new-equipment-inventory').click();page.locator('#equipment-inventory-name').fill('Spare Parts');page.locator('#save-equipment-inventory').click();page.locator('#inventory-start-dialog').wait_for(state='visible');page.locator('#inventory-start-manual').click()
   page.locator('#equipment-form [name=description]').fill('Camera');page.locator('#equipment-form [name=brand]').fill('Sony');page.locator('#equipment-form [name=model]').fill('X');page.locator('#equipment-form [name=serial_number]').fill('A, B, C');page.locator('#equipment-form [name=quantity]').fill('3');page.locator('#equipment-form').get_by_role('button',name='New location',exact=True).click();page.get_by_label('New storage location',exact=True).fill('Locker');page.locator('#equipment-form').get_by_role('button',name='Add location',exact=True).click();page.locator('#save-equipment').click();page.locator('#equipment-dialog').wait_for(state='hidden')
   page.locator('#equipment-table .equipment-delete-action').click();assert page.locator('#confirm-equipment-delete').is_disabled();page.locator('#equipment-delete-unit').select_option('serial:B');assert '3 to 2' in page.locator('#unit-removal-impact').inner_text();page.locator('#unit-removal-reason').fill('Installed in studio');page.locator('#confirm-equipment-delete').click();page.locator('#equipment-delete-dialog').wait_for(state='hidden')
   page.locator('#equipment-table .record-details-button').click();page.locator('#desktop-record-body .record-added-via').get_by_text('Manually',exact=False).wait_for();assert 'Verification and stock movement history' not in page.locator('#desktop-record-body').inner_text();page.locator('[data-close="desktop-record-dialog"]').click()
   assert page.locator('#main-navigation a').all_text_contents()==['Devices','IPTV','Inventory','Equipment backups']
   assert page.locator('#desktop-find').input_value()=='' and page.locator('#desktop-find').get_attribute('placeholder') is None
   page.locator('#desktop-find').fill('10.20.1.1');page.locator('#desktop-find').press('Enter');page.wait_for_function("() => document.querySelectorAll('#desktop-search-results .search-result').length===1");page.locator('[data-close="desktop-search-dialog"]').click()
   page.locator('.brand').click();page.locator('#workspace-export-menu summary').click()
   with page.expect_download() as download:page.get_by_role('link',name='Complete backup JSON',exact=True).click()
   backup=Path(tmp)/'full.json';download.value.save_as(backup);assert json.loads(backup.read_text())['format']=='avtrack-workspace'
   page.locator('#workspace-restore-open').click();page.locator('#workspace-restore-file').set_input_files(str(backup));page.locator('#workspace-restore-preview').wait_for(state='visible');assert '1 devices' in page.locator('#workspace-restore-preview').inner_text();assert page.locator('#workspace-restore-submit').is_enabled();page.locator('#workspace-restore-cancel').click()
   page.screenshot(path='/tmp/avtrack-desktop-release.png',full_page=True)
   assert not errors,errors
   browser.close()
 finally:server.shutdown();server.server_close()
print('PASS: desktop drafts, source preview, explicit import, undo, stock movement, details, header search, JSON download and restore preview')
