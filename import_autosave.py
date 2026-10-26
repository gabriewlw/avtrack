"""Full-workspace recovery checkpoints after substantial inventory imports."""
import hashlib
import json
import threading
from pathlib import Path
import workspace_transfer

THRESHOLD = 25
_lock = threading.RLock()

def session_details(app, session_id):
    with app.connect() as con:
        session=con.execute('SELECT target,state,status FROM import_sessions WHERE id=?',(session_id,)).fetchone()
        if session is None or not session['target'].startswith('equipment:'):
            return None
        # Merged source rows share one receipt: count a saved record only once.
        added=con.execute("""SELECT COALESCE(SUM(COALESCE(json_extract(receipt,'$.result.added'),0)),0)
            FROM import_receipts WHERE session_id=? AND source_key=json_extract(receipt,'$.key')""",(session_id,)).fetchone()[0]
        # A restored/reused numeric session ID must not collide with an older import.
        source=hashlib.sha256((session['target']+session['state']).encode()).hexdigest()[:12]
        # State changes throughout review. The source file identity stays stable.
        state=json.loads(session['state'])
        if isinstance(state.get('file'),dict):
            source=hashlib.sha256(json.dumps(state['file'],sort_keys=True).encode()).hexdigest()[:12]
        else:
            first=con.execute('SELECT receipt FROM import_receipts WHERE session_id=? ORDER BY source_key LIMIT 1',(session_id,)).fetchone()
            source=hashlib.sha256((session['target']+(first[0] if first else '')).encode()).hexdigest()[:12]
    return int(added), f'avtrack-recovery-import-{session_id}-{source}-', session['status']

def status(app, session_id):
    details=session_details(app,session_id)
    if details is None:return {}
    added,prefix,stage=details
    if added<THRESHOLD:return {}
    directory=app.DB_PATH.parent/'recovery'
    saved=[]
    for file in directory.glob(prefix+'*.zip'):
        suffix=file.stem[len(prefix):]
        if suffix.isdigit():saved.append((int(suffix),file))
    count,file=max(saved,default=(0,None),key=lambda item:item[0])
    if file:
        result={'autosave':{'file':file.name,'records':count}}
        if stage in ('complete','paused') and count<added:
            result['autosave_warning']='The latest automatic backup does not include every imported record. Export a complete backup and check free disk space.'
        return result
    return {'autosave_warning':'Automatic backup is not available yet. Your imported records are saved in AVTrack; export a complete backup.'}

def checkpoint(app, session_id=None, added=0, final=False):
    """Run after commit. A backup failure must never turn a saved import into a retry."""
    with _lock:
        try:
            if session_id is not None:
                details=session_details(app,session_id)
                if details is None:return {}
                added,prefix,stage=details
                previous=status(app,session_id).get('autosave',{}).get('records',0)
                if added<THRESHOLD:return {}
                if added-previous<max(THRESHOLD,previous) and not final:
                    return status(app,session_id)
            elif added<THRESHOLD:return {}
            directory=app.DB_PATH.parent/'recovery'
            saved=workspace_transfer.save_recovery(app.connect,app.backup_directory,directory,version=app.source_revision())
            if session_id is not None:
                destination=directory/(prefix+str(added)+'.zip')
                saved.replace(destination)
                saved=destination
            else:
                destination=directory/('avtrack-recovery-import-bulk-'+saved.stem.removeprefix('avtrack-recovery-')+'-'+str(added)+'.zip')
                saved.replace(destination)
                saved=destination
            return {'autosave':{'file':saved.name,'records':added}}
        except Exception:
            # The data transaction is already committed. Explicitly keep success,
            # expose the missing recovery copy, and let a retry attempt it again.
            return {'autosave_warning':'Automatic backup failed. Your imported records are saved in AVTrack; export a complete backup and check free disk space.'}
