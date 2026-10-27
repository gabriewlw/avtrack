"""Message-table and Excel pastes preserve separate batches, source values and notes."""
import json, shutil, sys, tempfile, threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from browser_helpers import open_import_matching, start_import_review, open_import_settings
from playwright.sync_api import sync_playwright, expect

with tempfile.TemporaryDirectory() as temporary:
    app.DB_PATH=Path(temporary)/'inventory.sqlite3'
    templates=json.loads((app.ROOT/'static/inventory-templates.json').read_text())
    tv=app.save_equipment_inventory(dict(name='Spare TVs',layout=next(t['layout'] for t in templates if t['id']=='tv')))
    parts=app.save_equipment_inventory(dict(name='Spare parts',layout=next(t['layout'] for t in templates if t['id']=='spare_parts')))
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium') or None)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/inventory')
            def choose(inventory):
                page.wait_for_function("()=>!document.getElementById('equipment-inventory-select').disabled")
                page.locator('#equipment-inventory-select').select_option(str(inventory['id']))
                page.wait_for_function("(name)=>document.getElementById('equipment-inventory-title').textContent===name&&!document.getElementById('equipment-inventory-select').disabled",arg=inventory['name'])
            def paste(text):
                page.locator('#equipment-import').click()
                page.locator('#paste-inventory-dialog').wait_for(state='visible')
                assert page.locator('#paste-inventory-text').input_value()==''
                assert page.locator('#continue-paste-inventory').is_disabled()
                page.locator('#paste-inventory-text').fill(text)
                page.locator('#continue-paste-inventory').click()
                page.locator('#paste-layout-dialog').wait_for(state='visible')
                page.wait_for_function("()=>!document.getElementById('paste-start-review').disabled")
                assert page.locator('#paste-layout-rows tr').count()<=5
            def save_group():
                page.locator('#inventory-import-review').wait_for(state='visible')
                page.locator('#inventory-import-review-all').check()
                page.locator('#inventory-import-review-save').click()
            def finish():
                page.locator('#import-summary-panel').wait_for(state='visible')
                page.locator('#close-import-summary').click()

            choose(tv)
            paste('''| Description | Model | Deck 6 Locker | Deck 2 Starboard | Deck 2 Port | Total Count | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 24" TV LG | A | 8 | 0 | 0 | 8 | Brand New |
| 32" TV LG | B | 7 | 0 | 0 | 2 | Used |
| 32" TV LG | B | 1 | 0 | 0 | 22 | Brand New |
| 49" TV LG | C | 0 | 0 | 0 | 0 | Used |
| 43" TV LG | D | 0 | 0 | 3 | 2 | Brand New |
| 43" TV Samsung | E | 0 | 0 | 1 | 1 | Sent for testing |
| 75" TV LG | F | 0 | 1 | 0 | 1 | Used / not in box |
| 32" SAMSUNG | G | 0 | 0 | 7 | 7 | Needs clone file |
''')
            assert app.equipment_inventory(tv['id'])==[]
            assert page.locator('#paste-merge-models').count()==0
            open_import_matching(page)
            assert page.locator('#map-model').input_value()=='1'
            assert page.locator('#map-deck_6').input_value()=='2'
            assert page.locator('#map-deck_2_stbd').input_value()=='3'
            assert page.locator('#map-deck_2_port').input_value()=='4'
            start_import_review(page)
            expect(page.locator('#inventory-import-review-rows tr')).to_have_count(8)
            assert app.equipment_inventory(tv['id'])==[]
            save_group();finish()
            saved=app.equipment_inventory(tv['id'])
            assert len(saved)==7 and sum(row['quantity'] for row in saved)==28
            batches=[row for row in saved if row['model']=='B']
            assert len(batches)==2 and sorted(row['quantity'] for row in batches)==[1,7]
            assert any('Used' in row['notes'] for row in batches)
            assert any('Brand New' in row['notes'] for row in batches)
            assert next(row for row in saved if row['model']=='E')['brand']=='Samsung'
            assert not any(row['model']=='C' for row in saved)

            choose(parts)
            paste('Description\tBrand\tModel\tSerial Number\tQuantity\tLocation\tNotes\nCable\tSony\tX\tS1\t1\tLocker A\tnote\nCable\tSony\tY\tS2\t1\tLocker B\tnote\n')
            start_import_review(page)
            title=page.locator('#inventory-import-review-title').inner_text()
            save_group()
            page.wait_for_function("(old)=>document.getElementById('inventory-import-review-title').textContent!==old",arg=title)
            save_group();finish()
            assert {row['location'] for row in app.equipment_inventory(parts['id'])}=={'Locker A','Locker B'}

            # Same brand/model/location/notes can be deliberately merged.
            paste('Description\tBrand\tModel\tSerial Number\tQuantity\tLocation\tNotes\nReceiver\tAtlona\tRX-1\t\t2\tLocker E\tSame batch\nReceiver\tAtlona\tRX-1\t\t3\tLocker E\tSame batch\n')
            assert not page.locator('#paste-merge-models').is_checked()
            open_import_settings(page)
            page.locator('#paste-merge-models').check()
            assert '1 item' in page.locator('#paste-preview-counts').inner_text()
            start_import_review(page)
            expect(page.locator('#inventory-import-review-rows tr')).to_have_count(1)
            assert page.get_by_label('Qnt, row 2, 3',exact=True).input_value()=='5'
            save_group();finish()
            merged=next(row for row in app.equipment_inventory(parts['id']) if row['model']=='RX-1')
            assert merged['quantity']==5 and not merged['serial_number']
            assert merged['notes']=='Same batch · Combined source rows: 2, 3', merged['notes']

            # Different notes remain separate, including quantity annotations.
            paste('Description\tBrand\tModel\tSerial Number\tQuantity\tLocation\tNotes\nReceiver\tAtlona\tRX-2\t\t2 USED\tLocker E\tFirst\nReceiver\tAtlona\tRX-2\t\t3\tLocker E\tSecond\n')
            assert page.locator('#paste-merge-models').count()==0
            assert 'extra text to review' in page.locator('#paste-field-analysis').inner_text()
            start_import_review(page)
            expect(page.locator('#inventory-import-review-rows tr')).to_have_count(2)
            save_group();finish()
            separate=[row for row in app.equipment_inventory(parts['id']) if row['model']=='RX-2']
            assert len(separate)==2 and sum(row['quantity'] for row in separate)==5
            assert any('2 USED' in row['notes'] for row in separate)
            assert any('Second' in row['notes'] for row in separate)
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close()
print('PASS: message/Excel pastes, mappings, calculated counts, zero skips, inferred brands, explicit review, separate notes and deliberate merges.')
