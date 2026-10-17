"""Minimal metadata must describe the incomplete source without false entrypoints."""
from pathlib import Path
import tomllib
import unittest


class PackagingTests(unittest.TestCase):
    def test_exact_runtime_and_build_pins_and_source_layout(self):
        root=Path(__file__).resolve().parents[2]
        path=root/'pyproject.toml'
        self.assertTrue(path.is_file(),'minimal project metadata is absent')
        config=tomllib.loads(path.read_text())
        self.assertEqual(config['project']['name'],'replicatetable')
        self.assertEqual(config['project']['requires-python'],'>=3.12,<3.14')
        import replicatetable
        self.assertEqual(config['project']['version'],replicatetable.__version__)
        self.assertEqual(set(config['project']['dependencies']),{
            'numpy==2.3.5','pandas==2.2.3','xarray==2026.4.0','pint==0.25.2',
            'h5py==3.16.0','h5netcdf==1.8.1','flexcache==0.3','flexparser==0.4',
            'platformdirs==4.12.3','typing-extensions==4.16.0','packaging==26.3',
            'python-dateutil==2.9.0.post0','pytz==2026.5','tzdata==2026.5','six==1.17.0'})
        self.assertEqual(config['build-system']['requires'],['setuptools==80.9.0','wheel==0.45.1'])
        self.assertEqual(config['tool']['setuptools']['package-dir'],{'':'src'})
        self.assertEqual(config['tool']['setuptools']['packages']['find']['where'],['src'])
        self.assertNotIn('scripts',config['project'])  # CLI implementation belongs to G1
        self.assertTrue((root/'MANIFEST.in').is_file())

    def test_no_evidence_archives_or_generated_files_in_source(self):
        root=Path(__file__).resolve().parents[2]
        for path in root.rglob('*'):
            if '.git' in path.parts: continue
            self.assertNotEqual(path.name,'__pycache__')
            self.assertNotIn(path.suffix,{'.whl','.tar','.gz','.zip','.pyc','.log'})
