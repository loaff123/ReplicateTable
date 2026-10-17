"""Actual-source reader reservation across standalone and canonical phases."""
from unittest.mock import patch
from replicatetable import admission, resources
from replicatetable.plan import _load_source_base
from replicatetable._native_budget import _parent_bytes
from tests.unit.test_reduce import ReductionCase, dataset, recipe


class ReaderAdmissionTests(ReductionCase):
    def setUp(self):
        super().setUp()
        self.assertTrue(callable(getattr(admission, '_BundleReaderScope', None)),
                        'Actual reader bootstrap reservation is absent')

    def simple(self):
        return self.run_case(dataset({'v': (('x',), [1., 2.], 'float64', None)},
            {'x': ([2, 1], 'int64')}), recipe(('x',)))

    def test_standalone_explicit_codec_baseline_includes_fixed_reader_reserve(self):
        source, _, _ = self.simple()
        original = _load_source_base(source)
        w136 = _parent_bytes(136, 29512)
        self.assertEqual(w136, 2913396)
        with admission._BundleReaderScope(source):
            self.assertEqual(_load_source_base(source), original+w136)
        self.assertEqual(_load_source_base(source), original)

    def test_actual_plan_guard_adds_only_reader_minus_plan_parent_credit(self):
        source, plan, result = self.simple()
        with admission._required_inputs(plan=plan, snapshot=source, result=result):
            ordinary = admission._guard('serialize')
            with admission._BundleReaderScope(source):
                extra = admission._bundle_reader_extra(plan)
                self.assertGreater(extra, 0)
                self.assertLess(extra, 2913396)
                total = admission._guard('serialize')
                self.assertEqual(total, ordinary+extra)
                # Isolate exact boundary arithmetic after the real source/plan
                # measurement. This simulated cache total is not IO authority.
                observed = admission._inspect_current().to_dict()
                for excess in (0, 1):
                    values = dict(observed)
                    values['cache_bytes'] += resources.LOGICAL_JOURNEY_LIMIT-extra-observed['total_bytes']+excess
                    values['total_bytes'] = resources.LOGICAL_JOURNEY_LIMIT-extra+excess
                    with patch.object(admission, '_inspect_current', return_value=admission.CallAdmission(**values)):
                        if excess:
                            self.refused('estimated_memory_limit', admission._guard, 'serialize')
                        else:
                            self.assertEqual(admission._guard('serialize'), resources.LOGICAL_JOURNEY_LIMIT)

    def test_exception_restores_context_and_retires_source_reader_references(self):
        source, _, _ = self.simple()
        expected = KeyboardInterrupt('fixture')
        scope = admission._BundleReaderScope(source)
        try:
            with scope:
                self.assertEqual(admission._bundle_reader_extra(), 2913396)
                raise expected
        except KeyboardInterrupt as observed:
            self.assertIs(observed, expected)
        self.assertEqual(admission._bundle_reader_extra(), 0)
        self.assertIsNone(scope._source)
        self.assertIsNone(scope._reader)

    def test_scope_rejects_scalar_source_and_fake_reader_authority(self):
        self.refused('invalid_source', admission._BundleReaderScope, object())
        source, _, _ = self.simple()
        with admission._BundleReaderScope(source) as scope:
            self.refused('unsafe_path', scope.adopt, object())
