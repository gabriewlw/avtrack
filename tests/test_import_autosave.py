"""Automatic complete backups after at least 25 newly imported inventory records."""
import json
import base64
import os
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import test_app
import workspace_transfer as transfer

class ImportAutosaveTests(unittest.TestCase):
    setUpClass=test_app.AppTests.__dict__['setUpClass']
    tearDownClass=test_app.AppTests.__dict__['tearDownClass']
    setUp=test_app.AppTests.setUp
    tearDown=test_app.AppTests.tearDown
    request=test_app.AppTests.request

    def rows(self, count, offset=0):
        return [dict(model=f'Converter {i}',quantity=1,notes=f'Shelf A{i}') for i in range(offset,offset+count)]

    def start(self):
        status,session=self.request('/api/import-sessions','POST',dict(target='equipment:1',name='stock.csv',state={'confirmation_mode':'none'}))
        self.assertEqual(status,201)
        return session

    def write(self, session, index, keys=None):
        return self.request(f"/api/import-sessions/{session['id']}/rows",'POST',
            dict(keys=keys or [str(index)],row=self.rows(1,index)[0]))

    def files(self):
        return list((app.DB_PATH.parent/'recovery').glob('*.zip'))

    def test_bulk_threshold_and_round_trip_with_configuration_attachment(self):
        attachment=b'<configuration>known-good</configuration>'
        app.save_av_backup(dict(equipment_type=app.BACKUP_TYPES[0],device_name='Audit switcher',filename='atem.xml',notes='Known good',content=base64.b64encode(attachment).decode()))
        status,result=self.request('/api/equipment/import','POST',dict(version=1,equipment=self.rows(24)))
        self.assertEqual(status,200);self.assertEqual(result['added'],24)
        self.assertEqual(self.files(),[])
        status,result=self.request('/api/equipment/import','POST',dict(version=1,equipment=self.rows(25,24)))
        self.assertEqual(status,200);self.assertEqual(result['added'],25)
        self.assertEqual(result['autosave']['records'],25)
        self.assertEqual(len(self.files()),1)
        saved=transfer.unpack(self.files()[0].read_bytes())
        self.assertEqual(len(saved['tables']['equipment']),49)
        self.assertEqual(base64.b64decode(next(iter(saved['files'].values()))),attachment)
        original=transfer.snapshot(app.connect,app.backup_directory)['tables']
        transfer.restore(saved,app.connect,app.backup_directory)
        restored=transfer.snapshot(app.connect,app.backup_directory)['tables']
        # Restore deliberately gives attachments new storage names to avoid
        # overwriting existing files. Their contents and record metadata survive.
        for before,after in zip(original['av_backups'],restored['av_backups']):
            self.assertEqual(app.av_backup_file(after['id'])[1],attachment)
            for key in ('storage_name','icon_storage_name'):
                after[key]=before[key]
        self.assertEqual(restored,original)

    def test_review_checkpoints_at_25_then_final_and_retry_is_idempotent(self):
        session=self.start()
        for i in range(24):
            status,result=self.write(session,i)
            self.assertEqual(status,200,result)
        self.assertEqual(self.files(),[])
        status,result=self.write(session,24,keys=['24','merged-source'])
        self.assertEqual(status,200,result)
        self.assertEqual(result['autosave']['records'],25)
        self.assertEqual(len(self.files()),1)
        self.assertEqual(self.write(session,24,keys=['24','merged-source'])[0],200)
        self.assertEqual(len(self.files()),1)
        self.assertEqual(self.write(session,25)[0],200)
        self.assertEqual(len(self.files()),1)
        url=f"/api/import-sessions/{session['id']}"
        status,complete=self.request(url,'PUT',dict(state=session['state'],status='complete'))
        self.assertEqual(status,200,complete)
        self.assertEqual(complete['autosave']['records'],26)
        self.assertEqual(len(self.files()),2)
        self.assertEqual(self.request(url)[1]['autosave']['records'],26)
        self.assertEqual(self.request(url,'PUT',dict(state=session['state'],status='complete'))[0],200)
        self.assertEqual(len(self.files()),2)
        latest=app.DB_PATH.parent/'recovery'/complete['autosave']['file']
        restored=transfer.unpack(latest.read_bytes())
        self.assertEqual(len(restored['tables']['equipment']),26)
        self.assertEqual(next(row for row in restored['tables']['import_sessions'] if row['id']==session['id'])['status'],'complete')

    def test_failure_keeps_import_committed_and_retry_can_create_backup(self):
        session=self.start()
        for i in range(24):self.assertEqual(self.write(session,i)[0],200)
        with patch('import_autosave.workspace_transfer.save_recovery',side_effect=OSError('disk full')):
            status,result=self.write(session,24)
        self.assertEqual(status,200)
        self.assertIn('autosave_warning',result)
        self.assertEqual(len(app.equipment_inventory()),25)
        self.assertEqual(self.files(),[])
        status,result=self.write(session,24)
        self.assertEqual(status,200)
        self.assertEqual(result['autosave']['records'],25)
        self.assertEqual(len(app.equipment_inventory()),25)
        self.assertEqual(len(self.files()),1)

    def test_skipped_rows_and_invalid_imports_do_not_trigger_autosave(self):
        session=self.start()
        for i in range(25):
            status,result=self.request(f"/api/import-sessions/{session['id']}/rows",'POST',
                dict(keys=[str(i)],row=self.rows(1,i)[0],action='skip'))
            self.assertEqual(status,200,result)
        self.assertEqual(self.files(),[])
        status,result=self.request('/api/equipment/import','POST',dict(version=1,equipment=self.rows(25)+[dict(model='Invalid',quantity=-1)]))
        self.assertEqual(status,400)
        self.assertEqual(app.equipment_inventory(),[])
        self.assertEqual(self.files(),[])

    def test_growing_checkpoints_and_final_failure_report(self):
        session=self.start()
        for i in range(50):
            status,result=self.write(session,i)
            self.assertEqual(status,200,result)
        self.assertEqual(len(self.files()),2)
        self.assertEqual(result['autosave']['records'],50)
        self.assertEqual(self.write(session,50)[0],200)
        url=f"/api/import-sessions/{session['id']}"
        with patch('import_autosave.workspace_transfer.save_recovery',side_effect=OSError('disk full')):
            status,result=self.request(url,'PUT',dict(state=session['state'],status='complete'))
        self.assertEqual(status,200)
        self.assertIn('autosave_warning',result)
        status,result=self.request(url)
        self.assertEqual(status,200)
        self.assertEqual(result['autosave']['records'],50)
        self.assertIn('autosave_warning',result)
        status,result=self.request(url,'PUT',dict(state=session['state'],status='complete'))
        self.assertEqual(status,200)
        self.assertEqual(result['autosave']['records'],51)
        self.assertNotIn('autosave_warning',self.request(url)[1])

    def test_stock_quantity_does_not_multiply_new_record_threshold(self):
        status,result=self.request('/api/equipment/import','POST',dict(version=1,equipment=[dict(model='Cable batch',quantity=1000)]))
        self.assertEqual(status,200)
        self.assertEqual(result['added'],1)
        self.assertEqual(app.equipment_inventory()[0]['quantity'],1000)
        self.assertEqual(self.files(),[])

    def test_recovery_list_is_newest_first_instead_of_sorting_session_ids(self):
        self.request('/api/equipment/import','POST',dict(version=1,equipment=self.rows(25)))
        content=self.files()[0].read_bytes()
        directory=app.DB_PATH.parent/'recovery'
        old=directory/'avtrack-recovery-import-9-test-25.zip'
        new=directory/'avtrack-recovery-import-10-test-25.zip'
        old.write_bytes(content);new.write_bytes(content)
        os.utime(old,(100,100));os.utime(new,(200,200))
        status,result=self.request('/api/workspace/recovery')
        self.assertEqual(status,200)
        names=[row['name'] for row in result['backups']]
        self.assertLess(names.index(new.name),names.index(old.name))
        self.assertTrue(all('modified_at' in row for row in result['backups']))
