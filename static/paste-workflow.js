/* Paste-only shortcuts reuse the existing import mappings and review engine. */
window.pasteWorkflow=(()=>{
  const node=id=>document.getElementById(id);
  const stockOrder=['description','brand','model','serial_number','quantity','location','notes'];
  const normalized=value=>String(value ?? '').trim().toLowerCase();

  function prepareInventory(inventory){
    if(!inventory?.layout)return inventory;
    const layout=structuredClone(inventory.layout),keys=new Set(layout.columns.map(column=>column.key));
    const stock=layout.location_role==='storage'||layout.template==='spare_parts';
    if(stock&&stockOrder.every(key=>keys.has(key))){
      const rank=key=>{const index=stockOrder.indexOf(key);return index<0?stockOrder.length:index;};
      layout.columns=layout.columns.map(column=>column.key==='description'?{...column,label:'Description'}:column.key==='quantity'?{...column,label:'Qnt',type:'text',options:[]}:column)
        .sort((a,b)=>rank(a.key)-rank(b.key));
      layout.primary_search='serial_number';
    }
    if(spreadsheetFile?.force_location){const location=layout.columns.find(column=>column.key==='location');if(location)Object.assign(location,{type:'location',filter:'buttons',options:[]});}
    if(layout.stock_mode==='tv_counts'&&layout.merge_duplicate_models===undefined)layout.merge_duplicate_models=true;
    return {...inventory,layout};
  }

  function stats(key){
    const mapping=node('map-'+key)?.value;
    if(mapping==null||mapping==='')return null;
    const values=spreadsheetData.rows.map(row=>String(row[Number(mapping)] ?? '').trim());
    const filled=values.filter(Boolean),counts=new Map();
    filled.forEach(value=>counts.set(normalized(value),(counts.get(normalized(value))||0)+1));
    const choices=[...counts].sort((a,b)=>b[1]-a[1]).map(([value,count])=>({value:filled.find(item=>normalized(item)===value),count}));
    return {values,filled,choices,blank:values.length-filled.length,repeated:choices.filter(choice=>choice.count>1),distinct:choices.length};
  }

  function modelGroups(){
    if(currentTab!=='equipment')return {eligible:[],blockedSerial:0,blockedLocation:0};
    const groups=new Map();
    spreadsheetEntries().forEach(entry=>{
      const model=normalized(entry.row.model),brand=normalized(entry.row.brand);if(!model)return;
      const key=JSON.stringify([brand,model]);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(entry);
    });
    const eligible=[],result={eligible,blockedSerial:0,blockedLocation:0};
    for(const group of groups.values()){
      if(group.length<2)continue;
      if(group.some(entry=>normalized(entry.row.serial_number))){result.blockedSerial++;continue;}
      const locations=new Set(group.map(entry=>normalized(entry.row.location)).filter(Boolean));
      if(locations.size>1){result.blockedLocation++;continue;}
      eligible.push(group);
    }
    return result;
  }

  function updateLayout(change){
    if(!spreadsheetInventory)return;
    const layout=structuredClone(spreadsheetInventory.layout||defaultInventoryLayout);change(layout);spreadsheetInventory={...spreadsheetInventory,layout};
    showSpreadsheetPreview();window.importWorkflow.checkpoint().catch(error=>toast(error.message));
  }

  function addChoice(container,id,label,help,checked,onchange){
    const wrapper=document.createElement('label');wrapper.className='batch-row-selection paste-analysis-choice';
    const input=document.createElement('input');input.type='checkbox';input.id=id;input.checked=checked;input.onchange=()=>onchange(input.checked);
    const text=document.createElement('span'),strong=document.createElement('strong'),small=document.createElement('small');strong.textContent=label;small.textContent=help;text.append(strong,small);wrapper.append(input,text);container.append(wrapper);
  }

  function renderAnalysis(){
    const section=node('paste-field-analysis'),list=node('paste-field-analysis-list'),choices=node('paste-field-choice-options');
    section.hidden=currentTab!=='equipment'||!spreadsheetInventory;list.replaceChildren();choices.replaceChildren();if(section.hidden)return;
    const profile=spreadsheetInventory.layout||defaultInventoryLayout;
    const labels={description:'Description',brand:'Brand',model:'Model',serial_number:'Serial Number',quantity:'Quantity',location:'Location',notes:'Notes'};
    const descriptions={description:'Text field',brand:'Text field',model:'Text field',serial_number:'Searchable unique text',quantity:'Numeric field',location:'Location text',notes:'Floating Notes editor'};
    for(const key of stockOrder){
      const sample=stats(key);if(!sample)continue;
      const card=document.createElement('div');card.className='paste-analysis-card';const title=document.createElement('strong'),detail=document.createElement('span');title.textContent=labels[key];
      let message=descriptions[key];
      if(key==='brand'&&sample.repeated.length)message+=` · ${sample.distinct} names; repeated: ${sample.repeated.slice(0,3).map(choice=>choice.value).join(', ')}`;
      if(key==='model'&&sample.repeated.length)message+=` · ${sample.repeated.length} repeated model${sample.repeated.length===1?'':'s'}`;
      if(key==='quantity'){const extra=sample.filled.filter(value=>!/^\d+$/.test(value)).length;message+=extra?` · ${extra} value${extra===1?' has':'s have'} extra text to review`:'';}
      if(key==='location')message+=` · ${sample.distinct} location${sample.distinct===1?'':'s'}; repeated locations are reviewed first`;
      if(sample.blank)message+=` · ${sample.blank} blank${sample.blank===1?'':'s'} highlighted for review`;
      detail.textContent=message;card.append(title,detail);list.append(card);
    }
    const brand=stats('brand'),brandColumn=profile.columns.find(column=>column.key==='brand');
    const brandSuggested=brand&&brand.repeated.length&&brand.distinct>1&&brand.distinct<=8&&brand.distinct<=Math.ceil(brand.filled.length*.6);
    if(brandColumn&&brandSuggested)addChoice(choices,'paste-brand-buttons',`Use quick Brand buttons for ${brand.choices.map(choice=>choice.value).join(', ')}`,`Recommended because ${brand.filled.length-brand.distinct} rows repeat an existing brand. Other brands can still be typed during review.`,['buttons','select'].includes(brandColumn.type),checked=>updateLayout(layout=>{
      const column=layout.columns.find(item=>item.key==='brand');Object.assign(column,checked?{type:'buttons',options:brand.choices.map(choice=>choice.value).slice(0,50),allow_custom:true}:{type:'text',options:[],allow_custom:false});
    }));
    const groups=modelGroups(),tv=profile.stock_mode==='tv_counts';
    if(groups.eligible.length)addChoice(choices,'paste-merge-models',`Merge ${groups.eligible.length} repeated model group${groups.eligible.length===1?'':'s'} and add quantities`,'Only rows with the same Brand, Model and location and no serial numbers are eligible. Notes and source row numbers are retained.',profile.merge_duplicate_models??tv,checked=>updateLayout(layout=>{layout.merge_duplicate_models=checked;}));
    if(groups.blockedSerial||groups.blockedLocation){const note=document.createElement('p');note.className='dialog-intro';note.textContent=`${groups.blockedSerial?groups.blockedSerial+' repeated model group(s) have individual serial numbers and stay separate. ':''}${groups.blockedLocation?groups.blockedLocation+' repeated model group(s) span different locations and stay separate.':''}`;choices.append(note);}
  }

  function render(){
    const pasted=!!spreadsheetFile?.pasted;node('paste-preview-settings').hidden=!pasted;node('paste-start-review').hidden=!pasted;node('keep-paste-layout').textContent=pasted?'Advanced matching':'Keep current fields';
    node('paste-layout-intro').textContent=pasted?'The first pasted row is always the column headings. Titles such as “Serial Number” or “Monitor Model” stay together in their Excel cells. AVTrack checks the values below each heading and suggests how the table should work.':'Likely column headings are detected automatically. You can change the header row in field matching. Each suggested column shows its matching Excel heading. Check the sample below, then adjust the fields in the next step. No records have been saved.';
    if(!pasted){node('continue-paste-layout').className='primary';node('continue-paste-layout').textContent='Set up headings one by one';node('paste-preview-help').textContent='';node('paste-preview-error').hidden=true;return;}
    const needsSetup=spreadsheetFile.from_headers&&!spreadsheetFile.fields_configured;node('paste-start-review').hidden=!!needsSetup;node('keep-paste-layout').hidden=!!needsSetup;node('continue-paste-layout').className=needsSetup?'primary':'secondary';node('continue-paste-layout').textContent=needsSetup?'Set up headings one by one':'Configure fields (optional)';
    const missingHeadings=!!spreadsheetData?.generated_headers;
    node('paste-preview-help').textContent=missingHeadings?'The first pasted row should contain clear column titles. AVTrack preserved your records; add the missing names below, then match each named column to its AVTrack field.':needsSetup?'Check the cells first, then set up each heading. Your choices stay a draft until you start importing.':'Change a source match directly above its sample cells. Then choose the suggested controls and checks below, or go straight to review.';renderAnalysis();
    showMissingPasteHeadings();
    const profile=spreadsheetInventory?.layout||{},tv=profile.template==='tv'||profile.stock_mode==='tv_counts';node('paste-inventory-check-options').hidden=!spreadsheetInventory;node('paste-preview-stock').checked=profile.stock_check_history??tv;node('paste-preview-record').checked=profile.show_record_check??!tv;
    node('paste-preview-check-help').textContent=spreadsheetInventory?'Item confirmation creates a Status column: every imported item starts To be found, then changes to Located when clicked. Stock checks keep dated count snapshots. Record checks compare details with the source file. Importing does not perform these checks.':'Choose manual IP validation or no confirmation. IP formats are always checked during import; physical stock checks apply to inventory tables.';
    const select=node('paste-preview-confirmation'),original=node('import-confirmation-choice');select.replaceChildren(...[...original.options].map(option=>new Option(option.value==='storage'?'Item confirmation — To be found / Located':option.value==='ip'?'IP validation — Confirm IP':option.textContent,option.value)));select.value=original.value;
    node('paste-preview-auto-label').hidden=currentTab!=='equipment';node('paste-preview-auto').checked=node('import-complete-rows').checked;node('paste-preview-impact').textContent=spreadsheetInventory&&spreadsheetInventory.layout?.confirmation_mode!==window.importWorkflow.originalLayout?.confirmation_mode?'Changing the confirmation method will reset previous confirmation marks when you apply this setup.':'No items or saved settings change until you apply this setup. Stock-check dates remain separate.';
    if(!needsSetup)importFields().forEach(([key,label])=>{const original=node('map-'+key),cell=node('paste-layout-head').querySelector(`[data-field-key="${key}"]`);if(!original||!cell)return;const source=original.cloneNode(true);source.id='paste-map-'+key;source.value=original.value;source.setAttribute('aria-label',`Excel column for ${label.replace(' (optional)','')}`);source.className='paste-source-match';source.onchange=()=>{original.value=source.value;original.dispatchEvent(new Event('change'));};cell.append(source);});
    let entries=spreadsheetEntries().filter(entry=>!entry.skippedLocation);entries=currentTab==='equipment'?orderEquipmentReview(combineTVEntries(entries)):entries.map(entry=>({...entry,issues:networkIssues(entry.row)}));const flagged=entries.filter(entry=>entry.issues?.length).length;
    node('paste-preview-counts').textContent=`${entries.length} ${currentTab==='equipment'?(entries.length===1?'item':'items'):(entries.length===1?'record':'records')} · ${flagged} flagged for review${currentTab==='equipment'&&spreadsheetInventory.layout?.columns.some(column=>column.key==='location')&&spreadsheetInventory.layout?.location_role!=='geographic'?' · '+new Set(entries.map(entry=>entry.row.location).filter(Boolean)).size+' locations':''}`;
    node('paste-start-review').textContent='Apply setup & review items';node('paste-start-review').disabled=missingHeadings||node('confirm-import').disabled||!spreadsheetData.rows.length;node('continue-paste-layout').disabled=missingHeadings;node('continue-paste-layout').textContent=missingHeadings?'Name columns to continue':needsSetup?'Set up headings one by one':'Configure fields (optional)';node('paste-preview-error').hidden=node('spreadsheet-error').hidden;node('paste-preview-error').textContent=node('spreadsheet-error').textContent;
  }
  document.addEventListener('DOMContentLoaded',()=>{
    node('paste-preview-confirmation').onchange=()=>{node('import-confirmation-choice').value=node('paste-preview-confirmation').value;node('import-confirmation-choice').dispatchEvent(new Event('change'));};
    for(const [id,key] of [['paste-preview-stock','stock_check_history'],['paste-preview-record','show_record_check']])node(id).onchange=()=>updateLayout(layout=>{layout[key]=node(id).checked;});
    node('paste-preview-auto').onchange=()=>{node('import-complete-rows').checked=node('paste-preview-auto').checked;window.importWorkflow.checkpoint().catch(error=>toast(error.message));};
    node('paste-start-review').onclick=()=>{if(node('paste-start-review').disabled)return;node('paste-start-review').disabled=true;node('spreadsheet-form').requestSubmit();};
  });
  return {render,prepareInventory};
})();
