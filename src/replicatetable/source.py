"""Exact source selection/phase seams. Storage qualification is separate."""
from dataclasses import dataclass

from .codec import OwnedMap
from .errors import Refusal
from .model import (SourceSnapshot, Recipe, _CoordinateMap, _ArrayMap,
                    MetadataValue, _source_identity_check, validate_name,
                    validate_unit, exact_int, _typed_map_validate, _validate_source_parts, _recipe_stage)
from ._resource_inputs import _owned_map, _fields, _names, _recipe_cost
from .resources import SOURCE_VARIABLE_LIMIT, SOURCE_DIMENSION_LIMIT


def _snapshot_exact(source, *, complete=True):
    if type(source) is not SourceSnapshot: raise Refusal('invalid_source')
    try:
        _source_identity_check(source.identity)
        for field,maximum in (('dimensions',16),('variables',64),('coordinate_descriptors',16)):
            _owned_map(object.__getattribute__(source,field),maximum=maximum)
        if type(source.attributes) is not MetadataValue: raise Refusal('invalid_source')
        object.__getattribute__(source.attributes,'_tagged')
        _typed_map_validate(source.arrays,_ArrayMap,children=False)
        _typed_map_validate(source.coordinates,_CoordinateMap,children=False)
        object.__getattribute__(source,'_handle')
        if complete:
            _validate_source_parts(source.identity,source.dimensions,source.variables,
                source.coordinate_descriptors,source.attributes,source.arrays,source.coordinates)
    except AttributeError:
        raise Refusal('invalid_source') from None
    return source


@dataclass(frozen=True,slots=True)
class _Selection:
    variables: tuple
    dimensions: tuple
    row_dims: tuple
    def __init_subclass__(cls,**kwargs): raise TypeError('Selections are final')
    def __post_init__(self):
        _selection_exact(self)


def _selection_exact(selection):
    if type(selection) is not _Selection: raise Refusal('invalid_source')
    try:
        for names,maximum in ((selection.variables,SOURCE_VARIABLE_LIMIT),
                              (selection.dimensions,SOURCE_DIMENSION_LIMIT)):
            if type(names) is not tuple or len(names)>maximum: raise Refusal('invalid_source')
            for name in names: validate_name(name)
            if any(a>=b for a,b in zip(names,names[1:])): raise Refusal('invalid_source')
        _names(selection.row_dims)
        if any(name not in selection.dimensions for name in selection.row_dims):
            raise Refusal('invalid_source')
    except AttributeError:
        raise Refusal('invalid_source') from None
    return selection


def _select(source,recipe):
    _snapshot_exact(source,complete=False)
    from ._resource_inputs import _inspection_cost
    _inspection_cost(source._projection())
    if type(recipe) is not Recipe: raise Refusal('invalid_recipe')
    try:
        _recipe_exact(recipe)
        _recipe_cost(recipe)
        _names(recipe.row_dims,'invalid_recipe')
        if type(recipe.columns) is not tuple or not 1<=len(recipe.columns)<=32:
            raise Refusal('invalid_recipe')
        names=set()
        for column in recipe.columns:
            _fields(column,('name','source','source_unit','target_unit','broadcast','stages'),'invalid_recipe')
            validate_name(column['source'],'invalid_recipe')
            names.add(column['source'])
            if type(column['stages']) is not tuple or len(column['stages'])>2: raise Refusal('invalid_recipe')
            for stage in column['stages']:
                _owned_map(stage,maximum=7,code='invalid_recipe')
                if 'op' not in stage or type(stage['op']) is not str: raise Refusal('invalid_recipe')
                if stage['op']=='weighted_mean':
                    if 'weights' not in stage: raise Refusal('invalid_recipe')
                    validate_name(stage['weights'],'invalid_recipe')
                    names.add(stage['weights'])
        if len(names)>SOURCE_VARIABLE_LIMIT: raise Refusal('invalid_source')
        dimensions=set(recipe.row_dims)
        for name in sorted(names):
            if name not in source.variables: raise Refusal('invalid_source')
            dims=_names(source.variables[name]['dims'])
            dimensions.update(dims)
        if len(dimensions)>SOURCE_DIMENSION_LIMIT: raise Refusal('invalid_source')
        for name in dimensions:
            if name not in source.dimensions: raise Refusal('invalid_source')
        return _Selection(tuple(sorted(names)),tuple(sorted(dimensions)),recipe.row_dims)
    except AttributeError:
        raise Refusal('invalid_recipe') from None


def _selection_snapshot(source,selection,*,expected=None):
    _snapshot_exact(source,complete=False)
    if expected is not None:
        _source_identity_check(expected)
        if source.identity != expected: raise Refusal('source_fingerprint_mismatch')
    _selection_exact(selection)
    # A private record's exact class is not authority for its source relation.
    # Qualify descriptor children before indexing, without source/runtime IO.
    from ._resource_inputs import _DESCRIPTOR_FIELDS
    dimensions=set(selection.row_dims)
    for name in selection.variables:
        if name not in source.variables: raise Refusal('invalid_source')
        descriptor=source.variables[name]
        _fields(descriptor,_DESCRIPTOR_FIELDS)
        dimensions.update(_names(descriptor['dims']))
    for name in dimensions:
        if name not in source.dimensions: raise Refusal('invalid_source')
    if tuple(sorted(dimensions))!=selection.dimensions: raise Refusal('invalid_source')
    arrays=tuple(source.arrays); coords=tuple(source.coordinates)
    if not ((arrays==() and coords==()) or
            (arrays==() and coords==selection.dimensions) or
            (arrays==selection.variables and coords==selection.dimensions)):
        raise Refusal('invalid_source_phase')
    _snapshot_exact(source)
    return source


def _recipe_exact(recipe):
    """Qualify the owned Recipe in place before equality, hashing or lookup."""
    if type(recipe) is not Recipe: raise Refusal('invalid_recipe')
    try:
        exact_int(recipe.version,'invalid_recipe',minimum=1,maximum=1)
        _names(recipe.row_dims,'invalid_recipe')
        if type(recipe.columns) is not tuple or not 1<=len(recipe.columns)<=32:
            raise Refusal('invalid_recipe')
        column_names=set()
        for column in recipe.columns:
            _fields(column,('name','source','source_unit','target_unit','broadcast','stages'),'invalid_recipe')
            for field in ('name','source'): validate_name(column[field],'invalid_recipe')
            for field in ('source_unit','target_unit'): validate_unit(column[field],'invalid_recipe')
            _names(column['broadcast'],'invalid_recipe')
            if column['name'] in column_names: raise Refusal('invalid_recipe')
            column_names.add(column['name'])
            stages=column['stages']
            if type(stages) is not tuple or len(stages)>2: raise Refusal('invalid_recipe')
            stage_names=set();removed=set()
            for index,stage in enumerate(stages):
                _recipe_stage(stage,index,recipe.row_dims,removed,owned=True)
                if stage['name'] in stage_names: raise Refusal('invalid_recipe')
                stage_names.add(stage['name'])
                removed.update(stage['dims'])
    except AttributeError:
        raise Refusal('invalid_recipe') from None


# Eager-memory source implementation. These helpers borrow only one current
# stock cursor; semantic authority is established afresh for every operation.
import hashlib
import math
import struct
from . import resources as r
from .codec import canonical_bytes, iter_json_chunks, utf8_length
from .model import MetadataValue, SourceIdentity, Coordinate, ArrayBuffer, numeric_dtype
from ._resource_bounds import (_JP,_Fold,_literal_cost,_container_cost,_count,
                               _checked_add,_checked_mul)
from ._resource_inputs import _binding, _fold_source_charge, _owned_cost


@dataclass(frozen=True,slots=True)
class _Prepass:
    stock: object
    metadata: object
    descriptor_cost: _JP
    def __init_subclass__(cls,**kwargs): raise TypeError('Source prepass is final')


@dataclass(frozen=True,slots=True)
class _ScanResult:
    inspection: object
    binding: OwnedMap
    cache_bytes: int
    identity: object
    def __init_subclass__(cls,**kwargs): raise TypeError('Source scan result is final')


def _dataset_members(dataset):
    from ._source_stock import _stock_roots
    return _stock_roots(dataset)[:4]


def _root_attrs(dataset):
    import xarray as xr
    return xr.Dataset.__dict__['_attrs'].__get__(dataset,xr.Dataset)


def _raw_text_pair(value):
    import numpy as np
    if value is None: return _literal_cost(None)
    if type(value) not in (str,np.str_): raise Refusal('invalid_source')
    length=str.__len__(value)
    if length>r.UNIT_BYTES_LIMIT: raise Refusal('invalid_source')
    size=0
    for i in range(length):
        c=ord(str.__getitem__(value,i))
        if 0xD800<=c<=0xDFFF: raise Refusal('invalid_source')
        size+=1 if c<128 else 2 if c<2048 else 3 if c<65536 else 4
        if size>r.UNIT_BYTES_LIMIT: raise Refusal('invalid_source')
    return _JP(6*size+2,128+4*size)


def _raw_unit(attrs):
    if attrs is None: return None
    if type(attrs) is not dict: raise Refusal('unsupported_source_storage')
    return attrs.get('units')


def _raw_declaration_bits(cursor,coordinate):
    from ._source_metadata import _REFERENCE_TIME
    import numpy as np
    bits=0
    for raw in (cursor.attrs,cursor.encoding):
        if raw is None: continue
        if type(raw) is not dict: raise Refusal('unsupported_source_storage')
        for key in raw:
            if type(key) is not str: raise Refusal('invalid_source')
        if coordinate:
            if 'calendar' in raw: bits|=1
            units=raw.get('units')
            if units is not None:
                if type(units) not in (str,np.str_): raise Refusal('invalid_source')
                if _REFERENCE_TIME.fullmatch(units) is not None: bits|=2
        for key,bit in (('scale_factor',4),('add_offset',8),('_Unsigned',16)):
            if key in raw: bits|=bit
        for key,bit in (('_FillValue',32),('missing_value',64)):
            if key not in raw: continue
            value=raw[key]
            if type(value) in (np.float32,np.float64): value=type(value).item(value)
            allowed=cursor.dtype in ('<f4','<f8') and type(value) is float and math.isnan(value)
            if not allowed: bits|=bit
    return bits


def _status_pair(bits,coordinate):
    from ._source_metadata import _REASONS
    if not bits: return _literal_cost(None)
    reasons=_Fold()
    for index,name in enumerate(_REASONS):
        if bits & (1<<index): reasons.add(_literal_cost(name))
    result=_Fold();result.add(_literal_cost('unsupported'),'status')
    result.add(_literal_cost('unsupported_coordinate_encoding' if coordinate else 'unsupported_source_encoding'),'code')
    result.add(reasons.finish(),'reasons')
    return result.finish()


def _descriptor_pair(cursor,coordinate,attributes,encoding):
    result=_Fold()
    result.add(_owned_cost(cursor.dims),'dims');result.add(_owned_cost(cursor.shape),'shape')
    result.add(_literal_cost(cursor.dtype if coordinate else numeric_dtype(cursor.dtype)),'dtype')
    result.add(_raw_text_pair(_raw_unit(cursor.attrs)),'unit')
    result.add(attributes,'attributes');result.add(encoding,'encoding')
    result.add(_status_pair(_raw_declaration_bits(cursor,coordinate),coordinate),'selection_status')
    return result.finish()


def _utf32_metrics(data,index):
    """Bounded codeunit scan, no padded Unicode scalar or normalized prefix."""
    width=data.dtype.itemsize
    view=memoryview(data);octets=None
    try:
        octets=view.cast('B');start=index*width;end=start+width
        while end>start and not (octets[end-4]|octets[end-3]|octets[end-2]|octets[end-1]): end-=4
        count=(end-start)//4;size=0
        for position in range(start,end,4):
            c=(octets[position]|octets[position+1]<<8|octets[position+2]<<16|octets[position+3]<<24)
            if c>0x10FFFF or 0xD800<=c<=0xDFFF: raise Refusal('invalid_coordinate')
            size+=1 if c<128 else 2 if c<2048 else 3 if c<65536 else 4
            if size>r.LABEL_UTF8_BYTES_LIMIT: raise Refusal('label_bytes_limit')
        return size,count
    finally:
        if octets is not None: octets.release()
        view.release()


def _fixed_metrics(data,index):
    """Strict UTF8 qualification of the physical fixed-S scalar before decode."""
    width=data.dtype.itemsize;view=memoryview(data);octets=None
    try:
        octets=view.cast('B');start=index*width;end=start+width
        while end>start and octets[end-1]==0: end-=1
        position=start;count=0
        while position<end:
            lead=octets[position];position+=1
            if lead<128: extra=0;point=lead;minimum=0
            elif 0xC2<=lead<=0xDF: extra=1;point=lead&31;minimum=0x80
            elif 0xE0<=lead<=0xEF: extra=2;point=lead&15;minimum=0x800
            elif 0xF0<=lead<=0xF4: extra=3;point=lead&7;minimum=0x10000
            else: raise Refusal('invalid_coordinate')
            if extra>end-position: raise Refusal('invalid_coordinate')
            for _ in range(extra):
                byte=octets[position];position+=1
                if not 0x80<=byte<=0xBF: raise Refusal('invalid_coordinate')
                point=(point<<6)|(byte&63)
            if point<minimum or point>0x10FFFF or 0xD800<=point<=0xDFFF:
                raise Refusal('invalid_coordinate')
            count+=1
        return end-start,count
    finally:
        if octets is not None: octets.release()
        view.release()


def _raw_coordinates_prepass(dataset):
    from ._source_stock import _stock_cursor
    _,_,coordinates,_=_dataset_members(dataset)
    for name in sorted(coordinates):
        cursor=_stock_cursor(dataset,name)
        if type(cursor.data) is not range:
            kind=cursor.data.dtype.kind
            if kind in 'US':
                for index in range(cursor.shape[0]):
                    if kind=='U': _utf32_metrics(cursor.data,index)
                    else: _fixed_metrics(cursor.data,index)
        del cursor


def _memory_prepass(dataset):
    from ._source_stock import _stock_prepass,_stock_cursor
    from ._source_metadata import _MetadataState,_scan_metadata,_finish_metadata
    stock=_stock_prepass(dataset)
    base=_fold_source_charge(r.MODEL_FIXED_BYTES,stock.stock_headers)
    for owner in stock.owners:
        base=_fold_source_charge(base,owner['terminal_bytes'])
        base=_fold_source_charge(base,owner['header_bytes'])
    state=_MetadataState(base_bytes=base)
    variables,dimensions,coordinates,_=_dataset_members(dataset)
    attrs=_scan_metadata(state,_root_attrs(dataset),context='root')
    data_cost=_Fold();coordinate_cost=_Fold();dimension_cost=_Fold()
    for name,length in dimensions.items(): dimension_cost.add(_literal_cost(length),name)
    for name in sorted(variables):
        cursor=_stock_cursor(dataset,name);coordinate=name in coordinates
        context='coordinate' if coordinate else 'data'
        a=_scan_metadata(state,cursor.attrs,context=context+'_attrs')
        e=_scan_metadata(state,cursor.encoding,context=context+'_encoding')
        pair=_descriptor_pair(cursor,coordinate,a,e)
        (coordinate_cost if coordinate else data_cost).add(pair,name)
        del cursor
    source_cost=_Fold();source_cost.add(_literal_cost('memory'),'kind')
    source_cost.add(_literal_cost('0'*64),'sha256');source_cost.add(_literal_cost(0),'size_bytes')
    result=_Fold();result.add(_literal_cost(2),'version');result.add(source_cost.finish(),'source')
    result.add(dimension_cost.finish(),'dimensions');result.add(data_cost.finish(),'variables')
    result.add(coordinate_cost.finish(),'coordinate_descriptors');result.add(attrs,'attributes')
    pair=result.finish()
    _finish_metadata(state,descriptor_cost=pair)
    _raw_coordinates_prepass(dataset)
    return _Prepass(stock,state,pair)


def _tag_unit(tag):
    for key,value in tag['items']:
        if key=='units':
            if value['type']=='null': return None
            if value['type']!='str': raise Refusal('invalid_source')
            return value['value']
    return None


def _source_descriptor(cursor,coordinate,state):
    from ._source_metadata import _build_metadata,_declaration_status
    context='coordinate' if coordinate else 'data'
    attrs=_build_metadata(state,cursor.attrs,context=context+'_attrs')._tagged
    encoding=_build_metadata(state,cursor.encoding,context=context+'_encoding')._tagged
    status=_declaration_status(attrs,encoding,dtype=cursor.dtype,coordinate=coordinate)
    return OwnedMap._from_checked((('attributes',attrs),('dims',cursor.dims),
        ('dtype',cursor.dtype if coordinate else numeric_dtype(cursor.dtype)),('encoding',encoding),
        ('selection_status',status),('shape',cursor.shape),('unit',_tag_unit(attrs))))


def _build_inspection_parts(dataset,prepass):
    from ._source_stock import _stock_cursor
    from ._source_metadata import _build_metadata
    variables,dimensions,coordinate_names,_=_dataset_members(dataset)
    attrs=_build_metadata(prepass.metadata,_root_attrs(dataset),context='root')
    data=[];coords=[]
    for name in sorted(variables):
        cursor=_stock_cursor(dataset,name);coordinate=name in coordinate_names
        descriptor=_source_descriptor(cursor,coordinate,prepass.metadata)
        (coords if coordinate else data).append((name,descriptor))
        del cursor,descriptor
    return (OwnedMap(dimensions),OwnedMap._from_checked(tuple(data)),
            OwnedMap._from_checked(tuple(coords)),attrs)


def _compare_topology(dataset,source):
    """Compare only safe finite names/counts, never derived declaration status."""
    variables,dimensions,coordinate_names,_=_dataset_members(dataset)
    if tuple(sorted(dimensions))!=tuple(source.dimensions): raise Refusal('source_changed')
    for name,length in dimensions.items():
        if source.dimensions[name]!=length: raise Refusal('source_changed')
    if tuple(sorted(coordinate_names))!=tuple(source.coordinate_descriptors): raise Refusal('source_changed')
    if tuple(sorted(name for name in variables if name not in coordinate_names))!=tuple(source.variables):
        raise Refusal('source_changed')


def _compare_inspection(dataset,prepass,source):
    from ._source_stock import _stock_cursor
    from ._source_metadata import _compare_metadata,_declaration_status
    _compare_topology(dataset,source)
    variables,_,coordinate_names,_=_dataset_members(dataset)
    _compare_metadata(prepass.metadata,_root_attrs(dataset),source.attributes._tagged,context='root')
    for name in sorted(variables):
        cursor=_stock_cursor(dataset,name);coordinate=name in coordinate_names
        descriptor=(source.coordinate_descriptors if coordinate else source.variables)[name]
        dtype=cursor.dtype if coordinate else numeric_dtype(cursor.dtype)
        if descriptor['dims']!=cursor.dims or descriptor['shape']!=cursor.shape or descriptor['dtype']!=dtype:
            raise Refusal('source_changed')
        context='coordinate' if coordinate else 'data'
        _compare_metadata(prepass.metadata,cursor.attrs,descriptor['attributes'],context=context+'_attrs')
        _compare_metadata(prepass.metadata,cursor.encoding,descriptor['encoding'],context=context+'_encoding')
        if _tag_unit(descriptor['attributes'])!=descriptor['unit']: raise Refusal('invalid_source')
        status=_declaration_status(descriptor['attributes'],descriptor['encoding'],dtype=cursor.dtype,coordinate=coordinate)
        if status!=descriptor['selection_status']: raise Refusal('source_changed')
        del cursor,status


def _inspection_without_source(dimensions,variables,coordinates,attributes):
    return OwnedMap._from_checked((('attributes',attributes._tagged),
        ('coordinate_descriptors',coordinates),('dimensions',dimensions),
        ('variables',variables),('version',2)))


def _read_label(cursor,index):
    import numpy as np
    if type(cursor.data) is range: return cursor.data[index]
    value=np.ndarray.item(cursor.data,index)
    if cursor.data.dtype.kind=='S':
        if type(value) is not bytes: raise Refusal('invalid_coordinate')
        try: value=value.rstrip(b'\0').decode('utf-8','strict')
        except UnicodeError: raise Refusal('invalid_coordinate') from None
    if type(value) is str:
        if len(value)>r.LABEL_UTF8_BYTES_LIMIT: raise Refusal('label_bytes_limit')
        if utf8_length(value,'invalid_coordinate')>r.LABEL_UTF8_BYTES_LIMIT:
            raise Refusal('label_bytes_limit')
    return value


def _scalar_metadata_tag(value):
    kind=type(value)
    if value is None: return OwnedMap._from_checked((('type','null'),))
    if kind is str: tag='str'
    elif kind is int: tag='int'
    elif kind is float:
        if math.isfinite(value): tag='float'
        else:
            tag='float_special'
            value='nan' if math.isnan(value) else '+inf' if value>0 else '-inf'
    else: raise Refusal('invalid_coordinate')
    return OwnedMap._from_checked((('type',tag),('value',value)))


def _label_payload(cursor):
    yield b'['
    for index in range(cursor.shape[0]):
        if index: yield b','
        value=_read_label(cursor,index)
        token=_scalar_metadata_tag(value)
        for part in iter_json_chunks(token,limit=r.SERIAL_BUFFER_BYTES):
            # A canonical scalar/tag's only literal LF is its document terminator.
            if part!=b'\n': yield part
    yield b']\n'


def _raw_payload(cursor,coordinate):
    if type(cursor.data) is range:
        for value in cursor.data: yield struct.pack('<q',value)
        return
    if coordinate and cursor.data.dtype.kind in 'UO':
        yield from _label_payload(cursor)
        return
    view=memoryview(cursor.data);octets=None
    try:
        octets=view.cast('B')
        for start in range(0,len(octets),r.SERIAL_BUFFER_BYTES):
            part=octets[start:start+r.SERIAL_BUFFER_BYTES]
            try: yield part
            finally: part.release()
    finally:
        if octets is not None: octets.release()
        view.release()


def _memory_identity(dataset,descriptor):
    from ._source_stock import _stock_cursor
    variables,_,coordinates,_=_dataset_members(dataset)
    digest=hashlib.sha256();size=0
    header=OwnedMap._from_checked((('descriptor',descriptor),('format','replicatetable-memory-source-v2')))
    for part in iter_json_chunks(header,limit=r.METADATA_BYTES_LIMIT):
        size=_checked_add(size,len(part));digest.update(part)
    for kind in ('coordinate','variable'):
        for name in sorted(variables):
            coordinate=name in coordinates
            if coordinate!=(kind=='coordinate'): continue
            cursor=_stock_cursor(dataset,name)
            dtype=cursor.dtype if coordinate else numeric_dtype(cursor.dtype)
            frame=canonical_bytes({'kind':kind,'name':name,'dtype':dtype,'shape':cursor.shape},limit=r.SERIAL_BUFFER_BYTES)
            if type(cursor.data) is range: payload_length=8*cursor.shape[0]
            elif coordinate and cursor.data.dtype.kind in 'UO':
                payload_length=0
                for part in _raw_payload(cursor,coordinate): payload_length=_checked_add(payload_length,len(part))
            else: payload_length=cursor.data.nbytes
            for part in (len(frame).to_bytes(8,'big'),frame,payload_length.to_bytes(8,'big')):
                size=_checked_add(size,len(part));digest.update(part)
            observed=0
            for part in _raw_payload(cursor,coordinate):
                observed=_checked_add(observed,len(part))
                if observed>payload_length: raise Refusal('source_changed')
                size=_checked_add(size,len(part));digest.update(part)
            if observed!=payload_length: raise Refusal('source_changed')
            del cursor,frame
    return SourceIdentity('memory',digest.hexdigest(),size)


def _current_binding(prepass):
    base=_fold_source_charge(prepass.metadata.base_bytes,prepass.metadata.raw_bytes)
    base=_fold_source_charge(base,prepass.descriptor_cost.object_bytes)
    return _binding('memory',base,prepass.stock.owners,prepass.descriptor_cost.object_bytes)


def _api_frame_cost(descriptor,coordinates=None,arrays=None,kind='descriptor'):
    model=descriptor
    if coordinates is not None:
        prepared=_Fold();prepared.add(descriptor,'inspection');prepared.add(coordinates,'coordinates')
        model=prepared.finish()
    frame=_Fold();frame.add(_literal_cost(2),'version');frame.add(_literal_cost(kind),'kind')
    frame.add(model,'model');frame.add(_container_cost(0,0,0) if arrays is None else arrays,'arrays')
    return frame.finish()


def _array_ledger_pair(name,dtype,shape,size,offset):
    item=_Fold();item.add(_literal_cost(name),'name')
    item.add(_literal_cost(dtype),'dtype');item.add(_owned_cost(shape),'shape')
    item.add(_literal_cost(size),'nbytes');item.add(_literal_cost('0'*64),'sha256')
    item.add(_literal_cost(offset),'offset')
    return item.finish()


def _retained_projection(source):
    """Scalar-only costs of the actual qualified caller/return model forest."""
    from ._resource_inputs import _inspection_cost
    descriptor=_inspection_cost(source._projection())
    coordinates=_Fold();arrays=_Fold();numeric=0
    for name,coordinate in source.coordinates.items():
        item=_Fold();item.add(_literal_cost(coordinate.dtype),'dtype')
        # Coordinate tuples follow their own Q bounds, not metadata member
        # limits. Fold labels one at a time and project the integer permutation.
        values=_Fold()
        for value in coordinate.values: values.add(_literal_cost(value))
        item.add(values.finish(),'values')
        length=len(coordinate.sorted_indices)
        item.add(_container_cost(length,32*length,128*length),'sorted_indices')
        coordinates.add(item.finish(),name)
    for name,buffer in source.arrays.items():
        size=len(buffer.data)
        arrays.add(_array_ledger_pair(name,buffer.dtype,buffer.shape,size,numeric))
        numeric=_checked_add(numeric,size,limit=r.SELECTED_NUMERIC_BYTES_LIMIT,code='selected_numeric_bytes_limit')
    return (descriptor,coordinates.finish() if len(source.coordinates) or len(source.arrays) else None,
            arrays.finish() if len(source.arrays) else None,numeric)


def _pair_max(first,second):
    if first is None: return second
    if second is None: return first
    return _JP(max(first.json_bytes,second.json_bytes),max(first.object_bytes,second.object_bytes))


def _standalone_measure(prepass,*,coordinates=None,arrays=None,numeric_bytes=0,
                      kind='descriptor',held=None,returning=None,recipe=None):
    binding=_current_binding(prepass)
    descriptor=prepass.descriptor_cost
    # The finite 3-model/2-array reservation covers the actual caller, the new
    # return and construction state. Maxima choose each full slot's capacity;
    # they do not remove a baseline or infer sharing from object identity.
    for model in (held,returning):
        if model is None: continue
        old_descriptor,old_coordinates,old_arrays,old_numeric=_retained_projection(model)
        descriptor=_pair_max(descriptor,old_descriptor)
        coordinates=_pair_max(coordinates,old_coordinates)
        arrays=_pair_max(arrays,old_arrays)
        numeric_bytes=max(numeric_bytes,old_numeric)
    if arrays is not None: kind='materialized'
    elif coordinates is not None: kind='prepared'
    frame=_api_frame_cost(descriptor,coordinates,arrays,kind)
    _count(numeric_bytes,'selected_numeric_bytes_limit',limit=r.SELECTED_NUMERIC_BYTES_LIMIT)
    recipe_bytes=0
    if recipe is not None:
        _recipe_exact(recipe);recipe_bytes=_recipe_cost(recipe).object_bytes
    # Direct eager worksheet: the source base already pays its source fixed
    # pool. Pay the distinct common model-header pool and three bounded
    # serialization buffers here. The actual raw source, 2A, 3-model frame,
    # Recipe and observed caches coexist. There is no native parent W0 or
    # worker/control decode in this route, so neither native term is borrowed.
    total=(r.RUNTIME_ALLOWANCE+binding['base_bytes']+recipe_bytes+5*(frame.json_bytes+1)+
           3*frame.object_bytes+2*numeric_bytes+r.CONTROL_STATE_BYTES+prepass.stock.cache_bytes+
           r.MODEL_FIXED_BYTES+3*r.SERIAL_BUFFER_BYTES)
    return binding,total


def _standalone_guard(prepass,**arguments):
    binding,total=_standalone_measure(prepass,**arguments)
    from .admission import _guard
    _guard(arguments.get('kind','descriptor'),baseline=total)
    return binding


def _footprint_memory(dataset):
    """Complete raw-owner/metadata scan, with no guard recursion or content proof."""
    prepass=_memory_prepass(dataset)
    return _current_binding(prepass),prepass.stock.cache_bytes


def _selected_declarations(dataset,selection):
    from ._source_stock import _stock_cursor
    _,_,coordinates,_=_dataset_members(dataset)
    order=selection.row_dims+tuple(name for name in selection.dimensions if name not in selection.row_dims)
    for name in order:
        if name not in coordinates:
            raise Refusal('missing_row_key' if name in selection.row_dims else 'missing_coordinate')
        cursor=_stock_cursor(dataset,name)
        if _raw_declaration_bits(cursor,True):
            raise Refusal('unsupported_coordinate_encoding','Selected coordinate encoding declaration is unsupported.')
    for name in selection.variables:
        cursor=_stock_cursor(dataset,name)
        if _raw_declaration_bits(cursor,False):
            raise Refusal('unsupported_source_encoding',
                'Only raw unpacked values and scalar NaN missing declarations on floating storage are supported.')


def _scan_memory(dataset,*,existing=None,selection=None,footprint=False,returning=None,recipe=None):
    from . import runtime
    from .admission import _active_plan,_preflight_required,_guard
    active=_active_plan()
    if active is not None: _preflight_required()
    prepass=_memory_prepass(dataset)
    # A previously present member disappearing is a held-source change, not a
    # fresh missing-coordinate/selection error. Raw safety still runs first;
    # fresh descriptor inspection and selected declaration priority are intact.
    if existing is not None and selection is not None: _compare_topology(dataset,existing)
    if selection is not None: _selected_declarations(dataset,selection)
    coordinates=arrays=None;numeric=0;kind='descriptor'
    if returning is not None and selection is not None:
        coordinates,arrays,numeric=_selected_projection(dataset,selection)
        kind='materialized' if len(returning.arrays) else 'prepared'
        if kind=='prepared': arrays=None
    if active is None:
        binding=_standalone_guard(prepass,held=existing,returning=returning,recipe=recipe,
            coordinates=coordinates,arrays=arrays,numeric_bytes=numeric,kind=kind)
    else:
        # The complete guard owns its fresh scans. Retire this prepass first,
        # including its owner tuple, so no two fresh scan forests coexist.
        del prepass
        runtime.require_runtime(active.runtime)
        _guard('recheck')
        prepass=_memory_prepass(dataset)
        if existing is not None and selection is not None: _compare_topology(dataset,existing)
        if selection is not None: _selected_declarations(dataset,selection)
        binding=_current_binding(prepass)
    if footprint: return _ScanResult(None,binding,prepass.stock.cache_bytes,None)
    runtime.runtime_identity()
    if existing is None:
        dimensions,variables,coordinates,attrs=_build_inspection_parts(dataset,prepass)
    else:
        _compare_inspection(dataset,prepass,existing)
        dimensions,variables,coordinates,attrs=(existing.dimensions,existing.variables,
            existing.coordinate_descriptors,existing.attributes)
    descriptor=_inspection_without_source(dimensions,variables,coordinates,attrs)
    identity=_memory_identity(dataset,descriptor)
    if existing is not None and identity!=existing.identity: raise Refusal('source_changed')
    if existing is None:
        inspection=SourceSnapshot(identity=identity,dimensions=dimensions,variables=variables,
            coordinate_descriptors=coordinates,attributes=attrs,arrays={},coordinates={},_handle=dataset)
    else: inspection=existing
    return _ScanResult(inspection,binding,prepass.stock.cache_bytes,identity)


def _coordinate_order(selection):
    return selection.row_dims+tuple(name for name in selection.dimensions if name not in selection.row_dims)


def _coordinate_measure(cursor,*,row,semantic=True):
    """Scalar-only selected-coordinate bounds before retaining physical labels."""
    length=cursor.shape[0]
    raw=8*length if type(cursor.data) is range else cursor.data.nbytes
    if raw>r.COORDINATE_RAW_BYTES_LIMIT: raise Refusal('coordinate_bytes_limit')
    values=_Fold();raw_values=_Fold();utf8=0;max_chars=0;missing=False;infinite=False
    for index in range(length):
        if type(cursor.data) is not range and cursor.data.dtype.kind in 'US':
            size,chars=(_utf32_metrics(cursor.data,index) if cursor.data.dtype.kind=='U'
                        else _fixed_metrics(cursor.data,index))
            pair=_JP(6*size+2,128+4*size);max_chars=max(max_chars,chars)
            utf8=_checked_add(utf8,size,limit=r.COORDINATE_LABEL_UTF8_BYTES_LIMIT,code='coordinate_bytes_limit')
        else:
            value=_read_label(cursor,index);kind=type(value)
            if kind is str:
                size=utf8_length(value,'invalid_coordinate');max_chars=max(max_chars,len(value))
                if size>r.LABEL_UTF8_BYTES_LIMIT: raise Refusal('label_bytes_limit')
                utf8=_checked_add(utf8,size,limit=r.COORDINATE_LABEL_UTF8_BYTES_LIMIT,code='coordinate_bytes_limit')
                if type(cursor.data) is not range and cursor.data.dtype.kind=='O': raw=_checked_add(raw,size,limit=r.COORDINATE_RAW_BYTES_LIMIT,code='coordinate_bytes_limit')
                pair=_literal_cost(value)
            elif value is None or (kind is float and not math.isfinite(value)):
                missing=missing or value is None or math.isnan(value)
                infinite=infinite or (kind is float and math.isinf(value))
                token=_scalar_metadata_tag(value);pair=_owned_cost(token)
                if cursor.dtype=='|O':
                    size=sum(len(part) for part in iter_json_chunks(token,limit=r.SERIAL_BUFFER_BYTES))
                    raw=_checked_add(raw,size,limit=r.COORDINATE_RAW_BYTES_LIMIT,code='coordinate_bytes_limit')
            elif kind in (int,float): pair=_literal_cost(value)
            else: raise Refusal('invalid_coordinate')
        values.add(pair);raw_values.add(pair)
        if raw_values.finish().json_bytes+1>r.COORDINATE_CANONICAL_BYTES_LIMIT:
            raise Refusal('coordinate_bytes_limit')
    if semantic:
        if missing: raise Refusal('missing_row_key' if row else 'missing_coordinate')
        if infinite: raise Refusal('nonfinite_coordinate')
    dtype=cursor.dtype
    if dtype=='|O': dtype='<U'+str(max(1,max_chars))
    elif dtype.startswith('|S'): dtype='<U'+dtype[2:]
    result=_Fold();result.add(_literal_cost(dtype),'dtype');result.add(values.finish(),'values')
    result.add(_container_cost(length,32*length,128*length),'sorted_indices')
    pair=result.finish()
    if pair.json_bytes+1>r.COORDINATE_CANONICAL_BYTES_LIMIT: raise Refusal('coordinate_bytes_limit')
    return dtype,pair,raw,raw_values.finish().json_bytes+1,utf8


def _selected_projection(dataset,selection):
    from ._source_stock import _stock_cursor
    coordinates=_Fold();arrays=_Fold();raw=before=after=utf8=numeric=0
    for name in _coordinate_order(selection):
        cursor=_stock_cursor(dataset,name)
        _,pair,local_raw,local_before,local_utf8=_coordinate_measure(cursor,row=name in selection.row_dims,semantic=False)
        raw=_checked_add(raw,local_raw,limit=r.COORDINATE_RAW_BYTES_LIMIT,code='coordinate_bytes_limit')
        before=_checked_add(before,local_before,limit=r.COORDINATE_CANONICAL_BYTES_LIMIT,code='coordinate_bytes_limit')
        after=_checked_add(after,pair.json_bytes+1,limit=r.COORDINATE_CANONICAL_BYTES_LIMIT,code='coordinate_bytes_limit')
        utf8=_checked_add(utf8,local_utf8,limit=r.COORDINATE_LABEL_UTF8_BYTES_LIMIT,code='coordinate_bytes_limit')
        coordinates.add(pair,name)
        del cursor
    offset=0
    for name in selection.variables:
        cursor=_stock_cursor(dataset,name);size=cursor.data.nbytes
        numeric=_checked_add(numeric,size,limit=r.SELECTED_NUMERIC_BYTES_LIMIT,code='selected_numeric_bytes_limit')
        arrays.add(_array_ledger_pair(name,numeric_dtype(cursor.dtype),cursor.shape,size,offset));offset+=size
        del cursor
    return coordinates.finish(),arrays.finish(),numeric


def _same_label(actual,expected):
    if type(actual) is not type(expected): return False
    if type(actual) is float:
        return actual==expected and (actual!=0.0 or math.copysign(1.0,actual)==math.copysign(1.0,expected))
    return actual==expected


def _prepare_coordinate_models(dataset,source,selection):
    from ._source_stock import _stock_cursor
    selected={}
    for name in _coordinate_order(selection):
        cursor=_stock_cursor(dataset,name);row=name in selection.row_dims
        dtype,_,_,_,_=_coordinate_measure(cursor,row=row)
        if name in source.coordinates:
            coordinate=source.coordinates[name]
            if coordinate.dtype!=dtype or len(coordinate.values)!=cursor.shape[0]: raise Refusal('invalid_source')
            for index,expected in enumerate(coordinate.values):
                if not _same_label(_read_label(cursor,index),expected): raise Refusal('invalid_source')
        else:
            values=[]
            for index in range(cursor.shape[0]): values.append(_read_label(cursor,index))
            order=sorted(range(len(values)),key=values.__getitem__)
            coordinate=Coordinate(dtype,values,order,row=row)
            del values,order
        selected[name]=coordinate
        del cursor,coordinate
    return _CoordinateMap(selected)


def _validate_retained_arrays(dataset,source,selection=None):
    if not len(source.arrays): return
    from ._source_stock import _stock_cursor
    for name in (source.arrays if selection is None else selection.variables):
        buffer=source.arrays[name];cursor=_stock_cursor(dataset,name)
        if buffer.dtype!=numeric_dtype(cursor.dtype) or buffer.shape!=cursor.shape:
            raise Refusal('invalid_source')
        view=memoryview(cursor.data);octets=None
        try:
            octets=view.cast('B')
            if len(octets)!=len(buffer.data): raise Refusal('invalid_source')
            for start in range(0,len(octets),r.SERIAL_BUFFER_BYTES):
                piece=octets[start:start+r.SERIAL_BUFFER_BYTES]
                try:
                    if piece!=buffer.data[start:start+r.SERIAL_BUFFER_BYTES]: raise Refusal('invalid_source')
                finally: piece.release()
        finally:
            if octets is not None: octets.release()
            view.release()
        del cursor,buffer


def _selected_start(source,recipe,expected=None):
    from .admission import _active_plan
    active=_active_plan()
    if active is not None and expected is None: expected=active.source
    if type(recipe) is not Recipe: raise Refusal('invalid_recipe')
    _snapshot_exact(source,complete=False)
    if expected is not None:
        _source_identity_check(expected)
        if source.identity!=expected: raise Refusal('source_fingerprint_mismatch')
    selection=_select(source,recipe)
    _selection_snapshot(source,selection,expected=expected)
    if active is not None and (selection.variables!=active.selected['variables'] or
            selection.dimensions!=active.selected['dimensions']):
        raise Refusal('invalid_source_phase')
    if source.identity.kind!='memory': raise Refusal('unsupported_source_storage')
    return selection


def _selected_guard(dataset,selection,kind,source,recipe):
    # Observe every original owner/metadata/cache again before the selected
    # allocation boundary, with no cached scan facts granting later authority.
    from .admission import _active_plan,_preflight_required,_guard
    active=_active_plan()
    if active is not None: _preflight_required()
    prepass=_memory_prepass(dataset)
    _selected_declarations(dataset,selection)
    coordinates,arrays,numeric=_selected_projection(dataset,selection)
    if active is None:
        _standalone_guard(prepass,coordinates=coordinates,
            arrays=arrays if kind=='materialized' else None,numeric_bytes=numeric,kind=kind,held=source,recipe=recipe)
    else:
        del prepass
        from . import runtime
        runtime.require_runtime(active.runtime)
        if kind=='materialized':
            from .admission import _guard_materialization
            _guard_materialization()
        else: _guard(kind)
        _validate_plan_coordinates(dataset,active,selection)


def _active_snapshot_preflight(source):
    from .admission import _active_plan,_preflight_required
    active=_active_plan()
    if active is not None:
        # Fresh anchor equality retains priority over consumed B semantics.
        # Its scan helper has returned before the model comparison begins.
        _preflight_required()
        from .plan import _bind_plan_snapshot
        _bind_plan_snapshot(active,source)


def _validate_plan_coordinates(dataset,plan,selection):
    """Stream actual B labels against plan coordinates without a new forest."""
    from ._source_stock import _stock_cursor
    for name in _coordinate_order(selection):
        cursor=_stock_cursor(dataset,name)
        coordinate=plan.coordinates[name]
        dtype,_,_,_,_=_coordinate_measure(cursor,row=name in selection.row_dims)
        if dtype!=coordinate.dtype or cursor.shape[0]!=len(coordinate.values):
            raise Refusal('plan_binding_mismatch')
        for index,wanted in enumerate(coordinate.values):
            if not _same_label(_read_label(cursor,index),wanted):
                raise Refusal('plan_binding_mismatch')
        del cursor,coordinate


def _snapshot_memory(dataset):
    import xarray as xr
    from .admission import _required_inputs,_ACTIVE
    from . import runtime
    if type(dataset) is not xr.Dataset: raise Refusal('invalid_source')
    if _ACTIVE.get() is not None: raise Refusal('invalid_plan_input')
    with _required_inputs(dataset=dataset):
        scan=_scan_memory(dataset);source=scan.inspection
        del scan
        _scan_memory(dataset,existing=source)
        runtime.runtime_identity()
        return source


def _prepare_memory(source,recipe):
    from .admission import _required_inputs,_active_plan,_guard,_PreparationRecipe
    from . import runtime
    selection=_selected_start(source,recipe)
    with _required_inputs(snapshot=source), _PreparationRecipe(recipe):
        _active_snapshot_preflight(source)
        _scan_memory(source._handle,existing=source,selection=selection,recipe=recipe)
        _selected_guard(source._handle,selection,'prepared',source,recipe)
        _validate_retained_arrays(source._handle,source,selection)
        coordinates=_prepare_coordinate_models(source._handle,source,selection)
        prepared=SourceSnapshot(identity=source.identity,dimensions=source.dimensions,variables=source.variables,
            coordinate_descriptors=source.coordinate_descriptors,attributes=source.attributes,
            arrays={},coordinates=coordinates,_handle=source._handle)
        _scan_memory(source._handle,existing=source,selection=selection,returning=prepared,recipe=recipe)
        runtime.runtime_identity()
        if _active_plan() is not None: _guard('prepared')
        return prepared


def _materialize_selected(source,recipe,expected):
    import numpy as np
    from ._source_stock import _stock_cursor
    from .admission import _required_inputs,_active_plan,_guard
    from . import runtime
    selection=_selected_start(source,recipe,expected)
    with _required_inputs(snapshot=source):
        _active_snapshot_preflight(source)
        _scan_memory(source._handle,existing=source,selection=selection,recipe=recipe)
        _selected_guard(source._handle,selection,'materialized',source,recipe)
        _validate_retained_arrays(source._handle,source,selection)
        coordinates=_prepare_coordinate_models(source._handle,source,selection)
        arrays={}
        for name in selection.variables:
            if _active_plan() is not None:
                from .admission import _guard_materialization
                _guard_materialization()
            cursor=_stock_cursor(source._handle,name)
            data=np.ndarray.tobytes(cursor.data,order='C')
            arrays[name]=ArrayBuffer(numeric_dtype(cursor.dtype),cursor.shape,data)
            del cursor,data
        result=SourceSnapshot(identity=source.identity,dimensions=source.dimensions,variables=source.variables,
            coordinate_descriptors=source.coordinate_descriptors,attributes=source.attributes,
            arrays=arrays,coordinates=coordinates,_handle=source._handle)
        _scan_memory(source._handle,existing=source,selection=selection,returning=result,recipe=recipe)
        runtime.runtime_identity()
        if _active_plan() is not None: _guard('materialized')
        return result


def _validate_retained_coordinates(dataset,source):
    from ._source_stock import _stock_cursor
    for name,coordinate in source.coordinates.items():
        cursor=_stock_cursor(dataset,name)
        dtype,_,_,_,_=_coordinate_measure(cursor,row=False)
        if coordinate.dtype!=dtype or len(coordinate.values)!=cursor.shape[0]:
            raise Refusal('invalid_source')
        for index,expected in enumerate(coordinate.values):
            if not _same_label(_read_label(cursor,index),expected): raise Refusal('invalid_source')
        del cursor,coordinate


def _recheck_memory(source):
    from .admission import _required_inputs,_active_plan,_guard
    from . import runtime
    active=_active_plan()
    selection=_selected_start(source,active.recipe,active.source) if active is not None else None
    _snapshot_exact(source)
    if source.identity.kind!='memory': raise Refusal('unsupported_source_storage')
    with _required_inputs(snapshot=source):
        _active_snapshot_preflight(source)
        _scan_memory(source._handle,existing=source,selection=selection)
        if active is not None:
            _selected_guard(source._handle,selection,'recheck',source,active.recipe)
        _validate_retained_coordinates(source._handle,source)
        _validate_retained_arrays(source._handle,source)
        runtime.runtime_identity()
        if _active_plan() is not None: _guard('recheck')
        return source


def _owned_attempt(operation,*arguments):
    """Drop only this escaping exception's owned links, using base descriptors.

    No caller-frame/heap walk, custom setter, recursive exception cleanup or GC
    mutation occurs. Detailed internal traceback/chaining is intentionally lost.
    The thin caller removes buffer-bearing arguments before reraising the SAME
    exception, including its exact refusal code or cancellation classification.
    """
    try: return operation(*arguments),None
    except BaseException as error:
        BaseException.__traceback__.__set__(error,None)
        BaseException.__context__.__set__(error,None)
        BaseException.__cause__.__set__(error,None)
        return None,error


def _raise_owned(error):
    raise error from None


def snapshot_dataset(dataset):
    result,error=_owned_attempt(_snapshot_memory,dataset)
    dataset=None
    if error is not None: _raise_owned(error)
    return result


def prepare_source(source,recipe):
    result,error=_owned_attempt(_prepare_memory,source,recipe)
    source=recipe=None
    if error is not None: _raise_owned(error)
    return result


def _materialize_memory(source,recipe,*,expected=None):
    result,error=_owned_attempt(_materialize_selected,source,recipe,expected)
    source=recipe=expected=None
    if error is not None: _raise_owned(error)
    return result


def recheck_source(source):
    result,error=_owned_attempt(_recheck_memory,source)
    source=None
    if error is not None: _raise_owned(error)
    return result


def _materialize_bound(source,plan):
    from .plan import _plan_exact,_qualify_units
    from .admission import _required_inputs,_guard
    from . import runtime
    _plan_exact(plan)
    selection=_selected_start(source,plan.recipe,plan.source)
    with _required_inputs(plan=plan,snapshot=source):
        _active_snapshot_preflight(source)
        _scan_memory(source._handle,existing=source,selection=selection,recipe=plan.recipe)
        runtime.require_runtime(plan.runtime)
        _selected_guard(source._handle,selection,'materialized',source,plan.recipe)
        _qualify_units(source,plan.recipe,expected=plan)
        return _materialize_selected(source,plan.recipe,plan.source)


def materialize_source(source,plan):
    result,error=_owned_attempt(_materialize_bound,source,plan)
    source=plan=None
    if error is not None: _raise_owned(error)
    return result
