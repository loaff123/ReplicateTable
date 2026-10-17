"""Private real temporary roots and four finite workspace members.

Original creation identities precede writes; stable witnesses never refresh.
Filesystem observations confer no source/replay/worker/commit authority. The
owning route proves worker quiescence before output sealing or entry cleanup.
An unadopted or lost worker never grants that condition. No install exists here.

Members have exactly the six projected workspace-file fields. Roots are passed
explicitly; no second pathname, root/witness forest or stored byte counter is
retained. FD/state, stat/walk/retirement and serial-buffer allowances remain the
existing ones, with concrete coexistence subject to independent qualification.
"""
import fcntl
import os
import stat

from . import resources as _r
from . import _native_fs_owners as _o
from . import _native_fs_generated as _g
from . import _native_fs_profile as _p
from ._native_budget_state import _checkpoint
from .codec import exact_int
from .errors import Refusal, ComputationError


_INPUTS = ('request.json', 'control.json')
_OUTPUTS = ('completion.json', 'payload.bin')
_ROLES = _INPUTS + _OUTPUTS
_CREATE_FLAGS = _o._READ_FLAGS | os.O_RDWR | os.O_CREAT | os.O_EXCL


def _role(value):
    if type(value) is not str or value not in _ROLES:
        raise Refusal('unsafe_path')


def _limit(value, *, input_limit=False):
    exact_int(value, 'memory_limit', maximum=_r.METADATA_BYTES_LIMIT if input_limit else _r.COUNT_MAX)


def _created_root(root, *, workspace=True):
    _g._active_root(root)
    if ((workspace and root.kind != 'workspace') or root.fd < 0 or
            root.created_identity is None):
        raise Refusal('unsafe_path')


def _root_original(root):
    if (not _o._matches_parent(root.parent_identity, os.fstat(root.parent_fd)) or
            not _o._matches_parent(root.created_identity, os.fstat(root.fd)) or
            not _o._matches_parent(root.created_identity,
                                  os.stat(root.name, dir_fd=root.parent_fd, follow_symlinks=False))):
        raise Refusal('unsafe_path')


def _create_generated_root(root, budget):
    _checkpoint(budget)
    _g._active_root(root)
    if root.fd != -1 or root.created_identity is not None or root.sealed_witness is not None:
        raise Refusal('unsafe_path')
    _g._recheck_root_parent(root, budget)
    _p._qualify_output_parent(root, budget)
    # mkdir is the exclusive acquisition attempt, never a prior exists check.
    try:
        os.mkdir(root.name, mode=0o700, dir_fd=root.parent_fd)
    except OSError:
        raise ComputationError('io_error') from None
    try:
        _checkpoint(budget)
        original = _o._identity(os.stat(root.name, dir_fd=root.parent_fd, follow_symlinks=False))
        object.__setattr__(root, '_created_identity', original)
        object.__setattr__(root._root_cell, '_fd', os.open(root.name, _o._DIR_FLAGS,
                                                        dir_fd=root.parent_fd))
        _root_original(root)
        _checkpoint(budget)
    except OSError as error:
        _g._os_failure(error)


class _WorkspaceMember(_o._Readonly):
    __slots__ = ('_file_cell', '_parent_cell', '_name', '_created_identity', '_witness', '_retired')

    def __init__(self):
        raise Refusal('unsafe_path')

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private workspace member is final')

    @property
    def fd(self): return -1 if self._file_cell is None else _o._cell_fd(self._file_cell)
    @property
    def parent_fd(self): return -1 if self._parent_cell is None else _o._cell_fd(self._parent_cell)
    @property
    def name(self): return self._name
    @property
    def created_identity(self): return self._created_identity
    @property
    def witness(self): return self._witness
    @property
    def retired(self): return self._retired


def _fresh_member(role):
    member = object.__new__(_WorkspaceMember)
    for field in _WorkspaceMember.__slots__:
        object.__setattr__(member, field, None)
    object.__setattr__(member, '_retired', False)
    object.__setattr__(member, '_name', role)
    object.__setattr__(member, '_file_cell', _o._FDCell())
    object.__setattr__(member, '_parent_cell', _o._FDCell())
    return member


def _member_shape(member):
    if type(member) is not _WorkspaceMember:
        raise Refusal('unsafe_path')
    for field in _WorkspaceMember.__slots__:
        if _o._stored(member, field) is _o._MISSING:
            raise Refusal('unsafe_path')
    if type(member._retired) is not bool:
        raise Refusal('unsafe_path')
    if member.retired:
        for field in _WorkspaceMember.__slots__:
            if field != '_retired' and _o._stored(member, field) is not None:
                raise Refusal('unsafe_path')
        return
    _role(member.name)
    if member._file_cell is member._parent_cell:
        raise Refusal('unsafe_path')
    _o._cell_fd(member._file_cell)
    _o._cell_fd(member._parent_cell)
    if member.created_identity is not None:
        _o._identity_state(member.created_identity)
        if not stat.S_ISREG(member.created_identity.mode):
            raise Refusal('unsafe_path')
    if member.witness is not None:
        _o._witness_state(member.witness)
        if (member.created_identity is None or member.witness.nlink != 1 or
                not _same_identity(member.created_identity, member.witness)):
            raise Refusal('unsafe_path')


def _active_member(member):
    _member_shape(member)
    if (member.retired or member.fd < 0 or member.parent_fd < 0 or
            member.created_identity is None):
        raise Refusal('unsafe_path')


def _same_identity(expected, observed):
    return (expected.device == observed.device and expected.inode == observed.inode and
            expected.mode == observed.mode)


def _regular_identity(observed):
    _o._raw_stat(observed)
    if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
        raise Refusal('unsafe_path')
    return _o._Identity(observed.st_dev, observed.st_ino, observed.st_mode)


def _original_regular_size(expected, observed):
    _o._raw_stat(observed)
    if (not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1 or
            observed.st_dev != expected.device or observed.st_ino != expected.inode or
            observed.st_mode != expected.mode):
        raise Refusal('unsafe_path')
    return observed.st_size


def _member_original(root, member):
    _root_original(root)
    if not _o._matches_parent(root.created_identity, os.fstat(member.parent_fd)):
        raise Refusal('unsafe_path')
    size = _original_regular_size(member.created_identity, os.fstat(member.fd))
    _original_regular_size(member.created_identity,
                           os.stat(member.name, dir_fd=member.parent_fd, follow_symlinks=False))
    return size


def _stable_member(root, member):
    if member.witness is None:
        raise Refusal('unsafe_path')
    _member_original(root, member)
    if (not _o._matches_stat(member.witness, os.fstat(member.fd)) or
            not _o._matches_stat(member.witness,
                                os.stat(member.name, dir_fd=member.parent_fd, follow_symlinks=False))):
        raise Refusal('unsafe_path')


def _retire_member(member, *, quiet=False):
    first, second = member._file_cell, member._parent_cell
    object.__setattr__(member, '_retired', True)
    for field in _WorkspaceMember.__slots__:
        if field != '_retired':
            object.__setattr__(member, field, None)
    _g._close_cells(first, second, quiet=quiet)


def _close_workspace_member(member):
    _member_shape(member)
    if not member.retired:
        _retire_member(member)


def _create_workspace_member(root, role, budget):
    _checkpoint(budget)
    _role(role)
    _created_root(root)
    member = None
    try:
        _root_original(root)
        member = _fresh_member(role)
        object.__setattr__(member._parent_cell, '_fd', os.dup(root.fd))
        if not _o._matches_parent(root.created_identity, os.fstat(member.parent_fd)):
            raise Refusal('unsafe_path')
        object.__setattr__(member._file_cell, '_fd',
                           os.open(role, _CREATE_FLAGS, 0o600, dir_fd=member.parent_fd))
        original = _regular_identity(os.fstat(member.fd))
        object.__setattr__(member, '_created_identity', original)
        if _member_original(root, member) != 0:
            raise Refusal('unsafe_path')
        _checkpoint(budget)
        return member
    except BaseException as error:
        if member is not None:
            _retire_member(member, quiet=True)
        if isinstance(error, OSError):
            _g._os_failure(error)
        raise


def _write_workspace_input(root, member, chunk, maximum_bytes, budget):
    _checkpoint(budget)
    if type(chunk) is not bytes:
        raise Refusal('unsafe_path')
    if len(chunk) > _r.SERIAL_BUFFER_BYTES:
        raise Refusal('memory_limit')
    _limit(maximum_bytes, input_limit=True)
    _created_root(root)
    _active_member(member)
    if member.name not in _INPUTS or member.witness is not None:
        raise Refusal('unsafe_path')
    try:
        if fcntl.fcntl(member.fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDWR:
            raise Refusal('unsafe_path')
        size = _member_original(root, member)
        if size > maximum_bytes or len(chunk) > maximum_bytes - size:
            raise Refusal('memory_limit')
        if os.lseek(member.fd, 0, os.SEEK_CUR) != size:
            raise Refusal('unsafe_path')
        view = memoryview(chunk)
        try:
            offset = 0
            while offset < len(chunk):
                _checkpoint(budget)
                piece = view[offset:]
                try:
                    written = os.write(member.fd, piece)
                finally:
                    piece.release()
                if type(written) is not int or not 1 <= written <= len(chunk) - offset:
                    raise ComputationError('io_error')
                offset += written
        finally:
            view.release()
        _checkpoint(budget)
    except OSError:
        raise ComputationError('io_error') from None


def _seal_workspace_input(root, member, budget):
    _checkpoint(budget)
    _created_root(root)
    _active_member(member)
    if member.name not in _INPUTS:
        raise Refusal('unsafe_path')
    try:
        if member.witness is not None:
            if fcntl.fcntl(member.fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
                raise Refusal('unsafe_path')
            _stable_member(root, member)
            _checkpoint(budget)
            return
        _member_original(root, member)
        witness = _o._witness(os.fstat(member.fd))
        if witness.nlink != 1 or not _same_identity(member.created_identity, witness):
            raise Refusal('unsafe_path')
        if not _o._matches_stat(witness,
                               os.stat(member.name, dir_fd=member.parent_fd, follow_symlinks=False)):
            raise Refusal('unsafe_path')
        object.__setattr__(member, '_witness', witness)
        member._file_cell._close()
        object.__setattr__(member._file_cell, '_fd',
                           os.open(member.name, _o._READ_FLAGS, dir_fd=member.parent_fd))
        if fcntl.fcntl(member.fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
            raise Refusal('unsafe_path')
        _stable_member(root, member)
        _checkpoint(budget)
    except OSError as error:
        _g._os_failure(error)


def _workspace_protocol_fd(root, member, role, budget):
    _checkpoint(budget)
    _role(role)
    _created_root(root)
    _active_member(member)
    if member.name != role:
        raise Refusal('unsafe_path')
    try:
        size = _member_original(root, member)
        access = fcntl.fcntl(member.fd, fcntl.F_GETFL) & os.O_ACCMODE
        if role in _INPUTS:
            if access != os.O_RDONLY:
                raise Refusal('unsafe_path')
            _stable_member(root, member)
        elif member.witness is not None or size != 0 or access not in (os.O_WRONLY, os.O_RDWR):
            raise Refusal('unsafe_path')
        _checkpoint(budget)
        return member.fd
    except OSError as error:
        _g._os_failure(error)


def _capture_workspace_output_witness(root, member, maximum_bytes, budget):
    """Caller must first prove actual worker quiescence; this is not that proof."""
    _checkpoint(budget)
    _limit(maximum_bytes)
    _created_root(root)
    _active_member(member)
    if member.name not in _OUTPUTS:
        raise Refusal('unsafe_path')
    try:
        if _member_original(root, member) > maximum_bytes:
            raise Refusal('memory_limit')
        if member.witness is not None:
            _stable_member(root, member)
            _checkpoint(budget)
            return
        witness = _o._witness(os.fstat(member.fd))
        if witness.size > maximum_bytes:
            raise Refusal('memory_limit')
        if witness.nlink != 1 or not _same_identity(member.created_identity, witness):
            raise Refusal('unsafe_path')
        if not _o._matches_stat(witness,
                               os.stat(member.name, dir_fd=member.parent_fd, follow_symlinks=False)):
            raise Refusal('unsafe_path')
        object.__setattr__(member, '_witness', witness)
        _checkpoint(budget)
    except OSError as error:
        _g._os_failure(error)


def _recheck_workspace_member(root, member, budget):
    _checkpoint(budget)
    _created_root(root)
    _active_member(member)
    try:
        _stable_member(root, member)
        _checkpoint(budget)
    except OSError as error:
        _g._os_failure(error)


def _remove_workspace_member(root, member):
    """Unlink only a proven sealed entry; caller owns worker-quiescence policy."""
    _g._root_shape(root)
    _member_shape(member)
    if (root.retired or root.kind != 'workspace' or root.committed or root.fd < 0 or
            root.created_identity is None or member.retired or member.fd < 0 or
            member.parent_fd < 0 or member.created_identity is None or member.witness is None):
        return False
    try:
        _stable_member(root, member)
        os.unlink(member.name, dir_fd=member.parent_fd)
        return True
    except (OSError, Refusal):
        return False


def _cleanup_empty_root(root):
    """Anchored rmdir proves emptiness; caller still owns quiescence policy."""
    _g._root_shape(root)
    if root.retired or root.committed or root.fd < 0 or root.created_identity is None:
        return False
    try:
        _root_original(root)
        os.rmdir(root.name, dir_fd=root.parent_fd)
        return True
    except (OSError, Refusal):
        return False
