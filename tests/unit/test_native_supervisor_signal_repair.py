"""Regression controls for meaningful native state and caller-policy handoff."""
import ctypes
import signal
import unittest
from unittest.mock import patch

from replicatetable.errors import Refusal
from tests.unit import test_native_supervisor_signals as fixtures

action, set_action = fixtures.action, fixtures.set_action


class NativeSignalRepairTests(unittest.TestCase):
    def setUp(self):
        fixtures.NativeSignalPolicyTests.setUp(self)
        if self._testMethodName in (
                'test_single_failure_before_python_table_change_restores_and_preserves_marker',
                'test_callback_replacement_preserves_its_python_mapping_and_kernel_action'):
            # Isolate Python handoff from the separately demonstrated libc-byte
            # defect. These independent helpers still query/restore real kernel
            # state; they neither simulate table mutation nor invoke callbacks.
            for name, function in (('_query_action', action), ('_restore_action', set_action)):
                replacement = patch.object(self.m, name, function)
                replacement.start()
                self.addCleanup(replacement.stop)
    restore_fixture_policy = fixtures.NativeSignalPolicyTests.restore_fixture_policy
    refuses = fixtures.NativeSignalPolicyTests.refuses

    def test_pristine_default_term_preserves_zero_flags_and_restorer(self):
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        set_action(signal.SIGTERM, bytes(152))
        self.assertEqual(action(signal.SIGTERM), bytes(152))
        policy = self.m._enter_signal_policy(self.deadline)
        self.m._leave_signal_policy(policy)
        self.assertEqual(action(signal.SIGTERM), bytes(152))
        self.assertFalse(policy.active)

    def test_nonempty_low64_action_mask_and_restart_flags_restore(self):
        def previous(signum, frame):
            pass
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, previous)
            signal.siginterrupt(sig, False)
            raw = bytearray(action(sig))
            # Actual supported USR1 and RT64 membership, including highest bit.
            mask = ((1 << (signal.SIGUSR1 - 1)) | (1 << (signal.SIGRTMAX - 1)) |
                    (1 << 31) | (1 << 32))
            raw[8:16] = mask.to_bytes(8, 'little')
            set_action(sig, raw)
        before = tuple(action(sig) for sig in (signal.SIGINT, signal.SIGTERM))
        policy = self.m._enter_signal_policy(self.deadline)
        self.m._leave_signal_policy(policy)
        self.assertEqual(tuple(action(sig) for sig in (signal.SIGINT, signal.SIGTERM)), before)

    def test_library_acquisition_failure_is_sanitized_before_mutation(self):
        with (patch.object(self.m, '_SIGNAL_API', None),
              patch.object(ctypes, 'CDLL', side_effect=OSError('fixture unavailable')),
              patch.object(signal, 'signal', side_effect=AssertionError('premature mutation'))):
            error = self.refuses(self.m._preflight_native, self.deadline)
        self.assertIsNone(error.__context__)
        self.assertIsNone(error.__cause__)

    def test_upper_kernel_flag_bits_refuse_before_saved_width_conversion(self):
        def query(*args):
            pointer = args[3] if len(args) == 5 else args[2]
            raw = bytes(8) + (1 << 40).to_bytes(8, 'little') + bytes(16)
            ctypes.memmove(pointer, raw, 32)
            return 0
        with (patch.object(self.m, '_signal_api',
                           return_value=(None, query, ctypes.c_ubyte * 32)),
              patch.object(signal, 'signal', side_effect=AssertionError('premature mutation'))):
            self.refuses(self.m._query_action, signal.SIGTERM)

    def test_missing_native_symbol_is_sanitized_before_mutation(self):
        with (patch.object(self.m, '_SIGNAL_API', None),
              patch.object(ctypes, 'CDLL', return_value=object()),
              patch.object(signal, 'signal', side_effect=AssertionError('premature mutation'))):
            error = self.refuses(self.m._preflight_native, self.deadline)
        self.assertIsNone(error.__context__)
        self.assertIsNone(error.__cause__)

    def test_single_failure_before_python_table_change_restores_and_preserves_marker(self):
        class Marker(BaseException):
            pass
        marker = Marker('one caller handoff interruption')
        def old_term(signum, frame):
            pass
        signal.signal(signal.SIGTERM, old_term)
        before = action(signal.SIGTERM)
        policy = self.m._enter_signal_policy(self.deadline)
        actual = signal.signal
        attempts = 0
        def one_pre_table_failure(sig, handler):
            nonlocal attempts
            if sig == signal.SIGTERM and handler is old_term:
                attempts += 1
                if attempts == 1:
                    raise marker
            return actual(sig, handler)
        with patch.object(signal, 'signal', one_pre_table_failure):
            with self.assertRaises(Marker) as caught:
                self.m._leave_signal_policy(policy)
        self.assertIs(caught.exception, marker)
        self.assertEqual(attempts, 2)
        self.assertIs(signal.getsignal(signal.SIGTERM), old_term)
        self.assertEqual(action(signal.SIGTERM), before)
        self.assertFalse(policy.active)
        self.assertIsNone(self.m._ACTIVE_POLICY)

    def test_callback_replacement_preserves_its_python_mapping_and_kernel_action(self):
        class Marker(BaseException):
            pass
        marker = Marker('caller replaced TERM policy')
        def old_term(signum, frame):
            pass
        def replacement(signum, frame):
            pass
        signal.signal(signal.SIGTERM, old_term)
        signal.siginterrupt(signal.SIGTERM, True)
        policy = self.m._enter_signal_policy(self.deadline)
        actual = signal.signal
        replacement_action = None
        attempts = 0
        def replace_during_handoff(sig, handler):
            nonlocal replacement_action, attempts
            if sig == signal.SIGTERM and handler is old_term:
                attempts += 1
                actual(sig, replacement)
                signal.siginterrupt(sig, False)
                replacement_action = action(sig)
                raise marker
            return actual(sig, handler)
        with patch.object(signal, 'signal', replace_during_handoff):
            with self.assertRaises(Marker) as caught:
                self.m._leave_signal_policy(policy)
        self.assertIs(caught.exception, marker)
        self.assertEqual(attempts, 1)
        self.assertIs(signal.getsignal(signal.SIGTERM), replacement)
        self.assertEqual(action(signal.SIGTERM), replacement_action)
        self.assertFalse(policy.active)


if __name__ == '__main__':
    unittest.main()
