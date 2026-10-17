"""Memory numerical core and cohesive immutable result1 implementation.

The approved CONTRACT/API-SCHEMAS/RESOURCES and PLAN remain authoritative;
no serialized field or resource cap is added. Source/runtime replay is an
execution responsibility; load_result validates structure only.

The public boundaries are:

    execute(plan: BoundPlan, source: SourceSnapshot) -> ComputationResult
    load_result(raw: bytes, plan: BoundPlan) -> ComputationResult

The cohesive private _result module owns final immutable, slot-backed
RowRecord, SupportRecord and ComputationResult classes. Constructor signatures:

    RowRecord(*, keys, values, reasons)
    SupportRecord(*, column, stage, keys, n_input, n_valid,
                  n_positive_weight_valid, weight_total, weight_valid,
                  reasons, value, unit)
    ComputationResult(*, version, row_dims, units, rows, support, _plan)

Records validate context-free exact types, scalar domains and local count /
sum / nullability coherence. The result validates the real BoundPlan, exact
root fields, output dtypes, typed canonical row and support grains, declared
stage policies, complete block offsets and final-row/support linkage. It does
not recalculate a reduction or prove adjacent-stage lineage. Coherent forged
values may therefore construct successfully and must fail later public replay.
The private result _plan is the supplied matching real BoundPlan, never a
synthetic carrier, second rebound plan or retained materialized source. Record
fields own immutable primitive maps/tuples without hidden plan/source handles.

Result methods are iter_rows(), iter_support(column=None, stage=None),
iter_json_chunks(), to_json(), and separately admitted to_dict(). Each record
offers to_dict() for one record only. Serialization visits retained fields and
scalars directly in canonical key order; no full result projection, freeze /
thaw forest, DataFrame, complete Unicode document or all-chunks list exists on
normal execution / serialization paths. Final pointer-copy and per-record
scratch stay inside the unchanged M and K terms.

Actual compiler interfaces inspected for this plan are BoundPlan._source,
plan._plan_exact/_plan_selected/_qualify_units, source._selected_start /
_materialize_selected/_scan_memory/_owned_attempt/_raise_owned, admission.
_required_inputs/_guard, and units.UnitOperation/normalize_weights. They are
provisional until independently sealed. The compiled columns are immutable
primitive records; stages carry input_dims, remaining_dims, support_dims,
support_count and global support_start. Coordinate.values is physical order;
Coordinate.sorted_indices defines typed canonical enumeration.

Execution establishes the original plan/source closure before nested work,
checks held identity before phase and follows existing selected declaration /
safe-owner / runtime / complete admission precedence. Actual supplied B is
consumed while the saved anchor A remains independently footprint-checked.
Fresh stock qualification compares the complete seven-field operations once
per semantic pass. The existing normalized-weight consumer uses a freshly
qualified UnitOperation without another stock context or qualification attempt.
The result slot is integrated into admission only after the genuine result
model exists: match explicit/result plans, preserve all A/B/C handles, dedupe
only Dataset identity, grant exact A binding credit once and add distinct X/C.

Columns execute sequentially. Measurement conversion happens once to every
finite original value before any reduction; identity direct integers remain
integers and float32 direct values retain binary32/signed-zero representation.
Each physical weight is validated and normalized once even when its aligned
measurement is missing. Named alignment uses zero-copy views, never tile or
repeat. Scratch follows the unchanged W formula, with source/weight views and
intermediate arrays retired before the next column. Completed columns survive
only as result-record fields, never another numerical array forest.

The frozen scalar oracle establishes the policy order: first classify inputs,
count finite and positive-weight-finite cells, and accumulate total/valid
weights independently. Then derive the exact ordered reasons. Only groups
without reasons evaluate numerator / sum / min / max / division. Thus a null
policy group skips an otherwise overflowing numerator, while actual conversion
or support-weight-sum overflow still fails. Mean uses the ordinary finite sum
then n_valid division. Weighted mean uses products, their ordinary sum and the
independently accumulated valid-weight denominator. Every performed nonfinite
float64 intermediate fails numeric_overflow. A failed stage is missing to the
next; final row reasons are solely its final-stage reasons. Separately rounded
weight sums retain their actual values and the documented envelope, unclamped.

load_result is structural only and uses the shared strict lexical/primitive
decoder and actual CALLER/PARSE/FINAL observer/admission context. Generic-loader
baseline subtraction is forbidden. One-record
validation/adoption creates no fourth forest. Model/parse/owned numerical
failure frames end before fresh outward exceptions; cancellation preserves
identity/type/code while removing only the documented owned diagnostic links.

New behavioral tests use real compiled plans and eager datasets. Runtime
fixtures in unit tests are explicitly schema/order instrumentation; separate
sealed profile journeys must prove actual runtime discovery. Frozen corpora
remain read-only, and independent expected values never import this module.
"""

import math

from .errors import Refusal, ComputationError
from ._result import (RowRecord, SupportRecord, ComputationResult, _effective,
                      _position, _cardinality)


def _indices(shape):
    """Physical odometer with O(rank) state, including one scalar index ()."""
    if not shape:
        yield ()
        return
    current = [0] * len(shape)
    while True:
        yield tuple(current)
        for axis in range(len(shape)-1, -1, -1):
            current[axis] += 1
            if current[axis] < shape[axis]: break
            current[axis] = 0
        else: return


def _canonical_indices(dims, coordinates):
    shape = tuple(len(coordinates[name].values) for name in dims)
    for positions in _indices(shape):
        yield tuple(coordinates[name].sorted_indices[position]
                    for name, position in zip(dims, positions))


def _finite(number):
    if not math.isfinite(number): raise ComputationError('numeric_overflow')
    return number


def _converted_values(buffer, operation):
    """One float64 conversion buffer; each original scalar converts once."""
    import numpy as np
    raw = converted = None
    try:
        raw = buffer.view()
        converted = np.empty(buffer.shape, dtype='float64')
        for index in _indices(buffer.shape):
            value = float(raw[index])
            if math.isnan(value):
                converted[index] = value
                continue
            if not math.isfinite(value): raise Refusal('nonfinite_value')
            value = _finite(value * operation['scale'])
            converted[index] = _finite(value + operation['offset'])
        return converted
    finally:
        raw = converted = None


def _check_direct_floats(values):
    for index in _indices(values.shape):
        if math.isinf(float(values[index])): raise Refusal('nonfinite_value')


def _named_weight_view(normalized, weight_dims, input_dims, input_shape):
    """One readonly named broadcast view over the already normalized bytes.

    Missing axes have zero strides. No tiled/repeated array or chained full
    transpose/reshape views survive alongside the measurement's view pair.
    """
    import numpy as np
    strides_by_name = {}
    stride = 8
    for name, length in reversed(tuple(zip(weight_dims, normalized.buffer.shape))):
        strides_by_name[name] = stride
        stride *= length
    return np.ndarray(shape=input_shape, dtype='float64',
        buffer=normalized.buffer.data,
        strides=tuple(strides_by_name.get(name, 0) for name in input_dims))


def _normalized_weights(materialized, column):
    from . import units
    weight = column['weight']; fields = weight['unit_operation']
    # materialize_source just freshly qualified and compared this entire
    # operation. Reconstruct its exact immutable structural model only; this
    # consumer opens no second registry context or qualification attempt.
    operation = units.UnitOperation(*(fields[name] for name in (
        'source_unit', 'target_unit', 'scale', 'offset', 'parsed_source',
        'parsed_target', 'definition_graph')))
    normalized = units.normalize_weights(materialized.arrays[weight['source']], operation)
    return _named_weight_view(normalized, weight['dims'], column['input_dims'], column['input_shape'])


def _reduce_stage(values, weights, column, stage, coordinates, support):
    """Support first, then value arithmetic only for policy-admitted groups."""
    import numpy as np
    output = np.empty(stage['remaining_shape'], dtype='float64')
    input_dims = stage['input_dims']
    remaining_axes = tuple(input_dims.index(name) for name in stage['remaining_dims'])
    reduced_axes = tuple(input_dims.index(name) for name in stage['dims'])
    reduced_shape = tuple(len(coordinates[name].values) for name in stage['dims'])
    n_input = math.prod(reduced_shape)
    weighted = stage['op'] == 'weighted_mean'
    if weighted != (weights is not None): raise Refusal('invalid_plan')
    remaining_support_axes = tuple(stage['support_dims'].index(name) for name in stage['remaining_dims'])
    for support_indices in _canonical_indices(stage['support_dims'], coordinates):
        selector = [0] * len(input_dims)
        remaining = tuple(support_indices[axis] for axis in remaining_support_axes)
        for axis, index in zip(remaining_axes, remaining): selector[axis] = index
        n_valid = positive = 0
        total = valid_total = 0.0
        for reduced in _indices(reduced_shape):
            for axis, index in zip(reduced_axes, reduced): selector[axis] = index
            index = tuple(selector)
            value = float(values[index])
            valid = not math.isnan(value)
            if valid: n_valid += 1
            if weighted:
                weight = float(weights[index])
                total = _finite(total + weight)
                if valid:
                    valid_total = _finite(valid_total + weight)
                    if weight > 0: positive += 1
        if not weighted:
            positive = n_valid; total = float(n_input); valid_total = float(n_valid)
        reasons = ()
        if stage['missing'] == 'propagate' and n_valid != n_input: reasons += ('missing_values',)
        if n_valid < stage['min_count']: reasons += ('insufficient_count',)
        if weighted and valid_total == 0: reasons += ('zero_weight',)
        answer = None
        if not reasons:
            accumulator = 0.0 if stage['op'] in ('mean', 'weighted_mean') else None
            for reduced in _indices(reduced_shape):
                for axis, index in zip(reduced_axes, reduced): selector[axis] = index
                index = tuple(selector); value = float(values[index])
                if math.isnan(value): continue
                if stage['op'] == 'weighted_mean':
                    product = _finite(value * float(weights[index]))
                    accumulator = _finite(accumulator + product)
                elif stage['op'] == 'mean': accumulator = _finite(accumulator + value)
                elif accumulator is None: accumulator = value
                elif stage['op'] == 'min': accumulator = min(accumulator, value)
                else: accumulator = max(accumulator, value)
            answer = (_finite(accumulator / valid_total)
                      if stage['op'] in ('mean', 'weighted_mean') else accumulator)
        output[remaining] = float('nan') if answer is None else answer
        keys = {name: coordinates[name].values[index]
                for name, index in zip(stage['support_dims'], support_indices)}
        support.append(SupportRecord(column=column['name'], stage=stage['name'], keys=keys,
            n_input=n_input, n_valid=n_valid, n_positive_weight_valid=positive,
            weight_total=total, weight_valid=valid_total, reasons=reasons,
            value=answer, unit=_effective(column)))
        del keys
    return output


def _fill_column_rows(rows, plan, column, values, support):
    row_dims = plan.recipe.row_dims
    if column['stages']:
        final = column['stages'][-1]
        for row_index, row in enumerate(rows):
            offset = 0
            for dim in final['support_dims']:
                offset = offset * len(plan.coordinates[dim].values) + _position(row_index, row_dims, plan.coordinates, dim)
            record = support[final['support_start'] + offset]
            row['values'][column['name']] = record.value
            row['reasons'][column['name']] = record.reasons
        return
    integer = column['output_dtype'].startswith(('int', 'uint'))
    for row_index, row in enumerate(rows):
        physical = tuple(plan.coordinates[dim].sorted_indices[
            _position(row_index, row_dims, plan.coordinates, dim)] for dim in column['final_dims'])
        value = int(values[physical]) if integer else float(values[physical])
        missing = not integer and math.isnan(value)
        row['values'][column['name']] = None if missing else value
        row['reasons'][column['name']] = ('missing_values',) if missing else ()


def _column_values(plan, materialized, column, rows, support):
    """One numerical column lifetime, ended before the next complete guard."""
    values = weights = None
    try:
        buffer = materialized.arrays[column['source']]
        direct = (not column['stages'] and column['unit_operation']['scale'] == 1 and
                  column['unit_operation']['offset'] == 0)
        if direct:
            values = buffer.view()
            if column['source_dtype'] in ('float32', 'float64'): _check_direct_floats(values)
        else: values = _converted_values(buffer, column['unit_operation'])
        if column['weight'] is not None: weights = _normalized_weights(materialized, column)
        for stage in column['stages']:
            if len(support) != stage['support_start']: raise Refusal('invalid_plan')
            values = _reduce_stage(values, weights, column, stage, plan.coordinates, support)
            weights = None
        _fill_column_rows(rows, plan, column, values, support)
    finally:
        values = weights = None


def _compute_records(plan, materialized):
    from .admission import _guard
    rows = []
    for indices in _canonical_indices(plan.recipe.row_dims, plan.coordinates):
        rows.append(dict(keys={name: plan.coordinates[name].values[index]
                               for name, index in zip(plan.recipe.row_dims, indices)},
                         values={}, reasons={}))
    support = []
    for column in plan.columns:
        _guard('materialized')
        _column_values(plan, materialized, column, rows, support)
    # Replace each mutable row builder in place. Only one bounded row's owned
    # fields overlap its builder; final tuple pointer copies are charged in M.
    for index in range(len(rows)):
        row = rows[index]
        rows[index] = RowRecord(keys=row['keys'], values=row['values'], reasons=row['reasons'])
        del row
    return rows, support


def _execute_memory(plan, source):
    from .plan import _plan_exact, _plan_selected
    from .source import _selection_snapshot, materialize_source, recheck_source
    from .admission import _required_inputs, _guard
    from . import runtime
    _plan_exact(plan)
    _selection_snapshot(source, _plan_selected(plan), expected=plan.source)
    with _required_inputs(plan=plan, snapshot=source):
        materialized = materialize_source(source, plan)
        # This is an actual known second source-model slot, never an uncharged
        # materialized local hidden from later complete guards.
        with _required_inputs(snapshot=materialized):
            _guard('materialized')
            rows, support = _compute_records(plan, materialized)
            recheck_source(materialized)
            runtime.require_runtime(plan.runtime)
            _guard('materialized')
            result = ComputationResult(version=1, row_dims=plan.recipe.row_dims,
                units={column['name']: _effective(column) for column in plan.columns},
                rows=rows, support=support, _plan=plan)
            del rows, support
        del materialized
        _guard('materialized')
        runtime.require_runtime(plan.runtime)
        return result


def execute(plan, source):
    """Execute the real eager memory plan under fresh source/runtime gates."""
    from .source import _owned_attempt, _raise_owned
    result, error = _owned_attempt(_execute_memory, plan, source)
    plan = source = None
    if error is not None: _raise_owned(error)
    return result


def _decode_adopt_result(raw, plan):
    from .codec import _strict_result_loads
    from ._result import _fields
    from .admission import _guard
    parsed = _strict_result_loads(raw, plan)
    _fields(parsed, ('version', 'row_dims', 'units', 'rows', 'support'))
    # Full decode can observe legitimate caller-cache growth. Recheck the
    # complete original closure before allocating any FINAL record backing.
    _guard('serialize')
    # Only PARSE and FINAL coexist with the retained caller result. Each
    # record is checked/adopted in place; no full validator forest is made.
    return ComputationResult(_plan=plan, **parsed)


def _load_result_memory(raw, plan):
    from .plan import _plan_exact
    from .admission import _required_inputs, _guard
    _plan_exact(plan)
    if type(raw) is not bytes: raise Refusal('invalid_result')
    with _required_inputs(plan=plan):
        result = _decode_adopt_result(raw, plan)
        # The parser/adoption helper frame and its PARSE forest have ended
        # before this final source/cache guard or any caller's later replay.
        _guard('serialize')
        return result


def load_result(raw, plan):
    """Strict structural result1 loading; no source-content replay is claimed."""
    from .source import _owned_attempt, _raise_owned
    result, error = _owned_attempt(_load_result_memory, raw, plan)
    raw = plan = None
    if error is not None: _raise_owned(error)
    return result
