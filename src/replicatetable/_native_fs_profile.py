"""Closed parent-FD gate for the experimental exact-kernel tmpfs profile.

No descriptor, path, feature token or source/install authority is created.
Native storage retires before a subsequent query, stat or checkpoint. Overlay
and all other filesystem implementations remain deliberately unsupported.
"""
import ctypes
import errno
import os
import sys

from . import _native_fs_owners as _o
from . import _native_fs_generated as _g
from ._native_abi import _syscall_binding
from ._native_budget_state import _checkpoint
from .errors import Refusal, ComputationError


_STATFS_STORAGE = ctypes.c_long * 15
_FLAGS_STORAGE = ctypes.c_ulong
_TMPFS = 0x01021994
_GETFLAGS = 0x80086601
_UNQUALIFIED_FEATURES = 0x40000800
_UNSUPPORTED_ERRORS = (errno.ENOSYS, errno.ENOTTY, errno.EOPNOTSUPP)
_PROFILE_MESSAGE = 'Output parent lookup semantics are not supported by this runtime profile.'


def _selected_profile():
    try:
        current = os.uname()
        return (current.sysname == 'Linux' and current.release == '6.18.44' and
                current.machine == 'x86_64' and sys.byteorder == 'little' and
                sys.implementation.name == 'cpython' and
                sys.version_info[:2] in ((3, 12), (3, 13)) and
                ctypes.sizeof(ctypes.c_long) == 8 and ctypes.sizeof(ctypes.c_int) == 4 and
                ctypes.sizeof(ctypes.c_void_p) == 8)
    except (OSError, AttributeError):
        return False


_PROFILE_SUPPORTED = _selected_profile()


def _query_failure(code):
    if type(code) is not int or code in _UNSUPPORTED_ERRORS:
        return 1
    return 2


def _query_fd(fd, flags):
    """Return only scalar status/value after native storage/error retirement."""
    native = storage = pointer = None
    try:
        native = _syscall_binding()
        if native is None:
            return 1, 0
        storage = _FLAGS_STORAGE() if flags else _STATFS_STORAGE()
        pointer = ctypes.byref(storage)
        if flags:
            result = native[1](ctypes.c_long(16), ctypes.c_int(fd),
                               ctypes.c_ulong(_GETFLAGS), pointer)
        else:
            result = native[1](ctypes.c_long(138), ctypes.c_int(fd), pointer)
        if result == -1:
            observed_errno = ctypes.get_errno()
            return _query_failure(observed_errno), 0
        if type(result) is not int or result != 0:
            return 1, 0
        value = storage.value if flags else storage[0]
        if flags and not 0 <= value <= 0xffffffff:
            return 1, 0
        return 0, value
    except OSError as error:
        # No dependency exception crosses this helper's real return barrier.
        return _query_failure(error.errno), 0
    finally:
        native = storage = pointer = None


def _require_query(status):
    if status == 1:
        raise Refusal('unsafe_path', _PROFILE_MESSAGE)
    if status != 0:
        raise ComputationError('io_error')


def _qualify_output_parent(root, budget):
    _checkpoint(budget)
    _g._active_root(root)
    if not _PROFILE_SUPPORTED:
        raise Refusal('unsafe_path', _PROFILE_MESSAGE)
    try:
        if not _o._matches_parent(root.parent_identity, os.fstat(root.parent_fd)):
            raise Refusal('unsafe_path')
        status, magic = _query_fd(root.parent_fd, False)
        _require_query(status)
        if magic != _TMPFS:
            raise Refusal('unsafe_path', _PROFILE_MESSAGE)
        status, flags = _query_fd(root.parent_fd, True)
        _require_query(status)
        if flags & _UNQUALIFIED_FEATURES:
            raise Refusal('unsafe_path', _PROFILE_MESSAGE)
        if not _o._matches_parent(root.parent_identity, os.fstat(root.parent_fd)):
            raise Refusal('unsafe_path')
    except OSError:
        raise ComputationError('io_error') from None
    _checkpoint(budget)
