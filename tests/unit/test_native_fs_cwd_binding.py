"""Cwd consumes the one preinitialized binding with bounded operation state."""
import ctypes
import errno
import importlib.util
import os
from pathlib import Path
import unittest
import weakref
from unittest.mock import patch

from replicatetable import _native_fs_owners as original
from replicatetable._native_budget_state import LogicalOnlyBudget, _CancellationState
from replicatetable.errors import Refusal


def _fresh_owners():
    name = 'replicatetable._native_fs_owners_cwd_fixture'
    spec = importlib.util.spec_from_file_location(name, Path(original.__file__))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CwdSharedBindingTests(unittest.TestCase):
    def setUp(self):
        self.module = _fresh_owners()
        self.budget = LogicalOnlyBudget(_CancellationState())

    def test_fixed_buffer_type_exists_before_any_operation(self):
        storage_type = getattr(self.module, '_CWD_STORAGE', None)
        self.assertIsNotNone(storage_type)
        self.assertIs(storage_type._type_, ctypes.c_ubyte)
        self.assertEqual(storage_type._length_, 4096)
        self.assertNotIn('_CWD_NATIVE', vars(self.module))

    def test_first_operation_does_not_acquire_another_cdll(self):
        with patch.object(ctypes, 'CDLL', wraps=ctypes.CDLL) as acquired:
            actual = self.module._bounded_cwd(self.budget)
        self.assertEqual(actual, os.getcwd())
        self.assertEqual(acquired.call_count, 0)

    def test_unavailable_binding_refuses_without_operation_time_retry(self):
        with patch.object(self.module, '_syscall_binding', return_value=None, create=True), \
                patch.object(ctypes, 'CDLL', wraps=ctypes.CDLL) as acquired:
            for _ in range(2):
                code = None
                try:
                    self.module._bounded_cwd(self.budget)
                except Refusal as error:
                    code = error.code
                self.assertEqual(code, 'unsafe_path')
        self.assertEqual(acquired.call_count, 0)

    def test_explicit_width_arguments_and_success_ignore_stale_errno(self):
        calls = []
        storage_refs = []

        def native(number, pointer, capacity):
            self.assertIs(type(number), ctypes.c_long)
            self.assertEqual(number.value, 79)
            self.assertIs(type(capacity), ctypes.c_ulong)
            self.assertEqual(capacity.value, 4096)
            storage = pointer._obj
            self.assertIs(type(storage), self.module._CWD_STORAGE)
            storage_refs.append(weakref.ref(storage))
            for index, byte in enumerate(b'/qualified\x00'):
                storage[index] = byte
            calls.append(True)
            ctypes.set_errno(errno.EIO)
            return 11

        with patch.object(self.module, '_syscall_binding', return_value=(None, native), create=True), \
                patch.object(ctypes, 'get_errno', side_effect=AssertionError('stale errno read')):
            actual = self.module._bounded_cwd(self.budget)
        self.assertEqual(actual, '/qualified')
        self.assertEqual(calls, [True])
        self.assertIsNone(storage_refs[0]())

    def test_failed_call_reads_errno_before_checkpoint_and_retires_storage(self):
        timeline = []
        storage_refs = []

        def native(number, pointer, capacity):
            timeline.append('call')
            storage_refs.append(weakref.ref(pointer._obj))
            return -1

        def observed_errno():
            timeline.append('errno')
            return errno.ERANGE

        retained_error = None
        with patch.object(self.module, '_syscall_binding', return_value=(None, native), create=True), \
                patch.object(self.module, '_checkpoint', side_effect=lambda budget: timeline.append('checkpoint')), \
                patch.object(ctypes, 'get_errno', observed_errno):
            try:
                self.module._bounded_cwd(self.budget)
            except Refusal as error:
                retained_error = error
        self.assertIsNotNone(retained_error)
        self.assertEqual(retained_error.code, 'unsafe_path')
        self.assertEqual(timeline[:3], ['checkpoint', 'call', 'errno'])
        self.assertEqual(len(storage_refs), 1)
        self.assertIsNone(storage_refs[0](), 'Retained failure traceback kept native storage alive')

    def test_malformed_native_result_retires_storage_with_plain_retained_error(self):
        for result in (0, 1, 4097, True):
            with self.subTest(result=result):
                storage_refs = []

                def native(number, pointer, capacity):
                    storage_refs.append(weakref.ref(pointer._obj))
                    return result

                retained_error = None
                with patch.object(self.module, '_syscall_binding', return_value=(None, native), create=True):
                    try:
                        self.module._bounded_cwd(self.budget)
                    except Refusal as error:
                        retained_error = error
                self.assertIsNotNone(retained_error)
                self.assertEqual(retained_error.code, 'unsafe_path')
                self.assertEqual(len(storage_refs), 1)
                self.assertIsNone(storage_refs[0]())

    def test_cancelled_operation_never_borrows_binding(self):
        state = _CancellationState()
        state._latch(2)
        with patch.object(self.module, '_syscall_binding', side_effect=AssertionError('binding after cancel'), create=True):
            with self.assertRaises(Refusal) as caught:
                self.module._bounded_cwd(LogicalOnlyBudget(state))
        self.assertEqual((caught.exception.code, caught.exception.exit_code), ('interrupted', 130))

    def test_invalid_utf8_refusal_does_not_retain_decode_error_or_storage(self):
        storage_refs = []

        def native(number, pointer, capacity):
            storage = pointer._obj
            storage_refs.append(weakref.ref(storage))
            storage[0], storage[1], storage[2] = 47, 255, 0
            return 3

        retained_error = None
        with patch.object(self.module, '_syscall_binding', return_value=(None, native), create=True):
            try:
                self.module._bounded_cwd(self.budget)
            except Refusal as error:
                retained_error = error
        self.assertIsNotNone(retained_error)
        self.assertEqual(retained_error.code, 'unsafe_path')
        self.assertIsNone(retained_error.__context__)
        self.assertEqual(len(storage_refs), 1)
        self.assertIsNone(storage_refs[0]())


if __name__ == '__main__':
    unittest.main()
