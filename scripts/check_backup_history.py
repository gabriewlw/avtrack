"""CI guard: published backup contracts and fixtures are append-only."""
import os
import subprocess

base = os.environ.get('COMPATIBILITY_BASE', '')
if base and set(base) != {'0'}:
    # Git refs arrive as an argument, not as shell code.
    changed = subprocess.check_output([
        'git', 'diff', '--no-renames', '--name-only', '--diff-filter=MD',
        base, 'HEAD', '--', 'backup_schemas', 'tests/fixtures/full_backups',
    ], text=True).splitlines()
    if changed:
        raise SystemExit('Published backup contracts and fixtures must remain unchanged. '
                         'Add a new version instead:\n' + '\n'.join(changed))
print('Published backup history preserved.')
