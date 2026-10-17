"""Fresh v10 structural unit tests; these do not certify stock labels."""
import dataclasses
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from replicatetable.codec import OwnedMap
from replicatetable.errors import Refusal


def module():
    assert importlib.util.find_spec('replicatetable.units') is not None, 'Bounded units increment is absent'
    from replicatetable import units
    return units


def operation():
    return dict(source_unit='ms', target_unit='s', scale=.001, offset=0.,
                parsed_source=[['millisecond', 1]], parsed_target=[['second', 1]],
                definition_graph=[
                    dict(name='millisecond', converter='ScaleConverter', scale=.001,
                         offset=0., is_base=False, reference=[['second', 1]]),
                    dict(name='second', converter='ScaleConverter', scale=1.,
                         offset=0., is_base=True, reference=[['[time]', 1]])])


class UnitModelTests(unittest.TestCase):
    def test_seven_field_atomic_owned_roundtrip(self):
        u = module(); raw = operation(); op = u.UnitOperation.from_dict(raw)
        self.assertEqual(op.to_dict(), raw)
        self.assertEqual(u.UnitOperation.from_dict(op.to_dict()), op)
        self.assertEqual(len(dataclasses.fields(op)), 7)
        self.assertIs(type(op.definition_graph), tuple)
        self.assertIs(type(op.definition_graph[0]), OwnedMap)
        raw['definition_graph'][0]['scale'] = 100
        self.assertEqual(op.scale, .001)
        self.assertEqual(op.definition_graph[0]['scale'], .001)
        with self.assertRaises((AttributeError, dataclasses.FrozenInstanceError)):
            op.scale = 9
        before = op.to_dict()
        with self.assertRaises(Refusal): op.__init__(**operation())
        self.assertEqual(op.to_dict(), before)

    def test_invalid_coefficients_refuse_before_owned_graph_copy(self):
        u = module(); raw = operation(); raw['scale'] = 1.
        with patch.object(u, 'freeze', side_effect=AssertionError('copied graph before coherence')):
            with self.assertRaises(Refusal) as caught: u.UnitOperation.from_dict(raw)
        self.assertEqual(caught.exception.code, 'invalid_unit_operation')

    def test_failed_constructor_sets_no_partial_fields(self):
        u = module(); op = object.__new__(u.UnitOperation); raw = operation()
        raw['definition_graph'][0]['reference'] = [['missing', 1]]
        with self.assertRaises(Refusal): op.__init__(**raw)
        for field in dataclasses.fields(op):
            self.assertFalse(hasattr(op, field.name))

    def test_exact_types_precede_comparisons_or_mapping_hooks(self):
        u = module()
        class Trap:
            def __eq__(self, other): raise AssertionError('equality hook')
            def __hash__(self): raise AssertionError('hash hook')
        for key in ('scale', 'offset', 'source_unit', 'target_unit'):
            raw = operation(); raw[key] = Trap()
            with self.subTest(key=key), self.assertRaises(Refusal): u.UnitOperation.from_dict(raw)
        for field in ('name', 'converter', 'is_base'):
            raw = operation(); raw['definition_graph'][0][field] = Trap()
            with self.subTest(field=field), self.assertRaises(Refusal): u.UnitOperation.from_dict(raw)
        raw = operation(); raw['parsed_source'][0][1] = True
        with self.assertRaises(Refusal): u.UnitOperation.from_dict(raw)

    def test_graph_sorted_closed_acyclic_reachable_and_capped(self):
        u = module()
        for mutation in ('unsorted', 'missing', 'cycle', 'unreachable', 'nodes', 'terms'):
            raw = operation(); graph = raw['definition_graph']
            if mutation == 'unsorted': graph.reverse()
            elif mutation == 'missing': graph.pop()
            elif mutation == 'cycle': graph[0]['reference'] = [['millisecond', 1]]
            elif mutation == 'unreachable': graph.insert(0, dict(name='meter', converter='ScaleConverter', scale=1., offset=0., is_base=True, reference=[['[length]', 1]]))
            elif mutation == 'nodes': graph *= 65
            else: graph[0]['reference'] = [['second', 1]] * 513
            with self.subTest(mutation=mutation), self.assertRaises(Refusal): u.UnitOperation.from_dict(raw)

    def test_poisoned_owned_map_never_runs_hooks(self):
        u = module()
        for backing in (None, [], (('name', 'millisecond'),), ((object(), 1),)):
            raw = operation(); node = object.__new__(OwnedMap)
            if backing is not None: object.__setattr__(node, '_items', backing)
            raw['definition_graph'][0] = node
            with self.subTest(backing_type=type(backing)), self.assertRaises(Refusal):
                u.UnitOperation.from_dict(raw)

    def test_null_measurement_and_weight_shapes(self):
        u = module()
        measurement = u.UnitOperation(None, None, 1., 0., None, None, [])
        weight = u.UnitOperation(None, 'dimensionless', 1., 0., None, [], [])
        self.assertIsNone(measurement.parsed_target)
        self.assertEqual(weight.parsed_target, ())
        for raw in ((None, 's', 1., 0., None, [], []), (None, None, 2., 0., None, None, [])):
            with self.assertRaises(Refusal): u.UnitOperation(*raw)

    def test_science_free_unit_model_import_and_recipe_parse(self):
        module()
        code = """import sys
import replicatetable
from replicatetable.units import UnitOperation
from replicatetable import parse_recipe
parse_recipe(b'{"version":1,"row_dims":[],"columns":[{"name":"v","source":"v","source_unit":null,"target_unit":null,"broadcast":[],"stages":[]}]}')
assert not any(n.split('.')[0] in ('numpy','pandas','xarray','pint','h5py','h5netcdf') for n in sys.modules)
UnitOperation(None,None,1.,0.,None,None,[])
"""
        subprocess.run([sys.executable, '-B', '-c', code], check=True, env=os.environ.copy(), capture_output=True, text=True)
