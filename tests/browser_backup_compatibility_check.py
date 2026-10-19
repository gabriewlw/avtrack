"""Desktop restore preview explains migration and protects against newer backups."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import workspace_transfer as transfer
from playwright.sync_api import sync_playwright

fixture = Path(__file__).parent / 'fixtures' / 'full_backups' / 'v0.0.187.json'
with tempfile.TemporaryDirectory() as tmp:
    app.DB_PATH = Path(tmp) / 'inventory.sqlite3'
    app.save_device(dict(name='Destination camera', ip='10.0.0.1'))
    original_bytes = fixture.read_bytes()
    server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium'))
            page = browser.new_page(viewport={'width':1440, 'height':1000})
            page.set_default_timeout(15000)
            errors = []
            page.on('pageerror', lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.locator('#workspace-restore-open').click()
            page.locator('#workspace-restore-file').set_input_files(str(fixture))
            page.locator('#workspace-restore-preview').get_by_text('will be upgraded automatically', exact=False).wait_for()
            assert app.inventory()[0]['name']=='Destination camera'
            assert not (app.DB_PATH.parent/'recovery').exists()
            page.locator('#workspace-restore-replace').check()
            with page.expect_navigation():
                page.locator('#workspace-restore-submit').click()
            assert {row['name'] for row in app.inventory()}=={'Historical camera', 'Historical channel'}
            assert list((app.DB_PATH.parent/'recovery').glob('*.zip'))
            before = transfer.snapshot(app.connect, app.backup_directory)
            newer = dict(json.loads(original_bytes), schema_version=999)
            path = Path(tmp)/'newer.json'
            path.write_bytes(transfer.pack(newer, 'json')[0])
            page.locator('#workspace-restore-open').click()
            page.locator('#workspace-restore-file').set_input_files(str(path))
            page.locator('#workspace-restore-error').get_by_text('Update AVTrack', exact=False).wait_for()
            assert page.locator('#workspace-restore-submit').is_disabled()
            after = transfer.snapshot(app.connect, app.backup_directory)
            assert before['tables']==after['tables'] and before['files']==after['files']
            assert fixture.read_bytes()==original_bytes
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
print('PASS: automatic legacy schema migration, recovery backup, and safe newer-schema rejection')
