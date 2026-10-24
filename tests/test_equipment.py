import sqlite3
import unittest
import app
import test_app

ITEM = dict(brand='Blackmagic Design', model='ATEM Mini Pro', description='HDMI switcher', serial_number='ATEM-001', quantity=1, location='Broadcast center', notes='With PSU')


class EquipmentTests(unittest.TestCase):
    setUpClass = test_app.AppTests.__dict__['setUpClass']
    tearDownClass = test_app.AppTests.__dict__['tearDownClass']
    setUp = test_app.AppTests.setUp
    tearDown = test_app.AppTests.tearDown
    request = test_app.AppTests.request

    def test_remove_chosen_unit_preserves_other_serials_and_rejects_stale_stock(self):
        _, item = self.request('/api/equipment', 'POST', dict(ITEM, quantity=3, serial_number='A, B, C'))
        payload = dict(inventory_id=item['inventory_id'], serial='B', original_quantity=3, original_serial_number=item['serial_number'])
        path = f"/api/equipment/{item['id']}/remove-unit"
        status, updated = self.request(path, 'POST', payload)
        self.assertEqual(status, 200)
        self.assertEqual(updated['quantity'], 2)
        self.assertEqual(updated['serial_number'], 'A, C')
        self.assertFalse(updated['data_checked'])
        self.assertEqual(self.request(path, 'POST', payload)[0], 400)
        payload.update(original_quantity=2, original_serial_number='A, C', serial=None)
        self.assertEqual(self.request(path, 'POST', payload)[0], 400)
        payload['serial']='missing'
        self.assertEqual(self.request(path, 'POST', payload)[0], 400)
        self.assertEqual(app.equipment_inventory()[0]['quantity'], 2)

    def test_remove_unit_without_serial_and_last_unit(self):
        _, item = self.request('/api/equipment', 'POST', dict(ITEM, quantity=2, serial_number='A'))
        path = f"/api/equipment/{item['id']}/remove-unit"
        payload = dict(serial=None, original_quantity=2, original_serial_number='A')
        status, updated = self.request(path, 'POST', payload)
        self.assertEqual(status, 200)
        self.assertEqual((updated['quantity'], updated['serial_number']), (1, 'A'))
        payload['original_quantity']=1
        self.assertEqual(self.request(path, 'POST', payload)[0], 400)

    def test_crud_quantity_and_persistence(self):
        status, item = self.request('/api/equipment', 'POST', ITEM)
        self.assertEqual(status, 201)
        self.assertEqual(app.equipment_inventory()[0]['serial_number'], 'ATEM-001')
        path = f"/api/equipment/{item['id']}"
        status, item = self.request(path, 'PUT', dict(ITEM, quantity=0, location='Repair bench'))
        self.assertEqual(status, 200)
        self.assertEqual(item['quantity'], 0)
        self.assertEqual(self.request('/api/equipment')[1]['equipment'][0]['location'], 'Repair bench')
        self.assertEqual(self.request(path, 'DELETE', {})[0], 200)
        self.assertEqual(app.equipment_inventory(), [])
        self.assertEqual(self.request(path, 'DELETE', {})[0], 404)
        self.assertEqual(self.request('/api/devices')[1]['devices'], [])

    def test_validation_and_serial_duplicates(self):
        for quantity in (-1, 1.5, True, 'lots', 1000001):
            self.assertEqual(self.request('/api/equipment', 'POST', dict(ITEM, quantity=quantity))[0], 400)
        for field in ('brand','model','location'):
            self.assertEqual(self.request('/api/equipment', 'POST', dict(ITEM, **{field:123}))[0], 400)
        self.assertEqual(self.request('/api/equipment', 'POST', ITEM)[0], 201)
        self.assertEqual(self.request('/api/equipment', 'POST', dict(ITEM, serial_number='atem-001', location='Theater'))[0], 409)

    def test_serial_lists_use_commas_ignore_spaces_and_keep_special_characters(self):
        status, saved = self.request('/api/equipment', 'POST', dict(ITEM, serial_number=' AB C-1 | D/E .2 ; AB C-1 ', quantity=2))
        self.assertEqual(status, 201)
        self.assertEqual(saved['serial_number'], 'ABC-1, D/E.2')
        self.assertEqual(self.request('/api/equipment', 'POST', dict(ITEM, serial_number='A B C-1', location='Theater'))[0], 201)
        self.assertEqual(self.request('/api/equipment', 'POST', dict(ITEM, serial_number='ABC-1', location='Store'))[0], 409)

    def test_import_roundtrip_and_atomic_errors(self):
        payload = {'version':1,'equipment':[ITEM, dict(ITEM, serial_number='', brand='Neutrik', model='XLR', quantity=20)]}
        self.assertEqual(self.request('/api/equipment/import', 'POST', payload)[1], {'added':2,'skipped':0})
        self.assertEqual(self.request('/api/equipment/import', 'POST', payload)[1], {'added':0,'skipped':2})
        exported = self.request('/api/equipment/export')[1]
        self.assertEqual(sum(i['quantity'] for i in exported['equipment']), 21)
        self.assertEqual(self.request('/api/equipment/import','POST', {'version':1,'equipment':[dict(ITEM,serial_number='new'),dict(ITEM,serial_number='other',quantity=-1)]})[0], 400)
        self.assertEqual(len(app.equipment_inventory()), 2)
        self.assertEqual(self.request('/api/equipment/import','POST', {'version':1,'equipment':[ITEM,ITEM]})[0], 400)
        self.assertEqual(self.request('/api/equipment', 'POST', dict(payload['equipment'][1], notes='Different note'))[0], 201)

    def test_csv_escape_and_cross_origin(self):
        self.request('/api/equipment', 'POST', dict(ITEM, description='=FORMULA()'))
        status, raw = self.request('/api/equipment/export.csv')
        self.assertEqual(status, 200)
        self.assertIn(b"'=FORMULA()", raw)
        self.assertIn(b'description,brand,model,serial_number,quantity,location,item_confirmed,notes', raw)
        self.assertEqual(self.request('/api/equipment', 'POST', ITEM, {'Content-Type':'application/json','Origin':'https://other.example'})[0], 403)

    def test_found_status_persists_and_resets_after_item_changes(self):
        item = self.request('/api/equipment', 'POST', ITEM)[1]
        path = f"/api/equipment/{item['id']}"
        self.assertEqual(item['item_confirmed'], 0)
        status, confirmed = self.request(path+'/confirm', 'POST', dict(item, item_confirmed=True))
        self.assertEqual(status, 200)
        self.assertEqual(app.equipment_inventory()[0]['item_confirmed'], 1)
        self.assertEqual(self.request(path, 'PUT', dict(item, notes='Located in the cabinet'))[1]['item_confirmed'], 1)
        self.assertEqual(self.request(path+'/confirm', 'POST', dict(item, item_confirmed=False))[1]['item_confirmed'], 0)
        for field, value in [('brand','Sony'), ('model','Other model'), ('description','Camera'),
                             ('serial_number','OTHER-01'), ('quantity',2), ('location','Theater')]:
            with self.subTest(field=field):
                current = self.request(path, 'PUT', ITEM)[1]
                self.assertEqual(self.request(path+'/confirm', 'POST', dict(current, item_confirmed=True))[0], 200)
                self.assertEqual(self.request(path, 'PUT', dict(ITEM, **{field:value}))[1]['item_confirmed'], 0)

    def test_confirmation_rejects_stale_or_invalid_items(self):
        item = self.request('/api/equipment', 'POST', ITEM)[1]
        path = f"/api/equipment/{item['id']}"
        self.request(path, 'PUT', dict(ITEM, location='Theater'))
        self.assertEqual(self.request(path+'/confirm', 'POST', dict(item, item_confirmed=True))[0], 400)
        self.assertEqual(app.equipment_inventory()[0]['item_confirmed'], 0)
        for payload in [dict(item, item_confirmed='yes'), dict(item, item_confirmed=1), dict(item_confirmed=True)]:
            self.assertEqual(self.request(path+'/confirm', 'POST', payload)[0], 400)
        self.assertEqual(self.request('/api/equipment/999/confirm', 'POST', dict(item, item_confirmed=True))[0], 404)

    def test_found_status_json_and_csv_transfers(self):
        item = self.request('/api/equipment', 'POST', ITEM)[1]
        self.request(f"/api/equipment/{item['id']}/confirm", 'POST', dict(item, item_confirmed=True))
        exported = self.request('/api/equipment/export')[1]
        self.assertEqual(exported['equipment'][0]['item_confirmed'], 1)
        with app.connect() as con:
            con.execute('DELETE FROM equipment')
        self.assertEqual(self.request('/api/equipment/import', 'POST', exported)[1], {'added':1,'skipped':0})
        self.assertEqual(app.equipment_inventory()[0]['item_confirmed'], 1)
        payload = dict(version=1, equipment=[dict(ITEM, serial_number='OTHER', item_confirmed='Found')])
        self.assertEqual(self.request('/api/equipment/import', 'POST', payload)[0], 200)
        self.assertEqual(self.request('/api/equipment/import', 'POST', dict(version=1,equipment=[dict(ITEM,serial_number='INVALID',item_confirmed='maybe')]))[0], 400)
        self.assertEqual(len(app.equipment_inventory()), 2)

    def test_migration_preserves_equipment_and_defaults_to_unchecked(self):
        with sqlite3.connect(app.DB_PATH) as con:
            con.execute("""CREATE TABLE equipment (id INTEGER PRIMARY KEY, brand TEXT NOT NULL,
                model TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', serial_number TEXT NOT NULL DEFAULT '',
                quantity INTEGER, location TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("INSERT INTO equipment VALUES (42,'Sony','Camera','Studio camera','SER-42',3,'Store','Keep note','2025-01-01')")
        row = app.equipment_inventory()[0]
        self.assertEqual((row['id'], row['quantity'], row['notes'], row['updated_at'], row['item_confirmed']), (42,3,'Keep note','2025-01-01',0))

    def test_location_merge_and_delete_preserve_equipment(self):
        self.request('/api/equipment', 'POST', ITEM)
        self.request('/api/equipment', 'POST', dict(ITEM, serial_number='other', location='Store'))
        self.assertEqual(self.request('/api/equipment/locations', 'POST', dict(action='merge', source='Broadcast center', target='Store')), (200, {'updated': 1}))
        records = app.equipment_inventory()
        self.assertEqual([r['location'] for r in records], ['Store', 'Store'])
        self.assertEqual(sum(r['quantity'] for r in records), 2)
        self.assertEqual(self.request('/api/equipment/locations', 'POST', dict(action='delete', source='Store')), (200, {'updated': 2}))
        self.assertEqual([r['location'] for r in app.equipment_inventory()], ['', ''])
        self.assertEqual(self.request('/api/equipment/locations', 'POST', dict(action='delete', source='Store'))[0], 404)

    def test_location_merge_combines_stock_and_validates(self):
        for location, serial in [('Source', ''), ('Source', 'unique'), ('Target', '')]:
            self.request('/api/equipment', 'POST', dict(ITEM, location=location, serial_number=serial))
        self.assertEqual(self.request('/api/equipment/locations', 'POST', dict(action='merge', source='Source', target='Target'))[0], 200)
        records = app.equipment_inventory()
        self.assertEqual(len(records), 2)
        self.assertEqual(sum(r['quantity'] for r in records), 3)
        self.assertTrue(all(r['location'] == 'Target' for r in records))
        for payload in [[], dict(action='merge', source='Source', target='Source'), dict(action='erase', source='Source'), dict(action='delete', source='')]:
            self.assertEqual(self.request('/api/equipment/locations', 'POST', payload)[0], 400)
        self.assertEqual(self.request('/api/equipment/locations', 'POST', dict(action='merge', source='Target', target='Missing'))[0], 404)

    def test_location_stock_merge_preserves_notes_unknowns_and_rolls_back(self):
        self.request('/api/equipment', 'POST', dict(ITEM, serial_number='', location='A', quantity=2, notes='Source note'))
        self.request('/api/equipment', 'POST', dict(ITEM, serial_number='', location='B', quantity=None, notes='Target note'))
        self.assertEqual(self.request('/api/equipment/locations', 'POST', dict(action='merge', source='A', target='B'))[0], 200)
        records=app.equipment_inventory()
        self.assertEqual(len(records),2)
        self.assertEqual({r['notes'] for r in records},{'Source note','Target note'})
        self.assertTrue(all(r['location']=='B' for r in records))
        row=next(r for r in records if r['notes']=='Target note')
        self.assertIsNone(row['quantity'])
        self.request('/api/equipment', 'POST', dict(ITEM, serial_number='', location='A', quantity=1000000))
        self.request(f"/api/equipment/{row['id']}", 'PUT', dict(ITEM, serial_number='', location='B', quantity=1))
        before = app.equipment_inventory()
        self.assertEqual(self.request('/api/equipment/locations', 'POST', dict(action='merge', source='A', target='B'))[0], 400)
        self.assertEqual(app.equipment_inventory(), before)

    def test_location_changes_are_scoped_to_current_inventory(self):
        other = app.save_equipment_inventory({'name': 'Other inventory'})['id']
        for inventory in (1, other):
            for location, serial in [('A','a'), ('B','b')]:
                app.save_equipment(dict(ITEM, inventory_id=inventory, location=location, serial_number=serial))
        self.assertEqual(self.request('/api/equipment/locations', 'POST', dict(inventory_id=other, action='merge', source='A', target='B'))[0], 200)
        self.assertEqual([r['location'] for r in app.equipment_inventory()], ['A','B'])
        self.assertEqual([r['location'] for r in app.equipment_inventory(other)], ['B','B'])

    def test_record_review_is_separate_from_physical_confirmation(self):
        item = self.request('/api/equipment', 'POST', ITEM)[1]
        path = f"/api/equipment/{item['id']}"
        checked = self.request(path+'/review', 'POST', dict(item, data_checked=True))[1]
        self.assertEqual((checked['data_checked'], checked['item_confirmed']), (1, 0))
        self.assertTrue(checked['data_checked_at'].endswith('Z'))
        history=self.request(path+'/record-checks')[1]['checks']
        self.assertEqual(len(history),1)
        self.assertEqual(history[0]['checked_at'],checked['data_checked_at'])
        self.assertEqual(app.equipment_inventory()[0]['data_checked'], 1)
        self.assertEqual(self.request(path+'/review', 'POST', dict(data_checked=True))[0], 400)
        self.request(path, 'PUT', dict(ITEM, notes='Corrected old record'))
        self.assertEqual(app.equipment_inventory()[0]['data_checked'], 0)
        self.assertEqual(self.request(path+'/review', 'POST', dict(item, data_checked=True))[0], 400)
