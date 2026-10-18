"""Portable complete-workspace backups and reports, without executing imported SQL."""
import base64
import binascii
import csv
import io
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
import uuid
import re
from datetime import datetime, timezone
import zipfile

MAX_BYTES = 200_000_000


def schema(con):
    return {row[0]: [column[1] for column in con.execute(f'PRAGMA table_info("{row[0]}")')]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")}


def digest(data):
    payload = {key: value for key, value in data.items() if key != 'integrity'}
    result=hashlib.sha256()
    for chunk in json.JSONEncoder(ensure_ascii=False,sort_keys=True,separators=(',',':')).iterencode(payload):result.update(chunk.encode('utf-8'))
    return result.hexdigest()


def validate_tables(tables, con):
    """SQLite affinity alone does not protect the types expected by the app."""
    from inventory_profiles import validate_profile
    json_fields = {'equipment_inventories': ('layout',), 'equipment': ('custom_values',),
                   'equipment_stock_checks': ('snapshot',), 'equipment_record_checks': ('snapshot',),
                   'import_sessions': ('state', 'reconciliation'), 'import_receipts': ('receipt',),
                   'import_preferences': ('settings',), 'record_audit': ('details',), 'backup_details': ('details',)}
    flags = {'ip_confirmed', 'confirmation_required', 'item_confirmed', 'data_checked', 'retired'}
    for name, rows in tables.items():
        definitions = list(con.execute(f'PRAGMA table_info("{name}")'))
        for row in rows:
            for column in definitions:
                key, kind, required, primary = column[1], column[2], column[3], column[5]
                value = row[key]
                if value is None:
                    if required or primary:
                        raise ValueError(f'The backup contains a missing {name}.{key}.')
                    continue
                expected = int if kind == 'INTEGER' else str
                if type(value) is not expected:
                    raise ValueError(f'The backup contains an invalid {name}.{key}.')
                if key in flags and value not in (0, 1):
                    raise ValueError('The backup contains an invalid confirmation status.')
                if key == 'quantity' and not 0 <= value <= 1_000_000:
                    raise ValueError('The backup contains an invalid stock quantity.')
                if (key == 'id' or key.endswith('_id')) and kind == 'INTEGER' and value < 1:
                    raise ValueError('The backup contains an invalid record identifier.')
            for key in json_fields.get(name, ()):
                if row[key] is None:
                    continue
                try:
                    value = json.loads(row[key])
                except (ValueError, RecursionError) as error:
                    raise ValueError(f'The backup contains unreadable {name}.{key}.') from error
                if not isinstance(value, dict):
                    raise ValueError(f'The backup contains an invalid {name}.{key}.')
                if key == 'layout' and value:
                    validate_profile(value)
                if key == 'custom_values' and any(not isinstance(v, str) for v in value.values()):
                    raise ValueError('The backup contains invalid custom inventory values.')


def snapshot(connect, backup_directory):
    with connect() as con:
        con.execute('BEGIN')
        columns = schema(con)
        tables = {name: [dict(row) for row in con.execute(f'SELECT * FROM "{name}"')] for name in columns}
        files = {}
        for row in tables['av_backups']:
            row['content'] = base64.b64encode(row['content']).decode('ascii')
            for key in ('storage_name', 'icon_storage_name'):
                name = row[key]
                if name:
                    if Path(name).name != name or '\\' in name:
                        raise ValueError('A saved backup has an invalid storage path.')
                    path = backup_directory() / name
                    if not path.is_file() or path.is_symlink():
                        raise ValueError('A saved backup file is missing. Restore it before exporting all data.')
                    files[name] = base64.b64encode(path.read_bytes()).decode('ascii')
    return {'format': 'avtrack-workspace', 'version': 1, 'exported_at':datetime.now(timezone.utc).isoformat(), 'columns': columns, 'tables': tables, 'files': files}


def export_name(extension):
    return 'avtrack-all-data-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'.'+extension


def report_sections(data):
    from inventory_profiles import column_value
    used=set()
    def title(value):
        clean=re.sub(r'[\\/*?:\[\]]','-',value).strip("'")[:27] or 'Inventory'
        name=clean;number=1
        while name.casefold() in used:number+=1;name=clean+' '+str(number)
        used.add(name.casefold());return name
    def section(name,fields,rows):return (title(name),[(label,key,26) for label,key in fields],rows)
    tables=data['tables'];sections=[]
    columns=[('Device name','name'),('Venue','venue'),('IP address','ip'),('VLAN','vlan'),('System','discipline'),('Notes','notes'),('IP manually verified','ip_confirmed')]
    sections.append(section('Devices',columns,[row for row in tables['devices'] if row['record_type']=='device']))
    sections.append(section('IPTV',[( 'Channel','name'),('IP address','ip'),('Port','port'),('Source','channel_source'),('Notes','notes')],[row for row in tables['devices'] if row['record_type']=='iptv']))
    for inventory in tables['equipment_inventories']:
        from inventory_profiles import DEFAULT_PROFILE
        profile=json.loads(inventory['layout']) or DEFAULT_PROFILE
        fields=[(col['label'],col['key']) for col in profile['columns']]+[('Record reviewed','data_checked'),('Physically located','item_confirmed'),('Last count check','last_checked_at')]
        rows=[]
        for saved in tables['equipment']:
            if saved['inventory_id']!=inventory['id']:continue
            row=dict(saved,custom_values=json.loads(saved['custom_values']))
            rows.append({**row,**{col['key']:column_value(row,col['key']) for col in profile['columns']}})
        sections.append(section(inventory['name'],fields,rows))
    metadata={row['backup_id']:json.loads(row['details']) for row in tables.get('backup_details',[])}
    sections.append(section('Equipment backups',[(key.replace('_',' ').title(),key) for key in ('equipment_type','device_name','filename','notes','created_at','state','model_serial','firmware','captured_on','tested_on')],[dict(row,**metadata.get(row['id'],{})) for row in tables['av_backups']]))
    return sections


def pack(data, kind):
    if kind in ('zip', 'json'):
        exported = dict(data, integrity={'algorithm': 'sha256', 'digest': digest(data)})
        serialized = json.dumps(exported, ensure_ascii=False).encode('utf-8')
        if len(serialized) > MAX_BYTES:
            raise ValueError('This complete backup exceeds the 200 MB transfer limit. Copy the data folder with AVTrack stopped instead.')
    if kind == 'json':
        return serialized, 'application/json', export_name('json')
    if kind == 'zip':
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('avtrack-workspace.json', serialized)
        return output.getvalue(), 'application/zip', export_name('zip')
    sections = report_sections(data)
    if kind == 'xlsx':
        from exports import workbook
        return workbook(sections), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', export_name('xlsx')
    if kind == 'csv':
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, columns, rows in sections:
                text = io.StringIO(newline='')
                writer = csv.writer(text)
                writer.writerow([label for label, key, width in columns])
                def safe(value):
                    text = str(value) if value is not None else ''
                    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text
                writer.writerows([[safe(row.get(key)) for label, key, width in columns] for row in rows])
                archive.writestr(name+'.csv', text.getvalue().encode('utf-8-sig'))
        return output.getvalue(), 'application/zip', export_name('csv.zip')
    raise ValueError('Choose ZIP, JSON, XLSX, or CSV.')


def unpack(content):
    if len(content) > MAX_BYTES:
        raise ValueError('The complete backup must be smaller than 200 MB.')
    try:
        if content.startswith(b'PK'):
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                entries = archive.infolist()
                if len(entries) != 1 or entries[0].filename != 'avtrack-workspace.json' or entries[0].file_size > MAX_BYTES:
                    raise ValueError('Choose an AVTrack complete ZIP backup, not a CSV report.')
                content = archive.read(entries[0])
        data = json.loads(content)
    except (zipfile.BadZipFile, RuntimeError, UnicodeError, ValueError, NotImplementedError, RecursionError) as error:
        raise ValueError('This file is not a readable AVTrack complete backup.') from error
    if not isinstance(data, dict) or data.get('format') != 'avtrack-workspace' or type(data.get('version')) is not int or data.get('version') != 1:
        raise ValueError('Choose an AVTrack complete ZIP or JSON backup.')
    integrity = data.get('integrity')
    if integrity is not None:
        if not isinstance(integrity, dict) or integrity.get('algorithm') != 'sha256' or not isinstance(integrity.get('digest'), str):
            raise ValueError('The backup integrity information is invalid.')
        if not re.fullmatch(r'[0-9a-f]{64}',integrity['digest']) or not hmac.compare_digest(integrity['digest'], digest(data)):
            raise ValueError('This backup has changed or is damaged. Export a fresh complete backup.')
    return data


def prepare(data, con):
    columns = schema(con)
    from operations import OPTIONAL_TABLES
    source_columns=data.get('columns',{})
    source_tables=data.get('tables',{})
    if isinstance(source_columns,dict) and isinstance(source_tables,dict):
        missing=set(columns)-set(source_columns)
        if missing.issubset(OPTIONAL_TABLES):
            data=dict(data,columns={**source_columns,**{key:columns[key] for key in missing}},tables={**source_tables,**{key:[] for key in missing}})
    if data.get('columns') != columns or not isinstance(data.get('tables'), dict) or set(data['tables']) != set(columns):
        raise ValueError('This backup uses a different database layout. Use the same AVTrack version to restore it.')
    if not isinstance(data.get('files'), dict):
        raise ValueError('The backup file list is invalid.')
    tables = data['tables']
    for name, rows in tables.items():
        if not isinstance(rows, list) or any(not isinstance(row, dict) or set(row) != set(columns[name]) for row in rows):
            raise ValueError('The backup contains incomplete records.')
    validate_tables(tables, con)
    # Keep the caller's backup reusable, even after a failed restore/retry.
    tables = {name: [dict(row) for row in rows] for name, rows in tables.items()}
    files = {}
    referenced = {row[key] for row in tables['av_backups'] for key in ('storage_name', 'icon_storage_name') if row[key]}
    if referenced != set(data['files']):
        raise ValueError('The backup is missing attached files or contains unexpected files.')
    for name, encoded in data['files'].items():
        if not isinstance(name, str) or Path(name).name != name or '\\' in name or name in ('.', '..'):
            raise ValueError('The backup contains an invalid file path.')
        files[name] = base64.b64decode(encoded, validate=True)
    for row in tables['av_backups']:
        row['content'] = base64.b64decode(row['content'], validate=True)
    for row in tables['av_backups']:
        content = files[row['storage_name']] if row['storage_name'] else row['content']
        if len(content) != row['size'] or not content:
            raise ValueError('An attached backup file is incomplete. Export a fresh complete backup.')
    return tables, files


def preview(data, connect):
    with connect() as con:
        tables,files=prepare(data,con)
    return {'exported_at':data.get('exported_at','Unknown — older backup'), 'app_version':data.get('app_version','Older backup'),
            'format_version':data['version'],'devices':sum(row['record_type']=='device' for row in tables['devices']),
            'iptv':sum(row['record_type']=='iptv' for row in tables['devices']), 'equipment':len(tables['equipment']),
            'inventories':[row['name'] for row in tables['equipment_inventories']], 'backup_records':len(tables['av_backups']), 'files':len(files)}


def save_recovery(connect,backup_directory,directory,version=None):
    data=snapshot(connect,backup_directory)
    if version:data['app_version']=version
    content,_,_=pack(data,'zip')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    destination=directory/('avtrack-recovery-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.zip')
    temporary=destination.with_suffix('.tmp')
    try:
        temporary.write_bytes(content);temporary.replace(destination)
    finally:temporary.unlink(missing_ok=True)
    return destination


def restore(data, connect, backup_directory):
    created = []
    try:
        with connect() as con:
            con.execute('BEGIN IMMEDIATE')
            columns = schema(con)
            tables,files=prepare(data,con)
            # Unique storage names leave existing files intact if the transaction fails.
            directory = backup_directory()
            directory.mkdir(parents=True, exist_ok=True)
            remapped = {}
            for name, content in files.items():
                destination = directory / ('restored-'+uuid.uuid4().hex+Path(name).suffix)
                with destination.open('xb') as handle:
                    created.append(destination)
                    handle.write(content)
                remapped[name] = destination.name
            for row in tables['av_backups']:
                for key in ('storage_name', 'icon_storage_name'):
                    if row[key]:
                        row[key] = remapped[row[key]]
            # Clear first, then insert: existing deletion triggers cannot erase restored history.
            for name in columns:
                con.execute(f'DELETE FROM "{name}"')
            for name, fields in columns.items():
                names = ','.join('"'+field+'"' for field in fields)
                con.executemany(f'INSERT INTO "{name}" ({names}) VALUES ({",".join("?" for _ in fields)})',
                                [[row[field] for field in fields] for row in tables[name]])
            if con.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('The backup contains records belonging to a missing inventory.')
            return {'restored': {name: len(rows) for name, rows in tables.items()}}
    except (TypeError, binascii.Error, sqlite3.DatabaseError) as error:
        for path in created:
            path.unlink(missing_ok=True)
        raise ValueError('The backup contains invalid records; current data was kept.') from error
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
