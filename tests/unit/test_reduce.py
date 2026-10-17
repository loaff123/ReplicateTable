"""Intended reds for the real memory reducer, not an independent oracle.

Defects detected: float-coerced identifiers/direct integers, missing columns or
support, incorrect weight alignment/denominators/policy ordering, arithmetic on
already-null groups, hidden source substitution, missing fresh gates, and
retained numerical buffers. Expected scientific values come from read-only
frozen files or short hand-derived examples. No candidate reducer is imported
to derive an expected value. The runtime fixture is explicit unit-test
schema/order instrumentation; actual runtime evidence belongs to sealed runs.
"""
import copy
import gc
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys
import unittest
import warnings
import weakref
from unittest.mock import patch

import replicatetable as rt
from replicatetable.errors import Refusal
from replicatetable.model import ArrayBuffer, Recipe, SourceSnapshot
from replicatetable.runtime import validate_runtime
from tests.frozen_tools import adapt_legacy_recipe
from tests.unit.test_runtime_binding import example as runtime_example


FROZEN = Path(__file__).resolve().parents[1] / 'frozen'


def column(name='out', source='v', *, stages=(), broadcast=(),
           source_unit=None, target_unit=None):
    return dict(name=name, source=source, source_unit=source_unit,
                target_unit=target_unit, broadcast=list(broadcast),
                stages=list(stages))


def stage(name='reduce', dims=('r',), op='mean', *, missing='skip',
          min_count=1, weights='w', weight_unit=None):
    value = dict(name=name, dims=list(dims), op=op, missing=missing,
                 min_count=min_count)
    if op == 'weighted_mean':
        value.update(weights=weights, weight_unit=weight_unit)
    return value


def recipe(rows=(), columns=None):
    return Recipe(1, list(rows), [column()] if columns is None else columns)


def dataset(variables, coordinates):
    """Real eager Dataset with explicit unindexed physical coordinate arrays."""
    import numpy as np
    import xarray as xr
    data = {}
    for name, specification in variables.items():
        dims, values, dtype, unit = specification
        values = np.array(values, dtype=dtype)
        shape = tuple(len(coordinates[d][0]) for d in dims)
        data[name] = xr.Variable(dims, values.reshape(shape),
                                 attrs={'units': unit})
    coords = {name: (name, np.array(values, dtype=dtype))
              for name, (values, dtype) in coordinates.items()}
    result = xr.Dataset(data, coords=xr.Coordinates(coords, indexes={}))
    for name, (_, values) in coords.items():
        result._variables[name]._data = values
    return result


def fixture_dataset(fixture):
    def number(value):
        if value is None:
            return float('nan')
        if type(value) is dict:
            return {'+inf': float('inf'), '-inf': -float('inf'),
                    'nan': float('nan')}[value['float_special']]
        return value
    coords = {}
    for name, entry in fixture['data']['coords'].items():
        if type(entry) is dict:
            coords[name] = (entry['values'], entry['dtype'])
        else:
            coords[name] = (entry, object if any(v is None for v in entry) else None)
    variables = {name: (entry['dims'], [number(v) for v in entry['values']],
                        entry['dtype'], entry['units'])
                 for name, entry in fixture['data']['variables'].items()}
    return dataset(variables, coords)


class ReductionCase(unittest.TestCase):
    """Shared real-source setup; this base deliberately has no test methods."""
    def setUp(self):
        self.runtime = validate_runtime(runtime_example())
        runtime_patch = patch('replicatetable.runtime.runtime_identity',
                              return_value=self.runtime)
        runtime_patch.start()
        self.addCleanup(runtime_patch.stop)

    def api(self, name):
        value = getattr(rt, name, None)
        self.assertTrue(callable(value), name + ' implementation is absent')
        return value

    def refused(self, code, function, *arguments, **keywords):
        with self.assertRaises(Refusal) as caught:
            function(*arguments, **keywords)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def compiled(self, ds, rec):
        source = rt.snapshot_dataset(ds)
        return source, self.api('compile_plan')(source, rec)

    def run_case(self, ds, rec):
        source, plan = self.compiled(ds, rec)
        return source, plan, self.api('execute')(plan, source)

    def assert_exact(self, actual, expected):
        self.assertIs(type(actual), type(expected))
        if type(expected) is dict:
            self.assertEqual(set(actual), set(expected))
            for key in expected:
                self.assert_exact(actual[key], expected[key])
        elif type(expected) is list:
            self.assertEqual(len(actual), len(expected))
            for left, right in zip(actual, expected):
                self.assert_exact(left, right)
        elif type(expected) is float:
            self.assertEqual(actual.hex(), expected.hex())
        else:
            self.assertEqual(actual, expected)

    def assert_number(self, actual, expected):
        self.assertIs(type(actual), type(expected))
        if type(expected) is float:
            self.assertTrue(math.isclose(actual, expected, rel_tol=1e-12,
                                         abs_tol=1e-12), (actual, expected))
            if expected == 0.0:
                self.assertEqual(math.copysign(1., actual),
                                 math.copysign(1., expected))
        else:
            self.assertEqual(actual, expected)

    def assert_scientific(self, actual, expected):
        self.assertEqual(actual['version'], 1)
        self.assertEqual(set(actual), {'version', 'row_dims', 'units', 'rows', 'support'})
        self.assert_exact(actual['row_dims'], expected['row_dims'])
        self.assert_exact(actual['units'], expected['units'])
        self.assertEqual(len(actual['rows']), len(expected['rows']))
        self.assertEqual(len(actual['support']), len(expected['support']))
        for left, right in zip(actual['rows'], expected['rows']):
            self.assertEqual(set(left), {'keys', 'values', 'reasons'})
            self.assert_exact(left['keys'], right['keys'])
            self.assert_exact(left['reasons'], right['reasons'])
            self.assertEqual(set(left['values']), set(right['values']))
            for name in right['values']:
                self.assert_number(left['values'][name], right['values'][name])
        numbers = {'weight_total', 'weight_valid', 'value'}
        for left, right in zip(actual['support'], expected['support']):
            self.assertEqual(set(left), set(right))
            for name in right:
                if name in numbers:
                    self.assert_number(left[name], right[name])
                else:
                    self.assert_exact(left[name], right[name])


class ReducerTests(ReductionCase):
    def test_public_reducer_and_real_result_types_exist(self):
        for name in ('execute', 'load_result', 'ComputationResult',
                     'RowRecord', 'SupportRecord'):
            self.api(name)
            self.assertIn(name, rt.__all__)

    def test_direct_integer_limits_float32_and_signed_zero_are_preserved(self):
        import numpy as np
        ds = dataset({'v': (('x',), [-2**63, 2**63-1], 'int64', None),
                      'u': (('x',), [2**64-1, 2**53+1], 'uint64', None),
                      'f': (('x',), [-0., np.float32(0.1)], 'float32', None)},
                     {'x': ([2**64-1, 2**53+1], 'uint64')})
        _, plan, result = self.run_case(ds, recipe(('x',),
            [column(), column('unsigned', 'u'), column('binary32', 'f')]))
        rows = [row.to_dict() for row in result.iter_rows()]
        self.assert_exact(rows, [
            {'keys': {'x': 2**53+1},
             'values': {'out': 2**63-1, 'unsigned': 2**53+1,
                        'binary32': float(np.float32(0.1))},
             'reasons': {'out': [], 'unsigned': [], 'binary32': []}},
            {'keys': {'x': 2**64-1},
             'values': {'out': -2**63, 'unsigned': 2**64-1, 'binary32': -0.},
             'reasons': {'out': [], 'unsigned': [], 'binary32': []}}])
        self.assertEqual(tuple(result.iter_support()), ())
        self.assertEqual([c['output_dtype'] for c in plan.columns],
                         ['int64', 'uint64', 'float32'])

    def test_scalar_direct_and_declared_broadcast_keep_one_stored_value(self):
        ds = dataset({'v': ((), 2**63-1, 'int64', None)},
                     {'z': (['b', 'a'], '<U1'), 'x': ([2, 1], 'int64')})
        _, _, scalar = self.run_case(ds, recipe())
        self.assert_exact(scalar.to_dict()['rows'], [
            dict(keys={}, values={'out': 2**63-1}, reasons={'out': []})])
        _, _, repeated = self.run_case(ds, recipe(('z', 'x'),
            [column(broadcast=('z', 'x'))]))
        self.assert_exact([r.to_dict()['keys'] for r in repeated.iter_rows()],
                          [{'z': 'a', 'x': 1}, {'z': 'a', 'x': 2},
                           {'z': 'b', 'x': 1}, {'z': 'b', 'x': 2}])
        self.assertTrue(all(r.values['out'] == 2**63-1 for r in repeated.iter_rows()))

    def test_direct_nan_is_missing_and_infinity_refuses(self):
        for value, code in ((float('inf'), 'nonfinite_value'),
                            (-float('inf'), 'nonfinite_value')):
            source, plan = self.compiled(dataset({'v': ((), value, 'float64', None)}, {}), recipe())
            self.refused(code, self.api('execute'), plan, source)
        _, _, result = self.run_case(dataset({'v': ((), float('nan'), 'float64', None)}, {}), recipe())
        self.assert_exact(result.to_dict()['rows'],
            [dict(keys={}, values={'out': None}, reasons={'out': ['missing_values']})])

    def test_affine_conversion_precedes_all_stages_and_direct_conversion(self):
        ds = dataset({'v': (('r',), [0., 100.], 'float64', 'degC')},
                     {'r': ([1, 0], 'int64')})
        _, _, reduced = self.run_case(ds, recipe(columns=[column(
            source_unit='degC', target_unit='K', stages=[stage()])]))
        self.assertAlmostEqual(reduced.rows[0].values['out'], 323.15)
        _, _, direct = self.run_case(ds, recipe(('r',), [column(
            source_unit='degC', target_unit='K')]))
        self.assertEqual([r.values['out'] for r in direct.iter_rows()], [373.15, 273.15])
        self.assertEqual(dict(direct.units), {'out': 'K'})

    def test_named_weight_alignment_handles_reversed_weight_axes_and_percent(self):
        # Physical v axes z,r,x; physical w axes x,r. Scalar hand calculation
        # after r reduction is x=10: (3*3+7*4)/7, x=20: (1*1+5*2)/3.
        ds = dataset({'v': (('z', 'r', 'x'), [1, 3, 5, 7, 2, 4, 6, 8], 'float64', None),
                      'w': (('x', 'r'), [100, 200, 300, 400], 'float64', 'percent')},
                     {'z': (['b', 'a'], '<U1'), 'r': ([9, 1], 'int64'),
                      'x': ([20, 10], 'int64')})
        rec = recipe(('x', 'z'), [column(stages=[stage(op='weighted_mean', weight_unit='percent')])])
        _, _, result = self.run_case(ds, rec)
        expected = [44/7, 37/7, 14/3, 11/3]
        for row, value in zip(result.iter_rows(), expected):
            self.assertAlmostEqual(row.values['out'], value)
        records = [record.to_dict() for record in result.iter_support()]
        self.assert_exact([r['keys'] for r in records],
                          [{'x': 10, 'z': 'a'}, {'x': 10, 'z': 'b'},
                           {'x': 20, 'z': 'a'}, {'x': 20, 'z': 'b'}])
        self.assertEqual([r['weight_total'] for r in records], [7., 7., 3., 3.])

    def test_zero_weight_finite_counts_and_missing_denominator_are_distinct(self):
        ds = dataset({'v': (('r',), [10., float('nan'), 30.], 'float64', None),
                      'w': (('r',), [0., 100., 2.], 'float64', None)},
                     {'r': ([0, 1, 2], 'int64')})
        _, _, result = self.run_case(ds, recipe(columns=[column(stages=[
            stage(op='weighted_mean', min_count=2)])]))
        support = result.support[0]
        self.assertEqual((support.n_input, support.n_valid, support.n_positive_weight_valid), (3, 2, 1))
        self.assertEqual((support.weight_total, support.weight_valid, support.value), (102., 2., 30.))
        self.assertEqual(support.reasons, ())

    def test_all_reasons_are_ordered_and_null_rows_are_retained(self):
        ds = dataset({'v': (('r',), [1., float('nan')], 'float64', None),
                      'w': (('r',), [0., 0.], 'float64', None)},
                     {'r': ([0, 1], 'int64')})
        _, _, result = self.run_case(ds, recipe(columns=[column(stages=[
            stage(op='weighted_mean', missing='propagate', min_count=2)])]))
        reasons = ('missing_values', 'insufficient_count', 'zero_weight')
        self.assertIsNone(result.rows[0].values['out'])
        self.assertEqual(result.rows[0].reasons['out'], reasons)
        self.assertEqual(result.support[0].reasons, reasons)

    def test_failed_stage_is_missing_input_and_final_reasons_are_last_stage_only(self):
        ds = dataset({'v': (('rep', 'r'), [1., float('nan'), 4., 8.], 'float64', None)},
                     {'rep': ([9, 2], 'int64'), 'r': ([0, 1], 'int64')})
        columns = [column(name, stages=[stage('first', missing='propagate'),
            stage('second', ('rep',), missing=policy)])
            for name, policy in (('skip', 'skip'), ('propagate', 'propagate'))]
        _, plan, result = self.run_case(ds, recipe(columns=columns))
        self.assertEqual(result.rows[0].values['skip'], 6.)
        self.assertEqual(result.rows[0].reasons['skip'], ())
        self.assertIsNone(result.rows[0].values['propagate'])
        self.assertEqual(result.rows[0].reasons['propagate'], ('missing_values',))
        self.assertEqual([s['support_start'] for c in plan.columns for s in c['stages']], [0, 2, 3, 5])
        self.assertEqual([s.n_valid for s in result.iter_support()], [2, 1, 1, 2, 1, 1])

    def test_policy_null_skips_overflowing_value_arithmetic_after_support(self):
        for op in ('mean', 'weighted_mean'):
            for missing, minimum, values in (
                    ('propagate', 1, [1e308, 1e308, float('nan')]),
                    ('skip', 4, [1e308, 1e308, 1e308])):
                ds = dataset({'v': (('r',), values, 'float64', None),
                              'w': (('r',), [2., 2., 2.], 'float64', None)},
                             {'r': ([0, 1, 2], 'int64')})
                with self.subTest(op=op, missing=missing):
                    _, _, result = self.run_case(ds, recipe(columns=[column(stages=[
                        stage(op=op, missing=missing, min_count=minimum)])]))
                    self.assertIsNone(result.rows[0].values['out'])
                    self.assertEqual(result.support[0].weight_total,
                                     6. if op == 'weighted_mean' else 3.)

    def test_policy_null_does_not_skip_actual_weight_sum_overflow(self):
        ds = dataset({'v': (('r',), [float('nan'), float('nan')], 'float64', None),
                      'w': (('r',), [1e308, 1e308], 'float64', None)},
                     {'r': ([0, 1], 'int64')})
        source, plan = self.compiled(ds, recipe(columns=[column(stages=[stage(op='weighted_mean')])]))
        with warnings.catch_warnings(record=True) as emitted:
            error = self.refused('numeric_overflow', self.api('execute'), plan, source)
        self.assertEqual(error.exit_code, 3)
        self.assertEqual(emitted, [])

    def test_min_max_and_implicit_weight_support(self):
        ds = dataset({'v': (('r',), [7., float('nan'), -2.], 'float64', None)},
                     {'r': ([2, 0, 1], 'int64')})
        _, _, result = self.run_case(ds, recipe(columns=[
            column(op, stages=[stage(op=op)]) for op in ('min', 'max', 'mean')]))
        self.assertEqual(dict(result.rows[0].values), {'min': -2., 'max': 7., 'mean': 2.5})
        for record in result.iter_support():
            self.assertEqual((record.n_input, record.n_valid, record.n_positive_weight_valid), (3, 2, 2))
            self.assertEqual((record.weight_total, record.weight_valid), (3., 2.))

    def test_bad_weight_is_checked_even_at_missing_measurement(self):
        for weight, code in ((-1., 'negative_weight'), (float('nan'), 'nonfinite_weight'),
                             (float('inf'), 'nonfinite_weight')):
            ds = dataset({'v': (('r',), [float('nan')], 'float64', None),
                          'w': (('r',), [weight], 'float64', None)}, {'r': ([0], 'int64')})
            source, plan = self.compiled(ds, recipe(columns=[column(stages=[stage(op='weighted_mean')])]))
            self.refused(code, self.api('execute'), plan, source)

    def test_execute_uses_actual_supplied_b_and_keeps_unused_a_as_footprint_only(self):
        from replicatetable import source as source_module
        a = dataset({'v': (('r',), [2., 4.], 'float64', None)}, {'r': ([0, 1], 'int64')})
        source, plan = self.compiled(a, recipe(columns=[column(stages=[stage()])]))
        b = dataset({'v': (('r',), [2., 4.], 'float64', None)}, {'r': ([0, 1], 'int64')})
        supplied = rt.snapshot_dataset(b)
        a._variables['v']._data[0] = 200.
        original = source_module._memory_identity
        seen = []
        def identity(handle, descriptor):
            self.assertIsNot(handle, a, 'unused anchor was semantically hashed')
            seen.append(handle)
            return original(handle, descriptor)
        with patch.object(source_module, '_memory_identity', identity):
            result = self.api('execute')(plan, supplied)
        self.assertEqual(result.rows[0].values['out'], 3.)
        self.assertTrue(seen)
        self.assertIs(result._plan, plan)
        self.refused('source_changed', self.api('execute'), plan, source)

    def test_success_releases_supplied_b_and_new_materialized_buffers(self):
        a = dataset({'v': (('r',), [2., 4.], 'float64', None)}, {'r': ([0, 1], 'int64')})
        _, plan = self.compiled(a, recipe(columns=[column(stages=[stage()])]))
        b = dataset({'v': (('r',), [2., 4.], 'float64', None)}, {'r': ([0, 1], 'int64')})
        source = rt.snapshot_dataset(b)
        b_ref = weakref.ref(b)
        result = self.api('execute')(plan, source)
        del source, b
        self.assertIsNone(b_ref())
        self.assertIs(result._plan, plan)
        self.assertEqual(tuple(result._plan._source.arrays), ())

    def test_normalization_does_not_open_another_unit_pass_or_repeat_physical_weights(self):
        from replicatetable import units
        ds = dataset({'v': (('x', 'r'), [1., 2., 3., 4.], 'float64', None),
                      'w': (('r',), [25., 75.], 'float64', 'percent')},
                     {'x': ([0, 1], 'int64'), 'r': ([0, 1], 'int64')})
        source, plan = self.compiled(ds, recipe(('x',), [column(stages=[
            stage(op='weighted_mean', weight_unit='percent')])]))
        original = units.normalize_weights
        calls = []
        def normalize(buffer, operation):
            self.assertIs(type(buffer), ArrayBuffer)
            self.assertEqual(buffer.shape, (2,))
            calls.append(buffer)
            with patch.object(units, '_StockUnitContext',
                              side_effect=AssertionError('normalization opened another stock pass')), \
                 patch.object(units, 'qualify_weight_unit',
                              side_effect=AssertionError('normalization requalified its operation')):
                return original(buffer, operation)
        with patch.object(units, 'normalize_weights', normalize), \
             patch('numpy.tile', side_effect=AssertionError('tiled named weights')), \
             patch('numpy.repeat', side_effect=AssertionError('repeated named weights')):
            result = self.api('execute')(plan, source)
        self.assertEqual(len(calls), 1)
        self.assertEqual([r.values['out'] for r in result.iter_rows()], [1.75, 3.75])


class FrozenReducerTests(ReductionCase):
    def test_original_nine_successes_match_34_rows_and_130_support(self):
        expected = json.loads((FROZEN/'original'/'frozen_expected.json').read_bytes())['cases']
        before = {p: hashlib.sha256(p.read_bytes()).digest() for p in (FROZEN/'original').rglob('*') if p.is_file()}
        total_rows = total_support = cases = 0
        for path in sorted((FROZEN/'original'/'fixtures').glob('*.json')):
            fixture = json.loads(path.read_bytes())
            with self.subTest(case=fixture['id']):
                source, plan, result = self.run_case(fixture_dataset(fixture), Recipe.from_dict(adapt_legacy_recipe(fixture)))
                actual = result.to_dict()
                self.assert_scientific(actual, expected[fixture['id']])
                self.assertEqual(result.to_json(), self.api('execute')(plan, source).to_json())
                cases += 1; total_rows += len(actual['rows']); total_support += len(actual['support'])
        self.assertEqual((cases, total_rows, total_support), (9, 34, 130))
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).digest() for p in before})

    def test_both_frozen_supplements_keep_exact_successes_and_execute_refusals(self):
        # These are two preserved revisions of the same nine scientific cases,
        # not eighteen distinct supplemental scientific observations.
        for revision in ('supplemental', 'supplemental-v2'):
            root = FROZEN/revision
            expected = json.loads((root/'expected.json').read_bytes())['cases']
            cases = json.loads((root/'fixtures.json').read_bytes())['cases']
            counts = [0, 0, 0]
            for fixture in cases:
                wanted = expected[fixture['id']]
                if fixture['kind'] != 'execute' or (wanted['status'] != 'success' and wanted['phase'] != 'execute'):
                    continue
                with self.subTest(revision=revision, case=fixture['id']):
                    source, plan = self.compiled(fixture_dataset(fixture), Recipe.from_dict(fixture['recipe']))
                    if wanted['status'] == 'success':
                        result = self.api('execute')(plan, source)
                        self.assert_scientific(result.to_dict(), wanted['result'])
                        counts[0] += 1; counts[1] += len(result.rows); counts[2] += len(result.support)
                    else:
                        with warnings.catch_warnings(record=True) as emitted:
                            error = self.refused(wanted['code'], self.api('execute'), plan, source)
                        self.assertEqual(error.exit_code, wanted['exit_code'])
                        self.assertEqual(emitted, [])
            self.assertEqual(counts, [9, 20, 72])

    def test_original_weight_refusals_keep_r05_r06_codes(self):
        root = FROZEN/'original'
        controls = {r['id']: r for r in json.loads((root/'frozen_expected.json').read_bytes())['refusals']}
        for name, weight in (('R05', -2.), ('R06', float('nan'))):
            fixture = json.loads((root/'fixtures'/'F3.json').read_bytes())
            fixture['data']['variables']['weights']['values'][1] = weight
            source, plan = self.compiled(fixture_dataset(fixture), Recipe.from_dict(adapt_legacy_recipe(fixture)))
            self.refused(controls[name]['code'], self.api('execute'), plan, source)


if __name__ == '__main__':
    unittest.main()
