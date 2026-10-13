"""Official AVTrack configuration keeps existing deployments on their saved data."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ProjectIdentityTests(unittest.TestCase):
    def test_database_setting_priority_and_legacy_fallbacks_preserve_records(self):
        # Each database carries its own marker, so loading a different file cannot pass.
        with tempfile.TemporaryDirectory() as tmp:
            base={k:v for k,v in os.environ.items() if k not in ('AVTRACK_DB','BROADCASTHUB_DB','IPTRACKING_DB')}
            variables=['AVTRACK_DB','BROADCASTHUB_DB','IPTRACKING_DB']
            paths={name:str(Path(tmp)/(name+'.sqlite3')) for name in variables}
            setup="import app; app.save_equipment({'description':__import__('os').environ['AVTRACK_TEST_MARKER']})"
            for name,path in paths.items():
                subprocess.run([sys.executable,'-c',setup],cwd=ROOT,env=dict(base,**{name:path,'AVTRACK_TEST_MARKER':name}),check=True,capture_output=True)
            read="import app; print(app.DB_PATH); print(app.equipment_inventory()[0]['description'])"
            for names in [variables,variables[1:],variables[2:]]:
                with self.subTest(configured=names):
                    result=subprocess.run([sys.executable,'-c',read],cwd=ROOT,env=dict(base,**{name:paths[name] for name in names}),check=True,capture_output=True,text=True)
                    self.assertEqual(result.stdout.splitlines(),[paths[names[0]],names[0]])
            default=subprocess.run([sys.executable,'-c','import app; print(app.DB_PATH)'],cwd=ROOT,env=base,check=True,capture_output=True,text=True)
            self.assertEqual(default.stdout.strip(),str(ROOT/'data'/'inventory.sqlite3'))
