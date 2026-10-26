"""Shared desktop navigation through the workspace menu."""
def open_workspace(page, tab):
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
