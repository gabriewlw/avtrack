"""Import choices control later checks without asserting physical verification."""
import copy
import unittest
import app
import test_app
from inventory_profiles import DEFAULT_PROFILE

class ImportConfirmationTests(unittest.TestCase):
    setUp=test_app.AppTests.setUp
    tearDown=test_app.AppTests.tearDown

    def test_network_choice_and_iptv_port_changes(self):
        app.import_devices(dict(version=1,devices=[test_app.EXAMPLE],confirmation_required=False))
        row=app.inventory()[0]
        self.assertEqual(row['confirmation_required'],0)
        self.assertEqual(row['ip_confirmed'],0)
        with self.assertRaises(ValueError):app.confirm_ip(row['id'],dict(ip=row['ip'],vlan=row['vlan']))
        value=dict(name='Test channel',record_type='iptv',ip='239.1.2.3',port=5000)
        app.import_devices(dict(version=1,devices=[value],confirmation_required=True))
        row=next(r for r in app.inventory() if r['record_type']=='iptv')
        self.assertEqual(row['ip_confirmed'],0)
        with self.assertRaises(ValueError):app.confirm_ip(row['id'],dict(ip=row['ip'],vlan=None,port=5001))
        confirmed=app.confirm_ip(row['id'],dict(ip=row['ip'],vlan=None,port=5000))
        self.assertEqual(confirmed['ip_confirmed'],1)
        changed=app.save_device(dict(row,port=5001),row['id'])
        self.assertEqual(changed['ip_confirmed'],0)

    def test_workflow_change_resets_location_but_keeps_stock_check(self):
        profile=copy.deepcopy(DEFAULT_PROFILE)
        inventory=app.save_equipment_inventory(dict(name='Storage',layout=profile))
        item=app.save_equipment(dict(inventory_id=inventory['id'],model='A',location='Locker'))
        confirmed=app.set_equipment_confirmation(item['id'],dict(item,item_confirmed=True))
        self.assertEqual(confirmed['item_confirmed'],1)
        profile.update(confirmation_mode='none',show_status=False)
        saved=app.save_equipment_inventory(dict(name='Storage',layout=profile),inventory['id'])
        self.assertFalse(saved['layout']['show_status'])
        self.assertEqual(app.equipment_inventory(inventory['id'])[0]['item_confirmed'],0)

    def test_inventory_ip_confirmation_requires_valid_address(self):
        profile=copy.deepcopy(DEFAULT_PROFILE)
        profile.update(confirmation_mode='ip',show_status=True)
        profile['columns'].append(dict(key='field_ip',label='IP Address',type='text',options=[],filter='none'))
        inventory=app.save_equipment_inventory(dict(name='Network list',layout=profile))
        item=app.save_equipment(dict(inventory_id=inventory['id'],model='A',custom_values={'field_ip':'wrong'}))
        with self.assertRaises(ValueError):app.set_equipment_confirmation(item['id'],dict(item,item_confirmed=True))
        item=app.save_equipment(dict(item,custom_values={'field_ip':'10.20.30.40'}),item['id'])
        self.assertEqual(app.set_equipment_confirmation(item['id'],dict(item,item_confirmed=True))['item_confirmed'],1)

    def test_invalid_choice_does_not_import(self):
        with self.assertRaises(ValueError):app.import_devices(dict(version=1,devices=[test_app.EXAMPLE],confirmation_required='yes'))
        self.assertEqual(app.inventory(),[])
