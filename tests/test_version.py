"""Real full-history, depth-one and archive builds must show the same version."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app

class BuildVersionTests(unittest.TestCase):
    def test_full_history_shallow_and_no_git_keep_the_same_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source'
            source.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-c', 'user.name=Version Test',
                    '-c', 'user.email=version@example.invalid', *args], cwd=source,
                    text=True, stderr=subprocess.DEVNULL).strip()
            git('init')
            (source / 'VERSION').write_text('v0.0.3\n')
            for number in range(3):
                (source / 'record').write_text(str(number))
                git('add', '.')
                git('commit', '-m', f'Synthetic revision {number + 1}')
            with patch.object(app, 'ROOT', source):
                self.assertTrue(app.source_revision().startswith('v0.0.3 · '))
            shallow = Path(temporary) / 'shallow'
            subprocess.check_call(['git', 'clone', '--depth=1', source.as_uri(), str(shallow)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertEqual(subprocess.check_output(['git', 'rev-list', '--count', 'HEAD'],
                             cwd=shallow, text=True).strip(), '1')
            with patch.object(app, 'ROOT', shallow):
                self.assertTrue(app.source_revision().startswith('v0.0.3 · '))
                with patch.object(app.subprocess, 'run', side_effect=FileNotFoundError):
                    self.assertEqual(app.source_revision(), 'v0.0.3')
                # A source archive has no .git directory at all.
                shutil.rmtree(shallow / '.git')
                self.assertEqual(app.source_revision(), 'v0.0.3')

    def test_invalid_stamp_is_not_presented_as_a_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'VERSION').write_text('invalid')
            with patch.object(app, 'ROOT', root), patch.object(app.subprocess, 'run', side_effect=FileNotFoundError):
                self.assertEqual(app.source_revision(), 'unversioned')

    def test_shipped_count_matches_complete_history(self):
        self.assertEqual(subprocess.check_output(['git', 'rev-parse', '--is-shallow-repository'],
                         cwd=app.ROOT, text=True).strip(), 'false')
        count = subprocess.check_output(['git', 'rev-list', '--count', 'HEAD'],
                                       cwd=app.ROOT, text=True).strip()
        self.assertEqual((app.ROOT / 'VERSION').read_text().strip(), 'v0.0.' + count)
