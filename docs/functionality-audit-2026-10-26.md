# AVTrack functionality audit — 26 October 2026

## Scope

Reviewed inventory persistence, condition/status, separate model batches, shelf and
free-text notes, imports, receipt/retry behavior, report exports, configuration
attachments, full-workspace backup/restore, request validation, and source/runtime
dependencies. All executions used temporary synthetic databases on GitHub Actions.
No workplace database, records, files, or installation were accessed.

## Changes made

- Browser inventory editors and inline count/status controls now send their original
  field values. The server rejects stale edits instead of silently overwriting
  another tab's newer quantity, status, notes, or custom values. Existing clients
  that omit the optional original-value snapshot remain API-compatible.
- Imports adding at least 25 new inventory records create full recovery ZIPs.
  Large reviews get growing checkpoints and a final checkpoint when completed or
  paused. Skips and repeated receipts do not count as new records. Backup failures
  preserve committed imports and produce an explicit warning. A retry can create
  the missing checkpoint without importing the row again.
- The recovery list now sorts by modification time, newest first. Import copies
  have a readable label, imported-record count and local date/time.
- Pillow was updated from 12.3.0 to 13.0.0 after the advisory scanner reported 37
  advisories in the former version. The updated runtime dependency scan passes.
- Current import tests now cover the real preview/review screens, including IPTV's
  dedicated main-column preview. The homepage browser harness initializes the
  database before serving, matching the actual application entry point.
- Added persistent CI checks for source syntax, runtime dependencies, stale-tab
  safety and large-import recovery.

No database schema, historical fixture, migration, or backup contract was changed.
See [automatic-import-backups.md](automatic-import-backups.md) for operation details.

## Verification

- **226 backend tests passed**, with PDF verification tools available and no skips.
  [Backend and historical-backup run](https://github.com/gabriewlw/avtrack/actions/runs/40420555276).
- **All 8 maintained browser suites passed**, including nine import-format/workspace
  combinations, stale-tab protection, import retries, automatic recovery and restore.
  [Browser run](https://github.com/gabriewlw/avtrack/actions/runs/40420555302).
- **All Python/JavaScript syntax checks, dependency consistency checks, and the
  updated runtime advisory scan passed.**
  [Source/dependency run](https://github.com/gabriewlw/avtrack/actions/runs/40420555360).

The backend suite includes every supported historical ZIP/JSON backup fixture,
attachment preservation, invalid/newer-backup rejection, integrity checks and
rollback. New tests cover the 24/25 boundary, 50-record checkpoints, final saves,
idempotent retries, disk-write failure, old-checkpoint warnings, quantity versus
record counting, recovery ordering, and configuration-file contents after restore.

Current browser checks cover desktop/mobile headers, the landing terminal, imported
table sizing, separate inventory batches and condition controls, notes/shelf edits,
the New-only filter, stale editors across two tabs, a complete 25-TV import and
restore, all nine CSV/XLSX/JSON × Devices/IPTV/Inventory combinations, and failed
row/final-checkpoint retries.

## Historical browser-suite findings

The initial exhaustive run executed all 46 browser scripts: **16 passed and 30
failed**. Its unmodified outcomes are retained in
[audit-browser-baseline-2026-10-26.json](audit-browser-baseline-2026-10-26.json).
Evidence: [full audit run](https://github.com/gabriewlw/avtrack/actions/runs/40418352590).

Many failures target earlier product behavior: a data table on the homepage,
fixed 39/47-pixel rows, the removed Last checked/stock-check controls, the old
navigation, an absent optional Status filter, immediate imports of JSON files,
or earlier setup dialogs and selectors. These are not 30 established data-loss
bugs. However, a failed legacy script is not counted as a passed check.

The maintained landing, condition, import-file matrix and retry checks were
updated and rerun. The remaining **26** legacy scripts still need individual maintenance
or replacement with equivalent checks of the current UI. They were not deleted,
disabled, or rewritten merely to make the exhaustive run green. The exhaustive
historical browser suite therefore remains an open test-maintenance finding;
this report does **not** certify that every archived UI scenario passes.

## Practical boundaries

- Autosave counts newly imported records, not the sum of quantities in stock rows.
  Ordinary record writes still persist immediately, including imports below 25.
- Recovery ZIPs are local copies on the same computer. Retain a complete ZIP on
  approved separate storage for recovery from computer/disk loss.
- Existing stock, notes and condition survive the tested update/backup paths. This
  audit does not inspect the accuracy of real workplace counts.
- Linux/Chromium CI does not establish Windows installer behavior, physical-device
  reachability, actual VLC playback on the workplace computer, or unrestricted
  multi-user/network deployment. No such environment was available in this session.
