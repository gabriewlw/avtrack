"""Desktop status and automatic Last checked dates, with no separate stock check."""
from pathlib import Path
import shutil,sys,tempfile,threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'inventory.sqlite3'
    base=dict(description='Camera',brand='Demo',model='Camera X',serial_number='CAM-1',quantity=1,location='Studio')
    first=app.save_equipment(base)
    partial=app.save_equipment(dict(base,description='Incomplete camera',model='',serial_number='CAM-2'))
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/inventory')
            page.wait_for_function("()=>document.querySelectorAll('#equipment-rows tr').length===2")
            headers=page.locator('#equipment-table thead').inner_text().lower()
            assert 'stock check' not in headers and 'status' in headers and 'last checked' in headers,repr(headers)
            assert not page.locator('.equipment-review-filter').is_visible()
            complete=page.locator('#equipment-rows tr').filter(has_text='CAM-1')
            incomplete=page.locator('#equipment-rows tr').filter(has_text='CAM-2')
            assert complete.locator('.equipment-last-checked').inner_text()=='Not checked'
            assert not complete.locator('.equipment-last-checked button').count()
            complete.locator('.equipment-confirm').check()
            page.wait_for_function("()=>document.querySelector('#equipment-stock-progress-count').textContent.includes('1 / 2')")
            assert complete.locator('.equipment-last-checked').inner_text()!='Not checked'
            assert incomplete.locator('.equipment-last-checked').inner_text()=='Not checked'
            incomplete.get_by_role('button',name='Edit equipment CAM-2',exact=True).click()
            page.locator('#equipment-form [name=model]').fill('Camera Y')
            page.locator('#save-equipment').click()
            page.locator('#equipment-dialog').wait_for(state='hidden')
            page.wait_for_function("()=>[...document.querySelectorAll('#equipment-rows tr')].some(row=>row.textContent.includes('CAM-2') && row.querySelector('.equipment-last-checked').textContent!=='Not checked')")
            assert not incomplete.locator('.equipment-confirm').is_checked()
            page.reload()
            page.wait_for_function("()=>document.querySelectorAll('#equipment-rows tr').length===2")
            assert all(text!='Not checked' for text in page.locator('.equipment-last-checked').all_inner_texts())
            for row in page.locator('#equipment-rows tr').all():
                assert row.locator('td').count()==page.locator('#equipment-table thead th').count()
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close()
print('PASS: desktop status, automatic completion dates, reload persistence, location progress, column alignment, no browser errors')
