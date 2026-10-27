from browser_helpers import open_workspace, open_import_settings, set_import_confirmation, open_import_matching, start_import_review, choose_new_inventory_import
"""Desktop table density, column fit, controls and alignment with realistic data."""
from pathlib import Path
import json,shutil,sys,tempfile,threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'inventory.sqlite3'
    app.save_device(dict(name='Studio camera',venue='Broadcast Center',discipline='Video',ip='255.255.255.254',vlan=1500,notes='Example notes'))
    app.save_device(dict(name='Audio console',venue='Main Theatre',discipline='Audio',ip='192.0.2.15',vlan=1510))
    app.save_device(dict(record_type='iptv',name='News channel',ip='239.252.2.61',port=1234,channel_source='Satellite'))
    app.save_equipment(dict(description='Video switcher',brand='Blackmagic',model='ATEM Mini Pro',serial_number='ATEM-001',quantity=1,location='Broadcast Center',notes='With power supply'))
    templates=json.loads((app.ROOT/'static/inventory-templates.json').read_text())
    tv=app.save_equipment_inventory(dict(name='Spare TVs',layout=next(t['layout'] for t in templates if t['id']=='tv')))
    app.save_equipment(dict(inventory_id=tv['id'],brand='LG',model='24LV760M-UA',custom_values=dict(deck_6='3',deck_2_port='2',deck_2_stbd='0')))
    with app.connect() as connection:connection.commit()
    server = app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1280,'height':1000})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            origin=f'http://127.0.0.1:{server.server_port}'
            for width in [1280,1440]:
                page.set_viewport_size({'width':width,'height':1000})
                page.goto(origin+'/#av')
                page.wait_for_function("()=>document.querySelectorAll('.device-row').length===2")
                page.evaluate('document.fonts.ready')
                directory=page.locator('#device-directory')
                assert directory.evaluate('(node)=>node.scrollWidth<=node.clientWidth+1'),('Devices overflow',width)
                row=page.locator('.device-row').first
                assert row.bounding_box()['height']<=110,row.bounding_box()
                address=page.get_by_role('link',name='Open IP address in browser for Studio camera',exact=True).locator('..')
                assert address.evaluate('(node)=>node.scrollWidth<=node.clientWidth+1'),('IP controls overflow',width)
                confirm=page.get_by_role('button',name='Confirm IP for Studio camera',exact=True)
                assert confirm.is_visible()
                boxes=[address.locator('.ip-copy').bounding_box(),address.locator('.ip-browser').bounding_box(),confirm.bounding_box()]
                centers=[box['y']+box['height']/2 for box in boxes]
                assert max(centers)-min(centers)<1,boxes
                assert 0<=boxes[2]['x']-(boxes[1]['x']+boxes[1]['width'])<=8,boxes
                page.locator('#workspaces-toggle').click()
                open_workspace(page, 'iptv-tab')
                page.wait_for_function("()=>document.querySelectorAll('.device-row').length===1")
                assert directory.evaluate('(node)=>node.scrollWidth<=node.clientWidth+1'),('IPTV overflow',width)
                assert page.locator('.device-row').first.bounding_box()['height']<=110
                page.goto(origin+'/inventory')
                page.wait_for_function("()=>!document.getElementById('equipment-inventory-select').disabled")
                page.locator('#equipment-inventory-select').select_option('1')
                page.wait_for_function("()=>document.querySelector('#equipment-rows')?.textContent.includes('ATEM-001')")
                table=page.locator('#equipment-table')
                wrap=page.locator('.equipment-table-wrap')
                assert wrap.evaluate('(node)=>node.scrollWidth<=node.clientWidth+1'),('Inventory overflow',width)
                row=page.locator('#equipment-rows tr').first
                assert row.bounding_box()['height']<=110,row.bounding_box()
                assert row.locator('td').count()==table.locator('th').count()
                for button in row.locator('.equipment-actions button').all():
                    assert button.is_visible()
                    assert button.bounding_box()['width']>=26
                row.get_by_role('button',name='View equipment details',exact=True).click()
                page.locator('#desktop-record-dialog').wait_for(state='visible')
                page.locator('[data-close=desktop-record-dialog]').click()
                page.locator('#equipment-inventory-select').select_option(str(tv['id']))
                page.wait_for_function("()=>document.querySelector('#equipment-rows')?.textContent.includes('24LV760M-UA')")
                assert wrap.evaluate('(node)=>node.scrollWidth<=node.clientWidth+1'),('TV overflow',width)
                assert page.locator('#equipment-rows tr').first.locator('td').count()==table.locator('th').count()
            Path('work/artifacts').mkdir(parents=True,exist_ok=True)
            page.screenshot(path='work/artifacts/avtrack-compact-inventory.png')
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('PASS: compact rows, columns fit at 1280/1440px, long IP controls, inventory/TV alignment and working Details')
