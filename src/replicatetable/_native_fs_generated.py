"""Prepared generated roots: parent ownership, never creation or commit.

Original directory identities and one optional absolute parent description
remain fixed. Generated names confer no ownership of a directory entry.
Containment examines the resolved parent's actual ancestry, preserving '..'
in the forward no-follow walk. The caller still owns source/plan qualification,
stream protection, worker authority and all eventual write/install ordering.

The existing two-root projection pays these records; the existing transient
pair and stat16/walk8 lanes pay sequential walks. No ancestor vector, second
persistent path, payload read, root creation, signal policy or public API exists
here. Trusted quiescent filesystem assumptions and check/use races remain.
"""
import errno
import os
import stat
from pathlib import PosixPath

from . import _native_fs_owners as _o
from . import _native_fs_profile as _p
from ._native_fs import _qualify_path
from ._native_budget_state import _checkpoint
from .errors import Refusal, ComputationError


_PREFIX_STAGE = '.replicatetable-stage-'
_PREFIX_WORKSPACE = '.replicatetable-work-'


def _parent_ancestor_steps(path_description):
    """Count a bound from actual qualified text; the count grants no authority."""
    if type(path_description) is not str:
        raise Refusal('unsafe_path')
    normalized = _qualify_path(path_description)
    if not path_description.startswith('/') or normalized != path_description:
        raise Refusal('unsafe_path')
    del normalized
    start = 2 if path_description.startswith('//') else 1
    steps = 0
    length = len(path_description)
    while start < length:
        end = path_description.find('/', start)
        if end < 0:
            end = length
        if not (end - start == 2 and path_description[start] == '.' and
                path_description[start + 1] == '.'):
            steps += 1
        start = end + 1
    return steps


class _GeneratedRoot(_o._Readonly):
    __slots__ = ('_kind', '_root_cell', '_parent_cell', '_name',
                 '_created_identity', '_sealed_witness', '_parent_identity',
                 '_committed', '_retired', '_argument', '_path', '_destination')

    def __init__(self):
        raise Refusal('unsafe_path')

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private generated root is final')

    @property
    def kind(self): return self._kind
    @property
    def fd(self): return -1 if self._root_cell is None else _o._cell_fd(self._root_cell)
    @property
    def parent_fd(self):
        return -1 if self._parent_cell is None else _o._cell_fd(self._parent_cell)
    @property
    def name(self): return self._name
    @property
    def created_identity(self): return self._created_identity
    @property
    def sealed_witness(self): return self._sealed_witness
    @property
    def parent_identity(self): return self._parent_identity
    @property
    def committed(self): return self._committed
    @property
    def retired(self): return self._retired
    @property
    def original_argument(self): return self._argument
    @property
    def path_description(self): return self._path
    @property
    def destination_name(self): return self._destination


def _fresh_root(kind):
    root = object.__new__(_GeneratedRoot)
    for field in _GeneratedRoot.__slots__:
        object.__setattr__(root, field, None)
    object.__setattr__(root, '_kind', kind)
    object.__setattr__(root, '_committed', False)
    object.__setattr__(root, '_retired', False)
    object.__setattr__(root, '_root_cell', _o._FDCell())
    object.__setattr__(root, '_parent_cell', _o._FDCell())
    return root


def _valid_name(kind, name):
    prefix = _PREFIX_STAGE if kind == 'stage' else _PREFIX_WORKSPACE
    if type(name) is not str or len(name) != len(prefix) + 32:
        raise Refusal('unsafe_path')
    if not name.startswith(prefix):
        raise Refusal('unsafe_path')
    for index in range(len(prefix), len(name)):
        if name[index] not in '0123456789abcdef':
            raise Refusal('unsafe_path')


def _root_shape(root):
    if type(root) is not _GeneratedRoot:
        raise Refusal('unsafe_path')
    for field in _GeneratedRoot.__slots__:
        if _o._stored(root, field) is _o._MISSING:
            raise Refusal('unsafe_path')
    if (type(root._kind) is not str or root._kind not in ('stage', 'workspace') or
            type(root._retired) is not bool or type(root._committed) is not bool):
        raise Refusal('unsafe_path')
    if root._retired:
        for field in _GeneratedRoot.__slots__:
            if field not in ('_kind', '_retired', '_committed') and _o._stored(root, field) is not None:
                raise Refusal('unsafe_path')
        return
    if (type(root._root_cell) is not _o._FDCell or type(root._parent_cell) is not _o._FDCell or
            root._root_cell is root._parent_cell):
        raise Refusal('unsafe_path')
    if root.fd < -1 or root.parent_fd < 0:
        raise Refusal('unsafe_path')
    if root._created_identity is not None:
        _o._identity_state(root._created_identity)
        if not stat.S_ISDIR(root._created_identity.mode):
            raise Refusal('unsafe_path')
    if root._sealed_witness is not None:
        _o._witness_state(root._sealed_witness)
        if (root._created_identity is None or root.fd < 0 or
                root._sealed_witness.device != root._created_identity.device or
                root._sealed_witness.inode != root._created_identity.inode or
                root._sealed_witness.mode != root._created_identity.mode):
            raise Refusal('unsafe_path')
    _o._identity_state(root._parent_identity)
    _valid_name(root._kind, root._name)
    if root._kind == 'stage':
        if (type(root._argument) is not str and type(root._argument) is not PosixPath or
                type(root._path) is not str or not root._path.startswith('/') or
                type(root._destination) is not str or not root._destination or
                '/' in root._destination or '\x00' in root._destination):
            raise Refusal('unsafe_path')
    elif root._path is None:
        if root._argument is not None or root._destination is not None:
            raise Refusal('unsafe_path')
    elif (type(root._path) is not str or root._path != '/tmp' or
          type(root._argument) is not str or root._argument != '/tmp' or
          root._destination is not None):
        raise Refusal('unsafe_path')


def _active_root(root):
    _root_shape(root)
    if root.retired or root.committed:
        raise Refusal('unsafe_path')
    if root.original_argument is not None:
        _qualify_path(root.original_argument)


def _close_cells(first, second, *, quiet=False):
    failure = None
    try:
        for cell in (first, second):
            if cell is None:
                continue
            try:
                cell._close()
            except BaseException as error:
                if failure is None:
                    failure = error
        if failure is not None and not quiet:
            if isinstance(failure, OSError):
                raise ComputationError('io_error') from None
            raise failure
    finally:
        # A secondary traceback can point back to this frame. End its local
        # back-reference on suppression, conversion and propagation alike.
        failure = None


def _retire_root(root, *, quiet=False):
    # Factories use this only for their own fresh local, including partial setup.
    first, second = root._root_cell, root._parent_cell
    object.__setattr__(root, '_retired', True)
    for field in _GeneratedRoot.__slots__:
        if field not in ('_kind', '_retired', '_committed'):
            object.__setattr__(root, field, None)
    _close_cells(first, second, quiet=quiet)


def _close_generated_root(root):
    _root_shape(root)
    if not root.retired:
        _retire_root(root)


def _os_failure(error):
    if error.errno in _o._PATH_ERRORS or error.errno == errno.EBADF:
        raise Refusal('unsafe_path') from None
    raise ComputationError('io_error') from None


def _held_identity_matches(owner):
    observed = os.fstat(owner.fd)
    _o._raw_stat(observed)
    original = owner.fd_witness
    return (observed.st_dev == original.device and observed.st_ino == original.inode and
            observed.st_mode == original.mode)


def _protected_shape(protected):
    if type(protected) is not tuple or len(protected) > 8:
        raise Refusal('unsafe_path')
    # Complete type/state checks precede every new acquisition.
    for owner in protected:
        if type(owner) is not _o._FileOwner and type(owner) is not _o._DirectoryOwner:
            raise Refusal('unsafe_path')
        for field in _o._Owner.__slots__:
            if _o._stored(owner, field) is _o._MISSING:
                raise Refusal('unsafe_path')
        _o._active_owner(owner)
    for owner in protected:
        if not _held_identity_matches(owner):
            raise Refusal('unsafe_path')


def _directory_overlap(identity, protected):
    for owner in protected:
        if type(owner) is _o._DirectoryOwner:
            original = owner.fd_witness
            if identity.device == original.device and identity.inode == original.inode:
                raise Refusal('source_output_overlap')


def _walk_directory(root, description, budget):
    start = 2 if description.startswith('//') else 1
    parent = root._parent_cell
    object.__setattr__(parent, '_fd', os.open('//' if start == 2 else '/', _o._DIR_FLAGS))
    identity = _o._identity(os.fstat(parent._fd))
    length = len(description)
    while start < length:
        _checkpoint(budget)
        end = description.find('/', start)
        if end < 0:
            end = length
        component = description[start:end]
        before = _o._identity(os.stat(component, dir_fd=parent._fd, follow_symlinks=False))
        child = root._root_cell
        object.__setattr__(child, '_fd', os.open(component, _o._DIR_FLAGS, dir_fd=parent._fd))
        if (not _o._matches_parent(before, os.fstat(child._fd)) or
                not _o._matches_parent(before, os.stat(component, dir_fd=parent._fd,
                                                       follow_symlinks=False)) or
                not _o._matches_parent(identity, os.fstat(parent._fd))):
            raise Refusal('unsafe_path')
        object.__setattr__(root, '_parent_cell', child)
        object.__setattr__(root, '_root_cell', parent)
        parent._close()
        parent = child
        identity = before
        del child, before, component
        start = end + 1
    object.__setattr__(root, '_parent_identity', identity)


def _check_ancestry(parent_fd, description, protected, budget):
    directories = False
    for owner in protected:
        if type(owner) is _o._DirectoryOwner:
            directories = True
    if not directories:
        return
    steps = _parent_ancestor_steps(description)
    current, following = _o._FDCell(), _o._FDCell()
    try:
        object.__setattr__(current, '_fd', os.dup(parent_fd))
        identity = _o._identity(os.fstat(current._fd))
        _directory_overlap(identity, protected)
        for _ in range(steps):
            _checkpoint(budget)
            before = _o._identity(os.stat('..', dir_fd=current._fd, follow_symlinks=False))
            object.__setattr__(following, '_fd', os.open('..', _o._DIR_FLAGS, dir_fd=current._fd))
            if (not _o._matches_parent(before, os.fstat(following._fd)) or
                    not _o._matches_parent(before, os.stat('..', dir_fd=current._fd,
                                                           follow_symlinks=False)) or
                    not _o._matches_parent(identity, os.fstat(current._fd))):
                raise Refusal('unsafe_path')
            _directory_overlap(before, protected)
            current._close()
            current, following = following, current
            identity = before
            del before
    except BaseException:
        _close_cells(current, following, quiet=True)
        raise
    else:
        _close_cells(current, following)


def _destination_absent(root, protected):
    try:
        observed = os.stat(root.destination_name, dir_fd=root.parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    _o._raw_stat(observed)
    if stat.S_ISLNK(observed.st_mode):
        raise Refusal('unsafe_path')
    for owner in protected:
        original = owner.fd_witness
        if observed.st_dev == original.device and observed.st_ino == original.inode:
            raise Refusal('source_output_overlap')
    raise Refusal('output_exists')


def _assign_name(root):
    try:
        entropy = os.urandom(16)
    except OSError:
        raise ComputationError('io_error') from None
    if type(entropy) is not bytes or len(entropy) != 16:
        raise ComputationError('io_error')
    prefix = _PREFIX_STAGE if root.kind == 'stage' else _PREFIX_WORKSPACE
    object.__setattr__(root, '_name', prefix + entropy.hex())


def _prepare_stage_root(output_path, protected_owners, budget):
    _checkpoint(budget)
    root = None
    try:
        _protected_shape(protected_owners)
        absolute = _o._absolute_path(output_path, budget)
        last = absolute.rfind('/')
        root_length = 2 if absolute.startswith('//') else 1
        destination = absolute[last + 1:] or '.'
        description = absolute[:max(last, root_length)]
        del absolute
        root = _fresh_root('stage')
        object.__setattr__(root, '_argument', output_path)
        object.__setattr__(root, '_path', description)
        object.__setattr__(root, '_destination', destination)
        _walk_directory(root, description, budget)
        _check_ancestry(root.parent_fd, description, protected_owners, budget)
        _destination_absent(root, protected_owners)
        if not _o._matches_parent(root.parent_identity, os.fstat(root.parent_fd)):
            raise Refusal('unsafe_path')
        _checkpoint(budget)
        _assign_name(root)
        if root.name == root.destination_name:
            raise ComputationError('io_error')
        _p._qualify_output_parent(root, budget)
        _checkpoint(budget)
        return root
    except BaseException as error:
        if root is not None:
            _retire_root(root, quiet=True)
        if isinstance(error, OSError):
            _os_failure(error)
        raise


def _prepare_workspace_root(stage_or_none, protected_owners, budget):
    _checkpoint(budget)
    root = None
    try:
        _protected_shape(protected_owners)
        if stage_or_none is not None:
            _active_root(stage_or_none)
            if stage_or_none.kind != 'stage':
                raise Refusal('unsafe_path')
            _recheck_root_parent(stage_or_none, budget)
        root = _fresh_root('workspace')
        if stage_or_none is None:
            description = '/tmp'
            object.__setattr__(root, '_argument', description)
            object.__setattr__(root, '_path', description)
            _walk_directory(root, description, budget)
        else:
            description = stage_or_none.path_description
            object.__setattr__(root._parent_cell, '_fd', os.dup(stage_or_none.parent_fd))
            identity = _o._identity(os.fstat(root.parent_fd))
            if identity != stage_or_none.parent_identity:
                raise Refusal('unsafe_path')
            object.__setattr__(root, '_parent_identity', identity)
            del identity
        _check_ancestry(root.parent_fd, description, protected_owners, budget)
        del description
        if not _o._matches_parent(root.parent_identity, os.fstat(root.parent_fd)):
            raise Refusal('unsafe_path')
        _checkpoint(budget)
        _assign_name(root)
        if stage_or_none is not None and root.name == stage_or_none.destination_name:
            raise ComputationError('io_error')
        _p._qualify_output_parent(root, budget)
        _checkpoint(budget)
        return root
    except BaseException as error:
        if root is not None:
            _retire_root(root, quiet=True)
        if isinstance(error, OSError):
            _os_failure(error)
        raise


def _recheck_root_parent(root, budget):
    _checkpoint(budget)
    _active_root(root)
    transient = None
    try:
        if not _o._matches_parent(root.parent_identity, os.fstat(root.parent_fd)):
            raise Refusal('unsafe_path')
        if root.path_description is not None:
            transient = _fresh_root(root.kind)
            _walk_directory(transient, root.path_description, budget)
            if transient.parent_identity != root.parent_identity:
                raise Refusal('unsafe_path')
        _checkpoint(budget)
    except BaseException as error:
        if transient is not None:
            _retire_root(transient, quiet=True)
        if isinstance(error, OSError):
            _os_failure(error)
        raise
    else:
        if transient is not None:
            _retire_root(transient)
