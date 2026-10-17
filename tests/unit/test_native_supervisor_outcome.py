"""First native finding and readonly borrowed operation error values.

These scalar tests establish no worker/source/stage/commit authority.
"""
import importlib
import unittest
from unittest.mock import patch

from replicatetable.errors import Refusal
from replicatetable._native_budget_state import _CancellationState


class NativeOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('replicatetable._native_supervisor')
        for name in ('_Outcome', '_record_failure', '_record_check',
                     '_select_failed_start', '_error_from_outcome', '_OperationFailure'):
            self.assertTrue(callable(getattr(self.m, name, None)),
                            'Frozen native outcome interface is missing: ' + name)
        self.models = importlib.import_module('replicatetable._bundle_models')

    def new(self):
        cancellation = _CancellationState()
        return self.m._Outcome(cancellation), cancellation

    def test_initial_owner_retains_one_cancellation_and_no_success_authority(self):
        outcome, cancellation = self.new()
        self.assertIs(outcome.cancellation, cancellation)
        self.assertIsNone(outcome.finding)
        self.assertIsNone(outcome.status)
        self.assertEqual(outcome.exit_code, 0)
        self.assertFalse(outcome.committed)
        self.assertIsNone(outcome.receipt)
        self.assertIsNone(outcome.prepared)
        self.assertEqual(set(outcome.checks),
                         {'structure', 'source_binding', 'runtime_binding', 'replay', 'report'})
        self.assertTrue(all(value == 'not_attempted' for value in outcome.checks.values()))
        self.assertFalse(outcome.startup_failed)

    def test_first_finding_preserves_code_message_exit_and_observed_checks(self):
        outcome, _ = self.new()
        self.m._record_check(outcome, 'structure', 'passed')
        self.m._record_check(outcome, 'runtime_binding', 'failed')
        self.m._record_failure(outcome, 'runtime_changed', 'Runtime binding changed.', 2)
        first = outcome.finding
        self.m._record_failure(outcome, 'io_error', 'Cleanup did not finish.', 3)
        self.assertIs(outcome.finding, first)
        self.assertEqual(outcome.finding['code'], 'runtime_changed')
        self.assertEqual(outcome.finding['message'], 'Runtime binding changed.')
        self.assertEqual(outcome.exit_code, 2)
        self.assertEqual(outcome.status, 'refused')
        self.assertEqual(outcome.checks['structure'], 'passed')
        self.assertEqual(outcome.checks['runtime_binding'], 'failed')
        self.assertEqual(outcome.checks['source_binding'], 'not_attempted')

    def test_operation_error_borrows_exact_immutable_envelope(self):
        outcome, _ = self.new()
        self.m._record_failure(outcome, 'io_error', 'Operation could not complete.', 3)
        error = self.m._error_from_outcome(outcome)
        self.assertIsInstance(error, Refusal)
        self.assertIs(type(error.envelope), self.models.ErrorEnvelope)
        self.assertIs(error.envelope.checks, outcome.checks)
        self.assertEqual((error.code, error.message, error.exit_code),
                         ('io_error', 'Operation could not complete.', 3))
        self.assertEqual(error.envelope.status, 'failed')
        self.assertFalse(error.envelope.committed)
        self.assertIsNone(error.envelope.receipt)
        for name in ('envelope', 'code', 'message', 'exit_code'):
            with self.subTest(name=name), self.assertRaises(AttributeError):
                setattr(error, name, None)
        with self.assertRaises(TypeError):
            type('DerivedOperationFailure', (self.m._OperationFailure,), {})

    def test_no_finding_cannot_be_projected_as_an_error_or_success(self):
        outcome, _ = self.new()
        with self.assertRaises(Refusal) as caught:
            self.m._error_from_outcome(outcome)
        self.assertEqual(caught.exception.code, 'supervision_unavailable')

    def test_failed_start_uses_the_contextual_operational_exit(self):
        outcome, _ = self.new()
        self.m._select_failed_start(outcome, None)
        error = self.m._error_from_outcome(outcome)
        self.assertEqual((error.code, error.envelope.status, error.exit_code),
                         ('supervision_unavailable', 'failed', 3))
        self.assertEqual(error.message,
                         'Native worker startup failed; worker termination could not be confirmed.')
        self.assertTrue(outcome.startup_failed)
        self.assertFalse(error.envelope.committed)
        self.assertIsNone(error.envelope.receipt)

    def test_both_observed_first_signals_select_cancelled_without_reclassification(self):
        for first, later in ((2, 15), (15, 2)):
            outcome, cancellation = self.new()
            cancellation._latch(first)
            self.m._select_failed_start(outcome, None)
            cancellation._latch(later)
            self.m._record_failure(outcome, 'io_error', 'Cleanup did not finish.', 3)
            error = self.m._error_from_outcome(outcome)
            self.assertEqual((error.code, error.envelope.status, error.exit_code),
                             ('interrupted', 'cancelled', 128 + first))
            self.assertEqual(error.message, 'Operation interrupted during worker startup; '
                             'worker termination could not be confirmed.')
            self.assertEqual(cancellation.signum, first)

    def test_first_late_signal_remains_recorded_without_replacing_startup_failure(self):
        outcome, cancellation = self.new()
        self.m._select_failed_start(outcome, None)
        first = outcome.finding
        cancellation._latch(15)
        self.assertIs(outcome.finding, first)
        self.assertEqual(outcome.cancellation.signum, 15)
        self.assertEqual(outcome.exit_code, 3)
        self.assertEqual(self.m._error_from_outcome(outcome).code, 'supervision_unavailable')

    def test_stage_hint_has_only_the_approved_generated_basename(self):
        for signum in (0, 2, 15):
            for with_stage in (False, True):
                outcome, cancellation = self.new()
                if signum:
                    cancellation._latch(signum)
                basename = '.replicatetable-stage-' + 'b4' * 16 if with_stage else None
                self.m._select_failed_start(outcome, basename)
                error = self.m._error_from_outcome(outcome)
                expected_length = (87 if signum else 72) + (164 if with_stage else 0)
                self.assertEqual(len(error.message.encode('ascii')), expected_length)
                raw = error.envelope.to_json()
                self.assertLessEqual(len(raw), 521)
                self.assertTrue(raw.endswith(b'\n'))
                if basename:
                    self.assertIn(basename, error.message)
                self.assertNotIn('/', error.message)

    def test_prior_finding_is_not_turned_into_a_failed_launch(self):
        outcome, _ = self.new()
        self.m._record_failure(outcome, 'invalid_source', 'Source is invalid.', 2)
        with self.assertRaises(Refusal) as caught:
            self.m._select_failed_start(outcome, None)
        self.assertEqual(caught.exception.code, 'supervision_unavailable')
        self.assertFalse(outcome.startup_failed)
        self.assertEqual(outcome.finding['code'], 'invalid_source')

    def test_exact_types_precede_caller_hooks(self):
        class Hook:
            def __eq__(self, other):
                raise AssertionError('unqualified equality')
            def __hash__(self):
                raise AssertionError('unqualified hashing')
        with self.assertRaises(Refusal):
            self.m._Outcome(Hook())
        outcome, _ = self.new()
        for args in ((Hook(), 'Operation failed.', 3),
                     ('io_error', Hook(), 3), ('io_error', 'Operation failed.', True)):
            with self.assertRaises(Refusal):
                self.m._record_failure(outcome, *args)
            self.assertIsNone(outcome.finding)

    def test_native_owner_and_operation_error_cannot_be_reinitialized(self):
        outcome, cancellation = self.new()
        self.m._record_failure(outcome, 'io_error', 'Operation failed.', 3)
        error = self.m._error_from_outcome(outcome)
        original = error.envelope
        with self.assertRaises(Refusal):
            outcome.__init__(cancellation)
        with self.assertRaises(Refusal):
            error.__init__(original, 3)
        self.assertIs(error.envelope, original)
        self.assertEqual(outcome.finding['code'], 'io_error')


if __name__ == '__main__':
    unittest.main()
