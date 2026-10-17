"""Bounded, path-independent declared identities for trusted installed runtimes.

Integrity/profile identity only: this is neither authenticity nor whole-OS
attestation. Installations must remain quiescent throughout the process life.
"""
from __future__ import annotations

import re
from types import MappingProxyType
from contextlib import contextmanager

from .errors import Refusal
from .codec import OwnedMap, exact_int, freeze, preflight_json, utf8_length

BINDING_VERSION = 1
INVENTORY_FILES_LIMIT = 2048
INVENTORY_DIRECTORIES_LIMIT = 512
RELATIVE_PATH_BYTES_LIMIT = 128
RETAINED_PATH_BYTES_LIMIT = 128 * 1024
BINDING_FILES_LIMIT = 8192
BINDING_DIRECTORIES_LIMIT = 4096
FILE_BYTES_LIMIT = 128 * 1024**2
BINDING_BYTES_LIMIT = 256 * 1024**2
HASH_BUFFER_BYTES = 64 * 1024
SCANNER_SCRATCH_BOUND = 1_524_736
CORE_LIBRARIES_LIMIT = 16
RESOURCE_FILES_LIMIT = 256
# Distribution name -> (exact version, imported top-level name, payload roots).
PROFILE = MappingProxyType({
    'numpy': ('2.3.5', 'numpy', ('numpy','numpy.libs')),
    'pandas': ('2.2.3', 'pandas', ('pandas',)),
    'xarray': ('2026.4.0', 'xarray', ('xarray',)),
    'pint': ('0.25.2', 'pint', ('pint',)),
    'h5py': ('3.16.0', 'h5py', ('h5py','h5py.libs')),
    'h5netcdf': ('1.8.1', 'h5netcdf', ('h5netcdf',)),
    'flexcache': ('0.3', 'flexcache', ('flexcache',)),
    'flexparser': ('0.4', 'flexparser', ('flexparser',)),
    'platformdirs': ('4.12.3', 'platformdirs', ('platformdirs',)),
    'typing-extensions': ('4.16.0', 'typing_extensions', ('typing_extensions.py',)),
    'packaging': ('26.3', 'packaging', ('packaging',)),
    'python-dateutil': ('2.9.0.post0', 'dateutil', ('dateutil',)),
    'pytz': ('2026.5', 'pytz', ('pytz',)),
    'tzdata': ('2026.5', 'tzdata', ('tzdata',)),
    'six': ('1.17.0', 'six', ('six.py',)),
})


def _fail(code, component='runtime'):
    if code=='runtime_changed':
        raise Refusal(code, 'Runtime changed; restart the process before retrying')
    raise Refusal(code, f'Declared runtime check refused: {component}')


def _mapping(value, maximum, minimum=0):
    """Qualify exact backing and all keys before lookup/equality/protocol use.

    OwnedMap is an internal final-value seam, never a general Mapping promise.
    Its tuple backing is checked before methods are used; mutable child backing
    cannot be smuggled into a reused final map through its private constructor.
    """
    if type(value) is dict:
        if not minimum <= len(value) <= maximum: _fail('invalid_runtime')
        for key in value:
            utf8_length(key, 'invalid_runtime', maximum=RELATIVE_PATH_BYTES_LIMIT)
    elif type(value) is OwnedMap:
        try: items = object.__getattribute__(value, '_items')
        except AttributeError: _fail('invalid_runtime')
        if type(items) is not tuple or not minimum <= len(items) <= maximum:
            _fail('invalid_runtime')
        for pair in items:
            if type(pair) is not tuple or len(pair) != 2: _fail('invalid_runtime')
            utf8_length(pair[0], 'invalid_runtime', maximum=RELATIVE_PATH_BYTES_LIMIT)
            if type(pair[1]) not in (str, int, bool, tuple, OwnedMap):
                _fail('invalid_runtime')
        previous = None
        for key, _ in items:
            if previous is not None and key <= previous: _fail('invalid_runtime')
            previous = key
    else:
        _fail('invalid_runtime')
    return value


def _fields(value, names):
    _mapping(value, len(names), len(names))
    if set(value) != set(names): _fail('invalid_runtime')
    return value


def _text(value, *, empty=False):
    n = utf8_length(value, 'invalid_runtime', maximum=128)
    if (not empty and not n) or any(ord(c)<32 or 127<=ord(c)<160 or c in '/\\' for c in value):
        _fail('invalid_runtime')
    return value


def _relative(value, code='invalid_runtime'):
    n = utf8_length(value, code, maximum=RELATIVE_PATH_BYTES_LIMIT)
    if not n or '\\' in value or any(ord(c)<32 or 127<=ord(c)<160 for c in value) or any(c in ('','.','..') for c in value.split('/')):
        _fail(code)
    return n


def _digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        _fail('invalid_runtime')


def _count(value, maximum, minimum=0):
    exact_int(value, 'invalid_runtime', minimum=minimum)
    if value > maximum:
        _fail('invalid_runtime')
    return value


def _artifact(value):
    _fields(value, ('sha256','size_bytes'))
    _digest(value['sha256'])
    return _count(value['size_bytes'], FILE_BYTES_LIMIT, 1)


def _summary(value, minimum=1):
    _fields(value, ('sha256','file_count','size_bytes'))
    _digest(value['sha256'])
    count = _count(value['file_count'], INVENTORY_FILES_LIMIT, minimum)
    size = _count(value['size_bytes'], min(BINDING_BYTES_LIMIT,count*FILE_BYTES_LIMIT))
    return count,size


def _resources(value, suffix):
    _mapping(value, RESOURCE_FILES_LIMIT, 1)
    for name,digest in value.items():
        _relative(name)
        if not name.endswith(suffix):
            _fail('invalid_runtime')
        _digest(digest)


def validate_runtime(value):
    """Validate public primitives before freezing; perform no runtime discovery."""
    _fields(value, ('binding_version','python','dependencies','replicatetable','resources','pint'))
    if type(value['binding_version']) is not int or value['binding_version'] != BINDING_VERSION:
        _fail('invalid_runtime')
    py = _fields(value['python'], ('implementation','version','build','compiler','abi','executable','core_libraries','stdlib_code'))
    if type(py['implementation']) is not str or py['implementation'] != 'cpython':
        _fail('invalid_runtime')
    _text(py['version'])
    if re.fullmatch(r'3\.(12|13)\.[0-9]+',py['version']) is None:
        _fail('invalid_runtime')
    if type(py['build']) not in (tuple,list) or len(py['build']) != 2:
        _fail('invalid_runtime')
    for part in py['build']: _text(part)
    _text(py['compiler'])
    abi = _fields(py['abi'], ('cache_tag','soabi','abiflags','multiarch','platform','machine','pointer_bits','byteorder','debug','gil_disabled','optimization'))
    minor = py['version'].split('.')[1]
    expected = {'cache_tag':f'cpython-3{minor}','soabi':f'cpython-3{minor}-x86_64-linux-gnu','abiflags':'',
                'multiarch':'x86_64-linux-gnu','platform':'linux','machine':'x86_64','byteorder':'little'}
    for key,wanted in expected.items():
        _text(abi[key],empty=key=='abiflags')
        if abi[key] != wanted: _fail('invalid_runtime')
    if type(abi['pointer_bits']) is not int or abi['pointer_bits'] != 64:
        _fail('invalid_runtime')
    for key in ('debug','gil_disabled'):
        if type(abi[key]) is not bool or abi[key]: _fail('invalid_runtime')
    _count(abi['optimization'],2)
    total_bytes = _artifact(py['executable']); total_files = 1
    core = py['core_libraries']
    _mapping(core, CORE_LIBRARIES_LIMIT)
    for name,artifact in core.items():
        _relative(name)
        if '/' in name or not name.startswith('libpython') or not (name.endswith('.so') or '.so.' in name):
            _fail('invalid_runtime')
        total_bytes += _artifact(artifact); total_files += 1
    n,size = _summary(py['stdlib_code']); total_files += n; total_bytes += size
    deps = _fields(value['dependencies'], PROFILE)
    for name,(version,_,_) in PROFILE.items():
        dep = _fields(deps[name], ('version','payload','metadata'))
        _text(dep['version'])
        if dep['version'] != version: _fail('invalid_runtime')
        for field,minimum in (('payload',1),('metadata',2)):
            n,size = _summary(dep[field],minimum); total_files += n; total_bytes += size
    _text(value['replicatetable'])
    _resources(value['resources'],'.py'); total_files += len(value['resources'])
    pint = _fields(value['pint'], ('registry','default_unit_file','resources'))
    if type(pint['registry']) is not str or pint['registry']!='stock' or type(pint['default_unit_file']) is not str or pint['default_unit_file']!='default_en.txt':
        _fail('invalid_runtime')
    _resources(pint['resources'],'.txt'); total_files += len(pint['resources'])
    if not {'default_en.txt','constants_en.txt'} <= pint['resources'].keys(): _fail('invalid_runtime')
    _count(total_files,BINDING_FILES_LIMIT); _count(total_bytes,BINDING_BYTES_LIMIT)
    preflight_json(value, limit=1024*1024, code='metadata_bytes_limit')
    return freeze(value, code='invalid_runtime')

# Only relative strings are retained while discovering an inventory. File bytes
# and canonical entries are streamed; no RECORD or full inventory map is built.
import hashlib
import json
import os
import stat


class _ScanBudget:
    def __init__(self):
        self.files = 0
        self.directories = 0
        self.bytes = 0
        self.buffer = bytearray(HASH_BUFFER_BYTES)

    def file(self):
        if self.files >= BINDING_FILES_LIMIT: _fail('runtime_identity_limit')
        self.files += 1

    def directory(self):
        if self.directories >= BINDING_DIRECTORIES_LIMIT: _fail('runtime_identity_limit')
        self.directories += 1

    def payload(self, size):
        if size < 0 or size > FILE_BYTES_LIMIT or self.bytes+size > BINDING_BYTES_LIMIT:
            _fail('runtime_identity_limit')
        self.bytes += size


def _stamp(st):
    return st.st_dev,st.st_ino,st.st_mode,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns


def _hash_open_file(stream, size, budget):
    digest = hashlib.sha256(); read = 0
    view = memoryview(budget.buffer)
    while True:
        n = stream.readinto(budget.buffer)
        if not n: break
        read += n
        if read > size: _fail('runtime_changed')
        digest.update(view[:n])
    if read != size: _fail('runtime_changed')
    return {'sha256':digest.hexdigest(),'size_bytes':read}


def _open_parent(root, relative):
    """Anchor components without following links below an already resolved root."""
    fd = os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        parts = relative.split('/')
        for component in parts[:-1]:
            next_fd = os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd); fd = next_fd
        return fd,parts[-1]
    except BaseException:
        os.close(fd)
        raise


def _hash_relative(root, relative, budget):
    parent = None
    try:
        parent,name = _open_parent(root,relative)
        before = os.stat(name,dir_fd=parent,follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode): _fail('runtime_identity_unavailable')
        budget.payload(before.st_size)
        fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
        with os.fdopen(fd,'rb',buffering=0) as stream:
            if _stamp(os.fstat(stream.fileno())) != _stamp(before): _fail('runtime_changed')
            result = _hash_open_file(stream,before.st_size,budget)
            if _stamp(os.fstat(stream.fileno())) != _stamp(before): _fail('runtime_changed')
        if _stamp(os.stat(name,dir_fd=parent,follow_symlinks=False)) != _stamp(before): _fail('runtime_changed')
        return result
    except FileNotFoundError:
        _fail('runtime_changed')
    except OSError:
        _fail('runtime_identity_unavailable')
    finally:
        if parent is not None: os.close(parent)


def _excluded_directory(name, kind):
    return (kind!='metadata' and name=='__pycache__') or (kind=='stdlib' and (name in ('site-packages','dist-packages') or name.startswith('config-')))


def _selected_file(name, kind):
    base = name.rsplit('/',1)[-1]
    if kind!='metadata' and base.endswith(('.pyc','.pyo')): return False
    if kind=='payload': return True
    if kind=='stdlib': return not base.startswith('_sysconfigdata_') and (base.endswith(('.py','.so')) or '.so.' in base)
    if kind=='product': return base.endswith('.py')
    if kind=='pint': return base.endswith('.txt')
    if kind=='metadata':
        return name in ('METADATA','WHEEL','entry_points.txt','top_level.txt') or 'licenses' in name.split('/')[:-1] or base.lower().startswith(('license','notice','copying','copyright'))
    _fail('runtime_identity_unavailable')


@contextmanager
def _directory(root, relative):
    parent=None; fd=None
    try:
        if relative:
            parent,name=_open_parent(root,relative)
            fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
        else:
            fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        before=os.fstat(fd)
        with os.scandir(fd) as entries:
            yield entries
        if _stamp(os.fstat(fd))!=_stamp(before): _fail('runtime_changed')
        after=os.stat(name,dir_fd=parent,follow_symlinks=False) if parent is not None else os.stat(root,follow_symlinks=False)
        if _stamp(after)!=_stamp(before): _fail('runtime_changed')
    finally:
        if fd is not None: os.close(fd)
        if parent is not None: os.close(parent)


def _inventory(root, roots, kind, budget, *, resource_map=False):
    """One bounded inventory; root is a privately resolved installation root."""
    if type(roots) not in (tuple,list) or not 1<=len(roots)<=INVENTORY_DIRECTORIES_LIMIT:
        _fail('runtime_identity_unavailable')
    for i,name in enumerate(roots):
        if name: _relative(name,'runtime_identity_limit')
        for other in roots[:i]:
            if name==other or not name or not other or name.startswith(other+'/') or other.startswith(name+'/'):
                _fail('runtime_identity_unavailable')
    files=[]; queued=[]; retained=0; directories=0

    def retain(name, directory):
        nonlocal retained,directories
        size = _relative(name,'runtime_identity_limit') if name else 0
        if retained+size > RETAINED_PATH_BYTES_LIMIT: _fail('runtime_identity_limit')
        if directory:
            if directories >= INVENTORY_DIRECTORIES_LIMIT: _fail('runtime_identity_limit')
            budget.directory(); directories += 1; queued.append(name)
        else:
            if len(files) >= INVENTORY_FILES_LIMIT or (resource_map and len(files)>=RESOURCE_FILES_LIMIT):
                _fail('runtime_identity_limit')
            budget.file(); files.append(name)
        retained += size

    try:
        for name in roots:
            # Checking every component also rejects a symlink used as a root.
            if name:
                parent,base = _open_parent(root,name)
                try: st = os.stat(base,dir_fd=parent,follow_symlinks=False)
                finally: os.close(parent)
            else: st = os.stat(root,follow_symlinks=False)
            if stat.S_ISDIR(st.st_mode): retain(name,True)
            elif stat.S_ISREG(st.st_mode):
                if _selected_file(name,kind): retain(name,False)
            else: _fail('runtime_identity_unavailable')
        while queued:
            directory = queued.pop()
            retained -= utf8_length(directory)
            # One iterator is consumed and closed before another directory.
            with _directory(root,directory) as entries:
                for entry in entries:
                    # The explicit sysconfig basename exception also covers its
                    # installer-generated link. Other links/special entries
                    # refuse before any directory or regular-file exclusion.
                    if kind=='stdlib' and entry.name.startswith('_sysconfigdata_'): continue
                    name = directory+'/'+entry.name if directory else entry.name
                    if entry.is_symlink(): _fail('runtime_identity_unavailable')
                    if entry.is_dir(follow_symlinks=False):
                        if not _excluded_directory(entry.name,kind): retain(name,True)
                    elif entry.is_file(follow_symlinks=False):
                        if _selected_file(name,kind): retain(name,False)
                    else: _fail('runtime_identity_unavailable')
    except FileNotFoundError:
        _fail('runtime_artifact_missing')
    except OSError:
        _fail('runtime_identity_unavailable')
    files.sort()
    inventory_hash=hashlib.sha256(); inventory_hash.update(b'{'); total=0
    resources={} if resource_map else None
    previous=None
    for name in files:
        if name==previous: _fail('runtime_identity_unavailable')
        if previous is not None: inventory_hash.update(b',')
        artifact=_hash_relative(root,name,budget)
        # One tiny framed entry, exactly the canonical whole-map representation.
        inventory_hash.update(json.dumps(name,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
        inventory_hash.update(b':')
        inventory_hash.update(json.dumps(artifact,sort_keys=True,separators=(',',':')).encode('ascii'))
        total += artifact['size_bytes']
        if resource_map: resources[name]=artifact['sha256']
        previous=name
    inventory_hash.update(b'}\n')
    if resource_map: return resources
    return {'sha256':inventory_hash.hexdigest(),'file_count':len(files),'size_bytes':total}

import importlib
import platform
import struct
import sys
import sysconfig
import threading

_METADATA_HEADER_BYTES_LIMIT = 128 * 1024
_METADATA_LINE_BYTES_LIMIT = 4096
_DISCOVERY_LINE_BYTES_LIMIT = 8192
_PROCESS_BINDING = None
_PROCESS_CHANGED = False
_PROCESS_LOCK = threading.RLock()


def _normal_name(name):
    return re.sub(r'[-_.]+','-',name).lower()


def _metadata_identity(root):
    """Read only bounded headers, without email/RECORD object materialization."""
    found={}; consumed=0; parent=None
    try:
        parent,name=_open_parent(root,'METADATA')
        # Nonblocking acquisition is necessary before fstat: a stable FIFO
        # with no writer must refuse here rather than block in open().
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(fd,'rb',buffering=0) as stream:
            before=os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode): _fail('runtime_identity_unavailable')
            while True:
                line=stream.readline(_METADATA_LINE_BYTES_LIMIT+1)
                consumed += len(line)
                if len(line)>_METADATA_LINE_BYTES_LIMIT or consumed>_METADATA_HEADER_BYTES_LIMIT:
                    _fail('runtime_identity_limit')
                if line in (b'\n',b'\r\n',b''): break
                for field in (b'Name:',b'Version:'):
                    if line.startswith(field):
                        if field in found: _fail('runtime_identity_unavailable')
                        start=len(field); end=len(line)
                        while start<end and line[start] in b' \t\r\n': start+=1
                        while end>start and line[end-1] in b' \t\r\n': end-=1
                        if not 1<=end-start<=128: _fail('runtime_identity_unavailable')
                        try:
                            value=line[start:end].decode('ascii')
                            _text(value)
                        except (UnicodeError,Refusal): _fail('runtime_identity_unavailable')
                        found[field]=value
            if _stamp(os.fstat(stream.fileno()))!=_stamp(before): _fail('runtime_changed')
            if _stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))!=_stamp(before): _fail('runtime_changed')
    except FileNotFoundError: _fail('runtime_artifact_missing')
    except OSError: _fail('runtime_identity_unavailable')
    finally:
        if parent is not None: os.close(parent)
    if set(found)!={b'Name:',b'Version:'}: _fail('runtime_identity_unavailable')
    for value in found.values():
        try: _text(value)
        except Refusal: _fail('runtime_identity_unavailable')
    return _normal_name(found[b'Name:']),found[b'Version:']


def _distribution_roots(root,budget):
    # Fixed 15-entry descriptors only; never importlib.metadata's unbounded
    # directory cache or Distribution.files (which materializes RECORD).
    found={}; budget.directory()
    try:
        with _directory(root,'') as entries:
            for entry in entries:
                if not entry.name.endswith('.dist-info'): continue
                stem=entry.name[:-10]
                if '-' not in stem: continue
                name,version=stem.rsplit('-',1); name=_normal_name(name)
                if name not in PROFILE: continue
                _relative(entry.name,'runtime_identity_limit')
                if entry.is_symlink() or not entry.is_dir(follow_symlinks=False): _fail('runtime_identity_unavailable',name)
                if name in found: _fail('runtime_identity_unavailable',name)
                if version!=PROFILE[name][0]: _fail('runtime_dependency_mismatch',name)
                found[name]=entry.name
    except OSError: _fail('runtime_identity_unavailable')
    if set(found)!=set(PROFILE): _fail('runtime_dependency_missing')
    return found


def _package_locations(module, spec, directory, component):
    """Every loaded package has one exact, matching, qualified search root."""
    locations = spec.submodule_search_locations
    actual = getattr(module, '__path__', None)
    if locations is None and actual is None: return
    # six.py deliberately exposes an empty synthetic package path. Only this
    # actual bound stock owner, with its ordinary source loader, qualifies.
    if (component == 'six' and module is sys.modules.get('six') and spec.name == 'six' and
            type(spec.loader) is importlib.machinery.SourceFileLoader and
            spec.loader.name == 'six' and spec.loader.path == spec.origin and
            type(locations) is list and not locations and type(actual) is list and not actual):
        return
    for paths in (locations, actual):
        if type(paths) not in (list, tuple) or len(paths) != 1 or type(paths[0]) is not str:
            _fail('runtime_import_origin_mismatch', component)
        if os.path.abspath(paths[0]) != directory or os.path.realpath(paths[0]) != directory:
            _fail('runtime_import_origin_mismatch', component)


def _file_origin(module, root, kind, component, *, expected=None):
    """Present ordinary membership under exactly the inventory's selectors.

    No retained inventory set or code-memory claim: under the required quiescent
    installation, anchored entry qualification and the identical selector prove
    that the following fresh inventory includes this loaded file. No byte read
    or new file occurrence is charged for this descriptor-only origin check.
    """
    from types import ModuleType
    if type(module) is not ModuleType: _fail('runtime_import_origin_mismatch', component)
    spec = getattr(module, '__spec__', None)
    if type(spec) is not importlib.machinery.ModuleSpec:
        _fail('runtime_import_origin_mismatch', component)
    origin = spec.origin; file = getattr(module, '__file__', None)
    if type(origin) is not str or type(file) is not str or origin != file or not os.path.isabs(file):
        _fail('runtime_import_origin_mismatch', component)
    absolute = os.path.abspath(file)
    if not absolute.startswith(root + os.sep) or os.path.realpath(file) != absolute:
        _fail('runtime_import_origin_mismatch', component)
    if expected is not None and absolute != expected:
        _fail('runtime_import_origin_mismatch', component)
    relative = os.path.relpath(absolute, root)
    _relative(relative, 'runtime_import_origin_mismatch')
    components = relative.split('/')
    # _sysconfigdata_* is explicitly out of the byte-bound stdlib scope, but
    # when loaded its origin must still be an ordinary anchored source file.
    sysconfig_source = kind == 'stdlib' and components[-1].startswith('_sysconfigdata_') and relative.endswith('.py')
    if kind == 'payload' and not (relative.endswith(('.py', '.so')) or '.so.' in components[-1]):
        _fail('runtime_import_origin_mismatch', component)
    if not (_selected_file(relative, kind) or sysconfig_source):
        _fail('runtime_import_origin_mismatch', component)
    if any(_excluded_directory(part, kind) or
           (kind == 'stdlib' and part.startswith('_sysconfigdata_')) for part in components[:-1]):
        _fail('runtime_import_origin_mismatch', component)
    parent = None; fd = None
    try:
        parent, name = _open_parent(root, relative)
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode): _fail('runtime_import_origin_mismatch', component)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        if _stamp(os.fstat(fd)) != _stamp(before): _fail('runtime_import_origin_mismatch', component)
    except OSError:
        _fail('runtime_import_origin_mismatch', component)
    finally:
        if fd is not None: os.close(fd)
        if parent is not None: os.close(parent)
    _package_locations(module, spec, os.path.dirname(absolute), component)
    return absolute


def _verify_module(module_name, root):
    """Verify actual top-level and all relevant already-loaded module origins."""
    module = sys.modules.get(module_name)
    if module is None: _fail('runtime_import_origin_mismatch', module_name)
    single = os.path.isfile(root)
    base = os.path.dirname(root) if single else root
    expected = root if single else os.path.join(root, '__init__.py')
    kind = 'product' if module_name == 'replicatetable' else 'payload'
    _file_origin(module, base, kind, module_name, expected=expected)
    for name, loaded in sys.modules.items():
        if name != module_name and not name.startswith(module_name + '.'): continue
        if loaded is None or loaded is module: continue
        spec = getattr(loaded, '__spec__', None)
        origin = getattr(spec, 'origin', None); file = getattr(loaded, '__file__', None)
        # The actual stock six.moves object and exact loader are the sole
        # synthetic dependency exception, never its arbitrary namespace prefix.
        if (module_name == 'six' and name == 'six.moves' and
                loaded is getattr(module, 'moves', None) and
                type(getattr(loaded, '__loader__', None)) is getattr(module, '_SixMetaPathImporter', None) and
                type(spec) is importlib.machinery.ModuleSpec and
                spec.loader is loaded.__loader__ and origin is None and file is None):
            continue
        _file_origin(loaded, base, kind, module_name, expected=root if single else None)


def _stock_interpreter_module(name, module):
    """Finite stock builtin/frozen qualification, not declared-origin trust."""
    import _imp
    from types import ModuleType
    from importlib.machinery import BuiltinImporter, FrozenImporter, ModuleSpec
    if type(module) is not ModuleType: return False
    spec = getattr(module, '__spec__', None)
    if type(spec) is not ModuleSpec or type(spec.name) is not str: return False
    # Exact stock aliases differ from their interpreter-registered names.
    # Each alias must still be the same object as that registered owner.
    aliases = {'os.path': 'posixpath', 'collections.abc': '_collections_abc',
               'importlib._bootstrap': '_frozen_importlib',
               'importlib._bootstrap_external': '_frozen_importlib_external'}
    if spec.name != name and (aliases.get(name) != spec.name or sys.modules.get(spec.name) is not module):
        return False
    if spec.origin == 'built-in':
        return (spec.name in sys.builtin_module_names and bool(_imp.is_builtin(spec.name)) and
                spec.loader is BuiltinImporter and getattr(module, '__loader__', None) is BuiltinImporter and
                getattr(module, '__file__', None) is None)
    if spec.origin == 'frozen':
        return (bool(_imp.is_frozen(spec.name)) and spec.loader is FrozenImporter and
                getattr(module, '__loader__', None) is FrozenImporter)
    return False


def _verify_stdlib(root):
    import typing
    # These two stock deprecated aliases are supplied by an ordinary bound
    # typing.py owner; a merely frozen-labelled owner never qualifies.
    _file_origin(typing, root, 'stdlib', 'stdlib', expected=os.path.join(root, 'typing.py'))
    for name, module in sys.modules.items():
        if module is None or name.split('.')[0] not in sys.stdlib_module_names:
            continue
        if (name in ('typing.io', 'typing.re') and
                module is getattr(typing, name.split('.')[1], None) and
                type(module) is getattr(typing, '_DeprecatedType', None)):
            continue
        if _stock_interpreter_module(name, module): continue
        _file_origin(module, root, 'stdlib', 'stdlib')


def _python_description():
    return {'implementation':sys.implementation.name,'version':platform.python_version(),
            'build':list(platform.python_build()),'compiler':platform.python_compiler(),
            'abi':{'cache_tag':sys.implementation.cache_tag,'soabi':sysconfig.get_config_var('SOABI'),
                'abiflags':sys.abiflags,'multiarch':sysconfig.get_config_var('MULTIARCH'),
                'platform':sys.platform,'machine':platform.machine(),'pointer_bits':struct.calcsize('P')*8,
                'byteorder':sys.byteorder,'debug':bool(sysconfig.get_config_var('Py_DEBUG')),
                'gil_disabled':bool(sysconfig.get_config_var('Py_GIL_DISABLED')),'optimization':sys.flags.optimize}}


def _executable(budget):
    try:
        with open('/proc/self/exe','rb',buffering=0) as stream:
            before=os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode): _fail('runtime_identity_unavailable','executable')
            budget.file(); budget.payload(before.st_size)
            result=_hash_open_file(stream,before.st_size,budget)
            if _stamp(os.fstat(stream.fileno()))!=_stamp(before) or _stamp(os.stat('/proc/self/exe'))!=_stamp(before):
                _fail('runtime_changed','executable')
            return result
    except OSError: _fail('runtime_identity_unavailable','executable')


def _core_libraries(budget):
    images={}; consumed=0
    try:
        with open('/proc/self/maps','rb',buffering=0) as stream:
            while True:
                line=stream.readline(_DISCOVERY_LINE_BYTES_LIMIT+1)
                if not line: break
                consumed+=len(line)
                if len(line)>_DISCOVERY_LINE_BYTES_LIMIT or consumed>1024*1024: _fail('runtime_identity_limit','core_libraries')
                fields=line.rstrip(b'\n').split(None,5)
                if len(fields)!=6: continue
                path=os.fsdecode(fields[5]); name=os.path.basename(path)
                if not name.startswith('libpython'): continue
                if not path.startswith('/') or not (name.endswith('.so') or '.so.' in name) or '\\' in path:
                    _fail('runtime_identity_unavailable','core_libraries')
                _relative(name,'runtime_identity_limit')
                dev=tuple(int(v,16) for v in fields[3].split(b':')); inode=int(fields[4])
                identity=(dev,inode)
                if name in images:
                    if images[name][0]!=identity: _fail('runtime_identity_unavailable','core_libraries')
                    continue
                # Alias-mapped images have no unique logical basename in this
                # alpha profile. Do not charge twice or guess a canonical alias.
                if any(image[0]==identity for image in images.values()):
                    _fail('runtime_identity_unavailable','core_libraries')
                if len(images)>=CORE_LIBRARIES_LIMIT: _fail('runtime_identity_limit','core_libraries')
                st=os.stat(path,follow_symlinks=False)
                if not stat.S_ISREG(st.st_mode) or ((os.major(st.st_dev),os.minor(st.st_dev)),st.st_ino)!=identity:
                    _fail('runtime_identity_unavailable','core_libraries')
                images[name]=(identity,path,_stamp(st))
        result={}
        for name in sorted(images):
            identity,path,stamp=images[name]
            budget.file()
            result[name]=_hash_relative(os.path.realpath(os.path.dirname(path)),name,budget)
            if _stamp(os.stat(path,follow_symlinks=False))!=stamp: _fail('runtime_changed','core_libraries')
        return result
    except Refusal: raise
    except (OSError,ValueError): _fail('runtime_identity_unavailable','core_libraries')


def _discover_runtime():
    from . import __version__
    if sys.platform!='linux' or sys.implementation.name!='cpython': _fail('runtime_identity_unavailable','python')
    budget=_ScanBudget()
    root=os.path.realpath(sysconfig.get_path('purelib'))
    if root!=os.path.realpath(sysconfig.get_path('platlib')): _fail('runtime_identity_unavailable','dependencies')
    distributions=_distribution_roots(root,budget)
    # Import before the first fingerprint; qualification requires pristine
    # startup. Hashes cannot retroactively prove already-loaded memory identity.
    for name,(_,module_name,_) in PROFILE.items():
        try: importlib.import_module(module_name)
        except ImportError: _fail('runtime_dependency_missing',name)
    for _,module_name,roots in PROFILE.values():
        _verify_module(module_name,os.path.join(root,roots[0]))
    product=os.path.realpath(os.path.dirname(__file__))
    _verify_module('replicatetable',product)
    stdlib=os.path.realpath(sysconfig.get_path('stdlib'))
    # os may be frozen; the actual source location still identifies the supported
    # single unzipped standard library. _io is expected to be built in.
    if os.path.realpath(os.path.dirname(os.__file__))!=stdlib:
        _fail('runtime_import_origin_mismatch','stdlib')
    _verify_stdlib(stdlib)
    py=_python_description()
    py['executable']=_executable(budget)
    py['core_libraries']=_core_libraries(budget)
    py['stdlib_code']=_inventory(stdlib,('',),'stdlib',budget)
    dependencies={}
    for name,(version,_,roots) in sorted(PROFILE.items()):
        metadata_root=os.path.join(root,distributions[name])
        actual_name,actual_version=_metadata_identity(metadata_root)
        if actual_name!=name or actual_version!=version: _fail('runtime_dependency_mismatch',name)
        for required in ('METADATA','WHEEL'):
            if not os.path.isfile(os.path.join(metadata_root,required)): _fail('runtime_artifact_missing',name)
        payload=_inventory(root,roots,'payload',budget)
        metadata=_inventory(metadata_root,('',),'metadata',budget)
        dependencies[name]={'version':version,'payload':payload,'metadata':metadata}
    resources=_inventory(product,('',),'product',budget,resource_map=True)
    pint_resources=_inventory(os.path.join(root,'pint'),('',),'pint',budget,resource_map=True)
    if not {'default_en.txt','constants_en.txt'}<=pint_resources.keys(): _fail('runtime_artifact_missing','pint')
    result={'binding_version':BINDING_VERSION,'python':py,'dependencies':dependencies,'replicatetable':__version__,
            'resources':resources,'pint':{'registry':'stock','default_unit_file':'default_en.txt','resources':pint_resources}}
    try: return validate_runtime(result)
    except Refusal as exc:
        if exc.code=='invalid_runtime': _fail('runtime_identity_unavailable')
        raise


def runtime_identity():
    """Fresh complete binding; later actual drift permanently requires restart."""
    global _PROCESS_BINDING,_PROCESS_CHANGED
    with _PROCESS_LOCK:
        if _PROCESS_CHANGED: _fail('runtime_changed')
        try: current=validate_runtime(_discover_runtime())
        except Refusal as exc:
            if exc.code=='runtime_changed' or _PROCESS_BINDING is not None:
                _PROCESS_CHANGED=True
            raise
        if _PROCESS_BINDING is None: _PROCESS_BINDING=current
        elif current!=_PROCESS_BINDING:
            _PROCESS_CHANGED=True
            _fail('runtime_changed')
        return current


def require_runtime(expected):
    """A wrong expected plan never poisons the unchanged current process."""
    expected=validate_runtime(expected)
    actual=runtime_identity()
    if actual!=expected: _fail('runtime_binding_mismatch')
    return actual
