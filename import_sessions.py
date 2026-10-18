"""Durable import drafts and atomic row receipts, stored beside inventory data."""
import json
import re

SCHEMA='''CREATE TABLE IF NOT EXISTS import_sessions (
 id INTEGER PRIMARY KEY, target TEXT NOT NULL, name TEXT NOT NULL, state TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft', mode TEXT NOT NULL DEFAULT '', reconciliation TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS import_receipts (
 session_id INTEGER NOT NULL, source_key TEXT NOT NULL, receipt TEXT NOT NULL,
 PRIMARY KEY(session_id,source_key));
CREATE TABLE IF NOT EXISTS import_preferences (target TEXT PRIMARY KEY, settings TEXT NOT NULL);
'''

def initialize(con):
    # Avoid executescript: it implicitly commits migrations and callers' transactions.
    for statement in SCHEMA.split(';'):
        if statement.strip():con.execute(statement)
    if 'retired' not in {r['name'] for r in con.execute('PRAGMA table_info(import_sessions)')}:
        con.execute("ALTER TABLE import_sessions ADD COLUMN retired INTEGER NOT NULL DEFAULT 0")
    if 'mode' not in {r['name'] for r in con.execute('PRAGMA table_info(import_sessions)')}:
        con.execute("ALTER TABLE import_sessions ADD COLUMN mode TEXT NOT NULL DEFAULT ''")

def target_name(value):
    if not isinstance(value,str) or not re.fullmatch(r'(device|iptv|equipment:[1-9][0-9]*)',value):
        raise ValueError('Choose a valid import destination.')
    return value

def get(con,session_id):
    row=con.execute('SELECT * FROM import_sessions WHERE id=?',(session_id,)).fetchone()
    if row is None:raise LookupError('Import session not found.')
    record=dict(row);record['state']=json.loads(record['state'])
    record['reconciliation']=json.loads(record['reconciliation']) if record['reconciliation'] else None
    receipts=[json.loads(r['receipt']) for r in con.execute('SELECT receipt FROM import_receipts WHERE session_id=?',(session_id,))]
    unique={r['key']:r for r in receipts}
    record['receipts']=list(unique.values())
    record['completed_keys']=[r['source_key'] for r in con.execute('SELECT source_key FROM import_receipts WHERE session_id=?',(session_id,))]
    return record

def save(con,value,session_id=None):
    if not isinstance(value,dict) or not isinstance(value.get('state'),dict):raise ValueError('Provide an import draft.')
    state=value['state'];serialized=json.dumps(state)
    if len(serialized.encode())>7_600_000:raise ValueError('This draft is too large. Import a smaller file.')
    status=value.get('status','draft')
    if status not in ('draft','reviewing','paused','complete'):raise ValueError('Choose a valid import stage.')
    if session_id is None:
        target=target_name(value.get('target'));name=value.get('name','Spreadsheet import')
        if not isinstance(name,str) or not 1<=len(name)<=240:raise ValueError('Enter a short import name.')
        session_id=con.execute('INSERT INTO import_sessions (target,name,state,status) VALUES (?,?,?,?)',(target,name,serialized,status)).lastrowid
    else:
        if get(con,session_id)['retired']:raise ValueError('This inventory was deleted. Its import report is read-only.')
        con.execute('UPDATE import_sessions SET state=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',(serialized,status,session_id))
    target=con.execute('SELECT target FROM import_sessions WHERE id=?',(session_id,)).fetchone()['target']
    mode=state.get('confirmation_mode','ip' if target=='device' else 'none')
    if mode not in ('ip','storage','none'):raise ValueError('Choose a valid confirmation workflow.')
    con.execute('UPDATE import_sessions SET mode=? WHERE id=?',(mode,session_id))
    return get(con,session_id)

def save_receipt(con,session_id,value,apply):
    stored=con.execute('SELECT id,target,status,mode,retired FROM import_sessions WHERE id=?',(session_id,)).fetchone()
    if stored is None:raise LookupError('Import session not found.')
    session=dict(stored);session['state']={'confirmation_mode':session['mode']}
    if session['retired']:raise ValueError('This inventory was deleted. Its import report is read-only.')
    if session['status']=='complete':raise ValueError('This import is already complete.')
    keys=value.get('keys');row=value.get('row');action=value.get('action','import')
    if not isinstance(keys,list) or not 1<=len(keys)<=10000 or any(not isinstance(k,str) or not 1<=len(k)<=300 for k in keys) or len(set(keys))!=len(keys):
        raise ValueError('Provide distinct worksheet row references.')
    if not isinstance(row,dict) or action not in ('import','skip','exclude','zero'):raise ValueError('Choose a valid row action.')
    existing=con.execute('SELECT receipt FROM import_receipts WHERE session_id=? AND source_key IN ('+','.join('?' for _ in keys)+')',[session_id,*keys]).fetchall()
    if existing:
        if len(existing)!=len(keys):raise ValueError('Some source rows were already processed. Resume with the saved grouping.')
        receipt=json.loads(existing[0]['receipt'])
        return dict(receipt['result'],_receipt=receipt)
    result=apply(session,row) if action=='import' else {'added':0,'skippedRow':True,**({'skipped_zero':1} if action=='zero' else {})}
    changes=result.pop('_changes',[])
    outcome='updated' if result.get('updated') else 'added' if result.get('added') else 'zero' if result.get('skipped_zero') else 'existing' if result.get('skipped') else action
    issues=value.get('issues',[])
    if not isinstance(issues,list) or any(not isinstance(i,str) or len(i)>4000 for i in issues):raise ValueError('Invalid review notes.')
    receipt={'key':keys[0],'keys':keys,'location':str(row.get('location') or row.get('venue') or value.get('sheet') or 'Unassigned')[:240],
             'sheet':str(value.get('sheet') or '')[:240],'label':str(row.get('model') or row.get('name') or row.get('serial_number') or row.get('description') or 'Item')[:240],
             'outcome':outcome,'issues':issues,'result':result,'merged':max(0,len(keys)-1),'changes':changes}
    serialized=json.dumps(receipt)
    con.executemany('INSERT INTO import_receipts (session_id,source_key,receipt) VALUES (?,?,?)',[(session_id,key,serialized) for key in keys])
    con.execute("UPDATE import_sessions SET status='reviewing',updated_at=CURRENT_TIMESTAMP WHERE id=?",(session_id,))
    return dict(result,_receipt=receipt)
