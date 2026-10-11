"""Pasted headers produce a suggested table before editable field matching."""
import sys,tempfile,threading,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'test.sqlite3'
    with app.connect() as con: con.commit()
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.wait_for_function("() => !document.getElementById('refresh').disabled")
            text='Venue\tDevice Name\tIP Address\tVLAN\tNotes\tOdd heading\nSports Bar\tWall TV\t10.20.30.40\t50\t\t<test>'
            page.locator('#network-paste').click();page.locator('#paste-inventory-text').fill(text)
            page.locator('#continue-paste-inventory').click()
            page.locator('#continue-paste-confirmation').click()
            page.locator('#paste-layout-dialog').wait_for(state='visible')
            page.wait_for_function("() => !document.getElementById('continue-paste-layout').disabled")
            assert page.locator('#spreadsheet-dialog').is_hidden()
            assert 'Excel: IP Address' in page.locator('#paste-layout-head').inner_text()
            assert 'Odd heading' in page.locator('#paste-layout-unmatched').inner_text()
            assert 'Needs review' in page.locator('#paste-layout-rows').inner_text()
            assert not app.inventory()
            page.locator('#back-paste-layout').click()
            assert page.locator('#paste-inventory-text').input_value()==text
            page.locator('#continue-paste-inventory').click()
            page.locator('#continue-paste-confirmation').click()
            page.wait_for_function("() => !document.getElementById('continue-paste-layout').disabled")
            page.locator('#keep-paste-layout').click()
            assert page.locator('#map-ip').input_value()=='2'
            assert page.locator('#map-notes').input_value()=='4'
            assert not app.inventory()
            page.locator('#cancel-spreadsheet').click()
            assert not app.inventory()
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('Header suggestions, sample blanks, unmatched headings, back navigation, editable matching and no premature saves passed.')
