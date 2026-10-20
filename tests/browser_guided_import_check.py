from browser_helpers import open_workspace
"""Desktop import drafts, batch IPs, resume, workbook queues and saved reports."""
import json,shutil,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from openpyxl import Workbook
from playwright.sync_api import sync_playwright
TEMPLATES=json.loads((Path(app.__file__).parent/'static/inventory-templates.json').read_text())
with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'inventory.sqlite3'
    parts=app.save_equipment_inventory(dict(name='Review parts',layout=next(t['layout'] for t in TEMPLATES if t['id']=='spare_parts')))
    tv=app.save_equipment_inventory(dict(name='Review TVs',layout=next(t['layout'] for t in TEMPLATES if t['id']=='tv')))
    book=Workbook();sheet=book.active;sheet.title='Locker A';sheet.append(['Title']);sheet.append([]);sheet.append(['Column1','Column2']);sheet.append([])
    sheet.append(['Description','Brand','Model','Serial Number','Quantity','Location','Notes'])
    sheet.append(['Cable','LG','A','0001',1,'','note'])
    other=book.create_sheet('Locker B');other.append(['Model','Description','Brand','Quantity','Serial Number','Location','Notes']);other.append(['B','Cable','LG',1,'0002','','note'])
    file=Path(tmp)/'inventory.xlsx';book.save(file)
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.wait_for_function("() => !document.getElementById('refresh').disabled")
            open_workspace(page, 'device-tab')
            def paste(text,mode=None):
                page.locator('#import' if page.locator('#equipment-panel').is_hidden() else '#equipment-import').click()
                page.locator('#paste-inventory-text').fill(text);page.locator('#continue-paste-inventory').click()
                page.wait_for_function("() => document.getElementById('paste-location-dialog').open || document.getElementById('paste-layout-dialog').open")
                if page.locator('#paste-location-dialog').is_visible():
                    page.locator('#paste-batch-location').fill('Shelf');page.locator('#continue-paste-location').click()
                page.locator('#paste-layout-dialog').wait_for(state='visible')
                page.wait_for_function("() => !document.getElementById('paste-start-review').disabled")
                if mode:page.locator('#paste-preview-confirmation').select_option(mode)
                page.locator('#paste-layout-dialog').wait_for(state='visible')
                page.wait_for_function("() => !document.getElementById('keep-paste-layout').disabled")
                assert not errors,errors
                page.locator('#keep-paste-layout').click()
            paste('Device Name\tIP Address\tVenue\tVLAN\tNotes\nFirst\t10.20.1.1\tStudio\t50\tlong notes\nSecond\tbad-ip\tStudio\t50\t', 'none')
            page.locator('#confirm-import').click()
            try:page.locator('#inventory-import-review').wait_for(state='visible',timeout=5000)
            except Exception:
                print('UI ERROR:',page.locator('#spreadsheet-error').inner_text(),'JS:',errors,'ACTIVE:',page.evaluate("document.querySelectorAll('#import-workspace section:not([hidden])').length"));raise
            assert page.locator('#inventory-import-review-rows tr').count()==2
            assert page.locator('#inventory-import-review-save').inner_text()=='Import selected (1)'
            page.get_by_role('button',name='Edit notes for row 2',exact=True).click();page.locator('#import-cell-notes-text').fill('Edited floating notes');page.locator('#apply-import-cell-notes').click()
            page.locator('#inventory-import-review-save').click()
            page.wait_for_function("() => document.querySelectorAll('.batch-row-done').length===1")
            page.locator('#inventory-import-review-stop').click();page.locator('#import-summary-panel').wait_for(state='visible')
            assert app.inventory()[0]['notes']=='Edited floating notes'
            assert app.inventory()[0]['confirmation_required']==0
            page.reload();page.locator('#import').click();page.get_by_role('button',name='Resume previous import',exact=True).click()
            page.locator('#spreadsheet-dialog').wait_for(state='visible');page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            page.locator('#confirm-import').click();page.locator('#inventory-import-review').wait_for(state='visible')
            assert page.locator('#inventory-import-review-rows tr').count()==1
            page.get_by_label('IP address, row 3',exact=True).fill('10.20.1.2');page.get_by_label('Select row 3',exact=True).check()
            page.locator('#inventory-import-review-save').click();page.locator('#import-summary-panel').wait_for(state='visible')
            assert len(app.inventory())==2
            assert 'Import complete' in page.locator('#import-summary-title').inner_text()
            assert page.locator('#import-summary-close-action').is_visible()
            assert 'Start another Excel paste' in page.locator('#import-summary-add-option').inner_text()
            page.locator('#import-summary-close-action').click()
            # Each new paste can reorder, rename, add or omit headings independently.
            page.locator('#import').click()
            page.locator('#paste-inventory-text').fill('Notes\tIP Address\tDevice Name\tMaintenance owner\nnew note\t10.20.1.3\tThird\tTara')
            page.locator('#continue-paste-inventory').click()
            page.wait_for_function("() => document.getElementById('paste-layout-dialog').open || document.getElementById('paste-confirmation-dialog').open")
            if page.locator('#paste-confirmation-dialog').is_visible():page.locator('#continue-paste-confirmation').click()
            page.locator('#paste-layout-dialog').wait_for(state='visible')
            page.wait_for_function("() => !document.getElementById('keep-paste-layout').disabled")
            page.locator('#keep-paste-layout').click()
            assert page.locator('#map-ip').input_value()=='1'
            assert page.locator('#map-name').input_value()=='2'
            assert page.locator('#map-venue').input_value()==''
            assert '1 new headings' in page.locator('#import-source-changes').inner_text()
            assert '2 previous headings absent' in page.locator('#import-source-changes').inner_text()
            page.locator('#reset-import-suggestions').click()
            assert page.locator('#map-ip').input_value()=='1'
            assert page.locator('#map-name').input_value()=='2'
            page.locator('#cancel-spreadsheet').click()
            assert len(app.inventory())==2
            open_workspace(page, 'equipment-tab')
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            page.locator('#equipment-inventory-select').select_option(str(parts['id']));page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            # A different confirmation choice stays a draft if the user cancels.
            before=next(i for i in app.equipment_inventories() if i['id']==parts['id'])
            paste('Description\tBrand\tModel\tSerial Number\tQuantity\tLocation\tNotes\nCable\tLG\tX\tS1\t1\tShelf\tnote','none')
            page.locator('#cancel-spreadsheet').click()
            assert next(i for i in app.equipment_inventories() if i['id']==parts['id'])==before
            # Whole workbook: header detection, per-sheet matching and blank-location defaults.
            page.locator('#equipment-import').click();page.locator('#upload-paste-inventory').click();page.locator('#import-file').set_input_files(str(file))
            page.locator('#spreadsheet-dialog').wait_for(state='visible');page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            assert page.locator('#header-row').input_value()=='5'
            page.locator('#import-sheet-choices input[value="Locker B"]').check()
            page.locator('#confirm-import').click()
            page.wait_for_function("() => document.getElementById('sheet-choice').value==='Locker B' && !document.getElementById('confirm-import').disabled")
            assert page.locator('#map-model').input_value()=='0'
            page.locator('#confirm-import').click();page.locator('#import-summary-panel').wait_for(state='visible')
            rows=app.equipment_inventory(parts['id']);assert len(rows)==2,rows
            assert {r['location'] for r in rows}=={'Locker A','Locker B'}
            assert {r['serial_number'] for r in rows}=={'0001','0002'}
            page.locator('#import-summary-compare').click();page.wait_for_function("() => document.getElementById('import-summary-comparison').textContent.includes('matched')")
            assert '2 matched' in page.locator('#import-summary-comparison').inner_text()
            with page.expect_download() as download:page.locator('#import-summary-download').click()
            report=json.loads(Path(download.value.path()).read_text())
            assert len(report['receipts'])==2 and report['reconciliation']['complete']
            assert 'state' not in report
            assert not errors,errors
            page.screenshot(path=str(Path(app.__file__).parent/'work/guided-import-summary.png'),full_page=True)
            page.reload()
            assert page.locator('#import-history-panel').count()==0
            page.locator('#equipment-inventory-select').select_option(str(tv['id']));page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            row=app.save_equipment(dict(inventory_id=tv['id'],brand='LG',model='TV1',custom_values={'deck_6':'2','deck_2_port':'0','deck_2_stbd':'0'}))
            page.locator('#equipment-refresh').click();page.wait_for_function("() => document.getElementById('equipment-records').textContent==='1'")
            assert page.get_by_role('button',name='Confirm stock check for TV1',exact=True).inner_text()=='Never checked'
            assert app.equipment_inventory(tv['id'])[0]['last_checked_at'] is None
            app.delete_equipment_inventory(parts['id'],{'name':parts['name']})
            page.reload();assert page.locator('#import-history-panel').count()==0
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('Guided desktop import: draft cancellation, batch IP edit/notes, reload resume, multi-sheet headers/mappings, reports, comparison and TV stock checks passed.')
