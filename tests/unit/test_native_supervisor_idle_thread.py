"""One real idle pthread, with no Python callback or custom product launcher."""
import ctypes
import importlib
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from replicatetable._native_budget_state import _CancellationState, _start_deadline


_FIXTURE_SOURCE = r'''
#include <pthread.h>
#include <errno.h>
static pthread_t thread;
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition = PTHREAD_COND_INITIALIZER;
static int entered = 0, stop_requested = 0;
static void *idle(void *unused) {
    (void)unused;
    pthread_mutex_lock(&mutex);
    entered = 1;
    pthread_cond_broadcast(&condition);
    while (!stop_requested) pthread_cond_wait(&condition, &mutex);
    pthread_mutex_unlock(&mutex);
    return 0;
}
int fixture_start(void) {
    int error;
    pthread_mutex_lock(&mutex);
    if (entered) { pthread_mutex_unlock(&mutex); return EBUSY; }
    error = pthread_create(&thread, 0, idle, 0);
    if (!error) while (!entered) pthread_cond_wait(&condition, &mutex);
    pthread_mutex_unlock(&mutex);
    return error;
}
int fixture_stop(void) {
    pthread_mutex_lock(&mutex);
    stop_requested = 1;
    pthread_cond_broadcast(&condition);
    pthread_mutex_unlock(&mutex);
    return pthread_join(thread, 0);
}
'''


class IdleNativeThreadTests(unittest.TestCase):
    def test_actual_idle_native_thread_does_not_refuse_native_preflight(self):
        module = importlib.import_module('replicatetable._native_supervisor')
        self.assertTrue(callable(getattr(module, '_preflight_native', None)),
                        'Native process preflight is missing')
        self.assertEqual(threading.active_count(), 1)
        before = set(os.listdir('/proc/self/task'))
        # This is an authored qualification fixture compiled by the existing
        # system compiler, not product code, installation or a launch fallback.
        with tempfile.TemporaryDirectory(prefix='replicatetable-idle-thread-') as directory:
            root = Path(directory)
            source, library = root / 'idle.c', root / 'idle.so'
            source.write_text(_FIXTURE_SOURCE, encoding='ascii')
            subprocess.run(['/usr/bin/cc', '-shared', '-fPIC', '-pthread', '-O2',
                            str(source), '-o', str(library)],
                           check=True, capture_output=True, timeout=30)
            native = ctypes.CDLL(str(library))
            native.fixture_start.argtypes = ()
            native.fixture_start.restype = ctypes.c_int
            native.fixture_stop.argtypes = ()
            native.fixture_stop.restype = ctypes.c_int
            self.assertEqual(native.fixture_start(), 0)
            try:
                self.assertEqual(threading.active_count(), 1)
                self.assertGreater(len(set(os.listdir('/proc/self/task')) - before), 0)
                module._preflight_native(_start_deadline(_CancellationState()))
            finally:
                self.assertEqual(native.fixture_stop(), 0)
        self.assertEqual(threading.active_count(), 1)


if __name__ == '__main__':
    unittest.main()
