"""Desktop recovery, provenance, and supervisor workflows."""
import json
from datetime import datetime, timezone

OPTIONAL_TABLES = {'record_audit', 'backup_details'}


def initialize(con):
    con.execute("CREATE TABLE IF NOT EXISTS record_audit (id INTEGER PRIMARY KEY, record_type TEXT NOT NULL, record_id INTEGER NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    con.execute("CREATE INDEX IF NOT EXISTS audit_record ON record_audit(record_type,record_id,id)")
    con.execute("CREATE TABLE IF NOT EXISTS backup_details (backup_id INTEGER PRIMARY KEY, details TEXT NOT NULL)")
    con.execute("CREATE TRIGGER IF NOT EXISTS delete_backup_details AFTER DELETE ON av_backups BEGIN DELETE FROM backup_details WHERE backup_id=OLD.id; END")
    # SQLite can reuse a deleted highest row ID. Do not attach its recovery file to a new item.
    for table, kind in (('devices', 'OLD.record_type'), ('equipment', "'equipment'")):
        con.execute(f"CREATE TRIGGER IF NOT EXISTS unlink_{table}_backups AFTER DELETE ON {table} BEGIN UPDATE backup_details SET details=json_remove(details,'$.record_type','$.record_id') WHERE json_extract(details,'$.record_id')=OLD.id AND json_extract(details,'$.record_type')={kind}; END")


def audit(con, kind, record_id, action, details):
    cursor=con.execute('INSERT INTO record_audit(record_type,record_id,action,details) VALUES (?,?,?,?)',
                (kind, record_id, action, json.dumps(details)))
    return cursor.lastrowid


def record(con, table, record_id):
    row=con.execute(f'SELECT * FROM {table} WHERE id=?',(record_id,)).fetchone()
    return dict(row) if row else None


def apply_import(app, con, session, row):
    target=session['target'];equipment=target.startswith('equipment:')
    table='equipment' if equipment else 'devices'
    scope=int(target.split(':')[1]) if equipment else target
    update=row.get('_update')
    if update:
        before=record(con,table,update.get('id'))
        if not before or before!=update.get('original'):
            raise ValueError('The existing record changed. Refresh the comparison before updating it.')
        if (equipment and before['inventory_id']!=scope) or (not equipment and before['record_type']!=scope):
            raise ValueError('The record belongs to a different workspace.')
        if equipment:
            profile=app.equipment_inventory_details(con,scope).get('layout') or app.DEFAULT_PROFILE
            values=app.custom_values(row.get('custom_values'),profile)
            valid=app.normalize_template_row(dict(app.validate_equipment(row),custom_values=values),profile)
            identity=app.profile_identifier(valid,profile)
            for other in con.execute('SELECT * FROM equipment WHERE inventory_id=? AND id!=?',(scope,before['id'])):
                if identity and app.profile_identifier(app.equipment_record(other),profile)==identity:raise ValueError('This identifier already belongs to another inventory record.')
                if profile.get('unique_location') and valid['location'] and other['location'].casefold()==valid['location'].casefold():raise ValueError('This location already belongs to another record.')
            fields={key:valid[key] for key in app.EQUIPMENT_FIELDS}
            fields.update(custom_values=json.dumps(values,sort_keys=True),data_checked=0,item_confirmed=0,data_checked_at=None)
        else:
            fields=app.validate(dict(row,record_type=scope));fields['ip_confirmed']=0
        con.execute(f'UPDATE {table} SET '+','.join(key+'=?' for key in fields)+',updated_at=CURRENT_TIMESTAMP WHERE id=?', [*fields.values(),before['id']])
        after=record(con,table,before['id'])
        stamp=audit(con,'equipment' if equipment else scope,before['id'],'import_updated',{'source':session['id']})
        return {'added':0,'updated':1,'_changes':[{'table':table,'before':before,'after':after,'audit_id':stamp}]}
    maximum=con.execute(f'SELECT COALESCE(MAX(id),0) FROM {table}').fetchone()[0]
    if equipment:
        result=app.import_equipment(dict(version=1,inventory_id=scope,equipment=[dict(row,item_confirmed=False)]),con)
    else:
        result=app.import_devices(dict(version=1,devices=[dict(row,record_type=scope)],source='spreadsheet',confirmation_required=session['state'].get('confirmation_mode')=='ip'),con)
    added=[dict(saved) for saved in con.execute(f'SELECT * FROM {table} WHERE id>?',(maximum,))]
    result['_changes']=[{'table':table,'before':None,'after':saved} for saved in added]
    for saved,change in zip(added,result['_changes']):change['audit_id']=audit(con,'equipment' if equipment else scope,saved['id'],'import_added',{'source':session['id']})
    return result


def undo_import(con, session_id):
    import import_sessions
    session=import_sessions.get(con,session_id)
    if session['retired']:raise ValueError('This import is read-only or was already undone.')
    changes=[change for receipt in session['receipts'] for change in receipt.get('changes',[])]
    if not changes:raise ValueError('This import has no undoable changes. Older imports remain available as reports.')
    for change in changes:
        kind='equipment' if change['table']=='equipment' else change['after']['record_type']
        latest=con.execute('SELECT MAX(id) FROM record_audit WHERE record_type=? AND record_id=?',(kind,change['after']['id'])).fetchone()[0]
        if change.get('audit_id') and latest!=change['audit_id']:raise ValueError('An imported record has later activity. Nothing was undone; review its history first.')
        if change['table'] not in ('devices','equipment') or record(con,change['table'],change['after']['id'])!=change['after']:
            raise ValueError('An imported record was edited or removed later. No changes were undone; review its history first.')
    for change in reversed(changes):
        table,after,before=change['table'],change['after'],change['before']
        if before is None:con.execute(f'DELETE FROM {table} WHERE id=?',(after['id'],))
        else:
            keys=[key for key in before if key!='id']
            con.execute(f'UPDATE {table} SET '+','.join(key+'=?' for key in keys)+' WHERE id=?',[*[before[key] for key in keys],before['id']])
        audit(con,'equipment' if table=='equipment' else after['record_type'],after['id'],'import_undone',{'source':session_id})
    state=dict(session['state'],undone=True)
    con.execute("UPDATE import_sessions SET retired=1,status='complete',state=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(json.dumps(state),session_id))
    return {'undone':len(changes)}


def preview_import(app, con, value):
    import import_sessions
    target=import_sessions.target_name(value.get('target'));rows=value.get('rows')
    if not isinstance(rows,list) or len(rows)>10000 or any(not isinstance(row,dict) for row in rows):raise ValueError('Provide a list of rows to compare.')
    equipment=target.startswith('equipment:')
    saved=[dict(row) for row in con.execute('SELECT * FROM equipment WHERE inventory_id=?',(int(target.split(':')[1]),))] if equipment else [dict(row) for row in con.execute('SELECT * FROM devices WHERE record_type=?',(target,))]
    result=[]
    for incoming in rows:
        matches=[]
        for existing in saved:
            if equipment:
                serial=app.normalize_serial(str(incoming.get('serial_number') or ''))
                profile=app.equipment_inventory_details(con,existing['inventory_id']).get('layout') or app.DEFAULT_PROFILE
                identity=app.profile_identifier(incoming,profile)
                old=dict(existing,custom_values=json.loads(existing['custom_values']))
                matched=bool(serial and serial.casefold()==existing['serial_number'].casefold() or identity and identity==app.profile_identifier(old,profile))
                if not matched and not serial and not identity:
                    matched=all(str(incoming.get(key) or '').strip().casefold()==str(existing[key] or '').strip().casefold() for key in ('brand','model','description','location')) and bool(incoming.get('model'))
            else:
                ip=str(incoming.get('ip') or '').strip()
                matched=bool(ip and ip.upper()!='DHCP' and ip==existing['ip'] and (target!='iptv' or str(incoming.get('port') or '')==str(existing['port'] or '')))
            if matched:matches.append(existing)
        if len(matches)!=1:result.append(None);continue
        old=matches[0];diffs=[]
        for key in app.EQUIPMENT_FIELDS if equipment else app.ALL_FIELDS:
            if key in incoming and str(incoming[key] or '').strip()!=str(old.get(key) or '').strip():diffs.append({'field':key,'before':old.get(key),'after':incoming[key]})
        if equipment and incoming.get('custom_values',{})!=json.loads(old['custom_values']):diffs.append({'field':'custom values','before':json.loads(old['custom_values']),'after':incoming.get('custom_values',{})})
        result.append({'id':old['id'],'original':old,'differences':diffs})
    return {'matches':result}


def backup_info(con, backup_id, value=None):
    if not con.execute('SELECT 1 FROM av_backups WHERE id=?',(backup_id,)).fetchone():raise LookupError('Equipment backup not found.')
    if value is not None:
        allowed={'record_type','record_id','model_serial','firmware','captured_on','tested_on','state'}
        if not isinstance(value,dict) or set(value)-allowed:raise ValueError('Provide valid recovery details.')
        result={key:value.get(key,'') for key in allowed}
        if result['state'] not in ('','untested','known_good','superseded'):raise ValueError('Choose a valid backup state.')
        for key in ('model_serial','firmware'):
            if not isinstance(result[key],str) or len(result[key])>240:raise ValueError('Recovery details are too long.')
        for key in ('captured_on','tested_on'):
            if result[key]:
                try:datetime.strptime(result[key],'%Y-%m-%d')
                except (TypeError,ValueError):raise ValueError('Use a valid date for capture and restore testing.') from None
        if result['record_type']:
            if result['record_type'] not in ('device','iptv','equipment') or type(result['record_id']) is not int:raise ValueError('Choose a related record.')
            linked=record(con,'equipment' if result['record_type']=='equipment' else 'devices',result['record_id'])
            if not linked or result['record_type']!='equipment' and linked['record_type']!=result['record_type']:raise ValueError('The linked record no longer exists.')
        con.execute('INSERT INTO backup_details(backup_id,details) VALUES (?,?) ON CONFLICT(backup_id) DO UPDATE SET details=excluded.details',(backup_id,json.dumps(result)))
        if result['record_type']:audit(con,result['record_type'],result['record_id'],'recovery_file_linked',{'backup_id':backup_id,'state':result['state']})
    row=con.execute('SELECT details FROM backup_details WHERE backup_id=?',(backup_id,)).fetchone()
    return json.loads(row[0]) if row else {}


def dispatch(handler, app):
    from urllib.parse import urlsplit,parse_qs
    path=urlsplit(handler.path).path;query=parse_qs(urlsplit(handler.path).query)
    if not path.startswith('/api/desktop/'):return False
    action=path.removeprefix('/api/desktop/')
    with app.connect() as con:
        if action=='import-preview' and handler.command=='POST':result=preview_import(app,con,handler.body())
        elif action=='undo-import' and handler.command=='POST':
            value=handler.body();con.execute('BEGIN IMMEDIATE');result=undo_import(con,value.get('session_id'))
        elif action=='records' and handler.command=='GET':
            inventory_names={row['id']:row['name'] for row in con.execute('SELECT id,name FROM equipment_inventories')}
            result={'records':[{**row,'kind':row['record_type'],'label':row['name'] or row['ip'] or 'Incomplete device'} for row in app.inventory()]+[{**row,'kind':'equipment','inventory_name':inventory_names.get(row['inventory_id'],'Inventory'),'label':' · '.join(filter(None,[row['description'],row['model'],row['serial_number']])) or 'Incomplete item'} for row in [app.equipment_record(saved) for saved in con.execute('SELECT * FROM equipment')]]}
        elif action=='record' and handler.command=='GET':
            kind=query.get('kind',['device'])[0];record_id=int(query.get('id',['0'])[0]);table='equipment' if kind=='equipment' else 'devices'
            saved=record(con,table,record_id)
            if not saved or kind not in ('device','iptv','equipment') or kind!='equipment' and saved['record_type']!=kind:raise LookupError('Record not found.')
            birth=con.execute("SELECT COALESCE(MAX(id),0) FROM record_audit WHERE record_type=? AND record_id=? AND action IN ('created','import_added')",(kind,record_id)).fetchone()[0]
            result={'record':app.equipment_record(saved) if kind=='equipment' else app.serialize(saved),'kind':kind,
                    'history':[dict(row,details=json.loads(row['details'])) for row in con.execute('SELECT * FROM record_audit WHERE record_type=? AND record_id=? AND id>=? ORDER BY id DESC',(kind,record_id,birth))],
                    'imports':[], 'backups':[]}
            for receipt in con.execute('SELECT session_id,receipt FROM import_receipts'):
                data=json.loads(receipt['receipt'])
                if any(change['table']==table and change['after']['id']==record_id and change.get('audit_id',0)>=birth for change in data.get('changes',[])):
                    source=con.execute('SELECT name,updated_at FROM import_sessions WHERE id=?',(receipt['session_id'],)).fetchone()
                    result['imports'].append(dict(data,session_id=receipt['session_id'],name=source['name'],imported_at=source['updated_at']))
            for backup in app.av_backups():
                details=backup_info(con,backup['id'])
                if details.get('record_type')==kind and details.get('record_id')==record_id:result['backups'].append(dict(backup,recovery=details))
            if kind=='equipment':
                result['checks']=[dict(row,snapshot=json.loads(row['snapshot'])) for name in ('equipment_record_checks','equipment_stock_checks') for row in con.execute(f'SELECT * FROM {name} WHERE equipment_id=?',(record_id,))]
        elif action=='backup-details' and handler.command in ('GET','POST'):
            if handler.command=='POST':
                value=handler.body();result=backup_info(con,value.get('id'),value.get('details'))
            else:result=backup_info(con,int(query.get('id',['0'])[0]))
        elif action=='handover' and handler.command=='GET':
            equipment=[app.equipment_record(row) for row in con.execute('SELECT * FROM equipment')]
            devices=app.inventory();linked={json.loads(row[0]).get('record_id') for row in con.execute('SELECT details FROM backup_details') if json.loads(row[0]).get('record_type')=='device' and json.loads(row[0]).get('state')=='known_good'}
            result={'unknown_counts':[row for row in equipment if row['quantity'] is None], 'unlocated':[row for row in equipment if not row['item_confirmed']],
                    'needs_review':[row for row in equipment if not row['data_checked']], 'no_linked_backup':[row for row in devices if row['record_type']=='device' and row['id'] not in linked],
                    'stale_checks':[row for row in equipment if (row.get('data_checked_at') or row.get('last_checked_at')) and (datetime.now(timezone.utc)-datetime.fromisoformat((row.get('data_checked_at') or row['last_checked_at']).replace('Z','+00:00')).replace(tzinfo=timezone.utc)).days>90]}
            result['movements']=[dict(row,details=json.loads(row['details'])) for row in con.execute("SELECT * FROM record_audit WHERE action IN ('unit_removed','stock_record_deleted') ORDER BY id DESC LIMIT 50")]
        else:raise LookupError('Desktop operation not found.')
        con.commit()
        handler.send(200,result)
    return True
