import base64
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import app

ICON_BYTES = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')


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
            'icon':{'mime_type':'image/png','content':base64.b64encode(ICON_BYTES).decode()},
            'notes':'Saved after the October show check.',
        }
        status, saved = self.request('/api/backups', 'POST', payload)
        self.assertEqual(status, 201)
        self.assertEqual(saved['size'], 31)
        status, listing = self.request('/api/backups')
        self.assertEqual(status, 200)
        backup_folder = Path(listing['folder']['path'])
        self.assertEqual(backup_folder, app.DB_PATH.parent / 'backups')
        self.assertEqual(listing['backups'][0]['filename'], 'show-control.xml')
        self.assertEqual(listing['backups'][0]['has_icon'], 1)
        self.assertNotIn('content', listing['backups'][0])
        stored_files = list(backup_folder.iterdir())
        self.assertEqual(len(stored_files), 2)
        self.assertIn(b'<switcher>known good</switcher>', [path.read_bytes() for path in stored_files])
        self.assertIn(ICON_BYTES, [path.read_bytes() for path in stored_files])
        self.assertEqual(self.request(f"/api/backups/{saved['id']}/download"), (200, b'<switcher>known good</switcher>'))
        self.assertEqual(self.request(f"/api/backups/{saved['id']}/icon"), (200, ICON_BYTES))
        self.assertEqual(self.request(f"/api/backups/{saved['id']}", 'DELETE', {}), (200, {'deleted':saved['id']}))
        self.assertEqual(self.request('/api/backups')[1]['backups'], [])
        self.assertEqual(list(backup_folder.iterdir()), [])
        self.assertEqual(self.request(f"/api/backups/{saved['id']}/download")[0], 404)

        for change in ({'equipment_type':'Unknown'}, {'filename':'../secret'}, {'filename':'bad"name.cfg'}, {'content':'not base64'}, {'content':''},
                       {'icon':{'mime_type':'image/svg+xml','content':base64.b64encode(b'<svg/>').decode()}},
                       {'icon':{'mime_type':'image/png','content':base64.b64encode(b'not a png').decode()}}):
            with self.subTest(change=change):
                self.assertEqual(self.request('/api/backups', 'POST', payload | change)[0], 400)

    def test_database_backups_are_moved_to_the_local_folder(self):
        with app.connect() as con:
            backup_id = con.execute(
                "INSERT INTO av_backups (equipment_type,device_name,filename,content,size,notes) VALUES (?,?,?,?,?,?)",
                ('Videohub', 'Main router', 'router.vhub', sqlite3.Binary(b'legacy backup'), 13, ''),
            ).lastrowid

        with app.connect() as con:
            row = con.execute('SELECT content,storage_name FROM av_backups WHERE id=?', (backup_id,)).fetchone()

        self.assertEqual(row['content'], b'')
        self.assertTrue(row['storage_name'])
        self.assertEqual((app.backup_directory() / row['storage_name']).read_bytes(), b'legacy backup')
        self.assertEqual(app.av_backup_file(backup_id), ('router.vhub', b'legacy backup'))


if __name__ == '__main__': unittest.main()
