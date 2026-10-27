from browser_helpers import open_workspace, open_import_settings, set_import_confirmation, open_import_matching, start_import_review, choose_new_inventory_import
"""Excel pastes on Devices and IPTV share column matching and editable review."""
import sys,tempfile,threading,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'test.sqlite3'
    with app.connect() as con: con.commit()
    with app.connect() as connection:connection.commit()
    server = app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.wait_for_function("() => !document.getElementById('refresh').disabled")
            open_workspace(page, 'device-tab')
            def paste(text,mode):
                assert page.locator('#transfer button').first.get_attribute('id')=='add-device'
                assert page.locator('#transfer #import').count()==1
                assert page.locator('#transfer').get_by_role('button',name='Paste from Excel',exact=True).count()==0
                page.locator('#import').click();page.locator('#paste-inventory-dialog').wait_for(state='visible')
                assert page.locator('#paste-inventory-location-label').is_hidden()
                page.locator('#paste-inventory-text').fill(text);page.locator('#continue-paste-inventory').click()
                page.locator('#paste-layout-dialog').wait_for(state='visible')
                page.wait_for_function("() => !document.getElementById('paste-start-review').disabled")
                open_import_settings(page)
                assert page.locator('#paste-preview-confirmation option[value=storage]').count()==0
                set_import_confirmation(page, mode)
                page.locator('#paste-layout-dialog').wait_for(state='visible')
                page.wait_for_function("() => !document.getElementById('paste-start-review').disabled")
                assert page.locator('#spreadsheet-dialog').is_hidden()
                assert page.locator('#paste-layout-head th').count()>0
                assert page.locator('#paste-layout-rows tr').count()<=5
                open_import_matching(page)
                page.locator('#spreadsheet-dialog:visible, #paste-layout-dialog:visible').first.wait_for()
                page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            paste('Venue\tDevice Name\tIP Address\tVLAN\tNotes\nSports Bar\tWall TV\t10.20.30.40\t50\tScreen one','none')
            assert 'Devices' in page.locator('#paste-inventory-target').inner_text()
            assert page.locator('#map-ip').input_value()=='2'
            assert not app.inventory()
            start_import_review(page);page.locator('#inventory-import-review').wait_for(state='visible')
            assert page.get_by_label('Device name, row 2',exact=True).input_value()=='Wall TV'
            page.get_by_role('button',name='Edit notes for row 2',exact=True).click();page.locator('#import-cell-notes-text').fill('Checked paste');page.locator('#apply-import-cell-notes').click()
            page.locator('#inventory-import-review-save').click();page.locator('#inventory-import-review').wait_for(state='hidden')
            page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            assert app.inventory()[0]['notes']=='Checked paste'
            assert app.inventory()[0]['confirmation_required']==0
            assert page.locator('.ip-confirm').count()==0
            page.locator('#import-summary-panel').wait_for(state='visible');page.locator('#close-import-summary').click()
            open_workspace(page, 'iptv-tab')
            paste('| Channel Name | Multicast IP | Port | Notes |\n| --- | --- | --- | --- |\n| Crew TV | 239.1.2.3 | 1234 | Onboard |','ip')
            assert 'IPTV Channels' in page.locator('#paste-inventory-target').inner_text()
            assert page.locator('#map-port').input_value()=='2'
            start_import_review(page);page.locator('#inventory-import-review').wait_for(state='visible')
            assert page.get_by_label('Multicast IP, row 2',exact=True).input_value()=='239.1.2.3'
            assert page.get_by_label('Port, row 2',exact=True).input_value()=='1234'
            page.locator('#inventory-import-review-save').click();page.locator('#inventory-import-review').wait_for(state='hidden')
            page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            records=app.inventory();assert len(records)==2
            assert next(r for r in records if r['record_type']=='iptv')['ip']=='239.1.2.3'
            channel=next(r for r in records if r['record_type']=='iptv')
            assert channel['confirmation_required']==1 and channel['ip_confirmed']==0
            page.locator('#import-summary-panel').wait_for(state='visible');page.locator('#close-import-summary').click()
            page.locator('.ip-confirm').click()
            page.get_by_role('button',name='IP confirmed for Crew TV',exact=True).wait_for(state='visible')
            assert next(r for r in app.inventory() if r['record_type']=='iptv')['ip_confirmed']==1
            page.reload();page.wait_for_function("() => !document.getElementById('refresh').disabled")
            open_workspace(page, 'iptv-tab')
            assert page.get_by_role('button',name='IP confirmed for Crew TV',exact=True).is_visible()
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('AV and IPTV pasted Excel/message tables, matching, editable review and correct destination passed.')
