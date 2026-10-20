/* One desktop workspace, reusable source mappings and durable import progress. */
window.importWorkflow = (() => {
  const byId=id=>document.getElementById(id);
  const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!=null)node.textContent=text;return node;};
  const panels=['paste-inventory-dialog','paste-confirmation-dialog','paste-layout-dialog','paste-field-dialog','spreadsheet-dialog','inventory-import-review','import-summary-panel'];
  let active=null,session=null,preferences={},queue=[],queueIndex=0,completed=new Set(),receipts=[],edited={},applied=false,originalLayout=null,sheetMappings={};
  let checkpointTimer=null;
  let saving=Promise.resolve(),knownRecords=[];
  const target=()=>currentTab==='equipment'?`equipment:${(spreadsheetInventory || pasteInventory)?.id}`:currentTab;
  function showPanel(panel){
    panels.forEach(id=>{byId(id).hidden=id!==panel.id;});active=panel;
    byId('import-workspace').dataset.panel=panel.id;
    const stage=panel.id==='paste-inventory-dialog'?0:['paste-confirmation-dialog','paste-layout-dialog','paste-field-dialog','spreadsheet-dialog'].includes(panel.id)?1:panel.id==='inventory-import-review'?1:2;
    byId('import-workspace-steps').querySelectorAll('li').forEach((li,index)=>{li.classList.toggle('current',index===stage);li.classList.toggle('finished',index<stage);if(index===stage)li.setAttribute('aria-current','step');else li.removeAttribute('aria-current');});
    byId('import-workspace').setAttribute('aria-labelledby',panel.getAttribute('aria-labelledby') || 'import-workspace-title');
    byId('import-workspace-caption').textContent=(currentTab==='equipment'?(panel.id==='paste-inventory-dialog'?pasteInventory?.name:spreadsheetInventory?.name) || 'Inventory':currentTab==='iptv'?'IPTV Channels':'Devices')+(stage!==0 && queue.length>1?` · Worksheet ${queueIndex+1} of ${queue.length}`:'');
    if(stage===0)byId('import-workspace-saved').textContent='';
    if(!byId('import-workspace').open)byId('import-workspace').showModal();
    byId('import-workspace').scrollTop=0;
  }
  function install(){
    const shell=byId('import-workspace');
    panels.forEach(id=>{
      const old=byId(id),panel=el('section','import-step');
      [...old.attributes].forEach(attr=>{if(attr.name!=='open')panel.setAttribute(attr.name,attr.value);});
      panel.append(...old.childNodes);old.replaceWith(panel);shell.append(panel);panel.hidden=true;
      Object.defineProperty(panel,'open',{get:()=>!panel.hidden && shell.open});
      panel.showModal=()=>showPanel(panel);
      panel.close=()=>{panel.hidden=true;if(active===panel){active=null;delete shell.dataset.panel;shell.close();}};
    });
    shell.addEventListener('cancel',event=>{event.preventDefault();if(!active)return;const panel=active,request=new Event('cancel',{cancelable:true});panel.dispatchEvent(request);if(!request.defaultPrevented && active===panel)panel.close();});
  }
  function snapshot(){
    return {file:spreadsheetFile,inventory:spreadsheetInventory,confirmation_mode:spreadsheetFile?.confirmation_mode,
      sheet:byId('sheet-choice').value,headers:spreadsheetData?.headers || [],header_row:Number(byId('header-row').value),queue,queueIndex,
      mappings:Object.fromEntries([...byId('column-mappings').querySelectorAll('select')].map(input=>[input.id.slice(4),input.value])),
      venueEdits:[...venueEdits],excluded:[...skippedImportLocations],edited,applied,originalLayout,
      sheetMappings,heading:typeof pastedFieldSetup!=='undefined' && pastedFieldSetup?{index:pastedFieldSetup.index,columns:pastedFieldSetup.columns,decisions:pastedFieldSetup.decisions,tab:pastedFieldSetup.tab}:null,autoComplete:byId('import-complete-rows').checked,source_count:spreadsheetData?.rows.length || 0};
  }
  function scheduleCheckpoint(status='reviewing'){clearTimeout(checkpointTimer);checkpointTimer=setTimeout(()=>checkpoint(status).catch(error=>toast(error.message)),350);}
  async function checkpoint(status='draft'){
    clearTimeout(checkpointTimer);
    if(!session || !spreadsheetFile)return;
    const state=snapshot(),id=session.id;
    saving=saving.catch(()=>{}).then(async()=>{const saved=await api(`/api/import-sessions/${id}`,'PUT',{state,status},20000);if(session?.id===id)session={...saved};});
    await saving;
  }
  async function begin(file,inventory){
    byId('import-workspace-saved').textContent='No records saved yet';
    session=null;completed=new Set();receipts=[];edited={};applied=false;queue=[];queueIndex=0;sheetMappings={};
    originalLayout=inventory?structuredClone((await api('/api/equipment/inventories')).inventories.find(record=>record.id===inventory.id)?.layout || defaultInventoryLayout):null;
    knownRecords=inventory?(await api('/api/equipment?inventory_id='+inventory.id)).equipment:(await api('/api/devices')).devices;
    preferences=await api('/api/import-preferences?target='+encodeURIComponent(inventory?`equipment:${inventory.id}`:currentTab));
    if(!file.confirmation_mode)file.confirmation_mode=preferences.confirmation_mode || (inventory?.layout?.confirmation_mode || (inventory?(inventory.layout?.show_status===false?'none':'storage'):currentTab==='device'?'ip':'none'));
    const saved=await api('/api/import-sessions','POST',{target:inventory?`equipment:${inventory.id}`:currentTab,name:file.source_filename||file.filename,state:{file,inventory,originalLayout,confirmation_mode:file.confirmation_mode}});
    session=saved;
  }
  function sourceKeys(entry){return (entry.sourceNumbers || [entry.number]).map(number=>`${queueIndex}:${byId('sheet-choice').value}:${number}`);}
  function remaining(entries){return entries.filter(entry=>!sourceKeys(entry).every(key=>completed.has(key))).map(entry=>({...entry,row:edited[sourceKeys(entry)[0]] || entry.row}));}
  async function write(entry,row,action='import'){
    if(!session)throw new Error('Start or resume an import session before adding rows.');
    if(action==='import'&&!applied)await applySetup();
    const keys=sourceKeys(entry);
    const result=await api(`/api/import-sessions/${session.id}/rows`,'POST',{keys,row,action,sheet:byId('sheet-choice').value || spreadsheetFile.source_label || '',issues:entry.issues || []},20000);
    keys.forEach(key=>{completed.add(key);delete edited[key];});
    const receipt=result._receipt;delete result._receipt;
    if(receipt && !receipts.some(saved=>saved.key===receipt.key))receipts.push(receipt);
    session={...session,receipts,completed_keys:[...completed]};
    byId('import-workspace-saved').textContent=`${receipts.reduce((sum,r)=>sum+(r.result.added || 0),0)} records saved · ${completed.size} source rows finished`;
    return result;
  }
  function edit(entry,row){edited[sourceKeys(entry)[0]]=row;}
  function restoreMappings(data){
    const stored=currentTab==='iptv'&&data.generated_headers?{}:preferences.mappings || {};
    Object.entries(stored).forEach(([key,match])=>{
      const input=byId('map-'+key);if(!input)return;
      const matches=data.headers.map((header,index)=>({header,index})).filter(item=>normalizedHeader(item.header)===match.name);
      const index=matches[match.occurrence || 0]?.index;if(index!=null)input.value=String(index);
    });
    if(session?.state?.sheet===(data.sheet || '') && session.state.mappings && JSON.stringify(session.state.headers)===JSON.stringify(data.headers))Object.entries(session.state.mappings).forEach(([key,value])=>{if(byId('map-'+key))byId('map-'+key).value=value;});
  }
  async function applySetup(){
    if(/\.xlsx$/i.test(spreadsheetFile.filename) && !queue.length)throw new Error('Select at least one worksheet to import.');

    if(spreadsheetInventory){
      const current=(await api('/api/equipment/inventories')).inventories.find(record=>record.id===spreadsheetInventory.id);
      if(!current)throw new Error('This inventory was deleted. Choose another destination.');
      if(originalLayout && JSON.stringify(current.layout || defaultInventoryLayout)!==JSON.stringify(originalLayout))throw new Error('Inventory setup changed in another window. Start again with the current columns.');
      if(JSON.stringify(current.layout || defaultInventoryLayout)!==JSON.stringify(spreadsheetInventory.layout || defaultInventoryLayout)){
        spreadsheetInventory=await api(`/api/equipment/inventories/${current.id}`,'PUT',{name:current.name,layout:spreadsheetInventory.layout});
        await window.equipmentUI.load(current.id);
      }
      originalLayout=structuredClone(spreadsheetInventory.layout || defaultInventoryLayout);
    }
    const mappings={};
    [...byId('column-mappings').querySelectorAll('select')].forEach(input=>{
      if(input.value==='')return;const index=Number(input.value),name=normalizedHeader(spreadsheetData.headers[index]);
      mappings[input.id.slice(4)]={name,occurrence:spreadsheetData.headers.slice(0,index).filter(header=>normalizedHeader(header)===name).length};
    });
    sheetMappings[byId('sheet-choice').value || '']={mappings,header_row:Number(byId('header-row').value),default_location:spreadsheetFile.default_location || spreadsheetFile.sheet_location || '',venueEdits:[...venueEdits],excluded:[...skippedImportLocations]};
    preferences={confirmation_mode:spreadsheetFile.confirmation_mode,mappings,seen_headers:spreadsheetData.headers.map(normalizedHeader)};
    await api('/api/import-preferences','PUT',{target:target(),settings:preferences});applied=true;await checkpoint('reviewing');
  }
  async function configureSheets(sheets){
    byId('import-sheet-selection').hidden=!sheets.length;
    const choices=byId('import-sheet-choices');
    if(!choices.childElementCount || choices.dataset.filename!==spreadsheetFile.filename){
      choices.dataset.filename=spreadsheetFile.filename;choices.replaceChildren(...sheets.map((name,index)=>{
        const label=el('label','batch-row-selection'),check=el('input');check.type='checkbox';check.value=name;check.checked=queue.length?queue.includes(name):index===0;check.onchange=()=>{queue=[...choices.querySelectorAll('input:checked')].map(input=>input.value);queueIndex=0;checkpoint().catch(error=>toast(error.message));};label.append(check,document.createTextNode(name));return label;
      }));
    }
    if(sheets.length && !queue.length)queue=[...choices.querySelectorAll('input:checked')].map(input=>input.value);
    choices.querySelectorAll('input').forEach(input=>input.disabled=completed.size>0);
    if(spreadsheetInventory && sheets.length && !spreadsheetFile.default_location && spreadsheetInventory.layout?.location_role!=='none' && (spreadsheetInventory.layout || defaultInventoryLayout).columns.some(column=>column.key==='location'))spreadsheetFile.sheet_location=byId('sheet-choice').value;else delete spreadsheetFile.sheet_location;
  }
  async function finish(stopped){
    await checkpoint(stopped?'paused':queueIndex+1<queue.length?'reviewing':'complete');
    session=await api(`/api/import-sessions/${session.id}`);receipts=session.receipts;
    if(!stopped && queueIndex+1<queue.length){
      queueIndex++;applied=false;venueEdits=new Map();skippedImportLocations.clear();byId('header-row').value='1';byId('sheet-choice').value=queue[queueIndex];delete $('header-row').dataset.manual;
      session.state.mappings=null;session.state.sheet=null;
      byId('paste-layout-dialog').showModal();await loadSpreadsheet();showPastedLayoutSuggestion();await checkpoint();return;
    }
    showSummary(stopped);
  }
  function showSummary(stopped=session?.status!=='complete'){
    const groups=new Map();receipts.forEach(receipt=>{if(!groups.has(receipt.location))groups.set(receipt.location,[]);groups.get(receipt.location).push(receipt);});
    byId('import-summary-title').textContent=session.state?.undone?'Import undone':session.retired?'Saved report — inventory deleted':stopped?'Import paused — progress saved':'Import complete';
    byId('import-summary-intro').textContent=`${session.name} · ${completed.size} source rows accounted for · ${receipts.reduce((sum,r)=>sum+(r.result.added || 0),0)} records added. ${session.retired?'This report is read-only because its inventory was deleted.':stopped?'Unfinished rows are available when you resume.':'Physical location, IP reachability and TV stock checks remain separate.'}`;
    byId('import-summary-groups').replaceChildren(...[...groups].map(([location,rows])=>{
      const detail=el('details','cross-check-location'),summary=el('summary');
      summary.textContent=location+' · '+['added','updated','existing','skip','exclude','zero'].map(outcome=>`${rows.filter(row=>row.outcome===outcome).length} ${outcome==='exclude'?'excluded':outcome==='zero'?'zero stock':outcome}`).join(' · ')+` · ${rows.reduce((sum,row)=>sum+row.merged,0)} source rows combined · ${rows.filter(row=>row.issues.length).length} flagged`;
      const list=el('ul');rows.forEach(row=>list.append(el('li','',`${row.sheet || 'Pasted table'} · ${row.keys.map(key=>key.split(':').pop()).join(', ')} · ${row.label} · ${row.outcome}${row.issues.length?' · '+row.issues.join(' · '):''}`)));detail.append(summary,list);return detail;
    }));
    byId('import-summary-resume-option').hidden=!stopped || !!session.retired;byId('import-summary-add-option').hidden=!!session.retired;byId('import-summary-compare-option').hidden=!!session.retired || !session.target.startsWith('equipment:');
    byId('import-summary-original-option').hidden=!!session.retired || !session.target.startsWith('equipment:');
    byId('import-summary-comparison-details').replaceChildren();
    byId('import-summary-comparison').textContent=session.reconciliation?`Last source comparison: ${session.reconciliation.complete?'All source rows matched':'Differences need review'}. Download the report for details.`:'';
    window.desktopUI?.importSummary(session);
    byId('import-summary-panel').showModal();
  }
  async function resume(id){
    const saved=await api(`/api/import-sessions/${id}`),state=saved.state;
    if(saved.retired){session=saved;receipts=saved.receipts;completed=new Set(saved.completed_keys);showSummary();return;}
    if(saved.target.startsWith('equipment:')){navigatePage('equipment');await window.equipmentUI.load(Number(saved.target.split(':')[1]));}
    else navigatePage(saved.target);
    session=saved;completed=new Set(saved.completed_keys);receipts=saved.receipts;queue=state.queue || [];queueIndex=state.queueIndex || 0;edited=state.edited || {};sheetMappings=state.sheetMappings || {};applied=!!state.applied;originalLayout=state.originalLayout || state.inventory?.layout || null;
    spreadsheetFile=state.file;spreadsheetInventory=state.inventory;
    knownRecords=saved.target.startsWith('equipment:')?(await api('/api/equipment?inventory_id='+state.inventory.id)).equipment:(await api('/api/devices')).devices;
    preferences=await api('/api/import-preferences?target='+encodeURIComponent(saved.target));
    if(saved.status==='complete'){showSummary(false);return;}
    byId('header-row').value=state.header_row || 1;byId('sheet-choice').replaceChildren(...queue.map(name=>new Option(name,name)));byId('sheet-choice').value=state.sheet || queue[queueIndex] || '';
    venueEdits=new Map(state.venueEdits || []);skippedImportLocations.clear();(state.excluded || []).forEach(location=>skippedImportLocations.add(location));
    byId('import-complete-rows').checked=state.autoComplete!==false;
    byId('spreadsheet-dialog').showModal();await loadSpreadsheet({preserve:true,manualHeader:!!state.headers?.length});
    if(state.heading){pastedFieldSetup={...state.heading,file:spreadsheetFile,inventory:spreadsheetInventory};showPastedHeading();byId('paste-field-dialog').showModal();}
    await checkpoint('paused');
  }
  async function offerResume(destination){
    const {sessions}=await api('/api/import-sessions?target='+encodeURIComponent(destination));
    const previous=sessions.find(record=>!record.retired && record.status!=='complete');
    const box=byId('import-paste-resume');box.replaceChildren();if(!previous)return;
    const resumeCopy=el('div','import-resume-copy');
    resumeCopy.append(el('strong','',`Saved draft · ${previous.name}`),el('span','', 'Continue where you stopped, or paste a new table below.'));
    const resumeButton=el('button','secondary','Resume previous import');resumeButton.type='button';resumeButton.onclick=()=>{byId('paste-inventory-dialog').close();resume(previous.id).catch(error=>toast(error.message));};
    box.append(resumeCopy,resumeButton);
  }
  async function compare(original){
    if(!session.target.startsWith('equipment:'))return;
    const file=original || session.state.file;
    byId('import-summary-comparison').textContent='Comparing source rows…';
    const report=await api('/api/equipment/reconcile','POST',{...file,inventory_id:Number(session.target.split(':')[1]),source_mappings:original?{_default:{mappings:preferences.mappings || {}}}:sheetMappings});
    await api(`/api/import-sessions/${session.id}/reconciliation`,'PUT',report);session.reconciliation=report;
    byId('import-summary-comparison').textContent=`${file.pasted?'Comparison covers this paste only. Upload the original workbook to check every worksheet. ':''}${report.source_rows} source rows · ${report.summary.matched} matched · ${report.summary.missing} missing · ${report.summary.different} different · ${report.summary.needs_review} need review. Physical checks are separate.`;
    const details=byId('import-summary-comparison-details');details.replaceChildren(...report.rows.filter(row=>row.status!=='matched').map(row=>el('p','inventory-flags',`${row.sheet || 'Pasted table'} row ${row.row_number} · ${row.status} · ${[...row.issues,...row.differences.map(diff=>`${diff.field}: original ${diff.original}; saved ${diff.saved}`)].join(' · ')}`)));
  }
  document.addEventListener('DOMContentLoaded',()=>{
    byId('cancel-import-cell-notes').onclick=()=>byId('import-cell-notes-dialog').close();
    byId('close-import-summary').onclick=byId('import-summary-close-action').onclick=()=>byId('import-summary-panel').close();
    byId('import-summary-resume').onclick=()=>resume(session.id).catch(error=>toast(error.message));
    byId('import-summary-download').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify({name:session.name,status:session.status,destination:session.state.inventory?.name || session.target,receipts:session.receipts,reconciliation:session.reconciliation,completed_keys:session.completed_keys},null,2)],{type:'application/json'})),link=el('a');link.href=url;link.download='avtrack-import-report.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
    byId('import-summary-add').onclick=()=>{byId('import-summary-panel').close();openPastedImport();};
    byId('import-summary-compare').onclick=()=>compare().catch(error=>{byId('import-summary-comparison').textContent=error.message;});
    byId('import-summary-original').onclick=()=>byId('import-summary-file').click();
    byId('import-summary-file').onchange=async event=>{try{const file=event.target.files[0];if(!file)return;if(file.size>5000000)throw new Error('Choose a file up to 5 MB.');const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});await compare({filename:file.name,content});}catch(error){byId('import-summary-comparison').textContent=error.message;}finally{event.target.value='';}};
  });
  install();
  return {begin,checkpoint,scheduleCheckpoint,write,remaining,sourceKeys,edit,restoreMappings,applySetup,configureSheets,finish,offerResume,
    resetSuggestions(){preferences={...preferences,mappings:{},seen_headers:[]};},get preferences(){return preferences;},get session(){return session;},get queue(){return queue;},get queueIndex(){return queueIndex;},get originalLayout(){return originalLayout;},get knownRecords(){return knownRecords;},showSummary};
})();
