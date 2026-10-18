# Desktop hardening release

This release implements the changes proposed in the desktop review of v0.0.187 (`53386a0`), from the perspectives of a first-time technician and a broadcast supervisor. Mobile and iOS work remain deferred. The previous release remains available at Git tag `v0.0.187` and branch `backup/v0.0.187`.

## Imports

- A common default flow for pasted tables, CSV, XLSX, and workspace record JSON: choose the source, preview it, review editable rows, explicitly import selected rows, then see results. Merely previewing does not save records or apply inventory layout changes.
- Column mapping and verification settings are available under Advanced settings. The destination and source remain part of the import workflow.
- Additional source columns continue into Notes, one value per line. Original notes, multiline JSON notes, and custom values are preserved.
- Worksheet selection is visible in the initial preview. Missing inventory locations use the worksheet name; an explicit source location wins. Multi-sheet imports return to the preview for each selected worksheet.
- A new custom inventory can infer headings from the source instead of requiring a separate column-definition wizard. Up to 15 source headings plus Notes are inferred; remaining unmapped data is retained in Notes. Layout changes are applied when the import is explicitly submitted.
- Add new records only is the visible default. Review changes to existing records compares recognized matches, shows field differences, and requires selecting updates. Ambiguous or unmatched rows are not silently treated as an update. Updates reject stale comparisons and clear obsolete verification flags.
- Complete app backup JSON is directed to Restore app backup rather than being mistaken for a single workspace import.
- Stop and keep saved rows describes partial-import behavior. Import results distinguish additions and updates, retain source reports, and offer Undo this import.
- Undo validates every affected record before changing any of them, reverses additions and reviewed updates atomically, and blocks when later edits or other tracked activity would be lost. Already-undone imports cannot be undone again.

## Adding and consulting records

- New inventory creation offers Add first item or Import spreadsheet.
- Unsaved new-device and new-equipment drafts survive closing and reopening the form within the browser tab. Successful saves clear the draft. Add another retains the current venue or location.
- A manually entered device without a name or IP requires the deliberate Save as incomplete action. Incomplete rows have a visible identity placeholder.
- Duplicate device IP errors offer View existing device.
- Active filter chips and Clear all filters clarify workspace search scope. Find anywhere searches saved records and equipment backup descriptions across all workspaces, grouping inventory matches by inventory name. It shows up to 200 results at once and asks for a narrower search when needed.
- Device names and inventory Details open a read-focused panel containing technical fields, multiline notes, copy actions, verification information, import provenance, history, and associated downloadable equipment configurations.
- Import provenance identifies source, worksheet, source rows, and date, with a downloadable source report for newly tracked imports. Existing records without tracked receipts are identified accordingly.
- Overview is an explicit navigation destination. Desktop workspaces use a compact header; the larger introductory hero remains on Overview. Equipment backups is used consistently to distinguish configuration files from complete app backups.

## Stock, verification, and handover

- Confirmed locations counts distinct locations only when every record in that location is physically located, rather than counting individual records.
- Unknown quantities are explicitly reported alongside known-unit totals; they no longer disappear behind a misleading completion figure.
- Record/source review, physical location, physical stock count, and manually verified IP are labeled separately. Spare parts enable dated physical count history by default.
- Optional reviewer initials are retained on this browser for subsequent checks. These are annotations, not authenticated user identities.
- Unit removal starts with no selected serial and a disabled submit action. Choose one of the row's serials, an unserialized unit where available, or Delete entire record. The confirmation shows the chosen serial and quantity before and after; success feedback identifies the removal.
- Stock movement history records serial/description, quantity change, time, optional reason, and initials. Whole-record stock deletion is also retained in movement history.
- Handover groups unknown quantities, unlocated equipment, pending source reviews, checks older than 90 days, devices without a linked known-good configuration, and the 50 most recent stock movements. Lists display up to 200 records per group.
- IPTV summaries say channels saved. No saved endpoint is presented as a continuously monitored on-air channel.

## Equipment configuration recovery

- Recovery details can associate a configuration file with a device, IPTV channel, or inventory item.
- Optional model/serial, compatible firmware, capture date, and last restore-test date give context when choosing a recovery file.
- Untested, known good, and superseded states appear on backup cards and in related-record details.
- Linked files appear in record consultation. Handover distinguishes a linked known-good device backup from an untested file.
- Deleting an item unlinks its configuration files without deleting those files. A new record that reuses a database ID does not inherit the deleted item's backup links or audit history.

## Complete backups, reports, and destructive actions

- Fixed the HTTP 500 when downloading a complete JSON backup; ZIP and JSON both support complete restore.
- Back up entire app and Restore app backup distinguish complete transfers from current-workspace exports and equipment configurations.
- Restore first validates the file and previews date, app/format version, record counts, inventory names, and attached-file counts. Replacement still requires the explicit confirmation checkbox. A rejected preview leaves saved records intact.
- Before complete restore, batch device deletion, or whole-inventory deletion, AVTrack saves a complete recovery ZIP beside the database in `recovery/`. Existing copies are downloadable from the restore dialog. They remain on disk until the operator removes them.
- New ZIP/JSON snapshots include an integrity digest. Restore checks structure, supported columns, scalar values, flags, quantities, custom-field JSON, attachment data, and recorded attachment sizes. Invalid restores roll back database changes and remove newly created attachment files while preserving prior files.
- Complete backups from the immediately previous v0.0.187 schema are accepted, initializing the new optional audit and recovery-detail tables. Other incompatible schemas are rejected rather than guessed.
- Timestamped filenames distinguish successive full exports. Backup metadata records export time and the Git-derived application version.
- Complete XLSX and CSV reports use Devices, IPTV, named inventories, and Equipment backups, including readable custom fields and recovery metadata. Internal preferences and receipt tables stay in the restorable ZIP/JSON instead of appearing as report worksheets.
- Current-workspace export menus show the scope and available row counts before download.
- The footer continues deriving version and short revision from Git. The service worker cache advances so updated browser assets are fetched.

## Verification

All tests use disposable data. All 184 backend tests passed. The suite covers export/restore formats, integrity and malformed snapshots, baseline-schema compatibility, recovery copies, safe reviewed updates, atomic undo and later-edit conflicts, audit history, stock movement, and equipment backup links alongside existing application behavior.

Five desktop Chromium acceptance checks cover drafts, manual and incomplete entry, source preview without writes, explicit add/update imports, undo, unknown stock counts, serial-specific removal, record details, search, handover, multi-worksheet locations, custom headings, JSON notes, full JSON downloads, restore previews, multiline inventory notes, and equipment backup file operations. This is a targeted desktop release check, not a claim that every historical browser script or mobile scenario was rerun.

## Practical limits

- Complete transfer files and their unpacked contents remain limited to 200 MB. For larger installations, stop the app and copy the complete data folders.
- A complete restore replaces data; it does not merge computers. Keep an independent copy of backups on another drive.
- Import undo is available for changes tracked by this release. Older imports remain reports, and any subsequent tracked activity blocks undo to avoid losing newer work.
- Drafts live within the current browser tab/session, not as durable server records.
- Checks, known-good labels, and test dates are entered manually. AVTrack does not ping equipment, monitor IPTV, validate a configuration against real hardware, or authenticate reviewer initials.
- Compatibility was exercised for v0.0.187 and the current schema. No promise is made for arbitrary releases or every real-world workbook.
