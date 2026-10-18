/* Desktop consultation, drafts, review safety, and supervisor tools. */
window.desktopUI=(()=>{
  const get=id=>document.getElementById(id);
  const node=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!=null)el.textContent=text;return el;};
  const button=(label,action,cls='secondary')=>{const el=node('button',cls,label);el.type='button';el.onclick=action;return el;};
  const date=value=>value?new Date(value).toLocaleString():'Not recorded';
  const drafts=new WeakMap(),draftDefaults=new WeakMap();let newInventory=null,backupId=null,searchRecords=[];
  function initials(){try{return localStorage.getItem('avtrack-reviewer')||'';}catch(_){return '';}}
  function values(form){return Object.fromEntries([...new FormData(form)].filter(([key,value])=>typeof value==='string'&&key).concat([...form.querySelectorAll('[data-draft-field]')].map(control=>['@'+control.dataset.draftField,control.value])));}
  function restoreDraft(form,key){
    if(!key){drafts.delete(form);return;}
    const storageKey='avtrack-draft-'+key;drafts.set(form,storageKey);draftDefaults.set(form,JSON.stringify(values(form)));
    try{const saved=JSON.parse(sessionStorage.getItem(storageKey)||'null');if(saved){for(const [name,value] of Object.entries(saved)){const control=name.startsWith('@')?[...form.querySelectorAll('[data-draft-field]')].find(input=>input.dataset.draftField===name.slice(1)):form.elements.namedItem(name);if(control&&control.type!=='file'){if(control.tagName==='SELECT'&&value&&![...control.options].some(option=>option.value===value))control.add(new Option(value,value));control.value=value;}}toast('Your unsaved draft was restored.');}}catch(_){}
    if(!form.dataset.draftListener){form.dataset.draftListener='true';const persist=()=>{const key=drafts.get(form);if(key)try{const saved=JSON.stringify(values(form));if(saved===draftDefaults.get(form))sessionStorage.removeItem(key);else sessionStorage.setItem(key,saved);}catch(_){}};form.addEventListener('input',persist);form.addEventListener('change',persist);form.closest('dialog').addEventListener('close',persist);}
  }
  function clearDraft(form){const key=drafts.get(form);if(key)try{sessionStorage.removeItem(key);}catch(_){}drafts.delete(form);}
  function offerIncomplete(){let el=get('save-incomplete-device');if(!el){el=button('Save as incomplete',()=>{get('device-form').dataset.allowIncomplete='true';get('device-form').requestSubmit();});el.id='save-incomplete-device';get('form-error').after(el);}el.hidden=false;}
  async function offerDuplicate(ip){
    if(!ip)return;let records;try{records=(await api('/api/devices')).devices.filter(record=>record.ip===ip&&record.record_type===currentTab);}catch(_){return;}if(!records.length)return;
    let el=get('view-duplicate-device');if(el)el.remove();el=button('View existing device',()=>openRecord(records[0].record_type,records[0].id));el.id='view-duplicate-device';get('form-error').after(el);
  }
  function chooseInventoryStart(inventory){newInventory=inventory;get('inventory-start-caption').textContent=`${inventory.name} is ready. Add an item manually or import a table.`;get('inventory-start-dialog').showModal();}
  function prepareUnitRemoval(item){
    const choices=get('equipment-delete-unit'),submit=get('confirm-equipment-delete');let explanation=get('unit-removal-impact');
    if(!explanation){explanation=node('p','dialog-intro');explanation.id='unit-removal-impact';choices.closest('label').after(explanation);const label=node('label','', 'Reason (optional)'),input=node('input');input.id='unit-removal-reason';input.maxLength=1000;label.append(input);explanation.after(label);}
    get('unit-removal-reason').value='';
    const update=()=>{const unit=choices.value;submit.disabled=!unit;submit.textContent=unit==='all'?'Delete entire record':'Remove chosen unit';explanation.textContent=!unit?'Choose a unit or the entire record.':unit==='all'?`This deletes the entire record and all ${item.quantity??'unknown'} units.`:`Remove ${unit==='unserialized'?'one unit without a serial':unit.slice(7)}. Quantity will change from ${item.quantity} to ${item.quantity-1}.`;};choices.onchange=update;update();
  }
  function renderFilters(){
    for(const [container,fields] of [['network-filters',['venue-filter','system-filter','source-filter']],['equipment-panel',['equipment-location-filter','equipment-status-filter','equipment-review-filter']]]){
      const host=container==='equipment-panel'?get(container).querySelector('.equipment-filters'):get(container);if(!host)continue;let bar=host.querySelector('.active-filter-chips');if(!bar){bar=node('div','active-filter-chips');host.append(bar);}bar.replaceChildren();
      fields.forEach(id=>{const control=get(id);if(!control?.value)return;const label=control.selectedOptions?.[0]?.textContent || control.value;bar.append(button(label+' ×',()=>{control.value='';control.dispatchEvent(new Event('change',{bubbles:true}));}));});
    }
  }
  async function openRecord(kind,id){
    const dialog=get('desktop-record-dialog'),body=get('desktop-record-body');get('desktop-record-title').textContent='Record details';body.replaceChildren(node('p','','Loading…'));if(!dialog.open)dialog.showModal();
    try{
      const data=await api(`/api/desktop/record?kind=${encodeURIComponent(kind)}&id=${id}`),record=data.record;
      get('desktop-record-title').textContent=record.name || record.description || record.model || record.serial_number || 'Incomplete record';body.replaceChildren();
      const list=node('dl','record-detail-grid');
      for(const [key,value] of Object.entries(record)){
        if(['id','record_type','custom_values','inventory_id','confirmation_required'].includes(key)||value==null||value==='')continue;
        let text=String(value);if(['ip_confirmed','item_confirmed','data_checked'].includes(key))text=value?'Yes — manually checked':'Not checked';
        list.append(node('dt','',({ip_confirmed:'IP manually verified',item_confirmed:'Physically located',data_checked:'Record reviewed',last_checked_at:'Last physical count',data_checked_at:'Last source review',updated_at:'Last record change'})[key] || key.replaceAll('_',' ')));
        const cell=node('dd',key==='notes'?'record-full-notes':'',text);if(['ip','serial_number','location'].includes(key))cell.append(button('Copy',async()=>{try{await navigator.clipboard.writeText(String(value));toast('Copied.');}catch(_){toast('Select the value to copy it.');}},'quiet'));list.append(cell);
      }
      for(const [key,value] of Object.entries(record.custom_values||{}))list.append(node('dt','',key.replaceAll('_',' ')),node('dd','',value));body.append(list);
      body.append(node('h3','','Related equipment backups'));
      if(!data.backups.length)body.append(node('p','','No equipment backup is linked. Use Recovery details in Equipment backups to link one.'));
      data.backups.forEach(backup=>{const row=node('p','',`${backup.device_name} · ${backup.filename} · ${(backup.recovery.state||'untested').replaceAll('_',' ')}`),download=node('a','', 'Download configuration');download.href=`/api/backups/${backup.id}/download`;download.download=backup.filename;row.append(download);body.append(row);});
      body.append(node('h3','','Import source and changes'));
      if(!data.imports.length)body.append(node('p','','No tracked import source for this record. Older records may predate source tracking.'));
      data.imports.forEach(source=>{const row=node('p','',`${source.name} · ${source.sheet||'Pasted table'} · source rows ${source.keys.map(key=>key.split(':').pop()).join(', ')} · ${date(source.imported_at)}`);row.append(button('Open source report',async()=>{const report=await api('/api/import-sessions/'+source.session_id);const link=node('a');link.href=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));link.download='avtrack-source-report.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);},'quiet'));body.append(row);});
      body.append(node('h3','','Verification and stock movement history'));
      if(!data.history.length&&!data.checks?.length)body.append(node('p','','No verification or movement history recorded.'));
      data.history.forEach(event=>body.append(node('p','history-entry',`${date(event.created_at)} · ${event.action.replaceAll('_',' ')} · ${Object.entries(event.details).map(([key,value])=>`${key.replaceAll('_',' ')}: ${value}`).join(' · ')}`)));
      if(!data.history.length)data.checks?.forEach(check=>body.append(node('p','',date(check.checked_at)+' · Legacy check (reviewer not recorded)')));
    }catch(error){body.replaceChildren(node('p','error',error.message));}
  }
  function attachDetails(){
    get('device-list').querySelectorAll('.device-row').forEach(row=>{const id=row.querySelector('.row-select')?.dataset.recordId,name=row.querySelector('.device-name');if(!id||!name||name.dataset.details)return;name.dataset.details='true';name.tabIndex=0;name.role='button';name.classList.add('details-trigger');name.title='View full details and recovery files';name.onclick=()=>openRecord(currentTab,Number(id));name.onkeydown=event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();name.click();}};});
    get('equipment-rows').querySelectorAll('tr').forEach(row=>{const actions=row.querySelector('.equipment-actions');if(!actions||actions.querySelector('.record-details-button'))return;const details=button('Details',()=>openRecord('equipment',Number(row.dataset.itemId)),'quiet record-details-button');details.setAttribute('aria-label','View equipment details');actions.prepend(details);});
  }
  async function findAnywhere(){
    const dialog=get('desktop-search-dialog');get('desktop-search-input').value='';get('desktop-search-results').textContent='Loading records…';dialog.showModal();
    try{searchRecords=(await api('/api/desktop/records')).records;const backups=(await api('/api/backups')).backups;searchRecords.push(...backups.map(row=>({...row,kind:'backup',label:row.device_name})));renderSearch();get('desktop-search-input').focus();}catch(error){get('desktop-search-results').textContent=error.message;}
  }
  function renderSearch(){
    const query=get('desktop-search-input').value.trim().toLowerCase(),results=get('desktop-search-results');results.replaceChildren();
    const found=searchRecords.filter(row=>JSON.stringify(row).toLowerCase().includes(query));results.append(node('p','',`${found.length} results across all workspaces`));
    const groups=new Map();found.slice(0,200).forEach(row=>{const title=row.kind==='equipment'?'Inventory · '+row.inventory_name:row.kind==='backup'?'Equipment backups':row.kind==='iptv'?'IPTV':'Devices';if(!groups.has(title))groups.set(title,[]);groups.get(title).push(row);});
    for(const [title,rows] of groups){results.append(node('h3','',title));rows.forEach(row=>results.append(button(`${row.label} · ${row.location||row.venue||row.ip||row.filename||''}`,()=>row.kind==='backup'?openBackup(row):openRecord(row.kind,row.id),'search-result')));}
    if(found.length>200)results.append(node('p','','Refine your search to see the remaining results.'));
  }
  async function handover(){
    const dialog=get('desktop-handover-dialog'),results=get('desktop-handover-results');results.textContent='Loading outstanding checks…';dialog.showModal();
    try{const data=await api('/api/desktop/handover');results.replaceChildren();for(const [key,title] of Object.entries({unknown_counts:'Unknown stock quantities',unlocated:'Items not physically located',needs_review:'Records awaiting source review',stale_checks:'Checks older than 90 days',no_linked_backup:'Devices without a linked known-good backup'})){const rows=data[key];const section=node('details','handover-group');section.append(node('summary','',`${title} (${rows.length})`));rows.slice(0,200).forEach(row=>section.append(button(row.name||row.description||row.model||row.serial_number||'Incomplete record',()=>openRecord(key==='no_linked_backup'?'device':'equipment',row.id),'search-result')));results.append(section);}const movement=node('details','handover-group');movement.append(node('summary','',`Recent stock movements (${data.movements.length})`));data.movements.forEach(event=>movement.append(node('p','history-entry',`${date(event.created_at)} · ${event.action.replaceAll('_',' ')} · ${event.details.serial||event.details.description||'Stock'} · ${event.details.quantity_before} → ${event.details.quantity_after}${event.details.reason?' · '+event.details.reason:''}${event.details.initials?' · '+event.details.initials:''}`)));results.append(movement);}catch(error){results.textContent=error.message;}
  }
  async function openBackup(item){
    backupId=item.id;const dialog=get('backup-recovery-dialog');get('recovery-error').hidden=true;dialog.showModal();get('save-recovery-details').disabled=true;
    try{const [details,records]=await Promise.all([api('/api/desktop/backup-details?id='+item.id),api('/api/desktop/records')]);get('recovery-related').replaceChildren(new Option('No related record',''),...records.records.map(row=>new Option(`${row.kind} · ${row.label}`,row.kind+':'+row.id)));get('recovery-related').value=details.record_type?details.record_type+':'+details.record_id:'';for(const [field,key] of [['recovery-model','model_serial'],['recovery-firmware','firmware'],['recovery-captured','captured_on'],['recovery-tested','tested_on'],['recovery-state','state']])get(field).value=details[key]|| (key==='state'?'untested':'');}catch(error){get('recovery-error').textContent=error.message;get('recovery-error').hidden=false;}finally{get('save-recovery-details').disabled=false;}
  }
  function suggestCustomColumns(data){
    if(currentTab!=='equipment'||!spreadsheetFile?.from_headers||spreadsheetFile.fields_configured)return;
    const used=new Set(),columns=[];
    data.headers.slice(0,15).forEach((header,index)=>{
      const existing=equipmentImportFields.find(([,label,aliases])=>[label,...aliases].some(alias=>normalizedHeader(alias)===normalizedHeader(header)));
      let key=existing?.[0] || 'custom_'+normalizedHeader(header).replace(/[^a-z0-9]+/g,'_').slice(0,24)+'_'+index;
      if(used.has(key))key='custom_column_'+index;used.add(key);
      columns.push({key,label:String(header).trim()||'Column '+(index+1),type:key==='location'?'location':'text',important:index===0,filter:key==='location'?'buttons':'none',options:[],aliases:[header]});
    });
    if(!used.has('notes'))columns.push({key:'notes',label:'Notes',type:'text',important:false,filter:'none',options:[]});
    spreadsheetInventory={...spreadsheetInventory,layout:{columns,primary_search:columns.find(column=>!['notes','quantity'].includes(column.key))?.key||columns[0].key,identifier:'',template:'custom',show_status:true,location_role:used.has('location')?'storage':'none'}};
    spreadsheetFile.fields_configured=true;
  }
  function importSummary(session){
    let undo=get('undo-current-import');if(!undo){undo=button('Undo this import',async()=>{if(!confirm('Undo the new records and reviewed updates from this import? Records edited later will block the undo to protect your changes.'))return;undo.disabled=true;try{const result=await api('/api/desktop/undo-import','POST',{session_id:window.importWorkflow.session.id});toast(`${result.undone} import changes undone.`);get('import-summary-panel').close();await load();if(currentTab==='equipment')await window.equipmentUI.load();}catch(error){toast(error.message);}finally{undo.disabled=false;}});undo.id='undo-current-import';get('import-summary-intro').after(undo);}undo.hidden=!!session.retired||!session.receipts.some(receipt=>receipt.changes?.length);
  }
  document.querySelectorAll('[data-close]').forEach(el=>el.onclick=()=>get(el.dataset.close).close());
  get('desktop-find').onclick=findAnywhere;get('desktop-search-input').oninput=renderSearch;get('desktop-handover').onclick=handover;
  get('inventory-start-manual').onclick=()=>{get('inventory-start-dialog').close();window.equipmentUI.open();};get('inventory-start-import').onclick=()=>{get('inventory-start-dialog').close();openPastedImport({fromHeaders:!!newInventory?.fromHeaders});};
  get('backup-recovery-form').onsubmit=async event=>{event.preventDefault();const [kind,id]=get('recovery-related').value.split(':'),submit=get('save-recovery-details');submit.disabled=true;try{await api('/api/desktop/backup-details','POST',{id:backupId,details:{record_type:kind||'',record_id:id?Number(id):'',model_serial:get('recovery-model').value,firmware:get('recovery-firmware').value,captured_on:get('recovery-captured').value,tested_on:get('recovery-tested').value,state:get('recovery-state').value}});get('backup-recovery-dialog').close();await window.backupsUI?.load(true);toast('Recovery details saved.');}catch(error){get('recovery-error').textContent=error.message;get('recovery-error').hidden=false;}finally{submit.disabled=false;}};
  const observer=new MutationObserver(attachDetails);observer.observe(get('device-list'),{childList:true});observer.observe(get('equipment-rows'),{childList:true});
  const reviewLabel=node('label','reviewer-label','Reviewer initials (optional)'),reviewer=node('input');reviewer.id='reviewer-initials';reviewer.maxLength=40;reviewer.value=initials();reviewer.oninput=()=>{try{localStorage.setItem('avtrack-reviewer',reviewer.value);}catch(_){}};reviewLabel.append(reviewer);get('equipment-record-review-details').before(reviewLabel);
  const policy=node('label','import-policy','Existing records'),mode=node('select');mode.id='import-existing-mode';mode.append(new Option('Add new records only — existing records stay unchanged','add'),new Option('Review changes to existing records — select updates explicitly','review'));policy.append(mode,node('small','','No records are saved until you click Import in the final review.'));get('import-workspace-steps').after(policy);
  get('paste-layout-summary').after(get('import-sheet-selection'));
  get('import-complete-rows').checked=false;get('import-complete-options').hidden=true;
  // Advanced controls stay available without interrupting the normal preview.
  const advanced=node('details','import-advanced'),summary=node('summary','','Advanced settings — columns and verification');advanced.append(summary);const settings=get('paste-preview-settings');settings.before(advanced);advanced.append(settings);get('paste-field-analysis')&&advanced.append(get('paste-field-analysis'));
  document.querySelectorAll('.export-dropdown:not(#workspace-export-menu)').forEach(menu=>{menu.addEventListener('toggle',()=>{if(!menu.open)return;let caption=menu.querySelector('.export-scope-caption');if(!caption){caption=node('p','export-scope-caption');menu.querySelector('.export-links').prepend(caption);}const scope=menu.querySelector('select');caption.textContent=scope?.selectedOptions[0]?.textContent||'Choose report content';});});
  for(const form of [get('device-form'),get('equipment-form')])form.addEventListener('reset',()=>{get('save-incomplete-device')?.remove();get('view-duplicate-device')?.remove();});
  renderFilters();attachDetails();
  return {initials,restoreDraft,clearDraft,offerIncomplete,offerDuplicate,chooseInventoryStart,prepareUnitRemoval,renderFilters,openRecord,openBackup,importSummary,suggestCustomColumns};
})();
