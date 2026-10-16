"""The empty home route is a landing page instead of a blank data directory."""
import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright


with tempfile.TemporaryDirectory() as temp:
    app.DB_PATH = Path(temp) / "inventory.sqlite3"
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=shutil.which("chromium"))
            page = browser.new_page()
            origin = f"http://127.0.0.1:{server.server_port}"
            page.goto(origin + "/")
            page.locator("#home-empty-state").wait_for(state="visible")
            assert page.locator("#inventory").is_hidden()
            assert page.locator("#workspace").is_hidden()
            assert page.get_by_role("heading", name="Your AV workspace is ready for its first record.").is_visible()
            heading_box = page.locator("#home-empty-title").bounding_box()
            assert heading_box and heading_box["height"] < 50, heading_box
            assert page.locator(".overview-card-actions").evaluate_all("groups => groups.every(group => group.firstElementChild.matches('a.overview-workspace-link') && group.lastElementChild.matches('button.overview-add'))")

            page.get_by_role("button", name="＋ Add channel").click()
            page.locator("#device-dialog").wait_for(state="visible")
            assert page.url.endswith("/#iptv")
            assert page.locator("#form-title").inner_text() == "Add channel"
            page.locator("#close-dialog").click()

            page.goto(origin + "/")
            page.locator("#home-empty-state").wait_for(state="visible")
            page.get_by_role("button", name="＋ Save backup").click()
            page.locator("#backup-dialog").wait_for(state="visible")
            assert page.url.endswith("/backups")
            page.locator("#close-backup").click()

            app.save_device(dict(name="Saved device", ip="10.20.1.1", vlan=1, venue="Studio", discipline="Video", notes=""))
            page.goto(origin + "/")
            page.wait_for_function("() => document.getElementById('overview-av-total').textContent.includes('1 device')")
            assert page.locator("#home-empty-state").is_hidden()
            assert page.locator("#inventory").is_visible()
            assert page.locator(".device-row").count() == 1
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

print("Empty home landing passed: blank directories stay hidden, start actions work, and data restores the dashboard.")
