"""Landing sections blend continuously and scrolling remains native and accessible."""
from pathlib import Path
import shutil, sys, tempfile, threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'landing.sqlite3'
    with app.connect() as connection:connection.commit()
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium') or None)
            for width in (1440,390):
                for reduced in (False,True):
                    context=browser.new_context(viewport={'width':width,'height':900},
                        reduced_motion='reduce' if reduced else 'no-preference')
                    page=context.new_page();errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{server.server_port}/avtrack')
                    page.evaluate('document.fonts.ready')
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    for selector in ('.purpose','.closing','.showcase-footer'):
                        assert page.locator(selector).evaluate('(n)=>parseFloat(getComputedStyle(n).borderTopWidth)')==0
                    assert page.locator('.capabilities').evaluate('(n)=>getComputedStyle(n).backgroundImage')=='none'
                    assert page.locator('html').evaluate('(n)=>getComputedStyle(n).scrollBehavior')==('auto' if reduced else 'smooth')
                    # Wheel input stays under browser control; no artificial scroll lag.
                    page.mouse.wheel(0,600)
                    page.wait_for_function('()=>scrollY>=500 && scrollY<1000')
                    assert page.locator('.ambient-one').evaluate('(n)=>n.style.transform')==''
                    if width==1440:
                        page.get_by_role('link',name='Workflow',exact=True).click()
                        page.wait_for_function("()=>{const y=document.querySelector('#workflow').getBoundingClientRect().top;return y>=70&&y<=90}")
                        assert page.locator('.showcase-nav').bounding_box()['y']==0
                    else:
                        page.locator('#capabilities').scroll_into_view_if_needed()
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    if not reduced:
                        out=Path('work/screenshots');out.mkdir(parents=True,exist_ok=True)
                        page.screenshot(path=str(out/f'avtrack-landing-scroll-{width}.png'))
                    assert not errors,errors
                    context.close()
            browser.close()
    finally:
        server.shutdown();server.server_close()
print('PASS: continuous landing backgrounds, native wheel input, smooth anchors, mobile and reduced motion.')
