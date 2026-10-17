"""Real call-local memory Dataset closure and fresh Formula2 admission.

Only actual SourceSnapshot/BoundPlan/ComputationResult arguments supply handles.
The original plan, source and result Dataset slots remain live across nested
helpers. The nonrecursive source scan grants no semantic content authority.
"""
from contextvars import ContextVar
from dataclasses import dataclass
from .errors import Refusal
from .model import SourceSnapshot, BoundPlan
from .codec import canonical_bytes, iter_json_chunks
from ._resource_bounds import _count, _checked_add
from . import resources as r


@dataclass(frozen=True,slots=True)
class _Inputs:
    plan: object
    datasets: tuple
    snapshots: tuple
    required_dataset_count: int
    distinct_dataset_count: int
    result: object = None
    def __init_subclass__(cls,**kwargs): raise TypeError('Input closure is final')


_ACTIVE=ContextVar('replicatetable_memory_inputs',default=None)
_PREPARATION_BYTES=ContextVar('replicatetable_retained_preparation_recipes',default=0)
_BUNDLE_READER=ContextVar('replicatetable_original_bundle_reader',default=None)


class _InputScope:
    __slots__=('inputs','_token','_entered')
    def __init__(self,inputs):
        self.inputs=inputs; self._token=None; self._entered=False
    def __enter__(self):
        if self._entered: raise Refusal('invalid_plan_input')
        self._entered=True
        outer=_ACTIVE.get()
        if outer is not None:
            if type(outer) is not _Inputs: raise Refusal('invalid_plan_input')
            if self.inputs.plan is not None and self.inputs.plan is not outer.plan:
                raise Refusal('invalid_plan_input')
            for dataset in self.inputs.datasets:
                if not any(dataset is known for known in outer.datasets):
                    raise Refusal('invalid_plan_input')
            result=outer.result
            required=outer.required_dataset_count
            if self.inputs.result is not None and self.inputs.result is not result:
                if result is not None: raise Refusal('invalid_plan_input')
                result=self.inputs.result
                required+=1
                if required>3: raise Refusal('invalid_plan_input')
            snapshots=outer.snapshots
            for snapshot in self.inputs.snapshots:
                if any(snapshot is known for known in snapshots): continue
                # Only the caller and one current nested source model may
                # coexist with the plan's own selected backing. Keep their
                # actual references until this helper scope really exits.
                if len(snapshots)>=2: raise Refusal('invalid_plan_input')
                snapshots=snapshots+(snapshot,)
            if snapshots is not outer.snapshots or result is not outer.result:
                nested=_Inputs(outer.plan,outer.datasets,snapshots,
                               required,outer.distinct_dataset_count,result)
                self._token=_ACTIVE.set(nested)
                return nested
            return outer
        self._token=_ACTIVE.set(self.inputs)
        return self.inputs
    def __exit__(self,kind,value,traceback):
        token=self._token; self._token=None
        try:
            if token is not None: _ACTIVE.reset(token)
        finally: self.inputs=None
        return False


def _required_inputs(*,plan=None,snapshot=None,result=None,dataset=None):
    if result is not None and plan is None: raise Refusal('invalid_plan_input')
    import xarray as xr
    datasets=[]; required=0
    if plan is not None:
        from .plan import _plan_exact
        _plan_exact(plan)
        handle=plan._source._handle
        if type(handle) is not xr.Dataset: raise Refusal('unsupported_source_storage')
        datasets.append(handle); required+=1
    if snapshot is not None:
        if type(snapshot) is not SourceSnapshot: raise Refusal('invalid_source')
        try: handle=object.__getattribute__(snapshot,'_handle')
        except AttributeError: raise Refusal('invalid_source') from None
        if dataset is not None and dataset is not handle: raise Refusal('invalid_source')
        dataset=handle
    if dataset is not None:
        if type(dataset) is not xr.Dataset: raise Refusal('invalid_source')
        required+=1
        if not any(dataset is known for known in datasets): datasets.append(dataset)
    if result is not None:
        _result_for_plan(plan,result)
        handle=result._plan._source._handle
        if type(handle) is not xr.Dataset: raise Refusal('unsupported_source_storage')
        required+=1
        if not any(handle is known for known in datasets): datasets.append(handle)
    if not datasets: raise Refusal('invalid_source')
    snapshots=() if snapshot is None else (snapshot,)
    return _InputScope(_Inputs(plan,tuple(datasets),snapshots,required,len(datasets),result))


def _matching_plans(left,right):
    """Exact canonical plan2 comparison without another plan projection."""
    if left is right: return True
    from .plan import _same
    if left.version!=right.version or left.formula_version!=right.formula_version or left.source!=right.source:
        return False
    if (left.recipe.version!=right.recipe.version or
            not _same(left.recipe.row_dims,right.recipe.row_dims) or
            not _same(left.recipe.columns,right.recipe.columns)):
        return False
    if tuple(left.coordinates)!=tuple(right.coordinates): return False
    for name,coordinate in left.coordinates.items():
        other=right.coordinates[name]
        if (coordinate.dtype!=other.dtype or not _same(coordinate.values,other.values) or
                not _same(coordinate.sorted_indices,other.sorted_indices)):
            return False
    return all(_same(getattr(left,name),getattr(right,name)) for name in
               ('runtime','selected','columns','resource_binding','estimates'))


def _result_for_plan(plan,result):
    from ._result import ComputationResult,_result_exact,_result_object_bound
    if type(result) is not ComputationResult: raise Refusal('invalid_plan_input')
    try: _result_exact(result)
    except Refusal: raise Refusal('invalid_plan_input') from None
    if not _matching_plans(plan,result._plan): raise Refusal('plan_binding_mismatch')
    if _result_object_bound(result.version,result.row_dims,result.units,result.rows,result.support)>plan.estimates['result_objects_bytes']:
        raise Refusal('invalid_plan_input')


def _shared_descriptor(left,right):
    return all(getattr(left,name) is getattr(right,name) for name in
        ('identity','dimensions','variables','coordinate_descriptors','attributes'))


def _retained_numeric_bytes(inputs):
    """Known ArrayBuffer slots only; repeated variable roles get no alias credit."""
    total=0
    for index,snapshot in enumerate(inputs.snapshots):
        for name,buffer in snapshot.arrays.items():
            if any(name in inputs.snapshots[earlier].arrays and
                   inputs.snapshots[earlier].arrays[name].data is buffer.data
                   for earlier in range(index)):
                continue
            total=_checked_add(total,len(buffer.data))
    return total


def _check_model_slots(inputs):
    """Qualify actual known forests against the existing fixed Dmeta/Q/A slots.

    No source content is certified here. Equal-cost descriptor/label changes
    still require actual-B semantic binding at the consuming boundary.
    """
    from .source import _snapshot_exact,_retained_projection
    plan=inputs.plan
    for snapshot in inputs.snapshots:
        _snapshot_exact(snapshot)
        descriptor,coordinates,_,numeric=_retained_projection(snapshot)
        if (descriptor.object_bytes>plan.estimates['descriptor_objects_bytes'] or
                coordinates is not None and coordinates.object_bytes>plan.estimates['coordinate_objects_bytes'] or
                numeric>plan.estimates['selected_numeric_bytes']):
            raise Refusal('plan_binding_mismatch')
    # Actual helper outputs share descriptor children. A different equal-value
    # third descriptor forest has no reserved role and cannot borrow 2Dmeta.
    descriptors=(plan._source,)+inputs.snapshots
    count=0
    for index,snapshot in enumerate(descriptors):
        if not any(_shared_descriptor(snapshot,descriptors[earlier]) for earlier in range(index)):
            count+=1
    if count>2: raise Refusal('invalid_plan_input')
    if inputs.result is not None:
        # The genuine matching second plan uses the existing second Z role.
        # Its selected-only backing adds no numeric array union. Its one
        # descriptor forest fits the source-base descriptor reserve plus the
        # existing two Dmeta roles; ordinary source helpers retain their
        # original two-forest rule above, so no fourth forest is introduced.
        backing=inputs.result._plan._source
        _snapshot_exact(backing)
        descriptor,coordinates,_,numeric=_retained_projection(backing)
        if (descriptor.object_bytes>plan.estimates['descriptor_objects_bytes'] or
                coordinates is not None and coordinates.object_bytes>plan.estimates['coordinate_objects_bytes'] or
                numeric!=0):
            raise Refusal('plan_binding_mismatch')
    if _retained_numeric_bytes(inputs)>2*plan.estimates['selected_numeric_bytes']:
        raise Refusal('invalid_plan_input')


def _guard_materialization():
    """Reserve a new numeric union; ordinary final guards may see both slots."""
    total=_guard('materialized')
    inputs=_ACTIVE.get()
    if inputs is None or inputs.plan is None: raise Refusal('invalid_plan_input')
    if _retained_numeric_bytes(inputs)>inputs.plan.estimates['selected_numeric_bytes']:
        raise Refusal('invalid_plan_input')
    return total


def _require_binding(dataset,saved):
    """Fresh scan ends here; only its cache scalar survives exact comparison."""
    from .source import _footprint_memory
    from .plan import _same, _check_saved_binding
    _check_saved_binding(saved)
    binding,cache=_footprint_memory(dataset)
    if not _same(binding,saved):
        raise Refusal('source_resource_binding_mismatch',
            'Source resource binding changed; inspect the current source and compile a new plan before retrying.')
    return cache


def _extra_footprint(dataset):
    from .source import _footprint_memory
    binding,cache=_footprint_memory(dataset)
    return binding['base_bytes'],cache


def _measure_sources(inputs):
    plan=inputs.plan
    if type(plan) is not BoundPlan: raise Refusal('invalid_plan_input')
    cache=_require_binding(plan._source._handle,plan.resource_binding)
    extra=0
    for dataset in inputs.datasets:
        if dataset is plan._source._handle: continue
        base,current_cache=_extra_footprint(dataset)
        extra=_checked_add(extra,base)
        cache=_checked_add(cache,current_cache,limit=r.LOGICAL_JOURNEY_LIMIT,code='estimated_memory_limit')
    return extra,cache


def _active_plan():
    inputs=_ACTIVE.get()
    return None if inputs is None else inputs.plan


def _preflight_required():
    """Safe complete owners/cache/anchor check, before declaration precedence."""
    inputs=_ACTIVE.get()
    if inputs is not None and inputs.plan is not None:
        _measure_sources(inputs)


class _PreparationRecipe:
    """Charge a real explicit Recipe while an existing plan remains active."""
    __slots__=('recipe','_token','_entered')
    def __init__(self,recipe):
        self.recipe=recipe; self._token=None; self._entered=False
    def __enter__(self):
        if self._entered: raise Refusal('invalid_plan_input')
        self._entered=True
        if _active_plan() is not None:
            from .source import _recipe_exact
            from ._resource_inputs import _recipe_cost
            _recipe_exact(self.recipe)
            total=_checked_add(_PREPARATION_BYTES.get(),_recipe_cost(self.recipe).object_bytes,
                               limit=r.LOGICAL_JOURNEY_LIMIT,code='estimated_memory_limit')
            self._token=_PREPARATION_BYTES.set(total)
        return self
    def __exit__(self,*arguments):
        token=self._token; self._token=None
        try:
            if token is not None: _PREPARATION_BYTES.reset(token)
        finally: self.recipe=None
        return False


@dataclass(frozen=True,slots=True,init=False)
class CallAdmission:
    version: int
    formula_version: int
    baseline_bytes: int
    extra_source_bytes: int
    cache_bytes: int
    total_bytes: int
    limit_bytes: int
    admitted: bool
    required_dataset_count: int
    distinct_dataset_count: int
    def __init_subclass__(cls,**kwargs): raise TypeError('CallAdmission is final')
    def __init__(self,*,version,formula_version,baseline_bytes,extra_source_bytes,
                 cache_bytes,total_bytes,limit_bytes,admitted,required_dataset_count,
                 distinct_dataset_count):
        try: object.__getattribute__(self,'version')
        except AttributeError: pass
        else: raise Refusal('invalid_plan_input')
        values=locals()
        for name in self.__slots__:
            if name!='admitted': _count(values[name],'invalid_plan_input')
        if (version!=2 or formula_version!=2 or limit_bytes!=536870912 or
                type(admitted) is not bool or total_bytes!=baseline_bytes+extra_source_bytes+cache_bytes or
                admitted!=(total_bytes<=limit_bytes) or not 0<=distinct_dataset_count<=required_dataset_count<=3):
            raise Refusal('invalid_plan_input')
        for name in self.__slots__: object.__setattr__(self,name,values[name])
    def _projection(self): return {name:getattr(self,name) for name in self.__slots__}
    def to_dict(self): return self._projection()
    def to_json(self): return canonical_bytes(self._projection())
    def iter_json_chunks(self): return iter_json_chunks(self._projection())


def _inspect_current():
    from .plan import _estimate_plan
    inputs=_ACTIVE.get()
    if type(inputs) is not _Inputs or inputs.plan is None: raise Refusal('invalid_plan_input')
    extra,cache=_measure_sources(inputs)
    baseline=_estimate_plan(inputs.plan)
    _check_model_slots(inputs)
    total=_checked_add(_checked_add(baseline,extra),cache)
    return CallAdmission(version=2,formula_version=2,baseline_bytes=baseline,
        extra_source_bytes=extra,cache_bytes=cache,total_bytes=total,limit_bytes=536870912,
        admitted=total<=536870912,required_dataset_count=inputs.required_dataset_count,
        distinct_dataset_count=inputs.distinct_dataset_count)


def _guard(phase,*,baseline=None):
    if type(phase) is not str or phase not in ('descriptor','prepared','materialized','recheck','compile','serialize'):
        raise Refusal('invalid_plan_input')
    from .plan import _route_extra
    inputs=_ACTIVE.get()
    if inputs is not None and inputs.plan is not None:
        if baseline is not None: raise Refusal('invalid_plan_input')
        total=_inspect_current().total_bytes
    else:
        if baseline is None: raise Refusal('invalid_plan_input')
        total=_count(baseline,'invalid_plan_input')
    total=_checked_add(_checked_add(total,_route_extra()),_PREPARATION_BYTES.get())
    total=_checked_add(total,_bundle_reader_extra(None if inputs is None else inputs.plan))
    if total>r.LOGICAL_JOURNEY_LIMIT: raise Refusal('estimated_memory_limit')
    return total


def _inspect_call(plan,snapshot,result):
    from .plan import _plan_exact,_plan_selected
    from .source import _selection_snapshot
    _plan_exact(plan)
    _selection_snapshot(snapshot,_plan_selected(plan),expected=plan.source)
    with _required_inputs(plan=plan,snapshot=snapshot,result=result): return _inspect_current()


def inspect_call_admission(plan,snapshot,*,result=None):
    from .source import _owned_attempt,_raise_owned
    answer,error=_owned_attempt(_inspect_call,plan,snapshot,result)
    plan=snapshot=result=None
    if error is not None: _raise_owned(error)
    return answer


class _BundleReaderScope:
    """Actual memory-source/original-reader lifetime; no scalar permit input."""
    __slots__ = ('_source', '_reader', '_token', '_entered')

    def __init__(self, source):
        from .source import _snapshot_exact
        _snapshot_exact(source)
        if source.identity.kind != 'memory': raise Refusal('unsupported_source_storage')
        # The exact eager handle is checked before entering the reserve.
        _required_inputs(snapshot=source)
        self._source = source
        self._reader = self._token = None
        self._entered = False

    def __init_subclass__(cls, **keywords):
        raise TypeError('Bundle reader scopes are final')

    def __enter__(self):
        if self._entered or _BUNDLE_READER.get() is not None:
            raise Refusal('invalid_plan_input')
        self._entered = True
        self._token = _BUNDLE_READER.set(self)
        try:
            from .plan import _load_source_base
            _checked_add(_load_source_base(self._source), 0, limit=r.LOGICAL_JOURNEY_LIMIT)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def adopt(self, reader):
        from . import _native_bundle_reader as native
        if _BUNDLE_READER.get() is not self or self._reader is not None:
            raise Refusal('unsafe_path')
        native._shape(reader)
        if reader.retired: raise Refusal('unsafe_path')
        self._reader = reader

    def __exit__(self, kind, value, traceback):
        token = self._token
        self._token = None
        try:
            if token is not None: _BUNDLE_READER.reset(token)
        finally:
            self._source = self._reader = None
        return False


def _bundle_reader_extra(plan=None):
    scope = _BUNDLE_READER.get()
    if scope is None: return 0
    if type(scope) is not _BundleReaderScope or scope._source is None:
        raise Refusal('invalid_plan_input')
    from ._native_budget import _parent_bytes
    # Frozen W136, computed from the same exact maximum positional namespace.
    reserved = _parent_bytes(136, 1352 + 64*((128+4*19)+(128+4*27)))
    if plan is None: return reserved
    from .plan import _plan_exact
    from ._bundle_payload import _payload_paths
    _plan_exact(plan)
    if plan._source._handle is not scope._source._handle:
        raise Refusal('invalid_plan_input')
    # Every canonical plan baseline already includes its own W_parent. Charge
    # only the actual retained-reader difference; never add a second full W.
    count = 1
    path_objects = 128 + 4*len('manifest.json')
    paths = _payload_paths(plan)
    try:
        for path in paths:
            count += 1
            path_objects += 128 + 4*len(path)
    finally:
        paths.close()
    if count > 7:
        count += 1
        path_objects += 128 + 4*len('support')
    return max(0, reserved-_parent_bytes(count, path_objects))
