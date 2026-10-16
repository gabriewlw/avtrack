"""AV Backups navigation, upload, custom icon, search, download, and delete check."""
import base64
import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temp:
    app.DB_PATH = Path(temp) / 'inventory.sqlite3'
    server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        backup = Path(temp) / 'control-room-show.xml'
        backup.write_bytes(b'<atem>known-good</atem>')
        icon = Path(temp) / 'atem-icon.png'
        icon.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='))
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium') or None)
            page = browser.new_page(viewport={'width':1440, 'height':1000})
            errors=[]; page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/backups')
            page.locator('#backups-panel').wait_for(state='visible')
            assert page.locator('#backups-tab').get_attribute('aria-current') == 'page'
            assert page.locator('#workspace-page-title').text_content() == 'AV Backups'
            assert str(Path(temp) / 'backups') in page.locator('#backup-folder-path').text_content()
            assert page.locator('#open-backup-folder').is_visible()
            page.locator('#add-backup').click()
            page.locator('#backup-type').select_option('ATEM')
            page.locator('#backup-device').fill('ATEM 2 M/E Production Studio')
            page.locator('#backup-file').set_input_files(str(backup))
            page.locator('#backup-icon').set_input_files(str(icon))
            page.locator('#backup-notes').fill('Known-good setup after show check')
            page.locator('#save-backup').click()
            page.locator('#backup-dialog').wait_for(state='hidden')
            page.wait_for_function("() => document.getElementById('backup-count').textContent === '1'")
            stored_files = list((Path(temp) / 'backups').iterdir())
            assert len(stored_files) == 2
            assert backup.read_bytes() in [path.read_bytes() for path in stored_files]
            assert icon.read_bytes() in [path.read_bytes() for path in stored_files]
            card=page.locator('.backup-card')
            assert card.locator('.backup-custom-icon').is_visible()
            page.wait_for_function("() => document.querySelector('.backup-custom-icon').naturalWidth > 0")
            assert 'ATEM 2 M/E Production Studio' in card.inner_text()
            assert 'control-room-show.xml' in card.inner_text()
            delete_button=card.get_by_role('button', name='Delete control-room-show.xml')
            assert delete_button.locator('svg').count() == 1
            assert '🗑' not in delete_button.inner_text()
            page.locator('#backup-search').fill('known-good')
            assert card.is_visible()
            page.locator('#backup-search').fill('videohub')
            assert page.locator('.backup-card').count() == 0
            page.locator('#backup-search').fill('')
            with page.expect_download() as download:
                card.get_by_role('link', name='Download').click()
            assert Path(download.value.path()).read_bytes() == backup.read_bytes()
            delete_button.click()
            page.locator('#confirm-delete-backup').click()
            page.wait_for_function("() => document.getElementById('backup-count').textContent === '0'")
            assert list((Path(temp) / 'backups').iterdir()) == []
            assert page.locator('#backups-empty').is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown(); server.server_close()
