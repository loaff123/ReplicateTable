"""Bounded reads of the adopted worker's kernel VmRSS observation only."""
import errno
import importlib
import os
import signal
import subprocess
import sys
import unittest
from unittest.mock import patch

from replicatetable.errors import Refusal
from replicatetable._native_budget_state import (
    _CancellationState, _start_deadline, LogicalOnlyBudget,
)


class ChildRSSObservationTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('replicatetable._native_supervisor')
        self.assertTrue(callable(getattr(self.m, '_read_child_rss', None)),
                        'Bounded adopted-child RSS observation is missing')
        self.cancel = _CancellationState()
        self.budget = _start_deadline(self.cancel)
        self.wrappers = []
        self.addCleanup(self.cleanup_children)

    def cleanup_children(self):
        for wrapper in self.wrappers:
            wrapper._child_created = False
            try:
                pid, _ = os.waitpid(wrapper.pid, os.WNOHANG)
                if not pid:
                    os.kill(wrapper.pid, signal.SIGKILL)
                    os.waitpid(wrapper.pid, 0)
            except ChildProcessError:
                pass

    def child(self, script='import time; time.sleep(30)'):
        wrapper = subprocess.Popen([sys.executable, '-B', '-c', script],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True,
            start_new_session=True, restore_signals=True)
        self.wrappers.append(wrapper)
        owner = self.m._ChildOwner()
        self.m._adopt_returned(owner, wrapper)
        return owner

    def refuse(self, code, function, *args):
        with self.assertRaises(Refusal) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def synthetic_read(self, owner, parts):
        source = iter(parts)
        calls = []
        def read(fd, count):
            calls.append((fd, count))
            self.assertLessEqual(count, 65536)
            return next(source, b'')
        with patch.object(os, 'read', read):
            value = self.m._read_child_rss(owner, self.budget)
        self.assertTrue(calls)
        return value

    def test_real_live_worker_sample_uses_only_its_exact_pid(self):
        owner = self.child()
        actual = os.open
        names = []
        def opening(name, flags, *args, **kwargs):
            names.append(name)
            return actual(name, flags, *args, **kwargs)
        with patch.object(os, 'open', opening):
            value = self.m._read_child_rss(owner, self.budget)
        self.assertIs(type(value), int)
        self.assertGreaterEqual(value, 0)
        self.assertEqual(names, ['/proc/' + str(owner.pid) + '/status'])

    def test_scalar_kernel_parse_preserves_kibibyte_conversion(self):
        owner = self.child()
        self.assertEqual(self.synthetic_read(owner,
            [b'Name:\tpython\nVmRSS:\t', b' 123', b'45 kB\nThreads:\t1\n']), 12345 * 1024)

    def test_long_unselected_line_does_not_require_a_line_buffer(self):
        owner = self.child()
        # A bounded kernel read chunk, not an admitted native/scientific input.
        parts = [b'Groups:\t'] + [b'1 ' * 32768] * 3 + [b'\nVmRSS:\t7 kB\n']
        self.assertEqual(self.synthetic_read(owner, parts), 7168)

    def test_missing_process_is_not_a_zero_rss_success(self):
        owner = self.child()
        with patch.object(os, 'open', side_effect=FileNotFoundError(errno.ENOENT, 'fixture')):
            self.assertIsNone(self.m._read_child_rss(owner, self.budget))
        self.assertEqual(owner.state, 'OWNED')

    def test_missing_rss_field_is_not_a_zero_sample(self):
        owner = self.child()
        self.assertIsNone(self.synthetic_read(owner, [b'Name:\tpython\nState:\tZ\n']))

    def test_invalid_kernel_value_and_units_refuse(self):
        owner = self.child()
        for text in (b'VmRSS:\t-1 kB\n', b'VmRSS:\t1 MB\n',
                     b'VmRSS:\t1.0 kB\n', b'VmRSS:\t kB\n',
                     b'VmRSS:\t18446744073709551616 kB\n'):
            with self.subTest(text=text):
                self.refuse('supervision_unavailable', self.synthetic_read, owner, [text])

    def test_observation_descriptor_retires_on_read_error(self):
        owner = self.child()
        original_open = os.open
        descriptors = []
        def opening(*args, **kwargs):
            fd = original_open(*args, **kwargs)
            descriptors.append(fd)
            return fd
        with (patch.object(os, 'open', opening),
              patch.object(os, 'read', side_effect=OSError(errno.EIO, 'private fixture'))):
            failure = self.refuse('io_error', self.m._read_child_rss, owner, self.budget)
        self.assertEqual(len(descriptors), 1)
        with self.assertRaises(OSError) as closed:
            os.fstat(descriptors[0])
        self.assertEqual(closed.exception.errno, errno.EBADF)
        self.assertIsNone(failure.__context__)

    def test_no_rss_read_after_reap_or_lost(self):
        for lost in (False, True):
            owner = self.child()
            if lost:
                with patch.object(os, 'waitpid', side_effect=ChildProcessError(errno.ECHILD, 'fixture')):
                    self.refuse('supervision_unavailable', self.m._probe_child, owner)
            else:
                self.m._stop_child(owner)
            with patch.object(os, 'open', side_effect=AssertionError('nonowned RSS read')):
                self.refuse('supervision_unavailable', self.m._read_child_rss, owner, self.budget)

    def test_logical_budget_never_opens_procfs(self):
        owner = self.child()
        with patch.object(os, 'open', side_effect=AssertionError('logical RSS read')):
            self.refuse('supervision_unavailable', self.m._read_child_rss,
                        owner, LogicalOnlyBudget(self.cancel))

    def test_rss_over_limit_preserves_memory_failure_after_exact_reap(self):
        owner = self.child()
        with patch.object(self.m, '_read_child_rss', return_value=1073741825):
            failure = self.refuse('worker_memory_limit', self.m._wait_child, owner, self.budget)
        self.assertEqual(failure.exit_code, 3)
        self.assertEqual(owner.state, 'REAPED')
        self.assertEqual(os.waitstatus_to_exitcode(owner.wait_status), -signal.SIGKILL)

    def test_rss_exact_limit_is_not_over_limit(self):
        owner = self.child('import time; time.sleep(0.04)')
        with patch.object(self.m, '_read_child_rss', return_value=1073741824) as observed:
            status = self.m._wait_child(owner, self.budget)
        self.assertGreater(observed.call_count, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)

    def test_missing_observation_reprobes_before_classification_or_signal(self):
        owner = self.child()
        actual = os.waitpid
        events = []
        def wait(pid, flags):
            value = actual(pid, flags)
            events.append(('wait', pid, value[0]))
            return value
        def missing(child, budget):
            self.assertIs(child, owner)
            self.assertIs(budget, self.budget)
            events.append(('missing', owner.pid))
            return None
        with patch.object(os, 'waitpid', wait), patch.object(self.m, '_read_child_rss', missing):
            self.refuse('supervision_unavailable', self.m._wait_child, owner, self.budget)
        self.assertEqual(events[:3], [('wait', owner.pid, 0), ('missing', owner.pid),
                                     ('wait', owner.pid, 0)])
        self.assertEqual(owner.state, 'REAPED')


if __name__ == '__main__':
    unittest.main()
