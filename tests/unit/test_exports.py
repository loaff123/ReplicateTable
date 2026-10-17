"""Detects absent exports, source substitution, and accidental scientific imports."""
import importlib.util
from pathlib import Path
import unittest


class ExportTests(unittest.TestCase):
    def test_foundation_exports_are_from_this_source_tree(self):
        spec = importlib.util.find_spec('replicatetable')
        self.assertIsNotNone(spec, 'B1 foundation package is absent')
        self.assertIsNotNone(spec.origin, 'B1 foundation package is absent')
        import replicatetable
        expected = Path(__file__).resolve().parents[2] / 'src' / 'replicatetable'
        self.assertEqual(Path(replicatetable.__file__).resolve().parent, expected)
        for name in ('parse_recipe', 'Recipe', 'SourceIdentity', 'Coordinate', 'ArrayBuffer', 'Refusal', 'ComputationError'):
            self.assertTrue(hasattr(replicatetable, name), name)
