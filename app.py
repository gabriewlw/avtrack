"""AVTrack server. Python 3.12+; install requirements.txt for Excel import."""
import csv
import base64
import binascii
from contextlib import nullcontext
import import_sessions
import import_autosave
import workspace_transfer
import operations
import io
import ipaddress
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from spreadsheets import preview as spreadsheet_preview
from reconciliation import reconcile, reconcile_profile
from inventory_profiles import DEFAULT_PROFILE, SCALA_PROFILE, validate_profile, custom_values, profile_identifier, column_value, normalize_template_row, with_unit_status
from exports import network_xlsx, equipment_xlsx, network_pdf, equipment_pdf, demo_pdf

ROOT = Path(__file__).resolve().parent
# AVTRACK_DB is canonical; legacy names keep existing deployments on their data.
DB_PATH = Path(os.environ.get('AVTRACK_DB') or os.environ.get('BROADCASTHUB_DB') or os.environ.get('IPTRACKING_DB') or ROOT / 'data' / 'inventory.sqlite3')
BACKUP_MAX_BYTES = 25_000_000
BACKUP_ICON_MAX_BYTES = 1_000_000
BACKUP_ICON_TYPES = {
    'image/png': ('.png', lambda content: content.startswith(b'\x89PNG\r\n\x1a\n')),
    'image/jpeg': ('.jpg', lambda content: content.startswith(b'\xff\xd8\xff')),
    'image/webp': ('.webp', lambda content: len(content) >= 12 and content[:4] == b'RIFF' and content[8:12] == b'WEBP'),
}


def source_revision():
    """Use the checked-out commit as the displayed build identifier."""
    try:
        revision = subprocess.run(['git', 'rev-parse', '--short=7', 'HEAD'], cwd=ROOT,
                                  capture_output=True, text=True, check=True, timeout=2).stdout.strip()
        count = subprocess.run(['git', 'rev-list', '--count', 'HEAD'], cwd=ROOT,
                               capture_output=True, text=True, check=True, timeout=2).stdout.strip()
        return f'v0.0.{count} · {revision}' if count.isdigit() and re.fullmatch(r'[0-9a-f]{7,40}', revision) else 'unversioned'
    except (OSError, subprocess.SubprocessError):
        return 'unversioned'


def backup_directory():
    return Path(os.environ.get('AVTRACK_BACKUP_DIR') or DB_PATH.parent / 'backups')


def vlc_executable():
    """Return the locally installed VLC executable, if available."""
    configured = os.environ.get('AVTRACK_VLC')
    candidates = [configured] if configured else []
    candidates.extend(filter(None, (shutil.which('vlc'), shutil.which('vlc.exe'))))
    if sys.platform == 'win32':
        for variable in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            base = os.environ.get(variable)
            if base:
                candidates.append(str(Path(base) / 'VideoLAN' / 'VLC' / 'vlc.exe'))
    elif sys.platform == 'darwin':
        candidates.append('/Applications/VLC.app/Contents/MacOS/VLC')
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def open_iptv_in_vlc(device_id):
    executable = vlc_executable()
    if not executable:
        raise LookupError('VLC was not found. Install VLC, then restart AVTrack.')
    with connect() as con:
        row = con.execute("SELECT id,name,ip,port FROM devices WHERE id=? AND record_type='iptv'", (device_id,)).fetchone()
    if not row:
        raise LookupError('IPTV channel not found.')
    if not row['ip'] or not row['port']:
        raise ValueError('This channel needs an IP address and port before it can open in VLC.')
    stream = f"udp://@{row['ip']}:{row['port']}"
    subprocess.Popen([executable, stream], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return {'opened': stream, 'channel': row['name']}


def backup_storage_name(backup_id, filename):
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', filename).strip('._') or 'backup-file'
    return f'{backup_id}-{safe[:160]}'


def stored_backup_path(storage_name):
    if not storage_name or storage_name != Path(storage_name).name:
        raise ValueError('Invalid stored backup path.')
    return backup_directory() / storage_name


def write_stored_backup(storage_name, content):
    folder = backup_directory(); folder.mkdir(parents=True, exist_ok=True)
    destination = stored_backup_path(storage_name)
    temporary = folder / f'.{storage_name}.{os.getpid()}.tmp'
    temporary.write_bytes(content)
    temporary.replace(destination)
    return destination
DISCIPLINES = {'Video', 'Audio', 'Lighting', 'Control', 'Network', 'Other'}
SYSTEM_NAME_RULES = (
    ('audio', 'Audio'), ('amx', 'Control'), ('scheduler', 'Control'), ('dsp', 'Audio'),
    ('yamaha', 'Audio'), ('behringer', 'Audio'), ('shure', 'Audio'),
    ('clickshare', 'Video'), ('pixera', 'Video'), ('tv', 'Video'),
    ('video', 'Video'), ('led', 'Video'), ('light', 'Lighting'), ('cam', 'Video'),
    ('camera', 'Video'), ('bgm', 'Audio'), ('decoder', 'Video'),
    ('encoder', 'Video'), ('multiview', 'Video'), ('scala', 'Video'),
    ('blackmagic', 'Video'), ('castus', 'Video'),
    ('switch', 'Network'), ('dante', 'Audio'), ('cctv', 'Video'), ('iem', 'Audio'),
)
FIELDS = ('name', 'category', 'venue', 'discipline', 'ip', 'vlan', 'notes')
ALL_FIELDS = FIELDS + ('record_type', 'channel_source', 'port')
EQUIPMENT_FIELDS = ('brand', 'model', 'description', 'serial_number', 'quantity', 'location', 'notes')
EQUIPMENT_CONFIRM_FIELDS = EQUIPMENT_FIELDS[:-1]


SCHEMA = """CREATE TABLE {table} (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
    venue TEXT NOT NULL, discipline TEXT NOT NULL, ip TEXT NOT NULL,
    vlan INTEGER, notes TEXT NOT NULL DEFAULT '',
    record_type TEXT NOT NULL DEFAULT 'device', channel_source TEXT NOT NULL DEFAULT '',
    port INTEGER, ip_confirmed INTEGER NOT NULL DEFAULT 0, confirmation_required INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
EQUIPMENT_SCHEMA = """CREATE TABLE {table} (
    id INTEGER PRIMARY KEY, brand TEXT NOT NULL, model TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '', serial_number TEXT NOT NULL DEFAULT '',
    quantity INTEGER, location TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
    item_confirmed INTEGER NOT NULL DEFAULT 0, data_checked INTEGER NOT NULL DEFAULT 0,
    last_checked_at TEXT, data_checked_at TEXT, custom_values TEXT NOT NULL DEFAULT '{{}}',
    inventory_id INTEGER NOT NULL DEFAULT 1 REFERENCES equipment_inventories(id),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute(SCHEMA.format(table='IF NOT EXISTS devices'))
    columns = {row['name']: row for row in con.execute('PRAGMA table_info(devices)')}
    for column, definition in [('ip_confirmed', 'INTEGER NOT NULL DEFAULT 0'),
                               ('record_type', "TEXT NOT NULL DEFAULT 'device'"),
                               ('channel_source', "TEXT NOT NULL DEFAULT ''"), ('port', 'INTEGER')]:
        if column not in columns:
            con.execute(f'ALTER TABLE devices ADD COLUMN {column} {definition}')
    if 'confirmation_required' not in columns:
        con.execute('ALTER TABLE devices ADD COLUMN confirmation_required INTEGER NOT NULL DEFAULT 1')
        con.execute("UPDATE devices SET confirmation_required=0 WHERE record_type='iptv'")
        con.commit()
    if columns['vlan']['notnull']:
        # Rebuild the old table atomically to make VLAN optional for IPTV.
        # Copy every existing record, ID, timestamp, and confirmation without inventing ports.
        con.execute('BEGIN IMMEDIATE')
        try:
            con.execute(SCHEMA.format(table='devices_upgrade'))
            names = 'id,' + ','.join(ALL_FIELDS) + ',ip_confirmed,confirmation_required,updated_at'
            con.execute(f'INSERT INTO devices_upgrade ({names}) SELECT {names} FROM devices')
            con.execute('DROP TABLE devices')
            con.execute('ALTER TABLE devices_upgrade RENAME TO devices')
            con.commit()
        except Exception:
            con.rollback()
            con.close()
            raise
    con.execute('DROP INDEX IF EXISTS device_assignment')
    con.execute('DROP INDEX IF EXISTS device_assignment_known')
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS device_assignment_static ON devices(ip,vlan) WHERE record_type='device' AND ip NOT IN ('','DHCP')")
    con.execute('DROP TRIGGER IF EXISTS device_unique_ip_insert')
    con.execute('DROP TRIGGER IF EXISTS device_unique_ip_update')
    con.execute('DROP TRIGGER IF EXISTS device_known_ip_insert')
    con.execute('DROP TRIGGER IF EXISTS device_known_ip_update')
    # Preserve old records that share an IP across VLANs, but prevent new collisions.
    con.execute("""CREATE TRIGGER IF NOT EXISTS device_static_ip_insert
        BEFORE INSERT ON devices WHEN NEW.record_type='device' AND NEW.ip NOT IN ('','DHCP') AND EXISTS
        (SELECT 1 FROM devices WHERE record_type='device' AND ip=NEW.ip)
        BEGIN SELECT RAISE(ABORT, 'Duplicate AV IP address'); END""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS device_static_ip_update
        BEFORE UPDATE OF ip, record_type ON devices
        WHEN NEW.record_type='device' AND NEW.ip NOT IN ('','DHCP') AND (OLD.ip!=NEW.ip OR OLD.record_type!=NEW.record_type)
        AND EXISTS (SELECT 1 FROM devices WHERE record_type='device' AND ip=NEW.ip AND id!=NEW.id)
        BEGIN SELECT RAISE(ABORT, 'Duplicate AV IP address'); END""")
    con.execute('DROP INDEX IF EXISTS channel_endpoint')
    con.execute('DROP INDEX IF EXISTS channel_endpoint_known')
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS channel_endpoint_static ON devices(ip,port) WHERE record_type='iptv' AND ip NOT IN ('','DHCP') AND port IS NOT NULL")
    con.execute('CREATE TABLE IF NOT EXISTS equipment_inventories (id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE)')
    if 'layout' not in {r['name'] for r in con.execute('PRAGMA table_info(equipment_inventories)')}:
        con.execute("ALTER TABLE equipment_inventories ADD COLUMN layout TEXT NOT NULL DEFAULT '{}'")
    if not con.execute('SELECT 1 FROM equipment_inventories').fetchone():
        con.execute("INSERT OR IGNORE INTO equipment_inventories (id,name) VALUES (1,'Equipment inventory')")
        con.commit()
    con.execute(EQUIPMENT_SCHEMA.format(table='IF NOT EXISTS equipment'))
    equipment_columns = {row['name']: row for row in con.execute('PRAGMA table_info(equipment)')}
    if 'item_confirmed' not in equipment_columns:
        con.execute('ALTER TABLE equipment ADD COLUMN item_confirmed INTEGER NOT NULL DEFAULT 0')
    if 'custom_values' not in equipment_columns:
        con.execute("ALTER TABLE equipment ADD COLUMN custom_values TEXT NOT NULL DEFAULT '{}'")
    if 'data_checked' not in equipment_columns:
        con.execute('ALTER TABLE equipment ADD COLUMN data_checked INTEGER NOT NULL DEFAULT 0')
    if 'last_checked_at' not in equipment_columns:
        con.execute('ALTER TABLE equipment ADD COLUMN last_checked_at TEXT')
    if 'data_checked_at' not in equipment_columns:
        con.execute('ALTER TABLE equipment ADD COLUMN data_checked_at TEXT')
        con.execute('UPDATE equipment SET data_checked_at=updated_at WHERE data_checked=1')
    if 'inventory_id' not in equipment_columns:
        con.execute('ALTER TABLE equipment ADD COLUMN inventory_id INTEGER NOT NULL DEFAULT 1 REFERENCES equipment_inventories(id)')
    con.commit()
    if next(row for row in con.execute('PRAGMA table_info(equipment)') if row['name'] == 'quantity')['notnull']:
        # Preserve existing quantities; missing quantities are unknown, not zero or one.
        con.execute('BEGIN IMMEDIATE')
        try:
            con.execute(EQUIPMENT_SCHEMA.format(table='equipment_upgrade'))
            names = 'id,' + ','.join(EQUIPMENT_FIELDS) + ',item_confirmed,data_checked,last_checked_at,data_checked_at,custom_values,inventory_id,updated_at'
            con.execute(f'INSERT INTO equipment_upgrade ({names}) SELECT {names} FROM equipment')
            con.execute('DROP TABLE equipment')
            con.execute('ALTER TABLE equipment_upgrade RENAME TO equipment')
            con.commit()
        except Exception:
            con.rollback()
            con.close()
            raise
    con.execute('DROP INDEX IF EXISTS equipment_serial')
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS equipment_inventory_serial ON equipment(inventory_id, serial_number COLLATE NOCASE) WHERE serial_number != ''")
    con.execute('DROP INDEX IF EXISTS equipment_stock')
    con.execute('DROP INDEX IF EXISTS equipment_stock_known')
    stock_index=con.execute("SELECT sql FROM sqlite_master WHERE name='equipment_inventory_stock'").fetchone()
    if stock_index and 'description, notes,' not in stock_index['sql']:
        con.execute('DROP INDEX equipment_inventory_stock')
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS equipment_inventory_stock ON equipment(inventory_id, brand COLLATE NOCASE, model COLLATE NOCASE, description, notes, location COLLATE NOCASE) WHERE serial_number='' AND brand!='' AND model!='' AND location!='' AND custom_values='{}'")
    con.execute("""CREATE TABLE IF NOT EXISTS equipment_stock_checks (
        id INTEGER PRIMARY KEY, equipment_id INTEGER NOT NULL,
        checked_at TEXT NOT NULL, snapshot TEXT NOT NULL)""")
    con.execute('CREATE INDEX IF NOT EXISTS equipment_stock_check_item ON equipment_stock_checks(equipment_id,id)')
    con.execute("""CREATE TRIGGER IF NOT EXISTS equipment_delete_stock_history AFTER DELETE ON equipment
        BEGIN DELETE FROM equipment_stock_checks WHERE equipment_id=OLD.id; END""")
    con.execute("""CREATE TABLE IF NOT EXISTS equipment_record_checks (
        id INTEGER PRIMARY KEY, equipment_id INTEGER NOT NULL,
        checked_at TEXT NOT NULL, snapshot TEXT NOT NULL)""")
    con.execute('CREATE INDEX IF NOT EXISTS equipment_record_check_item ON equipment_record_checks(equipment_id,id)')
    con.execute("""CREATE TRIGGER IF NOT EXISTS equipment_delete_record_history AFTER DELETE ON equipment
        BEGIN DELETE FROM equipment_record_checks WHERE equipment_id=OLD.id; END""")
    con.execute("""CREATE TABLE IF NOT EXISTS av_backups (
        id INTEGER PRIMARY KEY, equipment_type TEXT NOT NULL, device_name TEXT NOT NULL,
        filename TEXT NOT NULL, content BLOB NOT NULL, size INTEGER NOT NULL,
        notes TEXT NOT NULL DEFAULT '', storage_name TEXT NOT NULL DEFAULT '',
        icon_storage_name TEXT NOT NULL DEFAULT '', icon_mime TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    backup_columns={row['name'] for row in con.execute('PRAGMA table_info(av_backups)')}
    if 'storage_name' not in backup_columns:
        con.execute("ALTER TABLE av_backups ADD COLUMN storage_name TEXT NOT NULL DEFAULT ''")
    if 'icon_storage_name' not in backup_columns:
        con.execute("ALTER TABLE av_backups ADD COLUMN icon_storage_name TEXT NOT NULL DEFAULT ''")
    if 'icon_mime' not in backup_columns:
        con.execute("ALTER TABLE av_backups ADD COLUMN icon_mime TEXT NOT NULL DEFAULT ''")
    # Existing database-backed files are extracted once into the visible backup folder.
    for row in con.execute("SELECT id,filename,content FROM av_backups WHERE storage_name='' AND length(content)>0"):
        storage_name=backup_storage_name(row['id'],row['filename'])
        write_stored_backup(storage_name,row['content'])
        con.execute("UPDATE av_backups SET storage_name=?,content=X'' WHERE id=?",(storage_name,row['id']))
    import_sessions.initialize(con)
    operations.initialize(con)
    return con


def serialize(record):
    row = dict(record)
    if row['record_type'] == 'iptv':
        row.update(venue='', vlan=None)
        if not row.get('confirmation_required'):row['ip_confirmed']=0
    else:
        row['venue'] = clean_venue(row['venue'])
    return row


def clean_venue(value):
    return re.sub(r'^RD\s+', '', value.strip(), flags=re.IGNORECASE).strip()


def validate(value):
    if not isinstance(value, dict):
        raise ValueError('Each device must be an object.')
    record_type = value.get('record_type') or 'device'
    if record_type not in ('device', 'iptv'):
        raise ValueError('Inventory type must be device or iptv.')
    channel_source = value.get('channel_source') or ''
    if record_type == 'iptv' and channel_source not in ('', 'Onboard', 'Satellite'):
        raise ValueError('Choose Onboard or Satellite for the IPTV channel source.')
    result = {'record_type': record_type, 'channel_source': channel_source if record_type == 'iptv' else ''}
    for field in ('name', 'category', 'venue', 'discipline', 'ip', 'notes'):
        raw = value.get(field, '')
        if raw is None:
            raw = ''
        if not isinstance(raw, str):
            raise ValueError(f'{field.capitalize()} must be text.')
        result[field] = raw.strip()
        if len(result[field]) > (2000 if field == 'notes' else 120):
            raise ValueError(f'{field.capitalize()} is too long.')
    if record_type == 'iptv':
        result.update(venue='')
    else:
        result['venue'] = clean_venue(result['venue'])
    if result['discipline'] and result['discipline'] not in DISCIPLINES:
        raise ValueError('Choose a valid system: Video, Audio, Lighting, Control, Network, or Other.')
    if result['ip'].upper() == 'DHCP':
        result['ip'] = 'DHCP'
    elif result['ip']:
        try:
            address = ipaddress.IPv4Address(result['ip'])
        except ipaddress.AddressValueError:
            raise ValueError('Enter a valid IPv4 address, such as 192.0.2.10.') from None
        if address.is_unspecified or address.is_loopback or (address.is_multicast and record_type != 'iptv') or int(address) == 0xffffffff:
            raise ValueError('Use a valid device address; multicast addresses are only allowed for IPTV channels.')
        result['ip'] = str(address)
    if record_type == 'iptv':
        port = value.get('port')
        if port is None or port == '':
            result.update(port=None, vlan=None)
        elif isinstance(port, bool) or not isinstance(port, (str, int)) or not str(port).isascii() or not str(port).isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError('Port must be a whole number from 1 to 65535.')
        else:
            result.update(port=int(port), vlan=None)
    else:
        vlan = value.get('vlan')
        if vlan is None or vlan == '':
            result.update(vlan=None, port=None)
        elif isinstance(vlan, bool) or not isinstance(vlan, (str, int)) or not str(vlan).isascii() or not str(vlan).isdigit():
            raise ValueError('VLAN must be a whole number from 1 to 4094.')
        else:
            result['vlan'] = int(vlan)
            if not 1 <= result['vlan'] <= 4094:
                raise ValueError('VLAN must be between 1 and 4094.')
        result['port'] = None
    if not any(result[f] is not None and result[f] != '' for f in ALL_FIELDS if f != 'record_type'):
        raise ValueError('Provide at least one device or channel detail.')
    return result


def inventory():
    with connect() as con:
        return [serialize(row) for row in con.execute('SELECT * FROM devices ORDER BY venue COLLATE NOCASE, name COLLATE NOCASE')]


def rename_device_venue(value):
    if not isinstance(value, dict) or not all(isinstance(value.get(key), str) for key in ('old_name', 'new_name')):
        raise ValueError('Choose a venue and enter its new name.')
    old, new = clean_venue(value['old_name']), clean_venue(value['new_name'])
    if not old or not new or len(new) > 120:
        raise ValueError('Use a venue name between 1 and 120 characters.')
    expected = value.get('expected_ids')
    if not isinstance(expected, list) or any(type(item) is not int or item < 1 for item in expected):
        raise ValueError('Refresh the Devices workspace before renaming a venue.')
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        rows = list(con.execute("SELECT id, venue FROM devices WHERE record_type='device'"))
        matching = [row for row in rows if clean_venue(row['venue']) == old]
        if not matching:
            raise LookupError('This venue no longer exists. Refresh the Devices workspace.')
        if set(expected) != {row['id'] for row in matching}:
            raise ValueError('Devices in this venue changed. Refresh and try again.')
        if any(clean_venue(row['venue']).casefold() == new.casefold() and clean_venue(row['venue']) != old for row in rows):
            raise ValueError('Another venue already uses that name. Choose a different name.')
        if old != new:
            for row in matching:
                con.execute('UPDATE devices SET venue=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (new, row['id']))
                operations.audit(con, 'device', row['id'], 'venue_renamed', {'from': old, 'to': new})
        return {'renamed': len(matching), 'old_name': old, 'new_name': new}


def save_device(value, device_id=None):
    creating=device_id is None
    row = validate(value)
    with connect() as con:
        if device_id is None:
            row['confirmation_required']=int(row['record_type']=='device')
            cursor = con.execute('INSERT INTO devices (' + ','.join(ALL_FIELDS) + ',confirmation_required) VALUES (' + ','.join('?' for _ in (*ALL_FIELDS,'confirmation_required')) + ')', [row[f] for f in (*ALL_FIELDS,'confirmation_required')])
            device_id = cursor.lastrowid
        else:
            cursor = con.execute('UPDATE devices SET ' + ','.join(f + '=?' for f in ALL_FIELDS) + ', ip_confirmed=CASE WHEN ip=? AND vlan IS ? AND port IS ? THEN ip_confirmed ELSE 0 END, updated_at=CURRENT_TIMESTAMP WHERE id=?', [row[f] for f in ALL_FIELDS] + [row['ip'], row['vlan'], row['port'], device_id])
            if cursor.rowcount == 0:
                raise LookupError('Device not found.')
        operations.audit(con,row['record_type'],device_id,'created' if creating else 'record_edited',{'initials':str(value.get('initials',''))[:40]})
        return serialize(con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone())


def confirm_ip(device_id, value):
    if not isinstance(value, dict):
        raise ValueError('Provide the IP and VLAN being confirmed.')
    with connect() as con:
        record = con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone()
        if record is None:
            raise LookupError('Device not found.')
        if not record['confirmation_required']:
            raise ValueError('This record does not require IP confirmation.')
        # Check the stored address and assignment, not just a stale browser value.
        row = validate(dict(record))
        if not row['ip']:
            raise ValueError('Add an IP address before confirming it.')
        if row['ip'] == 'DHCP':
            raise ValueError('DHCP does not have a fixed IP address to confirm.')
        if value.get('ip') != row['ip'] or value.get('vlan') != row['vlan'] or (row['record_type']=='iptv' and value.get('port')!=row['port']):
            raise ValueError('The IP or VLAN has changed. Refresh the inventory before confirming.')
        cursor = con.execute('UPDATE devices SET ip_confirmed=1, updated_at=CURRENT_TIMESTAMP WHERE id=? AND ip=? AND vlan IS ?', (device_id, row['ip'], row['vlan']))
        if not cursor.rowcount:
            raise ValueError('The assignment has changed. Refresh before confirming.')
        operations.audit(con,row['record_type'],device_id,'ip_manually_verified',{'method':'Manual reachability check','initials':str(value.get('initials',''))[:40]})
        return serialize(con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone())


def device_identity(row):
    if row['ip'] in ('', 'DHCP') or (row['record_type'] == 'iptv' and row['port'] is None):
        return None
    return (row['record_type'], row['ip'], row['port'] if row['record_type'] == 'iptv' else None)


def blank_import_row(value, fields):
    return isinstance(value, dict) and all(value.get(f) is None or (isinstance(value.get(f), str) and not value[f].strip()) for f in fields)


def set_device_system(device_id, value):
    if not isinstance(value, dict) or not isinstance(value.get('discipline', ''), str):
        raise ValueError('System must be text.')
    discipline = value.get('discipline', '').strip()
    if discipline and discipline not in DISCIPLINES:
        raise ValueError('Choose a valid system.')
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        record = con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone()
        if record is None:
            raise LookupError('Device not found.')
        if record['record_type'] != 'device':
            raise ValueError('System dropdowns apply to devices.')
        con.execute('UPDATE devices SET discipline=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (discipline, device_id))
        return serialize(con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone())


def set_device_notes(device_id, value):
    if not isinstance(value, dict) or not isinstance(value.get('notes', ''), str):
        raise ValueError('Notes must be text.')
    notes = value.get('notes', '').strip()
    if len(notes) > 2000:
        raise ValueError('Notes are too long.')
    with connect() as con:
        guarded = 'original_notes' in value
        if guarded and not isinstance(value['original_notes'], str):
            raise ValueError('Original notes must be text.')
        statement = 'UPDATE devices SET notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?'
        if not con.execute(statement + (' AND notes=?' if guarded else ''),
                           (notes, device_id, value['original_notes']) if guarded else (notes, device_id)).rowcount:
            if con.execute('SELECT 1 FROM devices WHERE id=?', (device_id,)).fetchone():
                raise ValueError('Notes changed in another window. Your draft was kept; reopen the note to review the latest text.')
            raise LookupError('Device not found.')
        current=con.execute('SELECT record_type FROM devices WHERE id=?',(device_id,)).fetchone()
        operations.audit(con,current['record_type'],device_id,'notes_edited',{'initials':str(value.get('initials',''))[:40]})
        return serialize(con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone())


def system_from_name(name):
    # Follow the user's rule order when several keywords match the same name.
    name = name.casefold()
    return next((system for keyword, system in SYSTEM_NAME_RULES if keyword in name), '')


def import_devices(payload, connection=None):
    if not isinstance(payload, dict) or payload.get('version') != 1 or not isinstance(payload.get('devices'), list):
        raise ValueError('Choose an avtrack network JSON export (version 1).')
    if len(payload['devices']) > 10000:
        raise ValueError('Import supports up to 10,000 devices per file.')
    spreadsheet = payload.get('source') == 'spreadsheet'
    row_numbers = payload.get('row_numbers') if spreadsheet else None
    if row_numbers is not None and (not isinstance(row_numbers, list) or len(row_numbers) != len(payload['devices']) or any(type(n) is not int or not 1 <= n <= 20050 for n in row_numbers)):
        raise ValueError('Invalid spreadsheet row numbers.')
    rows, numbers = [], []
    for index, value in enumerate(payload['devices'], 1):
        number = row_numbers[index - 1] if row_numbers else index
        if blank_import_row(value, FIELDS + ('channel_source', 'port')):
            continue
        try:
            if spreadsheet and isinstance(value, dict) and value.get('record_type', 'device') == 'device':
                value = dict(value)
                vlan = value.get('vlan')
                if isinstance(vlan, str):
                    vlan = vlan.strip()
                # Ignore text or decimal VLAN values; never invent a VLAN number.
                value['vlan'] = vlan if type(vlan) is int or (isinstance(vlan, str) and vlan.isascii() and vlan.isdigit()) else None
            if isinstance(value, dict) and value.get('record_type') == 'iptv':
                value = dict(value, notes='')
            row = validate(value)
            if row['record_type'] == 'device' and not row['discipline']:
                row['discipline'] = system_from_name(row['name'])
            required=value.get('confirmation_required',payload.get('confirmation_required',row['record_type']=='device'))
            if type(required) not in (bool,int) or required not in (0,1):raise ValueError('Choose whether IP confirmation is required.')
            row['confirmation_required']=int(required)
            rows.append(row)
            numbers.append(number)
        except ValueError as exc:
            raise ValueError(f'Device row {number}: {exc} Nothing was imported.') from None
    # A single transaction makes imports atomic. Existing records are never overwritten.
    with (nullcontext(connection) if connection is not None else connect()) as con:
        if connection is None:con.execute('BEGIN IMMEDIATE')
        existing = {identity for row in con.execute('SELECT record_type, ip, port FROM devices') if (identity := device_identity(row)) is not None}
        added = 0
        warnings = []
        seen = set()
        for index, row in enumerate(rows, 1):
            identity = device_identity(row)
            if identity is not None and identity in existing:
                if row['record_type'] == 'device' and (spreadsheet or identity in seen):
                    number = numbers[index - 1]
                    reason = 'already appears earlier in this file' if identity in seen else 'already exists in the inventory'
                    warnings.append(f"Row {number}: {row['name']} · {row['venue']} · duplicate IP {row['ip']} {reason}. Skipped; the first record was kept.")
                seen.add(identity)
                continue
            con.execute('INSERT INTO devices (' + ','.join(ALL_FIELDS) + ',confirmation_required) VALUES (' + ','.join('?' for _ in (*ALL_FIELDS,'confirmation_required')) + ')', [row[f] for f in (*ALL_FIELDS,'confirmation_required')])
            if identity is not None:
                existing.add(identity)
                seen.add(identity)
            added += 1
    result = {'added': added, 'skipped': len(rows) - added}
    if spreadsheet or warnings:
        result['warnings'] = warnings
    return result


def validate_equipment(value):
    if not isinstance(value, dict):
        raise ValueError('Each inventory item must be an object.')
    row = {}
    for field in EQUIPMENT_FIELDS:
        if field == 'quantity':
            continue
        raw = value.get(field, '')
        if raw is None:
            raw = ''
        if not isinstance(raw, str):
            raise ValueError(f'{field.replace("_", " ").title()} must be text.')
        row[field] = normalize_serial(raw) if field == 'serial_number' else raw.strip()
        if len(row[field]) > (2000 if field in ('description', 'notes') else 120):
            raise ValueError(f'{field.replace("_", " ").title()} is too long.')
    quantity = value.get('quantity')
    if quantity is None or quantity == '':
        row['quantity'] = None
    elif isinstance(quantity, bool) or not isinstance(quantity, (str, int)) or not str(quantity).isascii() or not str(quantity).isdigit() or not 0 <= int(quantity) <= 1000000:
        raise ValueError('Quantity must be a whole number from 0 to 1,000,000.')
    else:
        row['quantity'] = int(quantity)
    if not any(v is not None and v != '' for v in row.values()) and not (isinstance(value.get('custom_values'), dict) and any(isinstance(v,str) and v.strip() for v in value['custom_values'].values())):
        raise ValueError('Provide at least one equipment detail.')
    return row


def normalize_serial(value):
    """Use commas between serials and ignore whitespace inside each serial."""
    parts=[]
    for part in re.split(r'[,|;\r\n]+',value):
        serial=re.sub(r'\s+','',part)
        if serial and serial.casefold() not in {saved.casefold() for saved in parts}:parts.append(serial)
    return ', '.join(parts)


def serial_key(value):
    return re.sub(r'\s+','',str(value or '')).casefold()


def equipment_inventory_id(value=1):
    if type(value) is int and 0 < value <= 9223372036854775807:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit() and 0 < int(value) <= 9223372036854775807:
        return int(value)
    raise ValueError('Choose an inventory using a positive whole number.')


def equipment_inventory_details(con, inventory_id):
    record = con.execute('SELECT * FROM equipment_inventories WHERE id=?', (equipment_inventory_id(inventory_id),)).fetchone()
    if record is None:
        raise LookupError('Inventory not found.')
    record = dict(record)
    layout = json.loads(record.pop('layout'))
    if layout.get('template')=='tv' or layout.get('stock_mode')=='tv_counts':
        layout['columns']=[dict(column,type='select',options=['LG','Samsung']+[option for option in column.get('options',[]) if option.casefold() not in ('lg','samsung')][:48],allow_custom=True) if column['key']=='brand' else column for column in layout['columns'] if column['key']!='serial_number']
        if layout.get('primary_search')=='serial_number': layout['primary_search']='model'
        if layout.get('identifier')=='serial_number': layout['identifier']='model'
        layout['columns']=[dict(column,label='Total') if column['key']=='total_count' and column['label'].casefold()=='total count' else column for column in layout['columns']]
    # Apply Scala's display rules to existing inventories as well as new presets.
    keys = {column['key'] for column in layout.get('columns', [])}
    if 'scala' in record['name'].casefold() or {'monitor_model','orientation'}.issubset(keys):
        layout = dict(layout or DEFAULT_PROFILE)
        layout['columns'] = [dict(column,label='Where') if column['key']=='location' else column for column in layout['columns'] if column['key'] != 'serial_number']
        if not layout['columns']:
            layout['columns'] = [dict(SCALA_PROFILE['columns'][0])]
        keys = {column['key'] for column in layout['columns']}
        if layout.get('primary_search') not in keys:
            layout['primary_search'] = 'asset_id' if 'asset_id' in keys else layout['columns'][0]['key']
        if layout.get('identifier') and layout['identifier'] not in keys:
            layout['identifier'] = 'asset_id' if 'asset_id' in keys else ''
        layout['show_status'] = False
        layout['show_record_check'] = False
        layout['stock_check_history'] = False
        layout['unique_location'] = True
    if layout.get('confirmation_mode'):layout['show_status']=layout['confirmation_mode']!='none'
    if layout: record['layout'] = with_unit_status(layout)
    return record


def equipment_record(record):
    row = dict(record)
    values = json.loads(row.pop('custom_values', '{}'))
    if values: row['custom_values'] = values
    return row


def equipment_complete(row, profile):
    """Completion uses this inventory's required columns; optional notes stay optional."""
    return all(column_value(row, col['key']) not in ('', None)
               and str(column_value(row, col['key'])).strip() != ''
               for col in profile['columns'] if col.get('important') and col['key'] != 'orientation')


def record_inventory_check(con, item_id, reason, source=None):
    checked_at = con.execute("SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now')").fetchone()[0]
    operations.audit(con, 'equipment', item_id, 'inventory_checked',
                     {'checked_at': checked_at, 'reason': reason, 'source': source})


def equipment_checked_record(con, record):
    row = equipment_record(record)
    # Keep historical physical-count dates intact. Automatic checks live in audit
    # metadata, already preserved by every schema-2 complete backup.
    check = con.execute("SELECT details FROM record_audit AS checks WHERE record_type='equipment' "
                        "AND record_id=? AND action='inventory_checked' AND NOT EXISTS ("
                        "SELECT 1 FROM record_audit AS undone WHERE undone.record_type='equipment' "
                        "AND undone.record_id=checks.record_id AND undone.action='import_undone' "
                        "AND json_extract(undone.details,'$.source')=json_extract(checks.details,'$.source')) "
                        "AND id > COALESCE("
                        "(SELECT MAX(id) FROM record_audit WHERE record_type='equipment' "
                        "AND record_id=? AND action IN ('created','import_added')),0) "
                        "ORDER BY id DESC LIMIT 1", (row['id'], row['id'])).fetchone()
    automatic = json.loads(check['details']).get('checked_at') if check else None
    row['inventory_checked_at'] = max(filter(None, (automatic, row.get('last_checked_at'))), default=None)
    return row


def equipment_inventories():
    with connect() as con:
        return [equipment_inventory_details(con,row['id']) for row in con.execute('SELECT id FROM equipment_inventories ORDER BY name COLLATE NOCASE')]


def workspace_overview():
    with connect() as con:
        # One query keeps every home card on the same database snapshot.
        row = con.execute("""SELECT
            (SELECT COUNT(*) FROM devices WHERE record_type='device') AS av_total,
            (SELECT COUNT(*) FROM devices WHERE record_type='device' AND ip_confirmed=1 AND ip NOT IN ('','DHCP')) AS av_validated,
            (SELECT COUNT(*) FROM devices WHERE record_type='iptv') AS iptv_total,
            (SELECT COUNT(*) FROM devices WHERE record_type='iptv' AND channel_source='Onboard') AS iptv_onboard,
            (SELECT COUNT(*) FROM devices WHERE record_type='iptv' AND channel_source='Satellite') AS iptv_satellite,
            (SELECT COUNT(*) FROM equipment) AS inventory_total,
            (SELECT COUNT(DISTINCT NULLIF(location,'')) FROM equipment) AS inventory_locations,
            (SELECT COUNT(*) FROM equipment_inventories i
             WHERE i.name!='Equipment inventory' OR EXISTS (SELECT 1 FROM equipment e WHERE e.inventory_id=i.id)) AS inventory_count,
            (SELECT COUNT(*) FROM av_backups) AS backup_total,
            (SELECT COALESCE(SUM(size),0) FROM av_backups) AS backup_size""").fetchone()
        result=dict(row)
        inventories=[equipment_inventory_details(con,r['id']) for r in con.execute('SELECT id FROM equipment_inventories')]
        quantity_ids={record['id'] for record in inventories if any(col['key']=='quantity' or col['type'] in ('count','calculated') for col in record.get('layout',DEFAULT_PROFILE)['columns'])}
        result['inventory_units']=sum((r['quantity'] or 0) if r['inventory_id'] in quantity_ids else 1 for r in con.execute('SELECT inventory_id,quantity FROM equipment'))
        storage_ids={record['id'] for record in inventories if record.get('layout',{}).get('location_role','geographic' if 'scala' in record['name'].casefold() else 'storage')=='storage'}
        result['inventory_locations']=len({r['location'] for r in con.execute('SELECT inventory_id,location FROM equipment') if r['inventory_id'] in storage_ids and r['location']})
        return result


def save_equipment_inventory(value, inventory_id=None):
    name = value.get('name') if isinstance(value, dict) else None
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise ValueError('Enter an inventory name from 1 to 120 characters.')
    layout = validate_profile(value['layout']) if 'layout' in value else None
    with connect() as con:
        previous_mode=None
        if inventory_id is None:
            inventory_id = con.execute('INSERT INTO equipment_inventories (name) VALUES (?)', (name.strip(),)).lastrowid
        else:
            previous=equipment_inventory_details(con, inventory_id).get('layout',DEFAULT_PROFILE)
            previous_mode=previous.get('confirmation_mode', 'none' if previous.get('show_status') is False else 'storage')
            con.execute('UPDATE equipment_inventories SET name=? WHERE id=?', (name.strip(), inventory_id))
        if layout is not None:
            if previous_mode is not None and layout.get('confirmation_mode',previous_mode)!=previous_mode:
                con.execute('UPDATE equipment SET item_confirmed=0 WHERE inventory_id=?',(inventory_id,))
            con.execute('UPDATE equipment_inventories SET layout=? WHERE id=?',(json.dumps(layout),inventory_id))
        return equipment_inventory_details(con, inventory_id)


def delete_equipment_inventory(inventory_id, value):
    if not isinstance(value, dict):
        raise ValueError('Confirm the inventory to delete.')
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        inventory = equipment_inventory_details(con, inventory_id)
        if 'name' in value and value['name'] != inventory['name']:
            raise ValueError('The inventory name changed. Refresh and confirm deletion again.')
        next_id = con.execute('SELECT MAX(id)+1 FROM equipment_inventories').fetchone()[0]
        count = con.execute('DELETE FROM equipment WHERE inventory_id=?', (inventory_id,)).rowcount
        con.execute('DELETE FROM equipment_inventories WHERE id=?', (inventory_id,))
        con.execute('UPDATE import_sessions SET retired=1 WHERE target=?',(f'equipment:{inventory_id}',))
        con.execute('DELETE FROM import_preferences WHERE target=?',(f'equipment:{inventory_id}',))
        # Keep the application ready for a new import after deleting the final inventory.
        if not con.execute('SELECT 1 FROM equipment_inventories').fetchone():
            con.execute('INSERT INTO equipment_inventories (id,name) VALUES (?,?)', (next_id, 'Equipment inventory'))
        return {'deleted': inventory_id, 'deleted_items': count}


def equipment_inventory(inventory_id=1):
    with connect() as con:
        equipment_inventory_details(con, inventory_id)
        return [equipment_checked_record(con, row) for row in con.execute('SELECT * FROM equipment WHERE inventory_id=? ORDER BY location COLLATE NOCASE, brand COLLATE NOCASE, model COLLATE NOCASE', (inventory_id,))]


def save_equipment(value, item_id=None):
    creating=item_id is None
    row = validate_equipment(value)
    if creating:
        shelf=value.get('shelf','')
        if not isinstance(shelf,str) or len(shelf.strip())>120:
            raise ValueError('Shelf must be text, up to 120 characters.')
        if shelf.strip():
            row['notes']='\n'.join(filter(None,(row['notes'],'Shelf: '+shelf.strip())))
            if len(row['notes'])>2000:raise ValueError('Notes including shelf must be up to 2,000 characters.')
    inventory_id = equipment_inventory_id(value.get('inventory_id', 1))
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        profile = equipment_inventory_details(con, inventory_id).get('layout', DEFAULT_PROFILE)
        values = custom_values(value.get('custom_values'), profile)
        row=normalize_template_row(dict(row,custom_values=values),profile)
        identifier = profile_identifier(dict(row,custom_values=values), profile)
        enforce_identifier=creating or profile.get('stock_mode')!='tv_counts'
        if identifier and enforce_identifier and any(profile_identifier(equipment_record(saved),profile)==identifier for saved in con.execute('SELECT * FROM equipment WHERE inventory_id=? AND id!=?',(inventory_id,item_id or 0))):
            raise ValueError('This item identifier already exists in this inventory.')
        if profile.get('unique_location') and row['location'] and any(saved['location'].strip().casefold()==row['location'].casefold() for saved in con.execute('SELECT location FROM equipment WHERE inventory_id=? AND id!=?',(inventory_id,item_id or 0))):
            raise ValueError('This Scala location already has an item. Each location must be unique.')
        previous = con.execute('SELECT * FROM equipment WHERE id=? AND inventory_id=?', (item_id, inventory_id)).fetchone() if item_id is not None else None
        # Browser edits carry their source values so another tab cannot silently
        # overwrite newer counts, notes, condition, or custom inventory fields.
        if item_id is not None and '_original' in value:
            original=value['_original']
            if previous is None:
                raise LookupError('Inventory item not found.')
            current=equipment_record(previous)
            checked_fields=EQUIPMENT_FIELDS
            if not isinstance(original,dict) or any(field not in original for field in checked_fields):
                raise ValueError('Provide the original inventory values before saving.')
            if any(original[field] != current[field] for field in checked_fields) or original.get('custom_values',{}) != current.get('custom_values',{}):
                raise ValueError('This inventory item changed in another tab or session. Refresh the inventory and reopen the item before saving.')
        if item_id is None:
            cursor = con.execute('INSERT INTO equipment (' + ','.join(EQUIPMENT_FIELDS) + ',inventory_id,custom_values) VALUES (?,?,?,?,?,?,?,?,?)', [row[f] for f in EQUIPMENT_FIELDS] + [inventory_id,json.dumps(values,sort_keys=True)])
            item_id = cursor.lastrowid
        else:
            unchanged = ' AND '.join(f'{field} IS ?' for field in EQUIPMENT_CONFIRM_FIELDS)
            cursor = con.execute('UPDATE equipment SET data_checked=CASE WHEN ' + unchanged +
                ' AND notes IS ? THEN data_checked ELSE 0 END, item_confirmed=CASE WHEN ' + unchanged +
                ' THEN item_confirmed ELSE 0 END, ' + ','.join(f+'=?' for f in EQUIPMENT_FIELDS) +
                ', updated_at=CURRENT_TIMESTAMP WHERE id=? AND inventory_id=?',
                [row[f] for f in EQUIPMENT_CONFIRM_FIELDS] + [row['notes']] + [row[f] for f in EQUIPMENT_CONFIRM_FIELDS] + [row[f] for f in EQUIPMENT_FIELDS] + [item_id, inventory_id])
            if not cursor.rowcount:
                raise LookupError('Inventory item not found.')
        con.execute('UPDATE equipment SET custom_values=?, data_checked=CASE WHEN custom_values=? THEN data_checked ELSE 0 END, item_confirmed=CASE WHEN custom_values=? THEN item_confirmed ELSE 0 END WHERE id=?', (json.dumps(values,sort_keys=True), json.dumps(values,sort_keys=True), json.dumps(values,sort_keys=True),item_id))
        con.execute('UPDATE equipment SET data_checked_at=CASE WHEN data_checked=1 THEN data_checked_at ELSE NULL END WHERE id=?',(item_id,))
        operations.audit(con,'equipment',item_id,'created' if creating else 'record_edited',{'initials':str(value.get('initials',''))[:40]})
        if previous is not None and not equipment_complete(equipment_record(previous), profile) and equipment_complete(dict(row, custom_values=values), profile):
            record_inventory_check(con, item_id, 'Required fields completed')
        return equipment_checked_record(con, con.execute('SELECT * FROM equipment WHERE id=?', (item_id,)).fetchone())


def remove_equipment_unit(item_id, value):
    """Remove the chosen unit without overwriting concurrent stock edits."""
    if not isinstance(value, dict):
        raise ValueError('Choose the unit to remove.')
    inventory_id = equipment_inventory_id(value.get('inventory_id', 1))
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        current = con.execute('SELECT * FROM equipment WHERE id=? AND inventory_id=?', (item_id, inventory_id)).fetchone()
        if current is None:
            raise LookupError('Inventory item not found.')
        if current['quantity'] != value.get('original_quantity') or current['serial_number'] != value.get('original_serial_number'):
            raise ValueError('Stock changed. Close this dialog and refresh before removing a unit.')
        if (equipment_inventory_details(con, inventory_id).get('layout') or {}).get('stock_mode') == 'tv_counts':
            raise ValueError('Edit the stock count for the location to remove a television unit.')
        if current['quantity'] is None or current['quantity'] <= 1:
            raise ValueError('Use Delete equipment to remove the last unit.')
        serials = list(dict.fromkeys(re.sub(r'\s+', '', serial) for serial in re.split(r'[\r\n,|;]+', current['serial_number']) if serial.strip()))
        serial = value.get('serial')
        if serial is None:
            if len(serials) >= current['quantity']:
                raise ValueError('Choose the serial number of the unit to remove.')
        elif serial not in serials:
            raise ValueError('Choose a serial number from this row.')
        else:
            serials.remove(serial)
        con.execute('UPDATE equipment SET quantity=quantity-1, serial_number=?, data_checked=0, data_checked_at=NULL, item_confirmed=0, updated_at=CURRENT_TIMESTAMP WHERE id=? AND inventory_id=?',
                    (', '.join(serials), item_id, inventory_id))
        operations.audit(con,'equipment',item_id,'unit_removed',{'serial':serial,'quantity_before':current['quantity'],'quantity_after':current['quantity']-1,'reason':str(value.get('reason',''))[:1000],'initials':str(value.get('initials',''))[:40]})
        return equipment_checked_record(con, con.execute('SELECT * FROM equipment WHERE id=?', (item_id,)).fetchone())


def set_equipment_notes(item_id, value):
    if not isinstance(value,dict) or not isinstance(value.get('notes'),str) or len(value['notes'].strip())>2000 or not isinstance(value.get('original_notes'),str):
        raise ValueError('Provide notes up to 2,000 characters and their original value.')
    inventory_id=equipment_inventory_id(value.get('inventory_id',1))
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        current=con.execute('SELECT * FROM equipment WHERE id=? AND inventory_id=?',(item_id,inventory_id)).fetchone()
        if current is None:raise LookupError('Inventory item not found.')
        if current['notes']!=value['original_notes']:
            raise ValueError('Notes changed since you opened them. Close and reopen Notes to review the latest version.')
        notes=value['notes'].strip()
        con.execute('UPDATE equipment SET data_checked=CASE WHEN notes=? THEN data_checked ELSE 0 END, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND inventory_id=?',(notes,notes,item_id,inventory_id))
        con.execute('UPDATE equipment SET data_checked_at=CASE WHEN data_checked=1 THEN data_checked_at ELSE NULL END WHERE id=?',(item_id,))
        operations.audit(con,'equipment',item_id,'notes_edited',{'initials':str(value.get('initials',''))[:40]})
        return equipment_checked_record(con, con.execute('SELECT * FROM equipment WHERE id=?',(item_id,)).fetchone())


def set_equipment_confirmation(item_id, value):
    if not isinstance(value, dict) or type(value.get('item_confirmed')) is not bool:
        raise ValueError('Choose whether this item has been located.')
    if any(field not in value for field in EQUIPMENT_CONFIRM_FIELDS):
        raise ValueError('Provide the current item details being confirmed.')
    row = validate_equipment(value)
    inventory_id = equipment_inventory_id(value.get('inventory_id', 1))
    with connect() as con:
        equipment_inventory_details(con, inventory_id)
        current = con.execute('SELECT * FROM equipment WHERE id=? AND inventory_id=?', (item_id, inventory_id)).fetchone()
        if current is None:
            raise LookupError('Inventory item not found.')
        profile = equipment_inventory_details(con,inventory_id).get('layout',DEFAULT_PROFILE)
        if profile.get('confirmation_mode')=='ip' and value['item_confirmed']:
            column=next((col for col in profile['columns'] if col['key'] in ('ip','ip_address','multicast_ip') or re.search(r'\bip\b',col['label'],re.I)),None)
            address=column_value(equipment_record(current),column['key']) if column else ''
            if not address:raise ValueError('Add the IP address before confirming this item.')
            try:ipaddress.IPv4Address(address)
            except ipaddress.AddressValueError:raise ValueError('Use a valid IPv4 address before confirming.') from None
        if custom_values(value.get('custom_values'),profile) != json.loads(current['custom_values']):
            raise ValueError('This item changed. Refresh before confirming or reviewing it.')
        matches = ' AND '.join(f'{field} IS ?' for field in EQUIPMENT_CONFIRM_FIELDS)
        cursor = con.execute('UPDATE equipment SET item_confirmed=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND ' + matches,
            [int(value['item_confirmed']), item_id] + [row[f] for f in EQUIPMENT_CONFIRM_FIELDS])
        if not cursor.rowcount:
            raise ValueError('This item changed. Refresh the inventory before confirming it.')
        operations.audit(con,'equipment',item_id,'location_checked',{'method':'Manual location check','initials':str(value.get('initials',''))[:40],'located':value['item_confirmed']})
        if value['item_confirmed']:
            record_inventory_check(con, item_id, 'IP confirmed' if profile.get('confirmation_mode') == 'ip' else 'Marked Located')
        return equipment_checked_record(con, con.execute('SELECT * FROM equipment WHERE id=?', (item_id,)).fetchone())


def set_equipment_review(item_id, value):
    if not isinstance(value, dict) or type(value.get('data_checked')) is not bool:
        raise ValueError('Choose whether this item has been reviewed.')
    if any(field not in value for field in (*EQUIPMENT_CONFIRM_FIELDS, 'notes')):
        raise ValueError('Provide the current item details being confirmed.')
    row = validate_equipment(value)
    inventory_id = equipment_inventory_id(value.get('inventory_id', 1))
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        equipment_inventory_details(con, inventory_id)
        current = con.execute('SELECT * FROM equipment WHERE id=? AND inventory_id=?', (item_id, inventory_id)).fetchone()
        if current is None:
            raise LookupError('Inventory item not found.')
        profile = equipment_inventory_details(con,inventory_id).get('layout',DEFAULT_PROFILE)
        if custom_values(value.get('custom_values'),profile) != json.loads(current['custom_values']):
            raise ValueError('This item changed. Refresh before confirming or reviewing it.')
        matches = ' AND '.join(f'{field} IS ?' for field in (*EQUIPMENT_CONFIRM_FIELDS, 'notes'))
        cursor = con.execute("UPDATE equipment SET data_checked=?, data_checked_at=CASE WHEN ? THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') ELSE NULL END, updated_at=CURRENT_TIMESTAMP WHERE id=? AND " + matches,
            [int(value['data_checked']), int(value['data_checked']), item_id] + [row[f] for f in (*EQUIPMENT_CONFIRM_FIELDS, 'notes')])
        if not cursor.rowcount:
            raise ValueError('This item changed. Refresh the inventory before reviewing it.')
        checked=equipment_record(con.execute('SELECT * FROM equipment WHERE id=?', (item_id,)).fetchone())
        operations.audit(con,'equipment',item_id,'source_record_reviewed',{'method':'Compared with source inventory','initials':str(value.get('initials',''))[:40]})
        if value['data_checked']:
            con.execute('INSERT INTO equipment_record_checks (equipment_id,checked_at,snapshot) VALUES (?,?,?)',(item_id,checked['data_checked_at'],json.dumps(checked)))
        return checked


def equipment_record_history(item_id):
    with connect() as con:
        if not con.execute('SELECT 1 FROM equipment WHERE id=?',(item_id,)).fetchone():
            raise LookupError('Inventory item not found.')
        return [dict(id=row['id'],checked_at=row['checked_at'],snapshot=json.loads(row['snapshot']))
            for row in con.execute('SELECT * FROM equipment_record_checks WHERE equipment_id=? ORDER BY id DESC',(item_id,))]


BACKUP_TYPES=('Videohub','ATEM','Satellite receiver','OBS profile','Other')
def av_backups():
    with connect() as con:
        rows=[dict(row) for row in con.execute("SELECT id,equipment_type,device_name,filename,size,notes,created_at,icon_storage_name!='' AS has_icon FROM av_backups ORDER BY created_at DESC,id DESC")]
        details={row['backup_id']:json.loads(row['details']) for row in con.execute('SELECT * FROM backup_details')}
        return [dict(row,recovery=details.get(row['id'],{'state':'untested'})) for row in rows]


def backup_icon(value):
    if value in (None, ''):return None
    if not isinstance(value,dict):raise ValueError('Choose a PNG, JPEG, or WebP icon.')
    mime=value.get('mime_type')
    if mime not in BACKUP_ICON_TYPES:raise ValueError('Choose a PNG, JPEG, or WebP icon.')
    try:content=base64.b64decode(value.get('content',''),validate=True)
    except (ValueError,binascii.Error):raise ValueError('The backup icon could not be read.') from None
    if not content or len(content)>BACKUP_ICON_MAX_BYTES:raise ValueError('Choose an icon between 1 byte and 1 MB.')
    extension,valid=BACKUP_ICON_TYPES[mime]
    if not valid(content):raise ValueError('The backup icon does not match its image format.')
    return mime,extension,content


def save_av_backup(value):
    if not isinstance(value,dict):raise ValueError('Provide the backup file and its details.')
    kind,name,filename,notes=(value.get(key) for key in ('equipment_type','device_name','filename','notes'))
    if kind not in BACKUP_TYPES:raise ValueError('Choose a valid equipment type.')
    if not isinstance(name,str) or not name.strip() or len(name.strip())>120:raise ValueError('Enter a device name up to 120 characters.')
    if not isinstance(filename,str) or not filename.strip() or len(filename)>180 or filename!=Path(filename).name or any(char in filename for char in '\r\n"\\'):raise ValueError('Choose a valid backup filename.')
    if not isinstance(notes,str) or len(notes.strip())>2000:raise ValueError('Notes must be up to 2,000 characters.')
    try:content=base64.b64decode(value.get('content',''),validate=True)
    except (ValueError,binascii.Error):raise ValueError('The backup file could not be read.') from None
    if not content or len(content)>BACKUP_MAX_BYTES:raise ValueError('Choose a backup file between 1 byte and 25 MB.')
    icon=backup_icon(value.get('icon'))
    destinations=[]
    try:
        with connect() as con:
            backup_id=con.execute("INSERT INTO av_backups (equipment_type,device_name,filename,content,size,notes,storage_name) VALUES (?,?,?,?,?,?,?)",(kind,name.strip(),filename,b'',len(content),notes.strip(),'')).lastrowid
            storage_name=backup_storage_name(backup_id,filename);destinations.append(write_stored_backup(storage_name,content))
            icon_name=icon_mime=''
            if icon:
                icon_mime,extension,icon_content=icon
                icon_name=f'{backup_id}-icon{extension}'
                destinations.append(write_stored_backup(icon_name,icon_content))
            con.execute('UPDATE av_backups SET storage_name=?,icon_storage_name=?,icon_mime=? WHERE id=?',(storage_name,icon_name,icon_mime,backup_id))
            return dict(con.execute("SELECT id,equipment_type,device_name,filename,size,notes,created_at,icon_storage_name!='' AS has_icon FROM av_backups WHERE id=?",(backup_id,)).fetchone())
    except Exception:
        for destination in destinations:destination.unlink(missing_ok=True)
        raise


def av_backup_file(backup_id):
    with connect() as con:
        row=con.execute('SELECT filename,content,storage_name FROM av_backups WHERE id=?',(backup_id,)).fetchone()
        if row is None:raise LookupError('Backup file not found.')
        if row['storage_name']:
            path=stored_backup_path(row['storage_name'])
            if not path.is_file():raise LookupError('The saved backup file is missing from the backup folder.')
            return row['filename'],path.read_bytes()
        return row['filename'],row['content']


def av_backup_icon(backup_id):
    with connect() as con:
        row=con.execute('SELECT icon_storage_name,icon_mime FROM av_backups WHERE id=?',(backup_id,)).fetchone()
        if row is None or not row['icon_storage_name']:raise LookupError('Backup icon not found.')
        path=stored_backup_path(row['icon_storage_name'])
        if not path.is_file():raise LookupError('The saved backup icon is missing from the backup folder.')
        return row['icon_mime'],path.read_bytes()


def delete_av_backup(backup_id):
    with connect() as con:
        row=con.execute('SELECT storage_name,icon_storage_name FROM av_backups WHERE id=?',(backup_id,)).fetchone()
        if row is None:raise LookupError('Backup file not found.')
        con.execute('DELETE FROM av_backups WHERE id=?',(backup_id,))
    if row['storage_name']:stored_backup_path(row['storage_name']).unlink(missing_ok=True)
    if row['icon_storage_name']:stored_backup_path(row['icon_storage_name']).unlink(missing_ok=True)
    return {'deleted':backup_id}


def folder_open_command():
    folder=str(backup_directory().resolve())
    if sys.platform=='darwin' and shutil.which('open'):return ['open',folder]
    if os.name=='nt':return ['explorer',folder]
    if shutil.which('xdg-open'):return ['xdg-open',folder]
    return None


def set_equipment_stock_check(item_id, value):
    if not isinstance(value, dict) or any(field not in value for field in EQUIPMENT_CONFIRM_FIELDS):
        raise ValueError('Provide the current stock details being checked.')
    row = validate_equipment(value)
    inventory_id = equipment_inventory_id(value.get('inventory_id', 1))
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        profile = equipment_inventory_details(con, inventory_id).get('layout', {})
        if not profile.get('stock_check_history',profile.get('template')=='tv' or profile.get('stock_mode')=='tv_counts'):
            raise ValueError('Enable stock-check history in this inventory setup first.')
        current = con.execute('SELECT * FROM equipment WHERE id=? AND inventory_id=?', (item_id, inventory_id)).fetchone()
        if current is None:
            raise LookupError('Inventory item not found.')
        if any(row[field] != current[field] for field in EQUIPMENT_CONFIRM_FIELDS) or custom_values(value.get('custom_values'), profile) != json.loads(current['custom_values']):
            raise ValueError('Stock changed. Refresh and check the current counts before confirming.')
        con.execute("UPDATE equipment SET last_checked_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at=CURRENT_TIMESTAMP WHERE id=? AND inventory_id=?", (item_id, inventory_id))
        checked=equipment_record(con.execute('SELECT * FROM equipment WHERE id=?', (item_id,)).fetchone())
        con.execute('INSERT INTO equipment_stock_checks (equipment_id,checked_at,snapshot) VALUES (?,?,?)',
            (item_id,checked['last_checked_at'],json.dumps(checked)))
        operations.audit(con,'equipment',item_id,'physical_count_checked',{'method':'Manual physical stock count','initials':str(value.get('initials',''))[:40]})
        return checked


def equipment_stock_history(item_id):
    with connect() as con:
        if not con.execute('SELECT 1 FROM equipment WHERE id=?',(item_id,)).fetchone():
            raise LookupError('Inventory item not found.')
        return [dict(id=row['id'],checked_at=row['checked_at'],snapshot=json.loads(row['snapshot']))
            for row in con.execute('SELECT * FROM equipment_stock_checks WHERE equipment_id=? ORDER BY id DESC',(item_id,))]


def equipment_import_confirmation(value):
    status = value.get('item_confirmed', 0)
    if status is None or status == '':
        return 0
    if type(status) in (bool, int) and status in (0, 1):
        return int(status)
    if isinstance(status, str) and status.strip().lower() in ('0', '1', 'true', 'false', 'located', 'not located', 'found', 'to find', 'to be found', 'pending'):
        return int(status.strip().lower() in ('1', 'true', 'located', 'found'))
    raise ValueError('Status must be Located or To be found.')

def manage_equipment_location(payload):
    if not isinstance(payload, dict):
        raise ValueError('Choose a location action.')
    inventory_id = equipment_inventory_id(payload.get('inventory_id', 1))
    action = payload.get('action')
    source = payload.get('source')
    target = payload.get('target', '')
    if action not in ('delete', 'merge') or not isinstance(source, str) or not source.strip():
        raise ValueError('Choose a location and Delete or Merge.')
    if not isinstance(target, str) or len(target) > 120:
        raise ValueError('Choose a valid destination location.')
    if action == 'delete':
        target = ''
    elif not target.strip() or target == source:
        raise ValueError('Choose a different destination location.')
    with connect() as con:
        equipment_inventory_details(con, inventory_id)
        if not con.execute('SELECT 1 FROM equipment WHERE inventory_id=? AND location=?', (inventory_id, source)).fetchone():
            raise LookupError('Location no longer exists. Refresh and try again.')
        if action == 'merge' and not con.execute('SELECT 1 FROM equipment WHERE inventory_id=? AND location=?', (inventory_id, target)).fetchone():
            raise LookupError('Destination location no longer exists.')
        sources = [dict(row) for row in con.execute('SELECT * FROM equipment WHERE inventory_id=? AND location=?', (inventory_id, source))]
        count = len(sources)
        for row in sources:
            row['location'] = target
            identity = equipment_identity(row)
            matching = None
            if action == 'merge' and identity is not None and identity[0] == 'stock' and row['custom_values']=='{}':
                matching = con.execute("SELECT * FROM equipment WHERE inventory_id=? AND id!=? AND serial_number='' AND brand=? COLLATE NOCASE AND model=? COLLATE NOCASE AND description=? AND notes=? AND location=? COLLATE NOCASE AND custom_values='{}'", (inventory_id, row['id'], row['brand'], row['model'], row['description'], row['notes'], target)).fetchone()
            if matching:
                # Unknown quantities remain unknown rather than implying a complete count.
                quantity = None if row['quantity'] is None or matching['quantity'] is None else row['quantity'] + matching['quantity']
                if quantity is not None and quantity > 1000000:
                    raise ValueError('Combined stock quantity exceeds 1,000,000. Nothing was changed.')
                notes = '\n'.join(dict.fromkeys(note for note in (matching['notes'], row['notes']) if note))
                con.execute('DELETE FROM equipment WHERE id=?', (row['id'],))
                con.execute('UPDATE equipment SET data_checked=0, data_checked_at=NULL, item_confirmed=0, location=?, quantity=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (target, quantity, notes, matching['id']))
            else:
                con.execute('UPDATE equipment SET data_checked=0, data_checked_at=NULL, item_confirmed=0, location=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (target, row['id']))
    return {'updated': count}


def equipment_identity(row):
    if row['serial_number']:
        return ('serial', serial_key(row['serial_number']))
    if all(row[f] for f in ('brand', 'model', 'location')):
        values=row.get('custom_values') or {}
        if isinstance(values,str):values=json.loads(values)
        return ('stock', row['brand'].casefold(), row['model'].casefold(), row['description'], row['location'].casefold(), row.get('notes','').strip(), json.dumps({key:value for key,value in values.items() if value},sort_keys=True))
    return None


def import_equipment(payload, connection=None):
    if not isinstance(payload, dict) or payload.get('version') != 1 or not isinstance(payload.get('equipment'), list):
        raise ValueError('Choose an avtrack equipment JSON export.')
    if len(payload['equipment']) > 10000:
        raise ValueError('Import supports up to 10,000 inventory items.')
    inventory_id = equipment_inventory_id(payload.get('inventory_id', 1))
    with (nullcontext(connection) if connection is not None else connect()) as con:
        profile = equipment_inventory_details(con,inventory_id).get('layout',DEFAULT_PROFILE)
    rows = []
    for index, value in enumerate(payload['equipment'], 1):
        if blank_import_row(value, EQUIPMENT_FIELDS) and not (isinstance(value,dict) and value.get('custom_values')):
            continue
        try:
            rows.append(normalize_template_row(dict(validate_equipment(value), item_confirmed=equipment_import_confirmation(value),custom_values=custom_values(value.get('custom_values'),profile)),profile))
        except ValueError as exc:
            raise ValueError(f'Inventory row {index}: {exc} Nothing was imported.') from None
    zero_count=sum(profile.get('stock_mode')=='tv_counts' and row['quantity']==0 for row in rows)
    rows=[row for row in rows if not (profile.get('stock_mode')=='tv_counts' and row['quantity']==0)]
    custom_ids = [identity for row in rows if (identity := profile_identifier(row,profile)) is not None]
    if len(custom_ids)!=len(set(custom_ids)):
        raise ValueError('Repeated item identifiers in this file. Nothing was imported.')
    locations=[row['location'].strip().casefold() for row in rows if row['location']]
    if profile.get('unique_location') and len(locations)!=len(set(locations)):
        raise ValueError('Repeated Scala locations in this file. Each location must be unique. Nothing was imported.')
    identities = [identity for row in rows if not profile_identifier(row,profile) and (identity := equipment_identity(row)) is not None]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate serial numbers or stock records in this file. Nothing was imported.')
    with (nullcontext(connection) if connection is not None else connect()) as con:
        if connection is None:con.execute('BEGIN IMMEDIATE')
        if equipment_inventory_details(con, inventory_id).get('layout',DEFAULT_PROFILE) != profile:
            raise ValueError('Inventory columns changed. Refresh and try importing again.')
        existing = {identity for row in con.execute('SELECT * FROM equipment WHERE inventory_id=?', (inventory_id,)) if (identity := equipment_identity(dict(row))) is not None}
        existing_custom = {profile_identifier(equipment_record(saved),profile) for saved in con.execute('SELECT * FROM equipment WHERE inventory_id=?',(inventory_id,))}
        unique_locations = bool(profile.get('unique_location'))
        existing_locations = {saved['location'].strip().casefold() for saved in con.execute('SELECT location FROM equipment WHERE inventory_id=?',(inventory_id,)) if saved['location']} if unique_locations else set()
        added = 0
        for row in rows:
            custom_id = profile_identifier(row,profile)
            if custom_id and custom_id in existing_custom: continue
            location_key=row['location'].strip().casefold()
            if unique_locations and location_key and location_key in existing_locations: continue
            identity = None if custom_id else equipment_identity(row)
            if identity is not None and identity in existing:
                continue
            fields = EQUIPMENT_FIELDS + ('item_confirmed',)
            con.execute('INSERT INTO equipment (' + ','.join(fields) + ',inventory_id,custom_values) VALUES (?,?,?,?,?,?,?,?,?,?)', [row[f] for f in fields] + [inventory_id,json.dumps(row['custom_values'],sort_keys=True)])
            item_id = con.execute('SELECT last_insert_rowid()').fetchone()[0]
            con.execute('UPDATE equipment SET custom_values=? WHERE id=?',(json.dumps(row['custom_values'],sort_keys=True),item_id))
            added += 1
            if custom_id: existing_custom.add(custom_id)
            if unique_locations and location_key: existing_locations.add(location_key)
            if identity is not None:
                existing.add(identity)
    result={'added': added, 'skipped': len(rows)-added+zero_count}
    if zero_count:result['skipped_zero']=zero_count
    return result


def equipment_csv(rows=None, layout=None):
    output = io.StringIO(newline='')
    fields = ('description', 'brand', 'model', 'serial_number', 'quantity', 'location', 'item_confirmed', 'notes')
    if layout:
        layout=with_unit_status(layout)
        columns = [(col['label'],col['key']) for col in layout['columns']]
        if layout.get('show_status', True) or layout.get('stock_check_history', layout.get('template') == 'tv' or layout.get('stock_mode') == 'tv_counts'): columns.append(('Last checked (UTC)','last_checked_at'))
        writer=csv.writer(output)
        writer.writerow([label for label,key in columns]+(['Location check'] if layout.get('show_status',True) else []))
        for row in equipment_inventory() if rows is None else rows:
            values=[(row.get('inventory_checked_at') or row.get(key) or '') if key=='last_checked_at' else column_value(row,key) for label,key in columns]+([('IP confirmed' if row.get('item_confirmed') else 'Confirm IP') if layout.get('confirmation_mode')=='ip' else ('Located' if row.get('item_confirmed') else 'To be found')] if layout.get('show_status',True) else [])
            writer.writerow(["'"+str(v) if str(v).startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else v for v in values])
        return output.getvalue().encode('utf-8-sig')
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in equipment_inventory() if rows is None else rows:
        writer.writerow({f: ("'"+str(row[f]) if str(row[f]).startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else row[f]) for f in fields})
    return output.getvalue().encode('utf-8-sig')


def network_csv(rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=ALL_FIELDS, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow({f: ("'" + str(row[f]) if str(row[f]).startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else row[f]) for f in ALL_FIELDS})
    return output.getvalue().encode('utf-8-sig')


def selected_export_rows(rows, payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('ids'), list):
        raise ValueError('Choose the records to export using an IDs list.')
    ids = payload['ids']
    if len(ids) > 100000 or any(type(value) is not int or value < 1 for value in ids):
        raise ValueError('Export IDs must be positive whole numbers; choose up to 100,000 records.')
    by_id = {row['id']: row for row in rows}
    # Preserve the displayed order, ignore deleted records, and include each ID once.
    return [by_id[value] for value in dict.fromkeys(ids) if value in by_id]


class Handler(BaseHTTPRequestHandler):
    def can_launch_desktop_app(self):
        forwarded_host=self.headers.get('Host','').split(':',1)[0].lower().rstrip('.')
        remote=self.client_address[0]
        return remote in ('127.0.0.1','::1') and os.environ.get('CODESPACES','').lower()!='true' and not forwarded_host.endswith('.app.github.dev')

    def can_open_backup_folder(self):
        return self.can_launch_desktop_app() and folder_open_command() is not None

    def send(self, status, data, content_type='application/json; charset=utf-8', filename=None):
        body = json.dumps(data).encode() if content_type.startswith('application/json') and not isinstance(data, bytes) else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        # Codespaces' private-port proxy renews browser authentication at this endpoint.
        # Permit only that connection in Codespaces; ordinary deployments stay same-origin.
        connect_sources = "'self'"
        forwarded_host = self.headers.get('Host', '').split(':', 1)[0].lower().rstrip('.')
        if os.environ.get('CODESPACES', '').lower() == 'true' or forwarded_host.endswith('.app.github.dev'):
            connect_sources += ' https://github.dev/pf-signin'
        self.send_header('Content-Security-Policy', f"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src {connect_sources}; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The browser may abandon a timed-out import while the server is
            # finishing it. The transaction result remains durable and a retry
            # is idempotent; there is no response socket left to write to.
            return

    def body(self):
        # Reject cross-origin writes, including simple requests from other websites.
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            raise PermissionError('Cross-origin writes are not allowed.')
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise ValueError('Use application/json.')
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise ValueError('Invalid request size.') from None
        maximum=35_000_000 if urlsplit(self.path).path=='/api/backups' else 8_000_000
        if size < 1 or size > maximum:
            raise ValueError(f'Request must be between 1 byte and {maximum // 1_000_000} MB.')
        return json.loads(self.rfile.read(size))

    def dispatch(self):
        path = urlsplit(self.path).path
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        if operations.dispatch(self, sys.modules[__name__]):return
        if self.command=='GET' and path=='/api/workspace/recovery':
            directory=DB_PATH.parent/'recovery'
            name=query.get('file',[''])[0]
            if name:
                if not re.fullmatch(r'avtrack-recovery-[a-zA-Z0-9-]+\.zip',name):raise ValueError('Choose a saved recovery backup.')
                saved=directory/name
                if not saved.is_file():raise LookupError('Recovery backup not found.')
                return self.send(200,saved.read_bytes(),'application/zip',name)
            return self.send(200,{'backups':[{'name':saved.name,'size':saved.stat().st_size} for saved in sorted(directory.glob('avtrack-recovery-*.zip'),reverse=True)]})
        if self.command == 'GET' and path == '/api/workspace/export':
            data = workspace_transfer.snapshot(connect, backup_directory)
            data['app_version']=source_revision()
            content, mime, filename = workspace_transfer.pack(data, query.get('format', ['zip'])[0])
            return self.send(200, content, mime, filename)
        if self.command == 'POST' and path in ('/api/workspace/restore','/api/workspace/preview'):
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                raise PermissionError('Cross-origin writes are not allowed.')
            if path.endswith('/restore') and self.headers.get('X-AVTrack-Restore') != 'replace-all':
                raise ValueError('Confirm that this backup will replace all workspaces.')
            try:
                size = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                raise ValueError('Invalid request size.') from None
            if not 0 < size <= workspace_transfer.MAX_BYTES:
                raise ValueError('Choose a complete backup smaller than 200 MB.')
            data = workspace_transfer.unpack(self.rfile.read(size))
            if path.endswith('/preview'):
                return self.send(200, workspace_transfer.preview(data,connect))
            # Validate and migrate before writing even a recovery file.
            workspace_transfer.preview(data,connect)
            recovery=workspace_transfer.save_recovery(connect,backup_directory,DB_PATH.parent / 'recovery',version=source_revision())
            result=workspace_transfer.restore(data, connect, backup_directory)
            result['recovery_backup']=recovery.name
            return self.send(200,result)
        if path.startswith('/api/import-sessions'):
            with connect() as con:
                if path=='/api/import-sessions' and self.command=='GET':
                    target=query.get('target',[None])[0]
                    where,parameters=[],[]
                    if target:where.append('target=?');parameters.append(import_sessions.target_name(target))
                    before=query.get('before',[''])[0]
                    if before:
                        if not before.isascii() or not before.isdigit() or int(before)<1:raise ValueError('Choose a valid import history page.')
                        where.append('id<?');parameters.append(int(before))
                    rows=con.execute("SELECT id,target,name,status,retired,updated_at,COALESCE(json_extract(state,'$.inventory.name'),CASE target WHEN 'device' THEN 'Devices' WHEN 'iptv' THEN 'IPTV Channels' ELSE 'Inventory' END) AS destination FROM import_sessions "+('WHERE '+' AND '.join(where)+' ' if where else '')+'ORDER BY id DESC LIMIT 50',parameters).fetchall()
                    return self.send(200,{'sessions':[dict(r) for r in rows]})
                if path=='/api/import-sessions' and self.command=='POST':
                    value=self.body()
                    if isinstance(value,dict) and str(value.get('target','')).startswith('equipment:'):
                        equipment_inventory_details(con,int(value['target'].split(':')[1]))
                    saved=import_sessions.save(con,value);con.commit()
                    return self.send(201,saved)
                match=re.fullmatch(r'/api/import-sessions/([1-9][0-9]*)(/rows|/reconciliation)?',path)
                if match:
                    session_id=int(match[1])
                    if self.command=='GET' and not match[2]:
                        saved=import_sessions.get(con,session_id)
                        return self.send(200,dict(saved,**import_autosave.status(sys.modules[__name__],session_id)))
                    if self.command=='PUT' and not match[2]:
                        saved=import_sessions.save(con,self.body(),session_id);con.commit()
                        recovery=import_autosave.checkpoint(sys.modules[__name__],session_id,final=saved['status'] in ('complete','paused'))
                        return self.send(200,dict(saved,**recovery))
                    if self.command=='POST' and match[2]=='/rows':
                        value=self.body()
                        if not isinstance(value,dict):raise ValueError('Provide a source row.')
                        con.execute('BEGIN IMMEDIATE')
                        def apply(session,row):
                            return operations.apply_import(sys.modules[__name__],con,session,row)
                        result=import_sessions.save_receipt(con,session_id,value,apply);con.commit()
                        recovery=import_autosave.checkpoint(sys.modules[__name__],session_id)
                        return self.send(200,dict(result,**recovery))
                    if self.command=='PUT' and match[2]=='/reconciliation':
                        value=self.body()
                        if import_sessions.get(con,session_id)['retired']:raise ValueError('This inventory was deleted. Its import report is read-only.')
                        con.execute('UPDATE import_sessions SET reconciliation=? WHERE id=?',(json.dumps(value),session_id))
                        con.commit()
                        return self.send(200,{'saved':True})
            raise LookupError('Import session endpoint not found.')
        if path=='/api/import-preferences' and self.command in ('GET','PUT'):
            with connect() as con:
                if self.command=='GET':
                    target=import_sessions.target_name(query.get('target',[''])[0]);row=con.execute('SELECT settings FROM import_preferences WHERE target=?',(target,)).fetchone()
                    return self.send(200,json.loads(row['settings']) if row else {})
                value=self.body()
                if not isinstance(value,dict):raise ValueError('Provide valid import preferences.')
                target=import_sessions.target_name(value.get('target'))
                settings=value.get('settings')
                if not isinstance(settings,dict) or len(json.dumps(settings))>100000:raise ValueError('Provide valid import preferences.')
                con.execute('INSERT INTO import_preferences (target,settings) VALUES (?,?) ON CONFLICT(target) DO UPDATE SET settings=excluded.settings',(target,json.dumps(settings)))
                con.commit()
                return self.send(200,{'saved':True})
        if self.command == 'GET' and path in ('/equipment', '/inventory/'):
            self.send_response(308)
            self.send_header('Location', '/inventory')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if self.command == 'POST' and path == '/api/demo/export.pdf':
            value=self.body()
            if not isinstance(value,dict) or not isinstance(value.get('title'),str) or not value['title'].strip():
                raise ValueError('Choose a demo table to export.')
            labels=value.get('columns');rows=value.get('rows')
            if not isinstance(labels,list) or not 1<=len(labels)<=12 or any(not isinstance(label,str) or not label.strip() or len(label)>120 for label in labels):
                raise ValueError('Choose between 1 and 12 named demo columns.')
            if not isinstance(rows,list) or len(rows)>1000 or any(not isinstance(row,list) or len(row)!=len(labels) for row in rows):
                raise ValueError('Provide demo rows matching the selected columns.')
            cleaned=[]
            for row in rows:
                if any(isinstance(cell,(dict,list)) or len(str(cell if cell is not None else ''))>2000 for cell in row):
                    raise ValueError('Demo PDF cells must contain short text values.')
                cleaned.append(['' if cell is None else str(cell) for cell in row])
            slug=re.sub(r'[^a-z0-9]+','-',value['title'].lower()).strip('-') or 'demo'
            return self.send(200,demo_pdf(value['title'].strip(),[label.strip() for label in labels],cleaned),'application/pdf',f'avtrack-demo-{slug}.pdf')
        exports = {
            '/api/export': (lambda rows: {'version':1, 'devices':rows}, inventory, 'application/json; charset=utf-8', 'avtrack-network.json'),
            '/api/export.csv': (network_csv, inventory, 'text/csv; charset=utf-8', 'avtrack-network.csv'),
            '/api/export.xlsx': (network_xlsx, inventory, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'avtrack-network.xlsx'),
            '/api/export.pdf': (network_pdf, inventory, 'application/pdf', 'avtrack-network.pdf'),
            '/api/equipment/export': (lambda rows: {'version':1, 'equipment':rows}, equipment_inventory, 'application/json; charset=utf-8', 'avtrack-equipment.json'),
            '/api/equipment/export.csv': (equipment_csv, equipment_inventory, 'text/csv; charset=utf-8', 'avtrack-equipment.csv'),
            '/api/equipment/export.xlsx': (equipment_xlsx, equipment_inventory, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'avtrack-equipment.xlsx'),
            '/api/equipment/export.pdf': (equipment_pdf, equipment_inventory, 'application/pdf', 'avtrack-equipment.pdf'),
        }
        if self.command in ('GET', 'POST') and path in exports:
            payload = self.body() if self.command == 'POST' else None
            generate, read, mime, filename = exports[path]
            equipment_export = path.startswith('/api/equipment/')
            named_inventory = None
            if equipment_export:
                inventory_id = equipment_inventory_id(payload.get('inventory_id', 1) if isinstance(payload, dict) else query.get('inventory_id', [1])[0])
                with connect() as con:
                    named_inventory = equipment_inventory_details(con, inventory_id)
                rows = read(inventory_id)
            else:
                rows = read()
            record_type = None
            if self.command == 'GET' and path.startswith('/api/export'):
                if 'record_type' in query:
                    record_type = query['record_type'][0]
                    if record_type not in ('device', 'iptv'):
                        raise ValueError('Choose devices or IPTV channels for this export.')
                    rows = [row for row in rows if row['record_type'] == record_type]
            if self.command == 'POST':
                if path.startswith('/api/export') and isinstance(payload, dict) and 'record_type' in payload:
                    record_type = payload['record_type']
                    if record_type not in ('device', 'iptv'):
                        raise ValueError('Choose devices or IPTV channels for this export.')
                    rows = [row for row in rows if row['record_type'] == record_type]
                    if 'ids' in payload:
                        rows = selected_export_rows(rows, payload)
                else:
                    rows = selected_export_rows(rows, payload)
            if record_type:
                suffix = filename.rsplit('.', 1)[1]
                filename = f'avtrack-{"av-devices" if record_type == "device" else "iptv-channels"}.{suffix}'
            if record_type and generate in (network_pdf, network_xlsx):
                return self.send(200, generate(rows, record_type=record_type), mime, filename)
            if named_inventory:
                suffix = filename.rsplit('.', 1)[1]
                slug = re.sub(r'[^a-z0-9]+', '-', named_inventory['name'].lower()).strip('-') or 'equipment'
                if named_inventory['id'] != 1 or named_inventory['name'] != 'Equipment inventory':
                    filename = f'avtrack-{slug}.{suffix}'
                if generate in (equipment_pdf, equipment_xlsx):
                    return self.send(200, generate(rows, inventory_name=named_inventory['name'], layout=named_inventory.get('layout')), mime, filename)
                if path == '/api/equipment/export':
                    return self.send(200, {'version':1, 'inventory_name':named_inventory['name'], 'equipment':rows, **({'layout':named_inventory['layout']} if named_inventory.get('layout') else {})}, mime, filename)
            if named_inventory and path.endswith('.csv'):
                return self.send(200, equipment_csv(rows,layout=named_inventory.get('layout')),mime,filename)
            return self.send(200, generate(rows), mime, filename)
        if self.command == 'GET':
            if path == '/api/overview':
                return self.send(200, workspace_overview())
            if path == '/api/backups':
                folder=backup_directory();folder.mkdir(parents=True,exist_ok=True)
                return self.send(200,{'backups':av_backups(),'folder':{'path':str(folder.resolve()),'can_open':self.can_open_backup_folder()}})
            match=re.fullmatch(r'/api/backups/([1-9][0-9]*)/download',path)
            if match:
                filename,content=av_backup_file(int(match[1]));return self.send(200,content,'application/octet-stream',filename)
            match=re.fullmatch(r'/api/backups/([1-9][0-9]*)/icon',path)
            if match:
                mime,content=av_backup_icon(int(match[1]));return self.send(200,content,mime)
            if path == '/satellite-channels.json':
                return self.send(200, json.loads((ROOT / 'static' / 'satellite-channels.json').read_text()))
            if re.fullmatch(r'/channel-logos/[A-Za-z0-9_-]+\.[a-z]{2}\.png', path):
                logo = ROOT / 'static' / 'channel-logos' / path.rsplit('/', 1)[1]
                if logo.is_file():
                    return self.send(200, logo.read_bytes(), 'image/png')
            if re.fullmatch(r'/api/equipment/[0-9]+/stock-checks',path):
                return self.send(200,{'checks':equipment_stock_history(int(path.split('/')[3]))})
            if re.fullmatch(r'/api/equipment/[0-9]+/record-checks',path):
                return self.send(200,{'checks':equipment_record_history(int(path.split('/')[3]))})
            if path == '/api/equipment':
                return self.send(200, {'equipment': equipment_inventory(equipment_inventory_id(query.get('inventory_id', [1])[0]))})
            if path == '/api/equipment/inventories':
                return self.send(200, {'inventories': equipment_inventories()})
            if path == '/api/devices':
                return self.send(200, {'devices': inventory()})
            assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css'), '/equipment.js': ('equipment.js', 'text/javascript'), '/icon.svg': ('icon.svg', 'image/svg+xml'), '/favicon.svg': ('favicon.svg', 'image/svg+xml'), '/example-switcher.png': ('example-switcher.png', 'image/png'), '/fonts/Poppins-Regular.woff2': ('fonts/Poppins-Regular.woff2', 'font/woff2'), '/fonts/Poppins-Medium.woff2': ('fonts/Poppins-Medium.woff2', 'font/woff2'), '/fonts/Poppins-SemiBold.woff2': ('fonts/Poppins-SemiBold.woff2', 'font/woff2'), '/fonts/Poppins-Bold.woff2': ('fonts/Poppins-Bold.woff2', 'font/woff2')}
            assets['/workspace-examples.png'] = ('workspace-examples.png', 'image/png')
            for workspace in ('device', 'iptv', 'equipment', 'backups'):
                assets[f'/workspace-{workspace}.png'] = (f'workspace-{workspace}.png', 'image/png')
            assets['/inventory-templates.json'] = ('inventory-templates.json', 'application/json')
            assets['/inventory-columns.js'] = ('inventory-columns.js', 'text/javascript')
            assets['/import-review.js'] = ('import-review.js', 'text/javascript')
            assets['/demo'] = ('demo.html', 'text/html')
            assets['/demo/'] = ('demo.html', 'text/html')
            assets['/recover'] = ('recovery.html', 'text/html')
            assets['/recovery.js'] = ('recovery.js', 'text/javascript')
            assets['/paste-workflow.js'] = ('paste-workflow.js', 'text/javascript')
            assets['/import-workflow.js'] = ('import-workflow.js', 'text/javascript')
            assets['/demo.js'] = ('demo.js', 'text/javascript')
            assets['/demo.css'] = ('demo.css', 'text/css')
            assets['/avtrack'] = ('landing.html', 'text/html')
            assets['/avtrack/'] = ('landing.html', 'text/html')
            assets['/landing.css'] = ('landing.css', 'text/css')
            assets['/landing.js'] = ('landing.js', 'text/javascript')
            assets['/inventory'] = ('index.html', 'text/html')
            assets['/backups'] = ('index.html', 'text/html')
            assets['/desktop.js'] = ('desktop.js','text/javascript')
            assets['/workspace-ui.js'] = ('workspace-ui.js','text/javascript')
            assets['/workspace-transfer.js'] = ('workspace-transfer.js', 'text/javascript')
            assets['/backups.js'] = ('backups.js', 'text/javascript')
            assets['/service-worker.js'] = ('service-worker.js', 'text/javascript')
            assets['/broadcastgab-offline'] = ('broadcastgab/index.html', 'text/html')
            assets.update({f'/broadcastgab-assets/{file.name}': (f'broadcastgab/{file.name}',
                           'text/css' if file.suffix == '.css' else 'image/png' if file.suffix == '.png' else 'image/jpeg')
                           for file in (ROOT / 'static' / 'broadcastgab').iterdir() if file.name != 'index.html'})
            assets.update({f'/fonts/{family}-Variable.woff2': (f'fonts/{family}-Variable.woff2', 'font/woff2')
                           for family in ('SpaceGrotesk', 'DMSans', 'JetBrainsMono')})
            if path in assets:
                file, mime = assets[path]
                data=(ROOT / 'static' / file).read_bytes()
                if file=='index.html':
                    version=source_revision().split(' · ', 1)[0]
                    data=data.replace(b'{{AVTRACK_VERSION}}',version.encode('utf-8'))
                if mime=='application/json':data=json.loads(data)
                return self.send(200, data, mime + '; charset=utf-8' if mime.startswith('text/') or mime == 'image/svg+xml' else mime)
        elif self.command == 'POST' and path == '/api/backups/open-folder':
            self.body()
            if not self.can_open_backup_folder():raise PermissionError('The backup folder can only be opened when AVTrack is running locally with a desktop file manager.')
            subprocess.Popen(folder_open_command(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            return self.send(200,{'opened':str(backup_directory().resolve())})
        elif self.command == 'POST' and re.fullmatch(r'/api/iptv/[1-9][0-9]*/open-vlc', path):
            self.body()
            if not self.can_launch_desktop_app():
                raise PermissionError('VLC can only be opened when AVTrack is running locally on this computer.')
            return self.send(200, open_iptv_in_vlc(int(path.split('/')[3])))
        elif self.command == 'POST' and path == '/api/backups':
            return self.send(201,save_av_backup(self.body()))
        elif self.command == 'DELETE' and re.fullmatch(r'/api/backups/[1-9][0-9]*',path):
            self.body();return self.send(200,delete_av_backup(int(path.rsplit('/',1)[1])))
        elif self.command == 'POST' and path == '/api/equipment/inventories':
            return self.send(201, save_equipment_inventory(self.body()))
        elif self.command == 'PUT' and path.startswith('/api/equipment/inventories/'):
            inventory_id = equipment_inventory_id(path.removeprefix('/api/equipment/inventories/'))
            return self.send(200, save_equipment_inventory(self.body(), inventory_id))
        elif self.command == 'DELETE' and path.startswith('/api/equipment/inventories/'):
            inventory_id = equipment_inventory_id(path.removeprefix('/api/equipment/inventories/'))
            value=self.body()
            workspace_transfer.save_recovery(connect,backup_directory,DB_PATH.parent/'recovery',version=source_revision())
            return self.send(200, delete_equipment_inventory(inventory_id,value))
        elif self.command == 'POST' and path == '/api/equipment':
            return self.send(201, save_equipment(self.body()))
        elif self.command == 'POST' and path == '/api/equipment/reconcile':
            payload = self.body()
            if not isinstance(payload, dict):
                raise ValueError('Choose an original inventory file.')
            inventory_id = equipment_inventory_id(payload.get('inventory_id', 1))
            with connect() as con:
                layout = equipment_inventory_details(con,inventory_id).get('layout')
            return self.send(200, reconcile_profile(payload,equipment_inventory(inventory_id),layout) if layout else reconcile(payload, equipment_inventory(inventory_id)))
        elif self.command == 'POST' and path == '/api/equipment/locations':
            return self.send(200, manage_equipment_location(self.body()))
        elif self.command == 'POST' and path == '/api/equipment/import':
            result=import_equipment(self.body())
            recovery=import_autosave.checkpoint(sys.modules[__name__],added=result['added'],final=True)
            return self.send(200,dict(result,**recovery))
        elif self.command == 'POST' and re.fullmatch(r'/api/equipment/[1-9][0-9]*/remove-unit', path):
            return self.send(200, remove_equipment_unit(int(path.split('/')[3]), self.body()))
        elif self.command == 'POST' and path.startswith('/api/equipment/') and path.endswith('/notes'):
            try:
                item_id=int(path.removeprefix('/api/equipment/').removesuffix('/notes'))
            except ValueError:
                raise LookupError('Inventory item not found.') from None
            return self.send(200,set_equipment_notes(item_id,self.body()))
        elif self.command == 'POST' and path.startswith('/api/equipment/') and path.endswith('/stock-check'):
            try:
                item_id = int(path.removeprefix('/api/equipment/').removesuffix('/stock-check'))
            except ValueError:
                raise LookupError('Inventory item not found.') from None
            return self.send(200, set_equipment_stock_check(item_id, self.body()))
        elif self.command == 'POST' and path.startswith('/api/equipment/') and path.endswith('/review'):
            try:
                item_id = int(path.removeprefix('/api/equipment/').removesuffix('/review'))
            except ValueError:
                raise LookupError('Inventory item not found.') from None
            return self.send(200, set_equipment_review(item_id, self.body()))
        elif self.command == 'POST' and path.startswith('/api/equipment/') and path.endswith('/confirm'):
            try:
                item_id = int(path.removeprefix('/api/equipment/').removesuffix('/confirm'))
            except ValueError:
                raise LookupError('Inventory item not found.') from None
            return self.send(200, set_equipment_confirmation(item_id, self.body()))
        elif self.command == 'POST' and path == '/api/devices/batch-delete':
            payload = self.body()
            ids = payload.get('ids') if isinstance(payload, dict) else None
            if not isinstance(ids, list) or not ids or len(ids) > 10000 or any(type(value) is not int or value < 1 for value in ids):
                raise ValueError('Choose between 1 and 10,000 device IDs, using positive whole numbers.')
            workspace_transfer.save_recovery(connect,backup_directory,DB_PATH.parent/'recovery',version=source_revision())
            with connect() as con:
                for record_id in dict.fromkeys(ids):
                    saved=con.execute('SELECT record_type FROM devices WHERE id=?',(record_id,)).fetchone()
                    if saved:operations.audit(con,saved['record_type'],record_id,'deleted',{'reason':'Bulk deletion'})
                deleted = con.executemany('DELETE FROM devices WHERE id=?', ((value,) for value in dict.fromkeys(ids))).rowcount
            return self.send(200, {'deleted': deleted})
        elif self.command in ('PUT','DELETE') and path.startswith('/api/equipment/'):
            try:
                item_id = int(path.removeprefix('/api/equipment/'))
            except ValueError:
                raise LookupError('Inventory item not found.') from None
            if self.command == 'PUT':
                return self.send(200, save_equipment(self.body(), item_id))
            payload = self.body()
            if not isinstance(payload, dict):
                raise ValueError('Choose the inventory item to delete.')
            inventory_id = equipment_inventory_id(payload.get('inventory_id', 1))
            with connect() as con:
                equipment_inventory_details(con, inventory_id)
                saved=con.execute('SELECT * FROM equipment WHERE id=? AND inventory_id=?',(item_id,inventory_id)).fetchone()
                if saved:operations.audit(con,'equipment',item_id,'stock_record_deleted',{'serial':saved['serial_number'],'description':saved['description'],'quantity_before':saved['quantity'],'quantity_after':0,'reason':str(payload.get('reason',''))[:1000],'initials':str(payload.get('initials',''))[:40]})
                if not con.execute('DELETE FROM equipment WHERE id=? AND inventory_id=?', (item_id, inventory_id)).rowcount:
                    raise LookupError('Inventory item not found.')
            return self.send(200, {'deleted':item_id})
        elif self.command == 'POST' and path == '/api/devices/rename-venue':
            return self.send(200, rename_device_venue(self.body()))
        elif self.command == 'POST' and path == '/api/devices':
            return self.send(201, save_device(self.body()))
        elif self.command == 'POST' and path == '/api/spreadsheet-preview':
            return self.send(200, spreadsheet_preview(self.body()))
        elif self.command == 'POST' and path == '/api/import':
            return self.send(200, import_devices(self.body()))
        elif self.command == 'POST' and path.startswith('/api/devices/') and path.endswith('/notes'):
            try:
                device_id = int(path.removeprefix('/api/devices/').removesuffix('/notes'))
            except ValueError:
                raise LookupError('Device not found.') from None
            return self.send(200, set_device_notes(device_id, self.body()))
        elif self.command == 'POST' and path.startswith('/api/devices/') and path.endswith('/system'):
            try:
                device_id = int(path.removeprefix('/api/devices/').removesuffix('/system'))
            except ValueError:
                raise LookupError('Device not found.') from None
            return self.send(200, set_device_system(device_id, self.body()))
        elif self.command == 'POST' and path.startswith('/api/devices/') and path.endswith('/confirm'):
            try:
                device_id = int(path.removeprefix('/api/devices/').removesuffix('/confirm'))
            except ValueError:
                raise LookupError('Device not found.') from None
            return self.send(200, confirm_ip(device_id, self.body()))
        elif self.command in ('PUT', 'DELETE') and path.startswith('/api/devices/'):
            try:
                device_id = int(path.removeprefix('/api/devices/'))
            except ValueError:
                raise LookupError('Device not found.') from None
            if self.command == 'PUT':
                return self.send(200, save_device(self.body(), device_id))
            self.body()
            with connect() as con:
                if con.execute('DELETE FROM devices WHERE id=?', (device_id,)).rowcount == 0:
                    raise LookupError('Device not found.')
            return self.send(200, {'deleted': device_id})
        self.send(404, {'error': 'Not found.'})

    def handle_request(self):
        try:
            self.dispatch()
        except PermissionError as exc:
            self.send(403, {'error': str(exc)})
        except (ValueError, json.JSONDecodeError) as exc:
            self.send(400, {'error': str(exc)})
        except LookupError as exc:
            self.send(404, {'error': str(exc)})
        except sqlite3.IntegrityError as exc:
            if 'equipment_inventories.name' in str(exc):
                message = 'An inventory with this name already exists.'
            elif 'Duplicate AV IP' in str(exc):
                message = 'This IP address already exists in Devices. Each device IP must be unique, even across VLANs.'
            else:
                message = 'This assignment, serial number, or stock record already exists in the inventory.'
            self.send(409, {'error': message})
        except Exception:
            self.log_error('Internal request error')
            self.send(500, {'error': 'Could not complete the request. Check server storage and try again.'})

    do_GET = do_POST = do_PUT = do_DELETE = handle_request


if __name__ == '__main__':
    with connect():
        pass
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8000'))
    print(f'AVTrack listening on {host}:{port}', flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
