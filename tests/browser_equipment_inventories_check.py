from browser_helpers import open_workspace
"""Optional browser check of independent inventory creation and CSV/JSON work."""
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temp:
    app.DB_PATH = Path(temp) / 'inventory.sqlite3'
    server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium') or None)
            page = browser.new_page(viewport={'width':1440,'height':1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}')
            assert page.locator('#equipment-tab').text_content() == 'Inventory'
            open_workspace(page, 'equipment-tab')
            page.wait_for_function("() => !document.getElementById('new-equipment-inventory').disabled")

            def wait_loaded(name):
                page.wait_for_function("name => !document.getElementById('equipment-inventory-select').disabled && document.getElementById('equipment-inventory-title').textContent === name", arg=name)

            def create(name):
                page.locator('#new-equipment-inventory').click()
                page.locator('#equipment-inventory-name').fill(name)
                page.locator('#save-equipment-inventory').click()
                page.locator('#equipment-inventory-dialog').wait_for(state='hidden')
                wait_loaded(name)
                assert page.locator('#equipment-empty').is_visible()
                if page.locator('#paste-inventory-dialog').is_visible():
                    page.locator('#close-paste-inventory').click()
                return int(page.locator('#equipment-inventory-select').input_value())

            def import_csv(filename, rows):
                file = Path(temp) / filename
                file.write_text('Item,Brand,Model,Serial number,Quantity,Location,Notes\n'+rows)
                page.locator('#import-file').set_input_files(str(file))
                page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
                target = page.locator('#equipment-inventory-title').inner_text()
                assert 'Inventory: '+target in page.locator('#spreadsheet-summary').inner_text()
                page.locator('#import-confirmation-choice').select_option('storage')
                page.locator('#confirm-import').click()
                locations={line.split(',')[5] for line in rows.strip().splitlines()}
                for index in range(len(locations)):
                    page.locator('#inventory-import-review').wait_for(state='visible')
                    title=page.locator('#inventory-import-review-title').inner_text()
                    page.locator('#inventory-import-review-all').check();page.locator('#inventory-import-review-save').click()
                    if index<len(locations)-1:page.wait_for_function('previous => document.getElementById("inventory-import-review-title").textContent !== previous',arg=title)
                    else:page.locator('#inventory-import-review').wait_for(state='hidden')
                wait_loaded(target)
                page.locator('#import-summary-panel').wait_for(state='visible')
                page.locator('#close-import-summary').click()

            def download(label, scope):
                dropdown = page.locator('#equipment-panel .export-dropdown')
                if dropdown.get_attribute('open') is None:
                    dropdown.locator('summary').click()
                page.locator('#equipment-export-scope').select_option(scope)
                with page.expect_download() as result:
                    page.locator('#equipment-panel').get_by_role('link', name=label+' ↓', exact=True).click()
                return result.value

            tvs = create('TVs')
            import_csv('tvs.csv', 'Lounge TV,Sony,Bravia,ASSET-01,1,Main lounge,Wall mount\n'
                       'Cabin TV,Samsung,Q60,ASSET-02,1,Cabin 100,Remote included\n')
            assert len(app.equipment_inventory(tvs)) == 2
            assert page.locator('#workspace-page-summary').text_content() == '2 items across 2 locations'
            assert app.equipment_inventory() == []
            page.locator('#equipment-location-filter').select_option('Main lounge')
            page.locator('#equipment-rows .ip-confirm').click()
            page.wait_for_function("() => document.getElementById('equipment-found').textContent === '1'")
            page.locator('#equipment-rows .row-select').check()
            selected = json.loads(Path(download('JSON','selected').path()).read_text())
            assert selected['inventory_name'] == 'TVs' and len(selected['equipment']) == 1
            assert selected['equipment'][0]['item_confirmed'] == 1
            # All must also include items added by another browser since refresh.
            extra = app.save_equipment(dict(description='New TV', serial_number='ASSET-03', inventory_id=tvs))
            latest = json.loads(Path(download('JSON', 'all').path()).read_text())
            assert len(latest['equipment']) == 3 and any(row['id'] == extra['id'] for row in latest['equipment'])
            with app.connect() as con:
                con.execute('DELETE FROM equipment WHERE id=?', (extra['id'],))
            all_tvs = download('JSON', 'all')
            assert all_tvs.suggested_filename == 'avtrack-tvs.json'
            exported = json.loads(Path(all_tvs.path()).read_text())
            assert len(exported['equipment']) == 2
            assert {row['inventory_id'] for row in exported['equipment']} == {tvs}
            pdf = Path(download('PDF', 'filtered').path()).read_bytes()
            if shutil.which('pdftotext'):
                text = subprocess.run(['pdftotext','-','-'], input=pdf, capture_output=True, check=True).stdout.decode()
                assert 'TVs' in text and 'Main lounge' in text
                assert 'Cabin 100' not in text
            scalas = create('Media players')
            assert page.locator('#equipment-location-filter').input_value() == ''
            assert page.locator('#equipment-selection-summary').is_hidden()
            import_csv('scalas.csv', 'Scala player,Scala,Media player,ASSET-01,1,Theater,\n')
            assert len(app.equipment_inventory(scalas)) == 1
            assert page.locator('#equipment-found').inner_text() == '0'
            assert page.locator('#workspace-page-summary').text_content() == '1 item across 1 location'
            page.locator('#rename-equipment-inventory').click()
            page.locator('#equipment-inventory-name').fill('Signage players')
            page.locator('#save-equipment-inventory').click()
            wait_loaded('Signage players')
            assert int(page.locator('#equipment-inventory-select').input_value()) == scalas
            assert page.locator('#equipment-rows tr').count() == 1
            spare = create('Spare parts')
            json_file = Path(temp) / 'tvs.json'
            json_file.write_text(json.dumps(exported))
            page.locator('#import-file').set_input_files(str(json_file))
            page.wait_for_function("() => document.getElementById('equipment-records').textContent === '2'")
            assert {row['inventory_id'] for row in app.equipment_inventory(spare)} == {spare}
            assert page.locator('#equipment-found').inner_text() == '1'
            page.locator('#add-device').click()
            page.locator('#equipment-description').fill('USB cable')
            page.locator('#equipment-model').fill('USB-C')
            page.locator('#equipment-location').locator('xpath=..').get_by_role('button', name='New location').click()
            page.get_by_label('New storage location').fill('Storeroom')
            page.locator('#equipment-location').locator('xpath=..').get_by_role('button', name='Add location').click()
            page.locator('#save-equipment').click()
            page.locator('#equipment-dialog').wait_for(state='hidden')
            page.wait_for_function("() => document.getElementById('equipment-records').textContent === '3'")
            page.locator('#equipment-inventory-select').select_option(str(tvs))
            wait_loaded('TVs')
            assert page.locator('#equipment-rows tr').count() == 2
            assert page.locator('#equipment-found').inner_text() == '1'
            assert 'Storeroom' not in page.locator('#equipment-location-filter').inner_text()
            page.reload()
            open_workspace(page, 'equipment-tab')
            wait_loaded('TVs')
            assert page.locator('#equipment-rows tr').count() == 2
            for width in [1440,1024,901,900,390,320]:
                page.set_viewport_size({'width':width,'height':1000})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                assert page.locator('#equipment-inventory-select').is_visible()
                if width > 900:
                    assert page.locator('.equipment-confirm-label').evaluate_all('nodes => nodes.every(node => {const control=node.getBoundingClientRect(), cell=node.closest("td").getBoundingClientRect();return control.right <= cell.right && control.left >= cell.left;})'), width
            assert not errors, errors
            browser.close()
            print('PASS: create/rename, separate CSV imports, duplicate serials across inventories, scoped location/selected/all reports, JSON destination, manual additions, retained checks, remembered inventory, desktop/mobile layouts.')
    finally:
        server.shutdown()
        server.server_close()
