"""Private budget-state behavior only; no source/route/native qualification."""
import importlib
import sys
import unittest
from unittest.mock import patch
from replicatetable.errors import Refusal, ComputationError


LIMIT = 536870912
COUNT_MAX = (1 << 63) - 1
WINDOW = 60000000000


class NativeBudgetStateTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('replicatetable._native_budget_state')
        for name in ('_CancellationState', 'Deadline', 'LogicalOnlyBudget',
                     '_start_deadline', '_inherited_deadline', '_checkpoint',
                     '_require_deadline', '_admit'):
            self.assertTrue(callable(getattr(self.m, name, None)),
                            'Approved private budget-state interface is missing: ' + name)

    def cancel(self):
        return self.m._CancellationState()

    def refusal(self, code, function, *args):
        with self.assertRaises(Refusal) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_cancellation_starts_clear_and_keeps_first_signal(self):
        value = self.cancel()
        self.assertEqual(value.signum, 0)
        value._latch(2)
        value._latch(15)
        self.assertEqual(value.signum, 2)
        other = self.cancel()
        other._latch(15)
        other._latch(2)
        self.assertEqual(other.signum, 15)

    def test_signal_exact_domain_and_no_hooks(self):
        class Hook:
            def __eq__(self, other):
                raise AssertionError('untrusted signal equality')
        for signum in (0, 1, 3, 9, True, 2.0, '2', None, Hook()):
            value = self.cancel()
            self.refusal('supervision_unavailable', value._latch, signum)
            self.assertEqual(value.signum, 0)

    def test_deadline_records_exact_absolute_time_once(self):
        cancellation = self.cancel()
        with patch.object(self.m, 'monotonic_ns', return_value=7) as now:
            value = self.m._start_deadline(cancellation)
        self.assertIs(type(value), self.m.Deadline)
        self.assertEqual(value.deadline_ns, 7 + WINDOW)
        self.assertEqual(now.call_count, 1)
        with patch.object(self.m, 'monotonic_ns', return_value=8):
            self.m._checkpoint(value)
        self.assertEqual(value.deadline_ns, 7 + WINDOW)

    def test_inherited_deadline_has_no_clock_or_reset(self):
        with patch.object(self.m, 'monotonic_ns', side_effect=AssertionError):
            value = self.m._inherited_deadline(123, self.cancel())
            self.assertEqual(value.deadline_ns, 123)
        with patch.object(self.m, 'monotonic_ns', return_value=123):
            failure = self.refusal('operation_timeout', self.m._checkpoint, value)
        self.assertIsInstance(failure, ComputationError)
        self.assertEqual(value.deadline_ns, 123)

    def test_deadline_equality_is_expired(self):
        value = self.m.Deadline(100, self.cancel())
        with patch.object(self.m, 'monotonic_ns', return_value=99):
            self.m._checkpoint(value)
        for instant in (100, 101):
            with patch.object(self.m, 'monotonic_ns', return_value=instant):
                self.refusal('operation_timeout', self.m._checkpoint, value)

    def test_checked_start_arithmetic_equality_and_plus_one(self):
        with patch.object(self.m, 'monotonic_ns', return_value=COUNT_MAX-WINDOW):
            value = self.m._start_deadline(self.cancel())
        self.assertEqual(value.deadline_ns, COUNT_MAX)
        with patch.object(self.m, 'monotonic_ns', return_value=COUNT_MAX-WINDOW+1):
            self.refusal('supervision_unavailable', self.m._start_deadline, self.cancel())

    def test_invalid_absolute_timestamps_refuse(self):
        for instant in (-1, COUNT_MAX+1, True, 1.5, '1', None):
            self.refusal('supervision_unavailable', self.m.Deadline, instant, self.cancel())
            self.refusal('supervision_unavailable', self.m._inherited_deadline, instant, self.cancel())
        for instant in (-1, COUNT_MAX+1, True, 1.5):
            with patch.object(self.m, 'monotonic_ns', return_value=instant):
                self.refusal('supervision_unavailable', self.m._start_deadline, self.cancel())

    def test_cancellation_precedes_expiry_without_reading_clock(self):
        cancellation = self.cancel()
        value = self.m.Deadline(0, cancellation)
        cancellation._latch(2)
        with patch.object(self.m, 'monotonic_ns', side_effect=AssertionError):
            failure = self.refusal('interrupted', self.m._checkpoint, value)
        self.assertEqual(failure.exit_code, 130)

    def test_logical_only_never_reads_clock(self):
        cancellation = self.cancel()
        with patch.object(self.m, 'monotonic_ns', side_effect=AssertionError):
            value = self.m.LogicalOnlyBudget(cancellation)
            self.m._checkpoint(value)
            self.assertEqual(self.m._admit(value, 12, 3), 15)
            cancellation._latch(15)
            failure = self.refusal('interrupted', self.m._checkpoint, value)
        self.assertEqual(failure.exit_code, 143)

    def test_native_gate_accepts_only_exact_deadline(self):
        value = self.m.Deadline(10, self.cancel())
        self.assertIs(self.m._require_deadline(value), value)
        for invalid in (self.m.LogicalOnlyBudget(self.cancel()), None, object(), 10):
            self.refusal('supervision_unavailable', self.m._require_deadline, invalid)

    def test_admission_exact_limit_and_plus_one(self):
        value = self.m.LogicalOnlyBudget(self.cancel())
        self.assertEqual(self.m._admit(value, LIMIT-1, 1), LIMIT)
        self.refusal('estimated_memory_limit', self.m._admit, value, LIMIT, 1)
        self.refusal('estimated_memory_limit', self.m._admit, value, LIMIT+1, 0)

    def test_admission_checks_exact_scalar_domains(self):
        value = self.m.LogicalOnlyBudget(self.cancel())
        for bad in (True, 1.0, -1, COUNT_MAX+1, None, '1'):
            self.refusal('invalid_source', self.m._admit, value, bad, 0)
            self.refusal('invalid_source', self.m._admit, value, 0, bad)

    def test_valid_domain_admission_checks_cancellation_before_total(self):
        cancellation = self.cancel()
        value = self.m.LogicalOnlyBudget(cancellation)
        cancellation._latch(2)
        self.refusal('interrupted', self.m._admit, value, LIMIT, 1)
        self.refusal('invalid_source', self.m._admit, value, True, 1)

    def test_cancelled_failure_has_readonly_coherent_small_classification(self):
        for signum, exit_code in ((2, 130), (15, 143)):
            cancellation = self.cancel()
            value = self.m.LogicalOnlyBudget(cancellation)
            cancellation._latch(signum)
            failure = self.refusal('interrupted', self.m._checkpoint, value)
            self.assertEqual(failure.signum, signum)
            self.assertEqual(failure.exit_code, exit_code)
            self.assertLessEqual(len(failure.message), 512)
            for name, replacement in (('code', 'io_error'), ('message', 'changed'),
                                      ('signum', 0), ('exit_code', 3)):
                with self.assertRaises(AttributeError):
                    setattr(failure, name, replacement)
            self.refusal('supervision_unavailable', failure.__init__, signum)
            self.assertEqual(failure.exit_code, exit_code)

    def test_constructor_reentry_does_not_reset_state(self):
        cancellation = self.cancel()
        cancellation._latch(2)
        self.refusal('supervision_unavailable', cancellation.__init__)
        self.assertEqual(cancellation.signum, 2)
        deadline = self.m.Deadline(100, self.cancel())
        self.refusal('supervision_unavailable', deadline.__init__, 200, self.cancel())
        self.assertEqual(deadline.deadline_ns, 100)
        logical = self.m.LogicalOnlyBudget(cancellation)
        self.refusal('supervision_unavailable', logical.__init__, self.cancel())
        self.refusal('interrupted', self.m._checkpoint, logical)

    def test_uninitialized_and_partially_initialized_state_refuse(self):
        for cls in (self.m.Deadline, self.m.LogicalOnlyBudget):
            value = object.__new__(cls)
            self.refusal('supervision_unavailable', self.m._checkpoint, value)
        cancellation = object.__new__(self.m._CancellationState)
        self.refusal('supervision_unavailable', cancellation._latch, 2)
        self.refusal('supervision_unavailable', self.m.Deadline, 100, cancellation)
        partial = object.__new__(self.m.Deadline)
        object.__setattr__(partial, '_deadline_ns', 100)
        self.refusal('supervision_unavailable', partial.__init__, 200, self.cancel())
        self.refusal('supervision_unavailable', self.m._checkpoint, partial)

    def test_closed_classes_have_no_instance_dict_or_mutable_settings(self):
        cancellation = self.cancel()
        for value in (cancellation, self.m.Deadline(100, cancellation),
                      self.m.LogicalOnlyBudget(cancellation)):
            self.assertFalse(hasattr(value, '__dict__'))
            with self.assertRaises(AttributeError):
                value.extra = 1
        with self.assertRaises(AttributeError):
            cancellation.signum = 2
        deadline = self.m.Deadline(100, cancellation)
        with self.assertRaises(AttributeError):
            deadline.deadline_ns = 200

    def test_no_duck_state_or_callback_is_accepted(self):
        class Hook:
            def __getattr__(self, name):
                raise AssertionError('caller state hook invoked')
            def __call__(self):
                raise AssertionError('caller callback invoked')
        hook = Hook()
        for invalid in (hook, None, {}, ()): 
            self.refusal('supervision_unavailable', self.m._checkpoint, invalid)
            self.refusal('supervision_unavailable', self.m.Deadline, 100, invalid)
            self.refusal('supervision_unavailable', self.m.LogicalOnlyBudget, invalid)

    def test_both_records_fit_existing_two_state_slots(self):
        cancellation = self.cancel()
        deadline = self.m.Deadline(COUNT_MAX, cancellation)
        logical = self.m.LogicalOnlyBudget(cancellation)
        self.assertLessEqual(sys.getsizeof(cancellation)+sys.getsizeof(cancellation.signum), 512)
        self.assertLessEqual(sys.getsizeof(deadline)+sys.getsizeof(deadline.deadline_ns), 512)
        self.assertLessEqual(sys.getsizeof(logical), 512)
        self.assertEqual(2*512, 1024)
        self.assertLessEqual(2, 160)
        # Borrowed cancellation stays counted separately; no whole-call claim.
