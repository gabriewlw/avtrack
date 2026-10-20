# Desktop workspace controls

This release adds the following desktop workflows without changing the complete
backup schema or historical import compatibility:

- **Drag and drop:** Devices, IPTV, and named inventories accept one CSV, XLSX,
  or AVTrack record JSON file at a time, using the same existing 5 MB limit.
  Files open the normal preview and editable review; records save only after an
  explicit import. Equipment backups accept configuration files up to 25 MB and
  open their details form before saving. File and icon fields, and the complete
  restore file field, also accept drops. Full app restores still require preview
  and explicit replacement confirmation.
- **Notes:** Devices and IPTV now use compact View/Add buttons, with full text on
  hover and a popup for editing. Save notes applies the change, while Cancel
  discards it. The API rejects a stale competing edit and keeps the user's draft
  visible. Existing inventory note popups retain their Apply/Cancel behavior.
- **System filters:** The redundant Devices system dropdown is removed. System
  buttons toggle independently; selecting Video and Audio matches either system.
  Venue and text searches still combine with the selected systems. All systems,
  individual active-filter chips, and Clear all filters can clear selections.
  Filtered exports use the resulting visible rows.
- **IP access:** A globe beside the copy-IP icon opens a recorded fixed device IP
  over HTTP in a new tab, with no access to the original window. DHCP and blank
  addresses do not have a browser link. Confirmation controls are slightly
  smaller; verified controls retain their green status color.
- **Sorting:** Sort by is the first entry inside the sort dropdown; the external
  label is removed. Choosing this first entry restores the original ordering.
- **Validation progress:** The Devices-only green IPs validated card shows a count
  and percentage across all fixed device IPs, independently of table filters.
  DHCP and missing addresses are listed separately. Confirmation, import, and
  deletion refresh this overall progress.
- **Page bottom:** The complete app export/restore controls sit farther below the
  records and validation information. Their dropdown continues opening upward.
- **Record details:** Identity and network information are grouped into compact
  cards with readable field labels, full notes, copy actions, and current status.
  Related backup lists, source-report links, and verification/movement timelines
  are removed from this popup. A single Added via line identifies manual entry,
  pasted data, or file import and its original filename. Later imports updating
  a record do not change its original creation method. History and recovery-file
  relationships remain stored and included in complete exports.
- **Version:** The footer explicitly labels Commit # beside the Git-derived app
  version and short hash. The number follows the actual checked-out commit count.

Checks use disposable data. All 194 backend tests passed, including historical
full-backup restore tests and competing-note-edit/source-method regressions.
Desktop browser checks cover multi-system filtering, active filter removal,
popup notes and conflicts, safe new-tab IP links, progress updates, drag-and-drop
uploads across all workspaces, import review/undo, record details, stock removal,
equipment configuration metadata, and CSV/XLSX/JSON data preservation.
