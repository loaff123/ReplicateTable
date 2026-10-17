"""Permanent controls for the independent compiler review findings.

Sources, constructors, source scans and stock units are real. Runtime discovery
uses the same explicitly labeled schema fixture as test_plan; separate reviewed
probes exercise actual discovery. The near-limit Recipe test is a scalar
admission seam, not a practical capacity or whole-heap claim.
"""
import unittest
from unittest.mock import patch

import replicatetable as rt
from replicatetable import admission, plan as plan_module, source as source_module
from replicatetable.model import Coordinate, MetadataValue, ArrayBuffer
from replicatetable.codec import thaw
from replicatetable._resource_inputs import _recipe_cost
from tests.unit import test_plan as base


class CompilerReviewTests(unittest.TestCase):
    setUp = base.PlanTests.setUp
    api = base.PlanTests.api
    refused = base.PlanTests.refused
    dataset = base.PlanTests.dataset
    compiled = base.PlanTests.compiled
    clone_snapshot = base.PlanTests.clone_snapshot

    def replace_plan(self, original, **changes):
        fields = {name: getattr(original, name) for name in original.__slots__}
        fields.update(changes)
        return rt.BoundPlan(**fields)

    def false_coordinates(self):
        source, plan = self.compiled()
        backing = self.clone_snapshot(plan._source,
                    coordinates={'x': Coordinate('<i8', [4, 3], [1, 0])})
        return source, self.replace_plan(plan, coordinates=backing.coordinates, _source=backing)

    def test_materialization_binds_plan_coordinates_to_actual_b(self):
        source, forged = self.false_coordinates()
        self.assertTrue(rt.inspect_call_admission(forged, source).admitted)
        self.refused('plan_binding_mismatch', rt.materialize_source, source, forged)

    def test_active_preparation_binds_plan_coordinates_to_actual_b(self):
        source, forged = self.false_coordinates()
        with admission._required_inputs(plan=forged, snapshot=source):
            self.refused('plan_binding_mismatch', rt.prepare_source, source, forged.recipe)

    def test_materialization_binds_actual_raw_unit_descriptor(self):
        first = self.dataset(); first._variables['v']._attrs = {'units': 's'}
        other = self.dataset(); other._variables['v']._attrs = {'units': 'm'}
        source, source_plan = self.compiled(first,
                    base.recipe(columns=[base.column(source_unit='s')]))
        _, other_plan = self.compiled(other,
                    base.recipe(columns=[base.column(source_unit='m')]))
        self.assertEqual(source_plan.resource_binding, other_plan.resource_binding)
        backing = self.clone_snapshot(other_plan._source, identity=source.identity,
                                      _handle=source._handle)
        forged = self.replace_plan(other_plan, source=source.identity, _source=backing)
        self.assertTrue(rt.inspect_call_admission(forged, source).admitted)
        self.refused('plan_binding_mismatch', rt.materialize_source, source, forged)

    def test_nested_load_refuses_before_source_walk_or_full_parse(self):
        source, plan = self.compiled()
        raw = plan.to_json()
        with admission._required_inputs(plan=plan, snapshot=source), \
             patch.object(source_module, '_memory_prepass',
                          side_effect=AssertionError('source walk before context refusal')), \
             patch.object(plan_module, 'strict_loads',
                          side_effect=AssertionError('full parse before context refusal')):
            self.refused('invalid_plan_input', rt.load_plan, raw, source)

    def test_active_prepare_recipe_exact_scalar_boundary(self):
        source, plan = self.compiled()
        separate_recipe = base.recipe()
        self.assertIsNot(separate_recipe, plan.recipe)
        extra = _recipe_cost(separate_recipe).object_bytes
        limit = 536870912
        for excess in (0, 1):
            total = limit-extra+excess
            scalar = admission.CallAdmission(version=2, formula_version=2,
                baseline_bytes=total, extra_source_bytes=0, cache_bytes=0,
                total_bytes=total, limit_bytes=limit, admitted=True,
                required_dataset_count=2, distinct_dataset_count=1)
            with self.subTest(excess=excess), admission._required_inputs(plan=plan, snapshot=source), \
                 patch.object(admission, '_inspect_current', return_value=scalar):
                if excess:
                    with patch.object(source_module, '_prepare_coordinate_models',
                            side_effect=AssertionError('coordinates before Recipe admission')):
                        self.refused('estimated_memory_limit', rt.prepare_source, source, separate_recipe)
                else:
                    prepared = rt.prepare_source(source, separate_recipe)
                    self.assertEqual(prepared.coordinates['x'].values, (2, 1))

    def test_active_recheck_requires_held_identity_before_owner_scanning(self):
        source, plan = self.compiled()
        changed = self.dataset()
        changed._variables['v']._data[0] = 9.
        other = rt.snapshot_dataset(changed)
        self.assertIs(source_module.recheck_source(other), other)
        with admission._required_inputs(plan=plan, snapshot=other), \
             patch.object(source_module, '_memory_prepass',
                          side_effect=AssertionError('owner walk before held identity')):
            self.refused('source_fingerprint_mismatch', source_module.recheck_source, other)

    def test_active_recheck_requires_exact_phase_before_owner_scanning(self):
        source, plan = self.compiled()
        materialized = rt.materialize_source(source, plan)
        partial = self.clone_snapshot(materialized, coordinates={})
        with admission._required_inputs(plan=plan, snapshot=partial), \
             patch.object(source_module, '_memory_prepass',
                          side_effect=AssertionError('owner walk before phase')):
            self.refused('invalid_source_phase', source_module.recheck_source, partial)

    def test_admission_refuses_descriptor_model_exceeding_funded_slot(self):
        source, plan = self.compiled()
        inflated = self.clone_snapshot(source,
            attributes=MetadataValue({'padding': 'x'*1024}))
        self.assertGreater(source_module._retained_projection(inflated)[0].object_bytes,
                           plan.estimates['descriptor_objects_bytes'])
        self.refused('plan_binding_mismatch', rt.inspect_call_admission, plan, inflated)
        with admission._required_inputs(plan=plan, snapshot=inflated):
            self.refused('plan_binding_mismatch', admission._guard, 'prepared')

    def test_admission_refuses_coordinate_model_exceeding_funded_slot(self):
        import numpy as np
        source, plan = self.compiled(self.dataset(labels=np.array(['b', 'a'], dtype='<U256')))
        prepared = rt.prepare_source(source, plan.recipe)
        self.assertTrue(rt.inspect_call_admission(plan, prepared).admitted)
        inflated = self.clone_snapshot(prepared,
            coordinates={'x': Coordinate('<U256', ['b'*256, 'a'*256], [1, 0])})
        self.assertGreater(source_module._retained_projection(inflated)[1].object_bytes,
                           plan.estimates['coordinate_objects_bytes'])
        self.refused('plan_binding_mismatch', rt.inspect_call_admission, plan, inflated)

    def test_admission_refuses_numeric_model_exceeding_funded_slot(self):
        import struct
        source, plan = self.compiled()
        materialized = rt.materialize_source(source, plan)
        self.assertTrue(rt.inspect_call_admission(plan, materialized).admitted)
        variables = thaw(source.variables)
        coordinates = thaw(source.coordinate_descriptors)
        variables['v']['shape'] = [3]
        coordinates['x']['shape'] = [3]
        inflated = self.clone_snapshot(source, dimensions={'x': 3}, variables=variables,
            coordinate_descriptors=coordinates,
            coordinates={'x': Coordinate('<i8', [3, 2, 1], [2, 1, 0])},
            arrays={'v': ArrayBuffer('<f8', [3], struct.pack('<3d', 1., 2., 3.))})
        self.assertGreater(source_module._retained_projection(inflated)[3],
                           plan.estimates['selected_numeric_bytes'])
        self.refused('plan_binding_mismatch', rt.inspect_call_admission, plan, inflated)


    def test_nested_materialization_rejects_third_distinct_numeric_union(self):
        source, plan = self.compiled()
        first = rt.materialize_source(source, plan)
        second = rt.materialize_source(source, plan)
        # Isolate numeric ownership: descriptors and Coordinate instances are
        # shared, but the two ordinary materializations own different bytes.
        second = self.clone_snapshot(second, coordinates=first.coordinates)
        self.assertIsNot(first.arrays['v'].data, second.arrays['v'].data)
        with admission._required_inputs(plan=plan, snapshot=first):
            self.assertIs(source_module.recheck_source(first), first)
            allowed = rt.materialize_source(first, plan)
            self.assertEqual(allowed.arrays['v'].data, first.arrays['v'].data)
            self.assertTrue(rt.inspect_call_admission(plan, allowed).admitted)
            self.assertIs(source_module.recheck_source(allowed), allowed)
            prepared = rt.prepare_source(allowed, plan.recipe)
            self.assertFalse(prepared.arrays)
            del prepared
            del allowed
            with patch.object(source_module, '_prepare_coordinate_models',
                    side_effect=AssertionError('selected allocation before nested slot check')):
                self.refused('invalid_plan_input', rt.materialize_source, second, plan)



if __name__ == '__main__':
    unittest.main()
