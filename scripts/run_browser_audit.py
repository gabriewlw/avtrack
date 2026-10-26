"""Run isolated browser regressions and retain a complete, reviewable audit report."""
import json, os, subprocess, sys, time
from pathlib import Path

shard = int(os.environ.get('AUDIT_SHARD', '0'))
shards = int(os.environ.get('AUDIT_SHARDS', '1'))
scripts = sorted(set(Path('tests').glob('browser_*.py')) | {Path('tests/layout_browser_check.py')})
scripts = [p for p in scripts if p.name != 'browser_helpers.py'][shard::shards]
output = Path('work/audit')
output.mkdir(parents=True, exist_ok=True)
results = []
for script in scripts:
    started = time.monotonic()
    try:
        run = subprocess.run([sys.executable, str(script)], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=150, text=True)
        code, log = run.returncode, run.stdout
    except subprocess.TimeoutExpired as error:
        code = 124
        log = error.stdout or b''
        if isinstance(log, bytes): log = log.decode('utf-8', errors='replace')
        log += '\nAUDIT: exceeded 150 second limit.'
    log = '\n'.join(line for line in log.splitlines() if 'AVTRACK_PREVIEW_JPEG:' not in line)
    (output/(script.stem+'.log')).write_text(log, encoding='utf-8')
    result = dict(test=str(script), passed=code == 0, returncode=code,
                  seconds=round(time.monotonic()-started, 2))
    results.append(result)
    print(json.dumps(result), flush=True)
    if code: print(log[-5000:], flush=True)
(output/f'browser-shard-{shard}.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
sys.exit(any(not result['passed'] for result in results))
