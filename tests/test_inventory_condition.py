"""Separate stock batches, optional condition, shelf notes and portable reports."""
import copy
import csv
import io
import json
import unittest
from openpyxl import load_workbook
from pypdf import PdfReader
import app
import workspace_transfer as transfer
import test_inventory_templates
from exports import equipment_pdf, equipment_xlsx

class InventoryConditionTests(unittest.TestCase):
    setUpClass=test_inventory_templates.InventoryTemplateTests.__dict__['setUpClass']
    tearDownClass=test_inventory_templates.InventoryTemplateTests.__dict__['tearDownClass']
    setUp=test_inventory_templates.InventoryTemplateTests.setUp
    tearDown=test_inventory_templates.InventoryTemplateTests.tearDown
    request=test_inventory_templates.InventoryTemplateTests.request
    create=test_inventory_templates.InventoryTemplateTests.create
    tv=test_inventory_templates.InventoryTemplateTests.tv

    def test_same_tv_model_keeps_notes_and_condition_batches_separate(self):
        inv=self.create('tv')
        first=self.tv(inv);first['notes']='Sealed boxes'
        first['custom_values']['unit_status']='New'
        second=copy.deepcopy(first);second['notes']='Replacement stock'
        third=copy.deepcopy(first);third['custom_values']['unit_status']='Used'
        payload=dict(version=1,inventory_id=inv['id'],equipment=[first,second,third])
        self.assertEqual(app.import_equipment(payload),dict(added=3,skipped=0))
        self.assertEqual(app.import_equipment(payload),dict(added=0,skipped=3))
        rows=app.equipment_inventory(inv['id'])
        self.assertEqual(len(rows),3)
        self.assertEqual(sum(r['quantity'] for r in rows),15)
        self.assertEqual({(r['notes'],r['custom_values']['unit_status']) for r in rows},
                         {('Sealed boxes','New'),('Replacement stock','New'),('Sealed boxes','Used')})
        fourth=app.save_equipment(dict(first,notes='Another shelf',shelf='B4'))
        self.assertEqual(fourth['notes'],'Another shelf\nShelf: B4')
        self.assertEqual(len(app.equipment_inventory(inv['id'])),4)

    def test_optional_condition_is_editable_and_does_not_guess_new(self):
        inv=self.create('tv')
        item=app.save_equipment(self.tv(inv))
        self.assertEqual(item['custom_values'].get('unit_status',''),'')
        for status in ('New','Used','Broken',''):
            updated=app.save_equipment(dict(item,custom_values={**item['custom_values'],'unit_status':status}),item['id'])
            self.assertEqual(updated['custom_values'].get('unit_status',''),status)
        with self.assertRaises(ValueError):
            app.save_equipment(dict(self.tv(inv,'Other'),custom_values={**item['custom_values'],'unit_status':'Excellent'}))
        layout=next(c for c in inv['layout']['columns'] if c['key']=='unit_status')
        self.assertFalse(layout['important'])
        self.assertEqual(layout['options'],['New','Used','Broken'])

    def test_other_stock_models_keep_separate_notes_on_manual_add_and_import(self):
        inv=self.create('spare_parts')
        base=dict(inventory_id=inv['id'],brand='Blackmagic',model='Micro Converter',location='Locker',quantity=2)
        one=app.save_equipment(dict(base,notes='With PSU',shelf='A1'))
        self.assertEqual(one['notes'],'With PSU\nShelf: A1')
        payload=dict(version=1,inventory_id=inv['id'],equipment=[dict(base,notes='No PSU'),dict(base,notes='Cable included')])
        self.assertEqual(app.import_equipment(payload),dict(added=2,skipped=0))
        self.assertEqual(app.import_equipment(payload),dict(added=0,skipped=2))
        self.assertEqual(len(app.equipment_inventory(inv['id'])),3)
        with self.assertRaises(ValueError):app.save_equipment(dict(base,shelf='X'*121))

    def test_overview_reports_units_instead_of_rows_without_inventing_unknown_counts(self):
        tv=self.create('tv');app.save_equipment(self.tv(tv))
        spare=self.create('spare_parts')
        app.save_equipment(dict(inventory_id=spare['id'],model='Cable',quantity=12))
        app.save_equipment(dict(inventory_id=spare['id'],model='Unknown'))
        scala=self.create('scala')
        app.save_equipment(dict(inventory_id=scala['id'],location='Lobby',custom_values={'asset_id':'SC-1'}))
        summary=app.workspace_overview()
        self.assertEqual(summary['inventory_total'],4)
        self.assertEqual(summary['inventory_units'],18)

    def test_tv_csv_xlsx_pdf_include_notes_and_status(self):
        inv=self.create('tv')
        item=self.tv(inv);item.update(notes='Shelf B2 - sealed carton')
        item['custom_values']['unit_status']='New'
        row=app.save_equipment(item)
        raw=app.equipment_csv([row],inv['layout'])
        record=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))[0]
        self.assertEqual(record['Status'],'New')
        self.assertEqual(record['Notes'],item['notes'])
        book=load_workbook(io.BytesIO(equipment_xlsx([row],layout=inv['layout'])))
        values=list(book.active.values);record=dict(zip(values[0],values[1]))
        self.assertEqual(record['Status'],'New');self.assertEqual(record['Notes'],item['notes'])
        text=' '.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(equipment_pdf([row],layout=inv['layout']))).pages)
        self.assertIn('sealed carton',text);self.assertIn('New',text)

    def test_status_and_separate_batches_survive_complete_zip_and_json_backups(self):
        inv=self.create('tv')
        item=self.tv(inv);item.update(notes='First batch')
        item['custom_values']['unit_status']='New'
        app.save_equipment(item);app.save_equipment(dict(item,notes='Second batch',shelf='C1'))
        original=transfer.snapshot(app.connect,app.backup_directory)
        for kind in ('zip','json'):
            data=transfer.unpack(transfer.pack(original,kind)[0])
            transfer.restore(data,app.connect,app.backup_directory)
            self.assertEqual(transfer.snapshot(app.connect,app.backup_directory)['tables'],original['tables'])

    def test_old_layout_gains_optional_status_and_notes_without_overwriting_values(self):
        inv=self.create('tv')
        layout=copy.deepcopy(inv['layout'])
        layout['columns']=[c for c in layout['columns'] if c['key'] not in ('unit_status','notes')]
        with app.connect() as con:con.execute('UPDATE equipment_inventories SET layout=? WHERE id=?',(json.dumps(layout),inv['id']))
        restored=next(i for i in app.equipment_inventories() if i['id']==inv['id'])
        self.assertTrue({'unit_status','notes'} <= {c['key'] for c in restored['layout']['columns']})
