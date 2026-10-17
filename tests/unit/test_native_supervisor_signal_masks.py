"""Avoid the stock Python enum wrapper's duplicate mask set forest."""
import _signal
import signal
import unittest
from unittest.mock import patch

from tests.unit import test_native_supervisor_signals as fixtures


class RawMaskBoundaryTests(unittest.TestCase):
    setUp = fixtures.NativeSignalPolicyTests.setUp
    restore_fixture_policy = fixtures.NativeSignalPolicyTests.restore_fixture_policy

    def test_mask_pending_path_does_not_enter_enum_copy_wrappers(self):
        # Kernel action state is independently real; isolate the mask boundary
        # from the already demonstrated libc action-byte defect.
        with (patch.object(self.m, '_query_action', fixtures.action),
              patch.object(self.m, '_restore_action', fixtures.set_action),
              patch.object(signal, 'pthread_sigmask',
                           side_effect=AssertionError('Duplicate enum mask forest')),
              patch.object(signal, 'sigpending',
                           side_effect=AssertionError('Duplicate enum pending forest'))):
            policy = self.m._enter_signal_policy(self.deadline)
            self.m._leave_signal_policy(policy)
        self.assertFalse(policy.active)
        self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, ()), self.original_mask)


    def refuses_reserved_mask(self, reserved):
        actual = _signal.pthread_sigmask
        def observed(how, mask):
            if how == signal.SIG_BLOCK and mask == ():
                return {reserved}
            return actual(how, mask)
        with (patch.object(_signal, 'pthread_sigmask', observed),
              patch.object(signal, 'signal',
                           side_effect=AssertionError('Nonrestorable mask mutation')) as mutate):
            with self.assertRaises(fixtures.Refusal) as caught:
                self.m._enter_signal_policy(self.deadline)
        self.assertEqual(caught.exception.code, 'supervision_unavailable')
        self.assertEqual(mutate.call_count, 0)
        self.assertIsNone(self.m._ACTIVE_POLICY)

    def test_reserved32_original_main_mask_refuses_before_policy_mutation(self):
        self.refuses_reserved_mask(32)

    def test_reserved33_original_main_mask_refuses_before_policy_mutation(self):
        self.refuses_reserved_mask(33)


if __name__ == '__main__':
    unittest.main()
