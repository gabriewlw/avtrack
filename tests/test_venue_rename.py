"""Venue rename is atomic, current, and limited to Devices."""
import unittest
import app,test_app

class VenueRenameTests(unittest.TestCase):
    setUpClass=test_app.AppTests.__dict__['setUpClass']
    tearDownClass=test_app.AppTests.__dict__['tearDownClass']
    setUp=test_app.AppTests.setUp
    tearDown=test_app.AppTests.tearDown
    request=test_app.AppTests.request

    def test_rename_all_members_preserves_ip_confirmation(self):
        first=app.save_device(dict(test_app.EXAMPLE))
        second=app.save_device(dict(test_app.EXAMPLE,ip='192.0.2.2'))
        app.confirm_ip(first['id'],dict(ip=first['ip'],vlan=first['vlan']))
        other=app.save_device(dict(test_app.EXAMPLE,venue='Bridge',ip='192.0.2.3'))
        status,result=self.request('/api/devices/rename-venue','POST',dict(old_name=first['venue'],new_name='RD Lounge',expected_ids=[first['id'],second['id']]))
        self.assertEqual(status,200,result)
        self.assertEqual(result['renamed'],2)
        rows={row['id']:row for row in app.inventory()}
        self.assertEqual(rows[first['id']]['venue'],'Lounge')
        self.assertEqual(rows[second['id']]['venue'],'Lounge')
        self.assertTrue(rows[first['id']]['ip_confirmed'])
        self.assertEqual(rows[other['id']]['venue'],'Bridge')

    def test_rejects_stale_members_and_duplicate_destination_without_partial_changes(self):
        first=app.save_device(test_app.EXAMPLE)
        app.save_device(dict(test_app.EXAMPLE,ip='192.0.2.2'))
        app.save_device(dict(test_app.EXAMPLE,venue='Bridge',ip='192.0.2.3'))
        original=app.inventory()
        with self.assertRaises(ValueError):app.rename_device_venue(dict(old_name=first['venue'],new_name='Short',expected_ids=[first['id']]))
        self.assertEqual(app.inventory(),original)
        ids=[row['id'] for row in original if row['venue']==first['venue']]
        with self.assertRaises(ValueError):app.rename_device_venue(dict(old_name=first['venue'],new_name='bridge',expected_ids=ids))
        self.assertEqual(app.inventory(),original)

    def test_iptv_and_inventory_locations_are_untouched(self):
        first=app.save_device(test_app.EXAMPLE)
        item=app.save_equipment(dict(description='Monitor',location=first['venue']))
        channel=app.save_device(dict(record_type='iptv',name='Channel',ip='239.1.1.1',port=1234))
        app.rename_device_venue(dict(old_name=first['venue'],new_name='Short',expected_ids=[first['id']]))
        self.assertEqual(app.equipment_inventory()[0]['location'],item['location'])
        self.assertEqual(next(row for row in app.inventory() if row['id']==channel['id'])['venue'],'')

    def test_invalid_names_reject_without_changes(self):
        first=app.save_device(test_app.EXAMPLE)
        for name in ('',' ', 'x'*121):
            with self.subTest(name=name),self.assertRaises(ValueError):
                app.rename_device_venue(dict(old_name=first['venue'],new_name=name,expected_ids=[first['id']]))
        self.assertEqual(app.inventory()[0]['venue'],first['venue'])
