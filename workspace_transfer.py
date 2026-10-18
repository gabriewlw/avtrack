"""Portable complete-workspace backups and reports, without executing imported SQL."""
import base64
import binascii
import csv
import io
import json
from pathlib import Path
import sqlite3
import uuid
import zipfile

MAX_BYTES = 200_000_000


def schema(con):
    return {row[0]: [column[1] for column in con.execute(f'PRAGMA table_info("{row[0]}")')]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")}


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
    return {'format': 'avtrack-workspace', 'version': 1, 'columns': columns, 'tables': tables, 'files': files}


def pack(data, kind):
    if kind in ('zip', 'json'):
        serialized = json.dumps(data, ensure_ascii=False).encode('utf-8')
        if len(serialized) > MAX_BYTES:
            raise ValueError('This complete backup exceeds the 200 MB transfer limit. Copy the data folder with AVTrack stopped instead.')
    if kind == 'json':
        return serialized, 'application/json', 'avtrack-all-data.json'
    if kind == 'zip':
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('avtrack-workspace.json', serialized)
        return output.getvalue(), 'application/zip', 'avtrack-all-data.zip'
    # Reports contain all saved table fields; attached binary files stay in full backups.
    sections = []
    for name, columns in data['columns'].items():
        fields = [key for key in columns if not (name == 'av_backups' and key == 'content')]
        sections.append((name, [(field.replace('_', ' ').title(), field, 26) for field in fields], data['tables'][name]))
    if kind == 'xlsx':
        from exports import workbook
        return workbook(sections), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'avtrack-all-data.xlsx'
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
                writer.writerows([[safe(row[key]) for label, key, width in columns] for row in rows])
                archive.writestr(name+'.csv', text.getvalue().encode('utf-8-sig'))
        return output.getvalue(), 'application/zip', 'avtrack-all-data-csv.zip'
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
    except (zipfile.BadZipFile, RuntimeError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('This file is not a readable AVTrack complete backup.') from error
    if not isinstance(data, dict) or data.get('format') != 'avtrack-workspace' or data.get('version') != 1:
        raise ValueError('Choose an AVTrack complete ZIP or JSON backup.')
    return data


def restore(data, connect, backup_directory):
    created = []
    try:
        with connect() as con:
            con.execute('BEGIN IMMEDIATE')
            columns = schema(con)
            if data.get('columns') != columns or not isinstance(data.get('tables'), dict) or set(data['tables']) != set(columns):
                raise ValueError('This backup uses a different database layout. Use the same AVTrack version to restore it.')
            if not isinstance(data.get('files'), dict):
                raise ValueError('The backup file list is invalid.')
            tables = data['tables']
            for name, rows in tables.items():
                if not isinstance(rows, list) or any(not isinstance(row, dict) or set(row) != set(columns[name]) for row in rows):
                    raise ValueError('The backup contains incomplete records.')
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
