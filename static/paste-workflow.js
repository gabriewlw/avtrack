/* Paste-only shortcuts reuse the existing import mappings and review engine. */
window.pasteWorkflow=(()=>{
  const node=id=>document.getElementById(id);
  function render(){
    const pasted=!!spreadsheetFile?.pasted;
    node('paste-preview-settings').hidden=!pasted;
    node('paste-start-review').hidden=!pasted;
    node('keep-paste-layout').textContent=pasted?'Advanced matching':'Keep current fields';
    node('paste-layout-intro').textContent=pasted?'The first pasted row is always the column headings. Titles such as “Serial Number” or “Monitor Model” stay together in their Excel cells. Check the samples and choose the checks for this table below.':'Likely column headings are detected automatically. You can change the header row in field matching. Each suggested column shows its matching Excel heading. Check the sample below, then adjust the fields in the next step. No records have been saved.';
    if(!pasted){
      node('continue-paste-layout').className='primary';
      node('continue-paste-layout').textContent='Set up headings one by one';
      node('paste-preview-help').textContent='';
      node('paste-preview-error').hidden=true;
      return;
    }
    const needsSetup=spreadsheetFile.from_headers && !spreadsheetFile.fields_configured;
    node('paste-start-review').hidden=!!needsSetup;
    node('keep-paste-layout').hidden=!!needsSetup;
    node('continue-paste-layout').className=needsSetup?'primary':'secondary';
    node('continue-paste-layout').textContent=needsSetup?'Set up headings one by one':'Configure fields (optional)';
    node('paste-preview-help').textContent=needsSetup?'Check the cells first, then set up each heading. Your choices stay a draft until you start importing.':'Change a source match directly above its sample cells. When the preview looks right, go straight to review; field setup is optional.';
    const profile=spreadsheetInventory?.layout || {};
    const tv=profile.template==='tv' || profile.stock_mode==='tv_counts';
    node('paste-inventory-check-options').hidden=!spreadsheetInventory;
    node('paste-preview-stock').checked=profile.stock_check_history ?? tv;
    node('paste-preview-record').checked=profile.show_record_check ?? !tv;
    node('paste-preview-check-help').textContent=spreadsheetInventory?'Item confirmation marks Located / Not located; IP validation adds a manual Confirm IP control. Stock checks keep dated count snapshots. Record checks compare details with the source file. Importing does not perform these checks.':'Choose manual IP validation or no confirmation. IP formats are always checked during import; physical stock checks apply to inventory tables.';
    const select=node('paste-preview-confirmation'),original=node('import-confirmation-choice');
    select.replaceChildren(...[...original.options].map(option=>new Option(option.value==='storage'?'Item confirmation — Located / Not located':option.value==='ip'?'IP validation — Confirm IP':option.textContent,option.value)));
    select.value=original.value;
    node('paste-preview-auto-label').hidden=currentTab!=='equipment';
    node('paste-preview-auto').checked=node('import-complete-rows').checked;
    node('paste-preview-impact').textContent=spreadsheetInventory && spreadsheetInventory.layout?.confirmation_mode!==window.importWorkflow.originalLayout?.confirmation_mode?'Changing the confirmation method will reset previous confirmation marks when you apply this setup.':'No items or saved settings change until you apply this setup. Stock-check dates remain separate.';
    if(!needsSetup){
      importFields().forEach(([key,label])=>{
        const original=node('map-'+key),cell=node('paste-layout-head').querySelector(`[data-field-key="${key}"]`);
        if(!original || !cell)return;
        const source=original.cloneNode(true);source.id='paste-map-'+key;
        source.value=original.value;source.setAttribute('aria-label',`Excel column for ${label.replace(' (optional)','')}`);
        source.className='paste-source-match';
        source.onchange=()=>{original.value=source.value;original.dispatchEvent(new Event('change'));};
        cell.append(source);
      });
    }
    let entries=spreadsheetEntries().filter(entry=>!entry.skippedLocation);
    entries=currentTab==='equipment'?orderEquipmentReview(combineTVEntries(entries)):entries.map(entry=>({...entry,issues:networkIssues(entry.row)}));
    const flagged=entries.filter(entry=>entry.issues?.length).length;
    node('paste-preview-counts').textContent=`${entries.length} ${currentTab==='equipment'?(entries.length===1?'item':'items'):(entries.length===1?'record':'records')} · ${flagged} flagged for review${currentTab==='equipment' && spreadsheetInventory.layout?.columns.some(column=>column.key==='location') && spreadsheetInventory.layout?.location_role!=='geographic'?' · '+new Set(entries.map(entry=>entry.row.location).filter(Boolean)).size+' locations':''}`;
    node('paste-start-review').textContent='Apply setup & review items';
    node('paste-start-review').disabled=node('confirm-import').disabled || !spreadsheetData.rows.length;
    node('paste-preview-error').hidden=node('spreadsheet-error').hidden;
    node('paste-preview-error').textContent=node('spreadsheet-error').textContent;
  }
  document.addEventListener('DOMContentLoaded',()=>{
    node('paste-preview-confirmation').onchange=()=>{
      node('import-confirmation-choice').value=node('paste-preview-confirmation').value;
      node('import-confirmation-choice').dispatchEvent(new Event('change'));
    };
    for(const [id,key] of [['paste-preview-stock','stock_check_history'],['paste-preview-record','show_record_check']]){
      node(id).onchange=()=>{
        if(!spreadsheetInventory)return;
        spreadsheetInventory={...spreadsheetInventory,layout:{...spreadsheetInventory.layout,[key]:node(id).checked}};
        showSpreadsheetPreview();window.importWorkflow.checkpoint().catch(error=>toast(error.message));
      };
    }
    node('paste-preview-auto').onchange=()=>{
      node('import-complete-rows').checked=node('paste-preview-auto').checked;
      window.importWorkflow.checkpoint().catch(error=>toast(error.message));
    };
    node('paste-start-review').onclick=()=>{
      if(node('paste-start-review').disabled)return;
      node('paste-start-review').disabled=true;
      node('spreadsheet-form').requestSubmit();
    };
  });
  return {render};
})();
