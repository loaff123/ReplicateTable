"""Genuine anchored ordinary bundle reader with first-acquisition witnesses.

No manifest, schema, source or replay authority is granted by this acquisition.
The outer verifier derives membership from its actual loaded/rederived plan.
One root owner and one transient FD pair are retained; one directory iterator
and one read chunk are sequential. No path-based reopening or mutation occurs.
"""
import fcntl
import os
import stat

from . import _native_fs_owners as _o
from . import _native_fs_profile as _p
from . import _native_stage as _s
from . import _native_fs_generated as _g
from . import resources as _r
from ._native_budget_state import _checkpoint
from .codec import exact_int
from .errors import Refusal, ComputationError


class _BundleReader(_o._Readonly):
    __slots__=('_owner','_entries','_file_cell','_support_cell','_current_index',
               '_offset','_total','_retired')
    def __init__(self):raise Refusal('unsafe_path')
    def __init_subclass__(cls,**kwargs):raise TypeError('Private bundle reader is final')
    @property
    def entries(self):return self._entries
    @property
    def directory_witness(self):return self._owner.fd_witness
    @property
    def current_fd(self):return -1 if self._file_cell is None else _o._cell_fd(self._file_cell)
    @property
    def total_bytes(self):return self._total
    @property
    def retired(self):return self._retired


def _shape(reader):
    if type(reader) is not _BundleReader:raise Refusal('unsafe_path')
    for name in _BundleReader.__slots__:
        if _o._stored(reader,name) is _o._MISSING:raise Refusal('unsafe_path')
    if type(reader._retired) is not bool:raise Refusal('unsafe_path')
    if reader.retired:
        if any(_o._stored(reader,n) is not None for n in _BundleReader.__slots__ if n!='_retired'):
            raise Refusal('unsafe_path')
        return
    if type(reader._owner) is not _o._DirectoryOwner or type(reader._entries) is not tuple:
        raise Refusal('unsafe_path')
    if not 7<=len(reader._entries)<=136 or reader._file_cell is reader._support_cell:
        raise Refusal('unsafe_path')
    _o._cell_fd(reader._file_cell);_o._cell_fd(reader._support_cell)
    exact_int(reader._offset,'unsafe_path',maximum=_r.BUNDLE_BYTES_LIMIT)
    exact_int(reader._total,'unsafe_path',maximum=_r.BUNDLE_BYTES_LIMIT)
    if reader._current_index is not None:
        exact_int(reader._current_index,'unsafe_path',maximum=len(reader._entries)-1)


def _active(reader,budget):
    _s._budget(budget);_shape(reader)
    if reader.retired:raise Refusal('unsafe_path')
    _o._active_owner(reader._owner)


def _changed_os(error):
    if error.errno in _o._PATH_ERRORS or error.errno==9:
        raise Refusal('bundle_changed') from None
    raise ComputationError('io_error') from None


def _original_root(reader,budget):
    _o._recheck_owner(reader._owner,budget,changed_code='bundle_changed')


def _support_index(reader):return _s._index(reader._entries,'support')


def _support_original(reader):
    index=_support_index(reader)
    if index is None or reader._support_cell._fd<0:raise Refusal('unsafe_path')
    witness=reader._entries[index].witness
    if (not _o._matches_stat(witness,os.fstat(reader._support_cell._fd)) or
        not _o._matches_stat(witness,os.stat('support',dir_fd=reader._owner.fd,follow_symlinks=False))):
        raise Refusal('bundle_changed')


def _open_support(reader):
    object.__setattr__(reader._support_cell,'_fd',os.open('support',_o._DIR_FLAGS,dir_fd=reader._owner.fd))
    _support_original(reader)


def _capture_entries(fd, entries, total, budget, *, support):
    """One native iterator, bounded names, no additional names/set collection."""
    with os.scandir(fd) as iterator:
        for entry in iterator:
            _checkpoint(budget)
            if len(entries)>=136:raise Refusal('invalid_bundle')
            if support:
                path='support/'+entry.name
                try:_s._path(path,'bundle')
                except Refusal:raise Refusal('invalid_bundle') from None
            else:
                path=entry.name
                if path not in _s._ROOTS and path!='support':raise Refusal('invalid_bundle')
            observed=entry.stat(follow_symlinks=False);_o._raw_stat(observed)
            if stat.S_ISLNK(observed.st_mode):raise Refusal('unsafe_path')
            if path=='support':
                if not stat.S_ISDIR(observed.st_mode):raise Refusal('invalid_bundle')
            else:
                if not stat.S_ISREG(observed.st_mode):raise Refusal('invalid_bundle')
                if observed.st_nlink!=1:raise Refusal('unsafe_path')
                cap,code=_s._hard_cap(path)
                if observed.st_size>cap:raise Refusal(code)
                total+=observed.st_size
                if total>_r.BUNDLE_BYTES_LIMIT:raise Refusal('bundle_bytes_limit')
            entries.append(_s._entry(_s._SealedEntry,path,_o._witness(observed)))
    return total


def _namespace_complete(entries):
    for name in _s._ROOTS:
        if _s._index(entries,name) is None:raise Refusal('invalid_bundle')
    for entry in entries:
        if entry.path.startswith('support/'):
            other=(entry.path[:-4]+'.schema.json' if entry.path.endswith('.csv')
                   else entry.path[:-12]+'.csv')
            if _s._index(entries,other) is None:raise Refusal('invalid_bundle')
    if _s._index(entries,'support') is not None and not any(e.path.startswith('support/') for e in entries):
        raise Refusal('invalid_bundle')


def _open_bundle_reader(directory,budget):
    _s._budget(budget)
    reader=object.__new__(_BundleReader)
    for name in _BundleReader.__slots__:object.__setattr__(reader,name,None)
    object.__setattr__(reader,'_retired',False)
    object.__setattr__(reader,'_file_cell',_o._FDCell())
    object.__setattr__(reader,'_support_cell',_o._FDCell())
    entries=None
    try:
        object.__setattr__(reader,'_owner',_o._open_directory(directory,budget))
        if not _p._PROFILE_SUPPORTED:raise Refusal('unsafe_path',_p._PROFILE_MESSAGE)
        status,magic=_p._query_fd(reader._owner.fd,False);_p._require_query(status)
        if magic!=_p._TMPFS:raise Refusal('unsafe_path',_p._PROFILE_MESSAGE)
        status,flags=_p._query_fd(reader._owner.fd,True);_p._require_query(status)
        if flags&_p._UNQUALIFIED_FEATURES:raise Refusal('unsafe_path',_p._PROFILE_MESSAGE)
        entries=[]
        total=_capture_entries(reader._owner.fd,entries,0,budget,support=False)
        support=_s._index(entries,'support')
        if support is not None:
            witness=entries[support].witness
            object.__setattr__(reader._support_cell,'_fd',os.open('support',_o._DIR_FLAGS,dir_fd=reader._owner.fd))
            if not _o._matches_stat(witness,os.fstat(reader._support_cell._fd)):
                raise Refusal('bundle_changed')
            total=_capture_entries(reader._support_cell._fd,entries,total,budget,support=True)
            if (not _o._matches_stat(witness,os.fstat(reader._support_cell._fd)) or
                not _o._matches_stat(witness,os.stat('support',dir_fd=reader._owner.fd,follow_symlinks=False))):
                raise Refusal('bundle_changed')
            reader._support_cell._close()
        _namespace_complete(entries)
        object.__setattr__(reader,'_entries',tuple(entries));entries=None
        object.__setattr__(reader,'_total',total)
        object.__setattr__(reader,'_offset',0)
        _original_root(reader,budget)
        return reader
    except BaseException as error:
        first=reader._file_cell;second=reader._support_cell;owner=reader._owner
        object.__setattr__(reader,'_retired',True)
        for name in _BundleReader.__slots__:
            if name!='_retired':object.__setattr__(reader,name,None)
        _g._close_cells(first,second,quiet=True)
        if owner is not None:_o._close_quietly(owner)
        entries=None
        if isinstance(error,OSError):_changed_os(error)
        raise


def _member_original(reader):
    entry=reader._entries[reader._current_index]
    if entry.path.startswith('support/'):
        _support_original(reader);parent=reader._support_cell._fd;name=entry.path[8:]
    else:parent=reader._owner.fd;name=entry.path
    if (not _o._matches_stat(entry.witness,os.fstat(reader.current_fd)) or
        not _o._matches_stat(entry.witness,os.stat(name,dir_fd=parent,follow_symlinks=False))):
        raise Refusal('bundle_changed')
    return entry.witness


def _open_bundle_member(reader,path,budget):
    _active(reader,budget);_s._path(path,'bundle')
    index=_s._index(reader._entries,path)
    if (index is None or reader._current_index is not None or reader.current_fd!=-1 or
        reader._support_cell._fd!=-1):raise Refusal('unsafe_path')
    try:
        _original_root(reader,budget)
        if path.startswith('support/'):
            _open_support(reader);parent=reader._support_cell._fd;name=path[8:]
        else:parent=reader._owner.fd;name=path
        object.__setattr__(reader._file_cell,'_fd',os.open(name,_o._READ_FLAGS,dir_fd=parent))
        object.__setattr__(reader,'_current_index',index);object.__setattr__(reader,'_offset',0)
        if fcntl.fcntl(reader.current_fd,fcntl.F_GETFL)&os.O_ACCMODE!=os.O_RDONLY:
            raise Refusal('unsafe_path')
        _member_original(reader)
        if os.lseek(reader.current_fd,0,os.SEEK_CUR)!=0:raise Refusal('bundle_changed')
        _checkpoint(budget)
    except BaseException as error:
        _g._close_cells(reader._file_cell,reader._support_cell,quiet=True)
        object.__setattr__(reader,'_current_index',None);object.__setattr__(reader,'_offset',0)
        if isinstance(error,OSError):_changed_os(error)
        raise


def _read_bundle_chunk(reader,maximum_bytes,budget):
    _active(reader,budget)
    exact_int(maximum_bytes,'unsafe_path',minimum=1,maximum=_r.SERIAL_BUFFER_BYTES)
    if reader._current_index is None or reader.current_fd<0:raise Refusal('unsafe_path')
    try:
        _original_root(reader,budget);witness=_member_original(reader)
        if reader._offset>witness.size or os.lseek(reader.current_fd,0,os.SEEK_CUR)!=reader._offset:
            raise Refusal('bundle_changed')
        remaining=witness.size-reader._offset
        chunk=os.read(reader.current_fd,min(maximum_bytes,remaining) if remaining else 1)
        if type(chunk) is not bytes or len(chunk)>min(maximum_bytes,remaining) or remaining and not chunk:
            raise Refusal('bundle_changed')
        object.__setattr__(reader,'_offset',reader._offset+len(chunk))
        _member_original(reader)
        if os.lseek(reader.current_fd,0,os.SEEK_CUR)!=reader._offset:raise Refusal('bundle_changed')
        _checkpoint(budget);return chunk
    except OSError as error:_changed_os(error)


def _close_bundle_member(reader):
    _shape(reader)
    if reader.retired:return
    first=reader._file_cell;second=reader._support_cell
    object.__setattr__(reader,'_current_index',None);object.__setattr__(reader,'_offset',0)
    _g._close_cells(first,second)


def _enumerate_original(reader,fd,budget,*,support):
    seen=count=0
    with os.scandir(fd) as iterator:
        for entry in iterator:
            _checkpoint(budget);count+=1
            if count>136:raise Refusal('bundle_changed')
            found=None
            for index,original in enumerate(reader._entries):
                path=original.path
                if (path.startswith('support/') and path[8:]==entry.name if support else '/' not in path and path==entry.name):
                    found=index;break
            if found is None or seen&(1<<found):raise Refusal('bundle_changed')
            seen|=1<<found
            if not _o._matches_stat(original.witness,entry.stat(follow_symlinks=False)):
                raise Refusal('bundle_changed')
    for index,original in enumerate(reader._entries):
        belongs=original.path.startswith('support/') if support else '/' not in original.path
        if belongs and not seen&(1<<index):raise Refusal('bundle_changed')


def _recheck_bundle_reader(reader,budget):
    _active(reader,budget)
    if reader.current_fd!=-1 or reader._support_cell._fd!=-1:raise Refusal('unsafe_path')
    try:
        _original_root(reader,budget)
        _enumerate_original(reader,reader._owner.fd,budget,support=False)
        if _support_index(reader) is not None:
            try:
                _open_support(reader)
                _enumerate_original(reader,reader._support_cell._fd,budget,support=True)
                _support_original(reader)
            finally:reader._support_cell._close()
        _original_root(reader,budget)
    except OSError as error:_changed_os(error)


def _close_bundle_reader(reader,*,quiet=False):
    if type(quiet) is not bool:raise Refusal('unsafe_path')
    _shape(reader)
    if reader.retired:return
    first,second,owner=reader._file_cell,reader._support_cell,reader._owner
    object.__setattr__(reader,'_retired',True)
    for name in _BundleReader.__slots__:
        if name!='_retired':object.__setattr__(reader,name,None)
    failure=None
    try:
        try:_g._close_cells(first,second)
        except BaseException as error:failure=error
        try:_o._close_owner(owner)
        except BaseException as error:
            if failure is None:failure=error
        if failure is not None and not quiet:raise failure
    finally:failure=None
