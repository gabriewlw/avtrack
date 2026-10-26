/* Full-workspace transfers are independent of individual tab import/export filters. */
(() => {
  const get=id=>document.getElementById(id);
  let restoring=false,previewedFile=null,previewSequence=0;
  get('workspace-restore-open').onclick=()=>{
    get('workspace-export-menu').open=false;
    get('workspace-restore-form').reset();previewedFile=null;get('workspace-restore-submit').disabled=true;get('workspace-restore-preview').hidden=true;
    api('/api/workspace/recovery').then(data=>{const list=get('workspace-recovery-list');list.replaceChildren();if(data.backups.length){const title=document.createElement('h3');title.textContent='Recovery backups · automatic import saves and pre-restore copies';list.append(title);data.backups.slice(0,8).forEach(backup=>{const link=document.createElement('a');link.href='/api/workspace/recovery?file='+encodeURIComponent(backup.name);link.download=backup.name;link.textContent=backup.name;list.append(link,document.createElement('br'));});}}).catch(()=>{});
    get('workspace-restore-error').hidden=true;
    get('workspace-restore-status').textContent='';
    get('workspace-restore-dialog').showModal();
  };
  get('workspace-export-menu').querySelectorAll('a[download]').forEach(link=>link.addEventListener('click',async event=>{
    event.preventDefault();
    if(link.getAttribute('aria-disabled')==='true')return;
    link.setAttribute('aria-disabled','true');
    try{
      if(document.activeElement?.matches('.device-notes-editor'))document.activeElement.blur();
      await Promise.all([...pendingNoteSaves.values(),...pendingWrites]);
      await window.equipmentUI?.flush();
      const response=await fetch(link.href);
      if(!response.ok)throw new Error((await response.json()).error || 'Could not export all data.');
      const url=URL.createObjectURL(await response.blob());
      const download=document.createElement('a');download.href=url;
      download.download=response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || 'avtrack-all-data.zip';
      document.body.append(download);download.click();download.remove();
      setTimeout(()=>URL.revokeObjectURL(url),60000);
    }catch(failure){toast(failure.message);}
    finally{link.removeAttribute('aria-disabled');}
  }));
  get('workspace-restore-cancel').onclick=()=>{if(!restoring)get('workspace-restore-dialog').close();};
  get('workspace-restore-dialog').addEventListener('cancel',event=>{if(restoring)event.preventDefault();});
  get('workspace-restore-file').onchange=async()=>{
    const file=get('workspace-restore-file').files[0],sequence=++previewSequence;previewedFile=null;get('workspace-restore-submit').disabled=true;get('workspace-restore-preview').hidden=true;get('workspace-restore-error').hidden=true;
    if(!file)return;
    if(file.size>200000000){get('workspace-restore-error').textContent='Choose a backup smaller than 200 MB.';get('workspace-restore-error').hidden=false;return;}
    get('workspace-restore-status').textContent='Checking backup contents. Current records remain unchanged…';
    try{
      const response=await fetch('/api/workspace/preview',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});const result=await response.json();if(!response.ok)throw new Error(result.error||'Could not read this backup.');if(sequence!==previewSequence)return;
      const panel=get('workspace-restore-preview');panel.replaceChildren();const title=document.createElement('h3');title.textContent='Backup contents — review before replacing data';panel.append(title);
      for(const text of [`Created: ${result.exported_at}`,`Application: ${result.app_version} · backup format ${result.format_version}`,result.migration_required?`Compatible older backup — data schema ${result.source_schema_version} will be upgraded automatically to ${result.schema_version}.`:`Compatible backup — data schema ${result.schema_version}.`,`${result.devices} devices · ${result.iptv} IPTV channels · ${result.equipment} inventory records`,`${result.backup_records} backups · ${result.files} attached files`,`Inventories: ${result.inventories.join(', ')}`, 'A recovery backup of the current app will be saved automatically before replacement.']){const line=document.createElement('p');line.textContent=text;panel.append(line);}
      panel.hidden=false;previewedFile=file;get('workspace-restore-submit').disabled=false;
    }catch(error){if(sequence===previewSequence){get('workspace-restore-error').textContent=error.message;get('workspace-restore-error').hidden=false;}}
    finally{if(sequence===previewSequence)get('workspace-restore-status').textContent='';}
  };
  get('workspace-restore-form').onsubmit=async event=>{
    event.preventDefault();
    if(restoring || !get('workspace-restore-replace').checked)return;
    const file=get('workspace-restore-file').files[0];
    if(!file||file!==previewedFile)return;
    const error=get('workspace-restore-error');error.hidden=true;
    if(file.size>200000000){error.textContent='Choose a complete backup smaller than 200 MB.';error.hidden=false;return;}
    restoring=true;
    const controls=[...get('workspace-restore-form').querySelectorAll('button,input')];
    controls.forEach(control=>control.disabled=true);
    get('workspace-restore-status').textContent='Restoring all workspaces. Keep this page open…';
    try{
      await Promise.all([...pendingNoteSaves.values(),...pendingWrites]);await window.equipmentUI?.flush();
      const response=await fetch('/api/workspace/restore',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-AVTrack-Restore':'replace-all'},body:file});
      const result=await response.json();
      if(!response.ok)throw new Error(result.error || 'The backup could not be restored.');
      // Reload every workspace and discard selections that referred to the old data.
      try{localStorage.removeItem('avtrack-equipment-inventory');}catch(_){}
      window.location.assign('/');
    }catch(failure){error.textContent=failure.message;error.hidden=false;get('workspace-restore-status').textContent='';}
    finally{restoring=false;controls.forEach(control=>control.disabled=false);get('workspace-restore-submit').disabled=!previewedFile;}
  };
})();
