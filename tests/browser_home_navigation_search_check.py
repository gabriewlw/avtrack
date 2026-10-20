"""Home summary, workspace navigation and exact search links across workspaces."""
from pathlib import Path
import base64,json,shutil,sys,tempfile,threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'inventory.sqlite3'
    device=app.save_device(dict(name='Target camera',venue='Studio',discipline='Video',ip='192.0.2.8'))
    channel=app.save_device(dict(record_type='iptv',name='Target channel',ip='239.252.2.61',port=1234,channel_source='Satellite'))
    app.save_equipment(dict(description='Other item',serial_number='OTHER',quantity=1))
    templates=json.loads((app.ROOT/'static/inventory-templates.json').read_text())
    tv=app.save_equipment_inventory(dict(name='TV inventory',layout=next(t['layout'] for t in templates if t['id']=='tv')))
    item=app.save_equipment(dict(inventory_id=tv['id'],brand='LG',model='Target screen',custom_values=dict(deck_6='0',deck_2_port='0',deck_2_stbd='0')))
    backup=app.save_av_backup(dict(equipment_type='ATEM',device_name='Target backup',filename='setup.xml',notes='',content=base64.b64encode(b'<setup/>').decode()))
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            origin=f'http://127.0.0.1:{server.server_port}'
            page.goto(origin)
            page.wait_for_function("()=>document.getElementById('overview-av-total').textContent==='0 of 1 device'")
            assert page.locator('#home-tab').get_attribute('aria-current')=='page'
            assert page.locator('#homepage-overview').is_visible()
            assert page.locator('#inventory').is_hidden()
            assert page.locator('.hero-side').is_hidden()
            assert page.locator('#device-tab').is_hidden()
            page.locator('#workspaces-toggle').click()
            assert page.locator('#device-tab').is_visible()
            page.keyboard.press('Escape')
            assert page.locator('#device-tab').is_hidden()
            assert page.locator('#workspaces-toggle').evaluate('(node)=>node===document.activeElement')
            Path('/workspace/artifacts').mkdir(exist_ok=True)
            page.screenshot(path='/workspace/artifacts/avtrack-home-clean.png')
            page.locator('#workspaces-toggle').click();page.locator('#device-tab').click()
            assert page.locator('#inventory').is_visible()
            assert not page.locator('#workspaces-menu').evaluate('(node)=>node.open')
            assert page.locator('#workspaces-toggle').get_attribute('aria-current')=='page'
            page.locator('#search').fill('No matching camera')
            cases=[('Target camera',device,'device'),('Target channel',channel,'iptv'),('Target screen',item,'equipment'),('Target backup',backup,'backup')]
            for query,row,kind in cases:
                page.locator('#desktop-find').fill(query)
                page.locator('#header-search button').click()
                link=page.locator('#desktop-search-results .search-workspace-link')
                link.wait_for()
                href=link.get_attribute('href')
                assert f'record={kind}%3A{row["id"]}' in href
                link.click()
                page.wait_for_selector('.search-target')
                if kind=='equipment':
                    assert page.locator('#equipment-inventory-select').input_value()==str(tv['id'])
                    assert page.locator('#equipment-show-zero').is_checked()
                    assert page.locator('.search-target').get_attribute('data-item-id')==str(row['id'])
                elif kind=='backup':
                    assert page.locator('.search-target').get_attribute('data-backup-id')==str(row['id'])
                else:
                    assert page.locator('.search-target .row-select').get_attribute('data-record-id')==str(row['id'])
                    assert page.locator('#search').input_value()==''
                # The URL also works after reload or when opened in a fresh tab.
                page.reload();page.wait_for_selector('.search-target')
                assert query in page.locator('.search-target').inner_text()
                page.locator('#home-tab').click()
                assert page.locator('#homepage-overview').is_visible()
                assert page.locator('#inventory').is_hidden()
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('PASS: clean summary homepage, workspace menu/keyboard, exact asset links, zero-stock inventory, reload and all four workspaces')
