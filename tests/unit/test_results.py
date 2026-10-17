"""Intended reds for result1 structure, bounded streaming and real A/B/C.

Each mutation targets a documented invariant, never an alternative reducer.
Coherent forged values and impossible adjacent-stage lineage deliberately pass
local construction; later exact public replay is responsible for rejecting
them. No BoundPlan/result stand-ins supply accounting authority. New shared
decoder integration is exercised only through genuine plan/result arguments.
"""
import copy
from dataclasses import FrozenInstanceError
import gc
import importlib
import json
import math
import sys
from unittest.mock import patch
import unittest

import replicatetable as rt
from replicatetable.codec import canonical_bytes, OwnedMap
from replicatetable.model import ArrayBuffer, BoundPlan
from tests.unit.test_reduce import (ReductionCase, dataset, recipe, column,
                                    stage, FROZEN, fixture_dataset)


RESULT_FIELDS = {'version', 'row_dims', 'units', 'rows', 'support'}
ROW_FIELDS = {'keys', 'values', 'reasons'}
SUPPORT_FIELDS = {'column', 'stage', 'keys', 'n_input', 'n_valid',
                  'n_positive_weight_valid', 'weight_total', 'weight_valid',
                  'reasons', 'value', 'unit'}


class Poison:
    def __eq__(self, other):
        raise AssertionError('equality before exact type admission')
    def __bool__(self):
        raise AssertionError('truth before exact type admission')
    def __iter__(self):
        raise AssertionError('iteration before exact type admission')
    def __float__(self):
        raise AssertionError('float coercion before exact type admission')


class ResultCase(ReductionCase):
    def direct_plan(self, dtype='float64', values=(2., 4.), labels=(2, 1)):
        return self.compiled(dataset({'v': (('x',), values, dtype, None)},
                                     {'x': (labels, 'int64')}),
                             recipe(('x',), [column()]))

    def staged_plan(self, *, weighted=False, missing='skip', min_count=1):
        return self.compiled(dataset({
            'v': (('x', 'r'), [1., 3., 5., 7.], 'float64', None),
            'w': (('r',), [1., 1.], 'float64', None)},
            {'x': ([2, 1], 'int64'), 'r': ([9, 1], 'int64')}),
            recipe(('x',), [column(stages=[stage(
                op='weighted_mean' if weighted else 'mean',
                missing=missing, min_count=min_count)])]))

    def result(self, plan, value):
        return self.api('ComputationResult')(_plan=plan, **value)

    def direct_value(self):
        return dict(version=1, row_dims=['x'], units={'out': None}, support=[],
                    rows=[dict(keys={'x': 1}, values={'out': 4.}, reasons={'out': []}),
                          dict(keys={'x': 2}, values={'out': 2.}, reasons={'out': []})])

    def staged_value(self):
        value = self.direct_value()
        value['rows'][0]['values']['out'] = 6.
        value['rows'][1]['values']['out'] = 2.
        value['support'] = [dict(column='out', stage='reduce', keys={'x': key},
            n_input=2, n_valid=2, n_positive_weight_valid=2,
            weight_total=2., weight_valid=2., reasons=[], value=number, unit=None)
            for key, number in ((1, 6.), (2, 2.))]
        return value


class ResultModelTests(ResultCase):
    def test_result1_fields_records_and_private_plan_are_exact(self):
        _, plan = self.staged_plan()
        result = self.result(plan, self.staged_value())
        self.assertIs(type(result), self.api('ComputationResult'))
        self.assertIs(result._plan, plan)
        self.assertIs(type(result.rows), tuple)
        self.assertIs(type(result.support), tuple)
        self.assertEqual(set(result.to_dict()), RESULT_FIELDS)
        for row in result.iter_rows():
            self.assertIs(type(row), self.api('RowRecord'))
            self.assertEqual(set(row.to_dict()), ROW_FIELDS)
            self.assertFalse(hasattr(row, '_plan'))
        for record in result.iter_support():
            self.assertIs(type(record), self.api('SupportRecord'))
            self.assertEqual(set(record.to_dict()), SUPPORT_FIELDS)
            self.assertFalse(hasattr(record, '_plan'))
        self.assertEqual(result.to_json(), canonical_bytes(self.staged_value()))
        self.assertEqual(result.to_json(), b''.join(result.iter_json_chunks()))

    def test_mutable_inputs_are_owned_and_output_copies_are_independent(self):
        _, plan = self.staged_plan()
        value = self.staged_value()
        result = self.result(plan, value)
        before = result.to_json()
        value['rows'][0]['values']['out'] = 500.
        value['support'][0]['keys']['x'] = 400
        value['row_dims'].append('other')
        value['units']['out'] = 's'
        copied = result.to_dict()
        copied['rows'][0]['values']['out'] = 100.
        copied['support'][0]['reasons'].append('zero_weight')
        result.rows[0].to_dict()['values']['out'] = 900.
        self.assertEqual(result.to_json(), before)
        with self.assertRaises((FrozenInstanceError, AttributeError, TypeError)):
            result.version = 2
        with self.assertRaises((FrozenInstanceError, AttributeError, TypeError)):
            result.rows[0].values['out'] = 8.

    def test_atomic_reinitialization_does_not_inspect_replacement_values(self):
        _, plan = self.staged_plan()
        result = self.result(plan, self.staged_value())
        before = result.to_json()
        self.refused('invalid_result', result.__init__, version=Poison(),
            row_dims=Poison(), units=Poison(), rows=Poison(), support=Poison(), _plan=Poison())
        self.assertEqual(result.to_json(), before)
        row = result.rows[0]
        self.refused('invalid_result', row.__init__, keys=Poison(), values=Poison(), reasons=Poison())
        record = result.support[0]
        self.refused('invalid_result', record.__init__,
                     **{name: Poison() for name in SUPPORT_FIELDS})
        self.assertEqual(result.to_json(), before)

    def test_wrong_root_types_fields_and_grain_order_refuse(self):
        _, plan = self.direct_plan()
        mutations = [(['version'], True), (['row_dims'], {'x': 1}),
                     (['units', 'out'], False), (['rows', 0, 'keys', 'x'], 1.),
                     (['rows', 0, 'values', 'out'], True),
                     (['rows', 0, 'reasons', 'out'], ['zero_weight'])]
        for path, replacement in mutations:
            value = self.direct_value()
            target = value
            for key in path[:-1]: target = target[key]
            target[path[-1]] = replacement
            with self.subTest(path=path):
                self.refused('invalid_result', self.result, plan, value)
        for alteration in ('reversed', 'missing', 'duplicate', 'extra_key', 'extra_column', 'extra_support'):
            value = self.direct_value()
            if alteration == 'reversed': value['rows'].reverse()
            elif alteration == 'missing': value['rows'].pop()
            elif alteration == 'duplicate': value['rows'][1] = copy.deepcopy(value['rows'][0])
            elif alteration == 'extra_key': value['rows'][0]['keys']['other'] = 1
            elif alteration == 'extra_column': value['rows'][0]['values']['other'] = 1.
            else: value['support'] = self.staged_value()['support']
            with self.subTest(alteration=alteration):
                self.refused('invalid_result', self.result, plan, value)

    def test_exact_types_precede_equality_for_all_record_scalar_roles(self):
        _, plan = self.staged_plan()
        locations = [('rows', 0, 'keys', 'x'), ('rows', 0, 'values', 'out'),
                     ('units', 'out'), ('support', 0, 'column'),
                     ('support', 0, 'stage'), ('support', 0, 'unit'),
                     ('support', 0, 'n_input'), ('support', 0, 'n_valid'),
                     ('support', 0, 'n_positive_weight_valid'),
                     ('support', 0, 'weight_total'), ('support', 0, 'weight_valid'),
                     ('support', 0, 'value')]
        for path in locations:
            value = self.staged_value(); target = value
            for key in path[:-1]: target = target[key]
            target[path[-1]] = Poison()
            with self.subTest(path=path):
                self.refused('invalid_result', self.result, plan, value)
        value = self.staged_value(); value['support'][0]['reasons'] = [Poison()]
        self.refused('invalid_result', self.result, plan, value)

    def test_direct_integer_null_and_out_of_range_never_pass_float_coercion(self):
        for dtype, values, maximum in (('int64', [-2**63, 2**63-1], 2**63-1),
                                       ('uint64', [0, 2**64-1], 2**64-1)):
            _, plan = self.direct_plan(dtype, values)
            for replacement, reasons in ((None, ['missing_values']),
                                         (float(maximum), []), (maximum+1, [])):
                value = self.direct_value()
                value['rows'][0]['values']['out'] = replacement
                value['rows'][0]['reasons']['out'] = reasons
                value['rows'][1]['values']['out'] = values[0]
                with self.subTest(dtype=dtype, replacement=replacement):
                    self.refused('invalid_result', self.result, plan, value)

    def test_direct_float32_representability_and_stored_signed_zero(self):
        _, plan = self.direct_plan('float32', [0.5, -0.])
        value = self.direct_value()
        value['rows'][0]['values']['out'] = -0.
        value['rows'][1]['values']['out'] = 0.5
        result = self.result(plan, value)
        self.assertEqual(result.rows[0].values['out'].hex(), '-0x0.0p+0')
        value['rows'][0]['values']['out'] = 0.1
        self.refused('invalid_result', self.result, plan, value)

    def test_key_exact_type_signed_zero_and_stored_unicode_width_are_bound(self):
        for labels, dtype, replacement in (([-0.], 'float64', 0.),
                                            (['a'], '<U1', 'ab')):
            _, plan = self.compiled(dataset({'v': (('x',), [3.], 'float64', None)},
                                             {'x': (labels, dtype)}), recipe(('x',)))
            value = dict(version=1, row_dims=['x'], units={'out': None}, support=[],
                rows=[dict(keys={'x': labels[0]}, values={'out': 3.}, reasons={'out': []})])
            result = self.result(plan, value)
            self.assert_exact(result.rows[0].to_dict()['keys'], {'x': labels[0]})
            value['rows'][0]['keys']['x'] = replacement
            self.refused('invalid_result', self.result, plan, value)

    def test_final_stage_linkage_covers_every_declared_broadcast_row(self):
        _, plan = self.compiled(dataset({'v': (('r',), [1., 3.], 'float64', None)},
            {'r': ([0, 1], 'int64'), 'x': (['b', 'a'], '<U1')}),
            recipe(('x',), [column(broadcast=('x',), stages=[stage()])]))
        record = dict(column='out', stage='reduce', keys={}, n_input=2,
            n_valid=2, n_positive_weight_valid=2, weight_total=2., weight_valid=2.,
            reasons=[], value=2., unit=None)
        value = dict(version=1, row_dims=['x'], units={'out': None}, support=[record],
            rows=[dict(keys={'x': key}, values={'out': 2.}, reasons={'out': []})
                  for key in ('a', 'b')])
        self.assertEqual(len(self.result(plan, value).rows), 2)
        value['rows'][1]['values']['out'] = 4.
        self.refused('invalid_result', self.result, plan, value)

    def test_support_count_float_null_reason_and_implicit_weight_constraints(self):
        _, plan = self.staged_plan()
        changes = [('n_input', True), ('n_valid', 3), ('n_positive_weight_valid', 1),
                   ('weight_total', 2), ('weight_valid', 1.), ('weight_total', float('inf')),
                   ('value', None), ('value', 6), ('reasons', ['missing_values']),
                   ('reasons', ['zero_weight', 'insufficient_count']), ('unit', 's')]
        for field, replacement in changes:
            value = self.staged_value(); value['support'][0][field] = replacement
            if field == 'value': value['rows'][0]['values']['out'] = replacement
            if field == 'reasons': value['rows'][0]['reasons']['out'] = replacement
            with self.subTest(field=field, replacement=replacement):
                self.refused('invalid_result', self.result, plan, value)

    def test_support_grain_order_stage_identity_and_final_linkage_are_exact(self):
        _, plan = self.staged_plan()
        for alteration in ('order', 'key', 'column', 'stage', 'value', 'count', 'missing'):
            value = self.staged_value()
            if alteration == 'order': value['support'].reverse()
            elif alteration == 'key': value['support'][0]['keys']['x'] = 1.
            elif alteration == 'column': value['support'][0]['column'] = 'unknown'
            elif alteration == 'stage': value['support'][0]['stage'] = 'unknown'
            elif alteration == 'value': value['rows'][0]['values']['out'] = 8.
            elif alteration == 'count': value['support'][0]['n_input'] = 1
            else: value['support'].pop()
            with self.subTest(alteration=alteration):
                self.refused('invalid_result', self.result, plan, value)

    def test_rounded_weight_sum_envelope_preserves_legal_triple(self):
        fixtures = json.loads((FROZEN/'supplemental-v2'/'fixtures.json').read_bytes())['cases']
        expected = json.loads((FROZEN/'supplemental-v2'/'expected.json').read_bytes())['cases']
        for fixture in fixtures:
            if fixture['kind'] != 'support_model': continue
            wanted = expected[fixture['id']]
            with self.subTest(case=fixture['id']):
                if wanted['status'] == 'accepted':
                    record = self.api('SupportRecord')(**fixture['record'])
                    self.assert_exact(record.to_dict(), wanted['exact_record'])
                    self.assertGreater(record.weight_valid, record.weight_total)
                else:
                    self.refused(wanted['code'], self.api('SupportRecord'), **fixture['record'])

    def test_coherent_forged_final_values_remain_structurally_admissible(self):
        source, plan = self.staged_plan()
        value = self.staged_value()
        value['rows'][0]['values']['out'] = 123.
        value['support'][0]['value'] = 123.
        with patch('replicatetable.runtime.runtime_identity', side_effect=AssertionError('structural constructor read runtime')), \
             patch('replicatetable.source._memory_identity', side_effect=AssertionError('structural constructor read source')):
            forged = self.result(plan, value)
        self.assertEqual(forged.rows[0].values['out'], 123.)
        self.assertNotEqual(forged.to_json(), self.api('execute')(plan, source).to_json())

    def test_coherent_impossible_adjacent_stage_lineage_is_not_reduced_by_constructor(self):
        ds = dataset({'v': (('rep', 'r'), [2., 4., 6., 8.], 'float64', None)},
                     {'rep': ([0, 1], 'int64'), 'r': ([0, 1], 'int64')})
        source, plan = self.compiled(ds, recipe(columns=[column(stages=[stage('first'), stage('second', ('rep',))])]))
        value = dict(version=1, row_dims=[], units={'out': None},
            rows=[dict(keys={}, values={'out': 5.}, reasons={'out': []})], support=[])
        for name, keys, number in (('first', {'rep': 0}, 100.),
                                   ('first', {'rep': 1}, 200.), ('second', {}, 5.)):
            value['support'].append(dict(column='out', stage=name, keys=keys,
                n_input=2, n_valid=2, n_positive_weight_valid=2,
                weight_total=2., weight_valid=2., reasons=[], value=number, unit=None))
        forged = self.result(plan, value)
        self.assertEqual(forged.rows[0].values['out'], 5.)
        self.assertNotEqual(forged.to_json(), self.api('execute')(plan, source).to_json())

    def test_iterators_yield_retained_records_and_filter_without_cloning(self):
        _, plan = self.staged_plan()
        result = self.result(plan, self.staged_value())
        self.assertIs(next(result.iter_rows()), result.rows[0])
        self.assertIs(next(result.iter_support('out', 'reduce')), result.support[0])
        self.assertEqual(tuple(result.iter_support('unknown')), ())
        self.assertEqual(tuple(result.iter_support(stage='unknown')), ())
        for arguments in ({'column': Poison()}, {'stage': Poison()}):
            self.refused('invalid_result', result.iter_support, **arguments)

    def test_result_models_are_final_and_partially_initialized_instances_refuse(self):
        _, plan = self.direct_plan()
        for name in ('RowRecord', 'SupportRecord', 'ComputationResult'):
            model = self.api(name)
            with self.assertRaises(TypeError):
                type('UnqualifiedSubclass', (model,), {})
        partial = object.__new__(self.api('ComputationResult'))
        self.refused('invalid_plan_input', self.api('inspect_call_admission'),
                     plan, plan._source, result=partial)


class ResultLoadAndAdmissionTests(ResultCase):
    def test_load_result_is_structural_strict_and_uses_exact_private_plan(self):
        _, plan = self.staged_plan()
        raw = canonical_bytes(self.staged_value())
        with patch('replicatetable.runtime.runtime_identity', side_effect=AssertionError('structural loader read runtime')), \
             patch('replicatetable.source._memory_identity', side_effect=AssertionError('structural loader hashed source')):
            result = self.api('load_result')(raw, plan)
        self.assertIs(result._plan, plan)
        self.assertEqual(result.to_json(), raw)
        self.refused('invalid_json', self.api('load_result'), b'{"version":1,'+raw[1:], plan)
        value = self.staged_value(); value['unknown'] = 1
        self.refused('invalid_result', self.api('load_result'), canonical_bytes(value), plan)
        self.refused('invalid_result', self.api('load_result'), raw.decode(), plan)

    def test_serialization_streams_existing_records_without_full_forest_helpers(self):
        _, plan = self.staged_plan()
        result = self.result(plan, self.staged_value())
        wanted = canonical_bytes(self.staged_value())
        reducer = importlib.import_module('replicatetable.reduce')
        with patch.object(type(result), 'to_dict', side_effect=AssertionError('full result to_dict')), \
             patch.object(rt.RowRecord, 'to_dict', side_effect=AssertionError('row copy on stream')), \
             patch.object(rt.SupportRecord, 'to_dict', side_effect=AssertionError('support copy on stream')), \
             patch('replicatetable.codec.freeze', side_effect=AssertionError('full freeze')), \
             patch('replicatetable.codec.thaw', side_effect=AssertionError('full thaw')):
            self.assertEqual(result.to_json(), wanted)
            self.assertEqual(b''.join(result.iter_json_chunks()), wanted)

    def test_three_genuine_datasets_remain_in_original_required_closure(self):
        from replicatetable import admission
        from replicatetable.source import _footprint_memory
        a, plan_a = self.direct_plan()
        b, plan_b = self.direct_plan()
        c, plan_c = self.direct_plan()
        self.assertEqual(plan_a.to_json(), plan_c.to_json())
        result_c = self.result(plan_c, self.direct_value())
        result_a = self.result(plan_a, self.direct_value())
        triple = self.api('inspect_call_admission')(plan_a, b, result=result_c)
        self.assertEqual((triple.required_dataset_count, triple.distinct_dataset_count), (3, 3))
        binding_b, cache_b = _footprint_memory(b._handle)
        binding_c, cache_c = _footprint_memory(c._handle)
        _, cache_a = _footprint_memory(a._handle)
        self.assertEqual(triple.extra_source_bytes, binding_b['base_bytes'] + binding_c['base_bytes'])
        self.assertEqual(triple.cache_bytes, cache_a + cache_b + cache_c)
        self.assertEqual(triple.baseline_bytes, plan_a.estimates['estimated_memory_bytes'])
        same = self.api('inspect_call_admission')(plan_a, a, result=result_a)
        self.assertEqual((same.required_dataset_count, same.distinct_dataset_count), (3, 1))
        self.assertEqual(same.extra_source_bytes, 0)
        result_b = self.result(plan_b, self.direct_value())
        duplicate = self.api('inspect_call_admission')(plan_a, b, result=result_b)
        self.assertEqual((duplicate.required_dataset_count, duplicate.distinct_dataset_count), (3, 2))
        self.assertEqual(duplicate.extra_source_bytes, binding_b['base_bytes'])
        with admission._required_inputs(plan=plan_a, snapshot=b, result=result_c) as outer:
            with admission._required_inputs(snapshot=b) as inner:
                self.assertIs(inner, outer)
                self.assertEqual(len(inner.datasets), 3)
                self.assertTrue(any(ds is c._handle for ds in inner.datasets))
        self.assertIsNone(admission._ACTIVE.get())

    def test_matching_result_distinct_backing_is_still_scanned_for_cache_and_layout(self):
        a, plan_a = self.direct_plan()
        _, plan_c = self.direct_plan()
        result_c = self.result(plan_c, self.direct_value())
        before = self.api('inspect_call_admission')(plan_a, a, result=result_c)
        plan_c._source._handle._cache = {}
        after = self.api('inspect_call_admission')(plan_a, a, result=result_c)
        self.assertGreater(after.cache_bytes, before.cache_bytes)
        self.assertEqual(after.extra_source_bytes, before.extra_source_bytes)
        plan_c._source._handle._cache['unexpected'] = 1
        self.refused('unsupported_source_storage', self.api('inspect_call_admission'),
                     plan_a, a, result=result_c)

    def test_result_without_plan_and_mismatched_plan_are_refused(self):
        from replicatetable import admission
        a, plan_a = self.direct_plan()
        _, plan_c = self.direct_plan(values=(10., 20.))
        result = self.result(plan_c, self.direct_value())
        self.refused('invalid_plan_input', admission._required_inputs, result=result)
        self.refused('plan_binding_mismatch', self.api('inspect_call_admission'),
                     plan_a, a, result=result)
        class FakeResult:
            @property
            def _plan(self): raise AssertionError('unqualified backing hook')
        self.refused('invalid_plan_input', self.api('inspect_call_admission'),
                     plan_a, a, result=FakeResult())

    def test_actual_anchor_shrinkage_still_refuses_with_result_slot(self):
        import numpy as np
        owner = np.arange(64, dtype='float64')
        ds = dataset({'v': (('x',), [2., 4.], 'float64', None)}, {'x': ([2, 1], 'int64')})
        owner[:2] = [2., 4.]
        ds._variables['v']._data = owner[:2]
        source, plan = self.compiled(ds, recipe(('x',), [column()]))
        result = self.result(plan, self.direct_value())
        ds._variables['v']._data = np.array([2., 4.])
        self.refused('source_resource_binding_mismatch', self.api('inspect_call_admission'),
                     plan, source, result=result)

    def test_retained_cancellation_releases_new_buffers_and_preserves_identity(self):
        source, plan = self.staged_plan()
        support_type = self.api('SupportRecord')
        retained = []
        writes = []
        original = ArrayBuffer.__init__
        class Cancel(BaseException):
            def __setattr__(self, name, value):
                writes.append(name)
                return super().__setattr__(name, value)
        cancellation = Cancel('stop')
        def buffer_init(buffer, dtype, shape, data):
            original(buffer, dtype, shape, data)
            retained.append(data)
        enabled = gc.isenabled()
        gc.disable()
        try:
            with patch.object(ArrayBuffer, '__init__', buffer_init), \
                 patch.object(support_type, '__init__', side_effect=cancellation):
                with self.assertRaises(Cancel) as caught:
                    self.api('execute')(plan, source)
            self.assertIs(caught.exception, cancellation)
            self.assertIsNone(cancellation.__cause__)
            self.assertIsNone(cancellation.__context__)
            self.assertEqual(writes, [])
            self.assertTrue(retained)
            for raw in retained:
                self.assertEqual(sys.getrefcount(raw), 3)
        finally:
            if enabled: gc.enable()

    def test_retained_overflow_refusal_releases_new_materialized_buffers(self):
        source, plan = self.compiled(dataset({
            'v': (('r',), [1e308, 1e308], 'float64', None)},
            {'r': ([0, 1], 'int64')}), recipe(columns=[column(stages=[stage()])]))
        retained = []
        original = ArrayBuffer.__init__
        def buffer_init(buffer, dtype, shape, data):
            original(buffer, dtype, shape, data)
            retained.append(data)
        enabled = gc.isenabled()
        gc.disable()
        try:
            with patch.object(ArrayBuffer, '__init__', buffer_init):
                error = self.refused('numeric_overflow', self.api('execute'), plan, source)
            self.assertEqual(error.exit_code, 3)
            self.assertIsNone(error.__cause__)
            self.assertIsNone(error.__context__)
            self.assertTrue(retained)
            for raw in retained:
                self.assertEqual(sys.getrefcount(raw), 3)
        finally:
            if enabled: gc.enable()


if __name__ == '__main__':
    unittest.main()
