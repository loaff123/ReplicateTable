"""Exact adopted-child ownership; fixtures launch only benign owned children.

These tests do not qualify a public native route or lend fixture-only child
identity to production cleanup after an unadopted constructor failure.
"""
import errno
import importlib
import os
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from replicatetable.errors import Refusal
from replicatetable._native_budget_state import (
    _CancellationState, _inherited_deadline, _start_deadline, LogicalOnlyBudget,
)


class AdoptedChildTests(unittest.TestCase):
    def setUp(self):
        try:
            self.m = importlib.import_module('replicatetable._native_supervisor')
        except ModuleNotFoundError as error:
            if error.name != 'replicatetable._native_supervisor':
                raise
            self.fail('Frozen adopted-child supervision interface is missing')
        for name in ('_ChildOwner', '_adopt_returned', '_probe_child',
                     '_stop_child', '_wait_child', '_release_child'):
            self.assertTrue(callable(getattr(self.m, name, None)),
                            'Frozen adopted-child interface is missing: ' + name)
        self.cancel = _CancellationState()
        self.budget = _start_deadline(self.cancel)
        self.children = []
        self.addCleanup(self.fixture_cleanup)

    def fixture_cleanup(self):
        # The fixture owns the exact PID returned by its own stock constructor.
        # It never supplies a guessed/foreign PID to a production operation.
        for wrapper in self.children:
            wrapper._child_created = False
            try:
                pid, _ = os.waitpid(wrapper.pid, os.WNOHANG)
                if pid == 0:
                    os.kill(wrapper.pid, signal.SIGKILL)
                    while True:
                        try:
                            os.waitpid(wrapper.pid, 0)
                            break
                        except InterruptedError:
                            continue
            except ChildProcessError:
                pass

    def child(self, code='import time; time.sleep(30)'):
        wrapper = subprocess.Popen(
            [sys.executable, '-B', '-c', code], close_fds=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
            restore_signals=True,
        )
        self.children.append(wrapper)
        owner = self.m._ChildOwner()
        self.m._adopt_returned(owner, wrapper)
        return owner, wrapper

    def refuses(self, code, function, *args):
        with self.assertRaises(Refusal) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_empty_owner_confers_no_child_or_wait_authority(self):
        owner = self.m._ChildOwner()
        self.assertEqual(owner.state, 'PRELAUNCH')
        self.assertIsNone(owner.pid)
        self.assertIsNone(owner.wait_status)
        with (patch.object(os, 'waitpid', side_effect=AssertionError('unowned wait')),
              patch.object(os, 'kill', side_effect=AssertionError('unowned signal'))):
            self.refuses('supervision_unavailable', self.m._probe_child, owner)
            self.m._stop_child(owner)
        with self.assertRaises((AttributeError, TypeError)):
            owner.pid = os.getpid()
        self.refuses('supervision_unavailable', owner.__init__)

    def test_exact_owner_and_wrapper_types_precede_hooks(self):
        class Hook:
            @property
            def pid(self):
                raise AssertionError('untrusted PID property')
            def __eq__(self, other):
                raise AssertionError('untrusted equality')
        owner = self.m._ChildOwner()
        self.refuses('supervision_unavailable', self.m._adopt_returned, owner, Hook())
        self.refuses('supervision_unavailable', self.m._probe_child, Hook())
        self.assertEqual(owner.state, 'PRELAUNCH')
        with self.assertRaises(TypeError):
            type('DerivedOwner', (self.m._ChildOwner,), {})

    def test_adoption_strongly_retains_and_disarms_stock_wrapper(self):
        owner, wrapper = self.child()
        self.assertEqual(owner.state, 'OWNED')
        self.assertEqual(owner.pid, wrapper.pid)
        self.assertIs(owner.wrapper, wrapper)
        self.assertIs(wrapper._child_created, False)
        self.assertIsNone(wrapper.returncode)
        self.assertFalse(self.m._probe_child(owner))
        self.assertIsNone(owner.wait_status)
        self.refuses('supervision_unavailable', self.m._release_child, owner)

    def test_idempotent_transfer_keeps_one_owner(self):
        owner, wrapper = self.child()
        for _ in range(3):
            self.m._adopt_returned(owner, wrapper)
        self.assertEqual(owner.pid, wrapper.pid)
        other, other_wrapper = self.child()
        self.refuses('supervision_unavailable', self.m._adopt_returned,
                     owner, other_wrapper)
        self.assertIs(owner.wrapper, wrapper)
        self.assertIs(other.wrapper, other_wrapper)

    def test_real_zero_terminal_status_is_exact_pid_authority(self):
        owner, wrapper = self.child('raise SystemExit(0)')
        result = self.m._wait_child(owner, self.budget)
        self.assertEqual(owner.state, 'REAPED')
        self.assertEqual(result, owner.wait_status)
        self.assertTrue(os.WIFEXITED(result))
        self.assertEqual(os.WEXITSTATUS(result), 0)
        # Popen returncode is deliberately never wait authority.
        self.assertIsNone(wrapper.returncode)
        with self.assertRaises(ChildProcessError):
            os.waitpid(owner.pid, os.WNOHANG)
        self.m._release_child(owner)
        self.assertIsNone(owner.wrapper)
        self.m._release_child(owner)

    def test_real_nonzero_and_signal_status_are_not_fabricated_success(self):
        for script, exitcode in (
            ('raise SystemExit(7)', 7),
            ('import os, signal; os.kill(os.getpid(), signal.SIGTERM)', -15),
        ):
            owner, _ = self.child(script)
            status = self.m._wait_child(owner, self.budget)
            self.assertEqual(os.waitstatus_to_exitcode(status), exitcode)
            self.m._release_child(owner)

    def test_every_probe_uses_only_the_adopted_pid_and_wnohang(self):
        owner, _ = self.child()
        actual = os.waitpid
        calls = []
        def observe(pid, flags):
            calls.append((pid, flags))
            return actual(pid, flags)
        with patch.object(os, 'waitpid', observe):
            self.assertFalse(self.m._probe_child(owner))
        self.assertEqual(calls, [(owner.pid, os.WNOHANG)])

    def test_eintr_does_not_reset_or_lose_child_ownership(self):
        owner, _ = self.child()
        actual = os.waitpid
        calls = []
        def interrupt_once(pid, flags):
            calls.append((pid, flags))
            if len(calls) == 1:
                raise InterruptedError(errno.EINTR, 'fixture interruption')
            return actual(pid, flags)
        with patch.object(os, 'waitpid', interrupt_once):
            self.assertFalse(self.m._probe_child(owner))
        self.assertEqual(calls, [(owner.pid, os.WNOHANG)] * 2)
        self.assertEqual(owner.state, 'OWNED')

    def test_echild_permanently_loses_signaling_and_success_authority(self):
        owner, _ = self.child()
        with patch.object(os, 'waitpid', side_effect=ChildProcessError(errno.ECHILD, 'fixture')):
            failure = self.refuses('supervision_unavailable', self.m._probe_child, owner)
        self.assertEqual(failure.exit_code, 2)
        self.assertEqual(owner.state, 'LOST')
        self.assertIsNone(owner.wait_status)
        with (patch.object(os, 'waitpid', side_effect=AssertionError('lost wait')),
              patch.object(os, 'kill', side_effect=AssertionError('lost signal'))):
            self.m._stop_child(owner)
            self.refuses('supervision_unavailable', self.m._probe_child, owner)
            self.m._release_child(owner)
        self.assertIsNone(owner.wrapper)

    def test_oserror_echild_matches_childprocesserror(self):
        owner, _ = self.child()
        with patch.object(os, 'waitpid', side_effect=OSError(errno.ECHILD, 'fixture')):
            self.refuses('supervision_unavailable', self.m._probe_child, owner)
        self.assertEqual(owner.state, 'LOST')

    def test_a_terminal_child_is_reaped_before_kill_can_be_considered(self):
        owner, _ = self.child('raise SystemExit(0)')
        # WNOWAIT observes fixture readiness without stealing product wait.
        observed = os.waitid(os.P_PID, owner.pid, os.WEXITED | os.WNOWAIT)
        self.assertEqual(observed.si_pid, owner.pid)
        with patch.object(os, 'kill', side_effect=AssertionError('signal after exit')):
            self.m._stop_child(owner)
        self.assertEqual(owner.state, 'REAPED')
        self.assertEqual(os.waitstatus_to_exitcode(owner.wait_status), 0)

    def test_stop_signals_only_after_result_zero_then_reaps_exact_child(self):
        owner, _ = self.child()
        waitpid, kill = os.waitpid, os.kill
        events = []
        def wait(pid, flags):
            result = waitpid(pid, flags)
            events.append(('wait', pid, flags, result[0]))
            return result
        def signal_child(pid, signum):
            events.append(('kill', pid, signum))
            return kill(pid, signum)
        with patch.object(os, 'waitpid', wait), patch.object(os, 'kill', signal_child):
            self.m._stop_child(owner)
        self.assertEqual(events[0], ('wait', owner.pid, os.WNOHANG, 0))
        self.assertEqual(events[1], ('kill', owner.pid, signal.SIGKILL))
        self.assertTrue(all(event[1] == owner.pid for event in events))
        self.assertEqual(owner.state, 'REAPED')
        self.assertEqual(os.waitstatus_to_exitcode(owner.wait_status), -signal.SIGKILL)
        with (patch.object(os, 'kill', side_effect=AssertionError('reaped signal')),
              patch.object(os, 'waitpid', side_effect=AssertionError('reaped wait'))):
            self.m._stop_child(owner)

    def test_expired_deadline_still_kills_and_reaps_owned_child(self):
        owner, _ = self.child()
        expired = _inherited_deadline(0, self.cancel)
        failure = self.refuses('operation_timeout', self.m._wait_child, owner, expired)
        self.assertEqual(failure.exit_code, 3)
        self.assertEqual(expired.deadline_ns, 0)
        self.assertEqual(owner.state, 'REAPED')
        self.assertEqual(os.waitstatus_to_exitcode(owner.wait_status), -signal.SIGKILL)

    def test_first_cancellation_precedes_timeout_and_survives_reap(self):
        for first, second in ((2, 15), (15, 2)):
            owner, _ = self.child()
            cancellation = _CancellationState()
            cancellation._latch(first)
            cancellation._latch(second)
            expired = _inherited_deadline(0, cancellation)
            failure = self.refuses('interrupted', self.m._wait_child, owner, expired)
            self.assertEqual(failure.exit_code, 128 + first)
            self.assertEqual(cancellation.signum, first)
            self.assertEqual(owner.state, 'REAPED')

    def test_logical_budget_is_not_native_wait_authority(self):
        owner, _ = self.child()
        with patch.object(os, 'waitpid', side_effect=AssertionError('wrong-budget wait')):
            self.refuses('supervision_unavailable', self.m._wait_child,
                         owner, LogicalOnlyBudget(self.cancel))
        self.assertEqual(owner.state, 'OWNED')

    def test_stock_convenience_methods_never_observe_adopted_child(self):
        owner, _ = self.child('raise SystemExit(0)')
        from contextlib import ExitStack
        names = ('poll', 'wait', 'communicate', 'send_signal', 'terminate', 'kill',
                 '__enter__', '__exit__', '_internal_poll', '_try_wait')
        with ExitStack() as stack:
            for name in names:
                stack.enter_context(patch.object(subprocess.Popen, name,
                    side_effect=AssertionError('forbidden stock lifecycle: ' + name)))
            self.m._wait_child(owner, self.budget)
            self.m._release_child(owner)

    def test_wait_failure_cleans_owned_child_without_retaining_raw_context(self):
        owner, _ = self.child()
        actual = os.waitpid
        seen = 0
        def first_fault(pid, flags):
            nonlocal seen
            seen += 1
            if seen == 1:
                raise OSError(errno.EIO, 'private fixture text')
            return actual(pid, flags)
        with patch.object(os, 'waitpid', first_fault):
            failure = self.refuses('io_error', self.m._wait_child, owner, self.budget)
        self.assertEqual(owner.state, 'REAPED')
        self.assertNotIn('private fixture text', failure.message)
        self.assertIsNone(failure.__context__)
        self.assertIsNone(failure.__cause__)
        frame = failure.__traceback__
        while frame is not None:
            if frame.tb_frame.f_code.co_filename == self.m.__file__:
                self.assertNotIn('wrapper', frame.tb_frame.f_locals)
            frame = frame.tb_next

    def test_reap_release_never_changes_an_unrelated_live_child(self):
        owner, _ = self.child('raise SystemExit(0)')
        unrelated, wrapper = self.child()
        self.m._wait_child(owner, self.budget)
        self.m._release_child(owner)
        self.assertFalse(self.m._probe_child(unrelated))
        self.assertEqual(unrelated.pid, wrapper.pid)


if __name__ == '__main__':
    unittest.main()
