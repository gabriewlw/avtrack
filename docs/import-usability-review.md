# AVTrack import usability review

Reviewed 11 October 2026, with desktop use as the priority. Scope: paste and file upload, inventory templates, heading setup, field mapping, location management, batch review, duplicates, completion reports, original-file reconciliation, and checks after import.

Evidence: inspected the implementation and the attached spare-parts CSV and XLSX; exercised desktop browser flows for TV, Scala, spare parts, custom inventories, AV Devices and IPTV. Recommendations below are proposals, not implemented features.

## What works well

- Paste is the first option, with upload available for whole workbooks.
- The table preview shows suggested matches, blank cells and unmatched headings before records are imported.
- Custom inventories support heading-by-heading configuration; existing templates can keep their fields.
- Inventory review groups records by location and supports several editable rows on a screen. Complete rows can be imported automatically.
- TV imports derive totals from location counts, combine repeated brand/model rows, preserve source-total discrepancies for review and skip zero-stock models.
- Original-file reconciliation already reports matched, different, missing and ambiguous rows, plus saved records without a unique source match.
- TV **Last checked** remains a clickable date box. Only explicitly confirming a stock check sets its timestamp; an import does not establish that stock was physically checked.
- After a paste, users can choose no later confirmation, IP confirmation, or storage confirmation. IP lists offer the first two choices. Imported rows start unconfirmed.

## Highest-priority improvements

### 1. Detect and explain the header row

The attached XLSX has five worksheets. Real headings are generally on row 5; Deck 2 STB has a placeholder Column1/Column2 row above its real headings. Edit Room Deck 7 repeats LOCATION. The regular preview starts with header row 1 and uses the first nonempty row, while automatic header scanning is currently used in reconciliation. This means the import can initially select placeholder headings.

Scan the first 50 rows, score recognizable headings and the data below them, and propose the best row. Display “Column headings found on row 5” with an editable miniature sheet. For repeated headings, show the source column number and several sample values. Ask only when confidence is low. Preserve identifiers as text, including leading zeros.

Evidence: spreadsheets.py preview; static/app.js loadSpreadsheet; reconciliation.py reconcile_profile.

### 2. Consolidate the stages and reuse previous decisions

Paste, confirmation, preview, heading setup, mapping and review are separate dialogs. Heading setup already assigns source columns, but mapping then asks the user to inspect those same assignments again. Repeated worksheets also rebuild mappings.

Use a stable desktop workspace with a visible progress strip: **Paste or upload → Check headings and fields → Review by location → Import summary**. Keep the requested one-by-one questions for first-time setup, while displaying their answers in a side panel. Remember mappings and confirmation preferences per inventory; subsequent pastes should ask only about new or changed headings. Allow Back without losing edits.

Evidence: static/app.js showPastedLayoutSuggestion, startPastedHeadingSetup, loadSpreadsheet.

### 3. Keep setup changes as a draft until explicitly applied

Inventory layout changes are currently saved during heading setup, before item import. The new confirmation choice also applies the inventory-wide workflow before preview. Changing that workflow resets existing confirmation marks. Cancelling later does not undo settings already applied.

Hold field definitions, mappings and workflow changes in a draft. Show their effects together before an explicit “Apply setup and start import” action. State clearly when a change affects existing records. Keep confirmed location checks and IP checks distinct so one cannot be mistaken for the other.

Evidence: static/app.js paste-field-form and paste-confirmation-form; app.py save_equipment_inventory.

### 4. Offer batch review for AV Devices and IPTV

Inventory review supports batches of up to eight rows, while AV and IPTV still require an individual acceptance dialog for every row. This becomes repetitive for large IP lists.

Reuse the editable batch table for all types. Filter to invalid IPs, missing values or duplicate assignments; let users import valid selected rows together. Retain individual row editing. Import acceptance must remain separate from later IP reachability or storage confirmation.

Evidence: static/app.js spreadsheet-form, reviewImportRow; static/import-review.js reviewEquipmentBatch.

### 5. Make completion durable and allow interrupted imports to resume

Accepted rows are saved as review proceeds. Stopping retains those rows. Import reports and cross-check displays are stored in browser memory, so reload loses them; there is no saved import session to resume.

Persist an import session with source worksheet/row, mapping, completed rows, skipped rows and unresolved issues. Show “42 saved; 18 still to review” before stopping. Offer Resume and a downloadable report. Keep a clear summary by location: added, existing, merged, zero-stock, skipped and unresolved. Separate source-row counts from saved-record counts because TV merging changes those totals.

Evidence: static/app.js spreadsheet-form, closeSpreadsheet; static/equipment.js importReports and crossChecks; static/import-review.js outcomes.

## Further improvements

### 6. Import several worksheets as one session

Workbook import currently selects one worksheet at a time. The supplied file has Deck 6 Locker, Deck 2 PORT, Deck 2 STB, Edit Room Deck 7 and Tools, with different column orders.

Offer worksheet checkboxes, preview a separate mapping for each sheet, and suggest its name as a default location only where location cells are blank. Process each location's complete and flagged records before advancing. For repeated pastes, provide “Add another location” while retaining the session and inventory setup.

### 7. Explain duplicate decisions and make location exclusions reversible

Network duplicate assignments are skipped; TV brand/model rows can be combined. Location deletion during mapping excludes its items, and reloading the sheet resets those exclusions. These behaviors need an explicit, stable preview.

Show an existing-versus-source comparison and the intended action before import. List combined TV source rows and resulting counts. Include a separate “Excluded locations” panel with Restore. Label the action “Exclude location from this import” to distinguish it from deleting stored inventory locations.

### 8. Reduce horizontal scrolling during review

The batch table has a minimum width of 380 + 170 pixels per field. A wide custom inventory still requires substantial horizontal scrolling even on desktop.

Keep row selection, model/ID and result visible while scrolling. Size controls to their values, collapse notes into the existing floating editor, and allow secondary fields to expand per row. Provide keyboard Next/Previous and keep required unchecked fields visibly marked.

### 9. Bring original-file reconciliation into the finish step

The original-file cross-check is a separate upload action. Users must remember to run it, and reports disappear on reload unless downloaded.

Offer “Compare with original” directly in the final summary, reusing the source file and mappings where available. For paste-only imports, explain that comparison covers only pasted rows and allow uploading the original workbook for a complete check. Separate “all source rows accounted for” from “all items physically located.” Preserve the report after reload.

## Suggested order

1. Header detection and duplicate-heading samples.
2. Saved mappings and a unified progress workspace.
3. Draft setup plus batch review on IP pages.
4. Durable completion reports, resume and multiple worksheets.
5. Integrated reconciliation and compact review controls.

Keep template defaults, optional orientation editing, custom brands, location-first review, zero-stock handling and the TV Last checked box throughout these changes.
