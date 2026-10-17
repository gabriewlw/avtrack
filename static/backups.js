'use strict';
(() => {
  let backups = [], deleting = null, loaded = false, folderInfo = null;
  const form = $('backup-form');
  const dialog = $('backup-dialog');
  const deleteDialog = $('delete-backup-dialog');
  const formatSize = size => size < 1024 ? `${size} B` : size < 1024 * 1024 ? `${(size / 1024).toFixed(size < 10240 ? 1 : 0)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`;
  const formatDate = value => new Intl.DateTimeFormat(undefined, {dateStyle:'medium', timeStyle:'short'}).format(new Date(value.replace(' ', 'T') + (value.includes('Z') ? '' : 'Z')));
  const typeMark = type => ({Videohub:'VH', ATEM:'AT', 'Satellite receiver':'SAT', 'OBS profile':'OBS', Other:'AV'})[type] || 'AV';

  function render() {
    const filter = $('backup-filter').value;
    const query = $('backup-search').value.trim().toLocaleLowerCase();
    const visible = backups.filter(item => (!filter || item.equipment_type === filter) && (!query || [item.equipment_type,item.device_name,item.filename,item.notes].some(value => (value || '').toLocaleLowerCase().includes(query))));
    $('backup-count').textContent = backups.length;
    $('backup-type-count').textContent = new Set(backups.map(item => item.equipment_type)).size;
    $('backup-size').textContent = formatSize(backups.reduce((total, item) => total + item.size, 0));
    $('backups-empty').hidden = backups.length !== 0 || Boolean(filter || query);
    $('backups-grid').replaceChildren(...visible.map(item => {
      const card = element('article', 'backup-card');
      const top = element('div', 'backup-card-top');
      const badge = element('span', 'backup-type');
      if(item.has_icon){
        const icon=element('img','backup-custom-icon');icon.src=`/api/backups/${item.id}/icon`;icon.alt='';
        badge.append(icon,document.createTextNode(item.equipment_type));
      }else badge.append(element('b', '', typeMark(item.equipment_type)), document.createTextNode(item.equipment_type));
      top.append(badge, element('time', '', formatDate(item.created_at)));
      const name = element('h3', '', item.device_name);
      const file = element('div', 'backup-file');
      file.append(element('span', 'backup-file-icon', '↧'), element('span', 'backup-filename', item.filename), element('small', '', formatSize(item.size)));
      card.append(top, name, file);
      if (item.notes) card.append(element('p', 'backup-notes', item.notes));
      const actions = element('div', 'backup-actions');
      const download = element('a', 'primary compact', 'Download');
      download.href = `/api/backups/${item.id}/download`; download.download = item.filename;
      const remove = element('button', 'icon-button danger-icon backup-delete-action');
      remove.type = 'button'; remove.title = 'Delete backup'; remove.setAttribute('aria-label', `Delete ${item.filename}`);
      remove.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5M14 11v5"/></svg>';
      remove.onclick = () => {
        deleting = item;
        $('delete-backup-description').textContent = `${item.device_name} · ${item.filename}`;
        $('delete-backup-error').hidden = true;
        deleteDialog.showModal();
      };
      actions.append(download, remove); card.append(actions); return card;
    }));
    if (backups.length && !visible.length) $('backups-grid').append(element('p', 'backup-no-results', 'No backups match these filters.'));
  }

  async function load(force = false) {
    if (loaded && !force) { render(); return; }
    $('refresh-backups').disabled = true;
    try {
      const result = await api('/api/backups');backups = result.backups;folderInfo=result.folder;
      $('backup-folder-path').textContent=`Backup folder · ${folderInfo.path}`;
      $('open-backup-folder').textContent=folderInfo.can_open?'Open backup folder':'Copy backup folder path';
      loaded = true; $('backups-error').hidden = true; render();
    } catch (error) {
      $('backups-error').textContent = `Could not load backups. ${error.message}`;
      $('backups-error').hidden = false;
    } finally { $('refresh-backups').disabled = false; }
  }
  function open() {
    form.reset(); $('backup-form-error').hidden = true; dialog.showModal(); $('backup-type').focus();
  }
  const fileContent = file => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1] || '');
    reader.onerror = () => reject(new Error('The selected file could not be read.'));
    reader.readAsDataURL(file);
  });
  form.onsubmit = async event => {
    event.preventDefault();
    const file = $('backup-file').files[0];
    const icon = $('backup-icon').files[0];
    if (!file) return;
    const submit = $('save-backup'); submit.disabled = true; $('backup-form-error').hidden = true;
    try {
      if (file.size > 25_000_000) throw new Error('Choose a file no larger than 25 MB.');
      if(icon && (!['image/png','image/jpeg','image/webp'].includes(icon.type) || icon.size > 1_000_000)) throw new Error('Choose a PNG, JPEG, or WebP icon no larger than 1 MB.');
      await api('/api/backups', 'POST', {equipment_type:$('backup-type').value, device_name:$('backup-device').value, filename:file.name, content:await fileContent(file), icon:icon?{mime_type:icon.type,content:await fileContent(icon)}:null, notes:$('backup-notes').value});
      dialog.close(); loaded = false; await load(); await loadOverview(); toast('Backup saved.');
    } catch (error) {
      $('backup-form-error').textContent = error.message; $('backup-form-error').hidden = false;
    } finally { submit.disabled = false; }
  };
  $('confirm-delete-backup').onclick = async () => {
    if (!deleting) return;
    const button = $('confirm-delete-backup'); button.disabled = true;
    try {
      await api(`/api/backups/${deleting.id}`, 'DELETE', {});
      backups = backups.filter(item => item.id !== deleting.id); deleteDialog.close(); deleting = null; render(); await loadOverview(); toast('Backup deleted.');
    } catch (error) {
      $('delete-backup-error').textContent = error.message; $('delete-backup-error').hidden = false;
    } finally { button.disabled = false; }
  };
  $('add-backup').onclick = $('backups-empty-add').onclick = open;
  $('close-backup').onclick = $('cancel-backup').onclick = () => dialog.close();
  $('cancel-delete-backup').onclick = () => deleteDialog.close();
  $('backup-filter').onchange = $('backup-search').oninput = render;
  $('refresh-backups').onclick = () => load(true);
  $('open-backup-folder').onclick = async () => {
    if(!folderInfo)return;
    if(folderInfo.can_open){
      try{await api('/api/backups/open-folder','POST',{});toast('Backup folder opened.');}
      catch(error){toast('Could not open the backup folder: '+error.message);}
      return;
    }
    try{await navigator.clipboard.writeText(folderInfo.path);toast('Backup folder path copied.');}
    catch(_){toast(`Backup folder: ${folderInfo.path}`);}
  };
  window.backupsUI = {load, open};
})();
