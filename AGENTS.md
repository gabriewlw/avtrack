# Full-backup compatibility

Every release must keep importing all supported historical complete ZIP/JSON
backups. Application version numbers are independent of backup schema versions.

When changing database tables, columns, types, defaults, constraints, or the meaning
of stored fields:

1. Read `docs/backup-compatibility.md` and `backup_compat.py`.
2. Keep existing `backup_schemas/v*.json`, historical fixtures, and migration steps
   unchanged. Add a new schema contract and an explicit next-version migration
   where the stored data changes. Do not guess replacements or drop unknown data.
3. Add a complete synthetic backup fixture for the new schema. Test old-to-current
   migration, round-trip preservation, and rollback on rejection.
4. Run the complete backend suite, including `test_backup_compatibility`, before
   committing. Do not bypass compatibility checks to make a release pass.

Only local application code performs migrations; never execute SQL or code from an
imported backup. Unknown newer formats must explain that AVTrack needs updating
and must leave existing records and files untouched.
