"""Intended REDs for two pure failed-start scalar helpers, never a supervisor.

Regressions targeted: wrong constructor exit/status, coercion or user callbacks,
altered termination-uncertainty text, unsafe residue names, unbounded name work,
and loss of the unchanged seven-field diagnostic byte bound. JSON fixtures below
are independent schema arithmetic, not evidence that an emitter exists or ran.
"""
from contextlib import ExitStack
import builtins
import importlib
import itertools
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from replicatetable.errors import Refusal


FAILURE = ('Native worker startup failed; '
           'worker termination could not be confirmed.')
INTERRUPTED = ('Operation interrupted during worker startup; '
               'worker termination could not be confirmed.')
STAGE_PREFIX = '.replicatetable-stage-'
STAGE = STAGE_PREFIX + '0123456789abcdef' * 2
HINT = ('Operation did not complete; an unverified temporary stage may remain: '
        + STAGE + ' (in the requested destination parent).')
CHECK_NAMES = ('structure', 'source_binding', 'runtime_binding', 'replay', 'report')
CHECK_VALUES = ('not_attempted', 'passed', 'failed')
ERROR_KEYS = ('version', 'status', 'code', 'message', 'checks', 'committed', 'receipt')


def forbidden_hook(*args, **kwargs):
    raise AssertionError('Untrusted scalar callback was invoked')


class HookValue:
    __bool__ = __bytes__ = __eq__ = __fspath__ = __hash__ = forbidden_hook
    __index__ = __int__ = __iter__ = __len__ = __repr__ = forbidden_hook
    __getitem__ = __str__ = forbidden_hook


class IntSubclass(int):
    __bool__ = __eq__ = __hash__ = __index__ = __int__ = forbidden_hook
    __repr__ = __str__ = forbidden_hook


class StringSubclass(str):
    __bool__ = __eq__ = __fspath__ = __hash__ = __iter__ = forbidden_hook
    __getitem__ = __len__ = __repr__ = __str__ = encode = forbidden_hook


def json_bytes(value):
    """Test-only independent compact JSON; no product emitter is assumed."""
    return json.dumps(value, ensure_ascii=True, allow_nan=False,
                      separators=(',', ':'), sort_keys=True).encode('ascii')


class NativeStartupTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('replicatetable._native_startup')
        for name in ('_startup_classification', '_startup_message'):
            self.assertTrue(callable(getattr(self.m, name, None)),
                            'Approved private startup scalar helper is missing: ' + name)

    def refuse(self, code, function, *args):
        with self.assertRaises(Refusal) as caught:
            function(*args)
        error = caught.exception
        self.assertIs(type(error.code), str)
        self.assertEqual(error.code, code)
        self.assertIs(type(error.message), str)
        self.assertTrue(error.message.isascii())
        self.assertTrue(all(32 <= ord(c) <= 126 for c in error.message))
        self.assertLessEqual(len(error.message), 512)
        return error

    def envelope(self, signum, name, checks):
        code, status, exit_code = self.m._startup_classification(signum)
        # Finding's exit_code remains outside the existing ErrorEnvelope shape.
        finding = {'code': code, 'message': self.m._startup_message(signum, name),
                   'exit_code': exit_code}
        return {'version': 2, 'status': status, 'code': finding['code'],
                'message': finding['message'], 'checks': checks,
                'committed': False, 'receipt': None}

    def test_exact_startup_classifications(self):
        cases = ((0, ('supervision_unavailable', 'failed', 3)),
                 (2, ('interrupted', 'cancelled', 130)),
                 (15, ('interrupted', 'cancelled', 143)))
        for signum, expected in cases:
            with self.subTest(signum=signum):
                actual = self.m._startup_classification(signum)
                self.assertIs(type(actual), tuple)
                self.assertEqual(len(actual), 3)
                self.assertIs(type(actual[0]), str)
                self.assertIs(type(actual[1]), str)
                self.assertIs(type(actual[2]), int)
                self.assertEqual(actual, expected)

    def test_classification_tuple_is_readonly(self):
        for signum in (0, 2, 15):
            actual = self.m._startup_classification(signum)
            before = tuple(actual)
            with self.assertRaises(TypeError):
                actual[0] = 'worker_failed'
            with self.assertRaises(AttributeError):
                actual.exit_code = 0
            self.assertEqual(actual, before)

    def test_invalid_signal_types_refuse_before_callbacks(self):
        values = (None, False, True, 0.0, 2.0, 15.0, '2', b'2', [], {},
                  HookValue(), IntSubclass(0), IntSubclass(2), IntSubclass(15),
                  signal.SIGINT, signal.SIGTERM)
        for index, value in enumerate(values):
            with self.subTest(case=index):
                self.refuse('supervision_unavailable',
                            self.m._startup_classification, value)
                self.refuse('supervision_unavailable',
                            self.m._startup_message, value, STAGE)

    def test_invalid_exact_signal_integers_refuse(self):
        for value in (-1, 1, 3, 9, 14, 16, 130, 143, 1 << 200, -(1 << 200)):
            with self.subTest(signum=value):
                self.refuse('supervision_unavailable',
                            self.m._startup_classification, value)
                self.refuse('supervision_unavailable',
                            self.m._startup_message, value, None)

    def test_signal_validation_precedes_basename_validation(self):
        for index, signum in enumerate((True, IntSubclass(2), HookValue(), 1, -1)):
            for name_index, name in enumerate((HookValue(), StringSubclass(STAGE),
                                                'not-a-generated-stage')):
                with self.subTest(signal=index, basename=name_index):
                    self.refuse('supervision_unavailable',
                                self.m._startup_message, signum, name)

    def test_absent_stage_has_exact_ascii_message(self):
        for signum, expected in ((0, FAILURE), (2, INTERRUPTED), (15, INTERRUPTED)):
            with self.subTest(signum=signum):
                actual = self.m._startup_message(signum, None)
                self.assertIs(type(actual), str)
                self.assertEqual(actual, expected)
                self.assertTrue(actual.isascii())
                self.assertNotIn('temporary stage', actual)

    def test_stage_hint_is_unchanged_and_separated_by_one_space(self):
        for signum, base in ((0, FAILURE), (2, INTERRUPTED), (15, INTERRUPTED)):
            with self.subTest(signum=signum):
                actual = self.m._startup_message(signum, STAGE)
                self.assertIs(type(actual), str)
                self.assertEqual(actual, base + ' ' + HINT)
                self.assertEqual(actual[len(base):len(base) + 2], ' O')
                self.assertTrue(actual.isascii())

    def test_lowercase_hex_endpoints_and_all_digits_are_accepted(self):
        for suffix in ('0' * 32, 'f' * 32, '0123456789abcdef' * 2):
            name = STAGE_PREFIX + suffix
            self.assertEqual(len(name), 54)
            expected_hint = ('Operation did not complete; an unverified temporary '
                             'stage may remain: ' + name
                             + ' (in the requested destination parent).')
            for signum, base in ((0, FAILURE), (2, INTERRUPTED), (15, INTERRUPTED)):
                with self.subTest(signum=signum, suffix=suffix):
                    self.assertEqual(self.m._startup_message(signum, name),
                                     base + ' ' + expected_hint)

    def test_basename_type_guard_never_coerces_or_uses_path_hooks(self):
        values = (False, True, 0, b'', STAGE.encode('ascii'), [], {},
                  HookValue(), StringSubclass(STAGE), pathlib.PurePosixPath(STAGE),
                  pathlib.PosixPath(STAGE))
        for signum in (0, 2, 15):
            for index, value in enumerate(values):
                with self.subTest(signum=signum, case=index):
                    with patch.object(os, 'fspath', side_effect=forbidden_hook):
                        self.refuse('unsafe_path', self.m._startup_message, signum, value)

    def test_wrong_prefix_separator_and_lengths_refuse(self):
        names = ('', STAGE_PREFIX, STAGE[:-1], STAGE + '0', STAGE[1:],
                 'x' + STAGE[1:], '.replicatetable-STAGE-' + '0' * 32,
                 '.replicatetable-work-' + '0' * 33,
                 './' + STAGE, '/' + STAGE, '../' + STAGE,
                 STAGE_PREFIX + '0' * 15 + '/' + '0' * 16,
                 STAGE_PREFIX + '0' * 15 + '\\' + '0' * 16)
        for index, name in enumerate(names):
            with self.subTest(case=index):
                self.refuse('unsafe_path', self.m._startup_message, 0, name)

    def test_uppercase_nonhex_nonascii_and_controls_refuse(self):
        bad_chars = tuple('ABCDEFgGxX-_. ') + ('é', '🦀', '\ud800', '\udfff')
        bad_chars += tuple(chr(value) for value in range(32))
        bad_chars += tuple(chr(value) for value in range(127, 160))
        for index, char in enumerate(bad_chars):
            for position in (0, 15, 31):
                name = STAGE_PREFIX + '0' * position + char + '0' * (31 - position)
                self.assertEqual(len(name), 54)
                with self.subTest(character=index, position=position):
                    self.refuse('unsafe_path', self.m._startup_message, 2, name)

    def test_oversized_basename_refuses_before_scanning_long_text(self):
        # Test-only tracing bounds Python iteration. Profiling separately catches
        # native str methods on the long argument, including prefix and encoding
        # scans. This is a narrow guard observation, not whole-route admission.
        values = (STAGE_PREFIX + '0' * 65536,
                  STAGE_PREFIX + '0' * 65535 + '\ud800')
        for value in values:
            event_count = 0
            startup_file = self.m.__file__

            def trace(frame, event, arg):
                nonlocal event_count
                if frame.f_code.co_filename == startup_file:
                    event_count += 1
                    if event_count > 128:
                        raise AssertionError('Oversized basename entered an unbounded scan')
                return trace

            def profile(frame, event, arg):
                if (event == 'c_call' and getattr(arg, '__self__', None) is value
                        and getattr(arg, '__name__', '') != '__len__'):
                    raise AssertionError('Oversized basename reached a string operation')

            previous_trace, previous_profile = sys.gettrace(), sys.getprofile()
            try:
                sys.settrace(trace)
                sys.setprofile(profile)
                self.refuse('unsafe_path', self.m._startup_message, 15, value)
            finally:
                sys.setprofile(previous_profile)
                sys.settrace(previous_trace)
            self.assertGreater(event_count, 0)

    def test_four_forms_have_exact_ascii_byte_lengths(self):
        self.assertEqual((len(FAILURE), len(INTERRUPTED), len(HINT)), (72, 87, 163))
        cases = ((0, None, 72), (2, None, 87), (15, None, 87),
                 (0, STAGE, 236), (2, STAGE, 251), (15, STAGE, 251))
        for signum, name, length in cases:
            actual = self.m._startup_message(signum, name)
            self.assertEqual(len(actual.encode('ascii')), length)
            self.assertLessEqual(length, 512)
            self.assertEqual(json_bytes(actual), b'"' + actual.encode('ascii') + b'"')
            self.assertIn('worker termination could not be confirmed.', actual)
            self.assertNotIn('detailed diagnostics were suppressed', actual)

    def test_independent_envelope_components_give_521_byte_bound(self):
        maximum_checks = dict.fromkeys(CHECK_NAMES, 'not_attempted')
        self.assertEqual(len(json_bytes(maximum_checks)), 146)
        self.assertEqual(sum(len(key) for key in ERROR_KEYS), 46)
        # Seven quoted keys, seven colons, six commas and two braces.
        outer_syntax = 46 + 7 * 2 + 7 + 6 + 2
        self.assertEqual(outer_syntax, 75)
        maximum_code = self.m._startup_classification(0)[0]
        maximum_status = self.m._startup_classification(2)[1]
        maximum_message = self.m._startup_message(15, STAGE)
        components = (len(json_bytes(2)), len(json_bytes(maximum_status)),
                      len(json_bytes(maximum_code)), len(json_bytes(maximum_message)),
                      len(json_bytes(maximum_checks)), len(json_bytes(False)),
                      len(json_bytes(None)))
        self.assertEqual(components, (1, 11, 25, 253, 146, 5, 4))
        self.assertEqual(outer_syntax + sum(components) + 1, 521)
        self.assertLessEqual(521, 4096)

    def test_all_check_maps_fit_existing_envelope_with_exact_lf(self):
        # Exhaustive scalar check combinations deliberately overcover reachable
        # progress. They do not claim a worker completed any particular check.
        for values in itertools.product(CHECK_VALUES, repeat=5):
            checks = dict(zip(CHECK_NAMES, values))
            for signum in (0, 2, 15):
                for name in (None, STAGE):
                    envelope = self.envelope(signum, name, checks)
                    self.assertEqual(tuple(envelope), ERROR_KEYS)
                    self.assertIs(envelope['committed'], False)
                    self.assertIsNone(envelope['receipt'])
                    self.assertIs(envelope['checks'], checks)
                    wire = json_bytes(envelope) + b'\n'
                    self.assertEqual(wire.count(b'\n'), 1)
                    self.assertTrue(wire.endswith(b'\n'))
                    self.assertLessEqual(len(wire), 521)
                    self.assertEqual(json.loads(wire), envelope)
            self.assertEqual(tuple(checks.values()), values)

    def test_exact_maximum_check_envelope_lengths_for_each_form(self):
        checks = dict.fromkeys(CHECK_NAMES, 'not_attempted')
        for signum, name, length in ((0, None, 339), (2, None, 345), (15, None, 345),
                                     (0, STAGE, 503), (2, STAGE, 509), (15, STAGE, 509)):
            with self.subTest(signum=signum, stage=name is not None):
                self.assertEqual(len(json_bytes(self.envelope(signum, name, checks))) + 1,
                                 length)

    def test_scalar_helpers_do_not_observe_clocks_signals_processes_or_io(self):
        # These ordinary boundary sentinels detect unintended side effects of the
        # real scalar calls. No fake worker, root, clock or outcome is supplied.
        targets = ((builtins, ('open', 'print')),
                   (time, ('time', 'time_ns', 'monotonic', 'monotonic_ns',
                           'perf_counter', 'perf_counter_ns', 'sleep')),
                   (signal, ('getsignal', 'signal', 'pthread_sigmask', 'sigpending',
                             'raise_signal', 'sigwait')),
                   (subprocess, ('Popen', 'run', 'call')),
                   (os, ('open', 'read', 'write', 'close', 'stat', 'lstat', 'fstat',
                         'mkdir', 'unlink', 'rmdir', 'rename', 'scandir', 'listdir',
                         'getcwd', 'waitpid', 'kill', 'killpg', 'fork', 'posix_spawn')))
        with ExitStack() as stack:
            for module, names in targets:
                for name in names:
                    if hasattr(module, name):
                        stack.enter_context(patch.object(module, name,
                                                        side_effect=forbidden_hook))
            for stream in (sys.stdout, sys.stderr):
                stack.enter_context(patch.object(stream, 'write', side_effect=forbidden_hook))
            for signum, base in ((0, FAILURE), (2, INTERRUPTED), (15, INTERRUPTED)):
                self.assertIs(type(self.m._startup_classification(signum)), tuple)
                self.assertEqual(self.m._startup_message(signum, None), base)
                self.assertEqual(self.m._startup_message(signum, STAGE), base + ' ' + HINT)
            self.refuse('supervision_unavailable', self.m._startup_classification, True)
            self.refuse('supervision_unavailable', self.m._startup_message, 1, HookValue())
            self.refuse('unsafe_path', self.m._startup_message, 0, 'invalid-stage')
