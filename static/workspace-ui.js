/* Desktop file drops and a deliberate editor for device/channel notes. */
window.workspaceUI=(()=>{
  const get=id=>document.getElementById(id);
  let notesTarget=null,notesSaving=false,notesSequence=0;
  const notesDialog=get('device-notes-dialog'),notesText=get('device-notes-text'),notesSave=get('save-device-notes');
  async function openDeviceNotes(id){
    const record=devices.find(row=>row.id===id);if(!record)return;
    const sequence=++notesSequence;notesTarget=null;notesText.value=record.notes||'';notesText.disabled=true;notesSave.disabled=true;
    get('device-notes-caption').textContent=record.name||record.ip||'Incomplete record';get('device-notes-error').hidden=true;notesDialog.showModal();
    try{
      await pendingNoteSaves.get(id);
      const data=await api('/api/desktop/record?kind='+encodeURIComponent(record.record_type||'device')+'&id='+id);
      if(sequence!==notesSequence||!notesDialog.open)return;
      notesTarget=data.record;notesText.value=notesTarget.notes||'';notesSave.disabled=false;
    }catch(error){if(sequence===notesSequence){get('device-notes-error').textContent=error.message;get('device-notes-error').hidden=false;}}
    finally{if(sequence===notesSequence){notesText.disabled=false;notesText.focus();}}
  }
  for(const id of ['close-device-notes','cancel-device-notes'])get(id).onclick=()=>{if(!notesSaving)notesDialog.close();};
  notesDialog.addEventListener('close',()=>{notesSequence++;notesTarget=null;});
  notesDialog.addEventListener('cancel',event=>{if(notesSaving)event.preventDefault();});
  get('device-notes-form').onsubmit=async event=>{
    event.preventDefault();if(notesSaving||!notesTarget)return;
    notesSaving=true;get('device-notes-error').hidden=true;
    const controls=[...get('device-notes-form').querySelectorAll('button,textarea')];controls.forEach(control=>control.disabled=true);
    try{
      const updated=await saveNotes(notesTarget.id,notesText.value,notesTarget.notes||'');
      devices=devices.map(row=>row.id===updated.id?updated:row);render();notesDialog.close();toast('Notes updated.');
    }catch(error){get('device-notes-error').textContent=error.message;get('device-notes-error').hidden=false;}
    finally{notesSaving=false;controls.forEach(control=>control.disabled=false);}
  };
  const hasFiles=event=>Array.from(event.dataTransfer?.types||[]).includes('Files');
  function assignFile(input,file){const transfer=new DataTransfer();transfer.items.add(file);input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));}
  function bindDrop(target,highlight,receive){
    target.dataset.fileDropTarget='true';
    target.addEventListener('dragover',event=>{if(!hasFiles(event))return;event.preventDefault();event.stopPropagation();event.dataTransfer.dropEffect='copy';highlight.classList.add('file-drop-active');});
    target.addEventListener('dragleave',event=>{if(!target.contains(event.relatedTarget))highlight.classList.remove('file-drop-active');});
    target.addEventListener('drop',event=>{if(!hasFiles(event))return;event.preventDefault();event.stopPropagation();highlight.classList.remove('file-drop-active');const files=event.dataTransfer.files;if(files.length!==1){toast('Drop one file at a time.');return;}receive(files[0]);});
  }
  function importFile(file){
    if(get('import').disabled){toast('Wait for the current import to finish reading.');return;}
    if(!/\.(csv|xlsx|json)$/i.test(file.name)){toast('Choose CSV, XLSX, or AVTrack record JSON. Use Restore app backup for a complete ZIP.');return;}
    if(file.size>5_000_000){toast('Choose a file smaller than 5 MB.');return;}
    get('paste-inventory-dialog').close();pasteFromHeaders=false;assignFile(get('import-file'),file);
  }
  for(const [panel,zone] of [['inventory','network-drop-zone'],['equipment-panel','inventory-drop-zone']]){
    const hint=get(zone);bindDrop(get(panel),hint,importFile);hint.onclick=()=>get('import-file').click();hint.onkeydown=event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();hint.click();}};
  }
  bindDrop(get('paste-inventory-dialog'),get('paste-inventory-dialog'),importFile);
  const backupZone=get('backups-drop-zone');
  bindDrop(get('backups-panel'),backupZone,file=>{if(file.size>25_000_000){toast('Choose a file no larger than 25 MB.');return;}window.backupsUI.open();assignFile(get('backup-file'),file);get('backup-device').value=file.name.replace(/\.[^.]+$/,'').slice(0,120);});
  backupZone.onclick=()=>{window.backupsUI.open();get('backup-file').click();};backupZone.onkeydown=event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();backupZone.click();}};
  for(const id of ['backup-file','backup-icon','workspace-restore-file']){
    const input=get(id),label=input.closest('label');bindDrop(label,label,file=>{if(input.disabled)return;assignFile(input,file);});
  }
  document.addEventListener('dragover',event=>{if(hasFiles(event))event.preventDefault();});
  document.addEventListener('drop',event=>{if(!hasFiles(event))return;event.preventDefault();document.querySelectorAll('.file-drop-active').forEach(node=>node.classList.remove('file-drop-active'));if(!event.target.closest('[data-file-drop-target]'))toast('Drop the file into the destination workspace or its upload field.');});
  return {openDeviceNotes};
})();
