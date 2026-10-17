"""Immutable result1 records and structural validation, never a second reducer.

This private module is part of the cohesive reduce/result implementation.
Shared result-slot admission and strict decoding use the actual caller closure.
"""
from dataclasses import dataclass
import math
import struct

from .codec import OwnedMap, _chunks, _string_chunks, exact_int, primitive_bounds, utf8_length
from .errors import Refusal, ComputationError
from .model import (_dtype_info, _require_uninitialized, validate_name,
                    validate_unit, BoundPlan)
from . import resources as r

_ROW_FIELDS = ('keys', 'reasons', 'values')
_SUPPORT_FIELDS = ('column', 'keys', 'n_input', 'n_positive_weight_valid',
                   'n_valid', 'reasons', 'stage', 'unit', 'value',
                   'weight_total', 'weight_valid')
_REASONS = ('missing_values', 'insufficient_count', 'zero_weight')


def _map(value, maximum=32):
    if type(value) is dict:
        if len(value) > maximum: raise Refusal('invalid_result')
        if any(type(key) is not str for key in value): raise Refusal('invalid_result')
        return value
    if type(value) is OwnedMap:
        try: items = object.__getattribute__(value, '_items')
        except AttributeError: raise Refusal('invalid_result') from None
        if type(items) is not tuple or len(items) > maximum: raise Refusal('invalid_result')
        previous = None
        for pair in items:
            if type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not str:
                raise Refusal('invalid_result')
            if previous is not None and pair[0] <= previous: raise Refusal('invalid_result')
            previous = pair[0]
        return value
    raise Refusal('invalid_result')


def _fields(value, fields):
    _map(value, len(fields))
    if len(value) != len(fields) or any(key not in value for key in fields):
        raise Refusal('invalid_result')
    return value


def _sequence(value, maximum):
    if type(value) not in (list, tuple) or len(value) > maximum:
        raise Refusal('invalid_result')
    return value


def _same_scalar(left, right):
    if type(left) is not type(right): return False
    return left.hex() == right.hex() if type(left) is float else left == right


def _scalar(value, *, key=False):
    if value is None and not key: return
    kind = type(value)
    if kind is int:
        exact_int(value, 'invalid_result', minimum=-(2**63), maximum=2**64-1)
    elif kind is float:
        if not math.isfinite(value): raise Refusal('invalid_result')
    elif kind is str and key:
        if utf8_length(value, 'invalid_result', maximum=r.LABEL_UTF8_BYTES_LIMIT) > r.LABEL_UTF8_BYTES_LIMIT:
            raise Refusal('invalid_result')
    else: raise Refusal('invalid_result')


def _typed_scalar(value, dtype, *, nullable=False, coordinate=False):
    if value is None:
        if nullable: return
        raise Refusal('invalid_result')
    if coordinate and type(dtype) is str and dtype.startswith('<U'):
        if type(value) is not str or len(value) > int(dtype[2:]): raise Refusal('invalid_result')
        utf8_length(value, 'invalid_result', maximum=r.LABEL_UTF8_BYTES_LIMIT)
        return
    info = _dtype_info(dtype, 'invalid_result', coordinate=coordinate)
    if info[3] is not None:
        exact_int(value, 'invalid_result', minimum=info[3], maximum=info[4])
        return
    if type(value) is not float or not math.isfinite(value): raise Refusal('invalid_result')
    if info[0] == 'float32':
        try: rounded = struct.unpack('<f', struct.pack('<f', value))[0]
        except (OverflowError, struct.error): raise Refusal('invalid_result') from None
        if not _same_scalar(rounded, value): raise Refusal('invalid_result')


def _reasons(value):
    _sequence(value, 3)
    previous = -1
    for reason in value:
        if type(reason) is not str or reason not in _REASONS: raise Refusal('invalid_result')
        position = _REASONS.index(reason)
        if position <= previous: raise Refusal('invalid_result')
        previous = position
    return tuple(value)


def _key_map(value):
    _map(value, r.RANK_LIMIT)
    for name, label in value.items():
        validate_name(name, 'invalid_result'); _scalar(label, key=True)


def _row_parts(keys, values, reasons):
    _key_map(keys); _map(values); _map(reasons)
    if not values or len(values) != len(reasons): raise Refusal('invalid_result')
    for name, value in values.items():
        validate_name(name, 'invalid_result'); _scalar(value)
        if name not in reasons: raise Refusal('invalid_result')
        why = _reasons(reasons[name])
        if (value is None) != bool(why): raise Refusal('invalid_result')
    for name in reasons: validate_name(name, 'invalid_result')


def _support_parts(column, stage, keys, n_input, n_valid,
                   n_positive_weight_valid, weight_total, weight_valid,
                   reasons, value, unit):
    validate_name(column, 'invalid_result'); validate_name(stage, 'invalid_result')
    _key_map(keys)
    exact_int(n_input, 'invalid_result', minimum=1, maximum=r.SHAPE_PRODUCT_LIMIT)
    exact_int(n_valid, 'invalid_result', maximum=n_input)
    exact_int(n_positive_weight_valid, 'invalid_result', maximum=n_valid)
    for weight in (weight_total, weight_valid):
        if type(weight) is not float or not math.isfinite(weight) or weight < 0:
            raise Refusal('invalid_result')
    why = _reasons(reasons)
    if value is not None and (type(value) is not float or not math.isfinite(value)):
        raise Refusal('invalid_result')
    validate_unit(unit, 'invalid_result')
    if (value is None) != bool(why): raise Refusal('invalid_result')
    if (weight_valid == 0) != (n_positive_weight_valid == 0): raise Refusal('invalid_result')
    if weight_total == 0 and weight_valid != 0: raise Refusal('invalid_result')
    if not (weight_valid <= weight_total or math.isclose(weight_valid, weight_total,
            rel_tol=(n_input-1)*2**-52, abs_tol=0)):
        raise Refusal('invalid_result')


def _own_map(value, *, reasons=False):
    # Exactly one bounded record is copied here. No whole result forest is
    # thawed/refrozen; all scalar/container validation preceded adoption.
    return OwnedMap._from_checked(tuple((key, tuple(value[key]) if reasons else value[key])
                                        for key in sorted(value)))


@dataclass(frozen=True, slots=True, init=False, eq=False)
class RowRecord:
    keys: OwnedMap
    values: OwnedMap
    reasons: OwnedMap

    def __init_subclass__(cls, **kwargs): raise TypeError('RowRecord is final')
    def __init__(self, *, keys, values, reasons):
        _require_uninitialized(self, 'keys', 'invalid_result')
        from .source import _owned_attempt, _raise_owned
        owned, error = _owned_attempt(_row_ownership, keys, values, reasons)
        keys = values = reasons = None
        if error is not None:
            self = None
            _raise_owned(error)
        for name, value in owned: object.__setattr__(self, name, value)

    def to_dict(self):
        _row_exact(self)
        return dict(keys=dict(self.keys), values=dict(self.values),
                    reasons={key: list(value) for key, value in self.reasons.items()})


@dataclass(frozen=True, slots=True, init=False, eq=False)
class SupportRecord:
    column: str
    stage: str
    keys: OwnedMap
    n_input: int
    n_valid: int
    n_positive_weight_valid: int
    weight_total: float
    weight_valid: float
    reasons: tuple
    value: float | None
    unit: str | None

    def __init_subclass__(cls, **kwargs): raise TypeError('SupportRecord is final')
    def __init__(self, *, column, stage, keys, n_input, n_valid,
                 n_positive_weight_valid, weight_total, weight_valid,
                 reasons, value, unit):
        _require_uninitialized(self, 'column', 'invalid_result')
        from .source import _owned_attempt, _raise_owned
        owned, error = _owned_attempt(_support_ownership, column, stage, keys, n_input,
            n_valid, n_positive_weight_valid, weight_total, weight_valid, reasons, value, unit)
        column = stage = keys = n_input = n_valid = None
        n_positive_weight_valid = weight_total = weight_valid = reasons = value = unit = None
        if error is not None:
            self = None
            _raise_owned(error)
        for name, item in owned: object.__setattr__(self, name, item)

    def to_dict(self):
        _support_exact(self)
        return {name: dict(self.keys) if name == 'keys' else
                list(self.reasons) if name == 'reasons' else getattr(self, name)
                for name in _SUPPORT_FIELDS}


def _row_ownership(keys, values, reasons):
    _row_parts(keys, values, reasons)
    return (('keys', _own_map(keys)), ('values', _own_map(values)),
            ('reasons', _own_map(reasons, reasons=True)))


def _support_ownership(column, stage, keys, n_input, n_valid,
                       n_positive_weight_valid, weight_total, weight_valid,
                       reasons, value, unit):
    _support_parts(column, stage, keys, n_input, n_valid, n_positive_weight_valid,
                   weight_total, weight_valid, reasons, value, unit)
    return (('column', column), ('stage', stage), ('keys', _own_map(keys)),
        ('n_input', n_input), ('n_valid', n_valid),
        ('n_positive_weight_valid', n_positive_weight_valid),
        ('weight_total', weight_total), ('weight_valid', weight_valid),
        ('reasons', tuple(reasons)), ('value', value), ('unit', unit))


def _row_exact(row):
    if type(row) is not RowRecord: raise Refusal('invalid_result')
    try:
        if any(type(object.__getattribute__(row, field)) is not OwnedMap for field in _ROW_FIELDS):
            raise Refusal('invalid_result')
        _row_parts(row.keys, row.values, row.reasons)
        if any(type(value) is not tuple for _, value in row.reasons.items()): raise Refusal('invalid_result')
    except AttributeError: raise Refusal('invalid_result') from None
    return row


def _support_exact(record):
    if type(record) is not SupportRecord: raise Refusal('invalid_result')
    try:
        if type(record.keys) is not OwnedMap or type(record.reasons) is not tuple:
            raise Refusal('invalid_result')
        _support_parts(**{field: object.__getattribute__(record, field) for field in _SUPPORT_FIELDS})
    except AttributeError: raise Refusal('invalid_result') from None
    return record


def _record(value, cls, fields):
    if type(value) is cls:
        return _row_exact(value) if cls is RowRecord else _support_exact(value)
    _fields(value, fields)
    if cls is RowRecord: _row_parts(value['keys'], value['values'], value['reasons'])
    else: _support_parts(**{name: value[name] for name in fields})
    return value


def _get(record, field):
    return record[field] if type(record) in (dict, OwnedMap) else object.__getattribute__(record, field)


def _cardinality(dims, coordinates):
    count = 1
    for name in dims: count *= len(coordinates[name].values)
    return count


def _position(index, dims, coordinates, wanted):
    stride = 1
    for name in reversed(dims):
        length = len(coordinates[name].values)
        if name == wanted: return (index // stride) % length
        stride *= length
    raise Refusal('invalid_result')


def _keys_at(keys, dims, coordinates, index):
    _map(keys, 16)
    if len(keys) != len(dims) or any(name not in keys for name in dims):
        raise Refusal('invalid_result')
    for name in dims:
        coordinate = coordinates[name]
        _typed_scalar(keys[name], coordinate.dtype, coordinate=True)
        position = _position(index, dims, coordinates, name)
        expected = coordinate.values[coordinate.sorted_indices[position]]
        if not _same_scalar(keys[name], expected): raise Refusal('invalid_result')


def _effective(column):
    operation = column['unit_operation']
    return operation['source_unit'] if operation['target_unit'] is None else operation['target_unit']


def _check_result_parts(version, row_dims, units, rows, support, plan):
    from .plan import _plan_exact
    _plan_exact(plan)
    exact_int(version, 'invalid_result', minimum=1, maximum=1)
    _sequence(row_dims, 16)
    for name in row_dims: validate_name(name, 'invalid_result')
    if tuple(row_dims) != plan.recipe.row_dims: raise Refusal('invalid_result')
    _map(units)
    if len(units) != len(plan.columns): raise Refusal('invalid_result')
    for name, unit in units.items(): validate_name(name, 'invalid_result'); validate_unit(unit, 'invalid_result')
    for column in plan.columns:
        if column['name'] not in units or not _same_scalar(units[column['name']], _effective(column)):
            raise Refusal('invalid_result')
    _sequence(rows, r.OUTPUT_ROWS_LIMIT); _sequence(support, r.SUPPORT_RECORDS_LIMIT)
    if len(rows) != _cardinality(row_dims, plan.coordinates): raise Refusal('invalid_result')
    if len(support) != sum(stage['support_count'] for column in plan.columns for stage in column['stages']):
        raise Refusal('invalid_result')
    # Finish every local record/type check before any contextual equality.
    for row in rows: _record(row, RowRecord, _ROW_FIELDS)
    for record in support: _record(record, SupportRecord, _SUPPORT_FIELDS)
    for column in plan.columns:
        for stage in column['stages']:
            expected_input = _cardinality(stage['dims'], plan.coordinates)
            for local in range(stage['support_count']):
                record = support[stage['support_start'] + local]
                if (_get(record, 'column') != column['name'] or _get(record, 'stage') != stage['name'] or
                        not _same_scalar(_get(record, 'unit'), units[column['name']]) or
                        _get(record, 'n_input') != expected_input): raise Refusal('invalid_result')
                _keys_at(_get(record, 'keys'), stage['support_dims'], plan.coordinates, local)
                valid = _get(record, 'n_valid'); positive = _get(record, 'n_positive_weight_valid')
                total = _get(record, 'weight_total'); valid_weight = _get(record, 'weight_valid')
                weighted = stage['op'] == 'weighted_mean'
                wanted = (('missing_values',) if stage['missing'] == 'propagate' and valid != expected_input else ())
                if valid < stage['min_count']: wanted += ('insufficient_count',)
                if weighted and valid_weight == 0: wanted += ('zero_weight',)
                if tuple(_get(record, 'reasons')) != wanted: raise Refusal('invalid_result')
                if not weighted and (positive != valid or total != float(expected_input) or valid_weight != float(valid)):
                    raise Refusal('invalid_result')
    for index, row in enumerate(rows):
        _keys_at(_get(row, 'keys'), row_dims, plan.coordinates, index)
        values, reasons = _get(row, 'values'), _get(row, 'reasons')
        if len(values) != len(plan.columns): raise Refusal('invalid_result')
        for column in plan.columns:
            name = column['name']
            if name not in values or name not in reasons: raise Refusal('invalid_result')
            floating = column['output_dtype'] in ('float32', 'float64')
            _typed_scalar(values[name], column['output_dtype'], nullable=floating)
            if column['stages']:
                final = column['stages'][-1]; offset = 0
                for dim in final['support_dims']:
                    offset = offset * len(plan.coordinates[dim].values) + _position(index, row_dims, plan.coordinates, dim)
                record = support[final['support_start'] + offset]
                if (not _same_scalar(values[name], _get(record, 'value')) or
                        tuple(reasons[name]) != tuple(_get(record, 'reasons'))): raise Refusal('invalid_result')
            elif tuple(reasons[name]) != (('missing_values',) if values[name] is None and floating else ()):
                raise Refusal('invalid_result')


def _record_projection(record, fields):
    return {name: _get(record, name) for name in fields}


def _result_object_bound(version, row_dims, units, rows, support):
    # Scalar projections only; at most one bounded shallow record wrapper lives.
    fixed = primitive_bounds(dict(version=version, row_dims=row_dims, units=units,
                                  rows=(), support=()), code='invalid_result').object_bytes
    total = fixed + 136*(len(rows) + len(support))
    for records, fields in ((rows, _ROW_FIELDS), (support, _SUPPORT_FIELDS)):
        for record in records:
            total += 128 + primitive_bounds(_record_projection(record, fields), code='invalid_result').object_bytes
            if total > r.LOGICAL_JOURNEY_LIMIT: raise Refusal('estimated_memory_limit')
    return total


@dataclass(frozen=True, slots=True, init=False, eq=False)
class ComputationResult:
    version: int
    row_dims: tuple
    units: OwnedMap
    rows: tuple
    support: tuple
    _plan: BoundPlan

    def __init_subclass__(cls, **kwargs): raise TypeError('ComputationResult is final')
    def __init__(self, *, version, row_dims, units, rows, support, _plan):
        _require_uninitialized(self, 'version', 'invalid_result')
        from .source import _owned_attempt, _raise_owned
        owned, error = _owned_attempt(_result_ownership, version, row_dims, units, rows, support, _plan)
        version = row_dims = units = rows = support = _plan = None
        if error is not None:
            self = None
            _raise_owned(error)
        for name, value in owned: object.__setattr__(self, name, value)

    def iter_rows(self):
        _result_exact(self)
        return iter(self.rows)

    def iter_support(self, column=None, stage=None):
        for value in (column, stage):
            if value is not None: validate_name(value, 'invalid_result')
        _result_exact(self)
        return (record for record in self.support if
                (column is None or record.column == column) and (stage is None or record.stage == stage))

    def to_dict(self):
        return _serialize_result(self, 'dict')

    def iter_json_chunks(self):
        return _serialize_result(self, 'chunks')

    def to_json(self):
        return _serialize_result(self, 'bytes')


def _result_ownership(version, row_dims, units, rows, support, plan):
    _check_result_parts(version, row_dims, units, rows, support, plan)
    if _result_object_bound(version, row_dims, units, rows, support) > plan.estimates['result_objects_bytes']:
        raise Refusal('invalid_result')
    owned_rows = _adopt_records(rows, RowRecord, _ROW_FIELDS)
    owned_support = _adopt_records(support, SupportRecord, _SUPPORT_FIELDS)
    return (('version', version), ('row_dims', tuple(row_dims)),
        ('units', _own_map(units)), ('rows', owned_rows), ('support', owned_support), ('_plan', plan))


def _adopt_records(values, cls, fields):
    if all(type(value) is cls for value in values): return tuple(values)
    owned = []
    for value in values:
        owned.append(value if type(value) is cls else cls(**{name: value[name] for name in fields}))
    return tuple(owned)


def _result_exact(result):
    if type(result) is not ComputationResult: raise Refusal('invalid_result')
    try:
        if type(result.row_dims) is not tuple or type(result.units) is not OwnedMap or type(result.rows) is not tuple or type(result.support) is not tuple:
            raise Refusal('invalid_result')
        if any(type(row) is not RowRecord for row in result.rows) or any(type(s) is not SupportRecord for s in result.support):
            raise Refusal('invalid_result')
        _check_result_parts(result.version, result.row_dims, result.units, result.rows, result.support, result._plan)
    except AttributeError: raise Refusal('invalid_result') from None
    return result


def _serialize_guard(result):
    _result_exact(result)
    from .admission import _required_inputs, _guard, _active_plan
    # A matching result may retain C while the original active anchor is A.
    # Preserve that anchor and every original handle rather than reanchoring.
    plan = _active_plan()
    if plan is None: plan = result._plan
    with _required_inputs(plan=plan, result=result): _guard('serialize')


def _serialize_compute(result, kind):
    _serialize_guard(result)
    if kind == 'dict':
        return dict(version=result.version, row_dims=list(result.row_dims), units=dict(result.units),
            rows=[row.to_dict() for row in result.rows], support=[record.to_dict() for record in result.support])
    length = _serialized_size(result)
    if kind == 'chunks': return _owned_chunk_iterator(result)
    output = bytearray(length)
    offset = 0
    for fragment in _result_chunks(result):
        end = offset + len(fragment); output[offset:end] = fragment; offset = end
    return bytes(output)


def _serialize_result(result, kind):
    from .source import _owned_attempt, _raise_owned
    output, error = _owned_attempt(_serialize_compute, result, kind)
    result = None
    if error is not None: _raise_owned(error)
    return output


def _owned_chunk_iterator(result):
    """Borrow one result with no admission context held across a yield.

    The ordinary wrapper also owns the pre-first-next interval: throwing into
    an unstarted generator must not leave its result-bearing frame attached to
    the escaping exception. This bounded wrapper replaces a suspended wrapper
    generator; it adds no result/parse forest or admission-context lifetime.
    """
    return _ResultChunkIterator(result)


class _ResultChunkIterator:
    __slots__ = ('_result', '_inner', '_closed')
    def __init_subclass__(cls, **kwargs): raise TypeError('Result chunk iterator is final')
    def __init__(self, result):
        self._result = result; self._inner = None; self._closed = False
    def __iter__(self): return self
    def __next__(self): return _chunk_call(self, 'next')
    def close(self): return _chunk_call(self, 'close')
    def throw(self, error): return _chunk_call(self, 'throw', error)


def _retire_chunks(iterator):
    inner = iterator._inner
    iterator._result = iterator._inner = None
    iterator._closed = True
    if inner is not None: inner.close()


def _drive_chunks(iterator, kind, error):
    try:
        if kind == 'close':
            _retire_chunks(iterator)
            return None
        if kind == 'throw':
            if not isinstance(error, BaseException):
                raise TypeError('throw requires an exception instance')
            if iterator._inner is None:
                _retire_chunks(iterator)
                raise error
            return iterator._inner.throw(error)
        if iterator._closed: raise StopIteration
        if iterator._inner is None:
            iterator._inner = _result_chunks(iterator._result)
            iterator._result = None
        return next(iterator._inner)
    except BaseException:
        try: _retire_chunks(iterator)
        except BaseException as cleanup:
            # Only this owned cleanup error is detached. It cannot replace the
            # already escaping primary refusal/cancellation/StopIteration.
            BaseException.__traceback__.__set__(cleanup, None)
            BaseException.__context__.__set__(cleanup, None)
            BaseException.__cause__.__set__(cleanup, None)
        raise


def _chunk_call(iterator, kind, error=None):
    from .source import _owned_attempt, _raise_owned
    value, failure = _owned_attempt(_drive_chunks, iterator, kind, error)
    iterator = error = None
    if failure is not None: _raise_owned(failure)
    return value


def _record_chunks(record, fields):
    yield b'{'
    for index, name in enumerate(fields):
        if index: yield b','
        yield from _string_chunks(name); yield b':'
        yield from _chunks(object.__getattribute__(record, name))
    yield b'}'


def _result_chunks(result):
    yield b'{"row_dims":'; yield from _chunks(result.row_dims)
    yield b',"rows":['
    for index, row in enumerate(result.rows):
        if index: yield b','
        yield from _record_chunks(row, _ROW_FIELDS)
    yield b'],"support":['
    for index, record in enumerate(result.support):
        if index: yield b','
        yield from _record_chunks(record, _SUPPORT_FIELDS)
    yield b'],"units":'; yield from _chunks(result.units)
    yield b',"version":1}\n'


def _serialized_size(result):
    count = 0
    for fragment in _result_chunks(result):
        count += len(fragment)
        if count > r.BUNDLE_BYTES_LIMIT: raise Refusal('bundle_bytes_limit')
        if count > result._plan.estimates['result_json_bytes']:
            raise ComputationError('resource_estimate_mismatch')
    return count
