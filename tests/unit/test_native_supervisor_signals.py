"""Real main-thread INT/TERM policy capture and complete Linux restoration.

No worker is launched by this slice. A genuine idle native-helper-thread
fixture and closed-constructor integration remain separate qualification.
"""
import ctypes
import importlib
import os
import signal
import subprocess
import threading
import unittest
from unittest.mock import patch

from replicatetable.errors import Refusal
from replicatetable._native_budget_state import (
    _CancellationState, _start_deadline, LogicalOnlyBudget,
)


def action(signum):
    """Independent kernel observation in the qualified 152-byte saved shape."""
    library = ctypes.CDLL('/lib/x86_64-linux-gnu/libc.so.6', use_errno=True)
    call = library.syscall
    call.argtypes = (ctypes.c_long, ctypes.c_int, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_size_t)
    call.restype = ctypes.c_long
    storage = (ctypes.c_ubyte * 32)()
    if call(13, signum, None, ctypes.byref(storage), 8) != 0:
        raise OSError(ctypes.get_errno(), 'fixture sigaction query failed')
    raw = bytes(storage)
    assert raw[12:16] == bytes(4)
    return raw[:8] + raw[24:32] + bytes(120) + raw[8:12] + bytes(4) + raw[16:24]


def set_action(signum, raw):
    library = ctypes.CDLL('/lib/x86_64-linux-gnu/libc.so.6', use_errno=True)
    call = library.syscall
    call.argtypes = (ctypes.c_long, ctypes.c_int, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_size_t)
    call.restype = ctypes.c_long
    kernel = raw[:8] + raw[136:140] + bytes(4) + raw[144:152] + raw[8:16]
    storage = (ctypes.c_ubyte * 32).from_buffer_copy(kernel)
    if call(13, signum, ctypes.byref(storage), None, 8) != 0:
        raise OSError(ctypes.get_errno(), 'fixture sigaction restore failed')


class NativeSignalPolicyTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('replicatetable._native_supervisor')
        for name in ('_preflight_native', '_SignalPolicy',
                     '_enter_signal_policy', '_leave_signal_policy'):
            self.assertTrue(callable(getattr(self.m, name, None)),
                            'Frozen managed signal interface is missing: ' + name)
        self.cancellation = _CancellationState()
        self.deadline = _start_deadline(self.cancellation)
        self.original_handlers = tuple(signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM))
        self.original_actions = tuple(action(sig) for sig in (signal.SIGINT, signal.SIGTERM))
        self.original_mask = signal.pthread_sigmask(signal.SIG_BLOCK, ())
        self.fixture_int_sent = False
        self.original_active = self.m._ACTIVE_POLICY
        self.original_poisoned = self.m._SIGNAL_POISONED
        self.addCleanup(self.restore_fixture_policy)

    def restore_fixture_policy(self):
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        if self.fixture_int_sent and signal.SIGINT in signal.sigpending():
            signal.sigwait({signal.SIGINT})
        for sig, handler, raw in zip((signal.SIGINT, signal.SIGTERM),
                                    self.original_handlers, self.original_actions):
            signal.signal(sig, handler)
            set_action(sig, raw)
            self.assertIs(signal.getsignal(sig), handler)
            self.assertEqual(action(sig), raw)
        signal.pthread_sigmask(signal.SIG_SETMASK, self.original_mask)
        self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, ()), self.original_mask)
        # Test teardown owns the real restoration above. Keep failed red cases
        # isolated; this never certifies product restoration or retirement.
        self.m._ACTIVE_POLICY = self.original_active
        self.m._SIGNAL_POISONED = self.original_poisoned

    def refuses(self, function, *args):
        with self.assertRaises(Refusal) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, 'supervision_unavailable')
        self.assertEqual(caught.exception.exit_code, 2)
        return caught.exception

    def test_managed_handlers_latch_first_real_signal_without_calling_previous(self):
        called = []
        def previous(signum, frame):
            called.append(signum)
        signal.signal(signal.SIGINT, previous)
        signal.signal(signal.SIGTERM, previous)
        policy = self.m._enter_signal_policy(self.deadline)
        try:
            self.assertIs(type(policy), self.m._SignalPolicy)
            self.assertTrue(policy.active)
            self.assertIs(policy.deadline, self.deadline)
            os.kill(os.getpid(), signal.SIGTERM)
            os.kill(os.getpid(), signal.SIGINT)
            self.assertEqual(self.cancellation.signum, 15)
            self.assertEqual(called, [])
        finally:
            self.m._leave_signal_policy(policy)
        self.assertFalse(policy.active)
        self.assertIs(signal.getsignal(signal.SIGINT), previous)
        self.assertIs(signal.getsignal(signal.SIGTERM), previous)

    def test_full_actions_restart_flags_and_main_mask_restore_exactly(self):
        def previous(signum, frame):
            pass
        signal.signal(signal.SIGINT, previous)
        signal.signal(signal.SIGTERM, previous)
        signal.siginterrupt(signal.SIGINT, False)
        signal.siginterrupt(signal.SIGTERM, True)
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGUSR1})
        before = tuple(action(sig) for sig in (signal.SIGINT, signal.SIGTERM))
        before_mask = signal.pthread_sigmask(signal.SIG_BLOCK, ())
        policy = self.m._enter_signal_policy(self.deadline)
        self.m._leave_signal_policy(policy)
        self.assertEqual(tuple(action(sig) for sig in (signal.SIGINT, signal.SIGTERM)), before)
        self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, ()), before_mask)
        self.m._leave_signal_policy(policy)
        self.assertEqual(tuple(action(sig) for sig in (signal.SIGINT, signal.SIGTERM)), before)

    def test_pending_entry_signal_is_observed_under_managed_policy(self):
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
        self.fixture_int_sent = True
        os.kill(os.getpid(), signal.SIGINT)
        self.assertIn(signal.SIGINT, signal.sigpending())
        policy = self.m._enter_signal_policy(self.deadline)
        try:
            self.assertEqual(self.cancellation.signum, 2)
        finally:
            self.m._leave_signal_policy(policy)
        self.assertIn(signal.SIGINT, signal.pthread_sigmask(signal.SIG_BLOCK, ()))

    def test_unknown_python_handler_refuses_before_signal_mutation(self):
        actual = signal.getsignal
        def unknown(sig):
            return None if sig == signal.SIGTERM else actual(sig)
        before = tuple(action(sig) for sig in (signal.SIGINT, signal.SIGTERM))
        with (patch.object(signal, 'getsignal', unknown),
              patch.object(signal, 'signal', side_effect=AssertionError('premature mutation'))):
            self.refuses(self.m._enter_signal_policy, self.deadline)
        self.assertEqual(tuple(action(sig) for sig in (signal.SIGINT, signal.SIGTERM)), before)

    def test_sigchld_nondefault_or_auto_reap_refuses_without_changing_it(self):
        original_handler, original_action = signal.getsignal(signal.SIGCHLD), action(signal.SIGCHLD)
        try:
            for handler in (signal.SIG_IGN, lambda signum, frame: None):
                signal.signal(signal.SIGCHLD, handler)
                before = action(signal.SIGCHLD)
                self.refuses(self.m._preflight_native, self.deadline)
                self.assertEqual(action(signal.SIGCHLD), before)
            signal.signal(signal.SIGCHLD, signal.SIG_DFL)
            raw = bytearray(action(signal.SIGCHLD))
            flags = int.from_bytes(raw[136:140], 'little') | 2  # SA_NOCLDWAIT
            raw[136:140] = flags.to_bytes(4, 'little')
            set_action(signal.SIGCHLD, raw)
            before = action(signal.SIGCHLD)
            self.refuses(self.m._preflight_native, self.deadline)
            self.assertEqual(action(signal.SIGCHLD), before)
        finally:
            signal.signal(signal.SIGCHLD, original_handler)
            set_action(signal.SIGCHLD, original_action)

    def test_other_live_python_thread_refuses_before_mutation(self):
        entered, finish = threading.Event(), threading.Event()
        def background():
            entered.set()
            finish.wait()
        thread = threading.Thread(target=background)
        thread.start()
        entered.wait()
        try:
            with patch.object(signal, 'signal', side_effect=AssertionError('threaded mutation')):
                self.refuses(self.m._enter_signal_policy, self.deadline)
        finally:
            finish.set()
            thread.join()

    def test_background_python_caller_refuses_before_mutation(self):
        errors = []
        def background():
            try:
                self.m._preflight_native(self.deadline)
            except Refusal as error:
                errors.append((error.code, error.exit_code))
        thread = threading.Thread(target=background)
        with patch.object(signal, 'signal', side_effect=AssertionError('background mutation')):
            thread.start()
            thread.join()
        self.assertEqual(errors, [('supervision_unavailable', 2)])

    def test_stock_cleanup_has_no_unrelated_active_wrapper_scope(self):
        self.assertEqual(subprocess._active, [])
        marker = object()
        subprocess._active.append(marker)
        try:
            with patch.object(subprocess, '_cleanup', side_effect=AssertionError('foreign cleanup')):
                self.refuses(self.m._preflight_native, self.deadline)
            self.assertIs(subprocess._active[0], marker)
        finally:
            self.assertIs(subprocess._active.pop(), marker)

    def test_native_policy_reentry_and_logical_budget_refuse(self):
        self.refuses(self.m._enter_signal_policy, LogicalOnlyBudget(self.cancellation))
        policy = self.m._enter_signal_policy(self.deadline)
        try:
            self.refuses(self.m._enter_signal_policy, self.deadline)
        finally:
            self.m._leave_signal_policy(policy)

    def test_partial_install_failure_restores_every_touched_action(self):
        class Marker(BaseException):
            pass
        marker = Marker('fixture interruption')
        actual = signal.signal
        before = tuple(action(sig) for sig in (signal.SIGINT, signal.SIGTERM))
        calls = 0
        def fail_after_second_install(sig, handler):
            nonlocal calls
            result = actual(sig, handler)
            calls += 1
            if calls == 2:
                raise marker
            return result
        with patch.object(signal, 'signal', fail_after_second_install):
            with self.assertRaises(Marker) as caught:
                self.m._enter_signal_policy(self.deadline)
        self.assertIs(caught.exception, marker)
        self.assertEqual(tuple(action(sig) for sig in (signal.SIGINT, signal.SIGTERM)), before)
        self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, ()), self.original_mask)

    def test_prior_handler_exception_at_handoff_restores_remaining_policy(self):
        class CallerPolicyError(Exception):
            pass
        marker = CallerPolicyError('caller policy')
        def old_int(signum, frame):
            raise marker
        def old_term(signum, frame):
            pass
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
        before = tuple(action(sig) for sig in (signal.SIGINT, signal.SIGTERM))
        policy = self.m._enter_signal_policy(self.deadline)
        actual = signal.signal
        sent = False
        def during_handoff(sig, handler):
            nonlocal sent
            result = actual(sig, handler)
            if sig == signal.SIGINT and handler is old_int and not sent:
                sent = True
                self.fixture_int_sent = True
                os.kill(os.getpid(), signal.SIGINT)
            return result
        with patch.object(signal, 'signal', during_handoff):
            with self.assertRaises(CallerPolicyError) as caught:
                self.m._leave_signal_policy(policy)
        self.assertIs(caught.exception, marker)
        self.assertFalse(policy.active)
        self.assertEqual(self.cancellation.signum, 0)
        self.assertEqual(tuple(action(sig) for sig in (signal.SIGINT, signal.SIGTERM)), before)
        self.assertIs(signal.getsignal(signal.SIGTERM), old_term)
        self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, ()), self.original_mask)


if __name__ == '__main__':
    unittest.main()
