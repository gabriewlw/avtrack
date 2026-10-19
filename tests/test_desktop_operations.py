import copy,json
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import unittest
import app,test_app,workspace_transfer,operations

class DesktopOperationsTests(unittest.TestCase):
    setUpClass=test_app.AppTests.__dict__['setUpClass']
    tearDownClass=test_app.AppTests.__dict__['tearDownClass']
    setUp=test_app.AppTests.setUp
    tearDown=test_app.AppTests.tearDown
    request=test_app.AppTests.request

    def session(self):
        return self.request('/api/import-sessions','POST',dict(target='device',name='camera.csv',state={'confirmation_mode':'ip'}))[1]['id']

    def test_all_http_export_formats_and_restore_preview(self):
        app.save_device(test_app.EXAMPLE)
        for kind in ('zip','json','xlsx','csv'):
            with self.subTest(kind=kind),urlopen(self.url+'/api/workspace/export?format='+kind) as response:
                self.assertEqual(response.status,200);content=response.read();self.assertTrue(content)
                if kind in ('zip','json'):
                    data=workspace_transfer.unpack(content)
                    self.assertEqual(len(data['tables']['devices']),1)
                    request=Request(self.url+'/api/workspace/preview',data=content,method='POST')
                    with urlopen(request) as preview:self.assertEqual(json.load(preview)['devices'],1)
        self.assertFalse((app.DB_PATH.parent/'recovery').exists())

    def test_restore_saves_a_recoverable_copy_and_accepts_187_schema(self):
        original=app.save_device(test_app.EXAMPLE)
        data=workspace_transfer.snapshot(app.connect,app.backup_directory)
        data.pop('schema_version')  # Historical exports did not carry this field.
        for key in operations.OPTIONAL_TABLES:data['columns'].pop(key);data['tables'].pop(key)
        data['tables']['devices'][0]['name']='Restored camera'
        content=workspace_transfer.pack(data,'zip')[0]
        request=Request(self.url+'/api/workspace/restore',data=content,method='POST',headers={'X-AVTrack-Restore':'replace-all'})
        with urlopen(request) as response:result=json.load(response)
        self.assertEqual(app.inventory()[0]['name'],'Restored camera')
        recovery=app.DB_PATH.parent/'recovery'/result['recovery_backup']
        self.assertTrue(recovery.is_file())
        previous=workspace_transfer.unpack(recovery.read_bytes())
        self.assertEqual(previous['tables']['devices'][0]['name'],original['name'])

    def test_import_changes_are_tracked_and_undo_rejects_later_edits(self):
        session=self.session();path=f'/api/import-sessions/{session}/rows'
        status,result=self.request(path,'POST',{'keys':['0:Sheet:2'],'row':test_app.EXAMPLE})
        self.assertEqual(status,200)
        saved=app.inventory()[0]
        self.assertEqual(result['_receipt']['changes'][0]['after']['id'],saved['id'])
        details=self.request('/api/desktop/record?kind=device&id='+str(saved['id']))[1]
        self.assertEqual(details['imports'][0]['name'],'camera.csv')
        app.save_device(dict(test_app.EXAMPLE,notes='Edited later'),saved['id'])
        self.assertEqual(self.request('/api/desktop/undo-import','POST',{'session_id':session})[0],400)
        self.assertEqual(app.inventory()[0]['notes'],'Edited later')

    def test_reviewed_updates_are_explicit_stale_safe_and_undoable(self):
        saved=app.save_device(test_app.EXAMPLE)
        incoming=dict(test_app.EXAMPLE,notes='New spreadsheet note')
        match=self.request('/api/desktop/import-preview','POST',{'target':'device','rows':[incoming]})[1]['matches'][0]
        self.assertTrue(match['differences'])
        self.assertEqual(app.inventory()[0]['notes'],test_app.EXAMPLE['notes'])
        session=self.session()
        result=self.request(f'/api/import-sessions/{session}/rows','POST',{'keys':['0:Sheet:2'],'row':dict(incoming,_update=match)})
        self.assertEqual(result[0],200);self.assertEqual(result[1]['updated'],1)
        self.assertEqual(app.inventory()[0]['notes'],'New spreadsheet note')
        self.assertEqual(self.request('/api/desktop/undo-import','POST',{'session_id':session})[1]['undone'],1)
        self.assertEqual(app.inventory()[0]['notes'],test_app.EXAMPLE['notes'])
        # A comparison cannot overwrite a record changed after the preview.
        next_session=self.session();app.save_device(dict(test_app.EXAMPLE,notes='Someone else edited'),saved['id'])
        self.assertEqual(self.request(f'/api/import-sessions/{next_session}/rows','POST',{'keys':['0:Sheet:3'],'row':dict(incoming,_update=match)})[0],400)

    def test_added_import_undo_is_atomic_and_idempotent(self):
        session=self.session()
        for index in range(2):self.request(f'/api/import-sessions/{session}/rows','POST',{'keys':[f'0:Sheet:{index+2}'],'row':dict(test_app.EXAMPLE,ip=f'10.20.1.{index+1}')})
        self.assertEqual(self.request('/api/desktop/undo-import','POST',{'session_id':session})[1]['undone'],2)
        self.assertEqual(app.inventory(),[])
        self.assertEqual(self.request('/api/desktop/undo-import','POST',{'session_id':session})[0],400)

    def test_unit_movement_and_handover_are_auditable(self):
        saved=app.save_equipment(dict(description='Camera',serial_number='A, B',quantity=2,location='Locker'))
        payload=dict(inventory_id=saved['inventory_id'],original_quantity=2,original_serial_number=saved['serial_number'],serial='B',reason='Installed in studio',initials='GM')
        self.assertEqual(self.request(f"/api/equipment/{saved['id']}/remove-unit",'POST',payload)[0],200)
        details=self.request(f"/api/desktop/record?kind=equipment&id={saved['id']}")[1]
        self.assertEqual(details['history'][0]['details']['serial'],'B')
        self.assertEqual(details['history'][0]['details']['initials'],'GM')
        app.save_equipment(dict(description='Unknown stock',quantity=None))
        handover=self.request('/api/desktop/handover')[1]
        self.assertEqual(len(handover['unknown_counts']),1)
        self.assertEqual(len(handover['unlocated']),2)
        self.assertEqual(handover['movements'][0]['details']['reason'],'Installed in studio')
        self.assertEqual(self.request(f"/api/equipment/{saved['id']}",'DELETE',dict(inventory_id=saved['inventory_id'],reason='Retired',initials='GM'))[0],200)
        movement=self.request('/api/desktop/handover')[1]['movements'][0]
        self.assertEqual(movement['action'],'stock_record_deleted')
        self.assertEqual(movement['details']['reason'],'Retired')

    def test_deleted_identity_does_not_reuse_backup_links_or_history(self):
        import base64
        device=app.save_device(test_app.EXAMPLE)
        backup=app.save_av_backup(dict(equipment_type='OBS profile',device_name='Old PC',filename='profile.json',notes='',content=base64.b64encode(b'{}').decode()))
        details=dict(record_type='device',record_id=device['id'],state='known_good')
        self.assertEqual(self.request('/api/desktop/backup-details','POST',{'id':backup['id'],'details':details})[0],200)
        self.assertEqual(self.request(f"/api/devices/{device['id']}",'DELETE',{})[0],200)
        replacement=app.save_device(dict(test_app.EXAMPLE,name='Replacement PC'))
        self.assertEqual(device['id'],replacement['id'])
        current=self.request(f"/api/desktop/record?kind=device&id={replacement['id']}")[1]
        self.assertEqual(current['backups'],[])
        self.assertEqual([event['action'] for event in current['history']],['created'])
        self.assertEqual(len(self.request('/api/desktop/handover')[1]['no_linked_backup']),1)

    def test_undo_rejects_same_second_edit_even_when_values_return_to_original(self):
        session=self.session()
        self.request(f'/api/import-sessions/{session}/rows','POST',{'keys':['0:Sheet:2'],'row':test_app.EXAMPLE})
        saved=app.inventory()[0]
        app.save_device(dict(test_app.EXAMPLE,notes='Changed'),saved['id'])
        app.save_device(test_app.EXAMPLE,saved['id'])
        self.assertEqual(self.request('/api/desktop/undo-import','POST',{'session_id':session})[0],400)
        self.assertEqual(len(app.inventory()),1)

    def test_bulk_deletion_keeps_a_recovery_backup(self):
        saved=app.save_device(test_app.EXAMPLE)
        self.assertEqual(self.request('/api/devices/batch-delete','POST',{'ids':[saved['id']]})[1]['deleted'],1)
        backups=self.request('/api/workspace/recovery')[1]['backups']
        self.assertTrue(backups)
        recovered=workspace_transfer.unpack((app.DB_PATH.parent/'recovery'/backups[0]['name']).read_bytes())
        self.assertEqual(recovered['tables']['devices'][0]['name'],saved['name'])

    def test_equipment_backup_links_are_validated_and_survive_complete_restore(self):
        import base64
        device=app.save_device(test_app.EXAMPLE)
        backup=app.save_av_backup(dict(equipment_type='OBS profile',device_name='PC',filename='profile.json',notes='',content=base64.b64encode(b'{}').decode()))
        details=dict(record_type='device',record_id=device['id'],model_serial='Model / Serial',firmware='1.2.3',captured_on='2026-10-01',tested_on='2026-10-10',state='known_good')
        self.assertEqual(self.request('/api/desktop/backup-details','POST',{'id':backup['id'],'details':details})[0],200)
        self.assertEqual(self.request('/api/desktop/handover')[1]['no_linked_backup'],[])
        snapshot=workspace_transfer.snapshot(app.connect,app.backup_directory)
        workspace_transfer.restore(snapshot,app.connect,app.backup_directory)
        record=self.request(f"/api/desktop/record?kind=device&id={device['id']}")[1]
        self.assertEqual(record['backups'][0]['recovery']['firmware'],'1.2.3')
        self.assertEqual(self.request('/api/desktop/backup-details','POST',{'id':backup['id'],'details':dict(details,record_id=999)})[0],400)
