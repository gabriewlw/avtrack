# AVTrack

AVTrack is a local workspace for cruise ship broadcast operations. It brings AV device addresses, IPTV channel endpoints, equipment inventories, and configuration backups into one simple application.

## Why I created it

I designed AVTrack from my experience working as a broadcast technician on cruise ships. Our work involves the access of many audio and video devices, IP addresses, television channels, management of spare parts, storage locations, and configuration files. That information is often spread across spreadsheets, notes, and folders, which makes it slower to find during day-to-day work and much harder to use during an emergency.

I wanted one practical tool that could help me:

- find an AV device and copy its IP address quickly when I need to access or configure it;
- keep the IP address and port for every onboard IPTV channel in one place; and be able to open the stream in one click;
- make physical inventory checks less repetitive and make equipment easier to locate;
- preserve known-good equipment backups so recovery files are ready when something is lost or reset.

AVTrack is built around those jobs. It runs locally, uses a single SQLite database, and does not require a frontend build process or a cloud account.

## What AVTrack manages

### Devices

Store each device’s name, venue, IP address or DHCP assignment, VLAN, system, category, and notes. Search the full directory, filter it by venue or system, copy an IP address with one click, and record when an address has been manually confirmed.

AVTrack validates address formatting and prevents new duplicate fixed IP addresses. **IP confirmed** means that a user verified the device; AVTrack does not continuously ping or monitor devices.

### IPTV

Keep onboard and satellite channels together with their IP addresses, UDP ports, sources, and notes. Search the lineup, filter it by source, and copy a complete UDP address when troubleshooting or testing a channel.

AVTrack stores and validates the channel endpoint. It does not play the stream or automatically measure whether a channel is currently on air.

### Inventory

Create separate inventories for spare parts, Scala players, televisions, AMX equipment, Planar displays, TVRO, Daktronics, laptops, projectors, STBs, or a custom equipment type.

Paste cells directly from Excel or import CSV/XLSX files. AVTrack reads the headings, suggests field matches, identifies incomplete rows, groups review work by location, and lets you confirm several records at once. Locations, stock-check history, serial numbers, custom columns, notes, and Located/To be found status can be configured for each inventory.

Use the source comparison tools after an import to check that spreadsheet records reached AVTrack. Blank values remain available for later inspection instead of blocking the entire import.

### Backups

Save known-good files for Videohubs, ATEM switchers, satellite receivers, OBS profiles, and other AV systems. Each record includes the device name, equipment type, date, notes, and an optional card icon.

The actual files are stored in a normal local folder, so they remain easy to copy or synchronize. AVTrack stores their descriptions and file references in SQLite. Each uploaded backup can be up to 25 MB.

## Quick start

AVTrack requires **Python 3.12 or newer**. No Node.js installation or frontend compilation is required.

### Windows PowerShell

Open PowerShell in the downloaded AVTrack folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

If the `py` command is unavailable, use `python` instead:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Using `.venv\Scripts\python.exe` directly avoids PowerShell execution-policy problems and does not require activating the virtual environment.

### macOS or Linux

Open a terminal in the AVTrack folder and run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

When the terminal displays:

```text
AVTrack listening on 127.0.0.1:8000
```

open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

Keep the terminal open while using AVTrack. Press **Ctrl+C** in that terminal to stop the server.

### Product showcase

Open [http://127.0.0.1:8000/avtrack](http://127.0.0.1:8000/avtrack) for the standalone AVTrack presentation. This page explains the product through an animated, scroll-based tour and is designed to be adapted for `broadcastgab.com` without replacing the application home page.

## First use

The home page shows four workspace cards. Use **Add** to open the correct form immediately, or **Open workspace** to see the complete section.

A useful starting order is:

1. Add one AV device manually and confirm that its layout fits your workflow.
2. Paste a small section from an existing spreadsheet and review the suggested columns.
3. Create the inventory types you need and import one location at a time.
4. Add known-good recovery files under Backups.
5. Export a report and copy the `data` folder to safe storage.

## Importing spreadsheets

**Paste from Excel** is the quickest import method. Copy a rectangular group of cells in Excel, including the heading row, and paste it into AVTrack. The first pasted row is always treated as the column-heading row, and headings containing multiple words remain together when they come from one Excel cell.

AVTrack then:

1. previews the pasted table;
2. suggests matches between the source headings and AVTrack fields;
3. asks for the confirmation and stock-check behavior needed by that table;
4. shows complete and flagged rows for review;
5. imports accepted records and retains an import report for comparison.

File upload remains available for `.csv` and `.xlsx` files, including workbooks with multiple worksheets. Excel files preserve worksheets and cell structure better; CSV is smaller and easier to inspect manually.

Spreadsheet layouts can differ from one job to another. Always review the detected headings, destination inventory, quantities, and locations before applying a large import.

## Search, confirmation, and reports

- Devices searches names, IP addresses, venues, systems, VLANs, categories, and notes.
- IPTV searches channel names, IP addresses, ports, sources, and notes.
- Inventory searches every visible and custom field, including model and all stored serial numbers.
- Confirmation buttons save a manual check. They do not perform automatic network or physical verification.
- Inventory stock checks retain dated history when enabled for that inventory.
- Exports support JSON, CSV, XLSX, and PDF. You can export the current filtered view, selected rows, or the complete active list.

JSON is the best format for restoring AVTrack records. CSV and XLSX are convenient for spreadsheet work. PDF is intended for a clear printable or shareable report.

## Where the data is stored

By default, AVTrack uses:

```text
data/inventory.sqlite3   Main database
data/backups/            Uploaded backup files and icons
```

The SQLite database stores Devices, IPTV channels, inventories, import history, confirmation history, and backup metadata. The `data/backups` folder stores the actual equipment backup files.

To make a complete manual backup:

1. stop AVTrack with **Ctrl+C**;
2. copy the entire `data` folder;
3. store the copy on another drive or approved synchronized location.

To move AVTrack to another computer, copy the whole project folder, including `data`, and recreate `.venv` using the installation commands above. Virtual environments should be recreated after moving a folder because their launch files may contain paths from the previous computer.

### Export or move the complete workspace

On the homepage, use **Export all data** beside **Your workspace at a glance**:

- **Complete backup ZIP** is recommended when moving computers. One file includes every workspace, inventory layout, custom field, note, confirmation, saved history, and uploaded backup file/icon.
- **Complete backup JSON** contains the same restorable data in an uncompressed file.
- **Excel workbook** and **CSV files ZIP** are reports of saved records, without the uploaded file contents. They cannot restore the whole app.

On the other computer, run the same AVTrack version, choose **Workspace import** beside **Export all data** on the homepage, select the complete ZIP or JSON backup, and confirm **Replace all current workspaces**. The app reloads with the restored data. Export the destination's data first if you need to keep it: this is a complete replacement, not a merge.

Complete transfers support files up to 200 MB, including the uncompressed backup contents. For larger workspaces, stop AVTrack and copy the entire `data` folder instead. Custom `AVTRACK_DB` and `AVTRACK_BACKUP_DIR` locations remain configured on the destination computer.

### Custom storage locations

Set `AVTRACK_DB` to place the SQLite database elsewhere and `AVTRACK_BACKUP_DIR` to choose another folder for equipment backup files.

PowerShell example:

```powershell
$env:AVTRACK_DB='D:\AVTrack-Data\inventory.sqlite3'
$env:AVTRACK_BACKUP_DIR='D:\AVTrack-Data\backups'
.\.venv\Scripts\python.exe app.py
```

macOS/Linux example:

```sh
AVTRACK_DB=/path/to/AVTrack-Data/inventory.sqlite3 \
AVTRACK_BACKUP_DIR=/path/to/AVTrack-Data/backups \
.venv/bin/python app.py
```

Keep both locations backed up. Copying only the SQLite file does not include the uploaded equipment backup files.

## Opening AVTrack from another device

AVTrack listens only to the local computer by default. To make it available to another device on the same trusted network, bind it to all network interfaces.

PowerShell:

```powershell
$env:HOST='0.0.0.0'
$env:PORT='8000'
.\.venv\Scripts\python.exe app.py
```

macOS/Linux:

```sh
HOST=0.0.0.0 PORT=8000 .venv/bin/python app.py
```

On the other device, open `http://COMPUTER-IP:8000`, replacing `COMPUTER-IP` with the address of the computer running AVTrack. `localhost` always refers to the device on which the browser is running.

The operating-system firewall and shipboard VLAN rules must allow the connection. AVTrack currently has no user login, so expose it only on a trusted private network. Do not publish the built-in server directly to the Internet; an Internet deployment needs HTTPS and an authenticated reverse proxy or access gateway.

## GitHub Codespaces

In a Codespace, use:

```sh
cd /workspaces/avtrack
git pull --ff-only origin main
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
HOST=0.0.0.0 PORT=8000 .venv/bin/python app.py
```

Open port **8000** from the Codespaces **Ports** panel and keep its visibility **Private**. Leave the server running in that terminal and use a second terminal for Git or diagnostic commands.

If a forwarded Codespaces page remains stuck on Loading even though the API returns status 200, open `/recover` on the forwarded AVTrack address. The recovery page clears AVTrack’s browser cache and service worker without deleting the server database.

## Updating AVTrack

For a Git checkout:

```sh
git pull --ff-only origin main
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

PowerShell equivalent:

```powershell
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Stop the existing server before updating and restarting it. Keep the complete `data` folder. Database upgrades run automatically when AVTrack starts.

If you update from a downloaded ZIP instead of Git, copy your existing `data` folder into the new AVTrack folder before starting it.

## Troubleshooting

### PowerShell says that running scripts is disabled

Use the virtual environment’s Python executable directly:

```powershell
.\.venv\Scripts\python.exe app.py
```

Activation is optional. If you prefer activation for the current PowerShell window:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### The browser cannot open AVTrack

Confirm that the terminal still displays `AVTrack listening on ...`. Use the exact address shown, normally `http://127.0.0.1:8000`. If the terminal was closed or the computer restarted, start `app.py` again.

### Port 8000 is already in use

Choose another port:

```powershell
$env:PORT='8001'
.\.venv\Scripts\python.exe app.py
```

Then open `http://127.0.0.1:8001`.

### The page shows old code after an update

Restart the server and refresh the browser with **Ctrl+F5**. If the problem continues, open [http://127.0.0.1:8000/recover](http://127.0.0.1:8000/recover).

### Package installation fails

Check the Python version:

```sh
python --version
```

Use Python 3.12 or newer, recreate `.venv`, and run the dependency installation command again.

## Project structure

```text
app.py                 Local HTTP server, API, and SQLite storage
static/                Browser interface, styles, fonts, and offline assets
data/                  Local database and uploaded backup files
docs/                  Examples, screenshots, and workflow documentation
tests/                 Backend and browser checks
requirements.txt       Pinned Python dependencies
```

Useful references:

- [Sample equipment inventory CSV](docs/examples/equipment-inventory.csv)
- [Import usability review](docs/import-usability-review.md)
- [IPTV satellite channel reference](docs/satellite-channel-reference.md)

## Development checks

Run the backend test suite from the project folder:

```sh
PYTHONPATH=tests .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Browser checks in `tests/browser_*.py` require Playwright and Chromium in the development environment.

## Current scope

AVTrack is designed first for a trusted local or private-network workflow. It currently does not provide user accounts, permissions, automatic device polling, continuous IPTV stream monitoring, or cloud synchronization. Those capabilities can be added later without changing the purpose of the project: keeping broadcast information organized, searchable, and ready when it is needed.

AVTrack was created for real broadcast work at sea, where fast access to the right address, item, or recovery file can save valuable time.
