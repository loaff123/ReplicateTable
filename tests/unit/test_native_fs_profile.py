"""Closed actual-parent qualification for the experimental tmpfs profile."""
import ctypes
import errno
import importlib
import os
from pathlib import Path
import tempfile
import unittest
import weakref
from unittest.mock import patch

from replicatetable import _native_fs_generated as roots
from replicatetable._native_budget_state import LogicalOnlyBudget, _CancellationState
from replicatetable.errors import Refusal


class TmpfsParentProfileTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('replicatetable._native_fs_profile')
        self.assertTrue(callable(getattr(self.m, '_qualify_output_parent', None)),
                        'Missing closed tmpfs parent qualifier')
        self.temp = tempfile.TemporaryDirectory(dir='/tmp', prefix='rt-profile-')
        self.addCleanup(self.temp.cleanup)
        self.budget = LogicalOnlyBudget(_CancellationState())
        # Obtain the genuine parent owner before testing this gate itself.
        # No entry is created; the gate is restored for every test call.
        with patch.object(self.m, '_qualify_output_parent', return_value=None):
            self.root = roots._prepare_stage_root(Path(self.temp.name) / 'out', (), self.budget)
        self.addCleanup(roots._close_generated_root, self.root)

    def call(self, root=None, budget=None):
        return self.m._qualify_output_parent(self.root if root is None else root,
                                            self.budget if budget is None else budget)

    def fake(self, *, magic=0x01021994, flags=0, failed_call=None,
             failure_errno=errno.EIO, return_value=-1):
        calls = []
        storage_refs = []

        def native(number, fd, *arguments):
            self.assertIs(type(number), ctypes.c_long)
            self.assertIs(type(fd), ctypes.c_int)
            self.assertEqual(fd.value, self.root.parent_fd)
            calls.append(number.value)
            pointer = arguments[-1]
            storage = pointer._obj
            storage_refs.append(weakref.ref(storage))
            if failed_call == number.value:
                ctypes.set_errno(failure_errno)
                return return_value
            if number.value == 138:
                self.assertEqual(len(arguments), 1)
                self.assertEqual(ctypes.sizeof(storage), 120)
                storage[0] = magic
            elif number.value == 16:
                self.assertEqual(len(arguments), 2)
                self.assertIs(type(arguments[0]), ctypes.c_ulong)
                self.assertEqual(arguments[0].value, 0x80086601)
                self.assertEqual(ctypes.sizeof(storage), 8)
                self.assertEqual(storage.value, 0)
                storage.value = flags
            else:
                self.fail('Unexpected native syscall')
            return 0

        return native, calls, storage_refs

    def run_fake(self, native):
        supported = patch.object(self.m, '_PROFILE_SUPPORTED', True)
        binding = patch.object(self.m, '_syscall_binding', return_value=(None, native))
        supported.start()
        self.addCleanup(supported.stop)
        binding.start()
        self.addCleanup(binding.stop)

    def caught(self, function):
        caught = None
        try:
            function()
        except Refusal as error:
            caught = error
        self.assertIsNotNone(caught)
        return caught

    def test_actual_supported_tmpfs_parent_uses_original_fd_without_mutation(self):
        if not self.m._PROFILE_SUPPORTED:
            self.skipTest('Native success requires exact Linux6.18.44 x86_64 profile')
        original = os.fstat(self.root.parent_fd)
        self.assertIsNone(self.call())
        after = os.fstat(self.root.parent_fd)
        self.assertEqual((original.st_dev, original.st_ino, original.st_mode),
                         (after.st_dev, after.st_ino, after.st_mode))
        self.assertFalse((Path(self.temp.name) / 'out').exists())

    def test_closed_owner_and_partial_states_refuse_before_native_calls(self):
        native, calls, _ = self.fake()
        self.run_fake(native)
        for owner in (object(), object.__new__(roots._GeneratedRoot)):
            with self.subTest(owner=type(owner).__name__):
                error = self.caught(lambda: self.call(root=owner))
                self.assertEqual(error.code, 'unsafe_path')
        self.assertEqual(calls, [])

    def test_retired_owner_does_not_query_or_close_reused_descriptor(self):
        native, calls, _ = self.fake()
        self.run_fake(native)
        roots._close_generated_root(self.root)
        foreign = os.open(self.temp.name, os.O_RDONLY | os.O_DIRECTORY)
        try:
            error = self.caught(self.call)
            self.assertEqual(error.code, 'unsafe_path')
            os.fstat(foreign)
        finally:
            os.close(foreign)
        self.assertEqual(calls, [])

    def test_invalid_budget_refuses_before_native_calls(self):
        native, calls, _ = self.fake()
        self.run_fake(native)
        error = self.caught(lambda: self.call(budget=object()))
        self.assertEqual(error.code, 'supervision_unavailable')
        self.assertEqual(calls, [])

    def test_cancelled_budget_precedes_profile_queries(self):
        native, calls, _ = self.fake()
        self.run_fake(native)
        state = _CancellationState()
        state._latch(15)
        error = self.caught(lambda: self.call(budget=LogicalOnlyBudget(state)))
        self.assertEqual((error.code, error.exit_code), ('interrupted', 143))
        self.assertEqual(calls, [])

    def test_unqualified_kernel_profile_refuses_without_native_query(self):
        native, calls, _ = self.fake()
        self.run_fake(native)
        with patch.object(self.m, '_PROFILE_SUPPORTED', False):
            error = self.caught(self.call)
        self.assertEqual((error.code, error.exit_code), ('unsafe_path', 2))
        self.assertIn('lookup semantics', error.message)
        self.assertEqual(calls, [])

    def test_unavailable_shared_binding_refuses_without_retry(self):
        with patch.object(self.m, '_PROFILE_SUPPORTED', True), \
                patch.object(self.m, '_syscall_binding', return_value=None), \
                patch.object(ctypes, 'CDLL', side_effect=AssertionError('per-call CDLL')):
            error = self.caught(self.call)
        self.assertEqual((error.code, error.exit_code), ('unsafe_path', 2))

    def test_overlay_and_unknown_filesystems_refuse_before_flags_query(self):
        for magic in (0x794c7630, 0xef53, 0x1234):
            with self.subTest(magic=magic):
                native, calls, storage_refs = self.fake(magic=magic)
                with patch.object(self.m, '_PROFILE_SUPPORTED', True), \
                        patch.object(self.m, '_syscall_binding', return_value=(None, native)):
                    error = self.caught(self.call)
                self.assertEqual((error.code, error.exit_code), ('unsafe_path', 2))
                self.assertEqual(calls, [138])
                self.assertTrue(all(ref() is None for ref in storage_refs))

    def test_casefold_and_encryption_refuse_before_creation(self):
        for flags in (0x40000000, 0x800, 0x40000800):
            with self.subTest(flags=flags):
                native, calls, _ = self.fake(flags=flags)
                with patch.object(self.m, '_PROFILE_SUPPORTED', True), \
                        patch.object(self.m, '_syscall_binding', return_value=(None, native)):
                    error = self.caught(self.call)
                self.assertEqual((error.code, error.exit_code), ('unsafe_path', 2))
                self.assertEqual(calls, [138, 16])
                self.assertFalse((Path(self.temp.name) / 'out').exists())

    def test_supported_flags_and_widths_succeed_without_stale_errno_read(self):
        native, calls, storage_refs = self.fake(flags=0x40)
        self.run_fake(native)
        with patch.object(ctypes, 'get_errno', side_effect=AssertionError('stale errno')):
            self.assertIsNone(self.call())
        self.assertEqual(calls, [138, 16])
        self.assertTrue(all(ref() is None for ref in storage_refs))

    def test_unsupported_query_errno_is_refusal_and_keeps_borrowed_fd(self):
        for number in (138, 16):
            for code in (errno.ENOSYS, errno.ENOTTY, errno.EOPNOTSUPP):
                with self.subTest(number=number, errno=code):
                    native, _, storage_refs = self.fake(failed_call=number, failure_errno=code)
                    with patch.object(self.m, '_PROFILE_SUPPORTED', True), \
                            patch.object(self.m, '_syscall_binding', return_value=(None, native)):
                        error = self.caught(self.call)
                    self.assertEqual((error.code, error.exit_code), ('unsafe_path', 2))
                    self.assertTrue(all(ref() is None for ref in storage_refs))
                    os.fstat(self.root.parent_fd)

    def test_operational_query_error_preserves_exit3_and_retires_buffer(self):
        for number in (138, 16):
            with self.subTest(number=number):
                native, _, storage_refs = self.fake(failed_call=number)
                with patch.object(self.m, '_PROFILE_SUPPORTED', True), \
                        patch.object(self.m, '_syscall_binding', return_value=(None, native)):
                    error = self.caught(self.call)
                self.assertEqual((error.code, error.exit_code), ('io_error', 3))
                self.assertTrue(all(ref() is None for ref in storage_refs))

    def test_malformed_native_return_never_becomes_success(self):
        for result in (True, 1, -2):
            with self.subTest(result=result):
                native, calls, _ = self.fake(failed_call=138, return_value=result)
                with patch.object(self.m, '_PROFILE_SUPPORTED', True), \
                        patch.object(self.m, '_syscall_binding', return_value=(None, native)):
                    error = self.caught(self.call)
                self.assertEqual((error.code, error.exit_code), ('unsafe_path', 2))
                self.assertEqual(calls, [138])

    def test_high32_flag_bits_refuse_and_retire_storage(self):
        native, calls, storage_refs = self.fake(flags=1 << 32)
        self.run_fake(native)
        error = self.caught(self.call)
        self.assertEqual((error.code, error.exit_code), ('unsafe_path', 2))
        self.assertEqual(calls, [138, 16])
        self.assertTrue(all(ref() is None for ref in storage_refs))

    def test_raised_native_oserror_does_not_retain_operation_buffer(self):
        storage_refs = []

        def native(number, fd, pointer):
            storage_refs.append(weakref.ref(pointer._obj))
            raise OSError(errno.EIO, 'owned native fixture')

        self.run_fake(native)
        error = self.caught(self.call)
        self.assertEqual((error.code, error.exit_code), ('io_error', 3))
        self.assertEqual(len(storage_refs), 1)
        self.assertIsNone(storage_refs[0]())

    def test_cancellation_after_query_does_not_retain_operation_buffer(self):
        state = _CancellationState()
        observed, calls, storage_refs = self.fake()

        def native(number, fd, *arguments):
            result = observed(number, fd, *arguments)
            if number.value == 16:
                state._latch(2)
            return result

        self.run_fake(native)
        error = self.caught(lambda: self.call(budget=LogicalOnlyBudget(state)))
        self.assertEqual((error.code, error.exit_code), ('interrupted', 130))
        self.assertEqual(calls, [138, 16])
        self.assertTrue(all(ref() is None for ref in storage_refs))

    def test_original_parent_identity_mismatch_refuses_before_query(self):
        native, calls, _ = self.fake()
        self.run_fake(native)
        with patch.object(self.m._o, '_matches_parent', return_value=False):
            error = self.caught(self.call)
        self.assertEqual(error.code, 'unsafe_path')
        self.assertEqual(calls, [])

    def test_post_query_original_parent_identity_is_rechecked(self):
        native, calls, _ = self.fake()
        self.run_fake(native)
        with patch.object(self.m._o, '_matches_parent', side_effect=(True, False)):
            error = self.caught(self.call)
        self.assertEqual(error.code, 'unsafe_path')
        self.assertEqual(calls, [138, 16])


if __name__ == '__main__':
    unittest.main()
