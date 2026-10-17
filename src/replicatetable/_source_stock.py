"""Finite eager storage routes, qualified on the two pinned public profiles.

Only exact ndarray storage is observed here. This is not a generic buffer,
referent, backend, duck-array or caller-heap scanner. No payload is copied.
"""
from dataclasses import dataclass
import math

from .errors import Refusal
from .codec import utf8_length
from . import resources as r
from ._resource_bounds import _count, _checked_add
from ._resource_inputs import _header_charge, _fold_source_charge


@dataclass(frozen=True,slots=True)
class _ArrayOwner:
    terminal_bytes: int
    header_bytes: int
    logical_bytes: int
    def __init_subclass__(cls,**kwargs): raise TypeError('Owner facts are final')
    def __post_init__(self):
        for value in (self.terminal_bytes,self.header_bytes,self.logical_bytes):
            _count(value,limit=r.SOURCE_MEMORY_BASE_LIMIT)


def _dtype_kind(dtype, *, terminal=False):
    import numpy as np
    names=('bool','int8','int16','int32','int64','uint8','uint16','uint32','uint64',
           'float32','float64','complex64','complex128','U1','S1','V1','M8[ns]','m8[ns]','object')
    if terminal: names+=('float16','longdouble','clongdouble')
    classes=tuple(type(np.dtype(name)) for name in names)
    if type(dtype) not in classes:
        raise Refusal('unsupported_source_storage')
    if dtype.metadata is not None or dtype.fields is not None or dtype.subdtype is not None:
        raise Refusal('unsupported_source_storage')
    if not terminal and not dtype.isnative:
        raise Refusal('unsupported_source_storage')
    return dtype.kind


def _owner_chain_next(seen,identity):
    """Bounded identity-only chain guard; no storage authority or callbacks.

    A test may exercise 32/depth33/cycle arithmetic through this metadata-only
    seam. Actual observation always supplies id() from an exact ndarray.
    """
    if type(seen) is not tuple or len(seen)>r.OWNER_CHAIN_LIMIT or type(identity) is not int:
        raise Refusal('unsupported_source_storage')
    for old in seen:
        if type(old) is not int: raise Refusal('unsupported_source_storage')
    if len(seen)>=r.OWNER_CHAIN_LIMIT or identity in seen:
        raise Refusal('unsupported_source_storage')
    return seen+(identity,)


def _array_owner(array, *, object_coordinate=False, metadata=False):
    """Return only whole-owner/header/logical byte counts after a safe scan.

    object_coordinate permits the coordinate storage family, with immediate
    ownership mandatory for object strings/sentinels. metadata permits only the
    contract's small rank-one numeric/bool/Unicode vectors, including U0.
    """
    import numpy as np
    if type(object_coordinate) is not bool or type(metadata) is not bool:
        raise Refusal('unsupported_source_storage')
    if type(array) is not np.ndarray or (object_coordinate and metadata):
        raise Refusal('unsupported_source_storage')
    kind=_dtype_kind(array.dtype)
    if not array.flags.c_contiguous or array.ndim>r.RANK_LIMIT:
        raise Refusal('unsupported_source_storage')
    if metadata:
        if array.ndim!=1 or kind not in 'biufU':
            raise Refusal('unsupported_source_storage')
        if array.size>r.METADATA_SEQUENCE_LIMIT: raise Refusal('metadata_bytes_limit')
    elif object_coordinate:
        if array.ndim!=1 or kind not in 'iufUSO': raise Refusal('unsupported_source_storage')
    elif kind not in 'iuf':
        raise Refusal('unsupported_source_storage')
    if kind in 'iu' and array.dtype.itemsize not in (1,2,4,8): raise Refusal('unsupported_source_storage')
    if kind=='f' and array.dtype.itemsize not in (4,8): raise Refusal('unsupported_source_storage')
    if not metadata:
        if array.size<1 or array.size>r.SHAPE_PRODUCT_LIMIT:
            raise Refusal('invalid_source')
        for length in array.shape:
            if not 1<=length<=r.DIMENSION_LENGTH_LIMIT: raise Refusal('invalid_source')
    if object_coordinate and kind in 'US':
        width=array.dtype.itemsize//(4 if kind=='U' else 1)
        if not 1<=width<=4096: raise Refusal('invalid_coordinate')
    if kind=='O' and (array.base is not None or not array.flags.owndata):
        raise Refusal('unsupported_source_storage')
    logical=_count(array.nbytes,'source_bytes_limit',limit=r.SOURCE_MEMORY_BASE_LIMIT)
    current=array;seen=();headers=0
    while True:
        if type(current) is not np.ndarray: raise Refusal('unsupported_source_storage')
        seen=_owner_chain_next(seen,id(current))
        node_kind=_dtype_kind(current.dtype,terminal=True)
        if node_kind=='O' and not (current is array and kind=='O' and object_coordinate):
            raise Refusal('unsupported_source_storage')
        if current.ndim>r.RANK_LIMIT: raise Refusal('unsupported_source_storage')
        size=_count(current.nbytes,'source_bytes_limit',limit=r.SOURCE_MEMORY_BASE_LIMIT)
        owns=current.flags.owndata
        header=np.ndarray.__sizeof__(current)-(size if owns else 0)
        headers=_fold_source_charge(headers,_header_charge(current.ndim,header))
        base=current.base
        if base is None:
            if not owns or not (current.flags.c_contiguous or current.flags.f_contiguous):
                raise Refusal('unsupported_source_storage')
            terminal=size
            break
        if type(base) is bytes:
            terminal=_fold_source_charge(len(base),128)
            break
        if type(base) is not np.ndarray:
            raise Refusal('unsupported_source_storage')
        current=base
    _fold_source_charge(terminal,headers)
    if kind=='O':
        for value in array.flat:
            value_kind=type(value)
            if value_kind is str:
                if str.__len__(value)>r.LABEL_UTF8_BYTES_LIMIT:
                    raise Refusal('label_bytes_limit')
                length=utf8_length(value,'invalid_coordinate')
                if length>r.LABEL_UTF8_BYTES_LIMIT: raise Refusal('label_bytes_limit')
                charge=128+4*length
            elif value is None or (value_kind is float and not math.isfinite(value)):
                charge=128
            else: raise Refusal('unsupported_source_storage')
            terminal=_fold_source_charge(terminal,charge)
            _fold_source_charge(terminal,headers)
    return _ArrayOwner(terminal,headers,logical)


@dataclass(frozen=True,slots=True)
class _StockFacts:
    stock_headers: int
    cache_bytes: int
    owners: tuple
    def __init_subclass__(cls,**kwargs): raise TypeError('Stock facts are final')


@dataclass(frozen=True,slots=True)
class _StockCursor:
    data: object
    dims: tuple
    shape: tuple
    dtype: str
    attrs: object
    encoding: object
    def __init_subclass__(cls,**kwargs): raise TypeError('Stock cursors are final')


def _stock_slot(cls,name,value):
    """Read only one explicitly named, audited exact-class member slot."""
    try:
        return cls.__dict__[name].__get__(value,type(value))
    except AttributeError:
        raise Refusal('unsupported_source_storage') from None


def _stock_dict(value):
    try:
        result=object.__getattribute__(value,'__dict__')
    except AttributeError:
        raise Refusal('unsupported_source_storage') from None
    if type(result) is not dict: raise Refusal('unsupported_source_storage')
    return result


def _cache_add(total,additional):
    return _checked_add(total,additional,limit=r.LOGICAL_JOURNEY_LIMIT,
                        code='estimated_memory_limit')


def _stock_container(value,*,cache=False):
    """H for an already-qualified finite built-in container, never its children."""
    from ._resource_bounds import _checked_mul
    kind=type(value)
    if kind not in (dict,tuple,list,set): raise Refusal('unsupported_source_storage')
    limit=r.LOGICAL_JOURNEY_LIMIT if cache else r.SOURCE_MEMORY_BASE_LIMIT
    code='estimated_memory_limit' if cache else 'source_bytes_limit'
    fixed=_checked_add(512,_checked_mul(128,len(value),limit=limit,code=code),
                       limit=limit,code=code)
    measured=_checked_add(kind.__sizeof__(value),16,limit=limit,code=code)
    return max(fixed,measured)


def _stock_text(value,*,maximum=r.NAME_BYTES_LIMIT,code='unsupported_source_storage'):
    return 128+4*utf8_length(value,code,maximum=maximum)


def _stock_object(value,members):
    # Only called after an exact finite stock class has been established.
    return max(512+128*members,object.__sizeof__(value)+16)


def _stock_dtype(dtype):
    _dtype_kind(dtype)
    return max(512,object.__sizeof__(dtype)+16)


def _stock_array_layout(array,coordinate):
    """Qualify immediate fields without reading labels or following payloads."""
    import numpy as np
    from ._resource_bounds import _shape_product
    if type(array) is not np.ndarray: raise Refusal('unsupported_source_storage')
    kind=_dtype_kind(array.dtype)
    if not array.flags.c_contiguous or array.ndim>r.RANK_LIMIT:
        raise Refusal('unsupported_source_storage')
    if coordinate:
        if array.ndim!=1 or kind not in 'iufUSO':
            raise Refusal('unsupported_source_storage')
    elif kind not in 'iuf':
        raise Refusal('unsupported_source_storage')
    if kind in 'iu' and array.dtype.itemsize not in (1,2,4,8):
        raise Refusal('unsupported_source_storage')
    if kind=='f' and array.dtype.itemsize not in (4,8):
        raise Refusal('unsupported_source_storage')
    if kind=='O' and (array.base is not None or not array.flags.owndata):
        raise Refusal('unsupported_source_storage')
    if kind in 'US':
        width=array.dtype.itemsize//(4 if kind=='U' else 1)
        if not 1<=width<=4096: raise Refusal('invalid_coordinate')
    _shape_product(array.shape)
    return array.shape,array.dtype.str


def _stock_range_length(value):
    if type(value) is not range: raise Refusal('unsupported_source_storage')
    for scalar in (value.start,value.stop,value.step):
        if type(scalar) is not int or not -(2**63)<=scalar<2**63:
            raise Refusal('unsupported_source_storage')
    # Do not call len() on an as-yet unbounded range (Py_ssize_t overflow).
    if value.step>0:
        length=0 if value.start>=value.stop else 1+(value.stop-1-value.start)//value.step
    else:
        length=0 if value.start<=value.stop else 1+(value.start-1-value.stop)//(-value.step)
    if not 1<=length<=r.DIMENSION_LENGTH_LIMIT: raise Refusal('invalid_source')
    return length


def _stock_refs(refs):
    import weakref
    from pandas._libs.internals import BlockValuesRefs
    if type(refs) is not BlockValuesRefs: raise Refusal('unsupported_source_storage')
    values=_stock_slot(BlockValuesRefs,'referenced_blocks',refs)
    counter=_stock_slot(BlockValuesRefs,'clear_counter',refs)
    if type(values) is not list: raise Refusal('unsupported_source_storage')
    _count(counter,'unsupported_source_storage')
    # Admit retained capacity before entering the existing list. Never ref().
    total=_cache_add(640,_stock_container(values,cache=True))
    for value in values:
        if type(value) is not weakref.ReferenceType:
            raise Refusal('unsupported_source_storage')
        if weakref.ReferenceType.__callback__.__get__(value) is not None:
            raise Refusal('unsupported_source_storage')
        total=_cache_add(total,max(128,object.__sizeof__(value)+16))
    return total


def _stock_mask(mask,shape):
    """The narrower C-only bool/uint8 chain; no scientific 128MiB helper."""
    import numpy as np
    if type(mask) is not np.ndarray: raise Refusal('unsupported_source_storage')
    _dtype_kind(mask.dtype)
    if mask.dtype.str!='|b1' or mask.ndim!=1 or mask.shape!=shape or not mask.flags.c_contiguous:
        raise Refusal('unsupported_source_storage')
    current=mask; seen=(); headers=0
    while True:
        if type(current) is not np.ndarray: raise Refusal('unsupported_source_storage')
        seen=_owner_chain_next(seen,id(current))
        _dtype_kind(current.dtype)
        if current.dtype.str not in ('|b1','|u1') or current.ndim>r.RANK_LIMIT:
            raise Refusal('unsupported_source_storage')
        size=_count(current.nbytes,'estimated_memory_limit',limit=r.LOGICAL_JOURNEY_LIMIT)
        header=np.ndarray.__sizeof__(current)-(size if current.flags.owndata else 0)
        header=max(512+128*current.ndim,
                   _count(header,'estimated_memory_limit',limit=r.LOGICAL_JOURNEY_LIMIT))
        headers=_cache_add(headers,header)
        base=current.base
        if base is None:
            if not current.flags.owndata or not (current.flags.c_contiguous or current.flags.f_contiguous):
                raise Refusal('unsupported_source_storage')
            return _cache_add(headers,size)
        if type(base) is not np.ndarray: raise Refusal('unsupported_source_storage')
        current=base


def _stock_range_cache(array,length):
    import numpy as np
    if type(array) is not np.ndarray: raise Refusal('unsupported_source_storage')
    _dtype_kind(array.dtype)
    if (array.dtype.str!='<i8' or array.ndim!=1 or array.shape!=(length,)
            or not array.flags.c_contiguous or not array.flags.owndata or array.base is not None):
        raise Refusal('unsupported_source_storage')
    size=_count(array.nbytes,'estimated_memory_limit',limit=r.LOGICAL_JOURNEY_LIMIT)
    header=max(640,np.ndarray.__sizeof__(array)-size)
    return _cache_add(size,header)


def _stock_engine(engine,backing):
    import numpy as np
    from pandas._libs import index as engines, hashtable as tables
    if type(backing) is not np.ndarray: raise Refusal('unsupported_source_storage')
    families=(('|i1',engines.Int8Engine,tables.Int8HashTable),
              ('<i2',engines.Int16Engine,tables.Int16HashTable),
              ('<i4',engines.Int32Engine,tables.Int32HashTable),
              ('<i8',engines.Int64Engine,tables.Int64HashTable),
              ('|u1',engines.UInt8Engine,tables.UInt8HashTable),
              ('<u2',engines.UInt16Engine,tables.UInt16HashTable),
              ('<u4',engines.UInt32Engine,tables.UInt32HashTable),
              ('<u8',engines.UInt64Engine,tables.UInt64HashTable),
              ('<f4',engines.Float32Engine,tables.Float32HashTable),
              ('<f8',engines.Float64Engine,tables.Float64HashTable),
              ('|O',engines.ObjectEngine,tables.PyObjectHashTable))
    table=None
    for spelling,engine_class,table_class in families:
        if backing.dtype.str==spelling and type(engine) is engine_class:
            table=table_class
            break
    if table is None: raise Refusal('unsupported_source_storage')
    if _stock_slot(engines.IndexEngine,'values',engine) is not backing:
        raise Refusal('unsupported_source_storage')
    if _stock_slot(engines.IndexEngine,'mask',engine) is not None:
        raise Refusal('unsupported_source_storage')
    mapping=_stock_slot(engines.IndexEngine,'mapping',engine)
    total=_cache_add(512,object.__sizeof__(engine)+16)
    if mapping is not None:
        if type(mapping) is not table: raise Refusal('unsupported_source_storage')
        total=_cache_add(total,object.__sizeof__(mapping)+16)
        total=_cache_add(total,table.sizeof(mapping,deep=False))
    return total


def _stock_index_cache(cache,backing,range_length):
    if type(cache) is not dict or len(cache)>12:
        raise Refusal('unsupported_source_storage')
    flags=('is_unique','is_monotonic_increasing','is_monotonic_decreasing',
           '_is_multi','hasnans','_can_hold_na','_should_fallback_to_positional')
    common=('_engine','dtype','inferred_type','_na_value')+flags
    extra='_isnan' if range_length is None else '_data'
    for key in cache:
        if type(key) is not str or (key not in common and key!=extra):
            raise Refusal('unsupported_source_storage')
    total=_stock_container(cache,cache=True)
    range_charge=0
    engine_backing=backing
    if range_length is not None:
        engine_backing=None
        if '_data' in cache:
            engine_backing=cache['_data']
            range_charge=_stock_range_cache(engine_backing,range_length)
    for key,value in cache.items():
        total=_cache_add(total,_stock_text(key))
        if key=='_engine':
            charge=_stock_engine(value,engine_backing)
        elif key=='_data':
            charge=range_charge
        elif key=='_isnan':
            charge=_stock_mask(value,backing.shape)
        elif key=='dtype':
            charge=_stock_dtype(value)
            expected='<i8' if range_length is not None else backing.dtype.str
            if value.str!=expected: raise Refusal('unsupported_source_storage')
        elif key=='inferred_type':
            charge=_stock_text(value)
        elif key in flags:
            if type(value) is not bool: raise Refusal('unsupported_source_storage')
            charge=128
        else:
            # The one scalar sentinel slot has no semantic authority. Preserve
            # only its finite primitive family, without coercion or callbacks.
            kind=type(value)
            if kind is str:
                charge=_stock_text(value,maximum=r.LABEL_UTF8_BYTES_LIMIT)
            elif value is None or kind in (bool,float):
                charge=128
            elif kind is int and r.JSON_INTEGER_MIN<=value<=r.JSON_INTEGER_MAX:
                charge=128
            else:
                raise Refusal('unsupported_source_storage')
        total=_cache_add(total,charge)
    return total


def _stock_roots(dataset):
    import xarray as xr
    from .model import validate_name
    if type(dataset) is not xr.Dataset: raise Refusal('unsupported_source_storage')
    variables=_stock_slot(xr.Dataset,'_variables',dataset)
    dimensions=_stock_slot(xr.Dataset,'_dims',dataset)
    coordinates=_stock_slot(xr.Dataset,'_coord_names',dataset)
    indexes=_stock_slot(xr.Dataset,'_indexes',dataset)
    # Bound all four containers before examining any of their entries.
    if (type(variables) is not dict or type(dimensions) is not dict
            or type(coordinates) is not set or type(indexes) is not dict):
        raise Refusal('unsupported_source_storage')
    if (len(variables)>r.SOURCE_VARIABLE_LIMIT+r.SOURCE_DIMENSION_LIMIT
            or len(dimensions)>r.SOURCE_DIMENSION_LIMIT
            or len(coordinates)>r.SOURCE_DIMENSION_LIMIT
            or len(indexes)>r.SOURCE_DIMENSION_LIMIT):
        raise Refusal('invalid_source')
    _stock_slot(xr.Dataset,'_attrs',dataset)  # Presence only; metadata has its own pass.
    if _stock_slot(xr.Dataset,'_close',dataset) is not None:
        raise Refusal('unsupported_source_storage')
    encoding=_stock_slot(xr.Dataset,'_encoding',dataset)
    if encoding is not None and (type(encoding) is not dict or len(encoding)!=0):
        raise Refusal('unsupported_source_storage')
    # This exact member read must not fall through Dataset.__getattr__, even
    # when an ordinary data variable happens to be named "_cache".
    try:
        cache=xr.Dataset.__dict__['_cache'].__get__(dataset,xr.Dataset)
    except AttributeError:
        cache_bytes=0
    else:
        if type(cache) is not dict or len(cache)!=0:
            raise Refusal('unsupported_source_storage')
        cache_bytes=_stock_container(cache,cache=True)
    headers=_stock_object(dataset,9)
    headers=_fold_source_charge(headers,128)  # _close=None.
    headers=_fold_source_charge(headers,128 if encoding is None else _stock_container(encoding))
    for container in (variables,dimensions,coordinates,indexes):
        headers=_fold_source_charge(headers,_stock_container(container))
    for name in variables:
        validate_name(name)
        headers=_fold_source_charge(headers,_stock_text(name))
    for name,length in dimensions.items():
        validate_name(name)
        _count(length,'invalid_source',limit=r.DIMENSION_LENGTH_LIMIT)
        if not length: raise Refusal('invalid_source')
        headers=_fold_source_charge(headers,_stock_text(name)+128)
    for name in coordinates:
        validate_name(name)
        if name not in variables: raise Refusal('invalid_source')
        headers=_fold_source_charge(headers,_stock_text(name))
    if len(variables)-len(coordinates)>r.SOURCE_VARIABLE_LIMIT:
        raise Refusal('invalid_source')
    for name in indexes:
        validate_name(name,'unsupported_source_storage')
        if name not in coordinates: raise Refusal('unsupported_source_storage')
        headers=_fold_source_charge(headers,_stock_text(name))
    _fold_source_charge(r.MODEL_FIXED_BYTES,headers)
    return variables,dimensions,coordinates,indexes,headers,cache_bytes


def _stock_index(adapter,name,indexes):
    """One finite index route. Its source objects never escape in the result."""
    import numpy as np
    import pandas as pd
    from xarray.core.indexing import PandasIndexingAdapter
    from xarray.core.indexes import PandasIndex
    adapter_dict=_stock_dict(adapter)
    if len(adapter_dict)!=0: raise Refusal('unsupported_source_storage')
    index=_stock_slot(PandasIndexingAdapter,'array',adapter)
    dtype=_stock_slot(PandasIndexingAdapter,'_dtype',adapter)
    dtype_charge=_stock_dtype(dtype)
    if type(index) not in (pd.Index,pd.RangeIndex):
        raise Refusal('unsupported_source_storage')
    headers=_stock_object(adapter,2)
    headers=_fold_source_charge(headers,_stock_container(adapter_dict))
    headers=_fold_source_charge(headers,dtype_charge)
    wrapper_present=name in indexes
    if wrapper_present:
        wrapper=indexes[name]
        if type(wrapper) is not PandasIndex: raise Refusal('unsupported_source_storage')
        wrapper_dict=_stock_dict(wrapper)
        if len(wrapper_dict)!=0: raise Refusal('unsupported_source_storage')
        wrapper_dtype=_stock_slot(PandasIndex,'coord_dtype',wrapper)
        wrapper_dtype_charge=_stock_dtype(wrapper_dtype)
        wrapper_dim=_stock_slot(PandasIndex,'dim',wrapper)
        if (type(wrapper_dim) is not str or wrapper_dim!=name
                or _stock_slot(PandasIndex,'index',wrapper) is not index
                or wrapper_dtype.str!=dtype.str):
            raise Refusal('unsupported_source_storage')
        headers=_fold_source_charge(headers,_stock_object(wrapper,3))
        headers=_fold_source_charge(headers,_stock_container(wrapper_dict))
        headers=_fold_source_charge(headers,_stock_text(wrapper_dim))
        headers=_fold_source_charge(headers,wrapper_dtype_charge)
    state=_stock_dict(index)
    is_range=type(index) is pd.RangeIndex
    data_key='_range' if is_range else '_data'
    required=(data_key,'_name','_cache','_id','_references')
    if len(state)!=5: raise Refusal('unsupported_source_storage')
    for key in state:
        if type(key) is not str or key not in required:
            raise Refusal('unsupported_source_storage')
    index_name=state['_name']
    name_charge=128 if index_name is None else _stock_text(index_name)
    if type(state['_id']) is not object: raise Refusal('unsupported_source_storage')
    headers=_fold_source_charge(headers,_stock_object(index,5))
    headers=_fold_source_charge(headers,_stock_container(state))
    for key in state:
        headers=_fold_source_charge(headers,_stock_text(key))
    headers=_fold_source_charge(headers,name_charge+128)  # _name and exact _id.
    data=state[data_key]
    if is_range:
        length=_stock_range_length(data)
        if dtype.str!='<i8' or state['_references'] is not None:
            raise Refusal('unsupported_source_storage')
        # range carries three signed64 scalars; no conceptual ndarray exists.
        headers=_fold_source_charge(headers,max(512+128*3,range.__sizeof__(data)+16)+3*128)
        headers=_fold_source_charge(headers,128)  # _references=None.
        shape=(length,); raw_dtype='<i8'
        cache_bytes=_stock_index_cache(state['_cache'],None,length)
    else:
        shape,backing_dtype=_stock_array_layout(data,True)
        if data.dtype.kind not in 'iufO': raise Refusal('unsupported_source_storage')
        if data.dtype.kind=='O':
            if dtype.kind=='U':
                width=dtype.itemsize//4
                if not wrapper_present: raise Refusal('unsupported_source_storage')
                if not 1<=width<=4096: raise Refusal('invalid_coordinate')
                raw_dtype=dtype.str
            elif dtype.kind=='O':
                raw_dtype='|O'
            else:
                raise Refusal('unsupported_source_storage')
        else:
            if dtype.str!=backing_dtype: raise Refusal('unsupported_source_storage')
            raw_dtype=backing_dtype
        headers=_fold_source_charge(headers,_stock_dtype(data.dtype))
        cache_bytes=_stock_refs(state['_references'])
        cache_bytes=_cache_add(cache_bytes,_stock_index_cache(state['_cache'],data,None))
    return data,shape,raw_dtype,headers,cache_bytes


def _stock_local(name,variable,dimensions,coordinates,indexes):
    import numpy as np
    from xarray.core.variable import Variable,IndexVariable
    from xarray.namedarray.core import NamedArray
    from xarray.core.indexing import PandasIndexingAdapter
    from .model import validate_name
    from ._resource_inputs import _names
    if type(variable) not in (Variable,IndexVariable):
        raise Refusal('unsupported_source_storage')
    # These base member slots are distinct retained storage, not aliases of
    # the active Variable members. Stock instances leave them uninitialized.
    for field in ('_attrs','_data','_dims'):
        try:
            NamedArray.__dict__[field].__get__(variable,type(variable))
        except AttributeError:
            pass
        else:
            raise Refusal('unsupported_source_storage')
    dims=_stock_slot(Variable,'_dims',variable)
    attrs=_stock_slot(Variable,'_attrs',variable)
    encoding=_stock_slot(Variable,'_encoding',variable)
    data=_stock_slot(Variable,'_data',variable)
    _names(dims)
    coordinate=name in coordinates
    headers=_stock_object(variable,4)
    headers=_fold_source_charge(headers,_stock_container(dims))
    for dim in dims:
        headers=_fold_source_charge(headers,_stock_text(dim))
    cache_bytes=0
    if type(data) is np.ndarray:
        if name in indexes: raise Refusal('unsupported_source_storage')
        shape,raw_dtype=_stock_array_layout(data,coordinate)
        headers=_fold_source_charge(headers,_stock_dtype(data.dtype))
    elif type(data) is PandasIndexingAdapter and coordinate:
        data,shape,raw_dtype,index_headers,cache_bytes=_stock_index(data,name,indexes)
        headers=_fold_source_charge(headers,index_headers)
    else:
        raise Refusal('unsupported_source_storage')
    if len(dims)!=len(shape): raise Refusal('invalid_source')
    for dim,length in zip(dims,shape):
        if dim not in dimensions or dimensions[dim]!=length:
            raise Refusal('invalid_source')
    if coordinate and (dims!=(name,) or shape!=(dimensions.get(name),)):
        raise Refusal('unsupported_source_storage')
    return _StockCursor(data,dims,shape,raw_dtype,attrs,encoding),headers,cache_bytes


def _stock_scientific(cursor,coordinate):
    if type(cursor.data) is range:
        return 0,0,8*cursor.shape[0]
    owner=_array_owner(cursor.data,object_coordinate=coordinate)
    if coordinate and cursor.data.dtype.kind=='O' and cursor.dtype.startswith('<U'):
        width=int(cursor.dtype[2:])
        for value in cursor.data.flat:
            if type(value) is not str: raise Refusal('unsupported_source_storage')
            if str.__len__(value)>width: raise Refusal('invalid_coordinate')
    return owner.terminal_bytes,owner.header_bytes,owner.logical_bytes


def _stock_owners(variables,dimensions,coordinates,indexes,headers):
    from .codec import OwnedMap
    total=_fold_source_charge(r.MODEL_FIXED_BYTES,headers)
    # The bounded sort contains names only. tuple() below owns the sole final
    # OwnerCharge collection; no descriptor/index/array collection is built.
    for kind in ('coordinate','variable'):
        for name in sorted(variables):
            coordinate=name in coordinates
            if coordinate!=(kind=='coordinate'): continue
            cursor,_,_=_stock_local(name,variables[name],dimensions,coordinates,indexes)
            terminal,array_headers,logical=_stock_scientific(cursor,coordinate)
            total=_fold_source_charge(total,terminal)
            total=_fold_source_charge(total,array_headers)
            del cursor
            yield OwnedMap._from_checked((('header_bytes',array_headers),('kind',kind),
                ('logical_bytes',logical),('name',name),('terminal_bytes',terminal)))


def _stock_prepass(dataset):
    """Finish topology before labels, returning only bounded primitive facts.

    The frozen stock header equation is the sum of: Dataset C(9)/base header;
    four root-container H and their name/count occurrences; _close None;
    root encoding None/H; each Variable C(4)/base header, dims H and names;
    each retained immediate dtype reserve; adapter C(2), empty-dict H and dtype;
    optional PandasIndex C(3), empty-dict H, dimension and dtype; Index C(5),
    instance-dict H, five key occurrences, name and _id; or scalar range C(3),
    its three integers and None references. Every exact-object header uses at
    least 512 and C(member_count), and every dtype at least 512. Raw attrs and
    Variable encoding are excluded for the separate complete metadata pass.
    Dataset cache, Index cache/engines/masks and Index refs belong only to C.
    """
    variables,dimensions,coordinates,indexes,headers,cache_bytes=_stock_roots(dataset)
    for name,variable in variables.items():
        cursor,local_headers,local_cache=_stock_local(name,variable,dimensions,coordinates,indexes)
        headers=_fold_source_charge(headers,local_headers)
        _fold_source_charge(r.MODEL_FIXED_BYTES,headers)
        cache_bytes=_cache_add(cache_bytes,local_cache)
        del cursor
    # Dataset._dims is the exact union of active Variable dimension names.
    # This bounded rescan keeps no parallel dimension/descriptor collection.
    from xarray.core.variable import Variable
    for dim in dimensions:
        found=False
        for variable in variables.values():
            if dim in _stock_slot(Variable,'_dims',variable):
                found=True
                break
        if not found: raise Refusal('invalid_source')
    owners=tuple(_stock_owners(variables,dimensions,coordinates,indexes,headers))
    return _StockFacts(headers,cache_bytes,owners)


def _stock_cursor(dataset,name):
    """Borrow one locally qualified value; never provide admission authority."""
    from .model import validate_name
    validate_name(name)
    variables,dimensions,coordinates,indexes,_,_=_stock_roots(dataset)
    if name not in variables: raise Refusal('invalid_source')
    cursor,_,_=_stock_local(name,variables[name],dimensions,coordinates,indexes)
    _stock_scientific(cursor,name in coordinates)
    return cursor
