"""The exhibition page uses fictional browser-only records and leaves SQLite untouched."""
import sys,tempfile,threading,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'test.sqlite3'
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];requests=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:requests.append(request.url))
            page.goto(f'http://127.0.0.1:{server.server_port}/demo')
            assert page.locator('#demo-rows tr').count()==12
            page.locator('[data-demo-tab="iptv"]').click();assert page.locator('#demo-rows tr').count()==8
            page.locator('[data-demo-tab="inventory"]').click()
            assert 'Serial number' not in page.locator('#demo-head').inner_text()
            select=page.get_by_label('Deck 6 for SAMPLE-L24',exact=True)
            select.select_option('10');assert page.locator('#demo-rows tr').first.locator('td').nth(5).inner_text()=='11'
            page.get_by_role('button',name='Never checked',exact=True).first.click()
            page.locator('#demo-check-save').click();page.locator('#demo-check-dialog').wait_for(state='hidden')
            page.locator('#demo-type').select_option('scala')
            page.get_by_role('button',name='Horizontal for SC-DEMO-001',exact=True).click()
            assert page.get_by_role('button',name='Horizontal for SC-DEMO-001',exact=True).get_attribute('aria-pressed')=='true'
            page.get_by_role('button',name='View',exact=True).first.click()
            page.locator('#demo-notes').fill('Demonstration note')
            page.locator('#demo-notes-form button[type="submit"]').click()
            page.locator('#demo-search').fill('Demonstration note');assert page.locator('#demo-rows tr').count()==1
            page.locator('#demo-search').fill('')
            page.locator('#demo-import').click()
            for _ in range(5):page.locator('#demo-walkthrough-next').click()
            page.locator('#demo-walkthrough').wait_for(state='hidden')
            page.screenshot(path='work/demo-desktop.png',full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
            assert not any('/api/' in url for url in requests)
            assert not app.DB_PATH.exists()
            page.reload();assert 'Demonstration note' not in page.locator('#demo-rows').inner_text()
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('Fictional demo tabs, TV totals/check dates, orientation, floating notes, search, import walkthrough and database isolation passed.')
