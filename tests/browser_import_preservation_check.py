from browser_helpers import open_workspace, open_import_settings, set_import_confirmation, open_import_matching, start_import_review, choose_new_inventory_import
"""Preserve unmapped spreadsheet columns, stock progress, and chosen serial removal."""
import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from openpyxl import Workbook
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temporary:
    app.DB_PATH = Path(temporary) / 'inventory.sqlite3'
    inventory = app.save_equipment_inventory({'name': 'Spare Parts'})
    item = app.save_equipment(dict(inventory_id=inventory['id'], description='Camera', brand='Sony', model='X', quantity=3, serial_number='A, B, C', location='Locker', notes=''))
    with app.connect() as connection:connection.commit()
    server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium'))
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors=[]
            page.on('pageerror', lambda error: errors.append(str(error)))
            origin=f'http://127.0.0.1:{server.server_port}'
            page.goto(origin+'/')
            page.wait_for_function("() => !document.getElementById('import-file').disabled")
            data=b'VENUE\tSTATUS\tDEVICE NAME\tDEVICE LOCATION\tIP Address\tSUBNET\tGATEWAY\tVLAN\tNotes\nRD BROADCAST\tVALIDATED\tLIDO CAM\tLIDO DK9 MID\t10.24.176.33\t255.255.252.0\t10.24.179.254\t1500\tKeep this note\n'
            page.locator('#import-file').set_input_files({'name':'network.csv','mimeType':'text/csv','buffer':data})
            page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            notes=page.evaluate('mappedRows()[0].notes')
            assert notes.splitlines()==['Keep this note','STATUS VALIDATED','DEVICE LOCATION LIDO DK9 MID','SUBNET 255.255.252.0','GATEWAY 10.24.179.254'], notes
            page.evaluate("document.getElementById('map-notes').value='5'")
            notes=page.evaluate('mappedRows()[0].notes')
            assert notes.count('255.255.252.0')==1 and 'Notes Keep this note' in notes, notes
            page.goto(origin+'/inventory')
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            page.locator('#equipment-inventory-select').select_option(str(inventory['id']))
            page.wait_for_function("() => document.getElementById('equipment-stock-progress-count').textContent==='0 / 1 records (0%)'")
            assert page.locator('#equipment-stock-progress-count').inner_text()=='0 / 1 records (0%)'
            page.locator('#equipment-table .equipment-confirm').check()
            page.wait_for_function("() => document.getElementById('equipment-stock-progress-bar').value===1")
            assert page.locator('#equipment-table .equipment-confirm').is_checked()
            page.locator('#equipment-table .equipment-delete-action').click()
            choices=page.locator('#equipment-delete-unit')
            assert choices.locator('option').count()==4
            choices.select_option('serial:B')
            page.locator('#confirm-equipment-delete').click()
            page.wait_for_function("() => document.getElementById('equipment-delete-dialog').open===false")
            saved=app.equipment_inventory(inventory['id'])[0]
            assert (saved['quantity'],saved['serial_number'])==(2,'A, C'), saved
            assert page.locator('#equipment-stock-progress-count').inner_text()=='0 / 1 records (0%)'
            book=Workbook();book.active.title='Deck 9 Locker'
            book.active.append(['Description','Brand','Model','Serial Number','Quantity','Notes','Warranty'])
            book.active.append(['Camera','Sony','X','Z',1,'Original','2028'])
            book.create_sheet('Deck 10 Locker')
            path=Path(temporary)/'stock.xlsx';book.save(path)
            page.locator('#import-file').set_input_files(str(path))
            page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            row=page.evaluate('mappedRows()[0]')
            assert row['location']=='Deck 9 Locker', row
            assert row['notes']=='Original\nWarranty 2028', row
            assert page.locator('#sheet-choice option').count()==2
            page.screenshot(path='/tmp/avtrack-import-preservation.png',full_page=True)
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown();server.server_close()
print('PASS: unmapped notes, worksheet locations, stock progress and chosen serial removal')
