"""Desktop multi-sheet previews never save records before explicit import."""
import shutil,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from openpyxl import Workbook
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
 app.DB_PATH=Path(tmp)/'inventory.sqlite3'
 inventory=app.save_equipment_inventory({'name':'Parts'})
 book=Workbook();book.active.title='Locker A';book.active.append(['Item','Brand','Model','Serial Number','Quantity','Notes','Warranty']);book.active.append(['Camera','Sony','X','S1',1,'Original note','2028'])
 second=book.create_sheet('Locker B');second.append(['Item','Brand','Model','Serial Number','Quantity','Notes','Warranty']);second.append(['Camera','Sony','X','S2, S3',2,'Second note','2029']);path=Path(tmp)/'parts.xlsx';book.save(path)
 server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=shutil.which('chromium'));page=browser.new_page(viewport={'width':1440,'height':1000});page.set_default_timeout(10000);errors=[];page.on('pageerror',lambda error:errors.append(str(error)));page.goto(f'http://127.0.0.1:{server.server_port}/inventory');page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
   page.locator('#equipment-inventory-select').select_option(str(inventory['id']));page.locator('#equipment-import').click()
   with page.expect_file_chooser() as chooser:page.locator('#upload-paste-inventory').click()
   chooser.value.set_files(str(path));page.locator('#paste-layout-dialog').wait_for(state='visible');page.wait_for_function("() => !document.getElementById('paste-start-review').disabled")
   assert app.equipment_inventory(inventory['id'])==[]
   page.locator('#import-sheet-choices input[value="Locker B"]').check()
   page.locator('#paste-start-review').click();page.locator('#inventory-import-review').wait_for(state='visible');assert app.equipment_inventory(inventory['id'])==[]
   page.locator('#inventory-import-review-save').click();page.locator('#paste-layout-dialog').wait_for(state='visible');page.wait_for_function("() => !document.getElementById('paste-start-review').disabled")
   saved=app.equipment_inventory(inventory['id']);assert len(saved)==1 and saved[0]['location']=='Locker A',saved
   page.locator('#paste-start-review').click();page.locator('#inventory-import-review').wait_for(state='visible');page.locator('#inventory-import-review-save').click();page.locator('#import-summary-panel').wait_for(state='visible')
   saved=app.equipment_inventory(inventory['id']);assert len(saved)==2 and {row['location'] for row in saved}=={'Locker A','Locker B'},saved
   assert all('Warranty ' in row['notes'] for row in saved),saved
   page.locator('#close-import-summary').click()
   page.locator('#new-equipment-inventory').click();page.locator('#equipment-inventory-name').fill('Custom assets');page.locator('#equipment-template').select_option('custom');page.locator('#save-equipment-inventory').click();page.locator('#inventory-start-import').click()
   page.locator('#paste-inventory-text').fill('Asset Tag\tOwner\tNotes\nASSET-1\tBroadcast\tKeep this note');page.locator('#continue-paste-inventory').click();page.locator('#paste-layout-dialog').wait_for(state='visible');page.wait_for_function("() => !document.getElementById('paste-start-review').disabled")
   assert app.equipment_inventory(int(page.locator('#equipment-inventory-select').input_value()))==[]
   page.locator('#paste-start-review').click();page.locator('#inventory-import-review').wait_for(state='visible');page.locator('#inventory-import-review-save').click();page.locator('#import-summary-panel').wait_for(state='visible')
   custom=app.equipment_inventory(int(page.locator('#equipment-inventory-select').input_value()));assert len(custom)==1,custom
   assert set(custom[0]['custom_values'].values())=={'ASSET-1','Broadcast'},custom
   assert custom[0]['notes']=='Keep this note',custom
   page.locator('#close-import-summary').click()
   page.evaluate('() => window.equipmentUI.open()');custom_field=page.locator('#equipment-custom-fields [data-draft-field]').first;custom_field.fill('UNSAVED-ASSET');page.locator('#close-equipment').click()
   page.evaluate('() => window.equipmentUI.open()');assert page.locator('#equipment-custom-fields [data-draft-field]').first.input_value()=='UNSAVED-ASSET';page.locator('#close-equipment').click()
   page.locator('#device-tab').click()
   import json
   notes='Subnet 255.255.255.0\nGateway 10.0.0.1\nKeep\tthis tab'
   source=Path(tmp)/'devices.json';source.write_text(json.dumps({'version':1,'devices':[{'name':'JSON camera','ip':'10.0.0.2','notes':notes}]}))
   page.locator('#import-file').set_input_files(str(source));page.locator('#paste-layout-dialog').wait_for(state='visible');page.wait_for_function("() => !document.getElementById('paste-start-review').disabled");assert app.inventory()==[]
   page.locator('#paste-start-review').click();page.locator('#inventory-import-review').wait_for(state='visible');assert app.inventory()==[]
   page.locator('#inventory-import-review-save').click();page.locator('#import-summary-panel').wait_for(state='visible');assert app.inventory()[0]['notes']==notes,app.inventory()
   assert not errors,errors;browser.close()
 finally:server.shutdown();server.server_close()
print('PASS: multi-sheet locations, custom headings, multiline JSON notes, preview without writes, and explicit import')
