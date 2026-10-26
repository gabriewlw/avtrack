# Automatic recovery after large inventory imports

Inventory imports that add at least **25 new inventory records** automatically
create a complete ZIP backup of AVTrack, including every workspace, notes,
condition values, import progress, history, and attached configuration files.
Quantity units inside one stock row are not counted as separate new records.
Skipped source rows, existing records, failed rows, and repeated request receipts
do not increase the threshold.

During a long review AVTrack checkpoints after 25 records, then at growing
intervals (normally 50, 100, 200, and so on) to limit disk usage. Finishing or
pausing the import saves its latest state whenever at least 25 records were added.
Bulk equipment JSON imports also save a recovery copy when they add 25 or more.

Imports commit their rows and receipts first. A failed automatic backup never
turns a successful import into an error or duplicates rows on retry. The import
summary warns if the recovery copy could not be saved. The next checkpoint or
a repeated request can retry that backup.

Find the ZIP files under **Back up entire app → Restore → Recovery backups**.
The list shows the newest files first with a readable date and record count.
They are saved in the `recovery` folder beside the SQLite database. Each ZIP uses
the existing full-backup format, integrity validation, migration chain, and
200 MB limit. Restore previews the data and saves the current workspace before
replacement. Imports themselves remain durable database writes even below the
automatic-backup threshold.

These copies share the computer's disk. A complete backup copied to approved
separate storage is still needed to recover from loss of that computer or disk.
AVTrack does not automatically delete older recovery files.

No database schema or historical backup contract changed for this feature.
