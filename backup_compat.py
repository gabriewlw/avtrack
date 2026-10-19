"""Retained full-backup contracts and explicit, data-only schema migrations.

Application releases and backup schemas have independent version numbers. Never
rewrite an old contract or remove a migration: historical files must keep working.
"""
import copy
import json
from functools import lru_cache
from pathlib import Path

FORMAT_VERSION = 1
CURRENT_SCHEMA_VERSION = 2
SCHEMA_DIRECTORY = Path(__file__).resolve().parent / 'backup_schemas'


@lru_cache(maxsize=None)
def contract(version):
    return json.loads((SCHEMA_DIRECTORY / f'v{version}.json').read_text())


def assert_database_contract(con, columns):
    expected = contract(CURRENT_SCHEMA_VERSION)
    definitions = {name: [list(row)[1:] for row in con.execute(f'PRAGMA table_info("{name}")')]
                   for name in columns}
    definitions = {name: {row[0]: row[1:] for row in rows} for name, rows in definitions.items()}
    expected_definitions = {name: {row[0]: row[1:] for row in rows}
                            for name, rows in expected['definitions'].items()}
    if not same_columns(columns, expected['columns']) or definitions != expected_definitions:
        raise ValueError('The application database changed without a backup migration. '
                         'Install a release with the complete backup compatibility update.')


def same_columns(actual, expected):
    """Physical SQLite column order can differ after an in-place upgrade."""
    return (isinstance(actual, dict) and set(actual) == set(expected)
            and all(isinstance(fields, list)
                    and all(isinstance(field, str) for field in fields)
                    and len(fields) == len(set(fields))
                    and set(fields) == set(expected[name])
                    for name, fields in actual.items()))


def validate_shape(data, version):
    expected = contract(version)['columns']
    if not same_columns(data.get('columns'), expected):
        raise ValueError('The backup layout does not match its supported schema. '
                         'No records were replaced; keep the original backup.')
    tables = data.get('tables')
    if not isinstance(tables, dict) or set(tables) != set(expected):
        raise ValueError('The backup is missing workspace tables or contains unsupported data.')
    for name, rows in tables.items():
        if not isinstance(rows, list) or any(not isinstance(row, dict) or set(row) != set(expected[name]) for row in rows):
            raise ValueError('The backup contains incomplete records.')


def source_version(data):
    if not isinstance(data, dict) or data.get('format') != 'avtrack-workspace':
        raise ValueError('Choose an AVTrack complete ZIP or JSON backup.')
    version = data.get('version')
    if type(version) is not int or version < 1:
        raise ValueError('The backup format version is invalid.')
    if version != FORMAT_VERSION:
        raise ValueError('This backup uses an unsupported format. Update AVTrack to import it; '
                         'your current data has not been replaced.')
    if 'schema_version' in data:
        version = data['schema_version']
        if type(version) is not int or version < 1:
            raise ValueError('The backup schema version is invalid.')
        if version > CURRENT_SCHEMA_VERSION:
            raise ValueError('This backup was created with a newer data schema. Update AVTrack '
                             'to import it; your current data has not been replaced.')
        validate_shape(data, version)
        return version
    # v0.0.186–188 did not include schema_version. Identify their frozen layouts,
    # never infer missing fields from whichever database happens to be installed.
    for version in (1, 2):
        if same_columns(data.get('columns'), contract(version)['columns']):
            validate_shape(data, version)
            return version
    raise ValueError('This legacy backup layout is not recognized. Update AVTrack or '
                     'export a new backup from its original version; current data was kept.')


def migrate_1_to_2(data):
    for name in ('record_audit', 'backup_details'):
        data['columns'][name] = copy.deepcopy(contract(2)['columns'][name])
        data['tables'][name] = []


# Each function upgrades exactly one version and mutates only a private copy.
# Schema 3 adds MIGRATIONS[2], schema 4 adds MIGRATIONS[3], and so on.
MIGRATIONS = {1: migrate_1_to_2}


def upgrade(data):
    original = source_version(data)
    result = copy.deepcopy(data)
    result.pop('integrity', None)  # Original bytes were checked before migration.
    for version in range(original, CURRENT_SCHEMA_VERSION):
        migration = MIGRATIONS.get(version)
        if migration is None:
            raise ValueError('This AVTrack release is missing a required backup migration. '
                             'Install a complete release; your data has not been replaced.')
        migration(result)
        result['schema_version'] = version + 1
        validate_shape(result, version + 1)
    result['schema_version'] = CURRENT_SCHEMA_VERSION
    return result, {'source_schema_version': original,
                    'schema_version': CURRENT_SCHEMA_VERSION,
                    'migration_required': original != CURRENT_SCHEMA_VERSION}
