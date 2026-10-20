from browser_helpers import open_workspace
"""Recover stale browser files and report loading failures without losing server data."""
import shutil,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as temp:
    app.DB_PATH=Path(temp)/'inventory.sqlite3'
    saved=app.save_device(dict(name='Saved device',ip='10.20.1.1',vlan=1,venue='Studio',discipline='Video',notes='Keep me'))
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            origin=f'http://127.0.0.1:{server.server_port}'
            # A stalled optional reference cannot hold the overview or AV list hostage.
            context=browser.new_context(service_workers='block');page=context.new_page();held=[];errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.route('**/satellite-channels.json',lambda route:held.append(route))
            page.goto(origin+'/')
            page.wait_for_function("() => document.getElementById('overview-av-total').textContent.includes('1 device') && !document.getElementById('refresh').disabled")
            assert held and page.locator('.device-row').count()==1
            held[0].abort();page.wait_for_timeout(100)
            assert not errors,errors
            context.close()
            # A forwarded sign-in HTML page is displayed as an error, rather than JSON parsing noise.
            context=browser.new_context(service_workers='block');page=context.new_page()
            page.route('**/api/overview',lambda route:route.fulfill(status=200,content_type='text/html',body='<h1>Sign in</h1>'))
            page.goto(origin+'/');page.locator('#overview-error').wait_for(state='visible')
            assert 'page instead of inventory data' in page.locator('#overview-error').inner_text()
            assert page.locator('#overview-inventory-count').inner_text()=='Unavailable — use Refresh to retry'
            context.close()
            # A stalled API has a bounded wait and exposes the recovery action.
            context=browser.new_context(service_workers='block');page=context.new_page();held=[]
            page.route('**/api/overview',lambda route:held.append(route))
            page.goto(origin+'/');page.locator('#overview-error').wait_for(state='visible',timeout=25000)
            assert '20 seconds' in page.locator('#overview-error').inner_text()
            assert page.get_by_role('link',name='Reload workspace',exact=True).count()==0
            assert page.locator('#refresh').is_enabled()
            for route in held:route.abort()
            context.close()
            # Remove a real app worker and stale cache, preserving preferences and inventory.
            context=browser.new_context();page=context.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(origin+'/')
            page.evaluate('navigator.serviceWorker.ready.then(() => true)')
            page.reload();page.wait_for_function('() => !!navigator.serviceWorker.controller')
            page.evaluate("async () => {localStorage.setItem('recovery-test-preference','keep');await (await caches.open('avtrack-offline-stale')).put('/stale-marker',new Response('old'));}")
            page.goto(origin+'/recover');page.wait_for_url('**/?recovered=*')
            page.wait_for_function("() => !document.getElementById('refresh').disabled")
            assert 'avtrack-offline-stale' not in page.evaluate('caches.keys()')
            assert page.evaluate("localStorage.getItem('recovery-test-preference')")=='keep'
            assert app.inventory()[0]['id']==saved['id'] and len(app.inventory())==1
            open_workspace(page, 'equipment-tab')
            page.wait_for_function("() => !document.getElementById('new-equipment-inventory').disabled")
            page.locator('#new-equipment-inventory').click();page.locator('#equipment-inventory-dialog').wait_for(state='visible')
            assert not errors,errors
            context.close();browser.close()
    finally:server.shutdown();server.server_close()
print('Loading recovery passed: independent overview, stalled references and API timeout, readable errors, real worker/cache recovery, retained inventory/preferences and New inventory.')
