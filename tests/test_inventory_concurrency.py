"""Stale tabs must never silently restore old stock, notes, or condition."""
import copy
import unittest
import app
import test_inventory_templates

class InventoryConcurrencyTests(unittest.TestCase):
    setUpClass=test_inventory_templates.InventoryTemplateTests.__dict__['setUpClass']
    tearDownClass=test_inventory_templates.InventoryTemplateTests.__dict__['tearDownClass']
    setUp=test_inventory_templates.InventoryTemplateTests.setUp
    tearDown=test_inventory_templates.InventoryTemplateTests.tearDown
    request=test_inventory_templates.InventoryTemplateTests.request
    create=test_inventory_templates.InventoryTemplateTests.create
    tv=test_inventory_templates.InventoryTemplateTests.tv

    def test_stale_tv_editor_cannot_overwrite_new_count_or_status(self):
        inv=self.create('tv')
        original=app.save_equipment(self.tv(inv))
        path=f"/api/equipment/{original['id']}"
        latest=copy.deepcopy(original)
        latest['custom_values'].update(deck_6='7',unit_status='New')
        status,current=self.request(path,'PUT',dict(latest,_original=original))
        self.assertEqual(status,200)
        status,error=self.request(path,'PUT',dict(original,notes='Stale editor',_original=original))
        self.assertEqual(status,400)
        self.assertIn('changed in another tab',error['error'])
        self.assertEqual(app.equipment_inventory(inv['id'])[0],current)

    def test_notes_saved_elsewhere_are_preserved(self):
        inv=self.create('spare_parts')
        original=app.save_equipment(dict(inventory_id=inv['id'],model='Converter',quantity=2,notes='Shelf A'))
        app.set_equipment_notes(original['id'],dict(inventory_id=inv['id'],original_notes='Shelf A',notes='Shelf B'))
        status,error=self.request(f"/api/equipment/{original['id']}",'PUT',dict(original,quantity=9,_original=original))
        self.assertEqual(status,400)
        saved=app.equipment_inventory(inv['id'])[0]
        self.assertEqual(saved['notes'],'Shelf B')
        self.assertEqual(saved['quantity'],2)

    def test_fresh_and_legacy_updates_work_but_incomplete_original_is_rejected(self):
        inv=self.create('spare_parts')
        item=app.save_equipment(dict(inventory_id=inv['id'],model='Cable',quantity=2))
        path=f"/api/equipment/{item['id']}"
        self.assertEqual(self.request(path,'PUT',dict(item,quantity=3,_original={}))[0],400)
        status,current=self.request(path,'PUT',dict(item,quantity=3,_original=item))
        self.assertEqual(status,200)
        self.assertEqual(current['quantity'],3)
        status,current=self.request(path,'PUT',dict(current,quantity=4))
        self.assertEqual(status,200)
        self.assertEqual(current['quantity'],4)
