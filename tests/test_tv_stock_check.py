"""TV stock check dates require an explicit, current physical count confirmation."""
import copy
import io
import unittest
from openpyxl import load_workbook
import test_inventory_templates
import app
from exports import equipment_xlsx

class TVStockCheckTests(unittest.TestCase):
    setUpClass=test_inventory_templates.InventoryTemplateTests.__dict__['setUpClass']
    tearDownClass=test_inventory_templates.InventoryTemplateTests.__dict__['tearDownClass']
    setUp=test_inventory_templates.InventoryTemplateTests.setUp
    tearDown=test_inventory_templates.InventoryTemplateTests.tearDown
    request=test_inventory_templates.InventoryTemplateTests.request
    create=test_inventory_templates.InventoryTemplateTests.create
    tv=test_inventory_templates.InventoryTemplateTests.tv
    def test_stock_date_is_explicit_persistent_and_exported(self):
        inventory=self.create('tv')
        item=app.save_equipment(self.tv(inventory))
        self.assertIsNone(item['last_checked_at'])
        reviewed=app.set_equipment_review(item['id'],dict(item,data_checked=True))
        self.assertIsNone(reviewed['last_checked_at'])
        checked=self.request(f"/api/equipment/{item['id']}/stock-check",'POST',item)
        self.assertEqual(checked[0],200)
        checked=checked[1]
        self.assertTrue(checked['last_checked_at'].endswith('Z'))
        # Another edit must not fabricate a new physical stock check.
        edited=app.save_equipment(dict(checked,notes='Updated note'),item['id'])
        self.assertEqual(edited['last_checked_at'],checked['last_checked_at'])
        self.assertIn(checked['last_checked_at'],app.equipment_csv([edited],inventory['layout']).decode('utf-8-sig'))
        book=load_workbook(io.BytesIO(equipment_xlsx([edited],layout=inventory['layout'])))
        self.assertEqual(list(book.active.values)[0][-1],'Last checked (UTC)')
        self.assertEqual(list(book.active.values)[1][-1],checked['last_checked_at'])
        app.set_equipment_stock_check(item['id'],edited)

    def test_changed_counts_and_wrong_inventory_are_rejected(self):
        inventory=self.create('tv');item=app.save_equipment(self.tv(inventory))
        changed=copy.deepcopy(item);changed['custom_values']['deck_6']='4'
        app.save_equipment(changed,item['id'])
        self.assertEqual(self.request(f"/api/equipment/{item['id']}/stock-check",'POST',item)[0],400)
        self.assertIsNone(app.equipment_inventory(inventory['id'])[0]['last_checked_at'])
        self.assertEqual(self.request(f"/api/equipment/{item['id']}/stock-check",'POST',dict(item,inventory_id=1))[0],400)

    def test_existing_tv_layout_hides_serial_number(self):
        inventory=self.create('tv');profile=copy.deepcopy(inventory['layout'])
        profile['columns'].append(dict(key='serial_number',label='Serial number',type='text',filter='none'))
        profile['primary_search']='serial_number'
        updated=app.save_equipment_inventory(dict(name=inventory['name'],layout=profile),inventory['id'])
        self.assertNotIn('serial_number',[col['key'] for col in updated['layout']['columns']])
        self.assertEqual(updated['layout']['primary_search'],'model')
