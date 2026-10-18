/* Full-workspace transfers are independent of individual tab import/export filters. */
(() => {
  const get=id=>document.getElementById(id);
  let restoring=false;
  get('workspace-restore-open').onclick=()=>{
    get('workspace-export-menu').open=false;
    setNavigationOpen(false);
    get('workspace-restore-form').reset();
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
  get('workspace-restore-form').onsubmit=async event=>{
    event.preventDefault();
    if(restoring || !get('workspace-restore-replace').checked)return;
    const file=get('workspace-restore-file').files[0];
    if(!file)return;
    const error=get('workspace-restore-error');error.hidden=true;
    if(file.size>200000000){error.textContent='Choose a complete backup smaller than 200 MB.';error.hidden=false;return;}
    restoring=true;
    const controls=[...get('workspace-restore-form').querySelectorAll('button,input')];
    controls.forEach(control=>control.disabled=true);
    get('workspace-restore-status').textContent='Restoring all workspaces. Keep this page open…';
    try{
      const response=await fetch('/api/workspace/restore',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-AVTrack-Restore':'replace-all'},body:file});
      const result=await response.json();
      if(!response.ok)throw new Error(result.error || 'The backup could not be restored.');
      // Reload every workspace and discard selections that referred to the old data.
      try{localStorage.removeItem('avtrack-equipment-inventory');}catch(_){}
      window.location.assign('/');
    }catch(failure){error.textContent=failure.message;error.hidden=false;get('workspace-restore-status').textContent='';}
    finally{restoring=false;controls.forEach(control=>control.disabled=false);}
  };
})();
