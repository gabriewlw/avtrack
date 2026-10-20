from browser_helpers import open_workspace
"""Desktop drops, popup notes, multi-system filters, IP links, and progress."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import workspace_transfer
from openpyxl import Workbook
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'inventory.sqlite3'
    video=app.save_device(dict(name='Video unit',discipline='Video',ip='10.30.0.1',venue='Studio',notes='Original\nSecond line'))
    app.save_device(dict(name='Audio unit',discipline='Audio',ip='10.30.0.2',venue='Studio'))
    app.save_device(dict(name='Network unit',discipline='Network',ip='255.255.255.254',venue='Bridge'))
    app.save_device(dict(name='DHCP unit',discipline='Other',ip='DHCP',venue='Studio'))
    inventory=app.save_equipment_inventory(dict(name='Parts'))
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            context=browser.new_context(viewport={'width':1440,'height':1000})
            page=context.new_page();page.set_default_timeout(15000);errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            origin=f'http://127.0.0.1:{server.server_port}'
            def drop(selector,name,content):
                transfer=page.evaluate_handle("""({name,bytes})=>{const data=new DataTransfer();data.items.add(new File([new Uint8Array(bytes)],name));return data;}""",dict(name=name,bytes=list(content)))
                page.dispatch_event(selector,'drop',{'dataTransfer':transfer});transfer.dispose()
            def save_review():
                page.locator('#paste-layout-dialog').wait_for(state='visible')
                page.wait_for_function("() => !document.getElementById('paste-start-review').disabled")
                page.locator('#paste-start-review').click();page.locator('#inventory-import-review').wait_for(state='visible')
                page.locator('#inventory-import-review-save').click();page.locator('#import-summary-panel').wait_for(state='visible')
                page.locator('#close-import-summary').click()
            page.goto(origin+'/#av');page.wait_for_function("() => document.querySelectorAll('.device-row').length===4")
            assert page.locator('#system-filter').get_attribute('type')=='hidden'
            assert page.locator('#sort-order option').first.inner_text()=='Sort by'
            page.locator('#system-buttons button[data-value=Video]').click();assert page.locator('.device-row').count()==1
            page.locator('#system-buttons button[data-value=Audio]').click();assert page.locator('.device-row').count()==2
            assert page.locator('#system-buttons button[aria-pressed=true]').count()==2
            page.locator('#network-filters .active-filter-chips').get_by_role('button',name='Audio ×',exact=True).click();assert page.locator('.device-row').count()==1
            page.locator('#clear-filters').click();assert page.locator('.device-row').count()==4
            assert page.locator('.device-notes-editor').count()==0
            notes=page.get_by_role('button',name='View notes for Video unit',exact=True)
            assert notes.get_attribute('title')=='Original\nSecond line'
            notes.click();page.wait_for_function("() => !document.getElementById('save-device-notes').disabled")
            page.locator('#device-notes-text').fill('Discard');page.locator('#cancel-device-notes').click();assert next(row for row in app.inventory() if row['id']==video['id'])['notes']=='Original\nSecond line'
            notes.click();page.wait_for_function("() => !document.getElementById('save-device-notes').disabled")
            page.locator('#device-notes-text').fill('Subnet 255.255.255.0\nGateway 10.30.0.254');page.locator('#save-device-notes').click();page.locator('#device-notes-dialog').wait_for(state='hidden')
            assert next(row for row in app.inventory() if row['id']==video['id'])['notes']=='Subnet 255.255.255.0\nGateway 10.30.0.254'
            notes.click();page.wait_for_function("() => !document.getElementById('save-device-notes').disabled")
            app.set_device_notes(video['id'],dict(notes='Changed elsewhere'))
            page.locator('#device-notes-text').fill('My draft');page.locator('#save-device-notes').click();page.locator('#device-notes-error').wait_for(state='visible')
            assert page.locator('#device-notes-text').input_value()=='My draft';assert 'changed' in page.locator('#device-notes-error').inner_text();page.locator('#cancel-device-notes').click()
            context.route('http://10.30.0.1/**',lambda route:route.fulfill(status=200,body='Device UI'))
            globe=page.get_by_role('link',name='Open IP address in browser for Video unit',exact=True)
            assert globe.get_attribute('rel')=='noopener noreferrer'
            with context.expect_page() as opened:globe.click()
            opened.value.wait_for_load_state();assert opened.value.url=='http://10.30.0.1/';opened.value.close()
            assert page.locator('.device-row').filter(has_text='DHCP unit').locator('.ip-browser').count()==0
            page.get_by_role('button',name='Confirm IP for Video unit',exact=True).click()
            page.wait_for_function("() => document.getElementById('device-ip-progress-percent').textContent==='33%'")
            assert '1 of 3 fixed IP' in page.locator('#device-ip-progress-caption').inner_text()
            drop('#network-drop-zone','devices.csv',b'Device Name,IP Address,Venue,VLAN\nImported camera,10.30.0.4,Studio,100')
            page.locator('#paste-layout-dialog').wait_for(state='visible');assert len(app.inventory())==4
            save_review();assert len(app.inventory())==5
            page.locator('.device-name').get_by_text('Imported camera',exact=True).click();page.locator('.record-added-via').get_by_text('File import · devices.csv',exact=False).wait_for()
            assert not page.locator('#desktop-record-body').get_by_text('Related equipment backups',exact=True).count()
            page.screenshot(path='/tmp/avtrack-friendly-record.png');page.locator('[data-close="desktop-record-dialog"]').click()
            open_workspace(page, 'iptv-tab');assert page.locator('#device-ip-progress').is_hidden()
            drop('#network-drop-zone','channels.csv',b'Channel Name,IP Address,UDP Port,Source,Notes\nShip information,239.1.1.1,1234,Onboard,Channel note')
            save_review();assert len([row for row in app.inventory() if row['record_type']=='iptv'])==1
            open_workspace(page, 'equipment-tab');page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            page.locator('#equipment-inventory-select').select_option(str(inventory['id']))
            book=Workbook();book.active.title='Locker A';book.active.append(['Item','Brand','Model','Serial Number','Quantity','Notes']);book.active.append(['Camera','Sony','X','S1',1,'Equipment note'])
            path=Path(tmp)/'parts.xlsx';book.save(path);drop('#inventory-drop-zone','parts.xlsx',path.read_bytes());assert app.equipment_inventory(inventory['id'])==[]
            save_review();assert app.equipment_inventory(inventory['id'])[0]['location']=='Locker A'
            open_workspace(page, 'backups-tab');drop('#backups-drop-zone','profile.json',b'{"profile":"test"}');page.locator('#backup-dialog').wait_for(state='visible')
            assert page.locator('#backup-file').evaluate('(input)=>input.files[0].name')=='profile.json'
            assert app.av_backups()==[]
            page.locator('#backup-type').select_option('OBS profile');page.locator('#backup-device').fill('Control PC');page.locator('#save-backup').click();page.locator('#backup-dialog').wait_for(state='hidden');assert len(app.av_backups())==1
            content=workspace_transfer.pack(workspace_transfer.snapshot(app.connect,app.backup_directory),'json')[0]
            page.locator('#workspace-restore-open').click();drop('#workspace-restore-file','complete.json',content);page.locator('#workspace-restore-preview').wait_for(state='visible');page.locator('#workspace-restore-cancel').click()
            open_workspace(page, 'device-tab');page.locator('#device-ip-progress').scroll_into_view_if_needed();page.screenshot(path='/tmp/avtrack-device-progress.png')
            assert page.locator('.app-version').text_content().strip().startswith('v0.0.')
            assert '·' not in page.locator('.app-version').text_content()
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close()
print('PASS: multi-system filters, popup note editing/conflicts, IP browser links, device progress, and drops across all workspaces')
