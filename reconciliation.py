"""Read-only, one-to-one source inventory reconciliation across all worksheets."""
import re
from collections import Counter
from spreadsheets import preview

ALIASES = {
    'brand': ('brand', 'manufacturer', 'make'),
    'model': ('model', 'model number', 'part number'),
    'description': ('description', 'item', 'name', 'equipment', 'item name'),
    'serial_number': ('serial number', 'serial', 'serial no', 's/n', 'sn'),
    'quantity': ('quantity', 'qty', 'count', 'quantity in stock'),
    'location': ('location', 'venue', 'room', 'storage location'),
    'notes': ('notes', 'note', 'comments'),
}
PLACEHOLDERS = {'n/a', 'na', 'none', 'not applicable', '-'}


def norm(value):
    return re.sub(r'\s+', ' ', str(value or '').strip()).casefold()


def split_serials(value):
    return [re.sub(r'\s+', '', part) for part in re.split(r'[,|;\r\n]+', str(value or '')) if re.sub(r'\s+', '', part)]


def serial_values(value):
    values, seen = [], set()
    for serial in split_serials(value):
        key = serial.casefold()
        if key not in seen:
            seen.add(key)
            values.append(serial)
    return values


def serial_norm(value):
    return ','.join(serial.casefold() for serial in serial_values(value))


def serial_quantity_issues(value, quantity):
    serials, unique = split_serials(value), serial_values(value)
    issues = []
    if len(serials) != len(unique):
        issues.append('Duplicate serial numbers in one source row')
    if quantity is not None and len(unique) != quantity:
        issues.append(f'Serial count {len(unique)} does not match quantity {quantity}')
    return issues


def meaningful(value):
    return bool(norm(value)) and norm(value) not in PLACEHOLDERS


def original_records(payload):
    sheets = preview(dict(payload, sheets_only=True))['sheets'] if str(payload.get('filename','')).lower().endswith('.xlsx') else ['']
    records, sheet_errors = [], []
    for sheet in sheets:
        try:
            data = preview(dict(payload, sheet=sheet, auto_header=True))
        except ValueError as exc:
            sheet_errors.append({'sheet': sheet, 'error': str(exc)})
            continue
        headers = [re.sub(r'[_-]+', ' ', h.lower()).strip() for h in data['headers']]
        indexes = {field: next((headers.index(alias) for alias in aliases if alias in headers), None) for field, aliases in ALIASES.items()}
        locations = [index for index, header in enumerate(headers) if header == 'location']
        # The original workbook uses the first LOCATION for shelf position and
        # the second LOCATION for the room. Tools also stores drawer positions.
        if len(locations) > 1:
            indexes['location'] = locations[-1]
        for values, number in zip(data['rows'], data['row_numbers']):
            row = {field: values[index] if index is not None else '' for field, index in indexes.items()}
            if not any(meaningful(row[field]) for field in ('brand','model','description','serial_number','quantity')):
                continue
            details = {}
            for index, header in enumerate(headers):
                if values[index] and header in ('storage position','condition','unit','source sheet','source row','notes2'):
                    details[header] = values[index]
            if len(locations) > 1:
                details['storage position'] = values[locations[0]]
            elif sheet.casefold() == 'tools' and row['location']:
                details['storage position'] = row['location']
                row['location'] = sheet
            if not row['location']:
                row['location'] = sheet
            for field in ('model','serial_number'):
                if norm(row[field]) in PLACEHOLDERS:
                    row[field] = ''
            raw_quantity = row['quantity']
            row['quantity'] = int(raw_quantity) if re.fullmatch(r'\d+', raw_quantity or '') else None
            issues = [f'Missing {field.replace("_", " ")}' for field in ('brand','model','serial_number','quantity','location') if row[field] is None or row[field] == '']
            if raw_quantity and row['quantity'] is None:
                issues.append(f'Non-numeric original quantity: {raw_quantity}')
            issues.extend(serial_quantity_issues(row['serial_number'], row['quantity']))
            if re.search(r'\bsee\b.*invent|separate inventory', ' '.join(str(v) for v in row.values()), re.I):
                issues.append('Reference to another inventory; not an itemized stock entry')
            records.append({'sheet':sheet, 'row_number':number, 'record':row, 'details':details, 'issues':issues})
            if len(records) > 10000:
                raise ValueError('Cross-check supports up to 10,000 source rows across all sheets.')
    return records, sheet_errors


def reconcile(payload, inventory):
    sources, sheet_errors = original_records(payload)
    serial_counts = Counter(serial_norm(entry['record']['serial_number']) for entry in sources if entry['record']['serial_number'])
    used, results = set(), []
    for entry in sources:
        source = entry['record']
        serial = serial_norm(source['serial_number'])
        candidates = []
        basis = 'serial number' if serial else 'model/item and brand'
        if serial:
            candidates = [item for item in inventory if serial_norm(item['serial_number']) == serial]
        else:
            candidates = [item for item in inventory if
                          (not source['brand'] or norm(item['brand']) == norm(source['brand'])) and
                          (not source['model'] or norm(item['model']) == norm(source['model'])) and
                          (not source['description'] or norm(item['description']) == norm(source['description']))]
            local = [item for item in candidates if norm(item['location']) == norm(source['location'])]
            if local:
                candidates = local
        status, differences, match = 'missing', [], None
        if serial and serial_counts[serial] > 1:
            status = 'ambiguous'
            entry['issues'].append('Repeated source serial; one saved record cannot prove all source rows are present')
        elif len(candidates) > 1:
            status = 'ambiguous'
        elif len(candidates) == 1 and candidates[0]['id'] in used:
            status = 'ambiguous'
            entry['issues'].append('Saved record already matched to another source row; check separate stock entries or combined quantities')
        elif len(candidates) == 1:
            match = candidates[0]
            used.add(match['id'])
            for field in ('brand','model','description','serial_number','location','quantity'):
                original = source[field]
                if original is None or original == '':
                    continue
                equal = original == match[field] if field == 'quantity' else serial_norm(original) == serial_norm(match[field]) if field == 'serial_number' else norm(original) == norm(match[field])
                if not equal:
                    differences.append({'field':field, 'original':original, 'saved':match[field]})
            for field, value in {'notes':source['notes'], **entry['details']}.items():
                if value and field not in ('source sheet','source row') and norm(value) not in norm(match['notes']):
                    differences.append({'field':field, 'original':value, 'saved':match['notes']})
            status = 'different' if differences else 'needs_review' if entry['issues'] else 'matched'
        results.append({**entry, 'status':status, 'basis':basis, 'saved_id': match['id'] if match else None,
                        'candidate_ids':[item['id'] for item in candidates], 'differences':differences})
    summary = dict(Counter(row['status'] for row in results))
    for status in ('matched','needs_review','different','missing','ambiguous'):
        summary.setdefault(status, 0)
    return {'filename':payload['filename'], 'source_rows':len(sources), 'saved_rows':len(inventory),
            'summary':summary, 'rows':results, 'sheet_errors':sheet_errors,
            'extra_records':[item for item in inventory if item['id'] not in used],
            'complete':bool(sources) and not sheet_errors and all(row['status']=='matched' for row in results)}


def reconcile_profile(payload, inventory, profile):
    """Compare user-defined columns using their names and selected identifier."""
    from inventory_profiles import column_value, custom_values, BASE_FIELDS, normalize_template_row, profile_identifier
    source_mappings=payload.get('source_mappings',{})
    if not isinstance(source_mappings,dict) or any(not isinstance(value,dict) or not isinstance(value.get('mappings',{}),dict) for value in source_mappings.values()):raise ValueError('Provide valid source column mappings.')
    for setting in source_mappings.values():
        for match in setting.get('mappings',{}).values():
            if not isinstance(match,dict) or not isinstance(match.get('name'),str) or type(match.get('occurrence',0)) is not int or not 0<=match.get('occurrence',0)<50:raise ValueError('Provide valid source column mappings.')
        if not isinstance(setting.get('default_location',''),str):raise ValueError('Provide a valid source location.')
        if not isinstance(setting.get('excluded',[]),list) or any(not isinstance(value,str) for value in setting.get('excluded',[])):raise ValueError('Provide valid excluded locations.')
        if not isinstance(setting.get('venueEdits',[]),list) or any(not isinstance(pair,list) or len(pair)!=2 or any(not isinstance(value,str) for value in pair) for pair in setting.get('venueEdits',[])):raise ValueError('Provide valid location edits.')
    known=[norm(alias) for col in profile['columns'] if col['type']!='calculated' for alias in [col['label'],*(col.get('aliases',[]))]]
    sheets=preview(dict(payload,sheets_only=True))['sheets'] if payload['filename'].lower().endswith('.xlsx') else ['']
    entries,errors=[],[]
    for sheet in sheets:
        try:
            saved_mapping=source_mappings.get(sheet,source_mappings.get('_default',{}))
            extra=[value.get('name','') for value in saved_mapping.get('mappings',{}).values() if isinstance(value,dict)]
            manual=saved_mapping.get('header_row')
            data=preview(dict(payload,sheet=sheet,header_row=manual or 1,auto_header=manual is None,header_aliases=known+extra,keep_headers=known,minimum_headers=min(3,len(known))))
        except ValueError as exc:
            errors.append({'sheet':sheet,'error':str(exc)});continue
        headers=[re.sub(r'[_-]+',' ',h.lower()).strip() for h in data['headers']]
        mapping={}
        for col in profile['columns']:
            aliases=[norm(col['label']),col['key'].replace('_',' '),*ALIASES.get(col['key'],()),*[norm(alias) for alias in col.get('aliases',[])]]
            index=next((headers.index(alias) for alias in aliases if alias in headers),None)
            if col['key']=='location' and headers.count('location')>1:index=len(headers)-1-headers[::-1].index('location')
            saved_mapping=source_mappings.get(sheet,source_mappings.get('_default',{}))
            selected=saved_mapping.get('mappings',{}).get(col['key'])
            if isinstance(selected,dict):
                candidates=[i for i,header in enumerate(headers) if norm(header)==norm(selected.get('name',''))]
                occurrence=selected.get('occurrence',0)
                if type(occurrence) is int and 0<=occurrence<len(candidates):index=candidates[occurrence]
            mapping[col['key']]=index
        for raw,number in zip(data['rows'],data['row_numbers']):
            values={key:raw[index] if index is not None else '' for key,index in mapping.items()}
            if not any(meaningful(value) for value in values.values()):continue
            saved_mapping=source_mappings.get(sheet,source_mappings.get('_default',{}))
            if not values.get('location') and saved_mapping.get('default_location'):values['location']=saved_mapping['default_location']
            original_location=values.get('location','')
            values['location']=dict(saved_mapping.get('venueEdits',[])).get(original_location,original_location)
            row={field:'' for field in BASE_FIELDS};row['quantity']=None;row['custom_values']={}
            issues=['Location excluded from this import; check whether it should be present'] if original_location in saved_mapping.get('excluded',[]) else []
            for col in profile['columns']:
                value=values[col['key']]
                if col['important'] and col['type']!='calculated' and not meaningful(value):issues.append('Missing '+col['label'])
                if col['key']=='quantity':value=int(value) if re.fullmatch(r'\d+',value or '') else None
                if col['key'] in BASE_FIELDS:row[col['key']]=value
                else:row['custom_values'][col['key']]=value
            try:
                row['custom_values']=custom_values(row['custom_values'],profile)
                normalize_template_row(row,profile)
                for col in profile['columns']:
                    if col['type']=='calculated' and values[col['key']] and norm(values[col['key']])!=norm(column_value(row,col['key'])):
                        issues.append(f'Original {col["label"]}: {values[col["key"]]}; calculated: {column_value(row,col["key"]) or "unknown"}')
            except ValueError as exc:issues.append(str(exc))
            column_keys={col['key'] for col in profile['columns']}
            if {'serial_number','quantity'} <= column_keys:
                issues.extend(serial_quantity_issues(row['serial_number'], row['quantity']))
            entries.append({'sheet':sheet,'row_number':number,'record':row,'issues':issues,'details':{}})
            if len(entries)>10000:raise ValueError('Cross-check supports up to 10,000 source rows.')
    key=profile.get('identifier') or profile['primary_search']
    identity_for=lambda row: profile_identifier(row,profile) if profile.get('stock_mode')=='tv_counts' else serial_norm(column_value(row,key)) if key=='serial_number' else norm(column_value(row,key))
    counts=Counter(identity_for(entry['record']) for entry in entries if identity_for(entry['record']) and not (profile.get('stock_mode')=='tv_counts' and entry['record']['quantity']==0))
    used,results=set(),[]
    lookup={}
    for item in inventory:lookup.setdefault(identity_for(item),[]).append(item)
    for entry in entries:
        source=entry['record'];identity=identity_for(source)
        candidates=lookup.get(identity,[]) if identity else []
        match=None;differences=[];status='missing'
        if profile.get('stock_mode')=='tv_counts' and source['quantity']==0 and not entry['issues']:
            results.append(dict(entry,status='matched',basis='Zero total count — intentionally skipped',saved_id=None,candidate_ids=[],differences=[],skipped_zero=True));continue
        if not identity:
            status='ambiguous';entry['issues'].append('Missing primary identifier; match manually')
        elif counts[identity]>1 or len(candidates)>1 or (candidates and candidates[0]['id'] in used):
            status='ambiguous';entry['issues'].append('Identifier does not uniquely match one source row to one saved item')
        elif candidates:
            match=candidates[0];used.add(match['id'])
            for col in profile['columns']:
                original=column_value(source,col['key']);saved=column_value(match,col['key'])
                if original not in ('',None) and (serial_norm(original)!=serial_norm(saved) if col['key']=='serial_number' else norm(original)!=norm(saved)):differences.append({'field':col['label'],'original':original,'saved':saved})
            status='different' if differences else 'needs_review' if entry['issues'] else 'matched'
        results.append(dict(entry,status=status,basis=next(col['label'] for col in profile['columns'] if col['key']==key),saved_id=match['id'] if match else None,candidate_ids=[item['id'] for item in candidates],differences=differences))
    summary={status:sum(row['status']==status for row in results) for status in ('matched','needs_review','different','missing','ambiguous')}
    return dict(filename=payload['filename'],source_rows=len(entries),saved_rows=len(inventory),summary=summary,rows=results,sheet_errors=errors,extra_records=[row for row in inventory if row['id'] not in used],complete=bool(entries) and not errors and all(row['status']=='matched' for row in results))
