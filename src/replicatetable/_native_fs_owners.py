"""Private anchored ordinary-file/directory acquisition and original rechecks.

Private scalar records:
  _FileWitness(device,inode,mode,nlink,size,mtime_ns,ctime_ns)
  _Identity(device,inode,mode)
Device/inode/mode are nonnegative unsigned64 identifiers. Link count and size
are nonnegative signed64-domain counts. Timestamps have the signed64 domain.
Exact immutable scalar construction is NOT proof of filesystem acquisition.

Closed owners _FileOwner/_DirectoryOwner expose readonly fd, parent_fd, name,
normalized_path, fd_witness, entry_witness, parent_identity and retired. They
retain the original path argument, one absolute normalized description and
original observed identities; construction/reinitialization by a caller is
not acquisition. _open_regular(path,budget) and _open_directory(path,budget)
are the only acquiring factories. _recheck_owner(owner,budget,*,changed_code)
accepts only source_changed or bundle_changed and never refreshes originals.
_close_owner(owner) retires owned FD cells before one close each, is idempotent,
releases original argument/path/witness state, and does not unlink any entry.
_same_inode(left,right) compares only exact witnessed device/inode scalars.

Budget exact-state/checkpoint precedes acquisition. Path raw/state and bounded
cwd/join qualification precede opening. Every acquired FD enters its prebuilt
owned cell before fstat or other setup. Original parent comparison uses only
device/inode/mode; an ordinary file or external directory itself retains its
full seven-field witness. Known original-identity/path replacement is the
selected changed_code; acquisition path/type/link refusals are unsafe_path;
other ordinary OS failures are fixed io_error. Cleanup still runs after expiry
or cancellation, attempts both owned closes, and preserves an escaping primary.

Acquisition has at most two FD cells; recheck keeps the original two plus at
most two temporary walk cells. All are occupants of the EXISTING 160*512 state
reserve, alongside budget/cancellation and the 16-slot raw-stat/helper scratch. Scalar witnesses and owner
headers fit the existing input/root owner projections. Original and normalized
path occurrences use their nine existing slots. Fixed cwd/normalization buffers
and one-component traversal fit the existing 64KiB scratch, with lexical
relative text retired before cwd/final absolute construction. No persistent
cwd FD, ancestor vector, second path, global registry or new allowance.

The supported state is a trusted quiescent Linux x86_64 filesystem/process.
Final stat and path rewalk do not provide a hostile-mutation lock/snapshot.
Payload reads/hashes, source-reference sharing, stage writes/seals, receipt,
replay/native supervision and atomic commit belong to later increments.
Outer source/output/stream ordering and inode-alias protections are not waived.
"""
import ctypes
import errno
import os
import stat

from .codec import exact_int, utf8_length
from .errors import Refusal, ComputationError
from ._native_budget_state import _checkpoint
from ._native_abi import _syscall_binding
from ._native_fs import (_qualify_path, _joined_shape, _slot,
                         _normalize_workspace)


_UINT64 = (1 << 64) - 1
_INT64 = (1 << 63) - 1
_PATH_LIMIT = 4095
_MISSING = object()
_READ_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_DIR_FLAGS = _READ_FLAGS | os.O_DIRECTORY
_PATH_ERRORS = (errno.ENOENT, errno.ENOTDIR, errno.ELOOP, errno.ENAMETOOLONG)
_CWD_STORAGE = ctypes.c_ubyte * 4096


def _stored(value, name):
    try:
        return object.__getattribute__(value, name)
    except AttributeError:
        return _MISSING


def _new_record(value, kind):
    if type(value) is not kind:
        raise Refusal('unsafe_path')
    for field in kind.__slots__:
        if _stored(value, field) is not _MISSING:
            raise Refusal('unsafe_path')


class _Readonly:
    __slots__ = ()

    def __setattr__(self, name, value):
        raise AttributeError('Private filesystem state is readonly')

    def __delattr__(self, name):
        raise AttributeError('Private filesystem state is readonly')


def _id_fields(device, inode, mode):
    exact_int(device, 'unsafe_path', maximum=_UINT64)
    exact_int(inode, 'unsafe_path', maximum=_UINT64)
    exact_int(mode, 'unsafe_path', maximum=_UINT64)


def _file_fields(device, inode, mode, nlink, size, mtime_ns, ctime_ns):
    _id_fields(device, inode, mode)
    exact_int(nlink, 'unsafe_path', maximum=_INT64)
    exact_int(size, 'unsafe_path', maximum=_INT64)
    exact_int(mtime_ns, 'unsafe_path', minimum=-_INT64-1, maximum=_INT64)
    exact_int(ctime_ns, 'unsafe_path', minimum=-_INT64-1, maximum=_INT64)


class _Identity(_Readonly):
    __slots__ = ('device', 'inode', 'mode')

    def __init__(self, device, inode, mode):
        _new_record(self, _Identity)
        _id_fields(device, inode, mode)
        object.__setattr__(self, 'device', device)
        object.__setattr__(self, 'inode', inode)
        object.__setattr__(self, 'mode', mode)

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private identity is final')

    def __eq__(self, other):
        return (type(other) is _Identity and self.device == other.device and
                self.inode == other.inode and self.mode == other.mode)


class _FileWitness(_Readonly):
    __slots__ = ('device', 'inode', 'mode', 'nlink', 'size', 'mtime_ns', 'ctime_ns')

    def __init__(self, device, inode, mode, nlink, size, mtime_ns, ctime_ns):
        _new_record(self, _FileWitness)
        _file_fields(device, inode, mode, nlink, size, mtime_ns, ctime_ns)
        object.__setattr__(self, 'device', device)
        object.__setattr__(self, 'inode', inode)
        object.__setattr__(self, 'mode', mode)
        object.__setattr__(self, 'nlink', nlink)
        object.__setattr__(self, 'size', size)
        object.__setattr__(self, 'mtime_ns', mtime_ns)
        object.__setattr__(self, 'ctime_ns', ctime_ns)

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private file witness is final')

    def __eq__(self, other):
        return (type(other) is _FileWitness and self.device == other.device and
                self.inode == other.inode and self.mode == other.mode and
                self.nlink == other.nlink and self.size == other.size and
                self.mtime_ns == other.mtime_ns and self.ctime_ns == other.ctime_ns)


def _witness_state(value):
    if type(value) is not _FileWitness:
        raise Refusal('unsafe_path')
    _file_fields(_stored(value, 'device'), _stored(value, 'inode'),
                 _stored(value, 'mode'), _stored(value, 'nlink'),
                 _stored(value, 'size'), _stored(value, 'mtime_ns'),
                 _stored(value, 'ctime_ns'))


def _identity_state(value):
    if type(value) is not _Identity:
        raise Refusal('unsafe_path')
    _id_fields(_stored(value, 'device'), _stored(value, 'inode'), _stored(value, 'mode'))


def _raw_stat(value):
    # A single <=19-field stock structseq and helper state use 8KiB (16 of
    # the existing 512-byte state slots). Its frame ends before another stat.
    if (type(value) is not os.stat_result or os.stat_result.n_fields != 19 or
            os.stat_result.n_sequence_fields != 10):
        raise Refusal('unsafe_path')
    _file_fields(value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
                 value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _witness(value):
    _raw_stat(value)
    return _FileWitness(value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
                        value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _identity(value):
    _raw_stat(value)
    if not stat.S_ISDIR(value.st_mode):
        raise Refusal('unsafe_path')
    return _Identity(value.st_dev, value.st_ino, value.st_mode)


def _matches_stat(expected, observed):
    _witness_state(expected)
    _raw_stat(observed)
    return (expected.device == observed.st_dev and expected.inode == observed.st_ino and
            expected.mode == observed.st_mode and expected.nlink == observed.st_nlink and
            expected.size == observed.st_size and expected.mtime_ns == observed.st_mtime_ns and
            expected.ctime_ns == observed.st_ctime_ns)


def _matches_parent(expected, observed):
    _identity_state(expected)
    _raw_stat(observed)
    return (expected.device == observed.st_dev and expected.inode == observed.st_ino and
            expected.mode == observed.st_mode)


def _same_inode(left, right):
    _witness_state(left); _witness_state(right)
    return left.device == right.device and left.inode == right.inode


def _cwd_native():
    # The one shared binding was established before the operation. No local
    # CDLL/cache or allocating libc getcwd fallback is created here.
    native = _syscall_binding()
    if native is None:
        raise Refusal('unsafe_path')
    return native


def _decode_cwd(raw):
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return None
    finally:
        raw = None


def _bounded_cwd(budget):
    _checkpoint(budget)
    native = storage = pointer = raw = None
    try:
        native = _cwd_native()
        storage = _CWD_STORAGE()
        pointer = ctypes.byref(storage)
        result = native[1](ctypes.c_long(79), pointer, ctypes.c_ulong(4096))
        if result == -1:
            observed_errno = ctypes.get_errno()
        _checkpoint(budget)
        if type(result) is not int or not 2 <= result <= 4096:
            raise Refusal('unsafe_path')
        if storage[0] != 47 or storage[result-1] != 0:
            raise Refusal('unsafe_path')
        for index in range(result-1):
            if not storage[index]:
                raise Refusal('unsafe_path')
        raw = ctypes.string_at(pointer, result-1)
        decoded = _decode_cwd(raw)
        if decoded is None:
            raise Refusal('unsafe_path')
        return decoded
    finally:
        native = storage = pointer = raw = None


def _absolute_path(value, budget):
    normalized = _qualify_path(value)
    if normalized.startswith('/'):
        return normalized
    del normalized  # No relative normalized text survives cwd acquisition.
    cwd = _bounded_cwd(budget)
    cwd_bytes = utf8_length(cwd, 'unsafe_path', maximum=_PATH_LIMIT)
    raw = (value,) if type(value) is str else _slot(value, '_raw_paths')
    start, raw_bytes = _joined_shape(raw)
    separator = 0 if cwd.endswith('/') else 1
    total = cwd_bytes + separator + raw_bytes
    if total > _PATH_LIMIT:
        raise Refusal('unsafe_path')
    workspace = bytearray(max(1, total))
    encoded = cwd.encode('utf-8')
    workspace[:cwd_bytes] = encoded
    del encoded, cwd
    used = cwd_bytes
    # Even an empty raw sequence has the meaning of a trailing empty join.
    if not raw and separator:
        workspace[used] = 47
        used += 1
    for index in range(start, len(raw)):
        text = raw[index]
        if text.startswith('/'):
            raise Refusal('unsafe_path')  # Raw state changed after qualification.
        if used and workspace[used-1] != 47:
            workspace[used] = 47
            used += 1
        encoded = text.encode('utf-8')
        length = len(encoded)
        workspace[used:used+length] = encoded
        used += length
        del encoded
    return _normalize_workspace(workspace, used)


class _FDCell(_Readonly):
    """One registered descriptor; retired before any close or finalization."""
    __slots__ = ('_fd',)

    def __init__(self):
        _new_record(self, _FDCell)
        object.__setattr__(self, '_fd', -1)

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private descriptor cell is final')

    def _close(self):
        descriptor = _stored(self, '_fd')
        if type(descriptor) is not int or not -1 <= descriptor <= (1 << 31)-1:
            raise Refusal('unsafe_path')
        object.__setattr__(self, '_fd', -1)
        if descriptor >= 0:
            os.close(descriptor)

    def __del__(self):
        try:
            self._close()
        except BaseException:
            pass


def _cell_fd(cell):
    if type(cell) is not _FDCell:
        raise Refusal('unsafe_path')
    descriptor = _stored(cell, '_fd')
    if type(descriptor) is not int or not -1 <= descriptor <= (1 << 31)-1:
        raise Refusal('unsafe_path')
    return descriptor


class _Owner(_Readonly):
    __slots__ = ('_argument', '_normalized_path', '_name', '_file_cell', '_parent_cell',
                 '_fd_witness', '_entry_witness', '_parent_identity', '_retired')

    def __init__(self):
        raise Refusal('unsafe_path')

    @property
    def fd(self):
        cell = self._file_cell
        return -1 if cell is None else _cell_fd(cell)

    @property
    def parent_fd(self):
        cell = self._parent_cell
        return -1 if cell is None else _cell_fd(cell)

    @property
    def name(self): return self._name
    @property
    def normalized_path(self): return self._normalized_path
    @property
    def fd_witness(self): return self._fd_witness
    @property
    def entry_witness(self): return self._entry_witness
    @property
    def parent_identity(self): return self._parent_identity
    @property
    def retired(self): return self._retired


class _FileOwner(_Owner):
    __slots__ = ()
    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private file owner is final')


class _DirectoryOwner(_Owner):
    __slots__ = ()
    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private directory owner is final')


def _fresh_owner(kind):
    owner = object.__new__(kind)
    for field in _Owner.__slots__:
        object.__setattr__(owner, field, False if field == '_retired' else None)
    return owner


def _owner_shape(owner):
    kind = type(owner)
    if (kind is not _FileOwner and kind is not _DirectoryOwner or
            type(_stored(owner, '_retired')) is not bool):
        raise Refusal('unsafe_path')
    for field in ('_file_cell', '_parent_cell'):
        cell = _stored(owner, field)
        if cell is not None:
            _cell_fd(cell)


def _close_owner(owner):
    _owner_shape(owner)
    if owner._retired:
        return
    file_cell, parent_cell = owner._file_cell, owner._parent_cell
    object.__setattr__(owner, '_retired', True)
    for field in _Owner.__slots__:
        if field != '_retired':
            object.__setattr__(owner, field, None)
    first_error = None
    try:
        try:
            if file_cell is not None:
                file_cell._close()
        except BaseException as error:
            first_error = error
        try:
            if parent_cell is not None:
                parent_cell._close()
        except BaseException as error:
            if first_error is None:
                first_error = error
        if first_error is not None:
            if isinstance(first_error, OSError):
                raise ComputationError('io_error') from None
            raise first_error
    finally:
        # The first error's traceback can include this frame. Do not keep a
        # local back-reference after quiet suppression or outward propagation.
        first_error = None


def _close_quietly(owner):
    try:
        _close_owner(owner)
    except BaseException:
        pass


def _walk_parent(owner, absolute, budget, *, retain_name=True):
    root_length = 2 if absolute.startswith('//') else 1
    parent = _FDCell()
    object.__setattr__(owner, '_parent_cell', parent)
    object.__setattr__(parent, '_fd', os.open('//' if root_length == 2 else '/', _DIR_FLAGS))
    object.__setattr__(owner, '_parent_identity', _identity(os.fstat(parent._fd)))
    last = absolute.rfind('/')
    start = root_length
    while start < last:
        _checkpoint(budget)
        end = absolute.find('/', start, last+1)
        component = absolute[start:end]
        before = _identity(os.stat(component, dir_fd=parent._fd, follow_symlinks=False))
        child = _FDCell()
        object.__setattr__(owner, '_file_cell', child)
        object.__setattr__(child, '_fd', os.open(component, _DIR_FLAGS, dir_fd=parent._fd))
        if not _matches_parent(before, os.fstat(child._fd)):
            raise Refusal('unsafe_path')
        if not _matches_parent(before, os.stat(component, dir_fd=parent._fd, follow_symlinks=False)):
            raise Refusal('unsafe_path')
        object.__setattr__(owner, '_parent_cell', child)
        object.__setattr__(owner, '_parent_identity', before)
        object.__setattr__(owner, '_file_cell', None)
        parent._close()
        parent = child
        del child, component, before
        start = end+1
    if retain_name:
        object.__setattr__(owner, '_name', absolute[last+1:] or '.')


def _open_owner(kind, value, budget):
    _checkpoint(budget)
    absolute = _absolute_path(value, budget)
    owner = _fresh_owner(kind)
    object.__setattr__(owner, '_argument', value)
    object.__setattr__(owner, '_normalized_path', absolute)
    try:
        _walk_parent(owner, absolute, budget)
        _checkpoint(budget)
        before = _witness(os.stat(owner._name, dir_fd=owner.parent_fd, follow_symlinks=False))
        ordinary = stat.S_ISREG if kind is _FileOwner else stat.S_ISDIR
        if not ordinary(before.mode) or before.nlink < 1:
            raise Refusal('unsafe_path')
        cell = _FDCell()
        object.__setattr__(owner, '_file_cell', cell)
        flags = _READ_FLAGS if kind is _FileOwner else _DIR_FLAGS
        object.__setattr__(cell, '_fd', os.open(owner._name, flags, dir_fd=owner.parent_fd))
        opened = _witness(os.fstat(cell._fd))
        if opened != before or not _matches_stat(before, os.stat(owner._name, dir_fd=owner.parent_fd,
                                                                 follow_symlinks=False)):
            raise Refusal('unsafe_path')
        object.__setattr__(owner, '_fd_witness', opened)
        object.__setattr__(owner, '_entry_witness', before)
        if not _matches_parent(owner.parent_identity, os.fstat(owner.parent_fd)):
            raise Refusal('unsafe_path')
        _checkpoint(budget)
        return owner
    except BaseException as error:
        _close_quietly(owner)
        if isinstance(error, OSError):
            if error.errno in _PATH_ERRORS:
                raise Refusal('unsafe_path') from None
            raise ComputationError('io_error') from None
        raise


def _open_regular(path, budget):
    return _open_owner(_FileOwner, path, budget)


def _open_directory(path, budget):
    return _open_owner(_DirectoryOwner, path, budget)


def _active_owner(owner):
    _owner_shape(owner)
    if owner._retired or owner.fd < 0 or owner.parent_fd < 0:
        raise Refusal('unsafe_path')
    if type(owner._normalized_path) is not str or type(owner._name) is not str:
        raise Refusal('unsafe_path')
    _witness_state(owner._fd_witness); _witness_state(owner._entry_witness)
    _identity_state(owner._parent_identity)
    # Original arguments remain retained/charged; they cannot grow unexamined.
    _qualify_path(owner._argument)


def _recheck_owner(owner, budget, *, changed_code):
    if type(changed_code) is not str or changed_code not in ('source_changed', 'bundle_changed'):
        raise Refusal('unsafe_path')
    _checkpoint(budget)
    _active_owner(owner)
    transient = None
    try:
        if not _matches_parent(owner.parent_identity, os.fstat(owner.parent_fd)):
            raise Refusal(changed_code)
        if not _matches_stat(owner.fd_witness, os.fstat(owner.fd)):
            raise Refusal(changed_code)
        if not _matches_stat(owner.entry_witness, os.stat(owner.name, dir_fd=owner.parent_fd,
                                                          follow_symlinks=False)):
            raise Refusal(changed_code)
        transient = _fresh_owner(_DirectoryOwner)
        _walk_parent(transient, owner.normalized_path, budget, retain_name=False)
        if not _matches_parent(owner.parent_identity, os.fstat(transient.parent_fd)):
            raise Refusal(changed_code)
        if not _matches_stat(owner.entry_witness, os.stat(owner.name, dir_fd=transient.parent_fd,
                                                          follow_symlinks=False)):
            raise Refusal(changed_code)
        _checkpoint(budget)
    except BaseException as error:
        if transient is not None:
            _close_quietly(transient)
        if isinstance(error, OSError):
            if error.errno in _PATH_ERRORS or error.errno == errno.EBADF:
                raise Refusal(changed_code) from None
            raise ComputationError('io_error') from None
        if type(error) is Refusal and error.code == 'unsafe_path':
            raise Refusal(changed_code) from None
        raise
    else:
        if transient is not None:
            _close_owner(transient)
