"""Homepage typing order, reading pauses, stable layout, navigation and reduced motion."""
from pathlib import Path
import shutil,sys,tempfile,threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH=Path(tmp)/'inventory.sqlite3'
    app.save_device(dict(name='Demo',ip='192.0.2.1'))
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.add_init_script("""document.addEventListener('DOMContentLoaded',()=>{
                window.typingFrames=[];
                new MutationObserver(()=>{
                    const heading=document.querySelector('#hero-title .hero-typewriter-text');
                    const intro=document.querySelector('#hero-intro .hero-typewriter-text');
                    if(heading)typingFrames.push({heading:heading.textContent,intro:intro?.textContent,time:performance.now()});
                }).observe(document.querySelector('.hero-copy'),{subtree:true,childList:true,characterData:true});
            });""")
            origin=f'http://127.0.0.1:{server.server_port}'
            page.goto(origin)
            page.locator('#hero-title .hero-typewriter-cursor').wait_for()
            height=page.locator('.hero-copy').bounding_box()['height']
            page.wait_for_function("()=>document.querySelector('#hero-intro .hero-typewriter-text')?.textContent.endsWith('export it in seconds.')",timeout=30000)
            frames=page.evaluate('typingFrames')
            for word in ['device','stream','venue']:
                index=next(i for i,f in enumerate(frames) if f['heading']==f'Every {word}|')
                changed=next(f for f in frames[index+1:] if f['heading']!=f'Every {word}|')
                assert changed['time']-frames[index]['time']>=1600,word
            venue=next(i for i,f in enumerate(frames) if f['heading']=='Every venue|')
            assert any(f['heading']=='|' for f in frames[venue+1:])
            complete='Every device.\nEvery stream.\nEvery venue.\nAll in one place.'
            assert page.locator('#hero-title .hero-typewriter-text').inner_text()==complete
            assert all(not f['intro'] for f in frames if f['heading']!=complete)
            assert abs(page.locator('.hero-copy').bounding_box()['height']-height)<1
            assert page.locator('.hero-typewriter-cursor').count()==0
            page.locator('#device-tab').click()
            assert page.locator('#hero-title').get_attribute('aria-label') is None
            page.go_back();page.locator('#hero-title .hero-typewriter-cursor').wait_for()
            page.locator('#iptv-tab').click();page.wait_for_timeout(2000)
            assert 'Every channel.' in page.locator('#hero-title').inner_text()
            assert page.locator('.hero-typewriter-cursor').count()==0
            reduced=browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
            reduced.goto(origin)
            reduced.wait_for_function("()=>document.querySelector('#hero-intro .hero-typewriter-text')?.textContent.endsWith('export it in seconds.')")
            assert reduced.locator('#hero-title .hero-typewriter-text').inner_text()==complete
            assert reduced.locator('.hero-typewriter-cursor').count()==0
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
print('PASS: longer pauses, full erase, multiline typing, subtitle order, stable layout, navigation and reduced motion')
