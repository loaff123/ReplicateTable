"""Private borrowed-model walks and bounded source observation arithmetic.

These functions do not inspect a Dataset, native file, or process runtime.
Owning source/runtime/unit boundaries must qualify actual state first. A cost
walk is never an authenticity, unit-semantics, or source-admission shortcut.
"""
from dataclasses import dataclass
from . import resources as r
from .codec import OwnedMap
from .model import Coordinate, Recipe, MetadataValue, numeric_dtype, validate_name, validate_unit
from .errors import Refusal
from ._resource_bounds import (_JP,_Fold,_literal_cost,_checked_add,_checked_mul,
    _shape_product,_count,_utf8,_check_cap,_container_cost,NUMBER)


def _owned_map(value, *, maximum=r.METADATA_SCALAR_LIMIT, code='invalid_source'):
    if type(value) is not OwnedMap: raise Refusal(code)
    try:
        items=object.__getattribute__(value,'_items')
    except AttributeError:
        raise Refusal(code) from None
    if type(items) is not tuple or len(items)>maximum: raise Refusal(code)
    previous=None
    for pair in items:
        if type(pair) is not tuple or len(pair)!=2 or type(pair[0]) is not str:
            raise Refusal(code)
        _utf8(pair[0],code=code)
        if previous is not None and previous>=pair[0]: raise Refusal(code)
        previous=pair[0]
    return value


def _fields(value,names,code='invalid_source'):
    _owned_map(value,maximum=len(names),code=code)
    if len(value._items)!=len(names): raise Refusal(code)
    for name,_ in value._items:
        if name not in names: raise Refusal(code)
    return value


def _owned_cost(value, _depth=0, *, object_limit=r.LOGICAL_JOURNEY_LIMIT, object_code='estimated_memory_limit'):
    _count(object_limit,object_code,limit=r.LOGICAL_JOURNEY_LIMIT)
    kind=type(value)
    if kind not in (tuple,OwnedMap):
        cost=_literal_cost(value)
        _count(cost.object_bytes,object_code,limit=object_limit)
        return cost
    if _depth>=r.JSON_DEPTH_LIMIT:raise Refusal('invalid_source')
    if kind is OwnedMap:_owned_map(value);count=len(value._items)
    else:
        count=len(value)
        if count>r.METADATA_SCALAR_LIMIT*2:raise Refusal('invalid_source')
    base=_checked_add(512,_checked_mul(128,count),limit=object_limit,code=object_code)
    fold=_Fold()
    if kind is OwnedMap:
        for name,child in value._items:
            key=_literal_cost(name)
            _checked_add(base+fold.p,key.object_bytes,limit=object_limit,code=object_code)
            pair=_owned_cost(child,_depth+1,object_limit=object_limit-base-fold.p-key.object_bytes,
                             object_code=object_code)
            fold.add(pair,name)
    else:
        for child in value:
            fold.add(_owned_cost(child,_depth+1,object_limit=object_limit-base-fold.p,object_code=object_code))
    return fold.finish()


def _max_scalar_j(value, _depth=0):
    kind=type(value)
    if kind not in (tuple,OwnedMap): return _literal_cost(value).json_bytes
    if _depth>=r.JSON_DEPTH_LIMIT: raise Refusal('invalid_source')
    result=0
    if kind is OwnedMap:
        _owned_map(value)
        for name,child in value._items:
            result=max(result,_literal_cost(name).json_bytes,_max_scalar_j(child,_depth+1))
    else:
        if len(value)>r.METADATA_SCALAR_LIMIT*2: raise Refusal('invalid_source')
        for child in value: result=max(result,_max_scalar_j(child,_depth+1))
    return result


def _metadata_cost(value):
    if type(value) is not MetadataValue: raise Refusal('invalid_source')
    return _owned_cost(value._tagged)


def _runtime_cost(runtime):
    # Actual runtime.validate_runtime owns schema/profile qualification. Reuse
    # its exact immutable result by identity, including every occurrence.
    _fields(runtime,('binding_version','python','dependencies','replicatetable','resources','pint'),'invalid_runtime')
    cost=_owned_cost(runtime)
    _check_cap('runtime',_checked_add(cost.json_bytes,1))
    return cost


_DESCRIPTOR_FIELDS=('dims','shape','dtype','unit','attributes','encoding','selection_status')

def _inspection_cost(inspection,*,object_limit=r.LOGICAL_JOURNEY_LIMIT,object_code='estimated_memory_limit'):
    _fields(inspection,('version','source','dimensions','variables','coordinate_descriptors','attributes'))
    _count(inspection['version'],limit=2)
    if inspection['version']!=2: raise Refusal('invalid_source')
    identity=_fields(inspection['source'],('kind','sha256','size_bytes'))
    if type(identity['kind']) is not str or identity['kind'] not in ('memory','file'):raise Refusal('invalid_source')
    digest=identity['sha256']
    if type(digest) is not str or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise Refusal('invalid_source')
    _count(identity['size_bytes'])
    dims=_owned_map(inspection['dimensions'],maximum=r.SOURCE_DIMENSION_LIMIT)
    for name,length in dims._items:
        validate_name(name); _count(length,limit=r.DIMENSION_LENGTH_LIMIT)
        if not length: raise Refusal('invalid_source')
    metadata_state=_Fold()
    _validate_metadata(inspection['attributes'],metadata_state)
    for field,maximum in (('variables',r.SOURCE_VARIABLE_LIMIT),('coordinate_descriptors',r.SOURCE_DIMENSION_LIMIT)):
        descriptors=_owned_map(inspection[field],maximum=maximum)
        for name,desc in descriptors._items:
            validate_name(name); _fields(desc,_DESCRIPTOR_FIELDS)
            _shape_product(desc['shape']); _names(desc['dims'])
            if len(desc['dims'])!=len(desc['shape']): raise Refusal('invalid_source')
            for dim,length in zip(desc['dims'],desc['shape']):
                if dim not in dims or dims[dim]!=length: raise Refusal('invalid_source')
            _utf8(desc['dtype'],maximum=r.NAME_BYTES_LIMIT)
            validate_unit(desc['unit'],raw_coordinate=field=='coordinate_descriptors')
            _validate_metadata(desc['attributes'],metadata_state)
            _validate_metadata(desc['encoding'],metadata_state)
            _selection_status_cost(desc['selection_status'],coordinate=field=='coordinate_descriptors')
            if field=='coordinate_descriptors' and (name not in dims or desc['dims']!=(name,) or desc['shape']!=(dims[name],)):
                raise Refusal('unsupported_source_storage')
            # V8 role/status shape is closed here. Recomputing its declaration
            # predicate from raw storage is still the source boundary's duty.
    cost=_owned_cost(inspection,object_limit=object_limit,object_code=object_code)
    _check_cap('metadata',_checked_add(cost.json_bytes,1))
    return cost


def _recipe_cost(recipe):
    if type(recipe) is not Recipe: raise Refusal('invalid_recipe')
    f=_Fold(); f.add(NUMBER,'version'); f.add(_owned_cost(recipe.row_dims),'row_dims')
    f.add(_owned_cost(recipe.columns),'columns')
    cost=f.finish(); _check_cap('recipe',_checked_add(cost.json_bytes,1)); return cost


def _names(names,code='invalid_source'):
    if type(names) is not tuple or len(names)>r.RANK_LIMIT: raise Refusal(code)
    for i,name in enumerate(names):
        validate_name(name,code)
        for j in range(i):
            if name==names[j]: raise Refusal(code)
    return names


@dataclass(frozen=True,slots=True)
class _VariableFacts:
    itemsize: int
    cells: int
    nbytes: int
    name: str
    dtype: str
    dims: tuple
    shape: tuple
    def __post_init__(self):
        _count(self.itemsize);_count(self.cells);_count(self.nbytes)
        validate_name(self.name);dtype=numeric_dtype(self.dtype);_names(self.dims)
        cells=_shape_product(self.shape)
        size=1 if dtype.endswith('8') else 2 if dtype.endswith('16') else 4 if dtype.endswith('32') else 8
        if self.itemsize!=size or self.cells!=cells or len(self.dims)!=len(self.shape):raise Refusal('invalid_source')
        if self.nbytes!=_checked_mul(size,cells,limit=r.SELECTED_NUMERIC_BYTES_LIMIT,code='selected_numeric_bytes_limit'):
            raise Refusal('invalid_source')
    def __init_subclass__(cls,**kwargs):raise TypeError('Private resource records are final')


def _variable_facts(name,descriptor,dimensions):
    validate_name(name); _fields(descriptor,_DESCRIPTOR_FIELDS)
    _owned_map(dimensions,maximum=r.SOURCE_DIMENSION_LIMIT)
    for dim,length in dimensions._items:
        validate_name(dim)
        _count(length,limit=r.DIMENSION_LENGTH_LIMIT)
        if not length:raise Refusal('invalid_source')
    dims=_names(descriptor['dims']); shape=descriptor['shape']
    cells=_shape_product(shape)
    if len(dims)!=len(shape): raise Refusal('invalid_source')
    for dim,length in zip(dims,shape):
        if dim not in dimensions or dimensions[dim]!=length: raise Refusal('invalid_source')
    dtype=numeric_dtype(descriptor['dtype'])
    size=1 if dtype.endswith('8') else 2 if dtype.endswith('16') else 4 if dtype.endswith('32') else 8
    nbytes=_checked_mul(cells,size,limit=r.SELECTED_NUMERIC_BYTES_LIMIT,code='selected_numeric_bytes_limit')
    return _VariableFacts(size,cells,nbytes,name,dtype,dims,shape)


@dataclass(frozen=True,slots=True)
class _CoordinateFacts:
    length: int
    max_label_j: int
    max_label_p: int
    max_utf8: int
    sum_utf8: int
    raw_bytes: int
    preselection_j: int
    selected_j: int
    coordinate_p: int
    max_token_j: int
    name: str
    coordinate: Coordinate
    def __post_init__(self):
        for n in (self.length,self.max_label_j,self.max_label_p,self.max_utf8,self.sum_utf8,
                  self.raw_bytes,self.preselection_j,self.selected_j,self.coordinate_p,self.max_token_j):_count(n)
        validate_name(self.name)
        if type(self.coordinate) is not Coordinate or self.length!=len(self.coordinate.values):raise Refusal('invalid_coordinate')
        _check_cap('coordinate_raw',self.raw_bytes);_check_cap('coordinate_canonical',self.preselection_j)
        _check_cap('coordinate_canonical',self.selected_j);_check_cap('coordinate_utf8',self.sum_utf8)
        _check_cap('label',self.max_utf8)
    def __init_subclass__(cls,**kwargs):raise TypeError('Private resource records are final')


def _coordinate_facts(name,coordinate,*,raw_bytes,preselection_j):
    validate_name(name)
    if type(coordinate) is not Coordinate: raise Refusal('invalid_coordinate')
    _check_cap('coordinate_raw',raw_bytes); _check_cap('coordinate_canonical',preselection_j)
    maxj=maxp=maxu=sumu=0; values=_Fold()
    for label in coordinate.values:
        cost=_literal_cost(label); values.add(cost)
        maxj=max(maxj,cost.json_bytes); maxp=max(maxp,cost.object_bytes)
        if type(label) is str:
            u=_utf8(label,maximum=r.LABEL_UTF8_BYTES_LIMIT,code='label_bytes_limit')
            maxu=max(maxu,u); sumu=_checked_add(sumu,u,limit=r.COORDINATE_LABEL_UTF8_BYTES_LIMIT,code='coordinate_bytes_limit')
    f=_Fold(); f.add(_literal_cost(coordinate.dtype),'dtype'); f.add(values.finish(),'values')
    f.add(_owned_cost(coordinate.sorted_indices),'sorted_indices'); pair=f.finish()
    selected=_checked_add(pair.json_bytes,1); _check_cap('coordinate_canonical',selected)
    return _CoordinateFacts(len(coordinate.values),maxj,maxp,maxu,sumu,raw_bytes,
        preselection_j,selected,pair.object_bytes,max(maxj,32,_literal_cost(coordinate.dtype).json_bytes),name,coordinate)


def _coordinate_find(name,coordinates):
    if type(coordinates) is not tuple or len(coordinates)>r.RANK_LIMIT: raise Refusal('invalid_coordinate')
    for fact in coordinates:
        if type(fact) is not _CoordinateFacts: raise Refusal('invalid_coordinate')
        if fact.name==name: return fact
    raise Refusal('missing_coordinate')


def _key_bound(names,coordinates):
    _names(names); f=_Fold()
    for name in names:
        c=_coordinate_find(name,coordinates)
        f.add(_JP(c.max_label_j,c.max_label_p),name)
    return f.finish()


def _coordinates_cost(coordinates):
    if type(coordinates) is not tuple or len(coordinates)>r.RANK_LIMIT: raise Refusal('invalid_coordinate')
    f=_Fold(); previous=None
    for c in coordinates:
        if type(c) is not _CoordinateFacts: raise Refusal('invalid_coordinate')
        if previous is not None and previous>=c.name: raise Refusal('invalid_coordinate')
        f.add(_JP(c.selected_j-1,c.coordinate_p),c.name); previous=c.name
    return f.finish()


@dataclass(frozen=True,slots=True)
class _SourceScalars:
    source_base: int=0
    descriptor_j: int=0
    descriptor_p: int=0
    raw_coordinate_j: int=0
    selected_coordinate_j: int=0
    coordinate_p: int=0
    coordinate_raw: int=0
    coordinate_utf8: int=0
    selected_numeric: int=0
    max_scalar_j: int=0
    def __post_init__(self):
        for n in (self.source_base,self.descriptor_j,self.descriptor_p,self.raw_coordinate_j,
                  self.selected_coordinate_j,self.coordinate_p,self.coordinate_raw,self.coordinate_utf8,
                  self.selected_numeric,self.max_scalar_j):_count(n)
    def __init_subclass__(cls,**kwargs):raise TypeError('Private resource records are final')


def _coordinate_totals(coordinates):
    cost=_coordinates_cost(coordinates)
    pre=selected=raw=utf8=maxj=0
    for c in coordinates:
        pre=_checked_add(pre,c.preselection_j,limit=r.COORDINATE_CANONICAL_BYTES_LIMIT,code='coordinate_bytes_limit')
        selected=_checked_add(selected,c.selected_j,limit=r.COORDINATE_CANONICAL_BYTES_LIMIT,code='coordinate_bytes_limit')
        raw=_checked_add(raw,c.raw_bytes,limit=r.COORDINATE_RAW_BYTES_LIMIT,code='coordinate_bytes_limit')
        utf8=_checked_add(utf8,c.sum_utf8,limit=r.COORDINATE_LABEL_UTF8_BYTES_LIMIT,code='coordinate_bytes_limit')
        maxj=max(maxj,c.max_token_j)
    return _SourceScalars(raw_coordinate_j=pre,selected_coordinate_j=selected,
        coordinate_p=cost.object_bytes,coordinate_raw=raw,coordinate_utf8=utf8,max_scalar_j=maxj)


def _fixed_coordinate_preflight(dtype,length):
    if type(dtype) is not str or not (dtype.startswith('|S') or dtype.startswith('<U')):
        raise Refusal('invalid_coordinate')
    digits=dtype[2:]
    if not digits or len(digits)>4 or not digits.isascii() or not digits.isdecimal() or digits[0]=='0':
        raise Refusal('invalid_coordinate')
    width=int(digits)
    _count(width,'invalid_coordinate',limit=4096); _shape_product((length,))
    raw=_checked_mul(width*(1 if dtype[1]=='S' else 4),length,
        limit=r.COORDINATE_RAW_BYTES_LIMIT,code='coordinate_bytes_limit')
    label_width=width if dtype[1]=='S' else min(4096,4*width)
    labels=_checked_mul(label_width,length,limit=r.COORDINATE_LABEL_UTF8_BYTES_LIMIT,code='coordinate_bytes_limit')
    j=_container_cost(length,_checked_mul(length,6*label_width+2),0).json_bytes
    _check_cap('coordinate_canonical',j)
    # Selected dtype/value/permutation cost must also pass before decoding.
    f=_Fold(); f.add(_literal_cost('<U'+digits),'dtype')
    f.add(_JP(j,0),'values'); f.add(_container_cost(length,32*length,0),'sorted_indices')
    _check_cap('coordinate_canonical',f.finish().json_bytes+1)
    return raw,j,labels


def _header_charge(rank,measured_header_bytes):
    _count(rank,limit=r.RANK_LIMIT); _count(measured_header_bytes,limit=r.SOURCE_MEMORY_BASE_LIMIT)
    return max(512+128*rank,measured_header_bytes)


def _fold_source_charge(total,additional):
    """Incremental retained-memory-source base charge, not a file-base cap."""
    return _checked_add(total,additional,limit=r.SOURCE_MEMORY_BASE_LIMIT,code='source_bytes_limit')


def _owner_charge(kind,name,logical_bytes,terminal_kind,terminal_payload_bytes,headers,object_scalar_objects_bytes):
    if type(kind) is not str or kind not in ('coordinate','variable'): raise Refusal('invalid_source')
    validate_name(name)
    if type(terminal_kind) is not str or terminal_kind not in ('ndarray','bytes'): raise Refusal('unsupported_source_storage')
    if type(headers) is not tuple or not 1<=len(headers)<=r.OWNER_CHAIN_LIMIT: raise Refusal('unsupported_source_storage')
    _count(logical_bytes); _count(terminal_payload_bytes); _count(object_scalar_objects_bytes)
    h=0
    for charge in headers: h=_fold_source_charge(h,charge)
    terminal=_fold_source_charge(terminal_payload_bytes,128 if terminal_kind=='bytes' else 0)
    terminal=_fold_source_charge(terminal,object_scalar_objects_bytes)
    _fold_source_charge(terminal,h)
    return OwnedMap._from_checked((('header_bytes',h),('kind',kind),('logical_bytes',logical_bytes),
                                  ('name',name),('terminal_bytes',terminal)))


def _binding(kind,base,owners,descriptor_bytes):
    return OwnedMap._from_checked((('base_bytes',base),('descriptor_bytes',descriptor_bytes),
                                  ('kind',kind),('owners',owners)))


def _check_source_base(kind,base):
    if type(kind) is not str or kind not in ('memory','file'):raise Refusal('invalid_source')
    #128MiB bounds memory ownership, whereas the file cap bounds actual bytes.
    # A full file base is retained for combined admission. Its512MiB check is
    # only the existing necessary journey domain, not a second source ceiling.
    return _check_cap('source_base' if kind=='memory' else 'journey',base)


def _file_binding(inspection,file_size):
    _check_cap('source_file',file_size)
    base=_checked_add(file_size,r.MODEL_FIXED_BYTES,limit=r.LOGICAL_JOURNEY_LIMIT,code='estimated_memory_limit')
    descriptor=_inspection_cost(inspection,object_limit=r.LOGICAL_JOURNEY_LIMIT-base,object_code='estimated_memory_limit')
    base=_checked_add(base,descriptor.object_bytes,limit=r.LOGICAL_JOURNEY_LIMIT,code='estimated_memory_limit')
    return _binding('file',base,(),descriptor.object_bytes)


def _memory_binding(inspection,owners,stock_headers):
    if type(owners) is not tuple or len(owners)>r.SOURCE_VARIABLE_LIMIT+r.SOURCE_DIMENSION_LIMIT:
        raise Refusal('invalid_source')
    # Adapter folds each owner before retaining this already-model-charged
    # OwnerCharge tuple. It never retains one chain per source variable.
    base=_fold_source_charge(r.MODEL_FIXED_BYTES,stock_headers)
    previous=None
    for owner in owners:
        _fields(owner,('kind','name','terminal_bytes','header_bytes','logical_bytes'))
        if type(owner['kind']) is not str or owner['kind'] not in ('coordinate','variable'): raise Refusal('invalid_source')
        validate_name(owner['name']); key=(owner['kind'],owner['name'])
        if previous is not None and previous>=key: raise Refusal('invalid_source')
        previous=key
        _count(owner['logical_bytes'])
        base=_fold_source_charge(base,owner['terminal_bytes'])
        base=_fold_source_charge(base,owner['header_bytes'])
    descriptor=_inspection_cost(inspection,object_limit=r.SOURCE_MEMORY_BASE_LIMIT-base,object_code='source_bytes_limit')
    base=_fold_source_charge(base,descriptor.object_bytes)
    return _binding('memory',base,owners,descriptor.object_bytes)


@dataclass(frozen=True,slots=True)
class _CompilationInput:
    def __init_subclass__(cls,**kwargs):raise TypeError('Private resource records are final')
    source: OwnedMap
    binding: OwnedMap
    recipe: Recipe
    coordinates: tuple
    runtime: OwnedMap
    units: tuple
    def __post_init__(self):
        _inspection_cost(self.source)
        _fields(self.binding,('kind','base_bytes','owners','descriptor_bytes'))
        _check_source_base(self.binding['kind'],self.binding['base_bytes'])
        if self.binding['descriptor_bytes']!=_inspection_cost(self.source).object_bytes:
            raise Refusal('invalid_source')
        if self.binding['kind']!=self.source['source']['kind']: raise Refusal('invalid_source')
        _recipe_cost(self.recipe); _coordinates_cost(self.coordinates); _runtime_cost(self.runtime)
        if type(self.units) is not tuple or len(self.units)!=len(self.recipe.columns): raise Refusal('invalid_source')
        for pair in self.units:
            if type(pair) is not tuple or len(pair)!=2: raise Refusal('invalid_source')
            _unit_cost(pair[0])
            if pair[1] is not None: _unit_cost(pair[1])


def _unit_cost(operation):
    _fields(operation,('source_unit','target_unit','scale','offset','parsed_source','parsed_target','definition_graph'))
    validate_unit(operation['source_unit']); validate_unit(operation['target_unit'])
    for key in ('scale','offset'):
        value=operation[key]
        if type(value) not in (int,float): raise Refusal('invalid_source')
        _literal_cost(value)
    if operation['scale']<=0: raise Refusal('invalid_source')
    graph=operation['definition_graph']
    if type(graph) is not tuple or len(graph)>128: raise Refusal('invalid_source')
    terms=0
    for parsed in (operation['parsed_source'],operation['parsed_target']):
        if parsed is not None: _unit_terms(parsed)
    for node in graph:
        _fields(node,('name','converter','scale','offset','is_base','reference'))
        validate_name(node['name']); _unit_terms(node['reference'])
        terms=_checked_add(terms,len(node['reference']),limit=512,code='invalid_source')
        if type(node['converter']) is not str or node['converter'] not in ('ScaleConverter','OffsetConverter'):
            raise Refusal('invalid_source')
        if type(node['is_base']) is not bool: raise Refusal('invalid_source')
        for key in ('scale','offset'):
            if type(node[key]) not in (int,float): raise Refusal('invalid_source')
            _literal_cost(node[key])
    cost=_owned_cost(operation)
    _count(cost.json_bytes+1,'metadata_bytes_limit',limit=r.UNIT_GRAPH_JSON_LIMIT)
    return cost


def _unit_terms(terms):
    if type(terms) is not tuple or len(terms)>512: raise Refusal('invalid_source')
    previous=None
    for term in terms:
        if type(term) is not tuple or len(term)!=2: raise Refusal('invalid_source')
        validate_name(term[0]); _literal_cost(term[1])
        if type(term[1]) not in (int,float): raise Refusal('invalid_source')
        if previous is not None and previous>=term[0]: raise Refusal('invalid_source')
        previous=term[0]


_ENCODING_REASONS=('calendar_metadata','reference_time_units','scale_factor_metadata','add_offset_metadata',
                   'unsigned_metadata','fill_value_metadata','missing_value_metadata')


def _selection_status_cost(status,*,coordinate):
    if type(coordinate) is not bool:raise Refusal('invalid_source')
    if status is None:return _literal_cost(None)
    _fields(status,('status','code','reasons'))
    if type(status['status']) is not str or status['status']!='unsupported':raise Refusal('invalid_source')
    expected='unsupported_coordinate_encoding' if coordinate else 'unsupported_source_encoding'
    if type(status['code']) is not str or status['code']!=expected:raise Refusal('invalid_source')
    reasons=status['reasons']
    if type(reasons) is not tuple or not 1<=len(reasons)<=(7 if coordinate else 5):raise Refusal('invalid_source')
    previous=-1 if coordinate else 1
    for reason in reasons:
        if type(reason) is not str or reason not in _ENCODING_REASONS:raise Refusal('invalid_source')
        position=_ENCODING_REASONS.index(reason)
        if position<=previous:raise Refusal('invalid_source')
        previous=position
    return _owned_cost(status)


def _metadata_fields(value,names,*,raw=False):
    if type(value) is OwnedMap: return _fields(value,names)
    if not raw or type(value) is not dict or len(value)!=len(names):
        raise Refusal('invalid_source')
    for key in value:
        if type(key) is not str: raise Refusal('invalid_source')
    for key in value:
        if key not in names: raise Refusal('invalid_source')
    return value


def _validate_metadata(value,state,depth=0,*,raw=False):
    """Validate existing tags in place, preserving scalar/container distinctions.

    It deliberately does not untag, infer a declaration, import NumPy, or
    reconstruct another model. One existing fold frame holds aggregate counts.
    """
    if type(raw) is not bool: raise Refusal('invalid_source')
    if raw and type(value) is dict:
        if len(value)>2: raise Refusal('invalid_source')
        for key in value:
            if type(key) is not str: raise Refusal('invalid_source')
    else: _owned_map(value,maximum=2)
    if 'type' not in value or type(value['type']) is not str:raise Refusal('invalid_source')
    tag=value['type']
    if tag in ('list','map'):
        _metadata_fields(value,('type','items'),raw=raw)
        if depth>=r.METADATA_DEPTH_LIMIT:raise Refusal('metadata_bytes_limit')
        state.entries=_checked_add(state.entries,1,limit=r.METADATA_CONTAINER_LIMIT,code='metadata_bytes_limit')
        items=value['items'];maximum=r.METADATA_MAP_LIMIT if tag=='map' else r.METADATA_SEQUENCE_LIMIT
        sequence_types=(tuple,list) if raw else (tuple,)
        if type(items) not in sequence_types:raise Refusal('invalid_source')
        _count(len(items),'metadata_bytes_limit',limit=maximum)
        previous=None
        for item in items:
            if tag=='map':
                if type(item) not in sequence_types or len(item)!=2:raise Refusal('invalid_source')
                _utf8(item[0],maximum=r.LABEL_UTF8_BYTES_LIMIT)
                if previous is not None and previous>=item[0]:raise Refusal('invalid_source')
                previous=item[0]
                state.index=_checked_add(state.index,1,limit=r.METADATA_SCALAR_LIMIT,code='metadata_bytes_limit')
                _validate_metadata(item[1],state,depth+1,raw=raw)
            else:_validate_metadata(item,state,depth+1,raw=raw)
        return
    state.index=_checked_add(state.index,1,limit=r.METADATA_SCALAR_LIMIT,code='metadata_bytes_limit')
    if tag=='null':_metadata_fields(value,('type',),raw=raw);return
    _metadata_fields(value,('type','value'),raw=raw);scalar=value['value']
    if tag=='bool' and type(scalar) is bool:return
    if tag=='int' and type(scalar) is int:_literal_cost(scalar);return
    if tag=='float' and type(scalar) is float:_literal_cost(scalar);return
    if tag=='str' and type(scalar) is str:_utf8(scalar,maximum=r.LABEL_UTF8_BYTES_LIMIT);return
    if tag=='float_special' and type(scalar) is str and scalar in ('nan','+inf','-inf'):return
    raise Refusal('invalid_source')
