"""Shared full-width tables, content-aware columns, long rows and usable controls."""
from pathlib import Path
import shutil, sys, tempfile, threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'inventory.sqlite3'
    app.save_device(dict(name='Studio camera',venue='Studio',discipline='Video',ip='192.0.2.10',vlan=1500))
    app.save_device(dict(record_type='iptv',name='Sports demo',ip='239.1.1.10',port=1234,channel_source='Onboard'))
    app.save_equipment(dict(description='Panel',brand='BMD',model='Mini',serial_number='A1',quantity=1,location='Studio'))
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium') or None)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/inventory')
            page.locator('#equipment-rows tr').wait_for()
            page.evaluate('document.fonts.ready')
            table=page.locator('#equipment-table')
            short_width=table.bounding_box()['width']
            page.set_viewport_size({'width':1920,'height':1000})
            page.wait_for_timeout(250)
            wrap=page.locator('.equipment-table-wrap')
            assert abs(table.bounding_box()['width']-wrap.evaluate('(n)=>n.clientWidth'))<=2, 'Inventory must fill its available width'
            assert table.bounding_box()['width']>short_width, 'Table should grow with the workspace'
            long_name='Production switcher with advanced broadcast control and multiview monitoring'
            csv=Path(tmp)/'content-fit.csv'
            csv.write_text('Item,Brand,Model,Serial number,Quantity,Location,Notes\n'+long_name+',Blackmagic Design,ATEM Television Studio HD8 ISO,ATEM-HD8-001,1,Broadcast control room,With power supply\n')
            page.locator('#equipment-import').click()
            page.locator('#upload-paste-inventory').click()
            page.locator('#import-file').set_input_files(str(csv))
            page.locator('#paste-layout-dialog').wait_for(state='visible')
            page.wait_for_function("()=>!document.getElementById('keep-paste-layout').disabled")
            page.locator('#keep-paste-layout').click()
            page.locator('#spreadsheet-dialog').wait_for(state='visible')
            page.wait_for_function("()=>!document.getElementById('confirm-import').disabled")
            if page.locator('#import-complete-rows').is_checked():
                page.locator('#import-complete-rows').uncheck()
            page.locator('#confirm-import').click()
            page.locator('#inventory-import-review').wait_for(state='visible')
            page.locator('#inventory-import-review-save').click()
            page.locator('#import-summary-panel').wait_for(state='visible')
            page.locator('#close-import-summary').click()
            page.wait_for_function('(name)=>document.querySelector("#equipment-rows").textContent.includes(name)',arg=long_name)
            page.evaluate('document.fonts.ready')
            assert table.bounding_box()['width']>=wrap.evaluate('(n)=>n.clientWidth')-2
            assert page.locator('#equipment-rows tr').count()==2
            dimensions=page.evaluate("""() => {
                const table=document.querySelector('#equipment-table');
                const heads=[...table.querySelectorAll('th')];
                const rows=[...table.tBodies[0].rows];
                return heads.map((head,i)=>{
                    const cells=rows.map(row=>row.cells[i]);
                    const widths=[head,...cells].map(cell=>{
                        const range=document.createRange();range.selectNodeContents(cell);
                        return range.getBoundingClientRect().width;
                    });
                    return {label:head.textContent,width:head.getBoundingClientRect().width,
                        used:Math.max(...widths),aligned:cells.every(cell=>Math.abs(cell.getBoundingClientRect().x-head.getBoundingClientRect().x)<1)};
                });
            }""")
            for col in dimensions:
                assert col['aligned'], col
                assert col['width']>=col['used'], col
                if col['label'] in ['Notes','Actions']:
                    assert col['width']<180, col
            for control in page.locator('#equipment-rows .equipment-action-icon').all():
                assert control.bounding_box()['width']>=26
            assert page.locator('#equipment-rows tr').filter(has_text=long_name).locator('.equipment-brand-value > span').evaluate('(n)=>n.scrollWidth<=n.clientWidth+1')
            long_row=page.locator('#equipment-rows tr').filter(has_text=long_name)
            short_row=page.locator('#equipment-rows tr').filter(has_text='Panel')
            name_cell=long_row.locator('.inventory-text-value').first
            assert 35 <= name_cell.bounding_box()['height'] <= 55, name_cell.bounding_box()
            assert long_row.bounding_box()['height'] > short_row.bounding_box()['height']
            out=Path('work/screenshots');out.mkdir(parents=True,exist_ok=True)
            page.set_viewport_size({'width':1440,'height':1000})
            page.screenshot(path=str(out/'avtrack-imported-table-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.wait_for_timeout(250)
            overflow=page.evaluate("""()=>[...document.querySelectorAll('body *')].filter(n=>{
                const r=n.getBoundingClientRect();return r.width && r.right>innerWidth+1 &&
                !n.closest('.equipment-table-wrap,dialog,[hidden]');
            }).map(n=>({tag:n.tagName,id:n.id,cls:n.className,right:n.getBoundingClientRect().right,width:n.getBoundingClientRect().width})).slice(0,25)""")
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), overflow
            page.screenshot(path=str(out/'avtrack-imported-table-mobile.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            reference=wrap.bounding_box()
            reference_font=page.locator('#equipment-table th').first.evaluate('(n)=>getComputedStyle(n).fontFamily')
            origin=f'http://127.0.0.1:{server.server_port}'
            for route, label in [('/#av','devices'),('/#iptv','iptv')]:
                page.goto(origin+route)
                page.locator('.device-row').first.wait_for()
                directory=page.locator('#device-directory')
                box=directory.bounding_box()
                assert abs(box['x']-reference['x'])<2, (label,box,reference)
                assert abs(box['width']-reference['width'])<2, (label,box,reference)
                assert directory.evaluate('(n)=>n.scrollWidth<=n.clientWidth+1'), label
                assert page.locator('.directory-head').evaluate('(n)=>getComputedStyle(n).fontFamily')==reference_font
                page.screenshot(path=str(out/('avtrack-full-width-'+label+'.png')),full_page=True)
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close()
print('PASS: CSV import, shared full-width tables, content-aware columns, header alignment, wrapping and contained mobile scrolling')
