"""Static homepage, compact imagery, workspace titles, and screenshot regression."""
from pathlib import Path
import os, shutil, sys, tempfile, threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH = Path(tmp) / 'inventory.sqlite3'
    server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium') or None)
            page = browser.new_page(viewport={'width':1440,'height':1100})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            origin = f'http://127.0.0.1:{server.server_port}'
            page.goto(origin)
            page.locator('#home-empty-state').wait_for(state='visible')
            page.evaluate('document.fonts.ready')
            title = page.locator('#hero-title')
            assert title.inner_text() == 'Every device. Every stream.\nEvery venue. All in one place.'
            assert page.locator('.hero-typewriter-cursor').count() == 0
            assert title.evaluate('(n)=>getComputedStyle(n).textAlign') == 'center'
            assert float(title.evaluate('(n)=>parseFloat(getComputedStyle(n).fontSize)')) >= 50
            original = title.inner_text()
            page.wait_for_timeout(600)
            assert title.inner_text() == original
            image = page.locator('#example-media img')
            assert image.evaluate('(n)=>n.complete && n.naturalWidth > 0')
            assert image.bounding_box()['width'] <= 240
            empty = page.locator('#home-empty-state').bounding_box()
            overview = page.locator('#homepage-overview').bounding_box()
            assert empty['y'] - (overview['y'] + overview['height']) >= 40
            out = Path(os.environ.get('AVTRACK_SCREENSHOT_DIR', 'work/screenshots'))
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out/'avtrack-home-desktop.png'), full_page=True)
            for path, heading in [('/#av','AV devices'),('/#iptv','IPTV channels'),('/inventory','Equipment inventory'),('/backups','Configuration backups')]:
                page.goto(origin+path)
                page.wait_for_function('(text)=>document.querySelector("#hero-title").textContent===text', arg=heading)
                title.wait_for(state='visible')
                assert title.bounding_box()['height'] < 80
                assert 'One clear view.' not in title.inner_text()
                page.screenshot(path=str(out/(heading.lower().replace(' ','-')+'.png')), full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.goto(origin)
            page.locator('#home-empty-state').wait_for(state='visible')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(out/'avtrack-home-mobile.png'), full_page=True)
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
print('PASS: static centered homepage, spacing, compact image, workspace headers, mobile layout')
