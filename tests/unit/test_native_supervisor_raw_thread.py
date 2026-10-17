"""A raw Python thread can be live without a threading registry entry."""
import _thread
import importlib
import threading
import time
import unittest
from unittest.mock import patch

from replicatetable.errors import Refusal
from replicatetable._native_budget_state import _CancellationState, _start_deadline


class RawPythonThreadPreflightTests(unittest.TestCase):
    def test_unregistered_raw_python_thread_refuses_before_policy_mutation(self):
        product = importlib.import_module('replicatetable._native_supervisor')
        baseline = _thread._count()
        self.assertEqual(baseline, 0)
        self.assertEqual(threading.active_count(), 1)
        started, finish, stopped = (_thread.allocate_lock() for _ in range(3))
        started.acquire(); finish.acquire(); stopped.acquire()
        def raw_worker():
            # Deliberately do not request current_thread/DummyThread.
            started.release()
            finish.acquire()
            stopped.release()
        _thread.start_new_thread(raw_worker, ())
        self.assertTrue(started.acquire(timeout=5))
        try:
            self.assertEqual(threading.active_count(), 1)
            self.assertGreater(_thread._count(), baseline)
            with patch.object(product.signal, 'signal', side_effect=AssertionError('Premature mutation')):
                with self.assertRaises(Refusal) as caught:
                    product._preflight_native(_start_deadline(_CancellationState()))
            self.assertEqual(caught.exception.code, 'supervision_unavailable')
        finally:
            finish.release()
            self.assertTrue(stopped.acquire(timeout=5))
            limit = time.monotonic() + 5
            while _thread._count() != baseline and time.monotonic() < limit:
                time.sleep(0.001)
            self.assertEqual(_thread._count(), baseline)


if __name__ == '__main__':
    unittest.main()
