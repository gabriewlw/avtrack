"""Shared desktop navigation through the workspace menu."""
def open_workspace(page, tab):
    toggle=page.locator('#nav-toggle')
    if toggle.is_visible() and toggle.get_attribute('aria-expanded')=='false':
        toggle.click()
    menu = page.locator('#workspaces-menu')
    if not menu.evaluate('(node)=>node.open'):
        page.locator('#workspaces-toggle').click()
    page.locator('#'+tab).click()

def continue_uploaded_import(page):
    """Use the current shared import workspace before entering row review."""
    page.locator('#paste-layout-dialog:visible, #spreadsheet-dialog:visible').first.wait_for()
    if page.locator('#paste-layout-dialog').is_visible():
        page.wait_for_function("()=>!document.getElementById('keep-paste-layout').disabled")
        if page.locator('#keep-paste-layout').is_visible():
            page.locator('#keep-paste-layout').click()
        else:
            # IPTV uses its dedicated main-column preview, with direct Review.
            page.locator('#paste-start-review').click()
            page.locator('#inventory-import-review').wait_for(state='visible')
            return
    page.locator('#spreadsheet-dialog').wait_for(state='visible')
    page.wait_for_function("()=>!document.getElementById('confirm-import').disabled")
    # Review rather than auto-import, so the browser can exercise row actions.
    if page.locator('#import-complete-rows').is_visible():
        page.locator('#import-complete-rows').uncheck()

def open_import_settings(page):
    panel=page.locator('.import-advanced:visible').first
    if panel.count() and not panel.evaluate('(node)=>node.open'):
        panel.locator('summary').click()

def set_import_confirmation(page, mode):
    open_import_settings(page)
    control=page.locator('#paste-preview-confirmation:visible, #import-confirmation-choice:visible').first
    control.select_option(mode)

def open_import_matching(page):
    """Keep the simple IPTV preview; other tables offer Advanced matching."""
    page.locator('#paste-layout-dialog:visible, #spreadsheet-dialog:visible').first.wait_for()
    if page.locator('#paste-layout-dialog').is_visible() and page.locator('#keep-paste-layout').is_visible():
        page.locator('#keep-paste-layout').click()

def start_import_review(page):
    if page.locator('#inventory-import-review').is_visible():
        return
    page.locator('#paste-start-review:visible, #confirm-import:visible').first.click()

def choose_new_inventory_import(page):
    page.locator('#inventory-start-dialog').wait_for(state='visible')
    page.locator('#inventory-start-import').click()
    page.locator('#paste-inventory-dialog').wait_for(state='visible')
