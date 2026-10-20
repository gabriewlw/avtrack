"""Targeted note updates preserve item fields and reject competing note edits."""
import unittest
import app
import test_app

class InventoryNotesTests(unittest.TestCase):
    setUpClass=test_app.AppTests.__dict__['setUpClass']
    tearDownClass=test_app.AppTests.__dict__['tearDownClass']
    setUp=test_app.AppTests.setUp
    tearDown=test_app.AppTests.tearDown
    request=test_app.AppTests.request

    def test_device_note_popup_rejects_stale_edits_without_changing_other_fields(self):
        saved=app.save_device(dict(test_app.EXAMPLE,notes='Original'))
        path=f"/api/devices/{saved['id']}/notes"
        self.assertEqual(self.request(path,'POST',dict(notes='First line\nSecond line',original_notes='Original'))[0],200)
        self.assertEqual(self.request(path,'POST',dict(notes='Stale draft',original_notes='Original'))[0],400)
        current=app.inventory()[0]
        self.assertEqual(current['notes'],'First line\nSecond line')
        self.assertEqual(current['ip'],saved['ip'])
        self.assertEqual(self.request(path,'POST',dict(notes='Invalid',original_notes=5))[0],400)

    def test_notes_preserve_other_fields_and_physical_confirmation(self):
        row=app.save_equipment(dict(description='Spare',serial_number='S1',quantity=2,location='Locker A',notes='Old'))
        app.set_equipment_confirmation(row['id'],dict(row,item_confirmed=True))
        app.set_equipment_review(row['id'],dict(row,data_checked=True))
        status,updated=self.request(f"/api/equipment/{row['id']}/notes",'POST',dict(inventory_id=row['inventory_id'],notes=' New\nnotes ',original_notes='Old'))
        self.assertEqual(status,200);self.assertEqual(updated['notes'],'New\nnotes')
        self.assertEqual(updated['item_confirmed'],1);self.assertEqual(updated['data_checked'],0)
        self.assertEqual((updated['quantity'],updated['serial_number'],updated['location']),(2,'S1','Locker A'))

    def test_competing_fields_preserved_and_competing_notes_rejected(self):
        row=app.save_equipment(dict(description='Spare',quantity=2,notes='Old'))
        app.save_equipment(dict(row,quantity=9),row['id'])
        updated=app.set_equipment_notes(row['id'],dict(notes='New',original_notes='Old'))
        self.assertEqual(updated['quantity'],9)
        self.assertEqual(self.request(f"/api/equipment/{row['id']}/notes",'POST',dict(notes='Stale',original_notes='Old'))[0],400)
        self.assertEqual(app.equipment_inventory()[0]['notes'],'New')
        self.assertEqual(app.set_equipment_notes(row['id'],dict(notes='',original_notes='New'))['notes'],'')

    def test_validation_and_inventory_scope(self):
        row=app.save_equipment(dict(description='Spare',notes='Old'))
        other=app.save_equipment_inventory(dict(name='Other'))
        path=f"/api/equipment/{row['id']}/notes"
        self.assertEqual(self.request(path,'POST',dict(inventory_id=other['id'],notes='Wrong',original_notes='Old'))[0],404)
        for payload in (dict(notes=5,original_notes='Old'),dict(notes='x'*2001,original_notes='Old'),dict(notes='New')):
            self.assertEqual(self.request(path,'POST',payload)[0],400)
