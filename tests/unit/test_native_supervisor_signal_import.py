"""Actual first module execution owns one fixed shared syscall binding."""
import ctypes
import errno
import importlib
import importlib.util
from pathlib import Path
import signal
import unittest
from unittest.mock import patch


class SharedBindingImportTests(unittest.TestCase):
    def setUp(self):
        product = importlib.import_module('replicatetable._native_supervisor')
        self.path = Path(product.__file__).with_name('_native_abi.py')
        self.assertTrue(self.path.is_file(), 'Shared import-time ABI module is missing')

    def fresh_import(self):
        spec = importlib.util.spec_from_file_location(
            'replicatetable._native_abi_first_import_fixture', self.path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def assert_unavailable_without_retry(self, module):
        self.assertIsNone(module._BINDING)
        with patch.object(ctypes, 'CDLL', side_effect=AssertionError('Forbidden retry')):
            self.assertIsNone(module._syscall_binding())
            self.assertIsNone(module._syscall_binding())

    def test_first_import_library_failure_retires_exception_and_never_retries(self):
        error = OSError('Library unavailable')
        with patch.object(ctypes, 'CDLL', side_effect=error) as acquire:
            module = self.fresh_import()
        acquire.assert_called_once_with('/lib/x86_64-linux-gnu/libc.so.6', use_errno=True)
        self.assertIsNone(error.__traceback__)
        self.assertIsNone(error.__context__)
        self.assertIsNone(error.__cause__)
        self.assert_unavailable_without_retry(module)

    def test_first_import_symbol_failure_retires_exception_and_never_retries(self):
        error = AttributeError('syscall unavailable')
        class MissingSymbol:
            @property
            def syscall(self):
                raise error
        with patch.object(ctypes, 'CDLL', return_value=MissingSymbol()) as acquire:
            module = self.fresh_import()
        acquire.assert_called_once_with('/lib/x86_64-linux-gnu/libc.so.6', use_errno=True)
        self.assertIsNone(error.__traceback__)
        self.assertIsNone(error.__context__)
        self.assertIsNone(error.__cause__)
        self.assert_unavailable_without_retry(module)

    def test_successful_import_fixes_signature_and_errno_before_any_operation(self):
        actual = ctypes.CDLL
        with patch.object(ctypes, 'CDLL', wraps=actual) as acquire:
            module = self.fresh_import()
        acquire.assert_called_once_with('/lib/x86_64-linux-gnu/libc.so.6', use_errno=True)
        binding = module._BINDING
        self.assertIs(type(binding), tuple)
        self.assertEqual(len(binding), 2)
        library, call = binding
        self.assertIs(type(library), ctypes.CDLL)
        self.assertIs(type(call), library._FuncPtr)
        self.assertEqual(call.argtypes, (ctypes.c_long,))
        self.assertIs(call.restype, ctypes.c_long)
        storage = (ctypes.c_ubyte * 32)()
        with patch.object(ctypes, 'CDLL', side_effect=AssertionError('Lazy construction')):
            self.assertIs(module._syscall_binding(), binding)
            self.assertIs(module._syscall_binding(), binding)
            ctypes.set_errno(0)
            # Read-only invalid-signal query establishes use_errno behavior;
            # no signal action is installed or replaced.
            result = call(13, ctypes.c_int(0), None, ctypes.byref(storage), ctypes.c_size_t(8))
            observed_errno = ctypes.get_errno()
            self.assertEqual((result, observed_errno), (-1, errno.EINVAL))
            result = call(13, ctypes.c_int(signal.SIGTERM), None,
                          ctypes.byref(storage), ctypes.c_size_t(8))
            self.assertEqual(result, 0)
        self.assertIs(module._BINDING, binding)


if __name__ == '__main__':
    unittest.main()
