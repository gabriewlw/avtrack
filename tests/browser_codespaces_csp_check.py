"""Allow the private-port sign-in endpoint without permitting unrelated connections."""
import os,shutil,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as temp:
    app.DB_PATH=Path(temp)/'inventory.sqlite3'
    original=os.environ.get('CODESPACES')
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            origin=f'http://127.0.0.1:{server.server_port}'
            for enabled in (False,True):
                os.environ['CODESPACES']='true' if enabled else 'false'
                context=browser.new_context(service_workers='block');page=context.new_page();requests=[];errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                def authentication(route):
                    requests.append(route.request.url)
                    route.fulfill(status=200,body='Authentication fixture',headers={'Access-Control-Allow-Origin':origin})
                page.route('https://github.dev/**',authentication)
                page.goto(origin+'/inventory')
                page.wait_for_function("() => !document.getElementById('new-equipment-inventory').disabled")
                page.locator('#new-equipment-inventory').click()
                page.locator('#equipment-inventory-dialog').wait_for(state='visible')
                page.locator('#cancel-equipment-inventory').click()
                def connect(url):
                    return page.evaluate("async url => {try{return (await fetch(url)).ok;}catch(error){return false;}}",url)
                assert connect('https://github.dev/pf-signin?id=test')==enabled
                assert not connect('https://github.dev/unrelated')
                assert requests==(['https://github.dev/pf-signin?id=test'] if enabled else []),requests
                assert not errors,errors
                context.close()
            browser.close()
    finally:
        server.shutdown();server.server_close()
        if original is None:os.environ.pop('CODESPACES',None)
        else:os.environ['CODESPACES']=original
print('Codespaces CSP browser check passed: sign-in endpoint allowed only in Codespaces, unrelated connections blocked, inventory and New inventory load correctly.')
