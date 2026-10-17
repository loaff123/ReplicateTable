"""Compiler/admission intended reds over actual eager Dataset handles.

The runtime fixture below is explicit ordering/schema instrumentation, not a
claim of actual runtime discovery. Stock unit qualification and source scans
remain real. Separate sealed-copy profile runs establish real runtime gates.
Each test documents observable behavior that a missing or weakened compiler,
binding, topology, phase, or call-local guard must break. No result stand-in or
native route is used, and original frozen files are only read.
"""
import copy
import gc
import importlib
import json
from pathlib import Path
import unittest
import weakref
from unittest.mock import patch

import replicatetable as rt
from replicatetable.codec import OwnedMap, canonical_bytes, thaw
from replicatetable.errors import Refusal
from replicatetable.model import ArrayBuffer, Coordinate, Recipe, SourceSnapshot
from replicatetable.runtime import validate_runtime
from tests.unit.test_runtime_binding import example as runtime_example


PLAN_FIELDS = {'version', 'formula_version', 'source', 'recipe', 'runtime',
               'coordinates', 'selected', 'columns', 'resource_binding', 'estimates'}
COLUMN_FIELDS = {'name', 'source', 'source_dtype', 'input_dims', 'input_shape',
                 'final_dims', 'broadcast', 'output_dtype', 'unit_operation',
                 'weight', 'stages'}
STAGE_FIELDS = {'name', 'dims', 'op', 'missing', 'min_count', 'input_dims',
                'input_shape', 'remaining_dims', 'remaining_shape',
                'support_dims', 'support_count', 'support_start'}
ADMISSION_FIELDS = {'version', 'formula_version', 'baseline_bytes',
                    'extra_source_bytes', 'cache_bytes', 'total_bytes',
                    'limit_bytes', 'admitted', 'required_dataset_count',
                    'distinct_dataset_count'}


def column(name='out', source='v', source_unit=None, target_unit=None,
           broadcast=(), stages=()):
    return dict(name=name, source=source, source_unit=source_unit,
                target_unit=target_unit, broadcast=list(broadcast),
                stages=list(stages))


def stage(name='mean', dims=('r',), op='mean', **extra):
    result = dict(name=name, dims=list(dims), op=op, missing='skip', min_count=1)
    result.update(extra)
    return result


def recipe(rows=('x',), columns=None):
    return Recipe(1, list(rows), [column()] if columns is None else columns)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.runtime = validate_runtime(runtime_example())
        self.runtime_patch = patch('replicatetable.runtime.runtime_identity',
                                   return_value=self.runtime)
        self.runtime_patch.start()
        self.addCleanup(self.runtime_patch.stop)

    def api(self, name):
        result = getattr(rt, name, None)
        self.assertTrue(callable(result), name + ' public implementation is absent')
        return result

    def refused(self, code, function, *arguments, **keywords):
        with self.assertRaises(Refusal) as caught:
            function(*arguments, **keywords)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def dataset(self, values=None, labels=None, *, extras=None, attrs=None):
        import numpy as np
        import xarray as xr
        if values is None:
            values = np.array([1., 2.])
        if labels is None:
            labels = np.array([2, 1], dtype='int64')
        variables = {'v': (('x',), values)}
        if extras is not None:
            variables.update(extras)
        ds = xr.Dataset(variables, coords=xr.Coordinates(
            {'x': (('x',), labels)}, indexes={}), attrs=attrs)
        ds._variables['x']._data = labels
        return ds

    def compiled(self, dataset=None, rec=None):
        compile_plan = self.api('compile_plan')
        source = rt.snapshot_dataset(self.dataset() if dataset is None else dataset)
        return source, compile_plan(source, recipe() if rec is None else rec)

    def clone_snapshot(self, original, **changes):
        fields = {name: getattr(original, name) for name in original.__slots__}
        fields.update(changes)
        return SourceSnapshot(**fields)

    def test_real_plan_surface_excludes_unimplemented_routes(self):
        for name in ('BoundPlan', 'compile_plan', 'load_plan',
                     'materialize_source', 'CallAdmission', 'inspect_call_admission',
                     'ComputationResult', 'RowRecord', 'SupportRecord',
                     'execute', 'load_result'):
            self.api(name)
            self.assertIn(name, rt.__all__)
        for name in ('write_bundle', 'verify_bundle', 'render_report', 'explain_row'):
            self.assertTrue(callable(self.api(name)), name + ' must be callable')
            self.assertIn(name, rt.__all__)
        self.assertFalse(hasattr(rt, 'inspect_source'),
                         'native file-source inspection has no implemented route')

    def test_exact_plan2_and_compiled_field_shapes(self):
        source, plan = self.compiled()
        self.assertIs(type(plan), self.api('BoundPlan'))
        value = plan.to_dict()
        self.assertEqual(set(value), PLAN_FIELDS)
        self.assertEqual((value['version'], value['formula_version']), (2, 2))
        self.assertEqual(value['source'], source.identity.to_dict())
        self.assertEqual(set(value['columns'][0]), COLUMN_FIELDS)
        self.assertEqual(value['selected'],
                         dict(variables=['v'], dimensions=['x'], numeric_bytes=16))
        self.assertEqual(set(value['resource_binding']),
                         {'kind', 'base_bytes', 'owners', 'descriptor_bytes'})
        self.assertEqual(len(value['estimates']), 31)
        self.assertEqual(plan.to_json(), b''.join(plan.iter_json_chunks()))
        self.assertEqual(plan.to_json(), canonical_bytes(value))

    def test_plan_owns_selected_only_backing_and_shares_coordinates(self):
        import numpy as np
        import xarray as xr
        ds = self.dataset(extras={'other': (('unused',), np.array([9.]))})
        ds.coords['unused'] = xr.Variable(('unused',), np.array([7]))
        source, plan = self.compiled(ds)
        self.assertIs(plan._source._handle, ds)
        self.assertIsNot(plan._source, source)
        self.assertEqual(tuple(plan._source.arrays), ())
        self.assertEqual(tuple(plan.coordinates), ('x',))
        self.assertEqual(tuple(plan._source.coordinates), ('x',))
        self.assertIs(plan.coordinates['x'], plan._source.coordinates['x'])
        for name in ('dimensions', 'variables', 'coordinate_descriptors', 'attributes'):
            self.assertIs(getattr(plan._source, name), getattr(source, name))
        self.assertNotIn('unused', plan.coordinates)

    def test_plan_is_frozen_and_dict_result_is_not_mutable_backing(self):
        _, plan = self.compiled()
        before = plan.to_json()
        with self.assertRaises((TypeError, AttributeError)):
            plan.selected = None
        with self.assertRaises(TypeError):
            type('DerivedPlan', (type(plan),), {})
        value = plan.to_dict()
        value['coordinates']['x']['values'][0] = 999
        value['columns'][0]['name'] = 'changed'
        self.assertEqual(plan.to_json(), before)

    def test_same_anchor_legal_phases_compile_identical_bytes(self):
        source, plan = self.compiled()
        rec = recipe()
        prepared = rt.prepare_source(source, rec)
        materialized = self.api('materialize_source')(source, plan)
        for candidate in (source, prepared, materialized):
            with self.subTest(phase=(len(candidate.arrays), len(candidate.coordinates))):
                compiled = self.api('compile_plan')(candidate, rec)
                self.assertEqual(compiled.to_json(), plan.to_json())
                self.assertEqual(tuple(compiled._source.arrays), ())

    def test_complete_weight_and_reduced_dimension_union_and_support_offsets(self):
        import numpy as np
        import xarray as xr
        ds = xr.Dataset({'v': (('z', 'x', 'r'), np.arange(12.).reshape(2, 2, 3)),
                         'w': (('r',), np.array([1., 2., 3.]))},
                        coords={'z': [9, 7], 'x': [2, 1], 'r': [30, 10, 20]})
        rec = recipe(('x',), [column(stages=[
            stage('weighted', ('r',), 'weighted_mean', weights='w', weight_unit=None),
            stage('outer', ('z',), 'max')])])
        _, plan = self.compiled(ds, rec)
        value = plan.to_dict()
        self.assertEqual(value['selected']['variables'], ['v', 'w'])
        self.assertEqual(value['selected']['dimensions'], ['r', 'x', 'z'])
        self.assertEqual(set(value['coordinates']), {'r', 'x', 'z'})
        c = value['columns'][0]
        self.assertEqual(c['input_dims'], ['z', 'x', 'r'])
        self.assertEqual(c['weight']['dims'], ['r'])
        self.assertEqual(c['final_dims'], ['x'])
        self.assertEqual(c['output_dtype'], 'float64')
        first, second = c['stages']
        for item in (first, second):
            self.assertEqual(set(item), STAGE_FIELDS)
        self.assertEqual((first['remaining_dims'], first['support_dims']),
                         (['z', 'x'], ['x', 'z']))
        self.assertEqual((first['support_count'], first['support_start']), (4, 0))
        self.assertEqual((second['support_count'], second['support_start']), (2, 4))
        self.assertEqual(value['estimates']['support_records'], 6)

    def test_scalar_and_broadcast_grains_do_not_expand_from_unselected_dimensions(self):
        import numpy as np
        import xarray as xr
        ds = xr.Dataset({'v': ((), np.array(17, dtype='int64')),
                         'unused': (('z',), np.array([1., 2., 3.]))},
                        coords={'x': [2, 1], 'z': [1, 2, 3]})
        _, scalar = self.compiled(ds, recipe((), [column()]))
        self.assertEqual(tuple(scalar.coordinates), ())
        self.assertEqual(scalar.estimates['output_rows'], 1)
        self.assertEqual(scalar.columns[0]['input_shape'], ())
        self.assertEqual(scalar.columns[0]['output_dtype'], 'int64')
        _, repeated = self.compiled(ds, recipe(('x',), [column(broadcast=('x',))]))
        self.assertEqual(tuple(repeated.coordinates), ('x',))
        self.assertEqual(repeated.columns[0]['broadcast'], ('x',))
        self.assertEqual(repeated.estimates['output_rows'], 2)

    def test_direct_integer_widths_and_float32_are_not_promoted(self):
        import numpy as np
        for dtype, values in (('uint64', [2**64-1, 2**63+1]),
                              ('int64', [-2**63, 2**63-1]),
                              ('float32', [1.25, -0.])):
            labels = np.array([2**64-1, 2**63+1], dtype='uint64')
            source, plan = self.compiled(self.dataset(np.array(values, dtype=dtype), labels))
            self.assertEqual(plan.columns[0]['output_dtype'], dtype)
            self.assertEqual(plan.coordinates['x'].values, tuple(int(x) for x in labels))
            self.assertEqual(plan.coordinates['x'].sorted_indices, (1, 0))
            materialized = self.api('materialize_source')(source, plan)
            self.assertEqual(materialized.arrays['v'].dtype, dtype)
            self.assertEqual(materialized.arrays['v'].data, np.array(values, dtype=dtype).tobytes())

    def test_name_collisions_and_row_dimension_order_are_preserved(self):
        import numpy as np
        import xarray as xr
        ds = xr.Dataset({'v': (('stage', 'n_valid'), np.arange(4.).reshape(2, 2))},
                        coords={'stage': [2, 1], 'n_valid': ['b', 'a']})
        rec = recipe(('n_valid', 'stage'), [column(name='n_valid'), column(name='key:00')])
        _, plan = self.compiled(ds, rec)
        self.assertEqual(plan.recipe.row_dims, ('n_valid', 'stage'))
        self.assertEqual(tuple(c['name'] for c in plan.columns), ('n_valid', 'key:00'))
        self.assertEqual(plan.columns[0]['input_dims'], ('stage', 'n_valid'))
        self.assertEqual(plan.coordinates['n_valid'].sorted_indices, (1, 0))

    def test_residual_dimension_precedes_well_formed_wrong_broadcast(self):
        ds = self.dataset()
        source = rt.snapshot_dataset(ds)
        self.refused('residual_dimension', self.api('compile_plan'), source,
                     recipe((), [column(broadcast=('x',))]))

    def test_required_broadcast_is_exact_and_ordered(self):
        import numpy as np
        import xarray as xr
        ds = xr.Dataset({'v': ((), np.array(1.))}, coords={'x': [1], 'y': [2]})
        source = rt.snapshot_dataset(ds)
        for broadcast in ((), ('x',), ('y', 'x')):
            self.refused('unapproved_broadcast', self.api('compile_plan'), source,
                         recipe(('x', 'y'), [column(broadcast=broadcast)]))

    def test_illegal_reduction_dimension_and_weight_topology_refuse(self):
        import numpy as np
        ds = self.dataset(extras={'w': (('r',), np.ones(2))})
        ds.coords['r'] = [1, 2]
        source = rt.snapshot_dataset(ds)
        self.refused('invalid_recipe', self.api('compile_plan'), source,
                     recipe((), [column(stages=[stage(dims=('absent',))])]))
        self.refused('invalid_weights', self.api('compile_plan'), source,
                     recipe((), [column(stages=[stage(dims=('x',), op='weighted_mean',
                                                       weights='w', weight_unit=None)])]))

    def test_exact_unit_assertions_precede_pint(self):
        ds = self.dataset()
        ds._variables['v']._attrs = {'units': 'ms'}
        source = rt.snapshot_dataset(ds)
        with patch('replicatetable.units.qualify_conversion',
                   side_effect=AssertionError('Pint before source assertion')):
            for assertion, code in ((None, 'missing_unit_assertion'),
                                    ('s', 'source_unit_mismatch')):
                self.refused(code, self.api('compile_plan'), source,
                             recipe(columns=[column(source_unit=assertion)]))

    def test_weight_assertion_compares_exact_raw_label(self):
        import numpy as np
        ds = self.dataset(extras={'w': (('x',), np.ones(2))})
        ds._variables['w']._attrs = {'units': 'percent'}
        source = rt.snapshot_dataset(ds)
        rec = recipe((), [column(stages=[stage(dims=('x',), op='weighted_mean',
                                              weights='w', weight_unit='%')])])
        self.refused('weight_unit_mismatch', self.api('compile_plan'), source, rec)

    def test_stock_identity_unknown_affine_and_direct_conversion(self):
        ds = self.dataset()
        ds._variables['v']._attrs = {'units': 'degC'}
        _, plan = self.compiled(ds, recipe(columns=[column(source_unit='degC', target_unit='K')]))
        operation = plan.columns[0]['unit_operation']
        self.assertEqual((operation['scale'], operation['offset']), (1., 273.15))
        self.assertEqual(plan.columns[0]['output_dtype'], 'float64')
        ds._variables['v']._attrs = {'units': 'not_a_known_unit'}
        source = rt.snapshot_dataset(ds)
        self.refused('unknown_unit', self.api('compile_plan'), source,
                     recipe(columns=[column(source_unit='not_a_known_unit')]))

    def test_all_measurement_and_weight_attempts_share_one_stock_pass(self):
        import numpy as np
        from replicatetable import units
        ds = self.dataset(extras={'w': (('x',), np.ones(2))})
        rec = recipe((), [column(name='v'+str(i), stages=[stage(dims=('x',),
                     op='weighted_mean', weights='w', weight_unit=None)]) for i in range(32)])
        original = units._StockUnitContext._begin_attempt
        contexts = []
        def begin(context):
            contexts.append(context)
            return original(context)
        with patch.object(units._StockUnitContext, '_begin_attempt', begin):
            _, plan = self.compiled(ds, rec)
        self.assertEqual(len(contexts), 64)
        self.assertTrue(all(context is contexts[0] for context in contexts))
        self.assertEqual(len(plan.columns), 32)

    def test_changed_selection_requires_original_descriptor(self):
        import numpy as np
        ds = self.dataset(extras={'other': (('z',), np.array([7.]))})
        ds.coords['z'] = [1]
        source, plan = self.compiled(ds)
        rec = recipe(('z',), [column(source='other')])
        self.refused('invalid_source_phase', self.api('compile_plan'), plan._source, rec)
        other = self.api('compile_plan')(source, rec)
        self.assertEqual(tuple(other.coordinates), ('z',))

    def test_materialization_consumes_b_and_does_not_hash_unused_a(self):
        from replicatetable import source as source_module
        a = self.dataset()
        _, plan = self.compiled(a)
        b = self.dataset()
        supplied = rt.snapshot_dataset(b)
        a._variables['v']._data[0] = 91.
        original = source_module._memory_identity
        consumed = []
        def identity(dataset, descriptor):
            self.assertIsNot(dataset, a, 'unused anchor was content-hashed')
            consumed.append(dataset)
            return original(dataset, descriptor)
        with patch.object(source_module, '_memory_identity', identity):
            materialized = self.api('materialize_source')(supplied, plan)
        self.assertTrue(consumed)
        self.assertTrue(all(dataset is b for dataset in consumed))
        self.assertIs(materialized._handle, b)
        self.assertEqual(tuple(materialized.arrays['v'].view()), (1., 2.))

    def test_stale_consumed_b_is_source_changed(self):
        _, plan = self.compiled()
        b = self.dataset()
        supplied = rt.snapshot_dataset(b)
        b._variables['v']._data[0] = 8.
        self.refused('source_changed', self.api('materialize_source'), supplied, plan)

    def test_held_identity_precedes_phase_and_expensive_work(self):
        import numpy as np
        from replicatetable import source as source_module
        _, plan = self.compiled()
        supplied = rt.snapshot_dataset(self.dataset(np.array([8., 9.])))
        bad = self.clone_snapshot(supplied, coordinates={},
                                  arrays={'v': ArrayBuffer('float64', (2,), b'\0'*16)})
        with patch.object(source_module, '_memory_prepass',
                          side_effect=AssertionError('scan before held identity')):
            self.refused('source_fingerprint_mismatch', self.api('materialize_source'), bad, plan)

    def test_invalid_partial_phase_precedes_current_source_scan(self):
        import numpy as np
        import xarray as xr
        from replicatetable import source as source_module
        ds = xr.Dataset({'v': (('x', 'r'), np.ones((2, 2)))}, coords={'x': [1, 2], 'r': [1, 2]})
        source, plan = self.compiled(ds, recipe(columns=[column(stages=[stage()])]))
        bad = self.clone_snapshot(source, coordinates={'x': plan.coordinates['x']})
        with patch.object(source_module, '_memory_prepass',
                          side_effect=AssertionError('scan before phase')):
            self.refused('invalid_source_phase', self.api('materialize_source'), bad, plan)

    def test_real_same_handle_and_distinct_equivalent_admission(self):
        source, plan = self.compiled()
        inspect = self.api('inspect_call_admission')
        same = inspect(plan, source).to_dict()
        b = rt.snapshot_dataset(self.dataset())
        other = inspect(plan, b).to_dict()
        self.assertEqual(set(same), ADMISSION_FIELDS)
        self.assertEqual((same['required_dataset_count'], same['distinct_dataset_count']), (2, 1))
        self.assertEqual((other['required_dataset_count'], other['distinct_dataset_count']), (2, 2))
        self.assertEqual(same['extra_source_bytes'], 0)
        self.assertGreater(other['extra_source_bytes'], 0)
        self.assertEqual(other['baseline_bytes'], plan.estimates['estimated_memory_bytes'])
        for result in (same, other):
            self.assertEqual(result['total_bytes'], result['baseline_bytes']+
                             result['extra_source_bytes']+result['cache_bytes'])
            self.assertEqual(result['admitted'], result['total_bytes'] <= 536870912)

    def test_anchor_growth_and_shrinkage_refuse_before_coordinate_allocation(self):
        import numpy as np
        from replicatetable import source as source_module
        for old_size, new_size in ((2, 256), (256, 2)):
            old = np.zeros(old_size)
            old[:2] = [1., 2.]
            ds = self.dataset(old[:2])
            source, plan = self.compiled(ds)
            new = np.zeros(new_size)
            new[:2] = [1., 2.]
            ds._variables['v']._data = new[:2]
            with patch.object(source_module, '_prepare_coordinate_models',
                              side_effect=AssertionError('allocation before anchor equality')):
                error = self.refused('source_resource_binding_mismatch',
                                     self.api('materialize_source'), source, plan)
            self.assertEqual(error.message, 'Source resource binding changed; inspect the current source and compile a new plan before retrying.')

    def test_anchor_redistribution_with_equal_base_is_not_baseline_credit(self):
        import numpy as np
        left = np.zeros(32); right = np.zeros(64)
        left[:2] = [1., 2.]; right[:2] = [3., 4.]
        ds = self.dataset(left[:2], extras={'other': (('x',), right[:2])})
        source, plan = self.compiled(ds)
        swapped_left = np.zeros(64); swapped_right = np.zeros(32)
        swapped_left[:2] = [1., 2.]; swapped_right[:2] = [3., 4.]
        ds._variables['v']._data = swapped_left[:2]
        ds._variables['other']._data = swapped_right[:2]
        self.refused('source_resource_binding_mismatch',
                     self.api('inspect_call_admission'), plan, source)

    def test_dataset_cache_capacity_only_changes_call_local_cache(self):
        ds = self.dataset()
        source, plan = self.compiled(ds)
        inspect = self.api('inspect_call_admission')
        before = inspect(plan, source)
        canonical = plan.to_json()
        cache = {i: i for i in range(1024)}
        for key in tuple(cache):
            del cache[key]
        ds._cache = cache
        after = inspect(plan, source)
        self.assertGreater(after.cache_bytes, before.cache_bytes)
        self.assertEqual(after.baseline_bytes, before.baseline_bytes)
        self.assertEqual(after.extra_source_bytes, before.extra_source_bytes)
        self.assertEqual(plan.to_json(), canonical)
        self.assertIs(ds._cache, cache)
        self.assertEqual(cache, {})

    def test_nested_helpers_keep_outer_real_anchor_and_source(self):
        from replicatetable import admission
        source, plan = self.compiled()
        b = rt.snapshot_dataset(self.dataset())
        with admission._required_inputs(plan=plan, snapshot=b) as outer:
            with admission._required_inputs(snapshot=b) as inner:
                self.assertIs(inner, outer)
                self.assertEqual(len(inner.datasets), 2)
                self.assertTrue(any(ds is source._handle for ds in inner.datasets))
                self.assertTrue(any(ds is b._handle for ds in inner.datasets))
            self.assertIs(admission._ACTIVE.get(), outer)
        self.assertIsNone(admission._ACTIVE.get())

    def test_unqualified_result_context_refuses_without_running_backing_hooks(self):
        from replicatetable import admission
        class FakeResult:
            @property
            def _plan(self):
                raise AssertionError('fake result backing read')
        self.refused('invalid_plan_input', admission._required_inputs, result=FakeResult())
        source, plan = self.compiled()
        self.refused('invalid_plan_input', self.api('inspect_call_admission'),
                     plan, source, result=FakeResult())

    def test_saved_plan_roundtrip_and_binding_reanchor(self):
        source, plan = self.compiled()
        loaded = self.api('load_plan')(plan.to_json(), source)
        self.assertEqual(loaded.to_json(), plan.to_json())
        self.assertIs(loaded._source._handle, source._handle)
        self.assertIs(loaded.coordinates['x'], loaded._source.coordinates['x'])

    def test_saved_plan_equal_semantics_different_capacity_requires_replan(self):
        import numpy as np
        _, plan = self.compiled()
        owner = np.zeros(128); owner[:2] = [1., 2.]
        supplied = rt.snapshot_dataset(self.dataset(owner[:2]))
        self.assertEqual(supplied.identity, plan.source)
        self.refused('source_resource_binding_mismatch', self.api('load_plan'),
                     plan.to_json(), supplied)

    def test_saved_plan_wrong_held_identity_precedes_phase_runtime_and_scan(self):
        import numpy as np
        from replicatetable import source as source_module
        _, plan = self.compiled()
        supplied = rt.snapshot_dataset(self.dataset(np.array([3., 4.])))
        with patch('replicatetable.runtime.runtime_identity',
                   side_effect=AssertionError('runtime before identity')), \
             patch.object(source_module, '_memory_identity',
                          side_effect=AssertionError('semantic hash before identity')):
            self.refused('source_fingerprint_mismatch', self.api('load_plan'),
                         plan.to_json(), supplied)

    def test_saved_plan_strict_duplicate_unknown_and_exact_version_refusals(self):
        source, plan = self.compiled()
        loader = self.api('load_plan')
        raw = plan.to_json()
        self.refused('invalid_json', loader, b'{"version":2,'+raw[1:], source)
        for key, value in (('unknown', 1), ('version', True), ('formula_version', 1)):
            changed = plan.to_dict(); changed[key] = value
            self.refused('invalid_plan', loader, canonical_bytes(changed), source)

    def test_saved_plan_semantic_field_and_estimate_tampering_never_regenerates(self):
        source, plan = self.compiled()
        for field in ('selected', 'columns', 'estimates'):
            changed = plan.to_dict()
            if field == 'selected': changed[field]['numeric_bytes'] += 8
            elif field == 'columns': changed[field][0]['output_dtype'] = 'float32'
            else: changed[field]['work_cell_visits'] += 1
            with self.subTest(field=field):
                self.refused('plan_binding_mismatch', self.api('load_plan'),
                             canonical_bytes(changed), source)

    def test_saved_complete_unit_graph_is_freshly_compared(self):
        ds = self.dataset()
        ds._variables['v']._attrs = {'units': 'ms'}
        source, plan = self.compiled(ds, recipe(columns=[column(source_unit='ms', target_unit='s')]))
        changed = plan.to_dict()
        operation = changed['columns'][0]['unit_operation']
        operation['definition_graph'][0]['name'] = 'coherent_but_nonstock'
        old = operation['parsed_source'][0][0]
        operation['parsed_source'][0][0] = 'coherent_but_nonstock'
        for node in operation['definition_graph']:
            for term in node['reference']:
                if term[0] == old: term[0] = 'coherent_but_nonstock'
        operation['definition_graph'].sort(key=lambda node: node['name'])
        self.refused('plan_binding_mismatch', self.api('load_plan'),
                     canonical_bytes(changed), source)

    def test_saved_runtime_mismatch_precedes_stock_semantics(self):
        source, plan = self.compiled()
        changed = plan.to_dict()
        changed['runtime']['python']['executable']['sha256'] = 'f'*64
        with patch('replicatetable.units.qualify_conversion',
                   side_effect=AssertionError('Pint before runtime expectation')):
            self.refused('runtime_binding_mismatch', self.api('load_plan'),
                         canonical_bytes(changed), source)

    def test_success_does_not_retain_materialized_source_forest(self):
        source, plan = self.compiled()
        materialized = self.api('materialize_source')(source, plan)
        # The raw bytes are represented by the actual ArrayBuffer; lifetime is
        # observed through a separately weak-referenceable exact Dataset owner.
        b = self.dataset()
        supplied = rt.snapshot_dataset(b)
        b_ref = weakref.ref(b)
        rebound = self.api('compile_plan')(self.api('materialize_source')(supplied, plan), recipe())
        self.assertEqual(tuple(rebound._source.arrays), ())
        del materialized, supplied, b, rebound
        gc.collect()
        self.assertIsNone(b_ref())


class PlanSafetyTests(unittest.TestCase):
    """Additional observed-boundary controls; no surrogate sources or plans."""
    setUp = PlanTests.setUp
    api = PlanTests.api
    refused = PlanTests.refused
    dataset = PlanTests.dataset
    compiled = PlanTests.compiled
    clone_snapshot = PlanTests.clone_snapshot

    def test_saved_nested_schema_refuses_before_compilation(self):
        from replicatetable import plan as plan_module
        source, plan = self.compiled()
        for place in ('selected', 'column', 'coordinate', 'estimates', 'binding'):
            value = plan.to_dict()
            target = {'selected': value['selected'], 'column': value['columns'][0],
                      'coordinate': value['coordinates']['x'], 'estimates': value['estimates'],
                      'binding': value['resource_binding']}[place]
            target['unknown'] = 1
            with self.subTest(place=place), patch.object(plan_module, '_compile_memory',
                    side_effect=AssertionError('saved schema reached compiler')):
                self.refused('invalid_plan', self.api('load_plan'), canonical_bytes(value), source)

    def test_saved_scalar_types_refuse_before_compilation(self):
        from replicatetable import plan as plan_module
        source, plan = self.compiled()
        for place in ('numeric_bytes', 'column_dtype', 'coordinate_index', 'estimate'):
            value = plan.to_dict()
            if place == 'numeric_bytes': value['selected']['numeric_bytes'] = True
            elif place == 'column_dtype': value['columns'][0]['output_dtype'] = False
            elif place == 'coordinate_index': value['coordinates']['x']['sorted_indices'][0] = True
            else: value['estimates']['work_cell_visits'] = True
            with self.subTest(place=place), patch.object(plan_module, '_compile_memory',
                    side_effect=AssertionError('saved type reached compiler')):
                self.refused('invalid_plan', self.api('load_plan'), canonical_bytes(value), source)

    def test_structural_forged_estimate_never_grants_baseline_credit(self):
        from replicatetable import source as source_module
        source, plan = self.compiled()
        fields = {name: getattr(plan, name) for name in plan.__slots__}
        fields['estimates'] = thaw(plan.estimates)
        fields['estimates']['estimated_memory_bytes'] = 1
        forged = self.api('BoundPlan')(**fields)
        with patch.object(source_module, '_prepare_coordinate_models',
                          side_effect=AssertionError('forged budget permitted allocation')):
            self.refused('invalid_plan', self.api('materialize_source'), source, forged)

    def test_bound_plan_reinitialization_is_atomic_without_reading_replacements(self):
        _, plan = self.compiled()
        before = plan.to_json()
        class Poison:
            def __eq__(self, other): raise AssertionError('replacement equality')
            def __iter__(self): raise AssertionError('replacement iteration')
        self.refused('invalid_plan', plan.__init__, **{name: Poison() for name in plan.__slots__})
        self.assertEqual(plan.to_json(), before)

    def over_budget_cache(self):
        import numpy as np
        ds = self.dataset().assign_coords(y=('y', [1]), z=('z', [1]), q=('q', [1]))
        source, plan = self.compiled(ds)
        owner = np.zeros(124*1024*1024, dtype='uint8')
        mask = owner[:1].view('bool')
        for name in ('y', 'z', 'q'):
            index = ds._indexes[name].index
            object.__getattribute__(index, '__dict__')['_cache']['_isnan'] = mask
        return source, plan

    def test_complete_real_cache_diagnostic_and_preallocation_refusal(self):
        from replicatetable import source as source_module
        source, plan = self.over_budget_cache()
        admission = self.api('inspect_call_admission')(plan, source)
        self.assertFalse(admission.admitted)
        self.assertGreater(admission.total_bytes, 536870912)
        self.assertLess(admission.cache_bytes, 536870912)
        with patch.object(source_module, '_prepare_coordinate_models',
                          side_effect=AssertionError('coordinates before complete admission')), \
             patch.object(ArrayBuffer, '__init__', side_effect=AssertionError('array before complete admission')):
            self.refused('estimated_memory_limit', self.api('materialize_source'), source, plan)

    def test_selected_b_declaration_precedes_runtime_and_complete_overbudget(self):
        from replicatetable import source as source_module
        a, plan = self.over_budget_cache()
        # B has equivalent current semantics before its later declaration change.
        b = self.dataset().assign_coords(y=('y', [1]), z=('z', [1]), q=('q', [1]))
        supplied = rt.snapshot_dataset(b)
        self.assertEqual(a.identity, supplied.identity)
        b._variables['v']._attrs = {'scale_factor': 1}
        with patch('replicatetable.runtime.runtime_identity',
                   side_effect=AssertionError('runtime before selected declaration')), \
             patch.object(source_module, '_prepare_coordinate_models',
                          side_effect=AssertionError('allocation after unsupported declaration')):
            self.refused('unsupported_source_encoding', self.api('materialize_source'), supplied, plan)

    def test_active_guard_never_overlaps_fresh_owner_prepass_frames(self):
        import sys
        from replicatetable import source as source_module
        from replicatetable import admission
        source, plan = self.compiled()
        b = rt.snapshot_dataset(self.dataset())
        original = source_module._memory_prepass
        calls = []
        def scan(dataset):
            frame = sys._getframe(1)
            while frame is not None:
                self.assertFalse(any(type(value) is source_module._Prepass for value in frame.f_locals.values()),
                                 'a prior source prepass survives into the next handle scan')
                frame = frame.f_back
            calls.append(dataset)
            return original(dataset)
        with patch.object(source_module, '_memory_prepass', scan):
            with admission._required_inputs(plan=plan, snapshot=b):
                rt.prepare_source(b, plan.recipe)
            self.api('materialize_source')(b, plan)
        self.assertTrue(any(value is source._handle for value in calls))
        self.assertTrue(any(value is b._handle for value in calls))

    def test_retained_cancellation_does_not_hold_new_materialized_buffers(self):
        import numpy as np
        import sys
        source, plan = self.compiled(self.dataset(extras={'w': (('x',), np.array([3., 4.]))}),
                                     recipe(columns=[column(), column(name='other', source='w')]))
        retained = []
        writes = []
        class Cancel(BaseException):
            def __setattr__(self, name, value):
                writes.append(name)
                return super().__setattr__(name, value)
        cancel = Cancel('stop')
        original = ArrayBuffer.__init__
        calls = 0
        def construct(buffer, dtype, shape, data):
            nonlocal calls
            calls += 1
            original(buffer, dtype, shape, data)
            if calls == 1: retained.append(data)
            else: raise cancel
        enabled = gc.isenabled()
        gc.disable()
        try:
            with patch.object(ArrayBuffer, '__init__', construct):
                with self.assertRaises(Cancel) as caught:
                    self.api('materialize_source')(source, plan)
            self.assertIs(caught.exception, cancel)
            self.assertIsNone(cancel.__cause__)
            self.assertIsNone(cancel.__context__)
            self.assertEqual(writes, [])
            self.assertEqual(sys.getrefcount(retained[0]), 2)
        finally:
            if enabled: gc.enable()

    def test_saved_raw_and_recipe_remain_additive_through_final_admission(self):
        from replicatetable import admission, plan as plan_module
        from replicatetable._resource_inputs import _recipe_cost
        source, plan = self.compiled()
        raw = plan.to_json() + b' ' * 4096
        observations = []
        original = admission._guard
        def guard(phase, *, baseline=None):
            value = original(phase, baseline=baseline)
            active = admission._ACTIVE.get()
            if active is not None and active.plan is not None:
                route = plan_module._ROUTE.get()
                self.assertIsNotNone(route)
                observations.append((value, route.extra, len(route.raw)))
            return value
        with patch.object(admission, '_guard', guard):
            loaded = self.api('load_plan')(raw, source)
        self.assertEqual(loaded.to_json(), plan.to_json())
        self.assertTrue(observations)
        for total, extra, length in observations:
            self.assertEqual(length, len(raw))
            self.assertGreaterEqual(extra, len(raw))
            self.assertGreaterEqual(total, plan.estimates['estimated_memory_bytes'] + extra)


class FrozenCompilerRefusals(unittest.TestCase):
    """Read unchanged expected codes and apply only copied fixture mutations."""
    setUp = PlanTests.setUp
    api = PlanTests.api
    refused = PlanTests.refused
    def fixture(self, name):
        root = Path(__file__).resolve().parents[1] / 'frozen' / 'original'
        return json.loads((root / 'fixtures' / (name+'.json')).read_bytes())

    def from_fixture(self, fixture):
        import numpy as np
        import xarray as xr
        data = fixture['data']
        coords = {}
        for name, values in data['coords'].items():
            dtype = object if any(value is None for value in values) else None
            coords[name] = (name, np.array(values, dtype=dtype))
        variables = {}
        for name, variable in data['variables'].items():
            shape = tuple(len(data['coords'][d]) for d in variable['dims'])
            raw = [float('nan') if value is None else value for value in variable['values']]
            values = np.array(raw, dtype=variable['dtype']).reshape(shape)
            variables[name] = xr.Variable(variable['dims'], values,
                                           attrs={'units': variable['units']})
        ds = xr.Dataset(variables, coords=xr.Coordinates(coords, indexes={}))
        for name, (_, values) in coords.items():
            ds._variables[name]._data = values
        return ds

    def test_original_compiler_controls_keep_frozen_codes(self):
        from tests.frozen_tools import adapt_legacy_recipe
        root = Path(__file__).resolve().parents[1] / 'frozen' / 'original'
        expected = json.loads((root / 'frozen_expected.json').read_bytes())
        controls = {entry['id']: entry for entry in expected['refusals']}
        mutations = ('R01', 'R02', 'R03', 'R04', 'R07', 'R08', 'R09', 'R10', 'R11', 'R13', 'R14')
        compile_plan = self.api('compile_plan')
        for name in mutations:
            control = controls[name]
            original = self.fixture(control['base'])
            fixture = copy.deepcopy(original)
            rec = adapt_legacy_recipe(fixture)
            columns = {item['name']: item for item in rec['columns']}
            if name == 'R01': columns['response_mean']['stages'] = []
            elif name == 'R02': fixture['data']['coords']['case'] = ['c0', 'c0']
            elif name == 'R03': fixture['data']['coords']['case'][1] = None
            elif name == 'R04': columns['covariate']['broadcast'] = []
            elif name == 'R07': columns['duration_mean']['target_unit'] = 'not_a_known_unit'
            elif name == 'R08': columns['duration_mean']['target_unit'] = 'kg'
            elif name == 'R09': columns['duration_mean']['source_unit'] = None
            elif name == 'R10':
                columns['equal_replicate']['stages'][1].update(op='weighted_mean', weights='weights')
            elif name == 'R11': del columns['response_mean']['stages'][0]['missing']
            elif name == 'R13': columns['duration_mean']['source_unit'] = 's'
            ds = self.from_fixture(fixture)
            if name == 'R14':
                # Remove coordinate membership while preserving data shape.
                ds = ds.drop_vars('case')
            with self.subTest(control=name):
                def run():
                    parsed = Recipe.from_dict(rec)
                    return compile_plan(rt.snapshot_dataset(ds), parsed)
                self.refused(control['code'], run)
            self.assertEqual(self.fixture(control['base']), original)

    def test_original_r12_compares_new_held_source_identity(self):
        from tests.frozen_tools import adapt_legacy_recipe
        root = Path(__file__).resolve().parents[1] / 'frozen' / 'original'
        controls = json.loads((root / 'frozen_expected.json').read_bytes())['refusals']
        control = next(value for value in controls if value['id'] == 'R12')
        original = self.fixture(control['base'])
        ds = self.from_fixture(original)
        source = rt.snapshot_dataset(ds)
        plan = self.api('compile_plan')(source, Recipe.from_dict(adapt_legacy_recipe(original)))
        ds._variables['response']._data.flat[0] = 1.
        changed = rt.snapshot_dataset(ds)
        self.refused(control['code'], self.api('materialize_source'), changed, plan)
        self.assertEqual(self.fixture(control['base']), original)


if __name__ == '__main__':
    unittest.main()
