# Inventory batches and unit condition

Each row is a stock batch. The same TV brand/model may have separate counts when
Notes or Status differ. Other unserialized stock also preserves separate notes
and custom values. Serial numbers and explicitly configured unique asset IDs
remain unique. Combining storage locations preserves batches with different notes.

Status uses optional New / Used / Broken buttons, during import review, manual
entry and after import. Selecting the current status again clears it. Blank is
unknown and is never counted as New. The green TV summary sums known quantities
for New rows across the current TV inventory. Search and filters do not change
the summary's scope. Last-check timestamps and historical checks remain in saved
data and complete backups; the visible date column has been removed.

Manual Add equipment and Add count ask for an optional storage shelf. The server
appends Shelf: <value> to Notes, with the existing 2,000-character limit. Shelf is
not a separate table column. Notes and Status are included in inventory CSV,
XLSX and PDF exports, including TV exports.

The homepage inventory card reports known unit quantities across inventories,
rather than the number of rows. Inventories with no quantity field (such as Scala
locations) count each record as one unit; unknown quantities in counted inventories
are not assumed to be one.

Condition uses the existing optional custom-column storage contract
(custom_values.unit_status). Old layouts gain the optional Status and Notes
controls on read, without rewriting saved rows, assuming a condition, or deleting
historical check data. No table columns, field definitions, or backup contracts
changed. Published schema contracts, migration functions and historical fixtures
remain untouched. An additional complete schema-2 fixture covers condition and
shelf notes, and the full historical backup suite plus new round-trip tests run
on every push.
