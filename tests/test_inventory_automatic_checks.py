"""Inventory checks are automatic without fabricating historical physical counts."""
import unittest
import app
import test_app
import workspace_transfer
from test_equipment import ITEM


class AutomaticInventoryCheckTests(unittest.TestCase):
    setUpClass = test_app.AppTests.__dict__['setUpClass']
    tearDownClass = test_app.AppTests.__dict__['tearDownClass']
    setUp = test_app.AppTests.setUp
    tearDown = test_app.AppTests.tearDown
    request = test_app.AppTests.request

    def test_completed_date_survives_complete_backup_restore(self):
        item = app.save_equipment(dict(ITEM, model=''))
        checked = app.save_equipment(dict(item, model=ITEM['model']), item['id'])
        snapshot = workspace_transfer.snapshot(app.connect, app.backup_directory)
        content = workspace_transfer.pack(snapshot, 'zip')[0]
        workspace_transfer.restore(workspace_transfer.unpack(content), app.connect, app.backup_directory)
        restored = app.equipment_inventory()[0]
        self.assertEqual(restored['inventory_checked_at'], checked['inventory_checked_at'])
        self.assertIsNone(restored['last_checked_at'])

    def test_reviewed_import_completion_and_undo_restore_previous_check_date(self):
        saved = app.save_equipment(dict(ITEM, model=''))
        incoming = dict(ITEM, inventory_id=saved['inventory_id'])
        target = f"equipment:{saved['inventory_id']}"
        match = self.request('/api/desktop/import-preview', 'POST', {'target': target, 'rows': [incoming]})[1]['matches'][0]
        session = self.request('/api/import-sessions', 'POST', dict(target=target, name='inventory.csv', state={}))[1]['id']
        status, result = self.request(f'/api/import-sessions/{session}/rows', 'POST', {'keys': ['0:Sheet:2'], 'row': dict(incoming, _update=match)})
        self.assertEqual(status, 200, result)
        self.assertTrue(app.equipment_inventory()[0]['inventory_checked_at'])
        self.assertEqual(self.request('/api/desktop/undo-import', 'POST', {'session_id': session})[0], 200)
        self.assertIsNone(app.equipment_inventory()[0]['inventory_checked_at'])

    def test_located_updates_date_but_unlocating_and_notes_do_not(self):
        item = app.save_equipment(ITEM)
        self.assertIsNone(item['inventory_checked_at'])
        located = app.set_equipment_confirmation(item['id'], dict(item, item_confirmed=True))
        self.assertTrue(located['inventory_checked_at'].endswith('Z'))
        self.assertIsNone(located['last_checked_at'])
        unlocated = app.set_equipment_confirmation(item['id'], dict(located, item_confirmed=False))
        self.assertEqual(unlocated['inventory_checked_at'], located['inventory_checked_at'])
        edited = app.save_equipment(dict(unlocated, notes='Updated notes'), item['id'])
        self.assertEqual(edited['inventory_checked_at'], located['inventory_checked_at'])
        self.assertEqual(app.equipment_inventory()[0]['inventory_checked_at'], located['inventory_checked_at'])

    def test_incomplete_to_complete_only_and_optional_notes_stay_optional(self):
        item = app.save_equipment(dict(ITEM, model='', location='', notes=''))
        partial = app.save_equipment(dict(item, model=ITEM['model']), item['id'])
        self.assertIsNone(partial['inventory_checked_at'])
        complete = app.save_equipment(dict(partial, location=ITEM['location']), item['id'])
        self.assertTrue(complete['inventory_checked_at'])
        self.assertFalse(complete['item_confirmed'])
        self.assertIsNone(complete['last_checked_at'])
        edited = app.save_equipment(dict(complete, brand='Changed brand'), item['id'])
        self.assertEqual(edited['inventory_checked_at'], complete['inventory_checked_at'])
        with app.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM record_audit WHERE action='inventory_checked'").fetchone()[0], 1)

    def test_custom_required_columns_and_zero_counts(self):
        inventory = app.save_equipment_inventory(dict(name='Custom inventory', layout=dict(
            columns=[dict(key='description',label='Item',type='text',important=True),
                     dict(key='quantity',label='Count',type='count',important=True,minimum=0),
                     dict(key='asset_tag',label='Asset tag',type='text',important=True)],
            primary_search='description', identifier='')))
        item = app.save_equipment(dict(inventory_id=inventory['id'], description='Spare', quantity=0))
        completed = app.save_equipment(dict(item, custom_values={'asset_tag':'A-1'}), item['id'])
        self.assertTrue(completed['inventory_checked_at'])
        self.assertFalse(completed['item_confirmed'])

    def test_deleted_record_check_is_not_reused_by_next_item(self):
        item = app.save_equipment(ITEM)
        app.set_equipment_confirmation(item['id'], dict(item, item_confirmed=True))
        with app.connect() as con:
            con.execute('DELETE FROM equipment WHERE id=?', (item['id'],))
        replacement = app.save_equipment(dict(ITEM, serial_number='replacement'))
        self.assertIsNone(replacement['inventory_checked_at'])
