"""Shared AVTrack pages resolve the BroadcastGab design tokens consistently."""
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
    app.save_equipment_inventory({'name':'Test inventory'})
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=shutil.which("chromium") or None)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            origin = f"http://127.0.0.1:{server.server_port}"
            page.goto(origin + "/")
            page.locator("#home-empty-state").wait_for(state="visible")

            tokens = page.evaluate("""() => {
              const style = getComputedStyle(document.documentElement);
              const names = ['--background','--card','--secondary','--surface-accent','--border','--foreground','--muted-foreground','--primary','--primary-foreground'];
              return Object.fromEntries(names.map(name => [name, style.getPropertyValue(name).trim()]));
            }""")
            assert tokens == {
                "--background": "oklch(0.16 0.008 260)",
                "--card": "oklch(0.20 0.01 260)",
                "--secondary": "oklch(0.24 0.012 260)",
                "--surface-accent": "oklch(0.27 0.014 260)",
                "--border": "oklch(0.30 0.012 260)",
                "--foreground": "oklch(0.93 0.01 90)",
                "--muted-foreground": "oklch(0.62 0.015 260)",
                "--primary": "oklch(0.63 0.24 25)",
                "--primary-foreground": "oklch(0.14 0.01 260)",
            }

            colors = page.evaluate("""() => {
              const probe = document.createElement('div');
              probe.style.cssText = 'position:fixed;left:-9999px;background:var(--background);color:var(--foreground);border:1px solid var(--border)';
              document.body.append(probe);
              const p = getComputedStyle(probe);
              const b = getComputedStyle(document.body);
              const values = {
                probeBackground: p.backgroundColor,
                bodyBackground: b.backgroundColor,
                probeForeground: p.color,
                bodyForeground: b.color,
                primary: getComputedStyle(document.querySelector('.overview-card > strong')).color,
                probePrimary: (() => { probe.style.color = 'var(--primary)'; return getComputedStyle(probe).color; })(),
              };
              probe.remove();
              return values;
            }""")
            assert colors["bodyBackground"] == colors["probeBackground"], colors
            assert colors["bodyForeground"] == colors["probeForeground"], colors
            assert colors["primary"] == colors["probePrimary"], colors

            page.goto(origin + "/inventory")
            page.locator("#equipment-panel").wait_for(state="visible")
            page.locator("#add-device").click()
            dialog_colors = page.locator("#equipment-dialog").evaluate("""element => {
              const root = document.createElement('div');
              root.style.cssText = 'background:var(--card);color:var(--primary-foreground)';
              document.body.append(root);
              const button = getComputedStyle(element.querySelector('button.primary'));
              root.style.background = 'var(--primary)';
              const primaryBackground = getComputedStyle(root).backgroundColor;
              const result = {
                dialogBackground: getComputedStyle(element).backgroundColor,
                cardBackground: (() => { root.style.background = 'var(--card)'; return getComputedStyle(root).backgroundColor; })(),
                buttonBackground: button.backgroundColor,
                primaryBackground,
                buttonForeground: button.color,
                primaryForeground: getComputedStyle(root).color,
              };
              root.remove();
              return result;
            }""")
            assert dialog_colors["dialogBackground"] == dialog_colors["cardBackground"], dialog_colors
            assert dialog_colors["buttonBackground"] == dialog_colors["primaryBackground"], dialog_colors
            assert dialog_colors["buttonForeground"] == dialog_colors["primaryForeground"], dialog_colors
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

print("BroadcastGab identity passed across the AVTrack workspace and inventory dialog.")
