from browser_helpers import open_workspace, open_import_settings, set_import_confirmation, open_import_matching, start_import_review, choose_new_inventory_import
"""Download and restore one complete backup from the homepage controls."""
import base64
import shutil
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temporary:
    app.DB_PATH=Path(temporary)/'inventory.sqlite3'
    device=app.save_device(dict(name='Transfer camera',category='Camera',venue='Studio',discipline='Video',ip='10.20.1.1',vlan=1,notes='Preserve me'))
    app.save_av_backup(dict(equipment_type='OBS profile',device_name='PC',filename='profile.json',notes='Test',content=base64.b64encode(b'{"saved":true}').decode()))
    with app.connect() as connection:connection.commit()
    server = app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1100})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            origin=f'http://127.0.0.1:{server.server_port}'
            page.goto(origin+'/')
            heading=page.get_by_role('heading',name='Your workspace at a glance.')
            heading.wait_for()
            assert page.locator('#main-navigation #workspace-restore-open').count()==0
            assert page.locator('.workspace-transfer-actions #workspace-restore-open').is_visible()
            assert page.locator('#workspace-restore-open').evaluate("el=>el.classList.contains('primary')")
            assert page.locator('#workspace-export-menu summary svg').count()==2
            assert page.locator('#network-paste, #equipment-paste, #address-filter-group').count()==0
            assert page.locator('#import').evaluate("el=>el.classList.contains('primary')")
            open_workspace(page, 'device-tab')
            page.locator('#import').click()
            page.locator('#paste-inventory-dialog').wait_for(state='visible')
            assert page.locator('#paste-inventory-title').inner_text()=='Import data'
            assert page.locator('#upload-paste-inventory').is_visible()
            page.locator('#cancel-paste-inventory').click()
            page.locator('#workspace-export-menu summary').click()
            page.screenshot(path='/tmp/avtrack-workspace-transfer-desktop.png',full_page=True)
            with page.expect_download() as download:
                page.get_by_role('link',name='Complete backup ZIP · recommended',exact=True).click()
            backup=Path(temporary)/'transfer.zip';download.value.save_as(backup)
            assert download.value.suggested_filename.startswith('avtrack-all-data-') and download.value.suggested_filename.endswith('.zip')
            with app.connect() as con:con.execute('DELETE FROM devices')
            page.locator('#workspace-restore-open').click()
            page.locator('#workspace-restore-file').set_input_files(str(backup))
            page.locator('#workspace-restore-replace').check()
            page.locator('#workspace-restore-submit').click()
            page.wait_for_url(origin+'/')
            page.wait_for_function("() => document.getElementById('workspace-restore-dialog').open===false")
            assert app.inventory()[0]['notes']=='Preserve me'
            assert app.av_backup_file(1)[1]==b'{"saved":true}'
            page.locator('#workspace-restore-open').click()
            page.locator('#workspace-restore-file').set_input_files({'name':'invalid.json','mimeType':'application/json','buffer':b'{}'})
            page.locator('#workspace-restore-error').wait_for(state='visible')
            assert page.locator('#workspace-restore-submit').is_disabled()
            assert len(app.inventory())==1
            page.locator('#workspace-restore-cancel').click()
            page.set_viewport_size({'width':390,'height':844})
            page.locator('#workspace-export-menu summary').click()
            page.locator('#workspace-export-menu').scroll_into_view_if_needed()
            page.screenshot(path='/tmp/avtrack-workspace-transfer-mobile.png',full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close()
print('PASS: homepage full-backup download, restore, invalid-file preservation, and mobile layout')
