import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import app

EXAMPLE = dict(name='ATEM video switcher', category='Video switcher', venue='Liquid Lounge', discipline='Video', ip='10.24.176.66', vlan=1500, notes='Rack 2')


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        app.DB_PATH = Path(self.temp.name) / 'inventory.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def request(self, path, method='GET', data=None, headers=None):
        req = Request(self.url + path, data=json.dumps(data).encode() if data is not None else None, method=method, headers=headers or {'Content-Type': 'application/json'})
        try:
            response = urlopen(req)
        except HTTPError as error:
            response = error
        with response:
            content = response.read()
            return response.status, json.loads(content) if response.headers['Content-Type'].startswith('application/json') else content

    def test_codespaces_signin_connection_policy(self):
        from unittest.mock import patch
        for codespaces,host,allowed in (('',None,False),('false',None,False),('true',None,True),('false','test-8000.app.github.dev',True),('false','test-8000.app.github.dev.other.example',False)):
            with self.subTest(codespaces=codespaces,host=host), patch.dict(app.os.environ, {'CODESPACES':codespaces}):
                request=Request(self.url+'/inventory',headers={'Host':host} if host else {})
                with urlopen(request) as response:
                    policy=response.headers['Content-Security-Policy']
                directives=dict(part.strip().split(' ',1) for part in policy.split(';'))
                self.assertEqual(directives['connect-src'], "'self' https://github.dev/pf-signin" if allowed else "'self'")
                self.assertEqual(directives['script-src'], "'self'")
                self.assertEqual(directives['frame-ancestors'], "'none'")
                self.assertEqual(directives['form-action'], "'self'")
                self.assertEqual(self.request('/api/devices','POST',EXAMPLE,{'Content-Type':'application/json','Origin':'https://github.dev'})[0],403)

    def test_recovery_assets_do_not_change_saved_inventory(self):
        saved=app.save_device(EXAMPLE)
        self.assertEqual(self.request('/recover')[0],200)
        self.assertIn(b'/recovery.js',self.request('/recover')[1])
        self.assertEqual(self.request('/recovery.js')[0],200)
        self.assertEqual(app.inventory()[0]['id'],saved['id'])
        worker=self.request('/service-worker.js')[1].decode()
        assets=worker.split('const ASSETS = ',1)[1].split(';',1)[0]
        self.assertNotIn('/recover',assets)

    def test_import_history_is_not_rendered_in_workspace_pages(self):
        for path in ('/', '/inventory', '/backups'):
            status, page = self.request(path)
            self.assertEqual(status, 200)
            self.assertNotIn(b'import-history-panel', page)
            self.assertNotIn(b'>Import history<', page)
        workflow = self.request('/import-workflow.js')[1]
        self.assertNotIn(b'refreshHistory', workflow)
        self.assertIn(b'Resume previous import', workflow)

    def test_product_showcase_is_available_as_a_separate_page(self):
        status, page = self.request('/avtrack')
        self.assertEqual(status, 200)
        self.assertIn(b'Broadcast operations.', page)
        self.assertIn(b'LOCAL AV OPERATIONS WORKSPACE', page)
        self.assertNotIn(b'BUILT FOR BROADCAST OPERATIONS', page)
        self.assertIn(b'CMD.EXE \xe2\x80\x94 BROADCAST GAB', page)
        self.assertIn(b'AVTrack is a local AV operations tool built to keep your workspace organized.', page)
        self.assertIn(b'Find device IPs faster, test channel feeds in one click, track inventory across locations, and keep configuration backups ready when you need them.', page)
        self.assertNotIn(b'Broadcast Shell [Version 10.0.26100.1]', page)
        self.assertNotIn(b'(c) Gabriel Moura. All rights reserved.', page)
        self.assertIn(b'id="command-input"', page)
        self.assertNotIn(b'class="command-chips"', page)
        self.assertNotIn(b'Open BroadcastGab CMD', page)
        self.assertIn(b'View on GitHub', page)
        self.assertIn(b'aria-label="View AVTrack on GitHub (opens in a new tab)"', page)
        self.assertNotIn(b'>View the project ', page)
        self.assertIn(b'<div class="storage-core"><span class="storage-brand" aria-label="AVTrack">avtrack</span><small>LOCAL WORKSPACE</small></div>', page)
        self.assertNotIn(b'<div class="storage-core"><img src="/icon.svg"', page)
        self.assertEqual(self.request('/avtrack/')[0], 200)
        landing_css = self.request('/landing.css')[1]
        self.assertIn(b'.story-stage', landing_css)
        self.assertIn(b'color:#e6e6e6', landing_css)
        self.assertIn(b'color:#a8a8a8', landing_css)
        self.assertIn(b'box-shadow:0 24px 80px -20px rgba(0,0,0,.9)', landing_css)
        landing_js = self.request('/landing.js')[1]
        self.assertIn(b'activateScene', landing_js)
        self.assertIn(b'runTerminalCommand', landing_js)
        worker = self.request('/service-worker.js')[1].decode()
        self.assertIn('"/avtrack"', worker)

    def test_full_lifecycle_and_persistence(self):
        status, saved = self.request('/api/devices', 'POST', EXAMPLE)
        self.assertEqual(status, 201)
        self.assertEqual(saved['ip'], '10.24.176.66')
        self.assertEqual(app.inventory()[0]['venue'], 'Liquid Lounge')
        self.assertEqual(self.request('/api/devices')[1]['devices'][0]['id'], saved['id'])
        updated = dict(EXAMPLE, name='ATEM main')
        self.assertEqual(self.request(f"/api/devices/{saved['id']}", 'PUT', updated)[0], 200)
        self.assertEqual(app.inventory()[0]['name'], 'ATEM main')
        self.assertEqual(self.request(f"/api/devices/{saved['id']}", 'DELETE', {})[0], 200)
        self.assertEqual(app.inventory(), [])
        self.assertEqual(self.request(f"/api/devices/{saved['id']}", 'DELETE', {})[0], 404)

    def test_validation(self):
        for ip in ('10.24.176.999', 'hello', '127.0.0.1', '224.0.0.1', '0.0.0.0', '255.255.255.255', '10.24.176.066'):
            with self.subTest(ip=ip):
                self.assertEqual(self.request('/api/devices', 'POST', dict(EXAMPLE, ip=ip))[0], 400)
        for vlan in (0, 4095, 1.5, True, '1e3', 'text'):
            with self.subTest(vlan=vlan):
                self.assertEqual(self.request('/api/devices', 'POST', dict(EXAMPLE, vlan=vlan))[0], 400)
        self.assertEqual(self.request('/api/devices', 'POST', dict(EXAMPLE, name=123))[0], 400)
        self.assertEqual(self.request('/api/devices', 'POST', dict(EXAMPLE, discipline='invalid'))[0], 400)

    def test_duplicate_scope(self):
        self.assertEqual(self.request('/api/devices', 'POST', EXAMPLE)[0], 201)
        self.assertEqual(self.request('/api/devices', 'POST', EXAMPLE)[0], 409)
        self.assertEqual(self.request('/api/devices', 'POST', dict(EXAMPLE, vlan=1501))[0], 409)

    def test_export_import_roundtrip_and_idempotence(self):
        self.request('/api/devices', 'POST', EXAMPLE)
        status, payload = self.request('/api/export')
        self.assertEqual(status, 200)
        self.assertEqual(payload['version'], 1)
        with app.connect() as con:
            con.execute('DELETE FROM devices')
        self.assertEqual(self.request('/api/import', 'POST', payload)[1], {'added': 1, 'skipped': 0})
        self.assertEqual(self.request('/api/import', 'POST', payload)[1], {'added': 0, 'skipped': 1})
        self.assertEqual(app.inventory()[0]['ip'], EXAMPLE['ip'])

    def test_import_is_atomic(self):
        payload = {'version': 1, 'devices': [EXAMPLE, dict(EXAMPLE, ip='not valid')]}
        self.assertEqual(self.request('/api/import', 'POST', payload)[0], 400)
        self.assertEqual(app.inventory(), [])
        payload['devices'] = [EXAMPLE, EXAMPLE]
        status, result = self.request('/api/import', 'POST', payload)
        self.assertEqual(status, 200)
        self.assertEqual((result['added'], result['skipped']), (1, 1))
        self.assertIn(EXAMPLE['ip'], result['warnings'][0])
        self.assertEqual(len(app.inventory()), 1)

    def test_csv_formula_protection(self):
        self.request('/api/devices', 'POST', dict(EXAMPLE, name='=HYPERLINK("evil")'))
        status, content = self.request('/api/export.csv')
        self.assertEqual(status, 200)
        self.assertIn(b"'=HYPERLINK", content)

    def test_cross_origin_and_assets(self):
        status, _ = self.request('/api/devices', 'POST', EXAMPLE, {'Content-Type': 'application/json', 'Origin':'https://other.example'})
        self.assertEqual(status, 403)
        for path in ('/', '/app.js', '/style.css', '/icon.svg'):
            self.assertEqual(self.request(path)[0], 200)
        self.assertEqual(self.request('/../app.py')[0], 404)

    def test_workspace_uses_broadcastgab_color_tokens(self):
        style = self.request('/style.css')[1].decode()
        expected = {
            '--background': 'oklch(0.16 0.008 260)',
            '--card': 'oklch(0.20 0.01 260)',
            '--secondary': 'oklch(0.24 0.012 260)',
            '--surface-accent': 'oklch(0.27 0.014 260)',
            '--border': 'oklch(0.30 0.012 260)',
            '--foreground': 'oklch(0.93 0.01 90)',
            '--muted-foreground': 'oklch(0.62 0.015 260)',
            '--primary': 'oklch(0.63 0.24 25)',
            '--primary-foreground': 'oklch(0.14 0.01 260)',
        }
        for token, value in expected.items():
            with self.subTest(token=token):
                self.assertIn(f'{token}: {value};', style)
        self.assertIn('body { margin: 0; background: var(--background); color: var(--foreground); }', style)
        self.assertIn('.primary { background: var(--primary); color: var(--primary-foreground); }', style)
        self.assertIn("const CACHE = 'avtrack-offline-v69'", self.request('/service-worker.js')[1].decode())
        body = self.request('/')[1]
        self.assertIn(b'AVTrack \xc2\xb7 v0.0.170', body)
        self.assertIn(b'class="brand-tally"', body)
        self.assertIn(b'class="brand" href="/" aria-label="AVTrack homepage"', body)
        self.assertIn(b'class="brand-credit" href="https://broadcastgab.com"', body)
        self.assertIn(b'>BY BROADCASTGAB</a>', body)
        self.assertNotIn(b'.brand-tally { width: 10px; height: 10px; flex: 0 0 10px; border-radius: 50%; background: var(--primary); box-shadow: 0 0 12px 2px color-mix(in oklab,var(--primary) 60%,transparent); animation:', style.encode())
        self.assertNotIn(b'Reload workspace', body)

    def test_batch_delete_only_selected_ids_and_retry(self):
        first = self.request('/api/devices', 'POST', EXAMPLE)[1]
        second = self.request('/api/devices', 'POST', dict(name='Camera', venue='Theatre', ip='10.24.176.67'))[1]
        keep = self.request('/api/devices', 'POST', dict(name='DSP', ip='10.24.176.68'))[1]
        channel = self.request('/api/devices', 'POST', dict(record_type='iptv', name='Channel', ip='239.1.1.1', port=5000))[1]
        payload = {'ids':[first['id'], second['id'], first['id'], 999999]}
        self.assertEqual(self.request('/api/devices/batch-delete', 'POST', payload), (200, {'deleted':2}))
        self.assertEqual({row['id'] for row in app.inventory()}, {keep['id'], channel['id']})
        self.assertEqual(self.request('/api/devices/batch-delete', 'POST', payload), (200, {'deleted':0}))
        self.assertEqual(self.request('/api/devices/batch-delete', 'POST', {'ids':[channel['id']]}), (200, {'deleted':1}))
        self.assertEqual([row['id'] for row in app.inventory()], [keep['id']])

    def test_invalid_batch_delete_is_atomic_and_cross_origin_rejected(self):
        saved = self.request('/api/devices', 'POST', EXAMPLE)[1]
        for payload in [{}, [], {'ids':[]}, {'ids':'all'}, {'ids':[saved['id'], False]}, {'ids':[saved['id'], '2']}, {'ids':[saved['id'], -1]}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.request('/api/devices/batch-delete', 'POST', payload)[0], 400)
                self.assertEqual([row['id'] for row in app.inventory()], [saved['id']])
        self.assertEqual(self.request('/api/devices/batch-delete', 'POST', {'ids':[saved['id']]}, {'Content-Type':'application/json','Origin':'https://other.example'})[0], 403)
        self.assertEqual([row['id'] for row in app.inventory()], [saved['id']])


if __name__ == '__main__':
    unittest.main()
