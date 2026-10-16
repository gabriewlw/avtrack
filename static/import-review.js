/* Inventory import review keeps several editable rows from one location together. */
function reviewEquipmentBatch(entries, index, total, inventory, fields, filename, locations = [], network = false) {
  return new Promise(resolve => {
    const dialog = $('inventory-import-review');
    const identity=network?'name':inventory.layout?.primary_search || 'model';
    fields=[...fields.filter(([key])=>key===identity),...fields.filter(([key])=>key!==identity)];
    let saving = false, finishing = false, finished = false;
    const outcomes = [];
    $('inventory-import-review-title').textContent = network?'Review IP list':inventory.layout?.stock_mode==='tv_counts'?'Review TV models':`Review ${entries[0].row.location || 'unassigned location'}`;
    $('inventory-import-review-progress').textContent = `${filename} · ${inventory.name} · ${network?(entries[0].row.venue || 'IP list'):entries[0].locationProgress.split(' · ').slice(0,2).join(' · ')} · ${entries.length} rows on this screen · ${total} source rows`;
    const head = element('tr');
    ['Select / source row', ...fields.map(([key,label]) => label.replace(' (optional)','')+(key==='orientation'?' (optional)':'')), 'Result'].forEach(label => {
      const cell=element('th','',label);cell.scope='col';head.append(cell);
    });
    $('inventory-import-review-head').replaceChildren(head);
    head.firstChild.classList.add('batch-sticky');head.children[1]?.classList.add('batch-identity');head.lastChild.classList.add('batch-row-result');
    dialog.querySelector('table').style.minWidth=`${300+fields.length*125}px`;
    const states = entries.map(entry => {
      const row=element('tr');row.dataset.sourceRow=entry.number;
      const selection=element('td','batch-sticky');
      const label=element('label','batch-row-selection');
      const check=element('input');check.type='checkbox';check.checked=!entry.issues.length;check.setAttribute('aria-label',`Select row ${entry.number}`);
      label.append(check,element('strong','',`Row ${entry.number}`));selection.append(label);
      const flags=element('p','batch-row-flags',entry.issues.join(' · '));flags.hidden=!entry.issues.length;selection.append(flags);row.append(selection);
      const controls=new Map(),confirmations=new Map();
      fields.forEach(([key,label]) => {
        const cell=element('td');
        const column=inventory.layout?.columns.find(column=>column.key===key);
        let control;
        if (column && !network) {
          const input=inventoryInput(column,inventoryValue(entry.row,key),{allowClear:key!=='orientation',locations});
          cell.append(input.wrapper);control=input.control;
          input.wrapper.querySelectorAll('button').forEach(button=>button.setAttribute('aria-label',`${button.textContent} for row ${entry.number}`));
        } else {
          control=element(key==='notes'||key==='description'?'textarea':'input');
          control.value=entry.row[key] ?? '';control.maxLength=key==='notes'||key==='description'?2000:120;
          if(control.tagName==='TEXTAREA')control.rows=1;
          if(key==='quantity'){control.type='number';control.min='0';control.max='1000000';}
          cell.append(control);
        }
        if(key===identity)cell.classList.add('batch-identity');
        if(key==='notes'){
          control.hidden=true;const notesButton=element('button','quiet batch-notes-button',control.value?'Edit notes':'Add notes');notesButton.type='button';notesButton.title=control.value || 'Open notes editor';
          notesButton.setAttribute('aria-label',`Edit notes for row ${entry.number}`);
          notesButton.onclick=()=>{
            $('import-cell-notes-text').value=control.value;$('import-cell-notes-title').textContent=`Notes · row ${entry.number}`;
            $('apply-import-cell-notes').onclick=()=>{control.value=$('import-cell-notes-text').value;notesButton.textContent=control.value?'Edit notes':'Add notes';notesButton.title=control.value;control.dispatchEvent(new Event('change',{bubbles:true}));$('import-cell-notes-dialog').close();};
            $('import-cell-notes-dialog').showModal();$('import-cell-notes-text').focus();
          };cell.append(notesButton);
        }
        control.setAttribute('aria-label',`${label.replace(' (optional)','')}, row ${entry.number}`);
        if(column?.important&&key!=='orientation'){
          const showMissing=()=>cell.classList.toggle('batch-cell-missing',!String(control.value ?? '').trim());
          control.addEventListener('input',showMissing);control.addEventListener('change',showMissing);showMissing();
        }
        if(column?.require_confirmation){
          const label=element('label','batch-field-confirmation');const confirm=element('input');confirm.type='checkbox';confirm.setAttribute('aria-label',`Confirm ${column.label}, row ${entry.number}`);
          label.append(confirm,document.createTextNode('Checked'));cell.append(label);confirmations.set(key,confirm);confirm.onchange=updateSelection;
          control.addEventListener('change',()=>{confirm.checked=false;updateSelection();});
        }
        controls.set(key,control);row.append(cell);
      });
      const calculate=()=>{if(network)return;const values={...entry.row,custom_values:{...entry.row.custom_values}};controls.forEach((input,key)=>{if(inventoryBaseFields.has(key))values[key]=input.value;else values.custom_values[key]=input.value;});const calculated=inventoryCalculate(values,inventory.layout || defaultInventoryLayout);(inventory.layout?.columns || []).filter(col=>col.type==='calculated').forEach(col=>{const next=inventoryValue(calculated,col.key);if(controls.get(col.key).value!==next&&confirmations.has(col.key))confirmations.get(col.key).checked=false;controls.get(col.key).value=next;});};
      controls.forEach(control=>{const changed=()=>{calculate();window.importWorkflow.edit(entry,editedRow({entry,controls,flags}));window.importWorkflow.scheduleCheckpoint();updateSelection();};control.addEventListener('change',changed);control.addEventListener('input',changed);});calculate();
      const status=element('td','batch-row-result','Awaiting review');status.setAttribute('role','status');row.append(status);
      check.onchange=updateSelection;
      return {entry,row,check,flags,controls,confirmations,status,done:false};
    });
    $('inventory-import-review-rows').replaceChildren(...states.map(state=>state.row));
    function updateSelection() {
      const remaining=states.filter(state=>!state.done),selected=remaining.filter(state=>state.check.checked).length;
      const all=$('inventory-import-review-all');
      all.checked=!!remaining.length&&selected===remaining.length;all.indeterminate=selected>0&&selected<remaining.length;
      all.disabled=saving||finishing||!remaining.length;
      const unconfirmed=remaining.filter(state=>state.check.checked).some(state=>[...state.confirmations.values()].some(control=>!control.checked));
      $('inventory-import-review-save').disabled=saving||finishing||!selected||unconfirmed;
      $('inventory-import-review-skip').disabled=saving||finishing||!selected;
      $('inventory-import-review-save').textContent=saving?'Importing…':finishing?'Finishing…':`Import selected (${selected})`;
      $('inventory-import-review-count').textContent=`${states.filter(state=>state.done).length} of ${states.length} rows finished · ${selected} selected${unconfirmed?' · Check required fields before importing':''}`;
      $('inventory-import-review-stop').disabled=saving||finishing;
      $('inventory-import-review-close').disabled=saving||finishing;
    }
    async function finish(stopped=false) {
      if(saving||finishing||finished)return;
      finishing=true;updateSelection();
      try {
        const remaining=states.filter(state=>!state.done);
        remaining.forEach(state=>window.importWorkflow.edit(state.entry,editedRow(state)));
        // Completed rows already have durable receipts. Only a paused review needs
        // another checkpoint before closing; the parent completes the session once.
        if(remaining.length)await window.importWorkflow.checkpoint(stopped?'paused':'reviewing');
        finished=true;dialog.close();resolve({outcomes,stopped});
      } catch(error) {
        toast('Could not save import progress: '+error.message);
      } finally {
        finishing=false;if(!finished)updateSelection();
      }
    }
    function editedRow(state) {
      const row={...state.entry.row,custom_values:{...state.entry.row.custom_values}};
      state.controls.forEach((control,key)=>{if(network || inventoryBaseFields.has(key))row[key]=control.value.trim();else row.custom_values[key]=control.value.trim();});
      if(network){delete row.custom_values;row.record_type=currentTab;row.venue=cleanVenue(row.venue || '');row.ip=isDHCP(row.ip)?'DHCP':row.ip;if(currentTab==='iptv')row.channel_source=channelSourceFromName(row.name);}
      if(!network)row.location=cleanVenue(row.location || '');
      if(!network){const calculated=inventoryCalculate(row,inventory.layout || defaultInventoryLayout);Object.assign(row,calculated);}
      state.entry.row=row;
      state.entry.issues=[...(network?networkIssues(row):equipmentIssues(row,inventory.layout)),...state.entry.issues.filter(issue=>issue.startsWith('Repeated ')||issue.startsWith('Confirm ') && ![...(state.confirmations || new Map())].some(([key,control])=>control.checked && issue===`Confirm ${inventory.layout.columns.find(column=>column.key===key).label} during review`))];
      state.flags.textContent=state.entry.issues.join(' · ');state.flags.hidden=!state.entry.issues.length;
      return row;
    }
    function complete(state,result) {
      state.done=true;state.check.checked=false;
      state.row.querySelectorAll('input,select,textarea,button').forEach(control=>{control.disabled=true;});
      state.status.classList.remove('error');
      state.status.textContent=result.skippedRow?'Skipped by you':result.skipped?'Already saved · skipped':'Imported';
      state.row.classList.add('batch-row-done');outcomes.push({entry:state.entry,result});
    }
    $('inventory-import-review-all').onchange=event=>{states.filter(state=>!state.done).forEach(state=>{state.check.checked=event.target.checked;});updateSelection();};
    $('inventory-import-review-save').onclick=async()=>{
      if(saving||$('inventory-import-review-save').disabled)return;
      const selected=states.filter(state=>!state.done&&state.check.checked);
      saving=true;dialog.querySelectorAll('input,select,textarea,button').forEach(control=>{control.disabled=true;});updateSelection();
      try {
        for(const [position,state] of selected.entries()) {
          const row=editedRow(state);
          if(inventory.layout?.stock_mode==='tv_counts'&&row.quantity===0){complete(state,await window.importWorkflow.write(state.entry,row,'zero'));state.status.textContent='Zero total · skipped';continue;}
          if(!meaningfulImportRow(row)){complete(state,await window.importWorkflow.write(state.entry,row,'skip'));continue;}
          state.status.textContent=`Importing ${position+1} of ${selected.length}…`;
          try {
            const result=await window.importWorkflow.write(state.entry,row);
            complete(state,result);
          } catch(error) {
            state.status.textContent=error.message.replace('Nothing was imported.','This row was not imported.');state.status.classList.add('error');
          }
        }
      } finally {
        saving=false;states.filter(state=>!state.done).forEach(state=>state.row.querySelectorAll('input,select,textarea,button').forEach(control=>{control.disabled=false;if(control.dataset.columnKey && inventory.layout?.columns.some(col=>col.key===control.dataset.columnKey&&col.type==='calculated'))control.readOnly=true;}));
        updateSelection();if(states.every(state=>state.done))await finish();
      }
    };
    $('inventory-import-review-skip').onclick=async()=>{
      if(saving)return;
      saving=true;updateSelection();
      try{for(const state of states.filter(state=>!state.done&&state.check.checked)){const row=editedRow(state);complete(state,await window.importWorkflow.write(state.entry,row,'skip'));}}catch(error){toast('Could not save skipped rows: '+error.message);}finally{saving=false;}
      updateSelection();if(states.every(state=>state.done))await finish();
    };
    $('inventory-import-review-close').onclick=$('inventory-import-review-stop').onclick=()=>finish(true);
    dialog.oncancel=event=>{event.preventDefault();finish(true);};
    dialog.onkeydown=event=>{if(event.altKey && ['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();const current=states.findIndex(state=>state.row.contains(document.activeElement));const next=states[Math.max(0,Math.min(states.length-1,current+(event.key==='ArrowDown'?1:-1)))];next?.row.querySelector('input:not([type=hidden]),select,button')?.focus();}};
    updateSelection();dialog.showModal();$('inventory-import-review-all').focus();
  });
}
