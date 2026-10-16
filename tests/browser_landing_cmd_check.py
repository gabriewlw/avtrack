"""The landing-page CMD window matches the BroadcastGab desktop terminal."""
import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temporary:
    app.DB_PATH=Path(temporary)/'landing.sqlite3'
    with app.connect() as connection: connection.commit()
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(executable_path=shutil.which('chromium') or None)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/avtrack')
            bridge=page.locator('.command-bridge');bridge.scroll_into_view_if_needed()
            assert page.locator('.command-title>span').inner_text()=='CMD.EXE — BROADCAST GAB'
            assert page.locator('.command-controls').inner_text().splitlines()==['—','▢','✕']
            purpose=page.locator('.purpose').bounding_box();window=bridge.bounding_box()
            assert abs(window['x']-purpose['x'])<1
            assert abs((window['x']+window['width'])-(purpose['x']+purpose['width']))<1
            assert page.locator('.command-title').evaluate('(node)=>getComputedStyle(node).fontSize')=='11px'
            assert page.locator('.command-title').evaluate('(node)=>getComputedStyle(node).height')=='34px'
            assert bridge.evaluate('(node)=>getComputedStyle(node).borderRadius')=='6px'
            assert page.locator('.command-body').evaluate('(node)=>getComputedStyle(node).padding')=='16px 20px'
            assert page.locator('.command-body p').first.evaluate('(node)=>getComputedStyle(node).color')=='rgb(230, 230, 230)'
            assert page.locator('.command-dim').first.evaluate('(node)=>getComputedStyle(node).color')=='rgb(168, 168, 168)'
            shortcuts=page.locator('.command-chips button')
            assert shortcuts.count()==6
            assert shortcuts.first.inner_text()=='STATUS'
            assert shortcuts.last.inner_text()=='DEMO'
            terminal=page.locator('#command-input')
            terminal.fill('help');terminal.press('Enter')
            assert 'AVTRACK COMMANDS' in page.locator('#command-output').inner_text()
            page.locator('.command-chips button[data-command="inventory"]').click()
            inventory_link=page.get_by_role('link',name='Open Inventory workspace →',exact=True)
            assert inventory_link.get_attribute('href')=='/inventory'
            terminal.press('ArrowUp');assert terminal.input_value()=='inventory'
            terminal.fill('clear');terminal.press('Enter')
            assert page.locator('#command-output p').count()==0
            assert terminal.evaluate('(node)=>node===document.activeElement')
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close()
print('Landing CMD window matches BroadcastGab and supports typing, history, project shortcuts and clear.')
