"""Shared desktop navigation through the workspace menu."""
def open_workspace(page, tab):
    menu = page.locator('#workspaces-menu')
    if not menu.evaluate('(node)=>node.open'):
        page.locator('#workspaces-toggle').click()
    page.locator('#'+tab).click()
