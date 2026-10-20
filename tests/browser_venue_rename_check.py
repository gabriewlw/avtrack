from pathlib import Path
import shutil,sys,tempfile,threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
 app.DB_PATH=Path(tmp)/'inventory.sqlite3'
 old='Broadcast Technical Operations Center'
 for n in range(1,3):app.save_device(dict(name=f'Camera {n}',venue=old,ip=f'192.0.2.{n}'))
 app.save_device(dict(name='Console',venue='Bridge',ip='192.0.2.3'))
 server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
 threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=shutil.which('chromium'))
   page=browser.new_page(viewport={'width':1280,'height':1000});errors=[]
   page.on('pageerror',lambda error:errors.append(str(error)))
   page.goto(f'http://127.0.0.1:{server.server_port}/#av')
   page.wait_for_function("()=>!document.getElementById('rename-device-venue').disabled")
   label=page.locator('.device-venue').filter(has_text=old).first
   assert label.get_attribute('title')==old
   assert label.evaluate('(node)=>getComputedStyle(node).whiteSpace')=='nowrap'
   page.locator('#venue-filter').select_option(old)
   page.locator('#rename-device-venue').click()
   assert 'all 2 devices' in page.locator('#device-venue-impact').inner_text()
   page.locator('#device-venue-name').fill('BC')
   page.locator('#save-device-venue').click()
   page.locator('#rename-device-venue-dialog').wait_for(state='hidden')
   page.wait_for_function("()=>document.getElementById('venue-filter').value==='BC' && document.querySelectorAll('.device-venue')[0]?.textContent==='BC'")
   assert page.locator('.device-row').count()==2
   assert all(row['venue']=='BC' for row in app.inventory() if row['name'].startswith('Camera'))
   page.locator('#rename-device-venue').click()
   page.locator('#device-venue-name').fill('Bridge');page.locator('#save-device-venue').click()
   page.locator('#device-venue-error').wait_for(state='visible')
   assert 'already uses' in page.locator('#device-venue-error').inner_text()
   page.locator('#cancel-device-venue').click()
   page.reload();page.wait_for_function("()=>document.querySelectorAll('.device-row').length===3")
   assert page.locator('#venue-filter option[value=BC]').count()==1
   assert not errors,errors
   browser.close()
 finally:server.shutdown();server.server_close()
print('PASS: one-line venue labels, rename all members, filter preservation, duplicate error, cancel and reload')
