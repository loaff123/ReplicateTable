"""Memory compiler, immutable plan2 binding and strict persisted reanchoring.

Public boundaries frozen by API-SCHEMAS section 2:

    compile_plan(source: SourceSnapshot, recipe: Recipe) -> BoundPlan
    load_plan(raw: bytes, source: SourceSnapshot) -> BoundPlan

The resulting immutable BoundPlan has exactly the plan2 serialized fields:
version, formula_version, source, recipe, runtime, coordinates, selected,
columns, resource_binding, estimates. Its private ``_source`` is a real
SourceSnapshot whose arrays are empty and whose exact selected Coordinate
instances are identical to the plan's children. No earlier prepared snapshot,
materialized array map, source scan, topology table, or compilation-input
carrier survives merely to back the plan.

Compilation consumes the actual supplied eager source under its original
required-input closure. It applies held-identity/phase/declaration precedence,
complete standalone source and compiler reservations, a fresh actual runtime
gate, one stock-unit pass with at most 64 attempts, the existing unchanged
Formula2 projection, then full baseline plus actual cache admission before
exposure. Exact raw assertions precede stock unit qualification. Neither a
structural model nor a saved estimate establishes source or runtime authority.

Loading uses the one existing bounded strict parser, retains the explicit raw
input and parsed/Recipe forests under their route-local charges through their
actual frame lifetimes, compares held expected identity before source phase,
and recompiles actual semantics and complete unit graphs. Reanchoring requires
exact saved/fresh resource_binding equality, including shrinkage and owner
redistribution. Saved fields are compared; they are never silently regenerated.

Integration in source.py supplies materialize_source(source, plan). Integration
in admission.py extends _required_inputs/_guard only for the real plan and
snapshot slots, preserving the original outer closure. The anchor receives
saved baseline credit only after exact fresh non-cache binding equality.
Distinct equivalent supplied sources add their complete base; known caches add
call-local C. Same Dataset handles deduplicate solely by identity. Footprint
validation of unused A is not content proof; the consumed B supplies all
preparation, materialization and semantic content checks.

This increment provides only the eager memory route. File references, native
supervision, results, execution, bundles, explanation and CLI remain outside
its implemented API; no fake carrier or public bypass is introduced.
"""

from contextvars import ContextVar
from . import resources as r
from .codec import (OwnedMap, freeze, thaw, primitive_bounds, preflight_json,
                    canonical_bytes, iter_json_chunks, strict_loads, json_prepass)
from .errors import Refusal
from .model import (BoundPlan, SourceSnapshot, SourceIdentity, Recipe, _CoordinateMap,
                    _typed_map_validate, _source_identity_check, exact_int)
from ._resource_inputs import (_CompilationInput, _coordinate_facts, _owned_cost,
                               _recipe_cost, _inspection_cost, _unit_cost)
from ._resource_bounds import ESTIMATE_KEYS, _checked_add, _checked_mul, _count

_FIELDS = ('version','formula_version','source','recipe','runtime','coordinates',
           'selected','columns','resource_binding','estimates')
_COLUMN_FIELDS = ('name','source','source_dtype','input_dims','input_shape',
                  'final_dims','broadcast','output_dtype','unit_operation','weight','stages')
_STAGE_FIELDS = ('name','dims','op','missing','min_count','input_dims','input_shape',
                 'remaining_dims','remaining_shape','support_dims','support_count','support_start')
_UNIT_FIELDS = ('source_unit','target_unit','scale','offset','parsed_source',
                'parsed_target','definition_graph')
_ROUTE = ContextVar('replicatetable_compiler_live_inputs', default=None)


def _record(value, fields, code='invalid_plan'):
    if type(value) is OwnedMap:
        from ._resource_inputs import _fields
        return _fields(value,fields,code)
    from .model import _fields
    _fields(value, fields, code)
    return value


def _same(left, right):
    """Bounded primitive equality preserving integer/float and signed zero."""
    ltype, rtype = type(left), type(right)
    if ltype in (dict, OwnedMap) and rtype in (dict, OwnedMap):
        return (len(left) == len(right) and all(type(k) is str and k in right and
                _same(value, right[k]) for k, value in left.items()))
    if ltype in (list, tuple) and rtype in (list, tuple):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if ltype is not rtype:
        return False
    if ltype is float:
        return left.hex() == right.hex()
    return left == right


def _owned(fields):
    return OwnedMap._from_checked(tuple(sorted(fields)))


def _coordinates_projection(coordinates):
    return {name: coordinate._projection() for name, coordinate in coordinates.items()}


def _plan_projection(plan):
    return dict(version=plan.version, formula_version=plan.formula_version,
                source=plan.source._projection(), recipe=plan.recipe._projection(),
                runtime=plan.runtime, coordinates=_coordinates_projection(plan.coordinates),
                selected=plan.selected, columns=plan.columns,
                resource_binding=plan.resource_binding, estimates=plan.estimates)


def _check_plan_parts(version, formula_version, identity, recipe, runtime,
                      coordinates, selected, columns, binding, estimates, backing):
    """Structural only; no source storage/Pint/discovery authority is granted."""
    from .source import _snapshot_exact, _recipe_exact, _select, _selection_snapshot
    from .runtime import validate_runtime
    from ._resource_estimates import _validate_binding
    from .units import _check_operation
    try:
        exact_int(version,'invalid_plan',minimum=2,maximum=2)
        exact_int(formula_version,'invalid_plan',minimum=2,maximum=2)
        _source_identity_check(identity); _recipe_exact(recipe)
        _snapshot_exact(backing)
        _typed_map_validate(coordinates,_CoordinateMap)
        if backing.identity != identity or len(backing.arrays): raise Refusal('invalid_plan')
        selection = _select(backing,recipe)
        _selection_snapshot(backing,selection,expected=identity)
        if tuple(coordinates) != selection.dimensions or tuple(backing.coordinates) != selection.dimensions:
            raise Refusal('invalid_plan')
        for name, coordinate in coordinates.items():
            if backing.coordinates[name] is not coordinate: raise Refusal('invalid_plan')
        _record(selected,('variables','dimensions','numeric_bytes'))
        if not _same(selected['variables'],selection.variables) or not _same(selected['dimensions'],selection.dimensions):
            raise Refusal('invalid_plan')
        _count(selected['numeric_bytes'],'invalid_plan',limit=r.SELECTED_NUMERIC_BYTES_LIMIT)
        _record(binding,('kind','base_bytes','owners','descriptor_bytes'))
        # Pure validation accepts exact public dict/list shapes before freezing.
        primitive_bounds(binding,code='invalid_plan')
        _check_saved_binding(binding)
        _record(estimates,ESTIMATE_KEYS)
        for name in ESTIMATE_KEYS: _count(estimates[name],'invalid_plan')
        if estimates['formula_version'] != 2: raise Refusal('invalid_plan')
        if type(columns) not in (list,tuple) or len(columns) != len(recipe.columns):
            raise Refusal('invalid_plan')
        for c in columns:
            _record(c,_COLUMN_FIELDS)
            for field in ('unit_operation',):
                operation = _record(c[field],_UNIT_FIELDS)
                _check_operation(*(operation[key] for key in _UNIT_FIELDS))
            if c['weight'] is not None:
                w = _record(c['weight'],('source','dtype','dims','shape','unit_operation'))
                operation = _record(w['unit_operation'],_UNIT_FIELDS)
                _check_operation(*(operation[key] for key in _UNIT_FIELDS))
            if type(c['stages']) not in (list,tuple) or len(c['stages']) > 2:
                raise Refusal('invalid_plan')
            for stage in c['stages']: _record(stage,_STAGE_FIELDS)
        projection = dict(version=version,formula_version=formula_version,
            source=identity._projection(),recipe=recipe._projection(),runtime=runtime,
            coordinates=_coordinates_projection(coordinates),selected=selected,
            columns=columns,resource_binding=binding,estimates=estimates)
        preflight_json(projection,limit=r.METADATA_BYTES_LIMIT)
        validate_runtime(runtime)
        # Exact topology is checked against the bound immutable descriptors.
        _check_compiled_fields(backing,recipe,selected,columns)
    except (AttributeError,KeyError,TypeError):
        raise Refusal('invalid_plan') from None
    except Refusal as error:
        if error.code in ('estimated_memory_limit','metadata_bytes_limit'): raise
        raise Refusal('invalid_plan') from None


def _plan_exact(plan):
    if type(plan) is not BoundPlan: raise Refusal('invalid_plan_input')
    try:
        fields = tuple(object.__getattribute__(plan,name) for name in _FIELDS)
        backing = object.__getattribute__(plan,'_source')
    except AttributeError:
        raise Refusal('invalid_plan_input') from None
    _check_plan_parts(*fields,backing)
    return plan


def _plan_selected(plan):
    from .source import _Selection
    _plan_exact(plan)
    return _Selection(plan.selected['variables'],plan.selected['dimensions'],plan.recipe.row_dims)


def _bind_plan_snapshot(plan,source):
    """Bind all held descriptor semantics before using selected slot capacity.

    This is an argument-consistency check, not source authority. The source
    boundary still compares actual B against this snapshot and streams actual
    selected labels against the plan before any new selected models are made.
    Nothing hashes or semantically compares unused anchor A.
    """
    if not _same(plan._source._projection(),source._projection()):
        raise Refusal('plan_binding_mismatch')
    for name,coordinate in source.coordinates.items():
        if not _same(coordinate._projection(),plan.coordinates[name]._projection()):
            raise Refusal('plan_binding_mismatch')


def _topology_preflight(source, recipe):
    """Descriptor topology and exact assertions, before stock qualification."""
    for column in recipe.columns:
        descriptor = source.variables[column['source']]
        current = descriptor['dims']
        if column['source_unit'] != descriptor['unit']:
            raise Refusal('missing_unit_assertion' if column['source_unit'] is None and
                          descriptor['unit'] is not None else 'source_unit_mismatch')
        for index, stage in enumerate(column['stages']):
            if any(name not in current or name in recipe.row_dims for name in stage['dims']):
                raise Refusal('invalid_recipe')
            if stage['op'] == 'weighted_mean':
                if index: raise Refusal('unsupported_later_stage_weights')
                if stage['weights'] not in source.variables: raise Refusal('invalid_weights')
                weight = source.variables[stage['weights']]
                if any(name not in descriptor['dims'] for name in weight['dims']):
                    raise Refusal('invalid_weights')
                if stage['weight_unit'] != weight['unit']: raise Refusal('weight_unit_mismatch')
            current = tuple(name for name in current if name not in stage['dims'])
        if any(name not in recipe.row_dims for name in current): raise Refusal('residual_dimension')
        if column['broadcast'] != tuple(name for name in recipe.row_dims if name not in current):
            raise Refusal('unapproved_broadcast')


def _shape(source, names):
    return tuple(source.dimensions[name] for name in names)


def _product(shape):
    value = 1
    for length in shape: value = _checked_mul(value,length,limit=r.SHAPE_PRODUCT_LIMIT,code='invalid_plan')
    return value


def _check_compiled_fields(source, recipe, selected, columns):
    """Compare the finite compiled topology without building another table."""
    from .model import numeric_dtype
    _topology_preflight(source,recipe)
    numeric = 0
    for name in selected['variables']:
        d = source.variables[name]
        from ._resource_inputs import _variable_facts
        numeric += _variable_facts(name,d,source.dimensions).nbytes
    if numeric != selected['numeric_bytes']: raise Refusal('invalid_plan')
    offset = 0
    for recipe_column,c in zip(recipe.columns,columns):
        d = source.variables[recipe_column['source']]
        current = d['dims']; operation = c['unit_operation']
        for field,wanted in (('name',recipe_column['name']),('source',recipe_column['source']),
                ('source_dtype',d['dtype']),('input_dims',d['dims']),('input_shape',d['shape']),
                ('broadcast',recipe_column['broadcast'])):
            if not _same(c[field],wanted): raise Refusal('invalid_plan')
        if operation['source_unit'] != d['unit'] or operation['target_unit'] != recipe_column['target_unit']:
            raise Refusal('invalid_plan')
        if len(c['stages']) != len(recipe_column['stages']): raise Refusal('invalid_plan')
        for raw,compiled in zip(recipe_column['stages'],c['stages']):
            remaining = tuple(name for name in current if name not in raw['dims'])
            count = _product(_shape(source,remaining))
            for field,wanted in tuple((key,raw[key]) for key in ('name','dims','op','missing','min_count'))+(
                    ('input_dims',current),('input_shape',_shape(source,current)),
                    ('remaining_dims',remaining),('remaining_shape',_shape(source,remaining)),
                    ('support_dims',tuple(sorted(remaining))),('support_count',count),('support_start',offset)):
                if not _same(compiled[field],wanted): raise Refusal('invalid_plan')
            offset += count; current = remaining
        if not _same(c['final_dims'],current): raise Refusal('invalid_plan')
        wanted = d['dtype'] if not c['stages'] and operation['scale'] == 1 and operation['offset'] == 0 else 'float64'
        if type(c['output_dtype']) is not str or c['output_dtype'] != wanted: raise Refusal('invalid_plan')
        if recipe_column['stages'] and recipe_column['stages'][0]['op'] == 'weighted_mean':
            weight_recipe = recipe_column['stages'][0]; w = c['weight']
            if w is None: raise Refusal('invalid_plan')
            desc = source.variables[weight_recipe['weights']]
            for key,wanted in (('source',weight_recipe['weights']),('dtype',desc['dtype']),
                               ('dims',desc['dims']),('shape',desc['shape'])):
                if not _same(w[key],wanted): raise Refusal('invalid_plan')
            if w['unit_operation']['source_unit'] != desc['unit'] or w['unit_operation']['target_unit'] != 'dimensionless':
                raise Refusal('invalid_plan')
        elif c['weight'] is not None: raise Refusal('invalid_plan')


def _coordinate_input(source):
    """Read only qualified layout; label costs come from owned plan coordinates.

    On the unused-anchor path, this neither hashes nor semantically compares
    current coordinate contents. Fresh full binding equality precedes its use.
    """
    from ._source_stock import _stock_cursor
    result = []
    for name,coordinate in source.coordinates.items():
        cursor = _stock_cursor(source._handle,name)
        raw = 8*len(coordinate.values) if type(cursor.data) is range else cursor.data.nbytes
        object_backing = type(cursor.data) is not range and cursor.data.dtype.kind == 'O'
        del cursor
        values = _owned_cost(coordinate.values)
        if object_backing:
            from .codec import utf8_length
            raw += sum(utf8_length(value,'invalid_coordinate') for value in coordinate.values)
        result.append(_coordinate_facts(name,coordinate,raw_bytes=raw,preselection_j=values.json_bytes+1))
    return tuple(result)


def _compilation_input(source, recipe, binding, runtime, units):
    return _CompilationInput(source._projection(),binding,recipe,_coordinate_input(source),runtime,units)


def _estimate_plan(plan):
    from ._resource_estimates import _estimate_compilation
    units = tuple((c['unit_operation'],None if c['weight'] is None else c['weight']['unit_operation'])
                  for c in plan.columns)
    actual = _estimate_compilation(_compilation_input(plan._source,plan.recipe,
                                  plan.resource_binding,plan.runtime,units))
    if not _same(actual,plan.estimates): raise Refusal('invalid_plan')
    return actual['estimated_memory_bytes']


class _RouteScope:
    """Actual retained compiler/load inputs, never a caller-supplied permit."""
    __slots__ = ('recipe','raw','saved','extra','unit_objects','_token','_entered')
    def __init__(self,recipe,raw=None,saved=None):
        self.recipe=recipe; self.raw=raw; self.saved=saved
        self.extra = (0 if raw is None else len(raw)) + (0 if saved is None else primitive_bounds(saved,code='invalid_plan').object_bytes)
        self.unit_objects=0; self._token=None; self._entered=False
    def __enter__(self):
        if self._entered: raise Refusal('invalid_plan_input')
        self._entered=True
        outer=_ROUTE.get()
        if outer is not None:
            if outer.recipe is not self.recipe: raise Refusal('invalid_plan_input')
            return outer
        self._token=_ROUTE.set(self)
        return self
    def __exit__(self,*args):
        token=self._token; self._token=None
        if token is not None: _ROUTE.reset(token)
        self.recipe=self.raw=self.saved=None


def _route_extra():
    active=_ROUTE.get()
    return 0 if active is None else active.extra+active.unit_objects


def _compiler_preflight(source,recipe,selection):
    from .source import (_memory_prepass,_compare_topology,_selected_declarations,
                         _standalone_guard)
    prepass=_memory_prepass(source._handle)
    _compare_topology(source._handle,source)
    _selected_declarations(source._handle,selection)
    _standalone_guard(prepass,held=source,recipe=recipe)


def _compiler_reserve(source,recipe):
    from .source import _memory_prepass,_standalone_guard
    _standalone_guard(_memory_prepass(source._handle),held=source,recipe=recipe)


def _unit_projection(operation):
    return _owned(operation._projection().items())


def _qualify_units(source,recipe,route=None,expected=None):
    from .units import _StockUnitContext, qualify_conversion, qualify_weight_unit
    pairs=[]
    with _StockUnitContext() as context:
        for index,c in enumerate(recipe.columns):
            measurement=_unit_projection(qualify_conversion(c['source_unit'],c['target_unit'],context=context))
            weight=None
            if c['stages'] and c['stages'][0]['op']=='weighted_mean':
                weight=_unit_projection(qualify_weight_unit(c['stages'][0]['weight_unit'],context=context))
            if expected is not None:
                want=expected.columns[index]
                if not _same(measurement,want['unit_operation']) or not _same(weight,
                        None if want['weight'] is None else want['weight']['unit_operation']):
                    raise Refusal('plan_binding_mismatch')
            else:
                if route is not None:
                    route.unit_objects += _unit_cost(measurement).object_bytes
                    if weight is not None: route.unit_objects += _unit_cost(weight).object_bytes
                    _compiler_reserve(source,recipe)
                pairs.append((measurement,weight))
            del measurement,weight
    return tuple(pairs)


def _compile_columns(inp):
    from ._resource_estimates import _derive_topology,_selected_numeric
    topology=_derive_topology(inp)
    selected=_owned((('variables',tuple(v.name for v in topology[0])),
                     ('dimensions',topology[3]),('numeric_bytes',_selected_numeric(topology))))
    columns=[]
    for c in topology[1]:
        stages=[]
        for index in range(c.stage_begin,c.stage_begin+c.stage_count):
            s=topology[2][index]
            fields=[(key,s.recipe_stage[key]) for key in ('name','dims','op','missing','min_count')]
            fields.extend((('input_dims',s.input_dims),('input_shape',tuple(inp.source['dimensions'][d] for d in s.input_dims)),
                ('remaining_dims',s.remaining_dims),('remaining_shape',tuple(inp.source['dimensions'][d] for d in s.remaining_dims)),
                ('support_dims',s.support_dims),('support_count',s.output_cells),('support_start',s.support_start)))
            stages.append(_owned(fields))
        weight=None if c.weight is None else _owned((('source',c.weight.name),('dtype',c.weight.dtype),
                    ('dims',c.weight.dims),('shape',c.weight.shape),('unit_operation',c.weight_unit_operation)))
        columns.append(_owned((('name',c.recipe_column['name']),('source',c.measurement.name),
            ('source_dtype',c.measurement.dtype),('input_dims',c.input_dims),('input_shape',c.measurement.shape),
            ('final_dims',c.final_dims),('broadcast',c.broadcast),('output_dtype',c.output_dtype),
            ('unit_operation',c.unit_operation),('weight',weight),('stages',tuple(stages)))))
    return selected,tuple(columns)


def _compile_memory(source,recipe,expected_runtime=None,saved_binding=None):
    from . import runtime
    from .source import (_selected_start,_prepare_memory,_scan_memory,_owned_attempt,
                         _raise_owned)
    from .admission import _required_inputs,_ACTIVE,_guard
    from ._resource_estimates import _estimate_compilation
    active=_ACTIVE.get()
    if active is not None and active.plan is not None: raise Refusal('invalid_plan_input')
    selection=_selected_start(source,recipe)
    with _required_inputs(snapshot=source), _RouteScope(recipe) as route:
        _compiler_preflight(source,recipe,selection)
        if saved_binding is not None:
            from .admission import _require_binding
            _require_binding(source._handle,saved_binding)
        actual_runtime=runtime.runtime_identity() if expected_runtime is None else runtime.require_runtime(expected_runtime)
        _topology_preflight(source,recipe)
        prepared=_prepare_memory(source,recipe)
        units=_qualify_units(prepared,recipe,route)
        scan=_scan_memory(source._handle,existing=source,selection=selection,returning=prepared,recipe=recipe)
        binding,cache=scan.binding,scan.cache_bytes
        del scan
        inp=_compilation_input(prepared,recipe,binding,actual_runtime,units)
        estimates=_estimate_compilation(inp)
        route.unit_objects=0
        _guard('compile',baseline=estimates['estimated_memory_bytes']+cache+_recipe_cost(recipe).object_bytes)
        selected,columns=_compile_columns(inp)
        del inp,units
        plan=BoundPlan(version=2,formula_version=2,source=source.identity,recipe=recipe,
            runtime=actual_runtime,coordinates=prepared.coordinates,selected=selected,columns=columns,
            resource_binding=binding,estimates=estimates,_source=prepared)
        # No fresh scan tuple crosses the later active-plan guard boundary.
        del binding,selected,columns,prepared
        _scan_memory(source._handle,existing=source,selection=selection,recipe=recipe)
        runtime.require_runtime(actual_runtime)
    with _required_inputs(plan=plan,snapshot=source):
        if _guard('compile')+_recipe_cost(recipe).object_bytes>r.LOGICAL_JOURNEY_LIMIT:
            raise Refusal('estimated_memory_limit')
    return plan


def compile_plan(source,recipe):
    from .source import _owned_attempt,_raise_owned
    result,error=_owned_attempt(_compile_memory,source,recipe)
    source=recipe=None
    if error is not None: _raise_owned(error)
    return result


def _load_source_base(source):
    from .source import _snapshot_exact,_memory_prepass,_standalone_measure
    _snapshot_exact(source)
    if source.identity.kind!='memory': raise Refusal('unsupported_source_storage')
    _,total=_standalone_measure(_memory_prepass(source._handle),held=source)
    from .admission import _bundle_reader_extra
    from ._resource_bounds import _checked_add
    return _checked_add(total, _bundle_reader_extra(), limit=r.LOGICAL_JOURNEY_LIMIT)


def _load_memory(raw,source):
    from .admission import _active_plan
    if _active_plan() is not None: raise Refusal('invalid_plan_input')
    from .source import _snapshot_exact,_selected_start
    _snapshot_exact(source,complete=False)
    # Strict lexical/raw rejection is independent of a saved future baseline.
    if type(raw) is not bytes: raise Refusal('invalid_json')
    if len(raw)>r.METADATA_BYTES_LIMIT: raise Refusal('metadata_bytes_limit')
    base=_load_source_base(source)
    scan=json_prepass(raw,baseline_bytes=base)
    saved=strict_loads(raw,baseline_bytes=base)
    _record(saved,_FIELDS)
    for key in ('version','formula_version'):
        exact_int(saved[key],'invalid_plan',minimum=2,maximum=2)
    try: expected=SourceIdentity.from_dict(saved['source'])
    except Refusal: raise Refusal('invalid_plan') from None
    if source.identity != expected: raise Refusal('source_fingerprint_mismatch')
    recipe_p=primitive_bounds(saved['recipe'],code='invalid_plan').object_bytes
    if base+5*len(raw)+3*scan.object_bytes+recipe_p>r.LOGICAL_JOURNEY_LIMIT:
        raise Refusal('estimated_memory_limit')
    try: recipe=Recipe.from_dict(saved['recipe'])
    except Refusal: raise Refusal('invalid_plan') from None
    _selected_start(source,recipe,expected)
    _validate_saved_schema(saved,recipe)
    # Only exact saved primitives are retained; no saved BoundPlan forest.
    with _RouteScope(recipe,raw,saved):
        fresh=_compile_memory(source,recipe,saved['runtime'],saved['resource_binding'])
        if not _same(saved,fresh._projection()): raise Refusal('plan_binding_mismatch')
        return fresh


def load_plan(raw,source):
    from .source import _owned_attempt,_raise_owned
    result,error=_owned_attempt(_load_memory,raw,source)
    raw=source=None
    if error is not None: _raise_owned(error)
    return result


def _serialize_compute(plan,kind):
    from .admission import _required_inputs,_guard
    _plan_exact(plan)
    with _required_inputs(plan=plan):
        _guard('serialize')
        projection=plan._projection()
        if kind=='dict': return thaw(projection)
        if kind=='bytes': return canonical_bytes(projection,limit=r.METADATA_BYTES_LIMIT)
        if kind=='chunks': return iter_json_chunks(projection,limit=r.METADATA_BYTES_LIMIT)
        raise Refusal('invalid_plan_input')


def _serialize_plan(plan,kind):
    from .source import _owned_attempt,_raise_owned
    result,error=_owned_attempt(_serialize_compute,plan,kind)
    plan=None
    if error is not None: _raise_owned(error)
    return result


def _check_saved_binding(binding):
    """Validate a parsed or owned binding in place, without a second forest."""
    from .model import validate_name
    _record(binding,('kind','base_bytes','owners','descriptor_bytes'))
    if type(binding['kind']) is not str or binding['kind'] not in ('memory','file'):
        raise Refusal('invalid_plan')
    for key in ('base_bytes','descriptor_bytes'): _count(binding[key],'invalid_plan')
    owners=binding['owners']
    if type(owners) not in (list,tuple) or len(owners)>80: raise Refusal('invalid_plan')
    previous=None
    for owner in owners:
        _record(owner,('kind','name','terminal_bytes','header_bytes','logical_bytes'))
        if type(owner['kind']) is not str or owner['kind'] not in ('coordinate','variable'):
            raise Refusal('invalid_plan')
        validate_name(owner['name'],'invalid_plan')
        for key in ('terminal_bytes','header_bytes','logical_bytes'): _count(owner[key],'invalid_plan')
        key=(owner['kind'],owner['name'])
        if previous is not None and previous>=key: raise Refusal('invalid_plan')
        previous=key
    if binding['kind']=='file' and owners: raise Refusal('invalid_plan')


def _saved_names(value,*,maximum=16,nonempty=False,ordered=False):
    from .model import validate_name
    if type(value) is not list or not int(nonempty)<=len(value)<=maximum:
        raise Refusal('invalid_plan')
    for name in value: validate_name(name,'invalid_plan')
    if len(set(value))!=len(value) or ordered and value!=sorted(value):
        raise Refusal('invalid_plan')


def _saved_shape(value,dims):
    if type(value) is not list or len(value)!=len(dims): raise Refusal('invalid_plan')
    product=1
    for length in value:
        exact_int(length,'invalid_plan',minimum=1,maximum=r.DIMENSION_LENGTH_LIMIT)
        product=_checked_mul(product,length,limit=r.SHAPE_PRODUCT_LIMIT,code='invalid_plan')
    return product


def _saved_operation(value):
    from .units import _check_operation
    _record(value,_UNIT_FIELDS)
    _check_operation(*(value[name] for name in _UNIT_FIELDS))


def _validate_saved_schema(saved,recipe):
    """Finish bounded strict shape validation before any recompilation.

    The original strict decode's full D+Recipe reservation remains in force
    through this helper. It borrows the parsed forest; at most one Coordinate
    validator is constructed, discarded before the next, and none survives
    this actual frame boundary into source preparation or stock work.
    """
    from .model import Coordinate,numeric_dtype,validate_name
    from .runtime import validate_runtime
    try:
        preflight_json(saved,limit=r.METADATA_BYTES_LIMIT)
        selected=_record(saved['selected'],('variables','dimensions','numeric_bytes'))
        _saved_names(selected['variables'],maximum=64,ordered=True)
        _saved_names(selected['dimensions'],ordered=True)
        _count(selected['numeric_bytes'],'invalid_plan',limit=r.SELECTED_NUMERIC_BYTES_LIMIT)
        coordinates=saved['coordinates']
        if type(coordinates) is not dict or len(coordinates)>16: raise Refusal('invalid_plan')
        for name in coordinates: validate_name(name,'invalid_plan')
        if sorted(coordinates)!=selected['dimensions']: raise Refusal('invalid_plan')
        for name,value in coordinates.items():
            Coordinate.from_dict(value,row=name in recipe.row_dims)
        columns=saved['columns']
        if type(columns) is not list or len(columns)!=len(recipe.columns): raise Refusal('invalid_plan')
        for column in columns:
            _record(column,_COLUMN_FIELDS)
            for key in ('name','source'): validate_name(column[key],'invalid_plan')
            for key in ('source_dtype','output_dtype'):
                dtype=column[key]
                if numeric_dtype(dtype,'invalid_plan')!=dtype: raise Refusal('invalid_plan')
            for key in ('input_dims','final_dims','broadcast'): _saved_names(column[key])
            _saved_shape(column['input_shape'],column['input_dims'])
            _saved_operation(column['unit_operation'])
            weight=column['weight']
            if weight is not None:
                _record(weight,('source','dtype','dims','shape','unit_operation'))
                validate_name(weight['source'],'invalid_plan')
                if numeric_dtype(weight['dtype'],'invalid_plan')!=weight['dtype']:
                    raise Refusal('invalid_plan')
                _saved_names(weight['dims']); _saved_shape(weight['shape'],weight['dims'])
                _saved_operation(weight['unit_operation'])
            stages=column['stages']
            if type(stages) is not list or len(stages)>2: raise Refusal('invalid_plan')
            for stage in stages:
                _record(stage,_STAGE_FIELDS)
                validate_name(stage['name'],'invalid_plan')
                _saved_names(stage['dims'],nonempty=True)
                for key in ('input_dims','remaining_dims','support_dims'): _saved_names(stage[key])
                _saved_shape(stage['input_shape'],stage['input_dims'])
                _saved_shape(stage['remaining_shape'],stage['remaining_dims'])
                if type(stage['op']) is not str or stage['op'] not in ('mean','weighted_mean','min','max'):
                    raise Refusal('invalid_plan')
                if type(stage['missing']) is not str or stage['missing'] not in ('skip','propagate'):
                    raise Refusal('invalid_plan')
                exact_int(stage['min_count'],'invalid_plan',minimum=1,maximum=r.SHAPE_PRODUCT_LIMIT)
                exact_int(stage['support_count'],'invalid_plan',minimum=1,maximum=r.SUPPORT_RECORDS_LIMIT)
                _count(stage['support_start'],'invalid_plan',limit=r.SUPPORT_RECORDS_LIMIT)
        _check_saved_binding(saved['resource_binding'])
        if saved['resource_binding']['kind']!=saved['source']['kind']: raise Refusal('invalid_plan')
        _record(saved['estimates'],ESTIMATE_KEYS)
        for value in saved['estimates'].values(): _count(value,'invalid_plan')
        if saved['estimates']['formula_version']!=2: raise Refusal('invalid_plan')
        validate_runtime(saved['runtime'])
    except Refusal as error:
        if error.code in ('estimated_memory_limit','metadata_bytes_limit'): raise
        raise Refusal('invalid_plan') from None
