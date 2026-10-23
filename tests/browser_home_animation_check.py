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
            add = page.locator('.overview-add').first
            add.hover()
            card = page.locator('.overview-card').first
            assert add.evaluate('(n)=>getComputedStyle(n).backgroundColor') != card.evaluate('(n)=>getComputedStyle(n).backgroundColor')
            assert add.evaluate('(n)=>getComputedStyle(n).borderColor') != card.evaluate('(n)=>getComputedStyle(n).borderColor')
            Path('work/screenshots').mkdir(parents=True, exist_ok=True)
            page.screenshot(path='work/screenshots/avtrack-add-hover.png')
            original = title.inner_text()
            page.wait_for_timeout(600)
            assert title.inner_text() == original
            image = page.locator('.home-workspace-examples .workspace-example-strip')
            assert page.request.get(origin+'/workspace-examples.png').ok
            assert image.locator('image').get_attribute('href') == '/workspace-examples.png'
            assert image.locator('.inventory-example-status text').first.text_content() == 'Located'
            for detail in ['ATEM 1 M/E Advanced Panel 10', 'Liquid Lounge', 'Video', '1500', '10.24.176.67']:
                assert detail in image.locator('.atem-example-info').text_content()
            assert image.bounding_box()['width'] > 900
            assert page.locator('.workspace-example-labels span').count() == 4
            assert image.bounding_box()['height'] < 250
            assert page.locator('.hero-side').is_hidden()
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
                intro=page.locator('#hero-intro')
                for width in [1440,390]:
                    page.set_viewport_size({'width':width,'height':1000})
                    assert title.is_visible() and intro.is_visible(), (path,width)
                    assert intro.inner_text().strip(), (path,width)
                    example=page.locator('#workspace-example')
                    assert example.is_visible(), (path,width)
                    if path == '/#av':
                        assert 'Liquid Lounge' in example.locator('.atem-example-info').text_content()
                        assert '10.24.176.67' in example.locator('.atem-example-info').text_content()
                    if path == '/inventory':
                        assert example.locator('.inventory-example-status').is_visible()
                        assert example.locator('.inventory-example-status text').first.text_content() == 'Located'
                    assert example.get_attribute('data-workspace') == {'/#av':'device','/#iptv':'iptv','/inventory':'equipment','/backups':'backups'}[path]
                    assert example.locator('a,button').count()==0
                    assert example.locator('svg').bounding_box()['height']<=180
                    if width==1440:
                        copy_box=page.locator('.hero-copy').bounding_box()
                        image_box=example.bounding_box()
                        assert copy_box['x']+copy_box['width'] <= image_box['x'], (path,copy_box,image_box)
                    heading_box=page.locator('main > .heading').bounding_box()
                    summary_box=page.locator('#workspace').bounding_box()
                    if summary_box:
                        assert heading_box['y']+heading_box['height'] <= summary_box['y']+1
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.set_viewport_size({'width':1440,'height':1100})
                assert 'One clear view.' not in title.inner_text()
                page.screenshot(path=str(out/(heading.lower().replace(' ','-')+'.png')), full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.goto(origin)
            page.locator('#home-empty-state').wait_for(state='visible')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(out/'avtrack-home-mobile.png'), full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            page.goto(origin+'/avtrack')
            page.locator('[data-scene="iptv"]').scroll_into_view_if_needed()
            page.wait_for_function('()=>document.querySelector(".scene-iptv").classList.contains("active")')
            popup=page.locator('.vlc-stream-example')
            popup.wait_for(state='visible')
            assert popup.locator('svg image').get_attribute('href') == '/workspace-examples.png'
            assert popup.locator('.vlc-example-controls').is_visible()
            assert 'one click' in page.locator('[data-scene="iptv"]').inner_text()
            page.screenshot(path=str(out/'avtrack-landing-iptv-vlc.png'),full_page=False)
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
print('PASS: static centered homepage, spacing, compact image, workspace headers, mobile layout')
