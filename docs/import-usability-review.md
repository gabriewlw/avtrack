# AVTrack import usability review and improvements

Reviewed and implemented 10 October 2026 (Pacific time), with desktop use as the priority. The review covered paste and upload, templates, heading setup, mapping, location exclusions, batch review, duplicates, completion, reconciliation and physical checks.

## Implemented workflow

1. **Detect headings independently for every source.** Scan the first 50 rows, skip title and placeholder rows, and show candidate rows with sample values. Header selection remains editable. Duplicate headings display their column numbers and sample values. XLSX numeric identifiers with zero-padded number formats retain their displayed zeros.
2. **Keep the stages in one workspace.** A persistent progress strip connects paste/upload, headings and fields, review by location, and summary. Keep heading-by-heading questions for new custom fields. Reuse saved choices by heading name and occurrence, never by old column position. Each new paste can reorder, rename, add or omit headings. The preview reports changes, and Reset suggested matches allows a fresh setup.
3. **Apply setup explicitly.** Column and confirmation changes remain drafts until Apply setup and start import. Cancelling leaves the saved inventory unchanged. The preview explains when changing confirmation clears previous marks. Concurrent layout changes require a fresh setup.
4. **Review IP lists in batches.** AV Devices and IPTV use the same editable multi-row review as inventory, with up to eight records per screen. Valid rows start selected; flagged rows remain available for editing. Import acceptance remains separate from IP reachability and storage checks.
5. **Save resumable progress and reports.** SQLite stores the source, draft mappings, edited pending rows, exclusions and per-row receipts. Inventory writes and receipts commit together; retrying a completed source row does not add it again. History supports Resume and View report, including older sessions. Downloaded reports contain results without embedding the uploaded file. Deleted inventories retain read-only reports and cannot resume into a replacement inventory.
6. **Queue worksheets.** Select several XLSX worksheets and process them sequentially, reviewing each sheet's own headings and mappings. Blank storage locations can default to the worksheet name; Scala geographical locations remain blank. Add another location opens a new paste with suggested previous choices.
7. **Explain duplicates and exclusions.** Preview matching saved records and combined TV source rows before import. Exclude location applies only to the current import, with a visible Restore action. Exclusions survive preview reloads and resume, and remain visible in reports and reconciliation.
8. **Keep batch review compact.** Selection, model/ID and results stay visible while scrolling. Narrower controls and floating Notes editors reduce table width. Alt+Up/Down moves between rows. Required field checks stay explicit; optional orientation remains editable.
9. **Compare at completion.** The summary offers Compare with source and uploading the original workbook. It reuses saved mapping choices where applicable, displays discrepancies and saves the comparison for later viewing or download. Counts distinguish source rows, records added and combined TV rows.

## Preserved behavior

Template defaults, custom brands, optional orientation, location-first review and zero-stock handling remain available. TV **Last checked** stays a clickable stock-check box. Importing, reconciling or reviewing a record never establishes that stock was physically checked; only an explicit stock check sets the date.

## Practical limits

A paste comparison covers the pasted data only. Upload the original workbook to check the full source; unsupported worksheets, excluded locations and ambiguous matches remain visible for review. Different original-file headings can still require mapping adjustments through a new import preview or investigation of the reported differences. Comparison results are snapshots and should be rerun after edits. Wide custom inventories may still scroll horizontally, with key cells pinned.

Drafts and history live in the application's SQLite database and require access to its server. They are included in database backups; browser cache is not the source of truth. Sources are capped by the existing upload limit and session size limit. Separate pastes create separate resumable sessions, while selected worksheets share one session.

## Validation

Backend checks cover receipt retry, transaction rollback, destination pinning, deleted inventory protection, saved reports, header detection, zero-padded identifiers, duplicate heading mappings and explicit exclusions. Desktop browser checks cover draft cancellation, IP batch edits, floating notes, reload/resume, independently changed paste headings, reset suggestions, multi-sheet mapping, source comparison and report download, plus inventory templates, custom heading setup, repeated pastes, brands, optional orientation, exclusions and TV stock dates. The supplied five-sheet spare-parts workbook independently detects its real headings on row 5 in every sheet.
