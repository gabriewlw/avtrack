"""Permanent release gate: every published full-backup fixture must restore."""
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import app
import backup_compat as compat
import test_app
import workspace_transfer as transfer

FIXTURES = Path(__file__).parent / 'fixtures' / 'full_backups'


class BackupCompatibilityTests(unittest.TestCase):
    setUpClass = test_app.AppTests.__dict__['setUpClass']
    tearDownClass = test_app.AppTests.__dict__['tearDownClass']
    setUp = test_app.AppTests.setUp
    tearDown = test_app.AppTests.tearDown

    def upload(self, action, content):
        request = Request(self.url + '/api/workspace/' + action, data=content,
                          method='POST', headers={'X-AVTrack-Restore': 'replace-all'})
        try:
            response = urlopen(request)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def baseline(self):
        app.save_device(dict(test_app.EXAMPLE))
        return transfer.snapshot(app.connect, app.backup_directory)

    def assert_unchanged(self, original):
        current = transfer.snapshot(app.connect, app.backup_directory)
        self.assertEqual(current['tables'], original['tables'])
        self.assertEqual(current['files'], original['files'])

    def test_every_historical_fixture_restores_via_http_zip_and_json(self):
        paths = sorted(FIXTURES.glob('*.json'))
        self.assertGreaterEqual(len(paths), 4)
        for path in paths:
            original = json.loads(path.read_bytes())
            for kind in ('json', 'zip'):
                with self.subTest(fixture=path.name, kind=kind):
                    content = path.read_bytes()
                    if kind == 'zip':
                        output = io.BytesIO()
                        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                            archive.writestr('avtrack-workspace.json', content)
                        content = output.getvalue()
                    before = transfer.snapshot(app.connect, app.backup_directory)
                    status, preview = self.upload('preview', content)
                    self.assertEqual(status, 200, preview)
                    self.assertEqual((preview['devices'], preview['iptv'], preview['equipment']), (1, 1, 2))
                    self.assert_unchanged(before)
                    status, result = self.upload('restore', content)
                    self.assertEqual(status, 200, result)
                    self.assertEqual(result['schema_version'], compat.CURRENT_SCHEMA_VERSION)
                    restored = transfer.snapshot(app.connect, app.backup_directory)
                    for table, rows in original['tables'].items():
                        if table != 'av_backups':
                            self.assertEqual(restored['tables'][table], rows, table)
                        else:
                            # Attachment storage names are intentionally unique on each restore.
                            ignore = {'storage_name', 'icon_storage_name'}
                            self.assertEqual([{k:v for k,v in row.items() if k not in ignore} for row in restored['tables'][table]],
                                             [{k:v for k,v in row.items() if k not in ignore} for row in rows])
                    self.assertEqual(sorted(restored['files'].values()), sorted(original['files'].values()))
                    self.assertEqual(app.av_backup_file(1)[1], b'{"profile":"historical-test"}')
                    recovery = transfer.unpack((app.DB_PATH.parent / 'recovery' / result['recovery_backup']).read_bytes())
                    self.assertEqual(recovery['tables'], before['tables'])
                    # Export the migrated install, then restore it again.
                    exported = transfer.unpack(transfer.pack(restored, kind)[0])
                    transfer.restore(exported, app.connect, app.backup_directory)
                    self.assertEqual(sorted(app.inventory(), key=lambda row:row['id']),
                                     [app.serialize(row) for row in restored['tables']['devices']])

    def test_version_numbers_are_independent_and_original_payload_is_unchanged(self):
        original = transfer.unpack((FIXTURES / 'v0.0.187.json').read_bytes())
        unchanged = copy.deepcopy(original)
        upgraded, info = compat.upgrade(original)
        self.assertEqual(original, unchanged)
        self.assertEqual(info['source_schema_version'], 1)
        self.assertTrue(info['migration_required'])
        self.assertEqual(upgraded['schema_version'], compat.CURRENT_SCHEMA_VERSION)
        self.assertEqual(upgraded['tables']['record_audit'], [])
        self.assertNotIn('integrity', upgraded)
        upgraded['app_version'] = 'v500.123.99999'
        self.assertEqual(compat.source_version(upgraded), compat.CURRENT_SCHEMA_VERSION)

    def test_unknown_future_versions_and_malformed_schemas_never_replace_data(self):
        original = self.baseline()
        modifications = [dict(schema_version=compat.CURRENT_SCHEMA_VERSION+1),
                         dict(version=compat.FORMAT_VERSION+1), dict(schema_version=True),
                         dict(schema_version=0), dict(columns={})]
        for change in modifications:
            with self.subTest(change=change):
                candidate = dict(original, **change)
                content = transfer.pack(candidate, 'json')[0]
                for action in ('preview', 'restore'):
                    status, result = self.upload(action, content)
                    self.assertEqual(status, 400, result)
                    self.assert_unchanged(original)
        self.assertFalse((app.DB_PATH.parent / 'recovery').exists())

    def test_current_database_cannot_change_without_a_backup_schema_migration(self):
        self.baseline()
        with app.connect() as con:
            con.execute('ALTER TABLE equipment ADD COLUMN new_field TEXT')
        with self.assertRaisesRegex(ValueError, 'without a backup migration'):
            transfer.snapshot(app.connect, app.backup_directory)
        data = transfer.unpack((FIXTURES / 'v0.0.187.json').read_bytes())
        with self.assertRaisesRegex(ValueError, 'without a backup migration'):
            transfer.restore(data, app.connect, app.backup_directory)
        self.assertEqual(len(app.inventory()), 1)

    def test_physical_column_order_does_not_change_legacy_compatibility(self):
        data = transfer.unpack((FIXTURES / 'v0.0.187.json').read_bytes())
        for fields in data['columns'].values():
            fields.reverse()
        data.pop('integrity', None)
        transfer.restore(data, app.connect, app.backup_directory)
        self.assertEqual(next(row for row in app.inventory() if row['record_type']=='device')['notes'],
                         'Subnet 255.255.252.0\nGateway 10.24.179.254')
        bad = copy.deepcopy(data)
        bad['columns']['devices'].append('id')
        with self.assertRaises(ValueError):
            transfer.restore(bad, app.connect, app.backup_directory)

    def test_schema_additions_use_retained_migrations_in_order(self):
        """Exercise an actual future DB column/table and the full 1 → 2 → 3 path."""
        data = transfer.unpack((FIXTURES / 'v0.0.187.json').read_bytes())
        with app.connect() as con:
            con.execute('ALTER TABLE equipment ADD COLUMN service_days INTEGER NOT NULL DEFAULT 30')
            con.execute('CREATE TABLE handover_notes (id INTEGER PRIMARY KEY, note TEXT NOT NULL)')
            columns = transfer.schema(con)
            future = {'version':3, 'columns':columns,
                      'definitions':{name:[list(row)[1:] for row in con.execute(f'PRAGMA table_info("{name}")')]
                                     for name in columns}}
        load = compat.contract
        def next_step(value):
            for row in value['tables']['equipment']:
                row['service_days'] = 30
            value['columns']['equipment'].append('service_days')
            value['columns']['handover_notes'] = ['id', 'note']
            value['tables']['handover_notes'] = []
        with patch.object(compat, 'CURRENT_SCHEMA_VERSION', 3), \
             patch.object(compat, 'contract', side_effect=lambda version:future if version==3 else load(version)), \
             patch.dict(compat.MIGRATIONS, {2:next_step}):
            preview = transfer.preview(data, app.connect)
            self.assertEqual((preview['source_schema_version'], preview['schema_version']), (1, 3))
            transfer.restore(data, app.connect, app.backup_directory)
            saved = transfer.snapshot(app.connect, app.backup_directory)
            self.assertEqual(saved['schema_version'], 3)
            self.assertTrue(all(row['service_days']==30 for row in saved['tables']['equipment']))
            self.assertEqual(saved['tables']['handover_notes'], [])
            self.assertEqual(saved['tables']['devices'], data['tables']['devices'])
            self.assertEqual(sorted(saved['files'].values()), sorted(data['files'].values()))

    def test_missing_migration_and_invalid_migration_output_fail_closed(self):
        original = self.baseline()
        data = transfer.unpack((FIXTURES / 'v0.0.187.json').read_bytes())
        with patch.dict(compat.MIGRATIONS, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'missing a required backup migration'):
                transfer.restore(data, app.connect, app.backup_directory)
        self.assert_unchanged(original)
        with patch.dict(compat.MIGRATIONS, {1:lambda value:None}):
            with self.assertRaises(ValueError):
                transfer.restore(data, app.connect, app.backup_directory)
        self.assert_unchanged(original)

    def test_every_schema_has_a_contract_fixture_and_forward_migration(self):
        for version in range(1, compat.CURRENT_SCHEMA_VERSION+1):
            self.assertEqual(compat.contract(version)['version'], version)
            self.assertTrue(any(compat.source_version(json.loads(path.read_bytes()))==version
                                for path in FIXTURES.glob('*.json')), f'Missing fixture for schema {version}')
            if version < compat.CURRENT_SCHEMA_VERSION:
                self.assertIn(version, compat.MIGRATIONS)
