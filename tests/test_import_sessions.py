"""Durable progress and receipts must commit with their inventory writes."""
import base64,io,json
import unittest
import test_app
import app
from openpyxl import Workbook
from spreadsheets import preview

class ImportSessionTests(unittest.TestCase):
    setUpClass=test_app.AppTests.__dict__['setUpClass']
    tearDownClass=test_app.AppTests.__dict__['tearDownClass']
    setUp=test_app.AppTests.setUp
    tearDown=test_app.AppTests.tearDown
    request=test_app.AppTests.request

    def session(self,target='device',state=None):
        status,result=self.request('/api/import-sessions','POST',dict(target=target,name='test.csv',state=state or {'confirmation_mode':'none'}))
        self.assertEqual(status,201)
        return result

    def test_receipt_and_record_are_atomic_and_idempotent(self):
        session=self.session();url=f"/api/import-sessions/{session['id']}/rows"
        value=dict(keys=['0:Sheet:2'],row=test_app.EXAMPLE,sheet='Sheet')
        status,result=self.request(url,'POST',value);self.assertEqual(status,200);self.assertEqual(result['added'],1)
        self.assertEqual(self.request(url,'POST',value)[1],result)
        self.assertEqual(len(app.inventory()),1)
        saved=self.request(f"/api/import-sessions/{session['id']}")[1]
        self.assertEqual(saved['completed_keys'],['0:Sheet:2']);self.assertEqual(saved['receipts'][0]['outcome'],'added')
        self.assertEqual(app.inventory()[0]['ip_confirmed'],0)
        # Invalid metadata rolls back the inventory write too.
        status,result=self.request(url,'POST',dict(keys=['0:Sheet:3'],row=dict(test_app.EXAMPLE,ip='10.24.176.68'),issues=[123]))
        self.assertEqual(status,400);self.assertEqual(len(app.inventory()),1)
        self.assertEqual(len(self.request(f"/api/import-sessions/{session['id']}")[1]['receipts']),1)

    def test_unknown_identity_resume_does_not_duplicate_blank_records(self):
        session=self.session();url=f"/api/import-sessions/{session['id']}/rows"
        row=dict(test_app.EXAMPLE,ip='')
        value=dict(keys=['0::2'],row=row)
        self.assertEqual(self.request(url,'POST',value)[0],200)
        self.assertEqual(self.request(url,'POST',value)[0],200)
        self.assertEqual(len(app.inventory()),1)
        state={'file':{'filename':'test.csv','content':'abc'},'confirmation_mode':'none','mappings':{'ip':'2'},'excluded':['Locker']}
        self.assertEqual(self.request(f"/api/import-sessions/{session['id']}",'PUT',dict(state=state,status='paused'))[0],200)
        saved=self.request(f"/api/import-sessions/{session['id']}")[1]
        self.assertEqual(saved['state'],state);self.assertEqual(len(saved['receipts']),1)

    def test_skip_exclude_zero_and_partial_merge_receipts(self):
        session=self.session();url=f"/api/import-sessions/{session['id']}/rows"
        for index,action in enumerate(('skip','exclude','zero')):
            self.assertEqual(self.request(url,'POST',dict(keys=[str(index)],row=test_app.EXAMPLE,action=action))[0],200)
        saved=self.request(f"/api/import-sessions/{session['id']}")[1]
        self.assertEqual({r['outcome'] for r in saved['receipts']},{'skip','exclude','zero'})
        self.assertEqual(app.inventory(),[])
        self.assertEqual(self.request(url,'POST',dict(keys=['0','3'],row=test_app.EXAMPLE))[0],400)
        self.assertEqual(app.inventory(),[])

    def test_target_is_pinned_and_reports_survive_reload(self):
        session=self.session('iptv',{'confirmation_mode':'ip'});url=f"/api/import-sessions/{session['id']}"
        status,_=self.request(url+'/rows','POST',dict(keys=['0::2'],row=dict(name='Channel',ip='239.1.1.1',port=1234,record_type='device')))
        self.assertEqual(status,200);self.assertEqual(app.inventory()[0]['record_type'],'iptv')
        self.assertEqual(app.inventory()[0]['confirmation_required'],1)
        self.assertEqual(self.request(url+'/reconciliation','PUT',{'complete':True})[0],200)
        self.assertEqual(self.request(url)[1]['reconciliation'],{'complete':True})
        self.assertEqual(self.request('/api/import-sessions?target=iptv')[1]['sessions'][0]['destination'],'IPTV Channels')

    def test_deleted_inventory_sessions_cannot_write_to_reused_id(self):
        inventory=app.save_equipment_inventory({'name':'Temporary parts'})
        session=self.session(f"equipment:{inventory['id']}",{'inventory':inventory,'confirmation_mode':'none'})
        app.delete_equipment_inventory(inventory['id'],{'name':inventory['name']})
        replacement=app.save_equipment_inventory({'name':'Replacement parts'})
        self.assertEqual(replacement['id'],inventory['id'])
        url=f"/api/import-sessions/{session['id']}"
        self.assertEqual(self.request(url)[1]['retired'],1)
        self.assertEqual(self.request(url+'/rows','POST',dict(keys=['2'],row=dict(model='X',quantity=1)))[0],400)
        self.assertEqual(self.request(url,'PUT',dict(state={},status='paused'))[0],400)
        self.assertEqual(app.equipment_inventory(replacement['id']),[])

    def test_bad_session_and_preference_inputs(self):
        for target in ('equipment:0','unknown',None):
            self.assertEqual(self.request('/api/import-sessions','POST',dict(target=target,state={}))[0],400)
        for state in ([],None):
            self.assertEqual(self.request('/api/import-sessions','POST',dict(target='device',state=state))[0],400)
        self.assertEqual(self.request('/api/import-preferences','PUT',[])[0],400)
        self.assertEqual(self.request('/api/import-preferences','PUT',dict(target='device',settings={'mappings':{'ip':{'name':'address','occurrence':1}}}))[0],200)
        self.assertEqual(self.request('/api/import-preferences?target=device')[1]['mappings']['ip']['occurrence'],1)
        self.assertEqual(self.request('/api/import-sessions/999')[0],404)

    def test_detects_real_headers_and_preserves_displayed_identifiers(self):
        book=Workbook();sheet=book.active
        sheet.append(['Ship inventory']);sheet.append([]);sheet.append(['Column1','Column2','Column3']);sheet.append([])
        sheet.append(['Model','Serial Number','Location','Location']);sheet.append(['X',12,'Deck','Shelf'])
        sheet['B6'].number_format='000000'
        buffer=io.BytesIO();book.save(buffer)
        data=preview(dict(filename='test.xlsx',content=base64.b64encode(buffer.getvalue()).decode(),detect_header=True))
        self.assertEqual(data['header_row'],5);self.assertEqual(data['header_confidence'],'high')
        self.assertEqual(data['rows'][0][1],'000012');self.assertEqual(data['headers'].count('Location'),2)
        self.assertEqual(data['column_samples'][3],['Shelf'])

    def test_reconciliation_reuses_duplicate_heading_choices_and_exposes_exclusions(self):
        from inventory_profiles import DEFAULT_PROFILE
        from reconciliation import reconcile_profile
        import copy
        layout=copy.deepcopy(DEFAULT_PROFILE)
        next(column for column in layout['columns'] if column['key']=='model')['label']='Device code'
        inventory=app.save_equipment_inventory(dict(name='Mapped parts',layout=layout))
        app.save_equipment(dict(inventory_id=inventory['id'],description='Cable',brand='LG',model='Correct',serial_number='S1',quantity=1,location='Locker A',notes='note'))
        raw=b'Item,Brand,Model,Model,Serial number,Quantity,Location,Location,Notes\nCable,LG,Wrong,Correct,S1,1,Locker A,Drawer 1,note\n'
        settings={'mappings':{'model':{'name':'model','occurrence':1},'location':{'name':'location','occurrence':0}},'header_row':1}
        payload=dict(filename='test.csv',content=base64.b64encode(raw).decode(),source_mappings={'':settings})
        report=reconcile_profile(payload,app.equipment_inventory(inventory['id']),inventory['layout'])
        self.assertTrue(report['complete'],report)
        settings['excluded']=['Locker A']
        report=reconcile_profile(payload,app.equipment_inventory(inventory['id']),inventory['layout'])
        self.assertEqual(report['source_rows'],1)
        self.assertFalse(report['complete'])
        self.assertIn('Location excluded',report['rows'][0]['issues'][0])

    def test_custom_headings_and_manual_override(self):
        raw=base64.b64encode(b'Owner,Cost Code,Stage\nTara,A001,Stored\n').decode()
        data=preview(dict(filename='test.csv',content=raw,detect_header=True))
        self.assertEqual(data['header_row'],1);self.assertEqual(data['header_confidence'],'low')
        data=preview(dict(filename='test.csv',content=raw,header_row=2))
        self.assertEqual(data['header_row'],2);self.assertEqual(data['headers'][0],'Tara')
