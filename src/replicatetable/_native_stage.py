"""Sequential real stage files, original seals and bounded readback.

Only the eager-memory LogicalOnlyBudget factory is provided. This layer owns
neither semantic/source replay nor worker, installation or receipt authority.
The writer borrows its generated root and owns exactly the transient FD pair.
Creation and seal ledgers stay separate and bounded to 136 entries. Enumeration
is sequential, uses one membership mask and closes before any read/hash lane.
"""
import fcntl
import os
import stat

from . import resources as _r
from . import _native_fs_owners as _o
from . import _native_fs_generated as _g
from . import _native_fs_profile as _p
from . import _native_workspace as _w
from ._native_budget_state import LogicalOnlyBudget, _checkpoint
from .codec import exact_int
from .errors import Refusal, ComputationError


_BUNDLE, _PLAN = 'bundle', 'plan'
_WRITE, _READ, _FAILED = 'write', 'read', 'failed'
_ROOTS = ('plan.json', 'recipe.json', 'report.html', 'result.json',
          'schema.json', 'table.csv', 'manifest.json')
_CREATE_FLAGS = _o._READ_FLAGS | os.O_WRONLY | os.O_CREAT | os.O_EXCL


class _CreationEntry(_o._Readonly):
    __slots__ = ('path', 'identity')

    def __init__(self):
        raise Refusal('unsafe_path')

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private stage creation entry is final')


class _SealedEntry(_o._Readonly):
    __slots__ = ('path', 'witness')

    def __init__(self):
        raise Refusal('unsafe_path')

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private stage sealed entry is final')


class _StageWitness(_o._Readonly):
    __slots__ = ('directory', 'entries')

    def __init__(self):
        raise Refusal('unsafe_path')

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private stage witness is final')


class _StageWriter(_o._Readonly):
    __slots__ = ('_root', '_kind', '_created', '_sealed', '_support_cell',
                 '_file_cell', '_current_index', '_current_cap', '_current_size',
                 '_total_size', '_read_offset', '_mode', '_finished', '_retired', '_seal')

    def __init__(self):
        raise Refusal('unsafe_path')

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private stage writer is final')

    @property
    def root(self): return self._root
    @property
    def kind(self): return self._kind
    @property
    def current_fd(self):
        return -1 if self._file_cell is None else _o._cell_fd(self._file_cell)
    @property
    def support_fd(self):
        return -1 if self._support_cell is None else _o._cell_fd(self._support_cell)
    @property
    def retired(self): return self._retired
    @property
    def finished(self): return self._finished
    @property
    def created_count(self): return 0 if self._created is None else len(self._created)
    @property
    def sealed_count(self): return 0 if self._sealed is None else len(self._sealed)


def _entry(kind, path, value):
    entry = object.__new__(kind)
    object.__setattr__(entry, 'path', path)
    object.__setattr__(entry, kind.__slots__[1], value)
    return entry


def _path(path, kind):
    if type(path) is not str:
        raise Refusal('unsafe_path')
    if kind == _PLAN:
        if path != 'plan.json':
            raise Refusal('unsafe_path')
        return
    if path in _ROOTS:
        return
    if (len(path) not in (19, 27) or path[:9] != 'support/c' or
            path[11:13] != '-s' or path[15:] not in ('.csv', '.schema.json')):
        raise Refusal('unsafe_path')
    for index in (9, 10, 13, 14):
        if path[index] not in '0123456789':
            raise Refusal('unsafe_path')
    if int(path[9:11]) >= _r.COLUMN_LIMIT or int(path[13:15]) >= _r.STAGE_LIMIT:
        raise Refusal('unsafe_path')


def _hard_cap(path):
    if path == 'recipe.json':
        return _r.RECIPE_BYTES_LIMIT, 'recipe_bytes_limit'
    if path == 'report.html':
        return _r.REPORT_BYTES_LIMIT, 'report_bytes_limit'
    if path in ('plan.json', 'schema.json', 'manifest.json') or path.endswith('.schema.json'):
        return _r.METADATA_BYTES_LIMIT, 'metadata_bytes_limit'
    return _r.BUNDLE_BYTES_LIMIT, 'bundle_bytes_limit'


def _index(entries, path):
    for index, entry in enumerate(entries):
        if entry.path == path:
            return index
    return None


def _shape(writer):
    if type(writer) is not _StageWriter:
        raise Refusal('unsafe_path')
    for field in _StageWriter.__slots__:
        if _o._stored(writer, field) is _o._MISSING:
            raise Refusal('unsafe_path')
    if (writer._kind is not _BUNDLE and writer._kind is not _PLAN or
            type(writer._retired) is not bool or type(writer._finished) is not bool):
        raise Refusal('unsafe_path')
    if writer.retired:
        for field in _StageWriter.__slots__:
            if field not in ('_kind', '_retired', '_finished') and _o._stored(writer, field) is not None:
                raise Refusal('unsafe_path')
        return
    if (type(writer._created) is not list or type(writer._sealed) is not list or
            len(writer._created) > 136 or len(writer._sealed) > len(writer._created) or
            writer._file_cell is writer._support_cell):
        raise Refusal('unsafe_path')
    _o._cell_fd(writer._file_cell)
    _o._cell_fd(writer._support_cell)
    if writer._mode is not None and all(writer._mode is not mode for mode in (_WRITE, _READ, _FAILED)):
        raise Refusal('unsafe_path')
    if writer._current_index is not None:
        exact_int(writer._current_index, 'unsafe_path', maximum=len(writer._created)-1)
    for field in ('_current_cap', '_current_size', '_total_size', '_read_offset'):
        exact_int(_o._stored(writer, field), 'unsafe_path', maximum=_r.BUNDLE_BYTES_LIMIT)
    if type(writer.root) is not _g._GeneratedRoot:
        raise Refusal('unsafe_path')
    if writer.finished:
        if (type(writer._seal) is not _StageWitness or
                type(_o._stored(writer._seal, 'directory')) is not _o._FileWitness or
                type(_o._stored(writer._seal, 'entries')) is not tuple):
            raise Refusal('unsafe_path')
    elif writer._seal is not None:
        raise Refusal('unsafe_path')


def _active(writer):
    _shape(writer)
    if writer.retired or writer._mode is _FAILED:
        raise Refusal('unsafe_path')
    _w._created_root(writer.root, workspace=False)
    if writer.root.kind != 'stage':
        raise Refusal('unsafe_path')
    if writer.finished:
        if writer._seal.directory is not writer.root.sealed_witness:
            raise Refusal('unsafe_path')
    elif writer.root.sealed_witness is not None:
        raise Refusal('unsafe_path')


def _budget(budget):
    if type(budget) is not LogicalOnlyBudget:
        raise Refusal('supervision_unavailable')
    _checkpoint(budget)


def _empty(root, budget):
    iterator = None
    try:
        with os.scandir(root.fd) as iterator:
            for entry in iterator:
                _checkpoint(budget)
                raise Refusal('invalid_bundle')
        _checkpoint(budget)
    finally:
        iterator = None


def _begin_stage_writer(root, kind, budget):
    _budget(budget)
    if type(kind) is not str or kind not in (_BUNDLE, _PLAN):
        raise Refusal('unsafe_path')
    _w._created_root(root, workspace=False)
    if root.kind != 'stage' or root.sealed_witness is not None:
        raise Refusal('unsafe_path')
    try:
        _g._recheck_root_parent(root, budget)
        _p._qualify_output_parent(root, budget)
        _w._root_original(root)
        _empty(root, budget)
        _w._root_original(root)
    except OSError as error:
        _g._os_failure(error)
    writer = object.__new__(_StageWriter)
    for field in _StageWriter.__slots__:
        object.__setattr__(writer, field, None)
    object.__setattr__(writer, '_root', root)
    object.__setattr__(writer, '_kind', _BUNDLE if kind == _BUNDLE else _PLAN)
    object.__setattr__(writer, '_created', [])
    object.__setattr__(writer, '_sealed', [])
    object.__setattr__(writer, '_support_cell', _o._FDCell())
    object.__setattr__(writer, '_file_cell', _o._FDCell())
    for field in ('_current_cap', '_current_size', '_total_size', '_read_offset'):
        object.__setattr__(writer, field, 0)
    object.__setattr__(writer, '_finished', False)
    object.__setattr__(writer, '_retired', False)
    return writer


def _root_original(writer):
    _w._root_original(writer.root)
    if writer.finished:
        witness = writer._seal.directory
        if (not _o._matches_stat(witness, os.fstat(writer.root.fd)) or
                not _o._matches_stat(witness, os.stat(writer.root.name,
                                  dir_fd=writer.root.parent_fd, follow_symlinks=False))):
            raise Refusal('bundle_changed')


def _support_original(writer):
    index = _index(writer._created, 'support')
    if index is None or writer.support_fd < 0:
        raise Refusal('unsafe_path')
    original = writer._created[index].identity
    if (not _o._matches_parent(original, os.fstat(writer.support_fd)) or
            not _o._matches_parent(original, os.stat('support', dir_fd=writer.root.fd,
                                                       follow_symlinks=False))):
        raise Refusal('unsafe_path')
    if writer.finished:
        witness = writer._sealed[_index(writer._sealed, 'support')].witness
        if (not _o._matches_stat(witness, os.fstat(writer.support_fd)) or
                not _o._matches_stat(witness, os.stat('support', dir_fd=writer.root.fd,
                                                       follow_symlinks=False))):
            raise Refusal('bundle_changed')


def _open_support(writer, *, create=False):
    index = _index(writer._created, 'support')
    if index is None:
        if not create:
            raise Refusal('unsafe_path')
        try:
            os.mkdir('support', mode=0o700, dir_fd=writer.root.fd)
        except OSError:
            raise ComputationError('io_error') from None
        original = _o._identity(os.stat('support', dir_fd=writer.root.fd, follow_symlinks=False))
        writer._created.append(_entry(_CreationEntry, 'support', original))
    object.__setattr__(writer._support_cell, '_fd',
                       os.open('support', _o._DIR_FLAGS, dir_fd=writer.root.fd))
    _support_original(writer)
    _root_original(writer)


def _payloads_complete(writer):
    for path in _ROOTS[:6]:
        if _index(writer._sealed, path) is None:
            raise Refusal('invalid_bundle')
    for entry in writer._created:
        if entry.path.startswith('support/'):
            if entry.path.endswith('.csv'):
                other = entry.path[:-4] + '.schema.json'
            else:
                other = entry.path[:-12] + '.csv'
            if _index(writer._sealed, other) is None:
                raise Refusal('invalid_bundle')


def _failed(writer, *, close=False):
    object.__setattr__(writer, '_mode', _FAILED)
    if close:
        _g._close_cells(writer._file_cell, writer._support_cell, quiet=True)


def _failure(error, *, stable=False):
    if isinstance(error, OSError):
        if error.errno in _o._PATH_ERRORS or error.errno == 9:
            raise Refusal('bundle_changed' if stable else 'unsafe_path') from None
        raise ComputationError('io_error') from None
    if stable and type(error) is Refusal and error.code == 'unsafe_path':
        raise Refusal('bundle_changed') from None


def _open_stage_member(writer, path, maximum_bytes, budget):
    _budget(budget)
    _active(writer)
    _path(path, writer.kind)
    cap, code = _hard_cap(path)
    exact_int(maximum_bytes, code, maximum=cap)
    if (writer.finished or writer._mode is not None or writer.current_fd != -1 or
            writer.support_fd != -1 or _index(writer._created, path) is not None or
            _index(writer._created, 'manifest.json') is not None):
        raise Refusal('unsafe_path')
    if path == 'manifest.json':
        _payloads_complete(writer)
    try:
        _g._recheck_root_parent(writer.root, budget)
        _root_original(writer)
        if path.startswith('support/'):
            _open_support(writer, create=True)
            parent, name = writer.support_fd, path[8:]
        else:
            parent, name = writer.root.fd, path
        if len(writer._created) >= 136:
            raise Refusal('invalid_bundle')
        try:
            object.__setattr__(writer._file_cell, '_fd',
                               os.open(name, _CREATE_FLAGS, 0o600, dir_fd=parent))
        except OSError:
            raise ComputationError('io_error') from None
        original = _w._regular_identity(os.fstat(writer.current_fd))
        writer._created.append(_entry(_CreationEntry, path, original))
        object.__setattr__(writer, '_current_index', len(writer._created)-1)
        object.__setattr__(writer, '_current_cap', maximum_bytes)
        object.__setattr__(writer, '_current_size', 0)
        object.__setattr__(writer, '_read_offset', 0)
        object.__setattr__(writer, '_mode', _WRITE)
        if _current_original(writer) != 0:
            raise Refusal('unsafe_path')
        _checkpoint(budget)
    except BaseException as error:
        _failed(writer, close=True)
        _failure(error)
        raise


def _current_original(writer):
    _root_original(writer)
    entry = writer._created[writer._current_index]
    if entry.path.startswith('support/'):
        _support_original(writer)
        parent, name = writer.support_fd, entry.path[8:]
    else:
        parent, name = writer.root.fd, entry.path
    size = _w._original_regular_size(entry.identity, os.fstat(writer.current_fd))
    if _w._original_regular_size(entry.identity, os.stat(name, dir_fd=parent,
                                                        follow_symlinks=False)) != size:
        raise Refusal('unsafe_path')
    return size


def _append_stage_member(writer, chunk, budget):
    _budget(budget)
    _active(writer)
    if writer._mode is not _WRITE or writer.current_fd < 0:
        raise Refusal('unsafe_path')
    if type(chunk) is not bytes:
        raise Refusal('unsafe_path')
    if len(chunk) > _r.SERIAL_BUFFER_BYTES:
        raise Refusal('memory_limit')
    cap, code = _hard_cap(writer._created[writer._current_index].path)
    if len(chunk) > cap - writer._current_size:
        raise Refusal(code)
    if len(chunk) > _r.BUNDLE_BYTES_LIMIT - writer._total_size:
        raise Refusal('bundle_bytes_limit')
    if len(chunk) > writer._current_cap - writer._current_size:
        raise ComputationError('resource_estimate_mismatch')
    view = piece = None
    try:
        if fcntl.fcntl(writer.current_fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_WRONLY:
            raise Refusal('unsafe_path')
        if (_current_original(writer) != writer._current_size or
                os.lseek(writer.current_fd, 0, os.SEEK_CUR) != writer._current_size):
            raise Refusal('unsafe_path')
        view = memoryview(chunk)
        offset = 0
        while offset < len(chunk):
            _checkpoint(budget)
            piece = view[offset:]
            try:
                written = os.write(writer.current_fd, piece)
            finally:
                piece.release()
                piece = None
            if type(written) is not int or not 1 <= written <= len(chunk)-offset:
                raise ComputationError('io_error')
            offset += written
            object.__setattr__(writer, '_current_size', writer._current_size + written)
            object.__setattr__(writer, '_total_size', writer._total_size + written)
        if (_current_original(writer) != writer._current_size or
                os.lseek(writer.current_fd, 0, os.SEEK_CUR) != writer._current_size):
            raise Refusal('unsafe_path')
        _checkpoint(budget)
    except BaseException as error:
        _failed(writer)
        _failure(error)
        raise
    finally:
        if view is not None:
            view.release()
        view = piece = None


def _current_stat_matches(writer, witness):
    entry = writer._created[writer._current_index]
    parent = writer.support_fd if entry.path.startswith('support/') else writer.root.fd
    name = entry.path[8:] if entry.path.startswith('support/') else entry.path
    return (_o._matches_stat(witness, os.fstat(writer.current_fd)) and
            _o._matches_stat(witness, os.stat(name, dir_fd=parent, follow_symlinks=False)))


def _clear_current(writer):
    object.__setattr__(writer, '_current_index', None)
    for field in ('_current_cap', '_current_size', '_read_offset'):
        object.__setattr__(writer, field, 0)
    object.__setattr__(writer, '_mode', None)


def _finish_stage_member(writer, budget):
    _budget(budget)
    _active(writer)
    if writer._mode is not _WRITE or writer.current_fd < 0:
        raise Refusal('unsafe_path')
    try:
        if (_current_original(writer) != writer._current_size or
                os.lseek(writer.current_fd, 0, os.SEEK_CUR) != writer._current_size):
            raise Refusal('unsafe_path')
        witness = _o._witness(os.fstat(writer.current_fd))
        if witness.size != writer._current_size or not _current_stat_matches(writer, witness):
            raise Refusal('unsafe_path')
        _checkpoint(budget)
        _g._close_cells(writer._file_cell, writer._support_cell)
        _checkpoint(budget)
        writer._sealed.append(_entry(_SealedEntry,
                                     writer._created[writer._current_index].path, witness))
        _clear_current(writer)
        return witness
    except BaseException as error:
        _failed(writer, close=True)
        _failure(error)
        raise


def _enumerate(writer, parent, support, budget):
    """One iterator and one finite mask; no name collection or witness copies."""
    seen = count = 0
    iterator = entry = None
    try:
        with os.scandir(parent) as iterator:
            for entry in iterator:
                _checkpoint(budget)
                count += 1
                if count > 136:
                    raise Refusal('invalid_bundle')
                found = None
                for index, original in enumerate(writer._created):
                    path = original.path
                    if support:
                        matches = path.startswith('support/') and path[8:] == entry.name
                    else:
                        matches = '/' not in path and path == entry.name
                    if matches:
                        found = index
                        break
                if found is None or seen & (1 << found):
                    raise Refusal('invalid_bundle')
                seen |= 1 << found
                observed = entry.stat(follow_symlinks=False)
                _o._raw_stat(observed)
                if original.path == 'support':
                    if not stat.S_ISDIR(observed.st_mode):
                        raise Refusal('invalid_bundle')
                    if not _o._matches_parent(original.identity, observed):
                        raise Refusal('bundle_changed')
                else:
                    if not stat.S_ISREG(observed.st_mode):
                        raise Refusal('invalid_bundle')
                    sealed = writer._sealed[_index(writer._sealed, original.path)].witness
                    if (not _o._matches_parent(original.identity, observed) or
                            not _o._matches_stat(sealed, observed)):
                        raise Refusal('bundle_changed')
                del observed
                entry = None
        for index, original in enumerate(writer._created):
            belongs = original.path.startswith('support/') if support else '/' not in original.path
            if belongs and not seen & (1 << index):
                raise Refusal('invalid_bundle')
        _checkpoint(budget)
    finally:
        iterator = entry = None


def _seal_stage(writer, budget):
    _budget(budget)
    _active(writer)
    if writer.finished or writer._mode is not None or writer.current_fd != -1 or writer.support_fd != -1:
        raise Refusal('unsafe_path')
    support = _index(writer._created, 'support')
    if len(writer._sealed) != len(writer._created) - (support is not None):
        raise Refusal('invalid_bundle')
    if writer.kind == _PLAN:
        if len(writer._sealed) != 1 or writer._sealed[0].path != 'plan.json':
            raise Refusal('invalid_bundle')
    else:
        _payloads_complete(writer)
        if _index(writer._sealed, 'manifest.json') is None:
            raise Refusal('invalid_bundle')
    try:
        _g._recheck_root_parent(writer.root, budget)
        _root_original(writer)
        _enumerate(writer, writer.root.fd, False, budget)
        if support is not None:
            _open_support(writer)
            _enumerate(writer, writer.support_fd, True, budget)
            _support_original(writer)
            support_witness = _o._witness(os.fstat(writer.support_fd))
            if not _o._matches_stat(support_witness, os.stat('support', dir_fd=writer.root.fd,
                                                           follow_symlinks=False)):
                raise Refusal('bundle_changed')
            writer._support_cell._close()
            writer._sealed.append(_entry(_SealedEntry, writer._created[support].path, support_witness))
        _root_original(writer)
        directory = _o._witness(os.fstat(writer.root.fd))
        if not _o._matches_stat(directory, os.stat(writer.root.name,
                                  dir_fd=writer.root.parent_fd, follow_symlinks=False)):
            raise Refusal('bundle_changed')
        _checkpoint(budget)
        seal = object.__new__(_StageWitness)
        object.__setattr__(seal, 'directory', directory)
        object.__setattr__(seal, 'entries', tuple(writer._sealed))
        object.__setattr__(writer.root, '_sealed_witness', directory)
        object.__setattr__(writer, '_seal', seal)
        object.__setattr__(writer, '_finished', True)
        return seal
    except BaseException as error:
        _failed(writer, close=True)
        _failure(error, stable=True)
        raise


def _stable_current(writer):
    size = _current_original(writer)
    path = writer._created[writer._current_index].path
    witness = writer._sealed[_index(writer._sealed, path)].witness
    if size != witness.size or not _current_stat_matches(writer, witness):
        raise Refusal('bundle_changed')
    return witness


def _open_stage_read(writer, path, budget):
    _budget(budget)
    _active(writer)
    _path(path, writer.kind)
    if not writer.finished or writer._mode is not None or writer.current_fd != -1 or writer.support_fd != -1:
        raise Refusal('unsafe_path')
    index = _index(writer._created, path)
    if index is None or _index(writer._sealed, path) is None:
        raise Refusal('unsafe_path')
    try:
        _g._recheck_root_parent(writer.root, budget)
        _root_original(writer)
        if path.startswith('support/'):
            _open_support(writer)
            parent, name = writer.support_fd, path[8:]
        else:
            parent, name = writer.root.fd, path
        object.__setattr__(writer._file_cell, '_fd', os.open(name, _o._READ_FLAGS, dir_fd=parent))
        object.__setattr__(writer, '_current_index', index)
        object.__setattr__(writer, '_mode', _READ)
        object.__setattr__(writer, '_read_offset', 0)
        if fcntl.fcntl(writer.current_fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
            raise Refusal('unsafe_path')
        witness = _stable_current(writer)
        object.__setattr__(writer, '_current_size', witness.size)
        object.__setattr__(writer, '_current_cap', witness.size)
        if os.lseek(writer.current_fd, 0, os.SEEK_CUR) != 0:
            raise Refusal('bundle_changed')
        _checkpoint(budget)
    except BaseException as error:
        _failed(writer, close=True)
        _failure(error, stable=True)
        raise


def _read_stage_chunk(writer, maximum_bytes, budget):
    _budget(budget)
    _active(writer)
    exact_int(maximum_bytes, 'unsafe_path', minimum=1, maximum=_r.SERIAL_BUFFER_BYTES)
    if not writer.finished or writer._mode is not _READ or writer.current_fd < 0:
        raise Refusal('unsafe_path')
    try:
        witness = _stable_current(writer)
        if (writer._read_offset > witness.size or
                os.lseek(writer.current_fd, 0, os.SEEK_CUR) != writer._read_offset):
            raise Refusal('bundle_changed')
        remaining = witness.size - writer._read_offset
        chunk = os.read(writer.current_fd, min(maximum_bytes, remaining) if remaining else 1)
        if type(chunk) is not bytes or len(chunk) > min(maximum_bytes, remaining):
            raise Refusal('bundle_changed')
        if remaining and not chunk:
            raise Refusal('bundle_changed')
        object.__setattr__(writer, '_read_offset', writer._read_offset + len(chunk))
        _stable_current(writer)
        if os.lseek(writer.current_fd, 0, os.SEEK_CUR) != writer._read_offset:
            raise Refusal('bundle_changed')
        _checkpoint(budget)
        return chunk
    except BaseException as error:
        _failed(writer)
        _failure(error, stable=True)
        raise


def _close_stage_member(writer):
    _shape(writer)
    if writer.retired:
        return
    if not writer.finished or writer._mode is _FAILED:
        _close_stage_writer(writer)
        return
    try:
        _g._close_cells(writer._file_cell, writer._support_cell)
    except BaseException:
        _failed(writer)
        raise
    _clear_current(writer)


def _close_stage_writer(writer, *, quiet=False):
    if type(quiet) is not bool:
        raise Refusal('unsafe_path')
    _shape(writer)
    if writer.retired:
        return
    first, second = writer._file_cell, writer._support_cell
    object.__setattr__(writer, '_retired', True)
    for field in _StageWriter.__slots__:
        if field not in ('_kind', '_retired', '_finished'):
            object.__setattr__(writer, field, None)
    _g._close_cells(first, second, quiet=quiet)
