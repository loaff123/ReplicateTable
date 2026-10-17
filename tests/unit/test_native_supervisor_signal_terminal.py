"""Explicit bounded terminal restoration failure; fixture alone repairs it."""
import _signal
import signal
import unittest
from unittest.mock import patch

from tests.unit import test_native_supervisor_signals as fixtures


NOTE = 'Signal restoration is incomplete; restart this process before native work.'


class TerminalSignalRestorationTests(unittest.TestCase):
    def setUp(self):
        fixtures.NativeSignalPolicyTests.setUp(self)
        # The native byte-query defect is independently red. Isolate terminal
        # ownership from it using real, independently qualified kernel helpers.
        for name, function in (('_query_action', fixtures.action),
                               ('_restore_action', fixtures.set_action)):
            replacement = patch.object(self.m, name, function)
            replacement.start()
            self.addCleanup(replacement.stop)
    restore_fixture_policy = fixtures.NativeSignalPolicyTests.restore_fixture_policy
    refuses = fixtures.NativeSignalPolicyTests.refuses

    def assert_terminal(self, policy, error):
        self.assertTrue(self.m._SIGNAL_POISONED)
        self.assertIs(self.m._ACTIVE_POLICY, policy)
        self.assertTrue(policy.active)
        self.assertFalse(policy._retired)
        self.assertEqual(policy.restoration_message, NOTE)
        self.assertIsNone(error.__context__)
        self.assertIsNone(error.__cause__)
        self.assertTrue({signal.SIGINT, signal.SIGTERM}.issubset(
            signal.pthread_sigmask(signal.SIG_BLOCK, ())))
        refusal = self.refuses(self.m._preflight_native, self.deadline)
        self.assertEqual(refusal.message, NOTE)

    def test_second_mapping_failure_keeps_strong_owner_and_original_exception(self):
        class Marker(BaseException):
            def __getattribute__(self, name):
                if name == '__notes__':
                    raise AssertionError('Caller notes lookup is not authorized')
                return super().__getattribute__(name)
            def __setattr__(self, name, value):
                if name == '__notes__':
                    raise AssertionError('Caller notes assignment is not authorized')
                super().__setattr__(name, value)
        marker = Marker('first caller exception')
        notes = ['original caller note'] * 64
        object.__setattr__(marker, '__notes__', notes)
        def old_term(signum, frame):
            pass
        signal.signal(signal.SIGTERM, old_term)
        policy = self.m._enter_signal_policy(self.deadline)
        actual = signal.signal
        attempts = 0
        def fail_both(sig, handler):
            nonlocal attempts
            if sig == signal.SIGTERM and handler is old_term:
                attempts += 1
                if attempts == 1:
                    raise marker
                raise OSError('second restoration failure')
            return actual(sig, handler)
        with patch.object(signal, 'signal', fail_both):
            with self.assertRaises(Marker) as caught:
                self.m._leave_signal_policy(policy)
        self.assertIs(caught.exception, marker)
        self.assertEqual(attempts, 2)
        self.assertIs(signal.getsignal(signal.SIGTERM), self.m._managed_signal)
        self.assertTrue(policy._touched & 2)
        self.assert_terminal(policy, marker)
        self.assertIs(object.__getattribute__(marker, '__notes__'), notes)
        self.assertEqual(notes, ['original caller note'] * 64)

    def test_kernel_restore_failure_keeps_touched_state_after_mapping_handoff(self):
        class Marker(BaseException):
            pass
        marker = Marker('original callback exception')
        def old_term(signum, frame):
            pass
        signal.signal(signal.SIGTERM, old_term)
        policy = self.m._enter_signal_policy(self.deadline)
        actual_signal, actual_restore = signal.signal, self.m._restore_action
        failed_once = False
        def fail_first(sig, handler):
            nonlocal failed_once
            if sig == signal.SIGTERM and handler is old_term and not failed_once:
                failed_once = True
                raise marker
            return actual_signal(sig, handler)
        def fail_kernel(sig, raw):
            if sig == signal.SIGTERM:
                raise OSError('kernel action restore unavailable')
            return actual_restore(sig, raw)
        with (patch.object(signal, 'signal', fail_first),
              patch.object(self.m, '_restore_action', fail_kernel)):
            with self.assertRaises(Marker) as caught:
                self.m._leave_signal_policy(policy)
        self.assertIs(caught.exception, marker)
        self.assertIs(signal.getsignal(signal.SIGTERM), old_term)
        self.assertTrue(policy._touched & 2)
        self.assert_terminal(policy, marker)

    def test_main_mask_restore_failure_retains_unretired_policy(self):
        marker = OSError('main mask restore unavailable')
        policy = self.m._enter_signal_policy(self.deadline)
        actual = _signal.pthread_sigmask
        def fail_mask(how, mask):
            if how == signal.SIG_SETMASK and mask is policy._mask:
                raise marker
            return actual(how, mask)
        with patch.object(_signal, 'pthread_sigmask', fail_mask):
            with self.assertRaises(OSError) as caught:
                self.m._leave_signal_policy(policy)
        self.assertIs(caught.exception, marker)
        self.assertEqual(policy._touched, 0)
        self.assert_terminal(policy, marker)


if __name__ == '__main__':
    unittest.main()
