"""One fixed import-time Linux x86_64 libc syscall binding.

This private metadata supplies no process, FD, source or installation
authority. Consumers own fixed syscall arguments and all current buffers.
The tuple/function configuration is immutable in use, including unavailable
state. Runtime inventory must account for import initialization and retained
type/library metadata separately from each current-call ABI lane.
"""
import ctypes
import os
import sys


def _acquire_binding():
    try:
        if (sys.platform != 'linux' or os.uname().machine != 'x86_64' or
                sys.byteorder != 'little' or sys.implementation.name != 'cpython' or
                sys.version_info[:2] not in ((3, 12), (3, 13)) or
                ctypes.sizeof(ctypes.c_void_p) != 8 or
                ctypes.sizeof(ctypes.c_long) != 8 or
                ctypes.sizeof(ctypes.c_ulong) != 8 or
                ctypes.sizeof(ctypes.c_size_t) != 8 or
                ctypes.sizeof(ctypes.c_int) != 4):
            return None
        library = ctypes.CDLL('/lib/x86_64-linux-gnu/libc.so.6', use_errno=True)
        call = library.syscall
        call.argtypes = (ctypes.c_long,)
        call.restype = ctypes.c_long
        return library, call
    except (OSError, AttributeError) as error:
        # Dependency errors do not escape or retain this acquisition frame.
        # No exception text/notes/attributes are inspected or rewritten.
        BaseException.__traceback__.__set__(error, None)
        BaseException.__context__.__set__(error, None)
        BaseException.__cause__.__set__(error, None)
        return None


_BINDING = _acquire_binding()


def _syscall_binding():
    """Return fixed metadata/None; never initialize, retry or perform IO."""
    return _BINDING
