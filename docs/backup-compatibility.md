# Complete-backup compatibility policy

Full AVTrack ZIP/JSON backups are a long-lived transfer format. New releases must
continue importing every supported historical backup. The application release
number does not determine compatibility; the backup format and data-schema
versions do. A routine application update does not require a new export.

This policy applies to **Back up entire app → Complete backup ZIP/JSON**.
Spreadsheet reports and single-workspace record exports are separate formats.

## Supported historical backups

| Exporter | Envelope `version` | Data schema | Current restore |
| --- | --- | --- | --- |
| v0.0.186 and v0.0.187 | 1 | Legacy schema 1, detected from its known layout | Automatically migrates |
| v0.0.188 | 1 | Legacy schema 2, detected from its known layout | Restores directly |
| v0.0.189 onward | 1 | Explicit `schema_version`, initially 2 | Retained migration chain |

Version 186 introduced complete backups. Immutable synthetic exports from those
three historical releases are checked into `tests/fixtures/full_backups/`, along
with an explicit-schema backup. They contain Devices, IPTV, named inventories,
custom layouts and values, multiline notes, dated checks, import preferences and
receipts, and attached configuration files/icons. The schema-2 examples also retain
audit history and equipment configuration recovery metadata.

ZIP and JSON carry the same data. Storage filenames can change on restore to avoid
overwriting existing files; attachment contents and their record associations are
preserved. Legacy backups without integrity metadata remain supported. Backups
with integrity metadata are checked before migration.

## Version and migration rules

- `version` describes the outer backup envelope. It is independent of app versions
  such as v0.0.189. Envelope version 1 remains supported.
- `schema_version` describes the stored data contract. New exports always include
  it. Old files without it are recognized using frozen, complete layouts rather
  than guessed missing values.
- `backup_schemas/vN.json` freezes each data schema's columns and database field
  definitions. Physical column ordering can differ after an in-place upgrade;
  missing, duplicate, or unknown fields cannot be silently ignored.
- `backup_compat.MIGRATIONS[N]` transforms schema N into N+1 using application code.
  A restore applies every required step, validates each intermediate shape, then
  validates the final values and attachments against the current database.
- Migrations work on a private copy. The original backup remains reusable and is
  never rewritten. Restore still uses a database transaction and unique attachment
  storage names, with rollback and cleanup on failure.
- A schema change without an updated contract prevents full export/restore from
  proceeding. A missing migration also fails safely. This catches unversioned
  table, column, type, nullability, default, and primary-key changes.

Before replacing records, restore preview shows whether an older schema will be
upgraded automatically. Restore validates before creating the destination's
automatic recovery ZIP. A rejected backup leaves the records and attached files
in place. The transfer limit remains 200 MB; compatibility does not remove that
size limit.

## Required procedure for future releases

For any stored-data change, including a change in field meaning:

1. Keep the published contracts, fixtures, and migration functions unchanged.
2. Add `backup_schemas/v<N+1>.json` and increase `CURRENT_SCHEMA_VERSION`.
3. Add `MIGRATIONS[N]`. Explicitly map renamed/changed fields and supply safe
   defaults for additions. Preserve records, IDs, relationships, history, custom
   fields, and attachments. Never execute SQL or executable instructions from a
   backup, and never silently discard unsupported data.
4. Add a complete synthetic `schema-<N+1>.json` fixture containing representative
   values for the new fields. Include assertions for those values, migration
   failure, and restore/export/restore preservation.
5. Run all backend tests. `test_backup_compatibility` restores every historical
   fixture through both HTTP ZIP and JSON paths, checks all table values and
   attachment bytes, verifies recovery copies, and tests migration ordering and
   rejection without replacement.
6. Check the GitHub **Backend and full-backup compatibility** workflow before
   releasing. It runs on pushes and pull requests and rejects modifying/deleting
   published contracts or historical backup fixtures. It also requires a contract,
   fixture, and forward migration for each supported schema version.

Root `AGENTS.md` records the same requirement for future coding work. The runtime
guard and CI make accidental breakage visible; maintainers must retain these
checks and migration steps in future releases.

## Compatibility direction

The commitment is **older backup → newer AVTrack**. An older application cannot
interpret features and fields that have not been designed yet. If a backup has a
newer unsupported schema or envelope, AVTrack asks the operator to update and
keeps the destination data. It does not pretend to import the file by dropping
unrecognized information.

No current implementation can prove that every unwritten future release is
correct. This policy, retained migrations, immutable historical examples, runtime
guards, and CI provide the ongoing mechanism to preserve that compatibility.
