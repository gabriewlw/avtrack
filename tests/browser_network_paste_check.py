"""Excel pastes on AV Devices and IPTV share column matching and editable review."""
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
            def paste(text):
                page.locator('#network-paste').click();page.locator('#paste-inventory-dialog').wait_for(state='visible')
                assert page.locator('#paste-inventory-location-label').is_hidden()
                page.locator('#paste-inventory-text').fill(text);page.locator('#continue-paste-inventory').click()
                page.locator('#paste-layout-dialog').wait_for(state='visible')
                page.wait_for_function("() => !document.getElementById('continue-paste-layout').disabled")
                assert page.locator('#spreadsheet-dialog').is_hidden()
                assert page.locator('#paste-layout-head th').count()>0
                assert page.locator('#paste-layout-rows tr').count()<=5
                page.locator('#keep-paste-layout').click()
                page.locator('#spreadsheet-dialog').wait_for(state='visible')
                page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            paste('Venue\tDevice Name\tIP Address\tVLAN\tNotes\nSports Bar\tWall TV\t10.20.30.40\t50\tScreen one')
            assert 'AV Devices' in page.locator('#paste-inventory-target').inner_text()
            assert page.locator('#map-ip').input_value()=='2'
            assert not app.inventory()
            page.locator('#confirm-import').click();page.locator('#row-review-dialog').wait_for(state='visible')
            assert page.locator('#review-name').input_value()=='Wall TV'
            page.locator('#review-notes').fill('Checked paste')
            page.locator('#accept-review-row').click();page.locator('#row-review-dialog').wait_for(state='hidden')
            page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            assert app.inventory()[0]['notes']=='Checked paste'
            page.locator('#iptv-tab').click()
            paste('| Channel Name | Multicast IP | Port | Notes |\n| --- | --- | --- | --- |\n| Crew TV | 239.1.2.3 | 1234 | Onboard |')
            assert 'IPTV Channels' in page.locator('#paste-inventory-target').inner_text()
            assert page.locator('#map-port').input_value()=='2'
            page.locator('#confirm-import').click();page.locator('#row-review-dialog').wait_for(state='visible')
            assert page.locator('#review-ip').input_value()=='239.1.2.3'
            assert page.locator('#review-port').input_value()=='1234'
            page.locator('#accept-review-row').click();page.locator('#row-review-dialog').wait_for(state='hidden')
            page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            records=app.inventory();assert len(records)==2
            assert next(r for r in records if r['record_type']=='iptv')['ip']=='239.1.2.3'
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('AV and IPTV pasted Excel/message tables, matching, editable review and correct destination passed.')
