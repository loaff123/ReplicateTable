"""Anchored no-replace eager-memory install; no worker or signal-policy claim.

A actual completed stage is required. The caller owns semantic/source/runtime
replay and current-live admission. Cooperative cancellation precedes the kernel
attempt; arbitrary asynchronous exceptions may prevent capture or delivery.
Catchable interruption gets bounded best-effort original-inode reconciliation.
The destination is never deleted, including if reconciliation cannot finish.
"""
import ctypes
import errno
import os

from . import _native_fs_generated as _g
from . import _native_fs_owners as _o
from . import _native_fs_profile as _p
from . import _native_stage as _s
from . import _native_supervisor as _supervisor
from ._native_abi import _syscall_binding
from ._native_budget_state import LogicalOnlyBudget, _checkpoint, _validate_budget, _signal_value
from ._bundle_models import PreparedReceipt, BundleReceipt, _read_model
from .errors import Refusal, ComputationError


_UNSUPPORTED = (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP, errno.EXDEV)


def _rename_noreplace(parent_fd, old_name, destination_name):
    """Only errno/zero crosses the ABI helper; no fallback or signal mutation."""
    native = old = destination = None
    try:
        native = _syscall_binding()
        if native is None:
            return errno.ENOSYS
        old = old_name.encode('utf-8')
        destination = destination_name.encode('utf-8')
        result = native[1](ctypes.c_long(316), ctypes.c_int(parent_fd),
                           ctypes.c_char_p(old), ctypes.c_int(parent_fd),
                           ctypes.c_char_p(destination), ctypes.c_uint(1))
        if result == -1:
            return ctypes.get_errno()
        if type(result) is not int or result != 0:
            return errno.ENOSYS
        return 0
    finally:
        native = old = destination = None


def _original_installed(root):
    """Actual inode+namespace observation, never a scalar receipt as authority."""
    if (not _o._matches_parent(root.parent_identity, os.fstat(root.parent_fd)) or
            not _o._matches_parent(root.created_identity, os.fstat(root.fd))):
        return False
    try:
        destination = os.stat(root.destination_name, dir_fd=root.parent_fd,
                              follow_symlinks=False)
    except FileNotFoundError:
        return False
    if not _o._matches_parent(root.created_identity, destination):
        return False
    try:
        os.stat(root.name, dir_fd=root.parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    return False


def _capture_installed(root, outcome, prepared, receipt):
    object.__setattr__(outcome, '_prepared', prepared)
    object.__setattr__(outcome, '_receipt', receipt)
    object.__setattr__(outcome, '_committed', True)
    object.__setattr__(root, '_committed', True)


def _reconcile_install(root, outcome, prepared, receipt):
    if _original_installed(root):
        _capture_installed(root, outcome, prepared, receipt)
        return True
    return False


def _receipts(prepared):
    arguments = dict(version=2,status='committed',source=prepared.source,
        recipe_sha256=prepared.recipe_sha256,plan_sha256=prepared.plan_sha256,
        result_sha256=prepared.result_sha256,runtime_sha256=prepared.runtime_sha256,
        manifest_sha256=prepared.manifest_sha256,bundle_bytes=prepared.output_bytes)
    # Both shells are prepared before the syscall. Their immutable children
    # are the exact shared receipt bindings, not a second model/value forest.
    normal = BundleReceipt(**arguments,interrupted_after_commit=False)
    interrupted = BundleReceipt(**arguments,interrupted_after_commit=True)
    return normal, interrupted


def _validate_install(writer, prepared, outcome, budget):
    if type(budget) is not LogicalOnlyBudget:
        raise Refusal('supervision_unavailable')
    cancellation = _validate_budget(budget)
    _supervisor._outcome_state(outcome)
    if (outcome.cancellation is not cancellation or outcome.finding is not None or
            outcome.committed or outcome.startup_failed or outcome.receipt is not None or
            outcome.prepared is not None):
        raise Refusal('supervision_unavailable')
    _s._active(writer)
    if (writer.kind != 'bundle' or not writer.finished or writer._mode is not None or
            writer.current_fd != -1 or writer.support_fd != -1):
        raise Refusal('unsafe_path')
    if type(prepared) is not PreparedReceipt:
        raise Refusal('invalid_bundle')
    _read_model(prepared)
    if (prepared.kind != 'bundle' or prepared.source.kind != 'memory' or
            prepared.output_bytes != writer._total_size):
        raise Refusal('invalid_bundle')
    return cancellation


def _recheck_stage(writer, budget):
    _g._recheck_root_parent(writer.root, budget)
    _p._qualify_output_parent(writer.root, budget)
    _s._root_original(writer)
    _s._enumerate(writer, writer.root.fd, False, budget)
    if _s._index(writer._created, 'support') is not None:
        try:
            _s._open_support(writer)
            _s._enumerate(writer, writer.support_fd, True, budget)
            _s._support_original(writer)
        finally:
            writer._support_cell._close()
    _s._root_original(writer)


def _install_memory_bundle(writer, prepared, outcome, budget):
    cancellation = _validate_install(writer, prepared, outcome, budget)
    _checkpoint(budget)
    _recheck_stage(writer, budget)
    normal, interrupted = _receipts(prepared)
    root = writer.root
    _checkpoint(budget)
    try:
        code = _rename_noreplace(root.parent_fd, root.name, root.destination_name)
        if code:
            if code in (errno.EEXIST, errno.ENOTEMPTY):
                raise Refusal('output_exists')
            if code in _UNSUPPORTED:
                raise Refusal('unsupported_atomic_commit')
            raise ComputationError('io_error')
        # Confirm the effect: even an unqualified/no-op syscall cannot create
        # successful outcome state merely by returning zero.
        if not _original_installed(root):
            raise Refusal('unsupported_atomic_commit')
        receipt = interrupted if _signal_value(cancellation) else normal
        _capture_installed(root, outcome, prepared, receipt)
        _checkpoint(budget)
        return receipt
    except BaseException:
        try:
            _reconcile_install(root, outcome, prepared, interrupted)
        except BaseException:
            # Repeated caller interruption cannot be turned into a promise of
            # reconciliation, rollback or delivery. Preserve the first error.
            pass
        raise
