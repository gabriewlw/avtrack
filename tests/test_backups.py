import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import app


class BackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); app.DB_PATH = Path(self.temp.name) / 'inventory.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def request(self, path, method='GET', data=None):
        request = Request(self.url + path, data=json.dumps(data).encode() if data is not None else None, method=method, headers={'Content-Type':'application/json'})
        try: response = urlopen(request)
        except HTTPError as error: response = error
        with response:
            content=response.read(); return response.status, json.loads(content) if response.headers['Content-Type'].startswith('application/json') else content

    def test_backup_lifecycle_and_validation(self):
        payload = {
            'equipment_type':'ATEM',
            'device_name':'ATEM 2 M/E Production Studio',
            'filename':'show-control.xml',
            'content':base64.b64encode(b'<switcher>known good</switcher>').decode(),
            'notes':'Saved after the October show check.',
        }
        status, saved = self.request('/api/backups', 'POST', payload)
        self.assertEqual(status, 201)
        self.assertEqual(saved['size'], 31)
        status, listing = self.request('/api/backups')
        self.assertEqual(status, 200)
        self.assertEqual(listing['backups'][0]['filename'], 'show-control.xml')
        self.assertNotIn('content', listing['backups'][0])
        self.assertEqual(self.request(f"/api/backups/{saved['id']}/download"), (200, b'<switcher>known good</switcher>'))
        self.assertEqual(self.request(f"/api/backups/{saved['id']}", 'DELETE', {}), (200, {'deleted':saved['id']}))
        self.assertEqual(self.request('/api/backups')[1], {'backups':[]})
        self.assertEqual(self.request(f"/api/backups/{saved['id']}/download")[0], 404)

        for change in ({'equipment_type':'Unknown'}, {'filename':'../secret'}, {'filename':'bad"name.cfg'}, {'content':'not base64'}, {'content':''}):
            with self.subTest(change=change):
                self.assertEqual(self.request('/api/backups', 'POST', payload | change)[0], 400)


if __name__ == '__main__': unittest.main()
