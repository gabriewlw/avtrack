"""Import 25 TVs through the current UI, verify its automatic backup, then restore it."""
import json, shutil, sys, tempfile, threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import workspace_transfer as transfer
from playwright.sync_api import sync_playwright, expect

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'autosave.sqlite3'
    templates=json.loads((Path(app.__file__).parent/'static/inventory-templates.json').read_text())
    tv=app.save_equipment_inventory(dict(name='TV import audit',layout=next(t['layout'] for t in templates if t['id']=='tv')))
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium') or None)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            origin=f'http://127.0.0.1:{server.server_port}'
            page.goto(origin+'/inventory')
            page.wait_for_function("()=>!document.getElementById('equipment-inventory-select').disabled")
            page.locator('#equipment-inventory-select').select_option(str(tv['id']))
            page.wait_for_function("()=>document.getElementById('equipment-inventory-title').textContent==='TV import audit'")
            csv='Brand,Model,Deck 6,Deck 2 Port,Deck 2 Stbd,Status,Notes\n'+''.join(
                f'LG,Model {i},1,0,0,New,Shelf A{i}\n' for i in range(25))
            page.locator('#equipment-import').click()
            with page.expect_file_chooser():page.locator('#upload-paste-inventory').click()
            page.locator('#import-file').set_input_files({'name':'inventory-audit.csv','mimeType':'text/csv','buffer':csv.encode()})
            page.locator('#paste-layout-dialog:visible, #spreadsheet-dialog:visible').first.wait_for()
            if page.locator('#paste-layout-dialog').is_visible():
                page.wait_for_function("()=>!document.getElementById('keep-paste-layout').disabled")
                page.locator('#keep-paste-layout').click()
            page.locator('#spreadsheet-dialog').wait_for(state='visible')
            page.wait_for_function("()=>!document.getElementById('confirm-import').disabled")
            page.locator('#import-complete-rows').uncheck()
            page.locator('#confirm-import').click()
            page.locator('#inventory-import-review').wait_for(state='visible')
            assert page.locator('#inventory-import-review-rows tr').count()==25
            page.locator('#inventory-import-review-save').click()
            page.locator('#import-summary-panel').wait_for(state='visible',timeout=60000)
            expect(page.locator('#import-summary-intro')).to_contain_text('Full backup saved automatically')
            expect(page.locator('#import-summary-intro')).to_contain_text('25 new inventory records')
            page.locator('#close-import-summary').click()
            page.wait_for_function("()=>document.getElementById('equipment-new-tv-units').textContent==='25'")
            files=list((app.DB_PATH.parent/'recovery').glob('*.zip'))
            assert len(files)==1,files
            saved=transfer.unpack(files[0].read_bytes())
            assert len(saved['tables']['equipment'])==25
            assert saved['tables']['import_sessions'][-1]['status']=='complete'
            assert all(json.loads(row['custom_values'])['unit_status']=='New' for row in saved['tables']['equipment'])
            app.save_equipment(dict(inventory_id=tv['id'],brand='LG',model='Later item',notes='Added after autosave',custom_values={'deck_6':'2'}))
            page.locator('#workspace-restore-open').click()
            expect(page.locator('#workspace-recovery-list')).to_contain_text(files[0].name)
            page.locator('#workspace-restore-file').set_input_files(str(files[0]))
            page.locator('#workspace-restore-replace').check()
            with page.expect_navigation():
                page.locator('#workspace-restore-submit').click()
            assert len(app.equipment_inventory(tv['id']))==25
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close()
print('PASS: 25-row TV UI import autosaves a complete backup; restore preserves counts, status and notes.')
