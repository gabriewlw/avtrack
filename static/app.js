'use strict';
const $ = id => document.getElementById(id);
const formatFileSize = size => size < 1024 ? `${size} B` : size < 1024 * 1024 ? `${(size / 1024).toFixed(size < 10240 ? 1 : 0)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`;
const navToggle = $('nav-toggle');
const mainNavigation = $('main-navigation');
const header = navToggle.closest('.header-inner');
const mobileNavigation = window.matchMedia('(max-width: 639.98px)');
function setNavigationOpen(open, restoreFocus = false) {
  header.classList.toggle('menu-open', open);
  navToggle.setAttribute('aria-expanded', String(open));
  navToggle.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
  if (restoreFocus && mobileNavigation.matches) navToggle.focus();
}
navToggle.addEventListener('click', () => setNavigationOpen(navToggle.getAttribute('aria-expanded') !== 'true'));
mainNavigation.addEventListener('click', event => {
  if (event.target.closest('a')) setNavigationOpen(false, true);
});
document.addEventListener('pointerdown', event => {
  if (!header.contains(event.target)) setNavigationOpen(false, mainNavigation.contains(document.activeElement));
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && navToggle.getAttribute('aria-expanded') === 'true') {
    event.preventDefault();
    setNavigationOpen(false, true);
  }
});
header.addEventListener('focusout', event => {
  if (event.relatedTarget && !header.contains(event.relatedTarget)) setNavigationOpen(false);
});
mobileNavigation.addEventListener('change', () => setNavigationOpen(false, mainNavigation.contains(document.activeElement)));
let devices = [], editing = null, deleting = null, timer, currentTab = 'device';
let equipmentPageSummary = null;
let networkLoaded = false;
let overviewVersion = 0;
let overviewSnapshot;
const onHomeRoute = () => location.pathname === '/' && !location.hash;
function syncHomePresentation() {
  const home = onHomeRoute();
  const waiting = home && overviewSnapshot === undefined;
  const empty = home && overviewSnapshot && (overviewSnapshot.av_total + overviewSnapshot.iptv_total + overviewSnapshot.inventory_total === 0);
  document.body.classList.toggle('home-data-pending', waiting);
  document.body.classList.toggle('home-empty-workspace', Boolean(empty));
  $('home-empty-state').hidden = !empty;
}
async function loadOverview() {
  const version = ++overviewVersion;
  try {
    const totals = await api('/api/overview');
    if (version !== overviewVersion) return;
    $('overview-av-validated').textContent = totals.av_validated;
    $('overview-av-caption').textContent = totals.av_validated === 1 ? 'IP validated' : 'IPs validated';
    $('overview-av-total').textContent = `${totals.av_validated} of ${totals.av_total} ${totals.av_total === 1 ? 'device' : 'devices'}`;
    $('overview-iptv-total').textContent = totals.iptv_total;
    $('overview-iptv-caption').textContent = totals.iptv_total === 1 ? 'channel running' : 'channels running';
    $('overview-iptv-sources').textContent = `${totals.iptv_onboard} onboard · ${totals.iptv_satellite} satellite`;
    $('overview-inventory-total').textContent = totals.inventory_total;
    $('overview-inventory-locations').textContent = `${totals.inventory_total === 1 ? 'item' : 'items'} across ${totals.inventory_locations} ${totals.inventory_locations === 1 ? 'location' : 'locations'}`;
    $('overview-inventory-count').textContent = `${totals.inventory_count} ${totals.inventory_count === 1 ? 'inventory' : 'inventories'}`;
    $('overview-backup-total').textContent = totals.backup_total;
    $('overview-backup-caption').textContent = totals.backup_total === 1 ? 'configuration file saved' : 'configuration files saved';
    $('overview-backup-size').textContent = `${totals.backup_total} ${totals.backup_total === 1 ? 'file' : 'files'} · ${formatFileSize(totals.backup_size)}`;
    overviewSnapshot = totals;
    syncHomePresentation();
    $('overview-error').hidden = true;
  } catch (error) {
    if (version !== overviewVersion) return;
    for (const id of ['overview-av-validated','overview-iptv-total','overview-inventory-total','overview-backup-total']) $(id).textContent = '—';
    for (const id of ['overview-av-total','overview-iptv-sources','overview-inventory-count','overview-backup-size']) $(id).textContent='Unavailable — use Refresh to retry';
    overviewSnapshot = null;
    syncHomePresentation();
    $('overview-error').textContent = 'Could not refresh the workspace overview. '+error.message;
    $('overview-error').hidden = false;
  }
}
function updatePageSummary(equipmentItems, inventoryName, profile = {}) {
  if (equipmentItems) equipmentPageSummary = {count:equipmentItems.length, locations:new Set(equipmentItems.map(item => item.location).filter(Boolean)).size, name:inventoryName,storage:profile.location_role!=='geographic'&&profile.location_role!=='none'&&!inventoryName?.toLowerCase().includes('scala')};
  $('workspace-page-title').textContent = currentTab === 'backups' ? 'AV Backups' : currentTab === 'equipment' ? `Inventory${equipmentPageSummary ? ' · ' + equipmentPageSummary.name : ''}` : currentTab === 'iptv' ? 'IPTV' : 'AV Devices';
  if (currentTab === 'backups') {
    $('workspace-page-summary').textContent = 'Configuration files ready for recovery';
  } else if (currentTab === 'equipment') {
    $('workspace-page-summary').textContent = equipmentPageSummary
      ? `${equipmentPageSummary.count} ${equipmentPageSummary.count === 1 ? 'item' : 'items'}${equipmentPageSummary.storage ? ` across ${equipmentPageSummary.locations} ${equipmentPageSummary.locations === 1 ? 'location' : 'locations'}` : ''}`
      : 'Loading inventory…';
  } else if (!networkLoaded) {
    $('workspace-page-summary').textContent = currentTab === 'iptv' ? 'Loading IPTV channels…' : 'Loading AV devices…';
  } else if (currentTab === 'iptv') {
    const count = devices.filter(item => item.record_type === 'iptv').length;
    $('workspace-page-summary').textContent = `${count} ${count === 1 ? 'channel' : 'channels'} running`;
  } else {
    const count = devices.filter(item => (item.record_type || 'device') === 'device' && item.ip_confirmed && item.ip && !isDHCP(item.ip)).length;
    $('workspace-page-summary').textContent = `${count} ${count === 1 ? 'IP' : 'IPs'} validated`;
  }
}
let visibleDevices = [];
const networkSelections = {device:new Set(), iptv:new Set()};
let batchDeletingIds = [];
let importWarnings = [];
const pendingNoteSaves = new Map();
const pendingWrites = new Set();
const tabSortOrders = {device: '', iptv: ''};
const nameCollator = new Intl.Collator(undefined, {sensitivity: 'base', numeric: true});
const tabDevices = () => devices.filter(d => (d.record_type || 'device') === currentTab);
const form = $('device-form');
const filters = ['search', 'venue-filter', 'system-filter', 'source-filter', 'address-filter'];
const element = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const systems = ['Video', 'Audio', 'Lighting', 'Control', 'Network', 'Other'];
const deviceLabel = device => device.name || `record ${device.id}`;
const isDHCP = value => value.trim().toUpperCase() === 'DHCP';
function compareDirectoryRecords(a, b, order) {
  const [field, direction] = order.split('-');
  const sign = direction === 'desc' ? -1 : 1;
  let comparison = 0;
  if (field === 'ip') {
    const number = ip => /^(?:\d{1,3}\.){3}\d{1,3}$/.test(ip) && ip.split('.').every(octet => Number(octet) <= 255)
      ? ip.split('.').reduce((value, octet) => value * 256 + Number(octet), 0) : null;
    const left = number(a.ip), right = number(b.ip);
    // Static IPv4 addresses first, DHCP next, blank addresses last in either direction.
    const group = (record, value) => value !== null ? 0 : isDHCP(record.ip) ? 1 : 2;
    const grouping = group(a, left) - group(b, right);
    if (grouping) return grouping;
    if (left !== null && right !== null) comparison = left - right;
  } else {
    const key = field === 'system' ? (currentTab === 'iptv' ? 'channel_source' : 'discipline') : 'name';
    const left = (a[key] || '').trim(), right = (b[key] || '').trim();
    if (!left !== !right) return left ? -1 : 1;
    comparison = nameCollator.compare(left, right);
  }
  return comparison * sign || nameCollator.compare(a.name, b.name) || a.id - b.id;
}

let activeSystemMenu = null;
function closeSystemMenu(restoreFocus = false) {
  if (!activeSystemMenu) return;
  const {menu, button} = activeSystemMenu;
  activeSystemMenu = null; menu.remove(); button.setAttribute('aria-expanded', 'false');
  if (restoreFocus) button.focus();
}
document.addEventListener('pointerdown', event => {
  if (activeSystemMenu && !activeSystemMenu.menu.contains(event.target) && !activeSystemMenu.button.contains(event.target)) closeSystemMenu();
});
window.addEventListener('resize', () => activeSystemMenu?.position());
document.addEventListener('scroll', event => {
  if (activeSystemMenu && !activeSystemMenu.menu.contains(event.target)) activeSystemMenu.position();
}, true);
function systemDropdown(device) {
  const button = element('button', 'system-select system-tag');
  button.type = 'button'; button.dataset.value = device.discipline;
  button.setAttribute('role', 'combobox');
  button.setAttribute('aria-label', `System for ${deviceLabel(device)}`);
  button.setAttribute('aria-haspopup', 'listbox'); button.setAttribute('aria-expanded', 'false');
  button.setAttribute('aria-controls', `system-menu-${device.id}`);
  const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  arrow.classList.add('system-arrow'); arrow.setAttribute('viewBox', '0 0 12 12');
  arrow.setAttribute('aria-hidden', 'true'); arrow.setAttribute('focusable', 'false');
  const chevron = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  chevron.setAttribute('d', 'M3 4.5 6 7.5 9 4.5'); arrow.append(chevron);
  button.append(element('span', '', device.discipline), arrow);
  const open = (last = false) => {
    closeSystemMenu();
    const menu = element('div', 'system-options'); menu.id = `system-menu-${device.id}`;
    menu.setAttribute('role', 'listbox'); menu.setAttribute('aria-label', `Choose system for ${deviceLabel(device)}`);
    const choices = ['', ...systems].map(value => {
      const option = element('button', 'system-option system-tag', value || 'Clear system');
      option.type = 'button'; option.dataset.value = value; option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', String(value === device.discipline));
      option.onclick = async () => {
        closeSystemMenu(true); button.disabled = true;
        try {
          const updated = await api(`/api/devices/${device.id}/system`, 'POST', {discipline:value});
          devices = devices.map(row => row.id === updated.id ? {...row,discipline:updated.discipline} : row);
          updateFilterOptions(); render();
          document.querySelector(`.system-select[aria-controls="system-menu-${device.id}"]`)?.focus();
        } catch(error) { button.disabled = false; toast('Could not save system: ' + error.message); }
      };
      return option;
    });
    menu.append(...choices); document.body.append(menu);
    const position = () => {
      const rect = button.getBoundingClientRect(), width = Math.min(190, window.innerWidth - 16);
      menu.style.width = `${width}px`;
      menu.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))}px`;
      const height = Math.min(menu.scrollHeight, window.innerHeight - 16);
      menu.style.top = `${Math.max(8, rect.bottom + height + 8 <= window.innerHeight ? rect.bottom + 4 : rect.top - height - 4)}px`;
      menu.style.maxHeight = `${window.innerHeight - 16}px`;
    };
    activeSystemMenu = {menu, button, position}; position(); button.setAttribute('aria-expanded', 'true');
    const selected = choices.find(option => option.dataset.value === device.discipline);
    (last ? choices.at(-1) : selected || choices[0]).focus();
    menu.onkeydown = event => {
      const index = choices.indexOf(document.activeElement);
      if (event.key === 'Escape') { event.preventDefault(); closeSystemMenu(true); }
      else if (event.key === 'Tab') closeSystemMenu(true);
      else if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? choices.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : choices.length - 1)) % choices.length;
        choices[next].focus();
      }
    };
  };
  button.onclick = () => activeSystemMenu?.button === button ? closeSystemMenu() : open();
  button.onkeydown = event => {
    if (['ArrowDown','ArrowUp'].includes(event.key)) { event.preventDefault(); open(event.key === 'ArrowUp'); }
    else if (event.key === 'Escape') closeSystemMenu(true);
  };
  return button;
}
async function saveNotes(deviceId, notes) {
  const previous = pendingNoteSaves.get(deviceId) || Promise.resolve();
  const request = previous.catch(() => {}).then(() => api(`/api/devices/${deviceId}/notes`, 'POST', {notes}));
  pendingNoteSaves.set(deviceId, request);
  try { return await request; }
  finally { if (pendingNoteSaves.get(deviceId) === request) pendingNoteSaves.delete(deviceId); }
}
const cleanVenue = value => value.trim().replace(/^RD\s+/i, '').trim();
const venueColors = new Map();
const usedVenueColors = new Set();
function colorVenueButton(button, venue) {
  if (!venue) return;
  if (!venueColors.has(venue)) {
    let hash = 2166136261;
    for (const character of venue) hash = Math.imul(hash ^ character.codePointAt(0), 16777619) >>> 0;
    let hue = hash % 360;
    const saturation = 60 + (hash >>> 8) % 16, lightness = 65 + (hash >>> 16) % 10;
    let color = `hsl(${hue} ${saturation}% ${lightness}%)`;
    while (usedVenueColors.has(color)) {
      hue += 0.1;
      color = `hsl(${hue} ${saturation}% ${lightness}%)`;
    }
    venueColors.set(venue, color);
    usedVenueColors.add(color);
  }
  button.classList.add('venue-choice');
  button.style.setProperty('--venue-color', venueColors.get(venue));
}
// IDs preserve first appearance across imports even when the device list is sorted.
const savedVenues = () => [...new Set(tabDevices().slice().sort((a,b) => a.id-b.id).map(d => cleanVenue(d.venue)).filter(Boolean))];
function makeButtons(id, values, selected, onSelect, allLabel = null) {
  const choices = allLabel ? [['', allLabel], ...values.map(v => [v, v])] : values.map(v => [v, v]);
  $(id).replaceChildren(...choices.map(([value, label]) => {
    const button = element('button', 'choice-button', label);
    button.type = 'button';
    button.dataset.value = value;
    if (id === 'form-venue-buttons') colorVenueButton(button, value);
    button.setAttribute('aria-pressed', String(value === selected));
    button.onclick = () => onSelect(value);
    return button;
  }));
}
function syncButtons(id, value) {
  $(id).querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.value === value)));
}
function updateVenueFilter() {
  const venues = savedVenues();
  const selected = $('venue-filter').value;
  $('venue-filter').replaceChildren(new Option('All venues', ''), ...venues.map(venue => {
    const option = new Option(venue, venue);
    colorVenueButton(option, venue);
    return option;
  }));
  $('venue-filter').value = venues.includes(selected) ? selected : '';
}
makeButtons('system-buttons', systems, '', value => { $('system-filter').value = value; render(); }, 'All systems');
makeButtons('source-buttons', ['Onboard','Satellite'], '', value => { $('source-filter').value = value; render(); }, 'All sources');
makeButtons('address-buttons', ['DHCP'], '', value => { $('address-filter').value = value; render(); }, 'All addresses');
makeButtons('form-source-buttons', ['Onboard','Satellite'], '', value => { form.elements.channel_source.value = form.elements.channel_source.value === value ? '' : value; syncButtons('form-source-buttons', form.elements.channel_source.value); });
function updateFilterOptions() {
  updateVenueFilter();
  $('venues').replaceChildren(...savedVenues().map(v => new Option(v, v)));
}
function switchTab(type) {
  closeSystemMenu();
  closeExportMenus();
  currentTab = type;
  syncHomePresentation();
  $('homepage-overview').hidden = ['/inventory','/backups'].includes(location.pathname) || Boolean(location.hash);
  updatePageSummary();
  const equipment = type === 'equipment';
  const backups = type === 'backups';
  $('example-media').hidden = type === 'iptv';
  $('equipment-panel').hidden = !equipment;
  $('backups-panel').hidden = !backups;
  $('inventory').hidden = equipment || backups;
  document.querySelector('main > .stats').hidden = equipment || backups;
  $('add-device').hidden = backups;
  for (const [id, tab] of [['device-tab','device'], ['iptv-tab','iptv'], ['equipment-tab','equipment'], ['backups-tab','backups']]) {
    $(id).classList.toggle('nav-active', tab === type);
    if (tab === type) $(id).setAttribute('aria-current', 'page');
    else $(id).removeAttribute('aria-current');
  }
  if (backups) {
    $('hero-title').replaceChildren(document.createTextNode('Every setup.'), element('br'), document.createTextNode('Every recovery point.'), element('br'), element('span', '', 'Ready when needed.'));
    $('hero-intro').textContent = 'Save known-good configuration files for switchers, routers, satellite receivers, OBS systems, and other AV equipment in one searchable archive.';
    $('example-ip').textContent = 'ATEM 2 M/E'; $('example-name').textContent = 'Production Studio 4K';
    $('example-tags').replaceChildren(...['Configuration backup','Control room','Ready to restore'].map(text => element('span','',text)));
    $('validation-note').hidden = true;
    window.backupsUI?.load(); return;
  }
  $('add-device').hidden = false;
  if (equipment) {
    $('equipment-transfer').insertBefore($('add-device'), $('equipment-paste'));
    $('hero-title').replaceChildren(document.createTextNode('Every asset.'), element('br'), document.createTextNode('Every location.'), element('br'), element('span', '', 'One clear view.'));
    $('hero-intro').textContent = 'Manage your broadcast equipment, spare stock, and production tools. Keep brands, models, serial numbers, and quantities organized from the control room to the storeroom.';
    $('example-ip').textContent = 'Advanced Panel 10'; $('example-name').textContent = 'Blackmagic Design';
    $('example-tags').replaceChildren(...['Video control panel','Quantity 1','Broadcast center'].map(text => element('span','',text)));
    $('add-device').textContent = 'Add equipment'; $('validation-note').hidden = true;
    window.equipmentUI.load(); return;
  }
  $('transfer').insertBefore($('add-device'), $('network-paste'));
  filters.forEach(id => $(id).value = '');
  $('inventory').setAttribute('aria-labelledby', type === 'iptv' ? 'iptv-tab' : 'device-tab');
  const iptv = type === 'iptv';
  $('inventory').querySelectorAll('.export-links a[download]').forEach(link => {
    const url = new URL(link.href); url.searchParams.set('record_type', type); link.href = url.href;
    const extension = url.pathname.split('.').pop();
    link.download = `avtrack-${iptv ? 'iptv-channels' : 'av-devices'}.${['csv','xlsx','pdf'].includes(extension) ? extension : 'json'}`;
  });
  $('sort-order').value = tabSortOrders[type];
  for (const direction of ['asc', 'desc']) {
    $('sort-order').querySelector(`option[value="system-${direction}"]`).textContent = `${iptv ? 'Source' : 'System'} · ${direction === 'asc' ? 'A–Z' : 'Z–A'}`;
  }

  $('hero-title').replaceChildren(document.createTextNode(iptv ? 'Every channel.' : 'Every device.'), element('br'), document.createTextNode(iptv ? 'Every source.' : 'Every venue.'), element('br'), element('span', '', 'One clear view.'));
  $('hero-intro').textContent = iptv ? 'Keep your onboard and satellite channel lineup in view. Track stream addresses and ports, organize channels by source, and take your inventory from the control room to your phone.' : 'Manage your broadcast equipment, channel lineups, and AV connections. Keep your production workspace organized from the control room to your phone.';
  $('example-ip').textContent = iptv ? '239.1.1.10' : '10.24.176.67';
  $('example-name').textContent = iptv ? 'Ship information' : 'ATEM 1 M/E Advanced Panel 10';
  $('example-tags').replaceChildren(...(iptv ? ['Onboard', 'Port 1234'] : ['Liquid Lounge', 'Video', 'VLAN 1500']).map(text => element('span', '', text)));

  $('add-device').textContent = iptv ? 'Add channel' : 'Add device';
  $('empty-add').textContent = iptv ? 'Add a channel' : 'Add a device';
  $('empty-title').textContent = iptv ? 'Your channel lineup starts here' : 'Your inventory starts here';
  $('empty-description').textContent = iptv ? 'Add onboard and satellite channel addresses to your IPTV inventory.' : 'Add your first device to keep your ship’s AV network organized.';
  $('use-example').hidden = iptv;
  $('total-label').textContent = iptv ? 'Total channels' : 'Total devices';
  $('system-count-label').textContent = iptv ? 'Onboard / Satellite' : 'Video / Audio / Lighting';
  $('list-title').textContent = iptv ? 'IPTV channels' : 'AV Devices';
  $('search-label').textContent = iptv ? 'Search channels' : 'Search devices';
  $('clear-filters').hidden = iptv;
  $('network-filters').classList.toggle('iptv-filters', iptv);
  $('search').placeholder = iptv ? 'Channel, IP, port, or notes…' : 'Name, IP, venue, or notes…';
  $('system-filter-group').hidden = $('system-filter-label').hidden = iptv;
  $('source-filter-group').hidden = !iptv;
  for (const id of ['venue-filter-group','venue-stat','vlan-stat','validation-note']) $(id).hidden = iptv;
  document.querySelector('.stats').classList.toggle('iptv-stats', iptv);
  $('confirmation-legend').textContent = iptv ? 'Channel addresses and stream ports · Onboard / Satellite' : 'Yellow: awaiting confirmation · Green: reachability confirmed';
  updateFilterOptions(); render();
}
const inventoryTabs = [['device-tab','device'],['iptv-tab','iptv'],['equipment-tab','equipment'],['backups-tab','backups']];
function navigatePage(type) {
  const link = $(inventoryTabs.find(([,page]) => page === type)[0]);
  const destination = link.pathname + link.hash;
  if (location.pathname + location.hash !== destination) history.pushState(null, '', destination);
  switchTab(type);
}
function restorePage() {
  syncHomePresentation();
  $('homepage-overview').hidden = ['/inventory','/backups'].includes(location.pathname) || Boolean(location.hash);
  if (location.hash === '#equipment' || location.hash === '#inventory') history.replaceState(null, '', '/inventory');
  const page = location.pathname === '/inventory' ? inventoryTabs[2] : location.pathname === '/backups' ? inventoryTabs[3] : inventoryTabs.find(([id]) => $(id).hash && $(id).hash === location.hash) || (!location.hash ? inventoryTabs[0] : null);
  if (page && page[1] !== currentTab) switchTab(page[1]);
}
window.addEventListener('hashchange', restorePage);
window.addEventListener('popstate', restorePage);
window.addEventListener('DOMContentLoaded', restorePage);
document.querySelectorAll('.overview-workspace-link').forEach(link => {
  link.onclick = event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault(); navigatePage(link.dataset.page);
  };
});
async function openOverviewAdd(type) {
  navigatePage(type);
  if (type === 'equipment') {
    await window.equipmentUI.waitUntilReady();
    window.equipmentUI.open();
  } else if (type === 'backups') window.backupsUI.open();
  else $('add-device').click();
}
document.querySelectorAll('[data-add-page]').forEach(button => { button.onclick = () => openOverviewAdd(button.dataset.addPage).catch(error => toast(error.message)); });
for (const [id, type] of inventoryTabs) {
  $(id).onclick = event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault(); navigatePage(type);
  };
  $(id).onkeydown = event => {
    if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) {
      event.preventDefault();
      const index = inventoryTabs.findIndex(([,tab]) => tab === currentTab);
      const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? inventoryTabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : inventoryTabs.length - 1)) % inventoryTabs.length;
      const [nextId,next] = inventoryTabs[nextIndex]; navigatePage(next); $(nextId).focus();
    }
  };
}
function toast(message) {
  $('toast').textContent = message; $('toast').hidden = false;
  clearTimeout(timer); timer = setTimeout(() => { $('toast').hidden = true; }, 6000);
}
async function api(path, method = 'GET', body, timeoutMs = method === 'GET' ? 20000 : 60000) {
  const options = {method, headers: method==='GET'?{}:{'Content-Type':'application/json'}};
  if (body !== undefined) options.body = JSON.stringify(body);
  const request = (async () => {
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),timeoutMs);
    options.signal=controller.signal;
    try{
      const response=await fetch(path,options);
      const type=response.headers.get('Content-Type') || '';
      if(!type.includes('application/json')){
        if(response.status===401 || response.status===403 || response.redirected || location.hostname.endsWith('.app.github.dev'))throw new Error('GitHub sign-in may be required. Open Reload workspace below, complete sign-in, then try again.');
        throw new Error('The server returned a page instead of inventory data. Check the server address and reload.');
      }
      const data=await response.json();
      if(!response.ok)throw new Error(data.error || 'Request failed. Please try again.');
      return data;
    }catch(error){
      if(error.name==='AbortError')throw new Error(method==='GET'
        ? `The server did not respond within ${Math.round(timeoutMs/1000)} seconds. Check the running server or use Reload workspace below.`
        : `The server did not finish saving within ${Math.round(timeoutMs/1000)} seconds. Saved import rows are safe; try the action again.`);
      if(error instanceof TypeError && location.hostname.endsWith('.app.github.dev'))throw new Error('The Codespaces connection failed. Use Reload workspace below to renew sign-in and reload browser files.');
      throw error;
    }finally{clearTimeout(timeout);}
  })();
  if (method !== 'GET') pendingWrites.add(request);
  try { return await request; }
  finally { pendingWrites.delete(request); }
}
function closeExportMenus(restoreFocus = false) {
  document.querySelectorAll('.export-dropdown[open]').forEach(menu => {
    menu.open = false;
    if (restoreFocus && menu.contains(document.activeElement)) menu.querySelector('summary').focus();
  });
}
function updateExportScope(id, visible, selected, total) {
  const select = $(id);
  for (const [value, text] of [['filtered', `Current view · ${visible}`], ['selected', `Selected rows · ${selected}`], ['all', `All in this tab · ${total}`]]) {
    const option = select.querySelector(`option[value="${value}"]`);
    option.textContent = text;
    if (value === 'selected') option.disabled = !selected;
  }
  if (!selected && select.value === 'selected') select.value = 'filtered';
}
function selectionControl(id, name, selected, onChange) {
  const control = element('label', 'row-select-control');
  const checkbox = element('input', 'row-select');
  checkbox.type = 'checkbox'; checkbox.dataset.recordId = id;
  checkbox.checked = selected.has(id);
  checkbox.setAttribute('aria-label', `Select ${name}`);
  checkbox.onchange = () => {
    if (checkbox.checked) selected.add(id); else selected.delete(id);
    onChange();
  };
  control.append(checkbox);
  return control;
}
function updateNetworkSelection() {
  if (currentTab === 'equipment') return;
  const selected = networkSelections[currentTab];
  const check = $('select-visible-devices');
  const visibleSelected = visibleDevices.filter(row => selected.has(row.id)).length;
  check.disabled = !visibleDevices.length;
  check.checked = !!visibleDevices.length && visibleSelected === visibleDevices.length;
  check.indeterminate = visibleSelected > 0 && visibleSelected < visibleDevices.length;
  check.setAttribute('aria-label', `Select all visible ${currentTab === 'iptv' ? 'channels' : 'devices'}`);
  $('device-list').querySelectorAll('.row-select').forEach(checkbox => { checkbox.checked = selected.has(Number(checkbox.dataset.recordId)); });
  $('network-selection-summary').hidden = !selected.size;
  $('delete-selected-devices').disabled = !selected.size;
  $('network-selection-count').textContent = `${selected.size} selected`;
  updateExportScope('network-export-scope', visibleDevices.length, selected.size, tabDevices().length);
}
$('select-visible-devices').onchange = event => {
  const selected = networkSelections[currentTab];
  visibleDevices.forEach(row => event.target.checked ? selected.add(row.id) : selected.delete(row.id));
  if (selected.size) $('network-export-scope').value = 'selected';
  updateNetworkSelection();
};
$('clear-network-selection').onclick = () => { networkSelections[currentTab].clear(); updateNetworkSelection(); };
$('delete-selected-devices').onclick = () => {
  const selected = tabDevices().filter(row => networkSelections[currentTab].has(row.id));
  if (!selected.length) return;
  batchDeletingIds = selected.map(row => row.id);
  const hiddenCount = selected.filter(row => !visibleDevices.some(visible => visible.id === row.id)).length;
  const type = currentTab === 'iptv' ? 'channel' : 'device';
  $('batch-delete-title').textContent = `Delete ${selected.length} ${type}${selected.length === 1 ? '' : 's'}?`;
  $('batch-delete-description').textContent = `This permanently removes the selected records from the shared inventory.${hiddenCount ? ` ${hiddenCount} selected ${hiddenCount === 1 ? 'record is' : 'records are'} outside the current filters.` : ''}`;
  $('batch-delete-list').replaceChildren(...selected.map(row => element('li', '', [deviceLabel(row), row.venue, row.ip].filter(Boolean).join(' · '))));
  $('confirm-batch-delete').textContent = `Delete ${selected.length} ${type}${selected.length === 1 ? '' : 's'}`;
  $('batch-delete-error').hidden = true;
  $('batch-delete-dialog').showModal(); $('cancel-batch-delete').focus();
};
$('cancel-batch-delete').onclick = () => $('batch-delete-dialog').close();
$('confirm-batch-delete').onclick = async () => {
  const ids = [...batchDeletingIds];
  $('confirm-batch-delete').disabled = true;
  $('cancel-batch-delete').disabled = true;
  try {
    await Promise.allSettled([...pendingNoteSaves.values(), ...pendingWrites]);
    const result = await api('/api/devices/batch-delete', 'POST', {ids});
    for (const selected of Object.values(networkSelections)) ids.forEach(id => selected.delete(id));
    $('batch-delete-dialog').close(); toast(`${result.deleted} ${result.deleted === 1 ? 'record' : 'records'} deleted.`); await load();
  } catch(error) { $('batch-delete-error').textContent = error.message; $('batch-delete-error').hidden = false; }
  finally { $('confirm-batch-delete').disabled = false; $('cancel-batch-delete').disabled = false; }
};
$('batch-delete-dialog').addEventListener('cancel', event => {
  if ($('confirm-batch-delete').disabled) event.preventDefault();
});
document.querySelectorAll('.export-dropdown').forEach(menu => {
  menu.addEventListener('toggle', () => {
    if (menu.open) document.querySelectorAll('.export-dropdown').forEach(other => { if (other !== menu) other.open = false; });
  });
  menu.addEventListener('click', event => {
    if (event.target.closest('a[download]')) { menu.open = false; menu.querySelector('summary').focus(); }
  });
});
document.addEventListener('pointerdown', event => {
  if (!event.target.closest('.export-dropdown')) closeExportMenus();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && document.querySelector('.export-dropdown[open]')) {
    event.preventDefault(); closeExportMenus(true);
  }
});
document.querySelectorAll('.export-links a[download]').forEach(link => {
  link.addEventListener('click', async event => {
    event.preventDefault();
    if (link.getAttribute('aria-disabled') === 'true') return;
    link.setAttribute('aria-disabled', 'true');
    try {
      const equipment = link.closest('#equipment-panel') !== null;
      const exportInventory = equipment ? window.equipmentUI.currentInventory() : null;
      const recordType = currentTab;
      const scope = $(equipment ? 'equipment-export-scope' : 'network-export-scope').value;
      let exportRows = scope === 'selected' ? visibleDevices.filter(row => networkSelections[currentTab]?.has(row.id)) : visibleDevices;
      if (!equipment && scope === 'selected' && $('sort-order').value) exportRows.sort((a,b) => compareDirectoryRecords(a,b,$('sort-order').value));
      // A download immediately after a note edit must include that saved note.
      if (document.activeElement?.matches('.device-notes-editor')) document.activeElement.blur();
      await Promise.all([...pendingNoteSaves.values(), ...pendingWrites]);
      if (equipment) await window.equipmentUI.flush();
      if (equipment && window.equipmentUI.currentInventory().id !== exportInventory.id) throw new Error('The inventory changed. Choose the export again.');
      const equipmentExport = equipment ? window.equipmentUI.exportData(scope) : null;
      const ids = equipment ? equipmentExport.ids : exportRows.map(row => row.id);
      const payload = equipment ? {ids, inventory_id:equipmentExport.inventory_id} : {record_type:recordType, ...(scope === 'all' ? {} : {ids})};
      const exportURL = new URL(link.href);
      if (equipment && scope === 'all') exportURL.searchParams.set('inventory_id', equipmentExport.inventory_id);
      const response = await fetch(exportURL, equipment && scope === 'all' ? {} : {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
      });
      if (!response.ok) throw new Error((await response.json()).error || 'Could not export inventory.');
      const url = URL.createObjectURL(await response.blob());
      const download = element('a'); download.href = url;
      const extension = new URL(link.href).pathname.split('.').pop();
      let inventoryFilename = equipment ? equipmentExport.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'equipment' : '';
      if (equipment && equipmentExport.inventory_id === 1 && equipmentExport.name === 'Equipment inventory') inventoryFilename = 'equipment';
      download.download = `avtrack-${equipment ? inventoryFilename : recordType === 'iptv' ? 'iptv-channels' : 'av-devices'}.${['csv','xlsx','pdf'].includes(extension) ? extension : 'json'}`;
      document.body.append(download); download.click(); download.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch(error) { toast('Export failed: ' + error.message); }
    finally { link.removeAttribute('aria-disabled'); }
  });
});
function options(id, values) {
  const select = $(id), previous = select.value;
  while (select.options.length > 1) select.remove(1);
  [...new Set(values.filter(v => v !== null && v !== undefined && v !== ''))].sort((a,b) => typeof a === 'number' ? a-b : a.localeCompare(b)).forEach(value => select.add(new Option(value, value)));
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
}
async function load() {
  if (currentTab === 'equipment') return window.equipmentUI.load();
  $('refresh').disabled = true;
  const overview=loadOverview();
  try {
    devices = (await api('/api/devices')).devices;
    networkLoaded = true;
    $('load-error').hidden = true;
    updateFilterOptions();
    $('venues').replaceChildren(...savedVenues().map(v => new Option(v, v)));
    render();
    await overview;
    return true;
  } catch (error) {
    $('load-error').textContent = 'Could not refresh inventory. ' + error.message;
    $('load-error').hidden = false;
    return false;
  } finally { $('loading').hidden = true; $('refresh').disabled = false; }
}
const copyIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>';
function udpCell(device) {
  const cell = element('div', 'udp-cell');
  const field = element('div', 'udp-field');
  const input = element('input', 'udp-address');
  input.type = 'text'; input.readOnly = true; input.spellcheck = false;
  input.value = device.ip && !isDHCP(device.ip) && device.port ? `udp://@${device.ip}:${device.port}` : '';
  input.setAttribute('aria-label', `UDP address for ${deviceLabel(device)}`);
  input.onfocus = () => input.select();
  input.onclick = input.ondblclick = () => requestAnimationFrame(() => input.select());
  const copy = element('button', 'quiet udp-copy');
  copy.type = 'button'; copy.disabled = !input.value;
  copy.setAttribute('aria-label', `Copy UDP address for ${deviceLabel(device)}`);
  copy.title = 'Copy UDP address';
  copy.innerHTML = copyIcon;
  copy.onclick = async () => {
    try {
      await navigator.clipboard.writeText(input.value);
      toast('UDP address copied.');
    } catch {
      input.focus(); input.select();
      let copied = false;
      try { copied = document.execCommand('copy'); } catch {}
      toast(copied ? 'UDP address copied.' : 'UDP address selected. Copy it using your browser’s menu.');
    }
  };
  field.append(input, copy); cell.append(field); return cell;
}
function ipCopyButton(device, addressText) {
  const button = element('button', 'ip-copy'); button.type = 'button';
  button.title = 'Copy IP address';
  button.setAttribute('aria-label', `Copy IP address for ${deviceLabel(device)}`);
  button.innerHTML = copyIcon;
  button.onclick = async () => {
    let copied = false;
    try { await navigator.clipboard.writeText(device.ip); copied = true; } catch {}
    if (!copied) {
      const buffer = element('textarea', 'clipboard-copy-buffer');
      buffer.value = device.ip; buffer.readOnly = true;
      const previousFocus = document.activeElement;
      document.body.append(buffer);
      try {
        buffer.focus({preventScroll:true}); buffer.select();
        copied = document.execCommand('copy');
      } catch {} finally { buffer.remove(); previousFocus?.focus({preventScroll:true}); }
    }
    if (copied) toast('IP address copied.');
    else {
      const range = document.createRange(); range.selectNodeContents(addressText);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      toast('IP address selected. Use your browser’s Copy option.');
    }
  };
  return button;
}
function render() {
  if (currentTab === 'equipment' || currentTab === 'backups') return;
  closeSystemMenu();
  const iptvDirectory = currentTab === 'iptv';
  $('device-directory').classList.toggle('iptv-directory', iptvDirectory);
  $('directory-venue-title').hidden = iptvDirectory;
  $('directory-vlan-title').hidden = iptvDirectory;
  $('directory-udp-title').hidden = !iptvDirectory;
  $('directory-device-title').textContent = iptvDirectory ? 'CHANNEL' : 'DEVICE';
  $('directory-system-title').textContent = iptvDirectory ? 'SOURCE' : 'SYSTEM';
  $('venue-filter').classList.remove('venue-choice');
  $('venue-filter').style.removeProperty('--venue-color');
  colorVenueButton($('venue-filter'), $('venue-filter').value);
  syncButtons('system-buttons', $('system-filter').value);
  syncButtons('source-buttons', $('source-filter').value);
  syncButtons('address-buttons', $('address-filter').value);
  updatePageSummary();
  const current = tabDevices();
  const selected = networkSelections[currentTab];
  const hasDHCP = currentTab === 'device' && current.some(d => isDHCP(d.ip));
  $('address-filter-group').hidden = !hasDHCP;
  if (!hasDHCP) $('address-filter').value = '';
  $('total').textContent = current.length;
  $('venue-count').textContent = savedVenues().length;
  $('vlan-count').textContent = new Set(current.map(d => d.vlan).filter(v => v !== null)).size;
  $('system-count').textContent = (currentTab === 'iptv' ? ['Onboard','Satellite'].map(source => current.filter(d => d.channel_source === source).length) : ['Video','Audio','Lighting'].map(system => current.filter(d => d.discipline === system).length)).join(' / ');
  const query = $('search').value.trim().toLowerCase();
  const results = current.filter(d =>
    [d.name,d.ip,d.venue,d.category,d.discipline,d.notes,d.channel_source || '',String(d.vlan || ''), String(d.port || '')].some(v => v.toLowerCase().includes(query)) &&
    (!$('venue-filter').value || cleanVenue(d.venue) === $('venue-filter').value) &&
    (!$('system-filter').value || d.discipline === $('system-filter').value) &&
    (!$('source-filter').value || d.channel_source === $('source-filter').value) &&
    (!$('address-filter').value || isDHCP(d.ip)));
  if ($('sort-order').value) results.sort((a, b) => compareDirectoryRecords(a, b, $('sort-order').value));
  visibleDevices = results;
  const visibleIds = new Set(results.map(row => row.id));
  for (const id of selected) if (!visibleIds.has(id)) selected.delete(id);
  $('result-count').textContent = results.length;
  $('showing').textContent = `${results.length} of ${current.length} ${currentTab === 'iptv' ? 'channels' : 'devices'}`;
  $('empty').hidden = current.length > 0;
  $('no-results').hidden = current.length === 0 || results.length > 0;
  const rows = results.map(device => {
    const row = element('article', 'device-row');
    const identity = element('div', 'device-identity identity-cell');
    identity.append(selectionControl(device.id, deviceLabel(device), selected, () => {
      if (selected.size) $('network-export-scope').value = 'selected';
      updateNetworkSelection();
    }));
    const title = element('div');
    const name = element('div', 'device-name');
    const channel = device.record_type === 'iptv' ? satelliteChannelForName(device.name) : null;
    if (channel?.logo) {
      name.classList.add('channel-name');
      const logo = element('img', 'channel-logo');
      logo.src = channel.logo; logo.alt = ''; logo.loading = 'lazy';
      logo.onerror = () => logo.remove();
      name.append(element('span', '', device.name), logo);
    } else name.textContent = device.name;
    title.append(name, element('span', 'device-category', device.category));
    const notes = element('textarea', 'device-notes-editor');
    notes.rows = 1; notes.maxLength = 2000; notes.value = device.notes;
    notes.dataset.deviceId = device.id;
    notes.setAttribute('aria-label', `Notes for ${deviceLabel(device)}`);
    notes.title = 'Notes save when you leave this field.';
    notes.onchange = async () => {
      const draft = notes.value;
      const previous = devices.find(row => row.id === device.id)?.notes || '';
      devices = devices.map(row => row.id === device.id ? {...row,notes:draft} : row);
      try {
        const updated = await saveNotes(device.id, draft);
        // Keep the current field and focus; update only notes in case another edit ran too.
        devices = devices.map(row => row.id === updated.id && row.notes === draft ? {...row,notes:updated.notes} : row);
        const currentField = document.querySelector(`.device-notes-editor[data-device-id="${device.id}"]`);
        if (currentField?.value === draft) currentField.value = updated.notes;
      } catch(error) {
        devices = devices.map(row => row.id === device.id && row.notes === draft ? {...row,notes:previous} : row);
        toast('Could not save notes: ' + error.message);
      }
    };
    const notesCell = element('div', 'notes-cell');
    notesCell.append(notes);
    identity.append(title);
    const ip = element('div', 'ip-cell');
    const iptv = device.record_type === 'iptv';
    if (iptv) row.classList.add('iptv-row');
    const ipLine = element('div', 'ip-info-line');
    const address = element('div', 'ip-address-value');
    const addressText = element('div', 'device-ip', device.ip);
    address.append(addressText);
    if (device.ip && !isDHCP(device.ip)) address.append(ipCopyButton(device, addressText));
    ipLine.append(address);
    ip.append(ipLine, element('span', 'cell-caption', iptv ? (device.port ? `Port ${device.port}` : '') : ''));
    const confirmation = element('button', `ip-confirm ${device.ip_confirmed ? 'confirmed' : 'pending'}`, device.ip_confirmed ? '✓ IP confirmed' : '● Confirm IP');
    confirmation.type = 'button';
    confirmation.disabled = Boolean(device.ip_confirmed);
    confirmation.setAttribute('aria-label', `${device.ip_confirmed ? 'IP confirmed for' : 'Confirm IP for'} ${deviceLabel(device)}`);
    confirmation.title = device.ip_confirmed ? 'Network reachability confirmed by you.' : 'Click after verifying that this device is reachable on the network.';
    confirmation.onclick = async () => {
      confirmation.disabled = true;
      try {
        const updated = await api(`/api/devices/${device.id}/confirm`, 'POST', {ip:device.ip, vlan:device.vlan,port:device.port});
        devices = devices.map(row => row.id === updated.id ? {...row,ip_confirmed:updated.ip_confirmed} : row);
        render(); toast('IP assignment confirmed.'); await loadOverview();
      } catch(error) { confirmation.disabled = false; toast('Confirmation failed: ' + error.message); }
    };
    if (device.confirmation_required !== 0 && device.ip && !isDHCP(device.ip)) ipLine.append(confirmation);
    const venue = element('div', 'venue-cell');
    const venueName = cleanVenue(device.venue);
    const venueLabel = element(venueName ? 'button' : 'div', 'device-venue', venueName);
    if (venueName) {
      venueLabel.type = 'button'; venueLabel.classList.add('choice-button');
      colorVenueButton(venueLabel, venueName);
      venueLabel.setAttribute('aria-label', `Filter venue ${venueName}`);
      venueLabel.onclick = () => { $('venue-filter').value = venueName; render(); };
    }
    venue.append(venueLabel);
    const system = element('div','system-cell');
    if (iptv) {
      if (device.channel_source) system.append(element('span', `badge ${device.discipline.toLowerCase()}`, device.channel_source));
    } else {
      system.append(systemDropdown(device));
    }
    const actions = element('div', 'row-actions');
    const edit = element('button', 'quiet row-action-icon row-edit-action');
    edit.type = 'button'; edit.title = iptv ? 'Edit channel' : 'Edit device'; edit.setAttribute('aria-label', `Edit ${deviceLabel(device)}`);
    edit.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m15.5 4.5 4 4L8 20H4v-4Z"/><path d="m13.5 6.5 4 4"/></svg>';
    edit.onclick = () => openForm(device);
    const remove = element('button', 'quiet row-action-icon row-delete-action');
    remove.type = 'button'; remove.title = iptv ? 'Delete channel' : 'Delete device'; remove.setAttribute('aria-label', `Delete ${deviceLabel(device)}`);
    remove.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5M14 11v5"/></svg>';
    remove.onclick = () => { deleting = device; $('delete-description').textContent = `${device.name} · ${device.ip} · ${iptv ? 'Port ' + (device.port || 'not set') : 'VLAN ' + device.vlan}`; $('delete-error').hidden = true; $('delete-dialog').showModal(); $('cancel-delete').focus(); };
    actions.append(edit,remove);
    row.append(identity);
    if (!iptv) row.append(venue);
    row.append(ip);
    if (iptv) row.append(udpCell(device));
    if (!iptv) row.append(element('div', 'vlan-cell', device.vlan ?? ''));
    row.append(system,notesCell,actions); return row;
  });
  $('device-list').replaceChildren(...rows);
  updateNetworkSelection();
  renderImportWarnings();
}
function renderImportWarnings() {
  const duplicates = new Map();
  devices.filter(d => (d.record_type || 'device') === 'device' && d.ip && !isDHCP(d.ip)).forEach(d => {
    if (!duplicates.has(d.ip)) duplicates.set(d.ip, []);
    duplicates.get(d.ip).push(d.name);
  });
  const warnings = [...importWarnings, ...[...duplicates].filter(([, names]) => names.length > 1).map(([ip, names]) => `Duplicate IP ${ip} in existing inventory: ${names.join(', ')}. Edit or remove the repeated assignments.`)];
  $('import-warnings').hidden = currentTab !== 'device' || !warnings.length;
  $('import-warning-list').replaceChildren(...warnings.map(message => element('li', '', message)));
}
function openForm(device = null) {
  if (device?.id) device = devices.find(row => row.id === device.id) || device;
  editing = device?.id ?? null;
  form.reset(); $('form-error').hidden = true;
  const iptv = currentTab === 'iptv';
  form.elements.record_type.value = currentTab;
  $('category-field').hidden = iptv;
  $('form-system-group').hidden = iptv;
  $('form-source-group').hidden = !iptv;
  $('venue-field').hidden = $('vlan-field').hidden = iptv;
  form.elements.venue.disabled = form.elements.vlan.disabled = iptv;
  $('port-field').hidden = !iptv;
  form.elements.port.required = false; form.elements.port.disabled = !iptv;
  $('name-label').textContent = iptv ? 'Channel name' : 'Device name';
  $('form-intro').textContent = iptv ? 'Track the channel’s stream address, port, and source.' : 'Give this device a home in your inventory.';
  form.elements.name.placeholder = iptv ? 'e.g. Ship information or BBC News' : 'e.g. ATEM video switcher';
  form.elements.ip.placeholder = iptv ? 'e.g. 239.1.1.10' : '10.24.176.66 or DHCP';
  $('ip-hint').textContent = iptv ? 'IPv4 unicast or multicast' : 'IPv4 or DHCP · checked when saved';
  $('form-title').textContent = editing ? (iptv ? 'Edit channel' : 'Edit device') : (iptv ? 'Add channel' : 'Add device');
  $('save-device').textContent = editing ? 'Save changes' : (iptv ? 'Save channel' : 'Save device');
  if (device) for (const field of ['name','category','venue','discipline','ip','vlan','notes','channel_source','port']) form.elements[field].value = device[field] ?? '';
  syncButtons('form-source-buttons', form.elements.channel_source.value);
  form.elements.venue.value = cleanVenue(form.elements.venue.value);
  const venues = savedVenues();
  $('venue-suggestions').hidden = iptv || !venues.length;
  makeButtons('form-venue-buttons', venues, form.elements.venue.value, value => { form.elements.venue.value = value; syncButtons('form-venue-buttons', value); });
  $('device-dialog').showModal();
}
form.elements.venue.addEventListener('input', () => syncButtons('form-venue-buttons', form.elements.venue.value));
$('add-device').onclick = () => currentTab === 'equipment' ? window.equipmentUI.open() : openForm();
$('empty-add').onclick = () => openForm();
$('use-example').onclick = () => openForm({name:'ATEM video switcher', category:'Video switcher', venue:'Liquid Lounge', discipline:'Video', ip:'10.24.176.66', vlan:1500, notes:''});
for (const id of ['close-dialog','cancel-dialog']) $(id).onclick = () => $('device-dialog').close();
for (const id of filters) $(id).addEventListener(id === 'search' ? 'input' : 'change', render);
$('sort-order').onchange = () => { tabSortOrders[currentTab] = $('sort-order').value; render(); };
$('clear-filters').onclick = () => { filters.forEach(id => $(id).value = ''); render(); };
$('refresh').onclick = load;
form.onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  $('save-device').disabled = true; $('form-error').hidden = true;
  try {
    // Finish any inline note save before submitting newer changes from Edit.
    if (editing && pendingNoteSaves.has(editing)) await pendingNoteSaves.get(editing).catch(() => {});
    await api(editing ? `/api/devices/${editing}` : '/api/devices', editing ? 'PUT' : 'POST', data);
    $('device-dialog').close();
    toast(editing ? 'Record updated.' : currentTab === 'iptv' ? 'Channel added to IPTV inventory.' : 'Device added to inventory.');
    await load();
  } catch (error) { $('form-error').textContent = error.message; $('form-error').hidden = false; }
  finally { $('save-device').disabled = false; }
};
$('cancel-delete').onclick = () => $('delete-dialog').close();
$('confirm-delete').onclick = async () => {
  $('confirm-delete').disabled = true;
  try { await api(`/api/devices/${deleting.id}`, 'DELETE', {}); $('delete-dialog').close(); toast('Device deleted.'); await load(); }
  catch(error) { $('delete-error').textContent = error.message; $('delete-error').hidden = false; }
  finally { $('confirm-delete').disabled = false; }
};
let spreadsheetFile = null, spreadsheetData = null;
let spreadsheetInventory = null;
let spreadsheetReviewing = false, stopSpreadsheetReview = false;
let venueEdits = new Map();
const skippedImportLocations = new Set();
const networkImportFields = [
  ['venue', 'Venue', ['venue','location','venue location','room','area']],
  ['name', 'Device name', ['device name','name','device','equipment','equipment name','hostname','channel','channel name']],
  ['ip', 'IP address', ['ip address','ip adress','ip','ipaddress','ipadress','ipv4','ipv4 address']],
  ['vlan', 'VLAN (optional)', ['vlan','vlan id','vlan number']],
  ['category', 'Category', ['category','device category','device type','type','model']],
  ['discipline', 'System', ['discipline','system','department','av system','function']],
  ['notes', 'Notes (optional)', ['notes','note','comments','description']],
  ['record_type', 'Inventory type', ['record type','inventory type']],
  ['channel_source', 'Channel source (IPTV)', ['channel source','source','onboard or satellite']],
  ['port', 'Port (IPTV)', ['port','udp port','stream port','port number']]
];
const equipmentCheckFields = ['description','brand','model','serial_number','quantity','location'];
const splitEquipmentSerials = value => String(value || '').split(/[\r\n,|;]+/).map(part=>part.replace(/\s+/g,'')).filter(Boolean);
const uniqueEquipmentSerials = value => {
  const seen=new Set();
  return splitEquipmentSerials(value).filter(serial=>{
    const key=serial.toLowerCase();
    if(seen.has(key))return false;
    seen.add(key);
    return true;
  });
};
const serialKey = value => uniqueEquipmentSerials(value).map(serial=>serial.toLowerCase()).join(',');
function equipmentIssues(row,profile=window.equipmentUI?.profile() || defaultInventoryLayout) {
  const important=profile.columns.filter(col=>col.important&&col.key!=='orientation');
  const issues=[...(row.source_issues || []),...important.filter(col=>String(inventoryValue(row,col.key)).trim()==='').map(col=>`Missing ${col.label}`)];

  profile.columns.filter(col=>['select','buttons'].includes(col.type)&&!col.allow_custom).forEach(col=>{const value=String(inventoryValue(row,col.key));if(value&&!col.options.some(option=>option.toLowerCase()===value.toLowerCase()))issues.push(`Check ${col.label}: ${value}`);});
  profile.columns.filter(col=>col.type==='count').forEach(col=>{const value=String(inventoryValue(row,col.key)).trim();if(value&&(!/^\d+$/.test(value)||Number(value)<(col.minimum ?? 1)||Number(value)>50))issues.push(`Check ${col.label}: choose ${(col.minimum ?? 1)}–50`);});
  const stockFields=new Set(profile.columns.map(col=>col.key));
  if(stockFields.has('serial_number')&&stockFields.has('quantity')){
    const serials=splitEquipmentSerials(row.serial_number);
    const uniqueSerials=uniqueEquipmentSerials(row.serial_number);
    const quantity=Number(row.quantity);
    if(serials.length!==uniqueSerials.length)issues.push('Duplicate serial numbers in one record');
    if(Number.isInteger(quantity)&&quantity>=0&&uniqueSerials.length!==quantity){
      issues.push(`Serial count ${uniqueSerials.length} does not match quantity ${quantity}`);
    }
  }
  if (/separate inventory|not an itemized|reference to/i.test(row.notes || '')) issues.push('Inventory reference: check itemized source');
  return issues;
}
function orderEquipmentReview(entries) {
  const serialCounts = new Map();
  const profile=spreadsheetInventory?.layout || window.equipmentUI?.profile()||defaultInventoryLayout;const identifierCounts=new Map();
  const rowIdentifier=row=>profile.stock_mode==='tv_counts'&&row.brand&&row.model?JSON.stringify([row.brand.trim().toLowerCase(),row.model.trim().toLowerCase()]):profile.identifier?String(inventoryValue(row,profile.identifier)).trim().toLowerCase():'';
  entries.forEach(({row}) => { const key = serialKey(row.serial_number); if (key) serialCounts.set(key, (serialCounts.get(key) || 0) + 1); });
  entries.forEach(({row})=>{const value=rowIdentifier(row);if(value)identifierCounts.set(value,(identifierCounts.get(value)||0)+1);});
  const groups = new Map(),locationCounts=new Map();
  entries.forEach(({row})=>{const location=(row.location||'').trim();if(location)locationCounts.set(location,(locationCounts.get(location)||0)+1);});
  entries.forEach(entry => {
    entry.issues = equipmentIssues(entry.row,profile);
    profile.columns.filter(col=>col.require_confirmation).forEach(col=>entry.issues.push(`Confirm ${col.label} during review`));
    if(identifierCounts.get(rowIdentifier(entry.row))>1)entry.issues.push('Repeated item identifier in this file');
    if (serialCounts.get(serialKey(entry.row.serial_number)) > 1) entry.issues.push('Repeated serial number in this file');
    const location = entry.row.location || '';
    if(location&&locationCounts.get(location)===1&&locationCounts.size>1)entry.issues.push('Unusual location: appears once in this paste');
    if (!groups.has(location)) groups.set(location, []);
    groups.get(location).push(entry);
  });
  const ordered = [];
  [...groups].sort((a,b)=>!a[0]-!b[0]||b[1].length-a[1].length).forEach(([location, rows], groupIndex) => {
    rows.sort((a,b) => Boolean(a.issues.length) - Boolean(b.issues.length));
    rows.forEach((entry,index) => { entry.locationProgress = `${location || 'Unassigned location'} · Location ${groupIndex + 1} of ${groups.size} · Item ${index + 1} of ${rows.length} · ${entry.issues.length ? 'Flagged rows' : 'Complete rows'}`; ordered.push(entry); });
  });
  return ordered;
}
const equipmentImportFields = [
  ['description','Item',['item','description','equipment','item name','item description']],
  ['brand','Brand',['brand','manufacturer','make']],
  ['model','Model',['model','model number','model no','model no.','model #','part number']],
  ['serial_number','Serial number (optional)',['serial number','serial','serial no','s/n','sn']],
  ['quantity','Quantity',['quantity','qty','count','stock','quantity in stock']],
  ['location','Location',['location','venue','room','storage','storage location']],
  ['item_confirmed','Status (optional)',['item confirmed','located','found','confirmed','confirmation']],
  ['notes','Notes (optional)',['notes','note','comments']]
];
const iptvImportFields = [
  ['name', 'Channel Name', ['channel name','channel','name']],
  ['ip', 'Multicast IP', ['mcast ip [s]','mcast ip','multicast ip','ip address','ip adress','ip','ipv4']],
  ['port', 'Port', ['mcast port [s]','mcast port','multicast port','port','udp port','stream port','port number']],
  ['notes', 'Notes (optional)', ['notes','note','comments','description']]
];
const normalizedChannelName = name => name.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const satelliteChannelAliases = new Map();
let satelliteCatalogError = null;
const satelliteCatalogReady = api('/satellite-channels.json').then(catalog => {
  if (catalog.version !== 1 || !Array.isArray(catalog.channels)) throw new Error('Invalid satellite channel reference.');
  for (const channel of catalog.channels) {
    for (const alias of [channel.name, ...channel.aliases]) satelliteChannelAliases.set(normalizedChannelName(alias), channel);
  }
}).catch(error => { satelliteCatalogError = error; }).then(()=>{if(networkLoaded)render();});
function satelliteChannelForName(name) {
  const channel = normalizedChannelName(name).replace(/(?:\s+(?:hd|sd|fhd|uhd|4k|1080p|720p))+$/, '');
  return satelliteChannelAliases.get(channel);
}
function channelSourceFromName(name) {
  const text = name.toLowerCase().replace(/\s+/g, ' ');
  if (['cltv','carnival','map','crew','scala','casino','safety'].some(keyword => text.includes(keyword))) return 'Onboard';
  if (satelliteChannelForName(name)) return 'Satellite';
  return '';
}
function channelCodecIPs(rows) {
  return new Set(rows.filter(row => row.record_type === 'iptv' && Number(row.port) === 2000 && importAddressKey(row)).map(row => row.ip.trim()));
}
function channelNotesWithCodec(row, codecIPs) {
  const notes = row.notes || '';
  const codec = Number(row.port) === 2000 ? 'H.264'
    : Number(row.port) === 1234 && importAddressKey(row) && codecIPs.has(row.ip.trim()) ? 'H.265' : '';
  if (!codec || new RegExp(`\\b${codec.replace('.', '\\.')}\\b`, 'i').test(notes)) return notes;
  return notes ? `${notes} · ${codec}` : codec;
}
const customImportFields=()=> (spreadsheetInventory?.layout || window.equipmentUI?.profile() || defaultInventoryLayout).columns.filter(col=>col.type!=='calculated'&&!(spreadsheetFile?.force_location&&col.key==='location')).map(col=>{const existing=equipmentImportFields.find(([key])=>key===col.key);return [col.key,col.label,[normalizedHeader(col.label),col.key.replaceAll('_',' '),...(col.aliases || []).map(normalizedHeader),...(existing?.[2] || [])]];});
const importFields = () => currentTab === 'equipment' ? customImportFields() : currentTab === 'device'
  ? networkImportFields.filter(([field]) => ['venue','name','ip','vlan','notes'].includes(field))
  : iptvImportFields;
const normalizedHeader = value => value.toLowerCase().replace(/[_-]/g, ' ').replace(/\s+/g, ' ').trim();
function mappedRows(applyVenueEdits = true) {
  return spreadsheetData.rows.map(row => {
    const mapped = Object.fromEntries(importFields().map(([field]) => {
      const column = $('map-' + field).value;
      let value = column === '' ? '' : row[Number(column)];
      if(currentTab==='equipment'&&(spreadsheetInventory?.layout || window.equipmentUI.profile()).columns.some(col=>col.key===field&&col.type==='count'))value=value.replace(/^`(\d+)`?$/,'$1');
      if (field === 'record_type') value = value.toLowerCase() || currentTab;
      if (field === 'ip' && isDHCP(value)) value = 'DHCP';
      if (field === 'venue' || field === 'location') value = cleanVenue(value);
      if (field === 'vlan' && !/^[0-9]+$/.test(value)) value = '';
      if (field === 'channel_source') value = ({onboard:'Onboard', satellite:'Satellite'})[value.toLowerCase()] || value;
      if (field === 'discipline') {
        const aliases = {video:'Video', audio:'Audio', lighting:'Lighting', lights:'Lighting', light:'Lighting', control:'Control', network:'Network', other:'Other'};
        value = aliases[value.toLowerCase()] || value;
      }
      return [field, value];
    }));
    const sourceIssues=[];
    if (currentTab === 'equipment') {
      const values={};
      Object.keys(mapped).forEach(key=>{if(!inventoryBaseFields.has(key)){values[key]=mapped[key];delete mapped[key];}});
      mapped.custom_values=values;
      inventoryBaseFields.forEach(key=>{if(mapped[key]==null)mapped[key]='';});
      const quantityOriginal=String(mapped.quantity ?? '').trim(),quantityMatch=quantityOriginal.match(/^(\d+)\s+(.+)$/);
      if(quantityMatch){mapped.quantity=quantityMatch[1];mapped.notes=[mapped.notes,`Quantity detail: ${quantityOriginal}`].filter(Boolean).join(' · ');sourceIssues.push(`Quantity contained extra text: ${quantityOriginal}`);}
      else if(quantityOriginal&&!/^\d+$/.test(quantityOriginal))sourceIssues.push(`Quantity is not numeric: ${quantityOriginal}`);
      const extras = ['name','storage_position','condition','unit','quantity_original'];
      const read = name => { const index = spreadsheetData.headers.findIndex(header => header.trim().toLowerCase() === name); return index < 0 ? '' : String(row[index] ?? '').trim(); };
      if (!mapped.description && importFields().some(([key])=>key==='description') && $('map-description').value!=='') mapped.description = read('name');
      const tvProfile=spreadsheetInventory?.layout || window.equipmentUI.profile();
      if(tvProfile.stock_mode==='tv_counts'){
        const description=read('description') || read('item');
        if(!mapped.brand && $('map-brand')?.value===''){const brand=description.match(/\b(Samsung|LG|Sony|Panasonic|Philips|Sharp|Toshiba|TCL|Hisense|NEC|Planar)\b/i);if(brand)mapped.brand=brand[1].toUpperCase()==='LG'?'LG':brand[1].toUpperCase()==='TCL'?'TCL':brand[1].toUpperCase()==='NEC'?'NEC':brand[1][0].toUpperCase()+brand[1].slice(1).toLowerCase();}
        if(description)mapped.notes=[mapped.notes,'Description: '+description].filter(Boolean).join(' · ');
        const limelight=spreadsheetData.headers.findIndex(header=>normalizedHeader(header)==='deck 4 limelight');
        if(limelight>=0&&String(row[limelight]).trim())mapped.notes=[mapped.notes,'Deck 4 Limelight: '+row[limelight]].filter(Boolean).join(' · ');
      }
      const hasMapped=Object.entries(mapped).some(([key,value])=>key==='custom_values'?Object.values(value).some(v=>String(v).trim()):String(value??'').trim());
      const details = extras.filter(name => hasMapped && name !== 'name' && read(name)).map(name => `${name.replaceAll('_',' ')}: ${read(name)}`);
      if(hasMapped && spreadsheetData.headers.filter(header=>normalizedHeader(header)==='location').length>1){spreadsheetData.headers.forEach((header,index)=>{if(normalizedHeader(header)==='location' && String(index)!==$('map-location')?.value && row[index])details.push(`Source Location (column ${index+1}): ${row[index]}`);});}
      mapped.notes = [mapped.notes, ...details].filter(Boolean).join(' · ');
      if(hasMapped && spreadsheetFile?.force_location)mapped.location=spreadsheetFile.default_location;
      else if(hasMapped && !mapped.location && (spreadsheetFile?.default_location || spreadsheetFile?.sheet_location))mapped.location=spreadsheetFile.default_location || spreadsheetFile.sheet_location;
      mapped.item_confirmed = ''; // Old files do not establish a new physical location check.
    }
    if (currentTab !== 'equipment') mapped.record_type = currentTab;
    if (currentTab === 'iptv') mapped.channel_source = channelSourceFromName(mapped.name);
    const field = currentTab === 'equipment' ? 'location' : 'venue';
    if (applyVenueEdits && venueEdits.has(mapped[field])) mapped[field] = venueEdits.get(mapped[field]);
    if(currentTab==='equipment'){const profile=spreadsheetInventory?.layout || window.equipmentUI.profile();const calculated=inventoryCalculate(mapped,profile);calculated.source_issues=[...sourceIssues];profile.columns.filter(col=>col.type==='calculated').forEach(col=>{const aliases=[col.label,...(col.aliases || [])].map(normalizedHeader);const index=spreadsheetData.headers.findIndex(header=>aliases.includes(normalizedHeader(header)));const original=index>=0?String(row[index] || '').trim():'';if(original!==''&&String(inventoryValue(calculated,col.key))!==original)calculated.source_issues.push(`Original ${col.label}: ${original}; calculated: ${inventoryValue(calculated,col.key) || 'unknown'}`);});return calculated;}return mapped;
  });
}
function combineTVEntries(entries) {
  const profile=spreadsheetInventory?.layout || window.equipmentUI.profile();
  if(!(profile.merge_duplicate_models??profile.stock_mode==='tv_counts'))return entries;
  const groups=new Map();
  entries.forEach(entry=>{const row=entry.row,key=!row.serial_number&&row.model?JSON.stringify([row.brand.trim().toLowerCase(),row.model.trim().toLowerCase(),row.location.trim().toLowerCase()]):'row:'+entry.number;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(entry);});
  return [...groups.values()].map(group=>{if(group.length===1)return group[0];const row={...group[0].row,custom_values:{...group[0].row.custom_values}};
    for(const key of ['description','brand','model','location'])if(!row[key])row[key]=group.map(entry=>entry.row[key]).find(Boolean)||'';
    const sumKeys=new Set(profile.columns.filter(col=>col.type==='count').map(col=>col.key));if(profile.columns.some(col=>col.key==='quantity'))sumKeys.add('quantity');
    sumKeys.forEach(key=>{const counts=group.map(entry=>String(inventoryValue(entry.row,key)).trim());const total=counts.every(value=>/^\d+$/.test(value))?String(counts.reduce((sum,value)=>sum+Number(value),0)):'';if(inventoryBaseFields.has(key))row[key]=total;else row.custom_values[key]=total;});
    const numbers=group.map(entry=>entry.number),descriptions=new Set(group.map(entry=>entry.row.description).filter(Boolean).map(normalizedHeader));row.source_issues=group.flatMap(entry=>(entry.row.source_issues||[]).map(issue=>'Source row '+entry.number+': '+issue));if(descriptions.size>1)row.source_issues.push('Merged model has different source descriptions; check Description');row.notes=[...new Set(group.map(entry=>entry.row.notes).filter(Boolean)),'Combined source rows: '+numbers.join(', '),...row.source_issues].join(' · ');
    return {...group[0],row:inventoryCalculate(row,profile),number:numbers.join(', '),sourceNumbers:numbers};
  });
}
function spreadsheetEntries() {
  const rows=mappedRows();
  const sourceRows=currentTab==='equipment'&&skippedImportLocations.size?mappedRows(false):rows;
  return rows.map((row,index)=>({row,number:spreadsheetData.row_numbers[index],skippedLocation:currentTab==='equipment'&&skippedImportLocations.has(sourceRows[index].location)})).filter(({row})=>meaningfulImportRow(row));
}
function showVenueEditors() {
  const equipment = currentTab === 'equipment', field = equipment ? 'location' : 'venue';
  if(equipment && !(spreadsheetInventory?.layout || window.equipmentUI.profile()).columns.some(col=>col.key==='location'&&col.filter==='buttons')){$('import-venue-editor').hidden=true;return;}
  const sourceRows=mappedRows(false);
  const locationCounts=new Map();
  sourceRows.filter(meaningfulImportRow).forEach(row=>locationCounts.set(row[field],(locationCounts.get(row[field]) || 0)+1));
  const venues = [...new Set(sourceRows.filter(row => equipment || row.record_type !== 'iptv').map(row => row[field]).filter(Boolean))];
  $('import-venue-editor').hidden = !venues.length;
  $('import-venue-title').textContent = equipment ? 'Location buttons' : 'Venue buttons';
  $('import-venue-help').textContent=equipment?'Rename locations, or exclude a location to skip its items in this import. Restore exclusions below before importing.':'Click a colored button to edit its name in the field beside it. Changes apply to every row using that venue when you import.';
  $('import-venue-list').replaceChildren(...venues.map((original, index) => {
    const row = element('div', 'venue-editor-row');
    row.classList.toggle('inventory-location-editor',equipment);
    row.dataset.sourceLocation=original;
    if(equipment&&skippedImportLocations.has(original)){
      row.classList.add('import-location-skipped');
      const count=locationCounts.get(original) || 0;
      const name=venueEdits.has(original)?venueEdits.get(original):original;
      const restore=element('button','secondary','Restore');restore.type='button';restore.setAttribute('aria-label',`Restore location ${name}`);
      restore.onclick=()=>{venues.forEach(location=>{if((venueEdits.has(location)?venueEdits.get(location):location)===name)skippedImportLocations.delete(location);});showVenueEditors();showSpreadsheetPreview();};
      row.append(element('span','',`${name} · ${count} items skipped`),restore);return row;
    }
    const button = element('button', 'choice-button', venueEdits.has(original) ? venueEdits.get(original) : original);
    button.type = 'button';
    colorVenueButton(button, button.textContent);
    const label = element('label');
    label.append(element('span', 'sr-only', `Edit ${equipment ? 'location' : 'venue'} ${original}`));
    const input = element('input');
    input.id = `import-venue-${index}`; input.value = button.textContent; input.maxLength = 120;
    input.autocomplete = 'off';
    input.oninput = () => {
      const venue = cleanVenue(input.value);
      venueEdits.set(original, venue);
      button.textContent = venue;
      colorVenueButton(button, venue);
      showSpreadsheetPreview();
    };
    input.onblur = () => { input.value = cleanVenue(input.value); };
    button.onclick = () => { input.focus(); input.select(); };
    label.append(input); row.append(button, label);
    if(equipment){
      const remove=element('button','quiet delete-import-location','Exclude location');remove.type='button';
      remove.setAttribute('aria-label',`Exclude location ${button.textContent} and skip its items`);
      input.addEventListener('input',()=>remove.setAttribute('aria-label',`Exclude location ${button.textContent} and skip its items`));
      remove.onclick=()=>{const name=venueEdits.has(original)?venueEdits.get(original):original;venues.forEach(location=>{if((venueEdits.has(location)?venueEdits.get(location):location)===name)skippedImportLocations.add(location);});showVenueEditors();showSpreadsheetPreview();window.importWorkflow.checkpoint().catch(error=>toast(error.message));};row.append(remove);
    }
    return row;
  }));
}
function networkIssues(row){
  const issues=[];
  if(!row.name)issues.push('Missing name');
  if(row.ip && !isDHCP(row.ip)){
    if(!/^(?:0|[1-9]\d{0,2})(?:\.(?:0|[1-9]\d{0,2})){3}$/.test(row.ip) || row.ip.split('.').some(part=>Number(part)>255))issues.push('Invalid IP address');
    else if(currentTab==='device' && (Number(row.ip.split('.')[0])>=224 || row.ip==='0.0.0.0' || row.ip.startsWith('127.')))issues.push('Use a device address');
    else if(currentTab==='iptv' && (Number(row.ip.split('.')[0])<224 || Number(row.ip.split('.')[0])>239))issues.push('Use a multicast address');
  }
  if(currentTab==='iptv' && row.port && (!/^\d+$/.test(String(row.port)) || Number(row.port)<1 || Number(row.port)>65535))issues.push('Port must be 1–65535');
  if(currentTab==='device' && row.vlan && (Number(row.vlan)<1 || Number(row.vlan)>4094))issues.push('VLAN must be 1–4094');
  return issues;
}
function renderImportDraftDetails(){
  const seen=window.importWorkflow.preferences.seen_headers || [],headings=spreadsheetData.headers.map(normalizedHeader);
  const added=headings.filter(header=>!seen.includes(header)),missing=seen.filter(header=>!headings.includes(header));
  $('import-source-changes').textContent=`Read ${headings.length} columns from this source. ${seen.length?`${added.length} new headings · ${missing.length} previous headings absent. Saved choices are suggestions for matching names; column positions are read again.`:'Every new table is read independently. Check the headings, sample values and suggested matches below.'}`;
  const draft=spreadsheetInventory?.layout;
  $('import-draft-summary').textContent=`Setup is a draft until you start importing. ${draft?draft.columns.map(column=>column.label+' ('+column.type+')').join(' · '):'Fixed network fields'} · Confirmation: ${spreadsheetFile.confirmation_mode || 'default'}. ${draft && draft.confirmation_mode!==window.importWorkflow.originalLayout?.confirmation_mode?'Changing the confirmation workflow clears prior confirmation marks when applied.':''}`;
  const entries=spreadsheetEntries(),combined=currentTab==='equipment'?combineTVEntries(entries.filter(entry=>!entry.skippedLocation)):entries;
  const existing=window.importWorkflow.knownRecords;
  const match=row=>existing.find(saved=>{
    if(currentTab!=='equipment')return importAddressKey(row) && importAddressKey(row)===importAddressKey(saved);
    if(draft?.stock_mode==='tv_counts')return row.brand && row.model && row.brand.toLowerCase()===saved.brand.toLowerCase() && row.model.toLowerCase()===saved.model.toLowerCase();
    if(draft?.identifier){const id=String(inventoryValue(row,draft.identifier)).trim();return id && id.toLowerCase()===String(inventoryValue(saved,draft.identifier)).trim().toLowerCase();}
    if(row.serial_number)return serialKey(row.serial_number)===serialKey(saved.serial_number);
    return row.brand && row.model && row.location && ['brand','model','location','description'].every(key=>String(row[key] || '').toLowerCase()===String(saved[key] || '').toLowerCase());
  });
  const comparisons=combined.flatMap(entry=>{
    const saved=match(entry.row),lines=[];
    if(entry.sourceNumbers)lines.push(`Source rows ${entry.sourceNumbers.join(', ')} combine as ${entry.row.brand} ${entry.row.model}: ${draft.columns.filter(column=>column.type==='count'||column.type==='calculated').map(column=>column.label+' '+inventoryValue(entry.row,column.key)).join(' · ')}`);
    if(saved)lines.push(`Row ${entry.number}: source ${entry.row.model || entry.row.name || entry.row.serial_number} matches saved record #${saved.id}. It will be skipped; the saved record is kept.${currentTab==='equipment'?` Source quantity: ${entry.row.quantity ?? 'unknown'}; saved quantity: ${saved.quantity ?? 'unknown'}.`:''}`);
    return lines;
  });
  $('import-duplicate-list').replaceChildren(...(comparisons.length?comparisons:['No matching saved assignments or combined rows.']).map(text=>element('p','',text)));
  $('import-excluded-locations').hidden=!skippedImportLocations.size;
  $('import-excluded-list').replaceChildren(...[...skippedImportLocations].map(location=>{
    const row=element('div','import-history-row'),restore=element('button','secondary','Restore');restore.type='button';restore.setAttribute('aria-label',`Restore excluded location ${location}`);restore.onclick=()=>{skippedImportLocations.delete(location);showVenueEditors();showSpreadsheetPreview();window.importWorkflow.checkpoint().catch(error=>toast(error.message));};
    row.append(element('span','',`${location} · ${entries.filter(entry=>entry.skippedLocation && entry.row.location===location).length} source rows excluded`),restore);return row;
  }));
}
function showSpreadsheetPreview() {
  renderImportDraftDetails();
  const allEntries=spreadsheetEntries();
  $('equipment-import-audit').hidden = currentTab !== 'equipment';
  if (currentTab === 'equipment') {
    const entries = orderEquipmentReview(combineTVEntries(allEntries.filter(entry=>!entry.skippedLocation)));
    const profile=spreadsheetInventory.layout || defaultInventoryLayout;
    $('equipment-import-audit').textContent = `${profile.stock_mode==='tv_counts'?entries.filter(entry=>entry.row.quantity===0).length+' zero-stock rows will be skipped':profile.location_role==='geographic'?entries.length+' device locations':new Set(entries.map(entry => entry.row.location)).size+' storage locations'} · ${entries.filter(entry => entry.issues.length).length} flagged rows${profile.stock_mode==='tv_counts'?' · '+entries.filter(entry=>entry.sourceNumbers).length+' duplicate-model groups combined':''} · ${allEntries.filter(entry=>entry.skippedLocation).length} items skipped from excluded locations. For each location, complete rows come first, then flagged rows. Storage position, condition, unit and source details are kept in Notes. ${profile.confirmation_mode==='ip'?'Imported IPs start unconfirmed.':profile.show_status===false?'No post-import confirmation is required.':'Imported locations start unconfirmed.'}`;
  }
  const previewEntries=currentTab==='equipment'?combineTVEntries(allEntries.filter(entry=>!entry.skippedLocation)):allEntries.filter(entry=>!entry.skippedLocation);
  const rows = previewEntries.map(entry=>entry.row);
  if(currentTab==='equipment')$('confirm-import').textContent=`Apply setup & review ${rows.length} rows`;
  if (currentTab === 'iptv') {
    const codecIPs = channelCodecIPs([...devices, ...rows]);
    rows.forEach(row => { row.notes = channelNotesWithCodec(row, codecIPs); });
  }
  $('spreadsheet-preview').replaceChildren(...rows.slice(0,3).map((row, index) => {
    const card = element('div', 'spreadsheet-preview-row');
    if (currentTab === 'equipment') {
      card.append(element('strong','',`Row ${previewEntries[index].number}`));
      const profile=spreadsheetInventory?.layout || window.equipmentUI.profile();
      card.append(element('p','',profile.columns.map(col=>`${col.label}: ${inventoryValue(row,col.key) || 'Blank'}`).join(' · ')));return card;
    }
    card.append(element('strong', '', `Row ${previewEntries[index].number} · ${row.name}`));
    card.append(element('p', '', (row.record_type === 'iptv' ? [row.ip, row.port ? `Port ${row.port}` : '', row.channel_source] : [row.ip, row.vlan ? `VLAN ${row.vlan}` : '', row.venue]).filter(Boolean).join(' · ')));
    card.append(element('p', '', [row.discipline, row.category].filter(Boolean).join(' / ')));
    if (row.notes) card.append(element('p', '', row.notes));
    return card;
  }));
  if(spreadsheetFile?.pasted && $('paste-layout-dialog').open)showPastedLayoutSuggestion();
}
async function loadSpreadsheet(options={}) {
  const loadingFile=spreadsheetFile;
  $('confirm-import').disabled = true; $('reload-sheet').disabled = true;
  $('spreadsheet-error').hidden = true;
  try {
    const workbook=/\.xlsx$/i.test(spreadsheetFile.filename);
    $('sheet-label').hidden=!workbook;
    $('worksheet-note').hidden=workbook;
    if(workbook && ![...$('sheet-choice').options].some(option=>option.value)) {
      $('sheet-choice').disabled=true;
      $('sheet-choice').replaceChildren(new Option('Loading worksheets…',''));
      const catalog=await api('/api/spreadsheet-preview','POST',{...spreadsheetFile,sheets_only:true});
      if(!catalog.sheets?.length)throw new Error('This workbook has no worksheets.');
      $('sheet-choice').replaceChildren(...catalog.sheets.map(sheet=>new Option(sheet,sheet)));
      $('sheet-choice').disabled=false;
    }
    if (currentTab === 'iptv') {
      await satelliteCatalogReady;
      if (satelliteCatalogError) throw new Error('Could not load the satellite channel reference. Refresh the page and try again.');
    }
    if(spreadsheetFile!==loadingFile)return;
    const data = await api('/api/spreadsheet-preview', 'POST', {...spreadsheetFile, sheet: $('sheet-choice').value, header_row: Number($('header-row').value),detect_header:!spreadsheetFile.pasted && !options.manualHeader && !$('header-row').dataset.manual,header_aliases:importFields().flatMap(([key,label,aliases])=>[label,...aliases]),keep_headers:currentTab==='equipment'?customImportFields().flatMap(([key,label,aliases])=>[label,...aliases]):[]});
    if(spreadsheetFile!==loadingFile)return;
    spreadsheetData = data;
    $('header-row').value=data.header_row;
    $('header-row').disabled=!!spreadsheetFile.pasted;
    $('import-confirmation-choice').replaceChildren(new Option('No confirmation','none'),new Option('Confirm IP','ip'),...(currentTab==='equipment'?[new Option('To be found / Located','storage')]:[]));
    $('import-confirmation-choice').value=spreadsheetFile.confirmation_mode || 'none';
    $('import-header-list').replaceChildren(...(data.header_candidates || []).slice(0,12).map(candidate=>{
      const row=element('div','import-history-row'),button=element('button','secondary',`Use row ${candidate.number}`);button.type='button';button.onclick=()=>{$('header-row').value=candidate.number;$('header-row').dataset.manual='true';loadSpreadsheet({manualHeader:true});};
      row.append(element('span','',candidate.values.filter(Boolean).join(' · ').slice(0,360)),button);return row;
    }));
    $('import-header-candidates').hidden=!data.header_candidates?.length;
    $('header-row-help').textContent=data.generated_headers?'No column headings were detected, so AVTrack kept the first record and created temporary Column 1, Column 2… headings. Match each temporary column to the correct IPTV field below.':spreadsheetFile.pasted?'The first pasted row is always the header row. Multiword titles stay within their original Excel cells.':`Column headings found on row ${data.header_row}${data.header_confidence==='low'?' — check the sample headings below':''}. Change the number and reload if needed.`;
    $('sheet-label').hidden = !data.sheets.length;
    $('sheet-choice').replaceChildren(...data.sheets.map(sheet => new Option(sheet, sheet)));
    $('sheet-choice').value = data.sheet;
    if(currentTab==='equipment')$('spreadsheet-title').textContent='Step 2: match file columns to your inventory';else $('spreadsheet-title').textContent='Match your columns';
    $('import-complete-options').hidden=currentTab!=='equipment';
    $('spreadsheet-review-help').textContent=currentTab==='equipment' ? 'Match each inventory field to a file column. Complete matched rows can be added automatically. Review remaining rows together, grouped by location; edit their cells and import or skip selected rows. Calculated totals need no file column. Zero-stock TV rows are skipped. Orientation is optional.' : 'Match each field to a column, or choose Leave blank. Missing columns and empty cells stay blank. Click Review rows, then select valid rows and import them together.';
    $('spreadsheet-summary').textContent = `${spreadsheetFile.filename} · ${data.rows.length} records${spreadsheetInventory ? ' · Inventory: ' + spreadsheetInventory.name : ''}${data.generated_headers?' · Temporary headings added':''}`;
    if (data.ignored_columns?.length) $('spreadsheet-summary').textContent += ` · Ignored columns: ${data.ignored_columns.join(', ')}`;
    $('column-mappings').replaceChildren(...importFields().map(([field, label, aliases]) => {
      const group = element('div', 'mapping-row');
      const columnLabel = element('label', '', label);
      const select = element('select'); select.id = 'map-' + field;
      select.add(new Option('Leave blank', ''));
      data.headers.forEach((header, index) => select.add(new Option(`${index+1}. ${header} — ${(data.column_samples[index] || []).filter(Boolean).slice(0,2).join(' / ').slice(0,70) || 'blank samples'}`, String(index))));
      // Prefer the requested header before falling back to broader aliases.
      const matched = aliases.map(alias => data.headers.findIndex(header => normalizedHeader(header) === alias)).find(index => index >= 0) ?? -1;
      if (matched >= 0) select.value = String(matched);
      if(field==='location' && data.headers.filter(header=>normalizedHeader(header)==='location').length>1)select.value=String(data.headers.map(normalizedHeader).lastIndexOf('location'));
      columnLabel.append(select); group.append(columnLabel);
      select.onchange = () => { showVenueEditors(); showSpreadsheetPreview(); window.importWorkflow.checkpoint().catch(error=>toast(error.message)); };
      return group;
    }));
    await window.importWorkflow.configureSheets(data.sheets);
    window.importWorkflow.restoreMappings(data);
    showVenueEditors(); showSpreadsheetPreview();
    await window.importWorkflow.checkpoint();
    if(currentTab!=='equipment')$('confirm-import').textContent=`Review ${data.rows.length} rows together`;
    $('confirm-import').disabled = false;
  } catch (error) {
    if(![...$('sheet-choice').options].some(option=>option.value) && /\.xlsx$/i.test(spreadsheetFile.filename)) {
      $('sheet-choice').replaceChildren(new Option('Could not load worksheets',''));
      $('sheet-choice').disabled=true;
    }
    $('spreadsheet-error').textContent = error.message;
    $('spreadsheet-error').hidden = false;
  } finally { $('reload-sheet').disabled = false; }
}
function closeSpreadsheet() {
  if (spreadsheetReviewing) { stopSpreadsheetReview = true; return; }
  window.importWorkflow.checkpoint('paused').catch(error=>toast(error.message));
  $('spreadsheet-dialog').close(); spreadsheetData = null; spreadsheetFile = null; venueEdits = new Map(); skippedImportLocations.clear();
}
$('close-spreadsheet').onclick = $('cancel-spreadsheet').onclick = closeSpreadsheet;
$('spreadsheet-dialog').addEventListener('cancel', event => {
  if (spreadsheetReviewing) { event.preventDefault(); stopSpreadsheetReview = true; }
  else { event.preventDefault();closeSpreadsheet(); }
});
$('reset-import-suggestions').onclick=()=>{
  window.importWorkflow.resetSuggestions();
  importFields().forEach(([key,label,aliases])=>{
    const input=$('map-'+key),index=aliases.map(alias=>spreadsheetData.headers.findIndex(header=>normalizedHeader(header)===alias)).find(value=>value>=0);
    input.value=index==null?'':String(index);
    if(key==='location' && spreadsheetData.headers.filter(header=>normalizedHeader(header)==='location').length>1)input.value=String(spreadsheetData.headers.map(normalizedHeader).lastIndexOf('location'));
  });
  showVenueEditors();showSpreadsheetPreview();window.importWorkflow.checkpoint().catch(error=>toast(error.message));
};
$('import-confirmation-choice').onchange=()=>{const mode=$('import-confirmation-choice').value;spreadsheetFile.confirmation_mode=mode;if(spreadsheetInventory)spreadsheetInventory={...spreadsheetInventory,layout:{...(spreadsheetInventory.layout || defaultInventoryLayout),confirmation_mode:mode,show_status:mode!=='none'}};showSpreadsheetPreview();window.importWorkflow.checkpoint().catch(error=>toast(error.message));};
$('reload-sheet').onclick = () => loadSpreadsheet({manualHeader:!!$('header-row').dataset.manual});
// Sheet/header changes must be loaded before an import can be confirmed.
$('sheet-choice').onchange = () => { $('confirm-import').disabled=true;delete $('header-row').dataset.manual; };
$('header-row').oninput=()=>{$('header-row').dataset.manual='true';$('confirm-import').disabled=true;};
const meaningfulImportRow = row => Object.entries(row).some(([field,value]) => field==='custom_values'?Object.values(value).some(value=>String(value??'').trim()!==''):field !== 'record_type' && field !== 'source_issues' && value !== '' && value!=null);
function importAddressKey(row) {
  const ip = (row.ip || '').trim();
  if (!/^(?:0|[1-9]\d{0,2})(?:\.(?:0|[1-9]\d{0,2})){3}$/.test(ip) || ip.split('.').some(part => Number(part) > 255)) return null;
  if ((row.record_type || 'device') === 'device') return `device:${ip}`;
  const port = String(row.port ?? '').trim();
  return /^\d+$/.test(port) && Number(port) >= 1 && Number(port) <= 65535 ? `iptv:${ip}:${Number(port)}` : null;
}
function skippedDuplicateImport(entry, row = entry.row) {
  return {added:0, skipped:1, warnings:[`Row ${entry.number}: ${row.name || ''} · ${row.venue || ''} · duplicate IP ${row.ip} already exists in the inventory. Skipped; the first record was kept.`]};
}
let finishRowReview = null, rowReviewSaving = false;
function endRowReview(result) {
  if (rowReviewSaving || !finishRowReview) return;
  const finish = finishRowReview; finishRowReview = null;
  $('row-review-dialog').close(); finish(result);
}
$('stop-row-review').onclick = $('cancel-row-review').onclick = () => endRowReview(null);
$('skip-review-row').onclick = () => endRowReview({skippedRow:true});
$('row-review-dialog').addEventListener('cancel', event => { event.preventDefault(); endRowReview(null); });
function reviewImportRow(entry, index, total, tab, knownAddresses, inventory = null) {
  return new Promise(resolve => {
    finishRowReview = resolve;
    const equipment = tab === 'equipment';
    $('row-review-title').textContent = equipment ? 'Import this equipment?' : tab === 'iptv' ? 'Import this channel?' : 'Import this device?';
    $('row-review-progress').textContent = `Row ${entry.number} · ${index + 1} of ${total} · ${spreadsheetFile.filename}${inventory ? ' · Inventory: ' + inventory.name : ''}`;
    $('row-review-error').hidden = true;
    $('row-review-flags').hidden = !equipment || !entry.issues?.length;
    $('row-review-flags').textContent = equipment && entry.issues?.length ? 'Check: ' + entry.issues.join(' · ') + '. Blank values may remain for follow-up.' : '';
    if (equipment) $('row-review-progress').textContent += ' · ' + entry.locationProgress;
    $('row-review-ip-hint').textContent = tab === 'iptv'
      ? 'There is text in the Multicast IP field. Enter an IPv4 address, leave the field blank, or skip this row.'
      : 'There is text in the IP Address field. Enter an IPv4 address, click DHCP, leave the field blank, or skip this row.';
    const controls = new Map();
    const fields = tab === 'iptv'
      ? [...iptvImportFields.slice(0,3), ['channel_source', 'Type'], ...iptvImportFields.slice(3)]
      : importFields();
    $('row-review-fields').style.setProperty('--review-columns', fields.length);
    $('row-review-fields').replaceChildren(...fields.map(([field, label]) => {
      const group = element('label', '', label.replace(' (optional)', ''));
      const column=equipment?(inventory?.layout || window.equipmentUI.profile()).columns.find(col=>col.key===field):null;
      if (column?.key==='orientation') group.firstChild.textContent += ' (optional)';
      if(column && !inventoryBaseFields.has(field)){const {wrapper,control}=inventoryInput(column,inventoryValue(entry.row,field),{allowClear:field!=='orientation'});control.id=`review-${field}`;group.append(wrapper);controls.set(field,control);return group;}
      const input = element(field === 'channel_source' ? 'select' : field === 'notes' ? 'textarea' : 'input'); input.id = `review-${field}`;
      if (field === 'channel_source') input.append(new Option('Leave blank', ''), new Option('Onboard', 'Onboard'), new Option('Satellite', 'Satellite'));
      if (field === 'notes') input.rows = 1;
      input.value = entry.row[field] ?? ''; input.autocomplete = 'off';
      input.maxLength = field === 'notes' || field === 'description' ? 2000 : 120;
      if (field === 'ip') input.spellcheck = false;
      group.append(input); controls.set(field, input);
      if (field === 'ip') {
        const actions = element('div', 'review-ip-actions');
        const dhcp = tab === 'device' ? element('button', 'choice-button', 'DHCP') : null;
        if (dhcp) { dhcp.type = 'button'; dhcp.id = 'review-dhcp'; }
        const blank = element('button', 'quiet', 'Clear'); blank.type = 'button'; blank.id = 'review-clear-ip';
        const update = () => {
          dhcp?.setAttribute('aria-pressed', String(isDHCP(input.value)));
          $('row-review-ip-hint').hidden = !input.value.trim() || (dhcp && isDHCP(input.value)) || !/[^0-9.\s]/.test(input.value);
        };
        if (dhcp) dhcp.onclick = () => { input.value = 'DHCP'; update(); };
        blank.onclick = () => { input.value = ''; update(); input.focus(); };
        input.oninput = update; update(); if (dhcp) actions.append(dhcp); actions.append(blank); group.append(actions);
      }
      return group;
    }));
    if (tab === 'iptv') {
      const source = controls.get('channel_source');
      let sourceEdited = false;
      source.onchange = () => { sourceEdited = true; };
      controls.get('name').addEventListener('input', () => {
        if (!sourceEdited) source.value = channelSourceFromName(controls.get('name').value);
      });
      const codecIPs = channelCodecIPs(mappedRows().filter((row, index) => spreadsheetData.row_numbers[index] !== entry.number));
      knownAddresses.forEach(key => {
        if (key.startsWith('iptv:') && key.endsWith(':2000')) codecIPs.add(key.split(':')[1]);
      });
      const notes = controls.get('notes');
      let notesEdited = false;
      notes.addEventListener('input', () => { notesEdited = true; });
      const updateCodecNotes = () => {
        if (!notesEdited) notes.value = channelNotesWithCodec({record_type:'iptv', ip:controls.get('ip').value.trim(), port:controls.get('port').value.trim(), notes:entry.row.notes}, codecIPs);
      };
      controls.get('ip').addEventListener('input', updateCodecNotes);
      controls.get('port').addEventListener('input', updateCodecNotes);
      updateCodecNotes();
    }
    if (equipment) $('row-review-ip-hint').hidden = true;
    $('accept-review-row').onclick = async () => {
      if (rowReviewSaving) return;
      const row = {...entry.row};
      row.custom_values=equipment?{...entry.row.custom_values}:entry.row.custom_values;
      controls.forEach((input, field) => { if(equipment&&!inventoryBaseFields.has(field))row.custom_values[field]=input.value.trim();else row[field] = input.value.trim(); });
      if(!equipment)delete row.custom_values;
      if (!equipment) {
        if (isDHCP(row.ip)) row.ip = 'DHCP';
        if (tab === 'device') {
          row.venue = cleanVenue(row.venue);
          if (!/^[0-9]+$/.test(row.vlan)) row.vlan = '';
        }
      } else row.location = cleanVenue(row.location);
      // Clearing the final value makes this an empty row, which needs no write.
      if (!meaningfulImportRow(row)) { endRowReview({skippedRow:true}); return; }
      const addressKey = equipment ? null : importAddressKey(row);
      if (addressKey && knownAddresses.has(addressKey)) { endRowReview(skippedDuplicateImport(entry, row)); return; }
      const dialogControls = [...$('row-review-dialog').querySelectorAll('button,input,select,textarea')];
      rowReviewSaving = true; dialogControls.forEach(control => { control.disabled = true; });
      $('row-review-error').hidden = true;
      let result;
      try {
        result = await api(equipment ? '/api/equipment/import' : '/api/import', 'POST', equipment
          ? {version:1,inventory_id:inventory.id,equipment:[row]}
          : {version:1,devices:[row],source:'spreadsheet',row_numbers:[entry.number],...(spreadsheetFile.confirmation_mode?{confirmation_required:spreadsheetFile.confirmation_mode==='ip'}:{})});
        if (result.added && addressKey) knownAddresses.add(addressKey);
      } catch(error) {
        $('row-review-error').textContent = error.message.replace('Nothing was imported.', 'This row was not imported. Previously accepted rows remain saved.');
        $('row-review-error').hidden = false;
      } finally {
        rowReviewSaving = false; dialogControls.forEach(control => { control.disabled = false; });
      }
      if (result) endRowReview(result);
    };
    $('row-review-dialog').showModal();
    $('accept-review-row').focus();
  });
}
$('spreadsheet-form').onsubmit = async event => {
  event.preventDefault();
  if (!spreadsheetData || $('confirm-import').disabled) return;
  $('confirm-import').disabled=true;$('spreadsheet-error').hidden=true;
  spreadsheetReviewing=true;stopSpreadsheetReview=false;
  try{
    const tab=currentTab;
    if(window.importWorkflow.queue.length){const selected=$('sheet-choice').value;if(selected!==window.importWorkflow.queue[window.importWorkflow.queueIndex])throw new Error('Choose the first selected worksheet before starting.');}
    await window.importWorkflow.applySetup();
    const allEntries=spreadsheetEntries();
    for(const entry of window.importWorkflow.remaining(allEntries.filter(entry=>entry.skippedLocation)))await window.importWorkflow.write(entry,entry.row,'exclude');
    let entries=tab==='equipment'?combineTVEntries(allEntries.filter(entry=>!entry.skippedLocation)):allEntries.filter(entry=>!entry.skippedLocation);
    entries=window.importWorkflow.remaining(entries);
    if(tab==='equipment')entries=orderEquipmentReview(entries);
    else entries=entries.map(entry=>({...entry,issues:networkIssues(entry.row)}));
    const profile=tab==='equipment'?spreadsheetInventory.layout || defaultInventoryLayout:null;
    if(profile?.stock_mode==='tv_counts'){
      const zero=entries.filter(entry=>entry.row.quantity===0&&!entry.row.source_issues?.length);
      for(const entry of zero)await window.importWorkflow.write(entry,entry.row,'zero');
      entries=entries.filter(entry=>entry.row.quantity!==0||entry.row.source_issues?.length);
    }
    let stopped=false;
    for(let index=0;index<entries.length;){
      if(stopSpreadsheetReview){stopped=true;break;}
      const location=tab==='equipment'?entries[index].row.location:entries[index].row.venue || '';
      let end=index;
      while(end<entries.length && (tab==='equipment'?entries[end].row.location:entries[end].row.venue || '')===location)end++;
      const batch=entries.slice(index,end),remaining=[];
      for(const entry of batch){
        const complete=profile && $('import-complete-rows').checked && !profile.columns.some(column=>column.require_confirmation) && !entry.issues.length && profile.columns.filter(column=>column.key!=='orientation'&&column.type!=='calculated').every(column=>(($('map-'+column.key)?.value ?? '')!=='' || column.key==='brand'&&profile.stock_mode==='tv_counts' || column.key==='location'&&(spreadsheetFile.default_location || spreadsheetFile.sheet_location)) && String(inventoryValue(entry.row,column.key)).trim()!=='');
        if(!complete){remaining.push(entry);continue;}
        try{await window.importWorkflow.write(entry,entry.row);}catch(error){entry.issues.push(error.message);remaining.push(entry);}
      }
      if(remaining.length){
        const review=await reviewEquipmentBatch(remaining,index,entries.length,spreadsheetInventory || {name:tab==='iptv'?'IPTV Channels':'AV Devices',layout:{columns:[]}},profile?profile.columns.map(column=>[column.key,column.label]):importFields().map(([key,label])=>[key,label]),spreadsheetFile.filename,[...new Set(entries.map(entry=>entry.row.location).filter(Boolean))],tab!=='equipment');
        if(review.stopped){stopped=true;break;}
      }
      await load();index=end;
    }
    spreadsheetReviewing=false;
    $('spreadsheet-dialog').close();
    await window.importWorkflow.finish(stopped);
    await load();
  }catch(error){$('spreadsheet-error').textContent=error.message;$('spreadsheet-error').hidden=false;$('spreadsheet-dialog').showModal();}
  finally{spreadsheetReviewing=false;$('confirm-import').disabled=false;}
};
function showPastedLayoutSuggestion() {
  $('keep-paste-layout').hidden=!!spreadsheetFile.from_headers && !spreadsheetFile.fields_configured;
  if(spreadsheetFile.from_headers && !spreadsheetFile.fields_configured){
    const head=element('tr');spreadsheetData.headers.forEach(header=>{const th=element('th','',header);th.scope='col';head.append(th);});$('paste-layout-head').replaceChildren(head);
    $('paste-layout-rows').replaceChildren(...spreadsheetData.rows.slice(0,5).map(values=>{const row=element('tr');values.forEach(value=>row.append(element('td',String(value??'').trim()?'':'paste-layout-blank',String(value??'').trim() || 'Needs review')));return row;}));
    $('paste-layout-summary').textContent=`${spreadsheetInventory.name} · ${spreadsheetData.headers.length} headings on row ${spreadsheetData.header_row} · ${spreadsheetData.rows.length} source rows · Showing ${Math.min(5,spreadsheetData.rows.length)} sample rows`;
    $('paste-layout-unmatched').hidden=true;$('continue-paste-layout').disabled=false;window.pasteWorkflow.render();return;
  }

  const fields=currentTab==='equipment' ? (spreadsheetInventory.layout || defaultInventoryLayout).columns.map(column=>[column.key,column.label,column.type]) : importFields().map(([key,label])=>[key,label,'text']);
  const used=new Set();let matched=0;
  const head=element('tr');
  fields.forEach(([key,label,type])=>{
    const index=$('map-'+key)?.value ?? '';
    const th=element('th');th.scope='col';th.dataset.fieldKey=key;th.append(element('span','',label.replace(' (optional)','')));
    let source='No matching heading';
    if(type==='calculated')source='Calculated from counts';
    else if(index!==''){used.add(Number(index));matched++;source='Excel: '+spreadsheetData.headers[Number(index)];}
    else if(key==='location'&&spreadsheetFile.default_location)source='Location: '+spreadsheetFile.default_location;
    else if(key==='brand'&&spreadsheetInventory?.layout?.stock_mode==='tv_counts')source='Suggested from Description';
    th.append(element('small',index===''&&type!=='calculated'?'paste-layout-missing':'',source));head.append(th);
  });
  $('paste-layout-head').replaceChildren(head);
  const entries=spreadsheetEntries().filter(entry=>!entry.skippedLocation);
  const preview=currentTab==='equipment'?combineTVEntries(entries):entries;
  $('paste-layout-rows').replaceChildren(...preview.slice(0,5).map(({row})=>{
    const tr=element('tr');fields.forEach(([key,label])=>{
      const value=currentTab==='equipment'?inventoryValue(row,key):row[key];
      const blank=value==null||String(value).trim()==='';
      const td=element('td',blank?'paste-layout-blank':'',blank?'Needs review':String(value));td.title=blank?'Blank cell — check during import review':String(value);tr.append(td);
    });return tr;
  }));
  const unmatched=[...spreadsheetData.headers.filter((header,index)=>!used.has(index)),...(spreadsheetData.ignored_columns || [])];
  $('paste-layout-unmatched').hidden=!unmatched.length;
  $('paste-layout-unmatched').textContent='Headings without a direct field match: '+unmatched.join(', ')+'. Review these in field matching; some source details may be kept in Notes.';
  $('paste-layout-summary').textContent=`${spreadsheetInventory?.name || (currentTab==='iptv'?'IPTV Channels':'AV Devices')} · Heading row ${spreadsheetData.header_row} · ${spreadsheetData.rows.length} source rows · ${matched} suggested field matches · Showing ${Math.min(5,preview.length)} sample rows`;
  $('continue-paste-layout').disabled=false;$('keep-paste-layout').disabled=false;
  window.pasteWorkflow.render();
}
function showMissingPasteHeadings(){
  const missing=!!spreadsheetData?.generated_headers,section=$('paste-missing-headings');section.hidden=!missing;
  if(!missing){$('paste-heading-inputs').replaceChildren();return;}
  $('paste-heading-error').hidden=true;
  $('paste-heading-inputs').replaceChildren(...spreadsheetData.headers.map((header,index)=>{
    const sample=(spreadsheetData.column_samples[index] || []).filter(Boolean).slice(0,2).join(' · ') || 'blank cells';
    const label=element('label','',`Column ${index+1}`),input=element('input');input.maxLength=120;input.dataset.columnIndex=String(index);input.placeholder=`Name this column · ${sample}`;input.value=/^column\s+\d+$/i.test(header)?'':header;label.append(input,element('small','',`Examples: ${sample}`));return label;
  }));
}
$('apply-paste-headings').onclick=async()=>{
  const button=$('apply-paste-headings'),names=[...$('paste-heading-inputs').querySelectorAll('input')].map(input=>input.value.trim());
  $('paste-heading-error').hidden=true;
  if(names.some(name=>!name)){ $('paste-heading-error').textContent='Enter a clear name for every column before continuing.';$('paste-heading-error').hidden=false;return; }
  if(new Set(names.map(normalizedHeader)).size!==names.length){$('paste-heading-error').textContent='Use a different name for each column.';$('paste-heading-error').hidden=false;return;}
  button.disabled=true;spreadsheetFile.header_overrides=names;
  await loadSpreadsheet();button.disabled=false;
  if(!$('spreadsheet-error').hidden){$('paste-heading-error').textContent=$('spreadsheet-error').textContent;$('paste-heading-error').hidden=false;return;}
  showPastedLayoutSuggestion();
};
$('back-spreadsheet-layout').onclick=()=>{if(spreadsheetReviewing)return;$('spreadsheet-dialog').close();showPastedLayoutSuggestion();$('paste-layout-dialog').showModal();};
$('keep-paste-layout').onclick=()=>{$('paste-layout-dialog').close();$('spreadsheet-dialog').showModal();};
$('continue-paste-layout').onclick=startPastedHeadingSetup;
$('back-paste-layout').onclick=()=>{$('paste-layout-dialog').close();closeSpreadsheet();$('paste-inventory-dialog').showModal();$('paste-inventory-text').focus();};
for(const id of ['close-paste-layout','cancel-paste-layout'])$(id).onclick=()=>{$('paste-layout-dialog').close();closeSpreadsheet();};
$('paste-layout-dialog').addEventListener('cancel',()=>closeSpreadsheet());
let pastedFieldSetup=null;
function startPastedHeadingSetup(){
  if(pastedFieldSetup?.file===spreadsheetFile){$('paste-layout-dialog').close();showPastedHeading();$('paste-field-dialog').showModal();return;}
  const columns=currentTab==='equipment' ? structuredClone(spreadsheetInventory.layout || defaultInventoryLayout).columns : importFields().map(([key,label])=>({key,label,type:'text',options:[]}));
  const decisions=spreadsheetData.headers.map((header,index)=>{
    const matching=columns.find(column=>$('map-'+column.key)?.value===String(index)) || columns.find(column=>column.type==='calculated'&&[column.label,...(column.aliases || [])].some(alias=>normalizedHeader(alias)===normalizedHeader(header)));
    const serialNotUsed=currentTab==='equipment' && ['tv','scala'].includes(spreadsheetInventory.layout?.template) && /^(serial|serial number|s\/n|sn)$/.test(normalizedHeader(header));
    return {source:index,target:matching?.key || (currentTab==='equipment'&&!serialNotUsed&&!/^column\s*\d+$/i.test(header)?'__new':'__skip'),column:matching?structuredClone(matching):{key:'',label:header,type:'text',options:[],important:false,filter:'none',require_confirmation:false}};
  });
  const cached=window.importWorkflow.preferences.mappings;
  if(cached && Object.keys(cached).length){for(let i=decisions.length-1;i>=0;i--)if(decisions[i].target!=='__new' && (decisions[i].target!=='__skip' || window.importWorkflow.preferences.seen_headers?.includes(normalizedHeader(spreadsheetData.headers[decisions[i].source]))))decisions.splice(i,1);}
  if(!decisions.length){$('paste-layout-dialog').close();$('spreadsheet-dialog').showModal();return;}
  pastedFieldSetup={index:0,columns,decisions,file:spreadsheetFile,inventory:spreadsheetInventory,tab:currentTab};
  $('paste-layout-dialog').close();showPastedHeading();$('paste-field-dialog').showModal();
}
function showPastedHeading(){
  const setup=pastedFieldSetup,decision=setup.decisions[setup.index],header=spreadsheetData.headers[decision.source];
  $('paste-field-progress').textContent=`Heading ${setup.index+1} of ${setup.decisions.length}`;
  $('paste-field-title').textContent=header+(spreadsheetData.headers.filter(value=>value===header).length>1?` · source column ${decision.source+1}`:'');
  const samples=[...new Set(spreadsheetData.rows.map(row=>String(row[decision.source] ?? '').trim()).filter(Boolean))];
  $('paste-field-sample').textContent='Examples: '+(samples.slice(0,4).join(' · ') || 'All cells are blank');
  $('paste-field-target').replaceChildren(new Option('Skip this heading','__skip'),...(setup.tab==='equipment'?[new Option('Create a new column','__new')]:[]),...setup.columns.map(column=>new Option(column.label,column.key)));
  $('paste-field-target').value=decision.target;
  $('paste-field-error').hidden=true;renderPastedHeadingControls();
  $('back-paste-field').disabled=setup.index===0;
  $('next-paste-field').textContent=setup.index===setup.decisions.length-1?'Use these fields':'Next heading';
}
function renderPastedHeadingControls(){
  const setup=pastedFieldSetup,decision=setup.decisions[setup.index],column=decision.column;
  const skip=decision.target==='__skip',network=setup.tab!=='equipment';
  $('paste-field-name').value=column.label;$('paste-field-name').disabled=skip||network;
  const dependent=setup.columns.some(col=>col.type==='calculated'&&col.sources?.includes(column.key));
  const types=network?[['text','Text box']]:column.type==='calculated'?[['calculated','Calculated total']]:dependent?[['count',column.minimum===0?'Count dropdown (0–50)':'Count dropdown (1–50)']]:column.key==='notes'?[['text','Text box']]:column.key==='quantity'?[['text','Number input'],['count','Count dropdown (1–50)']]:[['text','Text box'],['buttons','Buttons'],['select','Dropdown list'],['checkbox','Checkbox'],...(!inventoryBaseFields.has(column.key)?[['count','Count dropdown (0–50)']]:[]),...(column.key==='location'?[['location','Imported location choices']]:[])];
  $('paste-field-type').replaceChildren(...types.map(([key,label])=>new Option(label,key)));
  $('paste-field-type').value=column.type;$('paste-field-type').disabled=skip||network||dependent||column.type==='calculated';
  const choices=['select','buttons'].includes(column.type)&&!skip;
  $('paste-field-options-label').hidden=!choices;
  $('paste-field-options').value=(column.options || []).join('\n');
  $('paste-field-confirm').checked=network || !!column.require_confirmation;$('paste-field-confirm').disabled=skip||network;
  $('paste-field-help').textContent=skip?'This source heading will not be mapped to a table column.':network?'AV Devices and IPTV use fixed fields and validation. Every pasted row is confirmed during review.':dependent||column.type==='calculated'?'This field is part of a calculated stock total, so its numeric control is preserved.':'These choices remain a draft until you start importing. Required fields will have a Checked box during import review; they cannot be added automatically.';
}
$('paste-field-target').onchange=()=>{
  const setup=pastedFieldSetup,decision=setup.decisions[setup.index];decision.target=$('paste-field-target').value;
  decision.column=decision.target.startsWith('__')?{key:'',label:spreadsheetData.headers[decision.source],type:'text',options:[],important:false,filter:'none'}:structuredClone(setup.columns.find(column=>column.key===decision.target));renderPastedHeadingControls();
};
$('paste-field-type').onchange=()=>{
  const decision=pastedFieldSetup.decisions[pastedFieldSetup.index];decision.column.label=$('paste-field-name').value;decision.column.require_confirmation=$('paste-field-confirm').checked;decision.column.type=$('paste-field-type').value;
  if(['buttons','select'].includes(decision.column.type)&&!decision.column.options?.length)decision.column.options=[...new Set(spreadsheetData.rows.map(row=>String(row[decision.source]??'').trim()).filter(Boolean))].slice(0,50);
  if(decision.column.type==='count')decision.column.minimum=decision.column.minimum ?? 0;
  renderPastedHeadingControls();
};
function readPastedHeading(){
  const setup=pastedFieldSetup,decision=setup.decisions[setup.index];
  if(decision.target==='__skip')return;
  decision.column.label=$('paste-field-name').value.trim();decision.column.type=$('paste-field-type').value;decision.column.require_confirmation=$('paste-field-confirm').checked;
  if(!decision.column.label)throw new Error('Enter a column name.');
  if(['select','buttons'].includes(decision.column.type)){
    decision.column.options=$('paste-field-options').value.split('\n').map(value=>value.trim()).filter(Boolean);
    if(!decision.column.options.length||decision.column.options.length>50||new Set(decision.column.options.map(value=>value.toLowerCase())).size!==decision.column.options.length)throw new Error('Enter between 1 and 50 distinct choices, one per line.');
  }
}
$('back-paste-field').onclick=()=>{try{readPastedHeading();pastedFieldSetup.index--;showPastedHeading();window.importWorkflow.checkpoint().catch(error=>toast(error.message));}catch(error){$('paste-field-error').textContent=error.message;$('paste-field-error').hidden=false;}};
$('paste-field-form').onsubmit=async event=>{
  event.preventDefault();const setup=pastedFieldSetup;
  try{
    readPastedHeading();
    if(setup.index<setup.decisions.length-1){setup.index++;showPastedHeading();await window.importWorkflow.checkpoint();return;}
    $('next-paste-field').disabled=true;
    const assignments=new Map(window.importWorkflow.preferences.mappings?importFields().map(([key])=>[key,$('map-'+key)?.value || '']):[]),columns=setup.file.from_headers && !setup.file.fields_configured?[]:structuredClone(setup.columns),used=new Set();
    for(const decision of setup.decisions){
      if(decision.target==='__skip')continue;
      const column=structuredClone(decision.column);
      if(decision.target==='__new'){
        const root=column.label.toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_+|_+$/g,'').slice(0,35) || 'field';
        column.key='field_'+root;let number=2;while(columns.some(col=>col.key===column.key))column.key='field_'+root+'_'+number++;
        if(columns.length>=16)throw new Error('An inventory supports up to 16 columns. Skip a heading or match an existing field.');columns.push(column);
      }else{
        if(used.has(column.key))throw new Error(`Two headings use ${column.label}. Go back and skip or change one.`);
        const index=columns.findIndex(col=>col.key===column.key);
        if(index>=0)columns[index]=column;else{if(columns.length>=16)throw new Error('Choose up to 16 columns.');columns.push(column);}
      }
      used.add(column.key);assignments.set(column.key,String(decision.source));
    }
    if(setup.tab==='equipment'){
      if(!columns.length)throw new Error('Use at least one heading for this inventory.');
      const layout={...(setup.inventory.layout || defaultInventoryLayout),columns};
      if(!columns.some(column=>column.key===layout.primary_search))layout.primary_search=columns[0].key;
      if(!columns.some(column=>column.key===layout.identifier))layout.identifier='';
      spreadsheetInventory={...setup.inventory,layout};
    }
    await loadSpreadsheet();
    if(!$('spreadsheet-error').hidden)throw new Error($('spreadsheet-error').textContent);
    importFields().forEach(([key])=>{$('map-'+key).value=assignments.get(key) ?? '';});
    showVenueEditors();showSpreadsheetPreview();
    await window.importWorkflow.checkpoint();
    $('paste-field-dialog').close();
    if(spreadsheetFile.pasted){spreadsheetFile.fields_configured=true;showPastedLayoutSuggestion();$('paste-layout-dialog').showModal();}else $('spreadsheet-dialog').showModal();
    pastedFieldSetup=null;await window.importWorkflow.checkpoint();
  }catch(error){$('paste-field-error').textContent=error.message;$('paste-field-error').hidden=false;}
  finally{$('next-paste-field').disabled=false;}
};
$('close-paste-field').onclick=()=>{if($('next-paste-field').disabled)return;try{readPastedHeading();}catch(_){}$('paste-field-dialog').close();$('paste-layout-dialog').showModal();window.importWorkflow.checkpoint().catch(error=>toast(error.message));};
$('paste-field-dialog').addEventListener('cancel',event=>{if($('next-paste-field').disabled){event.preventDefault();return;}try{readPastedHeading();}catch(_){}$('paste-layout-dialog').showModal();window.importWorkflow.checkpoint().catch(error=>toast(error.message));});
async function startSpreadsheetImport(file,inventory) {
  spreadsheetFile=file;spreadsheetInventory=inventory;spreadsheetData=null;pastedFieldSetup=null;
  $('confirm-import').disabled=true;$('spreadsheet-error').hidden=true;
  await window.importWorkflow.begin(file,inventory);
  if(file.pasted&&spreadsheetInventory)spreadsheetInventory=window.pasteWorkflow.prepareInventory(spreadsheetInventory);
  delete $('header-row').dataset.manual;$('import-sheet-choices').replaceChildren();
  spreadsheetData=null;venueEdits=new Map();skippedImportLocations.clear();$('import-venue-editor').hidden=true;
  $('import-venue-list').replaceChildren();$('header-row').value='1';$('sheet-choice').replaceChildren();$('sheet-choice').disabled=/\.csv$/i.test(file.filename);
  $('column-mappings').replaceChildren();$('spreadsheet-preview').replaceChildren();
  $('spreadsheet-summary').textContent='Reading '+file.filename+'…';
  if(file.pasted || file.from_headers){
    $('paste-preview-settings').hidden=true;$('paste-start-review').hidden=true;$('paste-start-review').disabled=true;$('paste-preview-error').hidden=true;$('paste-preview-help').textContent='';
    $('paste-layout-summary').textContent='Reading the first row and suggesting columns…';
    $('paste-layout-head').replaceChildren();$('paste-layout-rows').replaceChildren();$('paste-layout-unmatched').hidden=true;$('continue-paste-layout').disabled=true;$('keep-paste-layout').disabled=true;
    $('paste-layout-dialog').showModal();
  }else $('spreadsheet-dialog').showModal();
  await loadSpreadsheet();
  if(spreadsheetFile!==file)return;
  if((file.pasted || file.from_headers) && spreadsheetData && $('paste-layout-dialog').open)showPastedLayoutSuggestion();
  else if((file.pasted || file.from_headers) && $('paste-layout-dialog').open){$('paste-layout-dialog').close();$('spreadsheet-dialog').showModal();}
}
let pasteInventory=null,pasteInventorySaving=false,pasteTargetTab=null,pasteFromHeaders=false,pasteSavedPreferences={};
const normalizedLocation=value=>cleanVenue(value).normalize('NFKC').toLocaleLowerCase();
function pasteUsesBatchLocation(inventory){
  if(!inventory)return false;
  const profile=inventory.layout || defaultInventoryLayout,column=profile.columns.find(item=>item.key==='location');
  return !!column&&!['geographic','none'].includes(profile.location_role)&&(profile.location_role==='storage'||column.type==='location'||column.filter==='buttons');
}
function updatePasteContinue(){
  $('continue-paste-inventory').disabled=!$('paste-inventory-text').value.trim();
}
async function openPastedImport(options={}){
  pasteFromHeaders=options.fromHeaders===true;
  try{
    pasteTargetTab=currentTab;
    pasteInventory=currentTab==='equipment'?await window.equipmentUI.waitUntilReady():null;
    pasteSavedPreferences=await api('/api/import-preferences?target='+encodeURIComponent(pasteInventory?`equipment:${pasteInventory.id}`:currentTab));
    await window.importWorkflow.offerResume(pasteInventory?`equipment:${pasteInventory.id}`:currentTab);
    $('paste-inventory-form').reset();
    $('paste-batch-location-options').replaceChildren(...(pasteInventory?window.equipmentUI.locations():[]).map(location=>new Option(location,location)));
    $('paste-inventory-error').hidden=true;$('continue-paste-inventory').disabled=true;
    $('paste-inventory-target').textContent='Import into: '+(pasteInventory?.name || (currentTab==='iptv'?'IPTV Channels':'AV Devices'));
    $('paste-inventory-dialog').showModal();$('paste-inventory-text').focus();
  }catch(error){toast('Could not open pasted import: '+error.message);}
}
$('equipment-paste').onclick=openPastedImport;
$('network-paste').onclick=openPastedImport;
$('paste-inventory-text').oninput=updatePasteContinue;
for(const id of ['close-paste-inventory','cancel-paste-inventory'])$(id).onclick=()=>{if(!pasteInventorySaving)$('paste-inventory-dialog').close();};
$('paste-inventory-dialog').addEventListener('cancel',event=>{if(pasteInventorySaving)event.preventDefault();});
let pendingPastedBatch=null;
async function continuePastedBatch(file,inventory,enteredLocation=''){
  const forceLocation=pasteUsesBatchLocation(inventory),location=forceLocation?cleanVenue(enteredLocation):'';
  if(forceLocation&&!location)throw new Error('Enter the location for these items.');
  const existing=(inventory?window.equipmentUI.locations():[]).find(saved=>normalizedLocation(saved)===normalizedLocation(location));
  file.default_location=existing || location;file.force_location=forceLocation;
  file.confirmation_mode=inventory?.layout?.confirmation_mode || pasteSavedPreferences.confirmation_mode || (inventory?(inventory.layout?.show_status===false?'none':'storage'):currentTab==='device'?'ip':'none');
  const target=inventory?{...inventory,layout:{...(inventory.layout || defaultInventoryLayout),confirmation_mode:file.confirmation_mode,show_status:file.confirmation_mode!=='none'}}:null;
  await startSpreadsheetImport(file,target);
}
$('paste-inventory-form').onsubmit=async event=>{
  event.preventDefault();if(pasteInventorySaving)return;
  $('paste-inventory-error').hidden=true;pasteInventorySaving=true;$('continue-paste-inventory').disabled=true;
  try{
    if(currentTab!==pasteTargetTab)throw new Error('The destination changed. Close this dialog and paste again.');
    const text=$('paste-inventory-text').value;
    if(!text.trim())throw new Error('Paste your spreadsheet cells, including the header row.');
    const blob=new Blob([text],{type:'text/csv;charset=utf-8'});
    if(blob.size>5_000_000)throw new Error('Paste a smaller range, up to 5 MB.');
    const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Could not read the pasted cells.'));reader.readAsDataURL(blob);});
    const sourceLabel=$('paste-inventory-sheet').value.trim();
    const file={filename:(sourceLabel || 'Pasted spreadsheet')+'.csv',content,pasted:true,from_headers:pasteFromHeaders,source_label:sourceLabel,...(text.includes('\t')?{delimiter:'\t'}:{})};
    $('paste-inventory-dialog').close();
    if(pasteUsesBatchLocation(pasteInventory)){
      pendingPastedBatch={file,inventory:pasteInventory};$('paste-batch-location').value='';$('paste-location-error').hidden=true;$('paste-location-dialog').showModal();$('paste-batch-location').focus();
    }else await continuePastedBatch(file,pasteInventory);
  }catch(error){$('paste-inventory-error').textContent=error.message;$('paste-inventory-error').hidden=false;}
  finally{pasteInventorySaving=false;updatePasteContinue();}
};
$('paste-location-form').onsubmit=async event=>{
  event.preventDefault();if(!pendingPastedBatch)return;
  const button=$('continue-paste-location');button.disabled=true;$('paste-location-error').hidden=true;
  try{const pending=pendingPastedBatch,location=$('paste-batch-location').value;$('paste-location-dialog').close();await continuePastedBatch(pending.file,pending.inventory,location);pendingPastedBatch=null;}
  catch(error){$('paste-location-error').textContent=error.message;$('paste-location-error').hidden=false;if(!$('paste-location-dialog').open)$('paste-location-dialog').showModal();}
  finally{button.disabled=false;}
};
$('back-paste-location').onclick=()=>{$('paste-location-dialog').close();pendingPastedBatch=null;$('paste-inventory-dialog').showModal();$('paste-inventory-text').focus();};
$('close-paste-location').onclick=()=>{$('paste-location-dialog').close();pendingPastedBatch=null;};
let pendingPasteConfirmation=null;
function openPasteConfirmation(file,inventory){
  pendingPasteConfirmation={file,inventory,tab:currentTab};
  const options=[['none','No confirmation needed'],['ip','Confirm IP — check the network address afterward'],...(inventory?[['storage','Storage — To be found / Located afterward']]:[])];
  $('paste-confirmation-mode').replaceChildren(...options.map(([value,label])=>new Option(label,value)));
  $('paste-confirmation-mode').value=inventory?(inventory.layout?.confirmation_mode || (inventory.layout?.show_status===false?'none':'storage')):currentTab==='device'?'ip':'none';
  $('paste-confirmation-target').textContent='Import into: '+(inventory?.name || (currentTab==='iptv'?'IPTV Channels':'AV Devices'));
  $('paste-confirmation-help').textContent=inventory?'This setting will apply to this inventory when import starts. Changing the workflow resets existing confirmation marks. Closing the draft keeps your current settings.':'This choice applies to records added in this paste. Existing records keep their current workflow.';
  $('paste-confirmation-error').hidden=true;$('paste-confirmation-dialog').showModal();
}
$('back-paste-confirmation').onclick=()=>{if($('continue-paste-confirmation').disabled)return;$('paste-confirmation-dialog').close();pendingPasteConfirmation=null;$('paste-inventory-dialog').showModal();};
$('close-paste-confirmation').onclick=()=>{if(!$('continue-paste-confirmation').disabled){$('paste-confirmation-dialog').close();pendingPasteConfirmation=null;}};
$('paste-confirmation-dialog').addEventListener('cancel',event=>{if($('continue-paste-confirmation').disabled)event.preventDefault();else pendingPasteConfirmation=null;});
$('paste-confirmation-form').onsubmit=async event=>{
  event.preventDefault();const pending=pendingPasteConfirmation;if(!pending||$('continue-paste-confirmation').disabled)return;
  $('continue-paste-confirmation').disabled=true;$('paste-confirmation-error').hidden=true;
  try{
    if(currentTab!==pending.tab)throw new Error('The destination changed. Paste again into the correct list.');
    const mode=$('paste-confirmation-mode').value;pending.file.confirmation_mode=mode;
    if(pending.inventory){
      const layout={...(pending.inventory.layout || defaultInventoryLayout),confirmation_mode:mode,show_status:mode!=='none'};
      pending.inventory={...pending.inventory,layout};
    }
    $('paste-confirmation-dialog').close();pendingPasteConfirmation=null;await startSpreadsheetImport(pending.file,pending.inventory);
  }catch(error){$('paste-confirmation-error').textContent=error.message;$('paste-confirmation-error').hidden=false;}
  finally{$('continue-paste-confirmation').disabled=false;}
};
$('import').onclick = openPastedImport;
$('upload-paste-inventory').onclick=()=>{if(pasteInventorySaving)return;$('paste-inventory-dialog').close();$('import-file').click();};
$('import-file').onchange = async event => {
  const file = event.target.files[0]; if (!file) return;
  $('confirm-import').disabled=true;
  $('import').disabled = true;
  try {
    const importTab = currentTab;
    const importInventory = importTab === 'equipment' ? await window.equipmentUI.waitUntilReady() : null;
    if (file.size > 5_000_000) throw new Error('Choose a file smaller than 5 MB.');
    if (/\.(xlsx|csv)$/i.test(file.name)) {
      const content = await new Promise((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = () => reject(new Error('Could not read file.')); reader.readAsDataURL(file);
      });
      await startSpreadsheetImport({filename:file.name,content,from_headers:pasteFromHeaders},importInventory);
    } else if (/\.json$/i.test(file.name)) {
      const payload = JSON.parse(await file.text());
      if (importInventory && payload && typeof payload === 'object' && !Array.isArray(payload)) payload.inventory_id = importInventory.id;
      const result = await api(importTab === 'equipment' ? '/api/equipment/import' : '/api/import', 'POST', payload);
      if (currentTab === 'device') importWarnings = result.warnings || [];
      toast(`Imported ${result.added} records. Skipped ${result.skipped} existing assignments.`);
      await load();
    } else throw new Error('Choose .xlsx, .csv, or an avtrack .json export.');
  } catch(error) { toast('Import failed: ' + error.message); }
  finally { event.target.value = ''; $('import').disabled = false; }
};
load();

if (location.hostname.endsWith('.app.github.dev')) {
  $('broadcastgab-cache-status').textContent='Saved homepage · offline cache available when hosted locally';
} else if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/service-worker.js').then(() => navigator.serviceWorker.ready).then(() => {
    $('broadcastgab-offline-link').title = 'Saved BroadcastGab copy · available offline';
    $('broadcastgab-cache-status').textContent = 'Available offline';
  }).catch(() => {
    $('broadcastgab-offline-link').title = 'Saved copy · offline storage unavailable in this browser';
    $('broadcastgab-cache-status').textContent = 'Offline storage unavailable';
  });
} else {
  $('broadcastgab-cache-status').textContent = 'Offline storage requires HTTPS and a supported browser';
}
