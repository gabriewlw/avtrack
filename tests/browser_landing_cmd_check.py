"""The landing-page CMD window matches the BroadcastGab desktop terminal."""
import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright, expect

with tempfile.TemporaryDirectory() as temporary:
    app.DB_PATH=Path(temporary)/'landing.sqlite3'
    with app.connect() as connection: connection.commit()
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(executable_path=shutil.which('chromium') or None)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.clock.install()
            page.goto(f'http://127.0.0.1:{server.server_port}/avtrack')
            tally=page.locator('.showcase-nav .showcase-brand>span').first.bounding_box()
            brand=page.locator('.showcase-nav .showcase-brand>b').first.bounding_box()
            assert abs(tally['x']-164)<1,tally
            assert abs(brand['x']-186)<1,brand
            bridge=page.locator('.command-bridge');bridge.scroll_into_view_if_needed()
            assert page.locator('.command-title>span').inner_text()=='CMD.EXE — BROADCAST GAB'
            assert page.locator('.command-controls').inner_text().splitlines()==['—','▢','✕']
            purpose=page.locator('.purpose').bounding_box();window=bridge.bounding_box()
            assert abs(window['x']-purpose['x'])<1
            assert abs((window['x']+window['width'])-(purpose['x']+purpose['width']))<1
            assert page.locator('.command-title').evaluate('(node)=>getComputedStyle(node).fontSize')=='11px'
            assert page.locator('.command-title').evaluate('(node)=>getComputedStyle(node).height')=='34px'
            assert bridge.evaluate('(node)=>getComputedStyle(node).borderRadius')=='6px'
            assert page.locator('.command-body').evaluate('(node)=>getComputedStyle(node).padding')=='16px 20px'
            terminal=page.locator('#command-input')
            assert terminal.is_hidden()
            assert page.locator('[data-command]').count()==0
            page.locator('.command-cursor').wait_for(state='attached')
            page.clock.run_for(1000)
            partial=page.locator('#command-output').inner_text()
            assert partial and 'YOUR TURN' not in partial
            assert page.locator('.command-cursor').is_visible()
            page.clock.run_for(120000)
            page.wait_for_function("() => document.querySelector('#command-body').dataset.introComplete === 'true'")
            output=page.locator('#command-output').inner_text()
            assert output.index('WHO I AM') < output.index('WHY I CREATED AVTRACK') < output.index('HOW IT CAN HELP YOU') < output.index('YOUR TURN')
            assert terminal.is_visible() and terminal.is_enabled()
            assert page.locator('#command-body').evaluate('(n)=>n.scrollHeight-n.scrollTop-n.clientHeight') < 3
            assert page.get_by_role('button',name='demo → Explore sample data',exact=True).count()==1
            assert page.locator('.command-entry .command-prompt').inner_text()=='C:\\Users\\visitor\\avtrack>'
            terminal.focus()
            terminal.fill('help');page.clock.run_for(600);terminal.press('Enter')
            assert 'AVTRACK COMMANDS' in page.locator('#command-output').inner_text()
            assert page.locator('.command-accent').first.evaluate('(node)=>getComputedStyle(node).color')=='rgb(230, 230, 230)'
            assert page.locator('.command-option button').first.evaluate('(node)=>getComputedStyle(node).textDecorationLine')=='none'
            terminal.fill('demo');page.clock.run_for(600);terminal.press('Enter')
            demo_link=page.get_by_role('link',name='Launch the interactive demo →',exact=True)
            assert demo_link.get_attribute('href')=='/demo'
            terminal.press('ArrowUp');assert terminal.input_value()=='demo'
            # Chromium can suppress rapid repeated implicit form submissions.
            # Advance the installed clock to model the pause between commands.
            terminal.fill('clear');page.clock.run_for(600);terminal.press('Enter')
            expect(page.locator('#command-output p')).to_have_count(0)
            assert terminal.evaluate('(node)=>node===document.activeElement')
            storage_logo=page.locator('.storage-brand-mark')
            storage_logo.scroll_into_view_if_needed()
            assert storage_logo.inner_text()=='AVTRACK'
            assert page.locator('.storage-brand-mark i').count()==0
            assert page.locator('.storage-visual>svg path').get_attribute('d')=='M190 66L258 190M410 66L342 190M300 428V323'
            assert page.locator('.storage-core strong').count()==0
            actions=page.locator('.hero-copy .hero-actions .button')
            assert actions.count()==2
            widths=actions.evaluate_all('(nodes)=>nodes.map(node=>node.getBoundingClientRect().width)')
            assert abs(widths[0]-widths[1])<1,widths
            assert actions.nth(1).evaluate('(node)=>getComputedStyle(node).whiteSpace')=='nowrap'
            cards=page.locator('.workflow-track article')
            heights=cards.evaluate_all('(nodes)=>nodes.map(node=>node.getBoundingClientRect().height)')
            assert max(heights)-min(heights)<1,heights
            closing=page.locator('.closing');closing.scroll_into_view_if_needed()
            closing_box=closing.bounding_box();closing_action=closing.locator('.hero-actions .button.primary')
            assert closing_action.count()==1
            action_box=closing_action.bounding_box()
            assert abs((action_box['x']+action_box['width']/2)-(closing_box['x']+closing_box['width']/2))<1
            page.emulate_media(reduced_motion='reduce')
            page.goto(f'http://127.0.0.1:{server.server_port}/avtrack')
            page.locator('.command-bridge').scroll_into_view_if_needed()
            page.wait_for_function("() => document.querySelector('#command-body').dataset.introComplete === 'true'")
            assert 'HOW IT CAN HELP YOU' in page.locator('#command-output').inner_text()
            assert page.locator('#command-input').is_visible()
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close()
print('Landing CMD window matches BroadcastGab and supports typing, history, project commands and clear.')
