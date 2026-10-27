"""Stamp the next commit's offline version, or verify the current committed count."""
import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--next', action='store_true', help='Stamp before creating one new commit.')
    mode.add_argument('--check', action='store_true', help='Verify against full checked-out history.')
    args = parser.parse_args()
    if git('rev-parse', '--is-shallow-repository') != 'false':
        raise SystemExit('Full Git history is required: run git fetch --unshallow first.')
    count = int(git('rev-list', '--count', 'HEAD')) + int(args.next)
    expected = f'v0.0.{count}'
    path = ROOT / 'VERSION'
    if args.next:
        path.write_text(expected + '\n', encoding='utf-8')
        print('Prepared ' + expected + '; include VERSION in the next commit.')
    else:
        actual = path.read_text(encoding='utf-8').strip()
        if not re.fullmatch(r'v0\.0\.[1-9][0-9]*', actual) or actual != expected:
            raise SystemExit(f'VERSION is {actual!r}; full Git history requires {expected}. '
                             'Stamp VERSION before committing (python scripts/stamp_version.py --next).')
        print('Verified ' + expected + ' against full Git history.')

if __name__ == '__main__':
    main()
