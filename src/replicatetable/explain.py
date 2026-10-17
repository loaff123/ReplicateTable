"""Bounded eager-memory row explanations, after exact same-engine replay.

See docs/contracts/EXPLANATION-INTERFACE.md for the frozen allocation schedule.
The immutable output owns primitives only. It has no to_dict, source handle,
plan, result, registry, alternate reducer, or omitted-lineage proof engine.
"""
import hashlib
import math

from .codec import OwnedMap, _chunks, exact_int, primitive_bounds, utf8_length
from .errors import Refusal, ComputationError
from .model import (validate_name, validate_unit, numeric_dtype, _dtype_info,
                    _unicode_width, _require_uninitialized)
from ._result import (_map, _fields, _sequence, _typed_scalar, _reasons,
                      _same_scalar, _support_parts, _SUPPORT_FIELDS, _effective)
from . import resources as r

_ASSURANCE = 'Exact source-bound same-engine replay completed before tracing.'
_NOTICE = ('Displayed cells are a bounded prefix. Complete membership is defined by selectors, '
           'support offsets, and the source, plan, and result hashes. Replay is not independent numerical proof.')
_ROOT = tuple(sorted(('version','source','recipe_sha256','plan_sha256','result_sha256',
    'runtime_sha256','row_dims','key','coordinates','limit','byte_truncated','assurance','notice','columns')))
_COLUMN = ('name','source','source_dtype','converted_dtype','output_dtype','input_dims',
           'final_dims','broadcast','conversion','weight','value','reasons','source_cells','stages')
_COUNTERS = ('total','shown','truncated','limit_omitted','byte_omitted')
_STAGE = _COUNTERS + ('name','input_dims','dims','remaining_dims','op','missing','min_count',
                     'input_stage','support_start','records')
_CELL = ('indices','labels','raw','converted','raw_weight','normalized_weight','exclusion_reason')


def _integer(value, *, minimum=0, maximum=r.COUNT_MAX):
    return exact_int(value, 'invalid_explanation', minimum=minimum, maximum=maximum)


def _text(value, expected):
    if type(value) is not str or value != expected: raise Refusal('invalid_explanation')


def _boolean(value):
    if type(value) is not bool: raise Refusal('invalid_explanation')


def _digest(value):
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise Refusal('invalid_explanation')


def _float(value, *, positive=False, nonnegative=False):
    if type(value) is not float or not math.isfinite(value): raise Refusal('invalid_explanation')
    if positive and value <= 0 or nonnegative and value < 0: raise Refusal('invalid_explanation')


def _names(value, *, nonempty=False):
    _sequence(value, 16)
    if nonempty and not value: raise Refusal('invalid_explanation')
    for name in value: validate_name(name, 'invalid_explanation')
    if len(set(value)) != len(value): raise Refusal('invalid_explanation')
    return tuple(value)


def _product(names, coordinates):
    answer = 1
    for name in names:
        if name not in coordinates: raise Refusal('invalid_explanation')
        length = coordinates[name]['length']
        if answer > r.SHAPE_PRODUCT_LIMIT // length: raise Refusal('invalid_explanation')
        answer *= length
    return answer


def _selector(value, dims, coordinates, fixed):
    _sequence(value, 16)
    if len(value) != len(dims): raise Refusal('invalid_explanation')
    for dim, index in zip(dims, value):
        if dim in fixed:
            _integer(index, maximum=coordinates[dim]['length']-1)
        elif index is not None: raise Refusal('invalid_explanation')


def _section(value, fields, total, limit, content):
    _fields(value, _COUNTERS + fields)
    for name in ('total','shown','limit_omitted','byte_omitted'): _integer(value[name])
    _boolean(value['truncated'])
    shown = value['shown']
    if (value['total'] != total or value['limit_omitted'] != max(total-limit, 0) or
            value['byte_omitted'] != min(total,limit)-shown or value['truncated'] != (shown<total)):
        raise Refusal('invalid_explanation')
    _sequence(value[content], r.EXPLANATION_CELL_LIMIT)
    if len(value[content]) != shown: raise Refusal('invalid_explanation')


def _source_positions(ordinal, dims, coordinates, selection):
    """One physical selected-prefix index, computed with O(rank) state."""
    output = list(selection)
    for axis in range(len(dims)-1, -1, -1):
        if selection[axis] is None:
            length = coordinates[dims[axis]]['length']
            output[axis] = ordinal % length
            ordinal //= length
    return tuple(output)


def _check_cell(cell, col, coords, key, row_dims, ordinal):
    _fields(cell, _CELL)
    dims = col['input_dims']; section = col['source_cells']
    _sequence(cell['indices'],16); _sequence(cell['labels'],16)
    if len(cell['indices']) != len(dims) or len(cell['labels']) != len(dims):
        raise Refusal('invalid_explanation')
    for dim,index,label in zip(dims,cell['indices'],cell['labels']):
        _integer(index,maximum=coords[dim]['length']-1)
        _typed_scalar(label,coords[dim]['dtype'],coordinate=True)
        if dim in row_dims and not _same_scalar(label,key[dim]): raise Refusal('invalid_explanation')
    if tuple(cell['indices']) != _source_positions(ordinal,dims,coords,section['selection']):
        raise Refusal('invalid_explanation')
    source_float = col['source_dtype'] in ('float32','float64')
    _typed_scalar(cell['raw'],col['source_dtype'],nullable=source_float)
    _typed_scalar(cell['converted'],col['converted_dtype'],nullable=source_float)
    if (cell['raw'] is None) != (cell['converted'] is None): raise Refusal('invalid_explanation')
    why = cell['exclusion_reason']
    if why is not None and (type(why) is not str or why not in ('missing_value','zero_weight')):
        raise Refusal('invalid_explanation')
    weight = col['weight']
    if weight is None:
        if cell['raw_weight'] is not None: raise Refusal('invalid_explanation')
        if col['stages']:
            _float(cell['normalized_weight'])
            if cell['normalized_weight'] != 1.: raise Refusal('invalid_explanation')
        elif cell['normalized_weight'] is not None: raise Refusal('invalid_explanation')
    else:
        _typed_scalar(cell['raw_weight'],weight['dtype'])
        if cell['raw_weight'] < 0: raise Refusal('invalid_explanation')
        _float(cell['normalized_weight'],nonnegative=True)
    expected = ('missing_value' if cell['raw'] is None else
                'zero_weight' if weight is not None and cell['normalized_weight'] == 0 else None)
    if why != expected: raise Refusal('invalid_explanation')


def _check_stage(section, col, coords, key, row_dims, previous_dims, position, support_start):
    _fields(section,_STAGE)
    validate_name(section['name'],'invalid_explanation')
    for field in ('op','missing'):
        if type(section[field]) is not str: raise Refusal('invalid_explanation')
    if section['op'] not in ('mean','weighted_mean','min','max') or section['missing'] not in ('skip','propagate'):
        raise Refusal('invalid_explanation')
    _integer(section['min_count'],minimum=1,maximum=r.SHAPE_PRODUCT_LIMIT)
    input_dims = _names(section['input_dims']); dims = _names(section['dims'],nonempty=True)
    remaining = _names(section['remaining_dims'])
    if input_dims != previous_dims or any(d not in input_dims or d in row_dims for d in dims):
        raise Refusal('invalid_explanation')
    if remaining != tuple(d for d in input_dims if d not in dims): raise Refusal('invalid_explanation')
    if position == 0:
        if section['input_stage'] is not None: raise Refusal('invalid_explanation')
    else:
        _integer(section['input_stage'],maximum=0)
    weighted = section['op'] == 'weighted_mean'
    if weighted != (position == 0 and col['weight'] is not None): raise Refusal('invalid_explanation')
    _integer(section['support_start'])
    if section['support_start'] != support_start: raise Refusal('invalid_explanation')
    total = _product(tuple(d for d in remaining if d not in row_dims),coords)
    _section(section,_STAGE[len(_COUNTERS):],total,col['_limit'],'records')
    n_input = _product(dims,coords); support_count = _product(remaining,coords)
    previous_index = support_start-1; previous_keys = None
    for entry in section['records']:
        _fields(entry,('support_index','record','membership'))
        index = _integer(entry['support_index'],minimum=support_start,maximum=support_start+support_count-1)
        if index <= previous_index: raise Refusal('invalid_explanation')
        previous_index = index
        _selector(entry['membership'],input_dims,coords,remaining)
        record = _fields(entry['record'],_SUPPORT_FIELDS)
        _support_parts(**{name:record[name] for name in _SUPPORT_FIELDS})
        if (record['column'] != col['name'] or record['stage'] != section['name'] or
                not _same_scalar(record['unit'],col['conversion']['effective_unit']) or record['n_input'] != n_input):
            raise Refusal('invalid_explanation')
        _fields(record['keys'],remaining)
        for name in remaining:
            _typed_scalar(record['keys'][name],coords[name]['dtype'],coordinate=True)
            if name in row_dims:
                if not _same_scalar(record['keys'][name],key[name]): raise Refusal('invalid_explanation')
                source_axis = col['input_dims'].index(name)
                if entry['membership'][input_dims.index(name)] != col['source_cells']['selection'][source_axis]:
                    raise Refusal('invalid_explanation')
        order_keys = tuple(record['keys'][name] for name in sorted(remaining))
        if previous_keys is not None and order_keys <= previous_keys: raise Refusal('invalid_explanation')
        previous_keys = order_keys
        expected = (('missing_values',) if section['missing']=='propagate' and record['n_valid'] != n_input else ())
        if record['n_valid'] < section['min_count']: expected += ('insufficient_count',)
        if weighted and record['weight_valid'] == 0: expected += ('zero_weight',)
        if tuple(record['reasons']) != expected: raise Refusal('invalid_explanation')
        if not weighted and (record['n_positive_weight_valid'] != record['n_valid'] or
                record['weight_total'] != float(n_input) or record['weight_valid'] != float(record['n_valid'])):
            raise Refusal('invalid_explanation')
        if position == len(col['stages'])-1 and (not _same_scalar(record['value'],col['value']) or
                tuple(record['reasons']) != tuple(col['reasons'])): raise Refusal('invalid_explanation')
    return remaining,support_start+support_count


def _validate_root(root):
    _fields(root,_ROOT); _integer(root['version'],minimum=1,maximum=1)
    source = _fields(root['source'],('kind','sha256','size_bytes'))
    if type(source['kind']) is not str or source['kind'] not in ('memory','file'): raise Refusal('invalid_explanation')
    _digest(source['sha256']); _integer(source['size_bytes'])
    for name in ('recipe_sha256','plan_sha256','result_sha256','runtime_sha256'): _digest(root[name])
    rows = _names(root['row_dims']); _fields(root['key'],rows)
    _map(root['coordinates'],16); coords=root['coordinates']
    for name,coordinate in coords.items():
        validate_name(name,'invalid_explanation'); _fields(coordinate,('dtype','length'))
        dtype=coordinate['dtype']
        if type(dtype) is not str: raise Refusal('invalid_explanation')
        if _unicode_width(dtype) is None: _dtype_info(dtype,'invalid_explanation',coordinate=True)
        _integer(coordinate['length'],minimum=1,maximum=r.DIMENSION_LENGTH_LIMIT)
    for dim in rows:
        if dim not in coords: raise Refusal('invalid_explanation')
        _typed_scalar(root['key'][dim],coords[dim]['dtype'],coordinate=True)
    if _product(rows,coords)>r.OUTPUT_ROWS_LIMIT: raise Refusal('invalid_explanation')
    _integer(root['limit'],minimum=1,maximum=1000); _boolean(root['byte_truncated'])
    _text(root['assurance'],_ASSURANCE); _text(root['notice'],_NOTICE)
    _sequence(root['columns'],32)
    if not root['columns']: raise Refusal('invalid_explanation')
    names=set(); selected=set(rows); support_start=0; stopped=False; byte_truncated=False
    for col in root['columns']:
        _fields(col,_COLUMN)
        validate_name(col['name'],'invalid_explanation'); validate_name(col['source'],'invalid_explanation')
        if col['name'] in names: raise Refusal('invalid_explanation')
        names.add(col['name'])
        for name in ('source_dtype','converted_dtype','output_dtype'):
            if numeric_dtype(col[name],'invalid_explanation') != col[name]:
                raise Refusal('invalid_explanation')
        inputs=_names(col['input_dims']); final=_names(col['final_dims']); broadcast=_names(col['broadcast'])
        selected.update(inputs); _product(inputs,coords)
        conv=_fields(col['conversion'],('source_unit','target_unit','effective_unit','scale','offset'))
        for field in ('source_unit','target_unit','effective_unit'): validate_unit(conv[field],'invalid_explanation')
        _float(conv['scale'],positive=True); _float(conv['offset'])
        effective=conv['source_unit'] if conv['target_unit'] is None else conv['target_unit']
        if not _same_scalar(effective,conv['effective_unit']) or conv['source_unit'] is None and conv['target_unit'] is not None:
            raise Refusal('invalid_explanation')
        if conv['source_unit'] is None and (conv['scale'] != 1. or conv['offset'] != 0.):
            raise Refusal('invalid_explanation')
        _sequence(col['stages'],2)
        direct=not col['stages'] and conv['scale']==1. and conv['offset']==0.
        wanted_dtype=col['source_dtype'] if direct else 'float64'
        if col['converted_dtype'] != wanted_dtype or col['output_dtype'] != wanted_dtype: raise Refusal('invalid_explanation')
        _typed_scalar(col['value'],col['output_dtype'],nullable=col['output_dtype'] in ('float32','float64'))
        reasons=_reasons(col['reasons'])
        if (col['value'] is None) != bool(reasons): raise Refusal('invalid_explanation')
        if not col['stages'] and reasons != (('missing_values',) if col['value'] is None else ()):
            raise Refusal('invalid_explanation')
        weight=col['weight']
        if weight is not None:
            _fields(weight,('source','dtype','dims','source_unit','unit','scale','offset'))
            validate_name(weight['source'],'invalid_explanation')
            if numeric_dtype(weight['dtype'],'invalid_explanation') != weight['dtype']:
                raise Refusal('invalid_explanation')
            weight_dims=_names(weight['dims']); selected.update(weight_dims)
            if any(name not in inputs for name in weight_dims): raise Refusal('invalid_explanation')
            validate_unit(weight['source_unit'],'invalid_explanation'); _text(weight['unit'],'dimensionless')
            _float(weight['scale'],positive=True); _float(weight['offset'])
            if weight['offset'] != 0. or not col['stages']: raise Refusal('invalid_explanation')
            if weight['source_unit'] is None and weight['scale'] != 1.:
                raise Refusal('invalid_explanation')
        section=col['source_cells']; total=_product(tuple(d for d in inputs if d not in rows),coords)
        _section(section,('selection','cells'),total,root['limit'],'cells')
        _selector(section['selection'],inputs,coords,rows)
        for ordinal,cell in enumerate(section['cells']): _check_cell(cell,col,coords,root['key'],rows,ordinal)
        # One shallow validation wrapper, not a cloned column or plan forest.
        context={name:col[name] for name in _COLUMN}; context['_limit']=root['limit']
        previous=inputs; stage_names=set()
        for position,section in enumerate(col['stages']):
            previous,support_start=_check_stage(section,context,coords,root['key'],rows,previous,position,support_start)
            if support_start>r.SUPPORT_RECORDS_LIMIT: raise Refusal('invalid_explanation')
            if section['name'] in stage_names: raise Refusal('invalid_explanation')
            stage_names.add(section['name'])
        if previous != final or any(d not in rows for d in final): raise Refusal('invalid_explanation')
        if broadcast != tuple(d for d in rows if d not in final): raise Refusal('invalid_explanation')
        for section in (col['source_cells'],)+tuple(col['stages']):
            if stopped and section['shown']: raise Refusal('invalid_explanation')
            if section['byte_omitted']:
                stopped=byte_truncated=True
    if selected != set(coords) or root['byte_truncated'] != byte_truncated: raise Refusal('invalid_explanation')


def _checked_root(root):
    try:
        _validate_root(root)
        return primitive_bounds(root,code='invalid_explanation')
    except Refusal as error:
        if error.code in ('explanation_bytes_limit','estimated_memory_limit'): raise
        raise Refusal('invalid_explanation') from None


def _encoded_size(value):
    chunks=_chunks(value); total=0
    try:
        for fragment in chunks: total += len(fragment)
        return total
    finally: chunks.close()


def _adopt_tree(value, *, consume=False):
    """Adopt producer builders bottom-up, never a whole freeze/thaw mirror.

    Exact immutable primitives are borrowed. Public mutable inputs are owned
    without mutation; the private producer additionally retires each builder
    as its already-final children are adopted.
    """
    kind=type(value)
    if kind is OwnedMap: return value
    if kind is dict:
        if consume:
            for name in value: value[name]=_adopt_tree(value[name],consume=True)
            output=OwnedMap._from_checked(tuple((name,value[name]) for name in sorted(value)))
            value.clear()
            return output
        return OwnedMap._from_checked(tuple((name,_adopt_tree(value[name])) for name in sorted(value)))
    if kind in (list,tuple):
        if consume and kind is list:
            for index in range(len(value)): value[index]=_adopt_tree(value[index],consume=True)
            output=tuple(value); value.clear(); return output
        if kind is tuple and all(type(item) not in (dict,list) for item in value):
            return value
        return tuple(_adopt_tree(item,consume=consume) for item in value)
    return value


def _construct(root, consume=False):
    _checked_root(root)
    length=_encoded_size(root)+1
    if length>r.EXPLANATION_BYTES_LIMIT: raise Refusal('explanation_bytes_limit')
    owned=_adopt_tree(root,consume=consume)
    return owned,length


class RowExplanation:
    __slots__=('_data','_byte_limit','_serialized_size')
    def __init_subclass__(cls,**kwargs): raise TypeError('RowExplanation is final')
    def __setattr__(self,name,value): raise AttributeError('RowExplanation is immutable')
    def __delattr__(self,name): raise AttributeError('RowExplanation is immutable')
    def __getattr__(self,name):
        if name in _ROOT: return object.__getattribute__(self,'_data')[name]
        raise AttributeError(name)
    def __init__(self,*,version,source,recipe_sha256,plan_sha256,result_sha256,runtime_sha256,
                 row_dims,key,coordinates,limit,byte_truncated,assurance,notice,columns):
        _require_uninitialized(self,'_data','invalid_explanation')
        from .source import _owned_attempt,_raise_owned
        root=dict(version=version,source=source,recipe_sha256=recipe_sha256,plan_sha256=plan_sha256,
            result_sha256=result_sha256,runtime_sha256=runtime_sha256,row_dims=row_dims,key=key,
            coordinates=coordinates,limit=limit,byte_truncated=byte_truncated,assurance=assurance,
            notice=notice,columns=columns)
        output,error=_owned_attempt(_construct,root)
        version=source=recipe_sha256=plan_sha256=result_sha256=runtime_sha256=None
        row_dims=key=coordinates=limit=byte_truncated=assurance=notice=columns=root=None
        if error is not None:
            self=None; _raise_owned(error)
        owned,length=output
        object.__setattr__(self,'_data',owned)
        object.__setattr__(self,'_byte_limit',r.EXPLANATION_BYTES_LIMIT)
        object.__setattr__(self,'_serialized_size',length)
    def to_json(self): return _serialize_explanation(self,False)
    def iter_json_chunks(self): return _serialize_explanation(self,True)


def _explanation_exact(value):
    if type(value) is not RowExplanation: raise Refusal('invalid_explanation')
    try:
        data=object.__getattribute__(value,'_data')
        limit=object.__getattribute__(value,'_byte_limit'); size=object.__getattribute__(value,'_serialized_size')
    except AttributeError: raise Refusal('invalid_explanation') from None
    if type(data) is not OwnedMap: raise Refusal('invalid_explanation')
    _integer(limit,minimum=r.EXPLANATION_BYTES_LIMIT,maximum=r.EXPLANATION_BYTES_LIMIT)
    _integer(size,minimum=1,maximum=limit); _checked_root(data)
    if _encoded_size(data)+1 != size: raise Refusal('invalid_explanation')
    return data,size


def _trace_chunks(data):
    yield from _chunks(data)
    yield b'\n'


class _TraceIterator:
    __slots__=('_data','_inner','_closed')
    def __init__(self,data): self._data=data; self._inner=None; self._closed=False
    def __iter__(self): return self
    def __next__(self): return _iterator_call(self,'next')
    def close(self): return _iterator_call(self,'close')
    def throw(self,error): return _iterator_call(self,'throw',error)


def _retire_iterator(iterator):
    inner=iterator._inner
    iterator._data=iterator._inner=None; iterator._closed=True
    if inner is not None: inner.close()


def _drive_iterator(iterator,kind,error):
    try:
        if kind=='close': _retire_iterator(iterator); return None
        if kind=='throw':
            if not isinstance(error,BaseException): raise TypeError('throw requires an exception instance')
            if iterator._inner is None: _retire_iterator(iterator); raise error
            return iterator._inner.throw(error)
        if iterator._closed: raise StopIteration
        if iterator._inner is None:
            iterator._inner=_trace_chunks(iterator._data); iterator._data=None
        return next(iterator._inner)
    except BaseException:
        try: _retire_iterator(iterator)
        except BaseException as cleanup:
            BaseException.__traceback__.__set__(cleanup,None)
            BaseException.__context__.__set__(cleanup,None)
            BaseException.__cause__.__set__(cleanup,None)
        raise


def _iterator_call(iterator,kind,error=None):
    from .source import _owned_attempt,_raise_owned
    output,failure=_owned_attempt(_drive_iterator,iterator,kind,error)
    iterator=error=None
    if failure is not None: _raise_owned(failure)
    return output


def _serialize(value,chunks):
    data,length=_explanation_exact(value)
    if chunks: return _TraceIterator(data)
    output=bytearray(length); position=0; iterator=_trace_chunks(data)
    try:
        for fragment in iterator:
            end=position+len(fragment)
            if end>length: raise ComputationError('resource_estimate_mismatch')
            output[position:end]=fragment; position=end
    finally: iterator.close()
    if position != length: raise ComputationError('resource_estimate_mismatch')
    return bytes(output)


def _serialize_explanation(value,chunks):
    from .source import _owned_attempt,_raise_owned
    output,error=_owned_attempt(_serialize,value,chunks)
    value=None
    if error is not None: _raise_owned(error)
    return output


def _query_input(plan,key,limit):
    _integer(limit,minimum=1,maximum=r.EXPLANATION_CELL_LIMIT)
    if type(key) is not dict or len(key)!=len(plan.recipe.row_dims): raise Refusal('invalid_explanation_key')
    if any(type(name) is not str for name in key): raise Refusal('invalid_explanation_key')
    if any(name not in key for name in plan.recipe.row_dims): raise Refusal('invalid_explanation_key')
    try:
        for name in plan.recipe.row_dims:
            coord=plan.coordinates[name]; value=key[name]
            if coord.dtype.startswith('<U'):
                utf8_length(value,'invalid_explanation_key',maximum=r.LABEL_UTF8_BYTES_LIMIT)
            else: _typed_scalar(value,coord.dtype,coordinate=True)
        primitive_bounds(key,code='invalid_explanation_key')
    except Refusal as error:
        if error.code=='estimated_memory_limit': raise
        raise Refusal('invalid_explanation_key') from None
    if _encoded_size(key)+1>r.KEY_BYTES_LIMIT: raise Refusal('key_bytes_limit')


def _query(plan,key,limit):
    # The owning operation has freshly admitted its original A/B/C closure
    # before allocating these stored-key and rank-bounded position maps.
    _query_input(plan,key,limit)
    stored={}; positions={}; canonical={}; row_index=0
    for name in plan.recipe.row_dims:
        coord=plan.coordinates[name]; wanted=key[name]; matched=None
        for physical,label in enumerate(coord.values):
            if type(label) is type(wanted) and label==wanted:
                matched=physical; stored[name]=label; break
        if matched is None: raise Refusal('row_key_not_found')
        positions[name]=matched
        for rank,physical in enumerate(coord.sorted_indices):
            if physical==matched: canonical[name]=rank; break
        row_index=row_index*len(coord.values)+canonical[name]
    return stored,positions,canonical,row_index


def _hash_stream(iterator,*,final_lf=False):
    digest=hashlib.sha256()
    try:
        for fragment in iterator: digest.update(fragment)
        if final_lf: digest.update(b'\n')
        return digest.hexdigest()
    finally: iterator.close()


def _hash_context(plan,result_digest):
    from ._bundle_formats import _recipe_json_chunks,_plan_json_chunks
    return (_hash_stream(_recipe_json_chunks(plan.recipe),final_lf=True),
            _hash_stream(_plan_json_chunks(plan)),result_digest,
            _hash_stream(_chunks(plan.runtime),final_lf=True))


def _counter_fields(total,limit):
    return dict(total=total,shown=0,truncated=True,limit_omitted=max(total-limit,0),byte_omitted=min(total,limit))


def _build_skeleton(plan,result,stored,positions,row_index,limit,digests):
    coords={name:dict(dtype=c.dtype,length=len(c.values)) for name,c in plan.coordinates.items()}
    columns=[]; row=result.rows[row_index]
    for col in plan.columns:
        op=col['unit_operation']; weight=col['weight']
        weight_meta=None
        if weight is not None:
            wop=weight['unit_operation']
            weight_meta=dict(source=weight['source'],dtype=weight['dtype'],dims=weight['dims'],
                source_unit=wop['source_unit'],unit='dimensionless',scale=wop['scale'],offset=wop['offset'])
        source_total=_product(tuple(d for d in col['input_dims'] if d not in positions),coords)
        source_section=_counter_fields(source_total,limit)
        source_section.update(selection=tuple(positions.get(d) for d in col['input_dims']),cells=[])
        stages=[]
        for index,stage in enumerate(col['stages']):
            total=_product(tuple(d for d in stage['remaining_dims'] if d not in positions),coords)
            section=_counter_fields(total,limit)
            section.update(name=stage['name'],input_dims=stage['input_dims'],dims=stage['dims'],
                remaining_dims=stage['remaining_dims'],op=stage['op'],missing=stage['missing'],
                min_count=stage['min_count'],input_stage=None if index==0 else 0,
                support_start=stage['support_start'],records=[])
            stages.append(section)
        columns.append(dict(name=col['name'],source=col['source'],source_dtype=col['source_dtype'],
            converted_dtype=col['output_dtype'],output_dtype=col['output_dtype'],input_dims=col['input_dims'],
            final_dims=col['final_dims'],broadcast=col['broadcast'],conversion=dict(
                source_unit=op['source_unit'],target_unit=op['target_unit'],effective_unit=_effective(col),
                scale=op['scale'],offset=op['offset']),weight=weight_meta,value=row.values[col['name']],
            reasons=row.reasons[col['name']],source_cells=source_section,stages=stages))
    return dict(version=1,source=plan.source._projection(),recipe_sha256=digests[0],plan_sha256=digests[1],
        result_sha256=digests[2],runtime_sha256=digests[3],row_dims=plan.recipe.row_dims,key=stored,
        coordinates=coords,limit=limit,byte_truncated=True,assurance=_ASSURANCE,notice=_NOTICE,columns=columns)


class _TraceBudget:
    __slots__=('root','size','objects','remaining','stopped','estimate_bytes','estimate_objects')
    def __init__(self,root,estimates):
        bounds=primitive_bounds(root,code='invalid_explanation')
        if bounds.json_bytes+1>r.EXPLANATION_BYTES_LIMIT: raise Refusal('explanation_bytes_limit')
        self.root=root; self.size=_encoded_size(root)+1; self.objects=bounds.object_bytes+1024
        self.remaining=sum(min(section['total'],root['limit']) for col in root['columns']
                           for section in (col['source_cells'],)+tuple(col['stages']))
        self.stopped=False; self.estimate_bytes=estimates['trace_bytes']; self.estimate_objects=estimates['trace_objects_bytes']
        if self.size>self.estimate_bytes or self.objects>self.estimate_objects:
            raise ComputationError('resource_estimate_mismatch')
    def append(self,section,content,record):
        if self.stopped: return False
        shown=section['shown']; after=shown+1; byte_after=section['byte_omitted']-1
        delta=(len(str(after))-len(str(shown)) + len(str(byte_after))-len(str(section['byte_omitted'])))
        if after==section['total']: delta+=1  # true -> false
        if self.remaining==1: delta+=1       # root true -> false
        size=self.size+_encoded_size(record)+(1 if shown else 0)+delta
        if size>r.EXPLANATION_BYTES_LIMIT:
            self.stopped=True; return False
        objects=self.objects+primitive_bounds(record,code='invalid_explanation').object_bytes+136
        if size>self.estimate_bytes or objects>self.estimate_objects:
            raise ComputationError('resource_estimate_mismatch')
        section[content].append(record)
        section['shown']=after; section['byte_omitted']=byte_after; section['truncated']=after<section['total']
        self.remaining-=1; self.root['byte_truncated']=self.remaining!=0
        self.size=size; self.objects=objects
        return True


def _physical_indices(dims,coordinates,selection):
    shape=tuple(coordinates[d]['length'] for d in dims)
    current=[0 if index is None else index for index in selection]
    while True:
        yield tuple(current)
        for axis in range(len(dims)-1,-1,-1):
            if selection[axis] is not None: continue
            current[axis]+=1
            if current[axis]<shape[axis]: break
            current[axis]=0
        else: return


def _source_cell(plan,col,indices,values,raw_weights,normalized):
    from .reduce import _finite
    source_integer=col['source_dtype'].startswith(('int','uint'))
    raw=int(values[indices]) if source_integer else float(values[indices])
    if not source_integer and math.isnan(raw): raw=None
    direct=not col['stages'] and col['unit_operation']['scale']==1 and col['unit_operation']['offset']==0
    if raw is None: converted=None
    elif direct: converted=raw
    else:
        converted=_finite(float(raw)*col['unit_operation']['scale'])
        converted=_finite(converted+col['unit_operation']['offset'])
    weight=col['weight']; raw_weight=None; normalized_weight=None
    if weight is not None:
        weight_index=tuple(indices[col['input_dims'].index(d)] for d in weight['dims'])
        raw_weight=(int(raw_weights[weight_index]) if weight['dtype'].startswith(('int','uint'))
                    else float(raw_weights[weight_index]))
        normalized_weight=float(normalized[indices])
    elif col['stages']: normalized_weight=1.
    why=('missing_value' if raw is None else 'zero_weight' if weight is not None and normalized_weight==0 else None)
    return OwnedMap._from_checked(tuple(sorted(dict(indices=indices,
        labels=tuple(plan.coordinates[d].values[i] for d,i in zip(col['input_dims'],indices)),
        raw=raw,converted=converted,raw_weight=raw_weight,normalized_weight=normalized_weight,
        exclusion_reason=why).items())))


def _trace_source(plan,materialized,col,section,budget):
    import numpy as np
    from .reduce import _normalized_weights
    values=raw_weights=normalized=None; iterator=None
    try:
        if col['weight'] is not None:
            normalized=_normalized_weights(materialized,col)
        buffer=materialized.arrays[col['source']]
        values=np.ndarray(shape=buffer.shape,dtype=buffer.dtype,buffer=buffer.data)
        if col['weight'] is not None:
            buffer=materialized.arrays[col['weight']['source']]
            raw_weights=np.ndarray(shape=buffer.shape,dtype=buffer.dtype,buffer=buffer.data)
        iterator=_physical_indices(col['input_dims'],budget.root['coordinates'],section['selection'])
        for _ in range(min(section['total'],budget.root['limit'])):
            indices=next(iterator)
            record=_source_cell(plan,col,indices,values,raw_weights,normalized)
            if not budget.append(section,'cells',record): break
            record=None
    finally:
        if iterator is not None: iterator.close()
        values=raw_weights=normalized=iterator=None


def _support_entries(plan,stage,canonical):
    dims=stage['support_dims']; coordinates=plan.coordinates
    current=[canonical.get(d,0) for d in dims]
    while True:
        offset=0
        for dim,rank in zip(dims,current): offset=offset*len(coordinates[dim].values)+rank
        membership=tuple(None if d in stage['dims'] else
            coordinates[d].sorted_indices[current[dims.index(d)]] for d in stage['input_dims'])
        yield stage['support_start']+offset,membership
        for axis in range(len(dims)-1,-1,-1):
            if dims[axis] in canonical: continue
            current[axis]+=1
            if current[axis]<len(coordinates[dims[axis]].values): break
            current[axis]=0
        else: return


def _trace_stage(plan,result,stage,section,canonical,budget):
    iterator=_support_entries(plan,stage,canonical)
    try:
        for _ in range(min(section['total'],budget.root['limit'])):
            index,membership=next(iterator); record=result.support[index]
            projected=OwnedMap._from_checked(tuple((name,getattr(record,name)) for name in _SUPPORT_FIELDS))
            entry=OwnedMap._from_checked((('membership',membership),('record',projected),('support_index',index)))
            if not budget.append(section,'records',entry): break
            record=projected=entry=None
    finally: iterator.close()


def _trace_memory(plan,source,result,root,canonical):
    from .admission import _required_inputs,_guard
    from .source import materialize_source
    budget=_TraceBudget(root,plan.estimates)
    materialized=materialize_source(source,plan)
    with _required_inputs(snapshot=materialized):
        _guard('materialized')
        for col,output in zip(plan.columns,root['columns']):
            if not budget.stopped:
                _trace_source(plan,materialized,col,output['source_cells'],budget)
            for stage,section in zip(col['stages'],output['stages']):
                if not budget.stopped: _trace_stage(plan,result,stage,section,canonical,budget)
            _guard('materialized')
    if _encoded_size(root)+1 != budget.size: raise ComputationError('resource_estimate_mismatch')
    return budget.size


def _finalize(root,length):
    owned,actual=_construct(root,True)
    if actual!=length: raise ComputationError('resource_estimate_mismatch')
    output=object.__new__(RowExplanation)
    object.__setattr__(output,'_data',owned)
    object.__setattr__(output,'_byte_limit',r.EXPLANATION_BYTES_LIMIT)
    object.__setattr__(output,'_serialized_size',actual)
    return output


def _explain_memory(plan,source,result,key,limit):
    from .plan import _plan_exact,_plan_selected
    from .source import _selection_snapshot,recheck_source
    from .admission import _required_inputs,_guard
    from .runtime import require_runtime
    from ._replay import _require_exact_replay
    _plan_exact(plan)
    _selection_snapshot(source,_plan_selected(plan),expected=plan.source)
    _query_input(plan,key,limit)
    with _required_inputs(plan=plan,snapshot=source,result=result):
        _guard('materialized')
        stored,positions,canonical,row_index=_query(plan,key,limit)
        result_digest=_require_exact_replay(plan,source,result)
        # The replay helper, all of its result/iterator frames and selected
        # arrays have ended before any second trace materialization starts.
        digests=_hash_context(plan,result_digest)
        root=_build_skeleton(plan,result,stored,positions,row_index,limit,digests)
        length=_trace_memory(plan,source,result,root,canonical)
        # No selected trace array/view/helper frame survives this boundary.
        recheck_source(source); require_runtime(plan.runtime); _guard('serialize')
        output=_finalize(root,length)
        _guard('serialize'); require_runtime(plan.runtime)
        return output


def explain_row(plan,source,result,key,*,limit):
    """Explain one eager-memory row after complete exact same-engine replay."""
    from .source import _owned_attempt,_raise_owned
    output,error=_owned_attempt(_explain_memory,plan,source,result,key,limit)
    plan=source=result=key=limit=None
    if error is not None: _raise_owned(error)
    return output
