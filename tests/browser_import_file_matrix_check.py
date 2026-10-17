"""Every supported file type imports through each desktop workspace."""
import json,shutil,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from openpyxl import Workbook
from playwright.sync_api import sync_playwright

TEMPLATES=json.loads((Path(app.__file__).parent/'static/inventory-templates.json').read_text())

def workbook(path,headers,row):
    book=Workbook();sheet=book.active;sheet.title='Import';sheet.append(headers);sheet.append(row);book.save(path)

with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp);app.DB_PATH=tmp/'test.sqlite3'
    inventory=app.save_equipment_inventory(dict(name='Import matrix',layout=next(t['layout'] for t in TEMPLATES if t['id']=='spare_parts')))
    files={}
    files['device_csv']=tmp/'devices.csv';files['device_csv'].write_text('Device Name,IP Address,Venue,VLAN,Notes\nCSV switcher,10.20.0.1,Control room,10,CSV\n')
    files['device_xlsx']=tmp/'devices.xlsx';workbook(files['device_xlsx'],['Device Name','IP Address','Venue','VLAN','Notes'],['XLSX switcher','10.20.0.2','Control room',20,'XLSX'])
    files['device_json']=tmp/'devices.json';files['device_json'].write_text(json.dumps({'version':1,'devices':[{'name':'JSON switcher','ip':'10.20.0.3','venue':'Control room','vlan':30,'record_type':'device'}]}))
    files['iptv_csv']=tmp/'iptv.csv';files['iptv_csv'].write_text('Channel Name,Multicast IP,Port,Venue,Notes\nCSV channel,239.20.0.1,1201,Headend,CSV\n')
    files['iptv_xlsx']=tmp/'iptv.xlsx';workbook(files['iptv_xlsx'],['Channel Name','Multicast IP','Port','Venue','Notes'],['XLSX channel','239.20.0.2',1202,'Headend','XLSX'])
    files['iptv_json']=tmp/'iptv.json';files['iptv_json'].write_text(json.dumps({'version':1,'devices':[{'name':'JSON channel','ip':'239.20.0.3','port':1203,'venue':'Headend','record_type':'iptv'}]}))
    files['equipment_csv']=tmp/'equipment.csv';files['equipment_csv'].write_text('Description,Brand,Model,Serial Number,Quantity,Location,Notes\nCSV cable,Extron,CSV-100,CSV-1,1,Locker A,CSV\n')
    files['equipment_xlsx']=tmp/'equipment.xlsx';workbook(files['equipment_xlsx'],['Description','Brand','Model','Serial Number','Quantity','Location','Notes'],['XLSX cable','Extron','XLSX-100','XLSX-1',1,'Locker A','XLSX'])
    files['equipment_json']=tmp/'equipment.json';files['equipment_json'].write_text(json.dumps({'version':1,'equipment':[{'description':'JSON cable','brand':'Extron','model':'JSON-100','serial_number':'JSON-1','quantity':1,'location':'Locker A'}]}))
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/');page.wait_for_function("() => !document.getElementById('refresh').disabled")

            def upload_guided(path,equipment=False):
                page.locator('#equipment-paste' if equipment else '#network-paste').click()
                page.locator('#upload-paste-inventory').click();page.locator('#import-file').set_input_files(str(path))
                page.locator('#spreadsheet-dialog').wait_for(state='visible');page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
                if equipment and page.locator('#import-complete-rows').is_checked():page.locator('#import-complete-rows').uncheck()
                page.locator('#confirm-import').click();page.locator('#inventory-import-review').wait_for(state='visible')
                page.locator('#inventory-import-review-save').click();page.locator('#import-summary-panel').wait_for(state='visible',timeout=7000)
                assert page.locator('#import-summary-title').inner_text()=='Import complete';page.locator('#close-import-summary').click()

            def upload_json(path,equipment=False):
                page.locator('#equipment-paste' if equipment else '#network-paste').click()
                page.locator('#upload-paste-inventory').click();page.locator('#import-file').set_input_files(str(path))

            page.locator('#device-tab').click()
            upload_guided(files['device_csv']);upload_guided(files['device_xlsx']);upload_json(files['device_json'])
            page.wait_for_function("() => document.getElementById('total').textContent === '3'")
            page.locator('#iptv-tab').click()
            upload_guided(files['iptv_csv']);upload_guided(files['iptv_xlsx']);upload_json(files['iptv_json'])
            page.wait_for_function("() => document.getElementById('total').textContent === '3'")
            page.locator('#equipment-tab').click();page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            page.locator('#equipment-inventory-select').select_option(str(inventory['id']));page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            upload_guided(files['equipment_csv'],True);upload_guided(files['equipment_xlsx'],True);upload_json(files['equipment_json'],True)
            page.wait_for_function("() => document.getElementById('equipment-records').textContent === '3'")
            records=app.inventory();equipment=app.equipment_inventory(inventory['id'])
            assert {(row['record_type'],row['name']) for row in records}=={
                ('device','CSV switcher'),('device','XLSX switcher'),('device','JSON switcher'),
                ('iptv','CSV channel'),('iptv','XLSX channel'),('iptv','JSON channel')}
            assert {row['serial_number'] for row in equipment}=={'CSV-1','XLSX-1','JSON-1'}
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('CSV, XLSX and JSON imports passed in Devices, IPTV and Inventory.')
