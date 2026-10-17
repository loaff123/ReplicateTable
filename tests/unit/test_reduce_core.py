"""Module-qualified core tests while shared compiler integration is unapproved.

These call the real reduction module and genuine compiled plans/source. They
do not invent public exports, replace admission, emulate a BoundPlan, or provide
an alternate parser. Package exports, shared result decoding and result-slot
serialization are deliberately still covered by the earlier public tests.
"""
import copy
import importlib
import json
import math
import unittest
from unittest.mock import patch

import replicatetable as rt
from tests.unit.test_reduce import (ReductionCase, FROZEN, fixture_dataset,
                                    dataset, column, stage, recipe)
from tests.frozen_tools import adapt_legacy_recipe
from replicatetable.model import Recipe, ArrayBuffer


class CoreTests(ReductionCase):
    def core(self, name):
        value = getattr(importlib.import_module('replicatetable.reduce'), name, None)
        self.assertTrue(callable(value), name + ' module implementation is absent')
        return value

    def run_core(self, ds, rec):
        source, plan = self.compiled(ds, rec)
        return source, plan, self.core('execute')(plan, source)

    def observed(self, result):
        # Test-only inspection of retained records. Production never constructs
        # this full result dictionary on its streaming path.
        return dict(version=result.version, row_dims=list(result.row_dims),
                    units=dict(result.units),
                    rows=[r.to_dict() for r in result.iter_rows()],
                    support=[r.to_dict() for r in result.iter_support()])

    def test_original_and_current_supplement_match_independent_frozen_values(self):
        original = FROZEN/'original'
        expected = json.loads((original/'frozen_expected.json').read_bytes())['cases']
        counts = [0, 0, 0]
        for path in sorted((original/'fixtures').glob('*.json')):
            fixture = json.loads(path.read_bytes())
            with self.subTest(case=fixture['id']):
                _, _, result = self.run_core(fixture_dataset(fixture),
                    Recipe.from_dict(adapt_legacy_recipe(fixture)))
                observed = self.observed(result)
                self.assert_scientific(observed, expected[fixture['id']])
                counts[0] += 1; counts[1] += len(result.rows); counts[2] += len(result.support)
        supplement = FROZEN/'supplemental-v2'
        expected = json.loads((supplement/'expected.json').read_bytes())['cases']
        for fixture in json.loads((supplement/'fixtures.json').read_bytes())['cases']:
            wanted = expected[fixture['id']]
            if wanted['status'] != 'success': continue
            with self.subTest(case=fixture['id']):
                _, _, result = self.run_core(fixture_dataset(fixture), Recipe.from_dict(fixture['recipe']))
                self.assert_scientific(self.observed(result), wanted['result'])
                counts[0] += 1; counts[1] += len(result.rows); counts[2] += len(result.support)
        self.assertEqual(counts, [18, 54, 202])

    def test_current_supplement_execute_refusals_preserve_codes_and_exits(self):
        root = FROZEN/'supplemental-v2'
        expected = json.loads((root/'expected.json').read_bytes())['cases']
        for fixture in json.loads((root/'fixtures.json').read_bytes())['cases']:
            wanted = expected[fixture['id']]
            if fixture['kind'] != 'execute' or wanted['status'] == 'success' or wanted['phase'] != 'execute':
                continue
            with self.subTest(case=fixture['id']):
                source, plan = self.compiled(fixture_dataset(fixture), Recipe.from_dict(fixture['recipe']))
                error = self.refused(wanted['code'], self.core('execute'), plan, source)
                self.assertEqual(error.exit_code, wanted['exit_code'])

    def test_policy_null_skips_value_sum_and_product_after_support(self):
        for op in ('mean', 'weighted_mean'):
            ds = dataset({'v': (('r',), [1e308, 1e308, float('nan')], 'float64', None),
                          'w': (('r',), [2., 2., 2.], 'float64', None)},
                         {'r': ([0, 1, 2], 'int64')})
            _, _, result = self.run_core(ds, recipe(columns=[column(stages=[stage(op=op, missing='propagate')])]))
            self.assertIsNone(result.rows[0].values['out'])
            self.assertEqual(result.support[0].n_valid, 2)
            self.assertEqual(result.support[0].weight_total, 6. if op == 'weighted_mean' else 3.)

    def test_policy_null_still_checks_performed_weight_sum_and_conversion(self):
        ds = dataset({'v': (('r',), [float('nan'), float('nan')], 'float64', None),
                      'w': (('r',), [1e308, 1e308], 'float64', None)}, {'r': ([0, 1], 'int64')})
        source, plan = self.compiled(ds, recipe(columns=[column(stages=[stage(op='weighted_mean')])]))
        self.refused('numeric_overflow', self.core('execute'), plan, source)
        ds = dataset({'v': (('r',), [1e308, float('nan')], 'float64', 's')},
                     {'r': ([0, 1], 'int64')})
        source, plan = self.compiled(ds, recipe(columns=[column(source_unit='s', target_unit='ms',
            stages=[stage(missing='propagate')])]))
        self.refused('numeric_overflow', self.core('execute'), plan, source)

    def test_scalar_weights_normalize_once_and_align_without_tiling(self):
        from replicatetable import units
        ds = dataset({'v': (('x', 'r'), [1., 3., 5., 7.], 'float64', None),
                      'w': ((), 50., 'float64', 'percent')},
                     {'x': ([1, 0], 'int64'), 'r': ([0, 1], 'int64')})
        source, plan = self.compiled(ds, recipe(('x',), [column(stages=[stage(op='weighted_mean', weight_unit='percent')])]))
        real = units.normalize_weights
        calls = []
        def normalize(buffer, operation):
            self.assertIs(type(buffer), ArrayBuffer)
            self.assertEqual(buffer.shape, ())
            calls.append(buffer.shape)
            with patch.object(units, '_StockUnitContext', side_effect=AssertionError('nested qualification')):
                return real(buffer, operation)
        with patch.object(units, 'normalize_weights', normalize), \
             patch('numpy.tile', side_effect=AssertionError('tiled weights')), \
             patch('numpy.repeat', side_effect=AssertionError('repeated weights')):
            result = self.core('execute')(plan, source)
        self.assertEqual(calls, [()])
        self.assertEqual([r.values['out'] for r in result.iter_rows()], [6., 2.])

    def test_actual_supplied_source_is_consumed_without_retaining_it(self):
        import weakref
        make = lambda: dataset({'v': (('r',), [2., 4.], 'float64', None)}, {'r': ([0, 1], 'int64')})
        a, plan = self.compiled(make(), recipe(columns=[column(stages=[stage()])]))
        b = make(); reference = weakref.ref(b); supplied = rt.snapshot_dataset(b)
        a._handle._variables['v']._data[0] = 200.
        result = self.core('execute')(plan, supplied)
        self.assertEqual(result.rows[0].values['out'], 3.)
        self.assertIs(result._plan, plan)
        del supplied, b
        self.assertIsNone(reference())

    def test_record_structure_rounded_envelope_and_exact_types(self):
        record = dict(column='out', stage='reduce', keys={}, n_input=4, n_valid=3,
            n_positive_weight_valid=3, weight_total=1e16, weight_valid=1.0000000000000002e16,
            reasons=[], value=0.9999999999999998, unit=None)
        result = self.core('SupportRecord')(**record)
        self.assert_exact(result.to_dict(), record)
        for field, replacement in (('weight_valid', 1.000000000000001e16),
                                    ('n_valid', True), ('value', 1), ('unit', False)):
            changed = dict(record); changed[field] = replacement
            self.refused('invalid_result', self.core('SupportRecord'), **changed)

    def test_result_constructor_validates_context_without_a_second_reducer(self):
        ds = dataset({'v': (('r',), [2., 4.], 'float64', None)}, {'r': ([0, 1], 'int64')})
        _, plan = self.compiled(ds, recipe(columns=[column(stages=[stage()])]))
        record = dict(column='out', stage='reduce', keys={}, n_input=2, n_valid=2,
            n_positive_weight_valid=2, weight_total=2., weight_valid=2., reasons=[], value=900., unit=None)
        value = dict(version=1, row_dims=[], units={'out': None}, support=[record],
                     rows=[dict(keys={}, values={'out': 900.}, reasons={'out': []})])
        with patch('replicatetable.runtime.runtime_identity', side_effect=AssertionError('constructor runtime')), \
             patch('replicatetable.source._memory_identity', side_effect=AssertionError('constructor source')):
            result = self.core('ComputationResult')(_plan=plan, **value)
        self.assertEqual(result.rows[0].values['out'], 900.)
        value['rows'][0]['values']['out'] = 3.
        self.refused('invalid_result', self.core('ComputationResult'), _plan=plan, **value)

    def test_result_constructor_rejects_direct_integer_null(self):
        _, plan = self.compiled(dataset({'v': ((), 2**64-1, 'uint64', None)}, {}), recipe())
        value = dict(version=1, row_dims=[], units={'out': None}, support=[],
            rows=[dict(keys={}, values={'out': None}, reasons={'out': ['missing_values']})])
        self.refused('invalid_result', self.core('ComputationResult'), _plan=plan, **value)


if __name__ == '__main__':
    unittest.main()
