"""Exact immutable foundation models; no scientific/native import on construction."""
from dataclasses import dataclass
import math
import re
import struct

from .codec import (Refusal, ComputationError, OwnedMap, canonical_bytes,
    exact_int, freeze, iter_json_chunks, preflight_json, primitive_bounds,
    strict_loads, thaw, utf8_length, DEFAULT_PARSE_BASELINE_BYTES)
from .resources import (JSON_INTEGER_MIN, JSON_INTEGER_MAX, COUNT_MAX,
    COORDINATE_RAW_BYTES_LIMIT, COORDINATE_CANONICAL_BYTES_LIMIT,
    COORDINATE_LABEL_UTF8_BYTES_LIMIT, LABEL_UTF8_BYTES_LIMIT,
    DIMENSION_LENGTH_LIMIT, SHAPE_PRODUCT_LIMIT, RANK_LIMIT,
    METADATA_BYTES_LIMIT, METADATA_DEPTH_LIMIT, METADATA_MAP_LIMIT,
    METADATA_SEQUENCE_LIMIT, METADATA_CONTAINER_LIMIT, METADATA_SCALAR_LIMIT,
    NAME_BYTES_LIMIT, UNIT_BYTES_LIMIT, SELECTED_NUMERIC_BYTES_LIMIT,
    RECIPE_BYTES_LIMIT, COLUMN_LIMIT, STAGE_LIMIT)


# Immutable stock dtype data, without importing numpy just to parse a recipe.
_NUMERIC = (
    ('int8', '|i1', 1, -(2**7), 2**7-1),
    ('int16', '<i2', 2, -(2**15), 2**15-1),
    ('int32', '<i4', 4, -(2**31), 2**31-1),
    ('int64', '<i8', 8, -(2**63), 2**63-1),
    ('uint8', '|u1', 1, 0, 2**8-1),
    ('uint16', '<u2', 2, 0, 2**16-1),
    ('uint32', '<u4', 4, 0, 2**32-1),
    ('uint64', '<u8', 8, 0, 2**64-1),
    ('float32', '<f4', 4, None, None),
    ('float64', '<f8', 8, None, None),
)


def _dtype_info(value, code='invalid_source', *, coordinate=False):
    if type(value) is not str:
        raise Refusal(code)
    for info in _NUMERIC:
        if value == info[1] or (not coordinate and value == info[0]):
            return info
    raise Refusal(code)


def numeric_dtype(value, code='invalid_source'):
    return _dtype_info(value, code)[0]


def validate_name(value, code='invalid_source'):
    count = utf8_length(value, code, maximum=NAME_BYTES_LIMIT)
    if count == 0 or any(ord(c) < 32 or 127 <= ord(c) <= 159 or c in '/\\' for c in value):
        raise Refusal(code)
    return value


def validate_unit(value, code='invalid_source', *, raw_coordinate=False):
    if type(raw_coordinate) is not bool:
        raise Refusal(code)
    if value is None:
        return None
    count = utf8_length(value, code, maximum=UNIT_BYTES_LIMIT)
    if count == 0 or any((ord(c) < 32 and not (raw_coordinate and c == '\t'))
                         or 127 <= ord(c) <= 159 for c in value):
        raise Refusal(code)
    return value


def _fields(value, names, code):
    if type(value) is not dict:
        raise Refusal(code)
    for key in value:
        if type(key) is not str:
            raise Refusal(code)
    if set(value) != set(names):
        raise Refusal(code)
    return value


def _sequence(value, code, *, minimum=0, maximum=RANK_LIMIT, public=False):
    if type(value) not in ((list,) if public else (list, tuple)):
        raise Refusal(code)
    if not minimum <= len(value) <= maximum:
        raise Refusal(code)
    return value


class _JsonModel:
    __slots__ = ()

    def iter_json_chunks(self):
        return iter_json_chunks(self._projection(), limit=METADATA_BYTES_LIMIT)

    def to_json(self):
        return canonical_bytes(self._projection(), limit=METADATA_BYTES_LIMIT)

    def to_dict(self):
        return thaw(self._projection())


def _require_uninitialized(instance, first_field, code):
    """Reject ordinary repeat initialization before inspecting new arguments."""
    try:
        object.__getattribute__(instance, first_field)
    except AttributeError:
        return
    raise Refusal(code, 'Immutable model is already initialized.')


@dataclass(frozen=True, slots=True, init=False)
class SourceIdentity(_JsonModel):
    kind: str
    sha256: str
    size_bytes: int

    def __init__(self, kind, sha256, size_bytes):
        _require_uninitialized(self, 'kind', 'invalid_source')
        if type(kind) is not str or kind not in ('memory', 'file'):
            raise Refusal('invalid_source')
        if (type(sha256) is not str or len(sha256) != 64 or
                any(c not in '0123456789abcdef' for c in sha256)):
            raise Refusal('invalid_source')
        exact_int(size_bytes, 'invalid_source')
        object.__setattr__(self, 'kind', kind)
        object.__setattr__(self, 'sha256', sha256)
        object.__setattr__(self, 'size_bytes', size_bytes)

    @classmethod
    def from_dict(cls, value):
        _fields(value, ('kind', 'sha256', 'size_bytes'), 'invalid_source')
        return cls(value['kind'], value['sha256'], value['size_bytes'])

    def _projection(self):
        return {'kind': self.kind, 'sha256': self.sha256, 'size_bytes': self.size_bytes}


@dataclass(frozen=True, slots=True, init=False)
class Coordinate(_JsonModel):
    dtype: str
    values: tuple
    sorted_indices: tuple

    def __init__(self, dtype, values, sorted_indices, *, row=False):
        _require_uninitialized(self, 'dtype', 'invalid_coordinate')
        if type(row) is not bool or type(dtype) is not str:
            raise Refusal('invalid_coordinate')
        _sequence(values, 'invalid_coordinate', minimum=1, maximum=DIMENSION_LENGTH_LIMIT)
        _sequence(sorted_indices, 'invalid_coordinate', minimum=1, maximum=DIMENSION_LENGTH_LIMIT)
        width = _unicode_width(dtype)
        info = None if width is not None else _dtype_info(dtype, 'invalid_coordinate', coordinate=True)
        if len(sorted_indices) != len(values):
            raise Refusal('invalid_coordinate')
        # Selected models contain scalar labels, not original ndarray storage.
        # Q_raw belongs to the qualified source/storage route, never a guessed
        # dense <U<N> allocation during plan loading or fixed-S canonicalization.
        minimum_values = 2 + len(values)-1 + len(values)*(2 if width is not None else 32)
        if _coordinate_json_bound(dtype, len(values), minimum_values) > COORDINATE_CANONICAL_BYTES_LIMIT:
            raise Refusal('coordinate_bytes_limit', 'Canonical coordinate representation exceeds its byte limit.')
        json_values = 2 + len(values)-1
        utf8_total = 0
        # Qualify every exact element before missingness/finiteness branches.
        for value in values:
            kind = type(value)
            if value is None or (kind is float and not math.isfinite(value)):
                continue
            if width is not None:
                if kind is not str:
                    raise Refusal('invalid_coordinate')
            elif info[3] is not None:
                if kind is not int:
                    raise Refusal('invalid_coordinate')
            elif kind is not float:
                raise Refusal('invalid_coordinate')
        for index in sorted_indices:
            exact_int(index, 'invalid_coordinate', maximum=len(values)-1)
        if any(value is None or (type(value) is float and math.isnan(value)) for value in values):
            raise Refusal('missing_row_key' if row else 'missing_coordinate')
        if any(type(value) is float and not math.isfinite(value) for value in values):
            raise Refusal('nonfinite_coordinate')
        for value in values:
            # Missing sentinel routes are selected-phase errors, never labels.
            if value is None or (type(value) is float and math.isnan(value)):
                raise Refusal('missing_row_key' if row else 'missing_coordinate')
            if type(value) is float and not math.isfinite(value):
                raise Refusal('nonfinite_coordinate')
            if width is not None:
                if type(value) is not str or len(value) > width:
                    raise Refusal('invalid_coordinate')
                n = utf8_length(value, 'invalid_coordinate')
                if n > LABEL_UTF8_BYTES_LIMIT:
                    raise Refusal('label_bytes_limit')
                utf8_total += n
                if utf8_total > COORDINATE_LABEL_UTF8_BYTES_LIMIT:
                    raise Refusal('coordinate_bytes_limit', 'Coordinate label union exceeds its UTF-8 byte limit.')
                json_values += 6*n + 2
            elif info[3] is not None:
                exact_int(value, 'invalid_coordinate', minimum=info[3], maximum=info[4])
                json_values += 32
            else:
                if type(value) is not float:
                    raise Refusal('invalid_coordinate')
                if info[0] == 'float32':
                    try:
                        converted = struct.unpack('<f', struct.pack('<f', value))[0]
                    except (OverflowError, struct.error):
                        raise Refusal('invalid_coordinate') from None
                    if converted != value or math.copysign(1, converted) != math.copysign(1, value):
                        raise Refusal('invalid_coordinate')
                json_values += 32
        for index in sorted_indices:
            exact_int(index, 'invalid_coordinate', maximum=len(values)-1)
        # Precharge complete selected Coordinate before permutation allocation.
        if _coordinate_json_bound(dtype, len(values), json_values) > COORDINATE_CANONICAL_BYTES_LIMIT:
            raise Refusal('coordinate_bytes_limit', 'Canonical coordinate representation exceeds its byte limit.')
        # Values and indices have all been exact-type-qualified before comparison.
        expected = sorted(range(len(values)), key=values.__getitem__)
        for previous, current in zip(expected, expected[1:]):
            if values[previous] == values[current]:
                raise Refusal('duplicate_row_key' if row else 'duplicate_coordinate')
        if any(actual != target for actual, target in zip(sorted_indices, expected)):
            raise Refusal('invalid_coordinate')
        owned_values = tuple(values)
        owned_indices = tuple(sorted_indices)
        object.__setattr__(self, 'dtype', dtype)
        object.__setattr__(self, 'values', owned_values)
        object.__setattr__(self, 'sorted_indices', owned_indices)

    @classmethod
    def from_dict(cls, value, *, row=False):
        _fields(value, ('dtype', 'values', 'sorted_indices'), 'invalid_coordinate')
        _sequence(value['values'], 'invalid_coordinate', public=True, minimum=1, maximum=DIMENSION_LENGTH_LIMIT)
        _sequence(value['sorted_indices'], 'invalid_coordinate', public=True, minimum=1, maximum=DIMENSION_LENGTH_LIMIT)
        return cls(value['dtype'], value['values'], value['sorted_indices'], row=row)

    @classmethod
    def from_fixed_bytes(cls, dtype, raw, *, row=False):
        if type(row) is not bool or type(dtype) is not str or type(raw) is not bytes:
            raise Refusal('invalid_coordinate')
        if len(dtype) > 6 or re.fullmatch(r'\|S[1-9][0-9]*', dtype, re.ASCII) is None:
            raise Refusal('invalid_coordinate')
        width = int(dtype[2:])
        if width > 4096 or len(raw) == 0 or len(raw) % width:
            raise Refusal('invalid_coordinate')
        count = len(raw)//width
        if len(raw) > COORDINATE_RAW_BYTES_LIMIT or count > DIMENSION_LENGTH_LIMIT:
            raise Refusal('coordinate_bytes_limit', 'Raw coordinate storage exceeds its byte limit.')
        canonical = '<U'+str(width)
        values_bound = 2 + count-1 + count*(6*width+2)
        # N bytes per raw fixed string bound both its UTF-8 bytes and character
        # count. Canonical storage has the full <U<N> width, not inferred width.
        if count*width > COORDINATE_LABEL_UTF8_BYTES_LIMIT:
            raise Refusal('coordinate_bytes_limit', 'Coordinate label union exceeds its UTF-8 byte limit.')
        if _coordinate_json_bound(canonical, count, values_bound) > COORDINATE_CANONICAL_BYTES_LIMIT:
            raise Refusal('coordinate_bytes_limit', 'Canonical coordinate representation exceeds its byte limit.')
        values = []
        for offset in range(0, len(raw), width):
            try:
                value = raw[offset:offset+width].rstrip(b'\0').decode('utf-8')
            except UnicodeDecodeError:
                raise Refusal('invalid_coordinate') from None
            values.append(value)
        order = sorted(range(count), key=values.__getitem__)
        return cls(canonical, values, order, row=row)

    def _projection(self):
        return {'dtype': self.dtype, 'values': self.values, 'sorted_indices': self.sorted_indices}


def _unicode_width(dtype):
    if len(dtype) <= 6 and re.fullmatch(r'<U[1-9][0-9]*', dtype, re.ASCII):
        width = int(dtype[2:])
        if width <= 4096:
            return width
    return None


def _coordinate_json_bound(dtype, count, values_bound):
    # Exact map J punctuation and field-name/dtype J, numeric32 indices, LF.
    indices = 2 + max(count-1, 0) + 32*count
    return (2 + 2 + (6*5+2)+1+(6*utf8_length(dtype)+2)
            + (6*6+2)+1+values_bound + (6*14+2)+1+indices + 1)


@dataclass(frozen=True, slots=True, init=False)
class ArrayBuffer:
    """Immutable byte storage, not a finiteness/measurement semantic proof."""
    dtype: str
    shape: tuple
    data: bytes

    def __init__(self, dtype, shape, data):
        _require_uninitialized(self, 'dtype', 'invalid_source')
        info = _dtype_info(dtype)
        _sequence(shape, 'invalid_source')
        if type(data) is not bytes:
            raise Refusal('invalid_source')
        product = 1
        for length in shape:
            exact_int(length, 'invalid_source', minimum=1, maximum=DIMENSION_LENGTH_LIMIT)
            if length > SHAPE_PRODUCT_LIMIT//product:
                raise Refusal('selected_numeric_bytes_limit')
            product *= length
        if product > SELECTED_NUMERIC_BYTES_LIMIT//info[2]:
            raise Refusal('selected_numeric_bytes_limit')
        if len(data) != product*info[2]:
            raise Refusal('invalid_source')
        owned_shape = tuple(shape)
        object.__setattr__(self, 'dtype', info[0])
        object.__setattr__(self, 'shape', owned_shape)
        object.__setattr__(self, 'data', data)

    @property
    def nbytes(self):
        return len(self.data)

    def view(self):
        import numpy as np
        return np.frombuffer(self.data, dtype=self.dtype).reshape(self.shape)


@dataclass(frozen=True, slots=True, init=False)
class MetadataValue(_JsonModel):
    """Injectively tagged metadata. No NumPy coercion or object callbacks."""
    _tagged: OwnedMap

    def __init__(self, value):
        _require_uninitialized(self, '_tagged', 'invalid_source')
        _metadata_measure(value)
        counters = [0, 0]  # scalar/key occurrences, containers
        tagged = _metadata_tag(value, 0, counters)
        preflight_json(tagged, limit=METADATA_BYTES_LIMIT, code='metadata_bytes_limit')
        owned_tagged = freeze(tagged)
        object.__setattr__(self, '_tagged', owned_tagged)

    @classmethod
    def from_dict(cls, value):
        # A bounded strict tagged tree is checked before ordinary reconstruction.
        bound = primitive_bounds(value, code='invalid_source')
        if bound.json_bytes + 1 > METADATA_BYTES_LIMIT:
            raise Refusal('metadata_bytes_limit')
        return cls(_metadata_untag(value, 0, [0, 0]))

    def _projection(self):
        return self._tagged

    @classmethod
    def _from_owned_tagged(cls, value):
        """Validate and adopt one immutable tree, without an untagged copy."""
        if cls is not MetadataValue:
            raise Refusal('invalid_source')
        from ._resource_inputs import _validate_metadata, _owned_cost
        from ._resource_bounds import _Fold
        _validate_metadata(value, _Fold())
        if _owned_cost(value).json_bytes + 1 > METADATA_BYTES_LIMIT:
            raise Refusal('metadata_bytes_limit')
        instance = object.__new__(cls)
        object.__setattr__(instance, '_tagged', value)
        return instance

    def to_python(self):
        return _metadata_untag(self.to_dict(), 0, [0, 0])


def _metadata_scalar(counters):
    counters[0] += 1
    if counters[0] > METADATA_SCALAR_LIMIT:
        raise Refusal('metadata_bytes_limit')


def _metadata_container(counters, depth):
    counters[1] += 1
    if depth >= METADATA_DEPTH_LIMIT or counters[1] > METADATA_CONTAINER_LIMIT:
        raise Refusal('metadata_bytes_limit')


def _metadata_tag(value, depth, counters):
    kind = type(value)
    if kind in (list, tuple, dict):
        _metadata_container(counters, depth)
        if kind is dict:
            if len(value) > METADATA_MAP_LIMIT:
                raise Refusal('metadata_bytes_limit')
            for key in value:
                _metadata_scalar(counters)
                utf8_length(key, 'invalid_source', maximum=LABEL_UTF8_BYTES_LIMIT)
            return {'type': 'map', 'items': [[key, _metadata_tag(value[key], depth+1, counters)]
                                            for key in sorted(value)]}
        if len(value) > METADATA_SEQUENCE_LIMIT:
            raise Refusal('metadata_bytes_limit')
        return {'type': 'list', 'items': [_metadata_tag(child, depth+1, counters) for child in value]}
    _metadata_scalar(counters)
    if value is None:
        return {'type': 'null'}
    if kind is bool:
        return {'type': 'bool', 'value': value}
    if kind is int:
        exact_int(value, 'invalid_source', minimum=JSON_INTEGER_MIN, maximum=JSON_INTEGER_MAX)
        return {'type': 'int', 'value': value}
    if kind is float:
        if not math.isfinite(value):
            return {'type': 'float_special', 'value': 'nan' if math.isnan(value) else '+inf' if value > 0 else '-inf'}
        return {'type': 'float', 'value': value}
    if kind is str:
        utf8_length(value, 'invalid_source', maximum=LABEL_UTF8_BYTES_LIMIT)
        return {'type': 'str', 'value': value}
    raise Refusal('invalid_source')


def _metadata_untag(value, depth, counters):
    if type(value) is not dict:
        raise Refusal('invalid_source')
    for key in value:
        if type(key) is not str:
            raise Refusal('invalid_source')
    tag = value.get('type')
    if type(tag) is not str:
        raise Refusal('invalid_source')
    if tag == 'null':
        _fields(value, ('type',), 'invalid_source'); _metadata_scalar(counters)
        return None
    if tag in ('map', 'list'):
        _fields(value, ('type', 'items'), 'invalid_source')
        _metadata_container(counters, depth)
        items = value['items']
        _sequence(items, 'invalid_source', public=True,
                  maximum=METADATA_MAP_LIMIT if tag == 'map' else METADATA_SEQUENCE_LIMIT)
        if tag == 'list':
            return [_metadata_untag(child, depth+1, counters) for child in items]
        result, previous = {}, None
        for pair in items:
            _sequence(pair, 'invalid_source', public=True, minimum=2, maximum=2)
            key, child = pair
            utf8_length(key, 'invalid_source', maximum=LABEL_UTF8_BYTES_LIMIT)
            _metadata_scalar(counters)
            if previous is not None and key <= previous:
                raise Refusal('invalid_source')
            result[key] = _metadata_untag(child, depth+1, counters)
            previous = key
        return result
    _fields(value, ('type', 'value'), 'invalid_source')
    raw = value['value']
    _metadata_scalar(counters)
    if tag == 'bool' and type(raw) is bool:
        return raw
    if tag == 'int':
        return exact_int(raw, 'invalid_source', minimum=JSON_INTEGER_MIN, maximum=JSON_INTEGER_MAX)
    if tag == 'float' and type(raw) is float and math.isfinite(raw):
        return raw
    if tag == 'str' and type(raw) is str:
        utf8_length(raw, 'invalid_source', maximum=LABEL_UTF8_BYTES_LIMIT)
        return raw
    if tag == 'float_special' and type(raw) is str and raw in ('nan', '+inf', '-inf'):
        return float(raw)
    raise Refusal('invalid_source')


def descriptor_object_scalar(value):
    if value is None or type(value) is str or (type(value) is float and not math.isfinite(value)):
        return MetadataValue(value)
    raise Refusal('unsupported_source_storage')


def _metadata_measure(value):
    """Qualify and charge the complete tagged forest before constructing it.

    Counter costs use frozen J/P, including tag keys, wrappers, pair lists and
    repeated occurrences. No raw or tagged metadata forest is copied here.
    """
    counters = [0, 0]
    json_total = 1  # final LF
    object_total = 0

    def add(j, p):
        nonlocal json_total, object_total
        json_total += j
        object_total += p
        if json_total > METADATA_BYTES_LIMIT:
            raise Refusal('metadata_bytes_limit')
        # This is primitive-model boundedness, not formula2 journey admission.
        from .resources import LOGICAL_JOURNEY_LIMIT
        if object_total > LOGICAL_JOURNEY_LIMIT:
            raise Refusal('estimated_memory_limit')

    def string_cost(text):
        count = utf8_length(text, 'invalid_source', maximum=LABEL_UTF8_BYTES_LIMIT)
        return 6*count+2, 128+4*count

    def scalar(tag, raw, no_value=False):
        # Only a bounded primitive is present in this ephemeral tag projection.
        projection = {'type': tag} if no_value else {'type': tag, 'value': raw}
        cost = primitive_bounds(projection, code='invalid_source')
        add(cost.json_bytes, cost.object_bytes)

    def visit(item, depth):
        kind = type(item)
        if kind in (dict, list, tuple):
            _metadata_container(counters, depth)
            maximum = METADATA_MAP_LIMIT if kind is dict else METADATA_SEQUENCE_LIMIT
            if len(item) > maximum:
                raise Refusal('metadata_bytes_limit')
            tag = 'map' if kind is dict else 'list'
            # Tag object and its items-list shell, without child values.
            shell = primitive_bounds({'type': tag, 'items': []})
            add(shell.json_bytes+max(len(item)-1, 0), shell.object_bytes+128*len(item))
            if kind is dict:
                for key in item:
                    string_cost(key)  # qualify every key before sorting/lookup
                for key in sorted(item):
                    _metadata_scalar(counters)
                    j, p = string_cost(key)
                    add(3+j, 512+256+p)  # [key, child] pair shell and key
                    visit(item[key], depth+1)
            else:
                for child in item:
                    visit(child, depth+1)
            return
        _metadata_scalar(counters)
        if item is None:
            scalar('null', None, True)
        elif kind is bool:
            scalar('bool', item)
        elif kind is int:
            exact_int(item, 'invalid_source', minimum=JSON_INTEGER_MIN, maximum=JSON_INTEGER_MAX)
            scalar('int', item)
        elif kind is float:
            if math.isfinite(item):
                scalar('float', item)
            else:
                scalar('float_special', 'nan' if math.isnan(item) else '+inf' if item > 0 else '-inf')
        elif kind is str:
            string_cost(item)
            scalar('str', item)
        else:
            raise Refusal('invalid_source')

    visit(value, 0)
    return json_total, object_total


def _names(value, *, nonempty=False):
    _sequence(value, 'invalid_recipe', minimum=1 if nonempty else 0, public=True)
    for name in value:
        validate_name(name, 'invalid_recipe')
    if len(set(value)) != len(value):
        raise Refusal('invalid_recipe')
    return value


_STAGE_COMMON = ('name', 'dims', 'op', 'missing', 'min_count')
_STAGE_UNION = _STAGE_COMMON + ('weights', 'weight_unit')
_COLUMN_FIELDS = ('name', 'source', 'source_unit', 'target_unit', 'broadcast', 'stages')


def _recipe_stage(value, position, row_dims, removed, *, owned=False):
    # v5: exact keys/known union and all present primitive types precede branch.
    if type(owned) is not bool: raise Refusal('invalid_recipe')
    if owned:
        from ._resource_inputs import _owned_map
        _owned_map(value,maximum=7,code='invalid_recipe')
    elif type(value) is not dict: raise Refusal('invalid_recipe')
    for key in value:
        if type(key) is not str:
            raise Refusal('invalid_recipe')
    fields = set(value)
    if fields - set(_STAGE_UNION) or not set(('name', 'dims', 'op', 'min_count')) <= fields:
        raise Refusal('invalid_recipe')
    validate_name(value['name'], 'invalid_recipe')
    if owned:
        from ._resource_inputs import _names as _owned_names
        dims=_owned_names(value['dims'],'invalid_recipe')
        if not dims: raise Refusal('invalid_recipe')
    else: dims = _names(value['dims'], nonempty=True)
    op = value['op']
    if type(op) is not str or op not in ('mean', 'weighted_mean', 'min', 'max'):
        raise Refusal('invalid_recipe')
    exact_int(value['min_count'], 'invalid_recipe', minimum=1, maximum=DIMENSION_LENGTH_LIMIT)
    if 'missing' in fields:
        missing = value['missing']
        if type(missing) is not str or missing not in ('skip', 'propagate'):
            raise Refusal('invalid_recipe')
    if 'weights' in fields:
        validate_name(value['weights'], 'invalid_recipe')
    if 'weight_unit' in fields:
        validate_unit(value['weight_unit'], 'invalid_recipe')
    expected = set(_STAGE_UNION if op == 'weighted_mean' else _STAGE_COMMON)
    if 'missing' not in fields:
        if fields == expected - {'missing'}:
            raise Refusal('missing_stage_policy')
        raise Refusal('invalid_recipe')
    if position == 1 and op == 'weighted_mean':
        raise Refusal('unsupported_later_stage_weights')
    if fields != expected:
        raise Refusal('invalid_recipe')
    if set(dims) & (set(row_dims) | removed):
        raise Refusal('invalid_recipe')
    return value


@dataclass(frozen=True, slots=True, init=False)
class Recipe(_JsonModel):
    version: int
    row_dims: tuple
    columns: tuple

    def __init__(self, version, row_dims, columns):
        _require_uninitialized(self, 'version', 'invalid_recipe')
        exact_int(version, 'invalid_recipe', minimum=1, maximum=1)
        _names(row_dims)
        _sequence(columns, 'invalid_recipe', minimum=1, maximum=COLUMN_LIMIT, public=True)
        column_names = set()
        for column in columns:
            _fields(column, _COLUMN_FIELDS, 'invalid_recipe')
            name = validate_name(column['name'], 'invalid_recipe')
            validate_name(column['source'], 'invalid_recipe')
            validate_unit(column['source_unit'], 'invalid_recipe')
            validate_unit(column['target_unit'], 'invalid_recipe')
            _names(column['broadcast'])
            _sequence(column['stages'], 'invalid_recipe', maximum=STAGE_LIMIT, public=True)
            if name in column_names:
                raise Refusal('invalid_recipe')
            column_names.add(name)
            stage_names, removed = set(), set()
            for position, stage in enumerate(column['stages']):
                _recipe_stage(stage, position, row_dims, removed)
                if stage['name'] in stage_names:
                    raise Refusal('invalid_recipe')
                stage_names.add(stage['name'])
                removed.update(stage['dims'])
        # Exact schema caps imply a finite primitive model, independent of source.
        projection = {'version': version, 'row_dims': row_dims, 'columns': columns}
        # Preflight exact bytes, without allocating a serialized whole document.
        # iter_json_chunks does its complete size walk before returning.
        iter_json_chunks(projection, limit=RECIPE_BYTES_LIMIT, code='recipe_bytes_limit')
        owned_rows = tuple(row_dims)
        owned_columns = tuple(freeze(column) for column in columns)
        object.__setattr__(self, 'version', version)
        object.__setattr__(self, 'row_dims', owned_rows)
        object.__setattr__(self, 'columns', owned_columns)

    @classmethod
    def from_dict(cls, value):
        _fields(value, ('version', 'row_dims', 'columns'), 'invalid_recipe')
        return cls(value['version'], value['row_dims'], value['columns'])

    def _projection(self):
        return {'version': self.version, 'row_dims': self.row_dims, 'columns': self.columns}

    def to_json(self):
        return canonical_bytes(self._projection(), limit=RECIPE_BYTES_LIMIT, code='recipe_bytes_limit')

    def iter_json_chunks(self):
        return iter_json_chunks(self._projection(), limit=RECIPE_BYTES_LIMIT, code='recipe_bytes_limit')


def parse_recipe(raw):
    if type(raw) is not bytes:
        raise Refusal('invalid_recipe')
    return Recipe.from_dict(strict_loads(raw, limit=RECIPE_BYTES_LIMIT,
        limit_code='recipe_bytes_limit', baseline_bytes=DEFAULT_PARSE_BASELINE_BYTES))


class _TypedMap:
    """Private exact child maps; primitive OwnedMap never holds model objects."""
    __slots__ = ('_items',)
    _child = None
    _maximum = 0

    def __init__(self, value):
        _require_uninitialized(self, '_items', 'invalid_source')
        if type(value) is not dict or len(value) > self._maximum:
            raise Refusal('invalid_source')
        for key, child in value.items():
            validate_name(key)
            if type(child) is not self._child:
                raise Refusal('invalid_source')
        total_json = total_utf8 = total_numeric = 0
        for child in value.values():
            try:
                if self._child is Coordinate:
                    size,utf8 = _validate_coordinate_child(child)
                    total_json += size; total_utf8 += utf8
                    if (total_json > COORDINATE_CANONICAL_BYTES_LIMIT or
                            total_utf8 > COORDINATE_LABEL_UTF8_BYTES_LIMIT):
                        raise Refusal('coordinate_bytes_limit')
                else:
                    _validate_array_child(child)
                    total_numeric += len(child.data)
                    if total_numeric > SELECTED_NUMERIC_BYTES_LIMIT:
                        raise Refusal('selected_numeric_bytes_limit')
            except AttributeError:
                raise Refusal('invalid_source') from None
        object.__setattr__(self, '_items', tuple((key,value[key]) for key in sorted(value)))

    def __setattr__(self, name, value):
        raise AttributeError('Selected maps are immutable')

    def __delattr__(self, name):
        raise AttributeError('Selected maps are immutable')

    def __len__(self): return len(self._items)
    def __iter__(self): return (name for name, _ in self._items)
    def items(self): return self._items

    def __getitem__(self, name):
        if type(name) is not str: raise Refusal('invalid_source')
        for key, child in self._items:
            if key == name: return child
        raise KeyError(name)


class _CoordinateMap(_TypedMap):
    __slots__ = ()
    _child = Coordinate
    _maximum = 16
    def __init_subclass__(cls, **kwargs): raise TypeError('Selected maps are final')


class _ArrayMap(_TypedMap):
    __slots__ = ()
    _child = ArrayBuffer
    _maximum = 64
    def __init_subclass__(cls, **kwargs): raise TypeError('Selected maps are final')


def _validate_coordinate_child(child):
    # Existing immutable objects can be partial or forged via object.__new__.
    # Recheck in place; no replacement Coordinate/value/permutation is retained.
    if type(child) is not Coordinate: raise Refusal('invalid_source')
    dtype, values, indices = child.dtype, child.values, child.sorted_indices
    if type(dtype) is not str or type(values) is not tuple or type(indices) is not tuple:
        raise Refusal('invalid_source')
    if not 1 <= len(values) <= DIMENSION_LENGTH_LIMIT or len(indices) != len(values):
        raise Refusal('invalid_source')
    width = _unicode_width(dtype)
    info = None if width is not None else _dtype_info(dtype, 'invalid_source', coordinate=True)
    json_values = 2 + len(values)-1
    utf8_total = 0
    minimum = json_values + len(values)*(2 if width is not None else 32)
    if _coordinate_json_bound(dtype,len(values),minimum)>COORDINATE_CANONICAL_BYTES_LIMIT:
        raise Refusal('coordinate_bytes_limit')
    for value in values:
        if width is not None:
            if type(value) is not str or len(value) > width:
                raise Refusal('invalid_source')
            size=utf8_length(value, 'invalid_source', maximum=LABEL_UTF8_BYTES_LIMIT)
            utf8_total += size
            json_values += 6*size+2
            if utf8_total>COORDINATE_LABEL_UTF8_BYTES_LIMIT:
                raise Refusal('coordinate_bytes_limit')
        elif info[3] is not None:
            exact_int(value,'invalid_source',minimum=info[3],maximum=info[4])
        elif type(value) is not float or not math.isfinite(value):
            raise Refusal('invalid_source')
        elif info[0] == 'float32':
            try: converted=struct.unpack('<f',struct.pack('<f',value))[0]
            except (OverflowError,struct.error): raise Refusal('invalid_source') from None
            if converted != value: raise Refusal('invalid_source')
        if width is None: json_values += 32
    canonical=_coordinate_json_bound(dtype,len(values),json_values)
    if canonical>COORDINATE_CANONICAL_BYTES_LIMIT:
        raise Refusal('coordinate_bytes_limit')
    for index in indices:
        exact_int(index,'invalid_source',maximum=len(values)-1)
    # Strictly increasing labels under the supplied permutation prove both
    # uniqueness and coverage without an additional sorted/permutation forest.
    for position in range(1,len(indices)):
        previous,current=indices[position-1],indices[position]
        if not values[previous] < values[current]: raise Refusal('invalid_source')
    return canonical,utf8_total


def _validate_array_child(child):
    if type(child) is not ArrayBuffer: raise Refusal('invalid_source')
    dtype,shape,data=child.dtype,child.shape,child.data
    info=_dtype_info(dtype)
    if dtype != info[0] or type(shape) is not tuple or type(data) is not bytes:
        raise Refusal('invalid_source')
    from ._resource_bounds import _shape_product
    count=_shape_product(shape)
    if count > SELECTED_NUMERIC_BYTES_LIMIT // info[2]:
        raise Refusal('selected_numeric_bytes_limit')
    if len(data) != count * info[2]: raise Refusal('invalid_source')


def _typed_map_validate(value, cls, *, children=True):
    if type(value) is not cls: raise Refusal('invalid_source')
    try: items=object.__getattribute__(value,'_items')
    except AttributeError: raise Refusal('invalid_source') from None
    if type(items) is not tuple or len(items)>cls._maximum:
        raise Refusal('invalid_source')
    previous=None
    for pair in items:
        if type(pair) is not tuple or len(pair)!=2: raise Refusal('invalid_source')
        name,child=pair
        validate_name(name)
        if type(child) is not cls._child: raise Refusal('invalid_source')
        if previous is not None and previous>=name: raise Refusal('invalid_source')
        previous=name
    if children:
        total_json=total_utf8=total_numeric=0
        try:
            for name,child in items:
                if cls is _CoordinateMap:
                    size,utf8=_validate_coordinate_child(child)
                    total_json+=size;total_utf8+=utf8
                    if (total_json>COORDINATE_CANONICAL_BYTES_LIMIT or
                            total_utf8>COORDINATE_LABEL_UTF8_BYTES_LIMIT):
                        raise Refusal('coordinate_bytes_limit')
                else:
                    _validate_array_child(child);total_numeric+=len(child.data)
                    if total_numeric>SELECTED_NUMERIC_BYTES_LIMIT:
                        raise Refusal('selected_numeric_bytes_limit')
        except AttributeError: raise Refusal('invalid_source') from None
    return value


def _source_primitive_map(value, maximum):
    from ._resource_inputs import _owned_map, _owned_cost
    if type(value) is dict:
        if len(value)>maximum: raise Refusal('invalid_source')
        for key in value: validate_name(key)
        # Only the top-level map is new; qualified immutable children are reused.
        items=[]
        for key in sorted(value):
            child=value[key]
            if type(child) is dict: child=freeze(child,code='invalid_source')
            elif type(child) is OwnedMap: _owned_cost(child)
            elif type(child) is not int: raise Refusal('invalid_source')
            items.append((key,child))
        value=OwnedMap._from_checked(tuple(items))
    _owned_map(value,maximum=maximum)
    return value


def _raw_source_cost(value, depth=0):
    """Fold caller primitives before freezing any descriptor child.

    OwnedMap contents are checked in place; this allocates only bounded walk
    frames/scalar cost records, never a normalized or owned descriptor prefix.
    """
    from ._resource_inputs import _owned_map
    from ._resource_bounds import _Fold, _literal_cost
    from .resources import JSON_DEPTH_LIMIT, LOGICAL_JOURNEY_LIMIT
    kind=type(value)
    if kind not in (dict,list,tuple,OwnedMap): return _literal_cost(value)
    if depth>=JSON_DEPTH_LIMIT: raise Refusal('invalid_source')
    if kind is OwnedMap: _owned_map(value)
    if len(value)>METADATA_SCALAR_LIMIT: raise Refusal('metadata_bytes_limit')
    fold=_Fold()
    if kind in (dict,OwnedMap):
        for key in value: utf8_length(key,'invalid_source')
        for key,child in value.items():
            fold.add(_raw_source_cost(child,depth+1),key)
            if fold.j>METADATA_BYTES_LIMIT: raise Refusal('metadata_bytes_limit')
            if fold.p>LOGICAL_JOURNEY_LIMIT: raise Refusal('estimated_memory_limit')
    else:
        for child in value:
            fold.add(_raw_source_cost(child,depth+1))
            if fold.j>METADATA_BYTES_LIMIT: raise Refusal('metadata_bytes_limit')
            if fold.p>LOGICAL_JOURNEY_LIMIT: raise Refusal('estimated_memory_limit')
    result=fold.finish()
    if result.json_bytes+1>METADATA_BYTES_LIMIT: raise Refusal('metadata_bytes_limit')
    if result.object_bytes>LOGICAL_JOURNEY_LIMIT: raise Refusal('estimated_memory_limit')
    return result


def _source_identity_check(identity):
    if type(identity) is not SourceIdentity: raise Refusal('invalid_source')
    try: kind,digest,size=identity.kind,identity.sha256,identity.size_bytes
    except AttributeError: raise Refusal('invalid_source') from None
    if type(kind) is not str or kind not in ('memory','file'):
        raise Refusal('invalid_source')
    if type(digest) is not str or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise Refusal('invalid_source')
    exact_int(size,'invalid_source')


@dataclass(frozen=True, slots=True, init=False)
class SourceSnapshot:
    """Owned inspection with exact selected children, never source authority.

    The backing handle is private and is independently qualified by consuming
    boundaries. Structural construction performs no storage or runtime reads.
    """
    identity: SourceIdentity
    dimensions: OwnedMap
    variables: OwnedMap
    coordinate_descriptors: OwnedMap
    attributes: MetadataValue
    arrays: _ArrayMap
    coordinates: _CoordinateMap
    _handle: object

    def __init_subclass__(cls,**kwargs): raise TypeError('SourceSnapshot is final')

    def __init__(self, *, identity, dimensions, variables, coordinate_descriptors,
                 attributes, arrays, coordinates, _handle):
        _require_uninitialized(self,'identity','invalid_source')
        _source_identity_check(identity)
        if type(attributes) is not MetadataValue: raise Refusal('invalid_source')
        from ._resource_inputs import (_owned_map,_metadata_fields,
                                      _validate_metadata,_DESCRIPTOR_FIELDS)
        from ._resource_bounds import _Fold
        for value,maximum in ((dimensions,16),(variables,64),(coordinate_descriptors,16)):
            if type(value) is OwnedMap: _owned_map(value,maximum=maximum)
            elif type(value) is not dict or len(value)>maximum: raise Refusal('invalid_source')
        try:
            metadata_state=_Fold()
            _validate_metadata(attributes._tagged,metadata_state,raw=True)
            for descriptors in (variables,coordinate_descriptors):
                for name,desc in descriptors.items():
                    validate_name(name)
                    _metadata_fields(desc,_DESCRIPTOR_FIELDS,raw=True)
                    _validate_metadata(desc['attributes'],metadata_state,raw=True)
                    _validate_metadata(desc['encoding'],metadata_state,raw=True)
            _raw_source_cost({'version':2,'source':identity._projection(),'dimensions':dimensions,
                'variables':variables,'coordinate_descriptors':coordinate_descriptors,'attributes':attributes._tagged})
        except AttributeError: raise Refusal('invalid_source') from None
        dimensions=_source_primitive_map(dimensions,16)
        variables=_source_primitive_map(variables,64)
        coordinate_descriptors=_source_primitive_map(coordinate_descriptors,16)
        if type(arrays) is not _ArrayMap: arrays=_ArrayMap(arrays)
        if type(coordinates) is not _CoordinateMap: coordinates=_CoordinateMap(coordinates)
        _validate_source_parts(identity,dimensions,variables,coordinate_descriptors,attributes,arrays,coordinates)
        for name,value in (('identity',identity),('dimensions',dimensions),('variables',variables),
                ('coordinate_descriptors',coordinate_descriptors),('attributes',attributes),
                ('arrays',arrays),('coordinates',coordinates),('_handle',_handle)):
            object.__setattr__(self,name,value)

    def _projection(self):
        return OwnedMap._from_checked((('attributes',self.attributes._tagged),
            ('coordinate_descriptors',self.coordinate_descriptors),('dimensions',self.dimensions),
            ('source',OwnedMap(self.identity._projection())),('variables',self.variables),('version',2)))

    def iter_json_chunks(self):
        return iter_json_chunks(self._projection(),limit=METADATA_BYTES_LIMIT)

    def to_json(self):
        return canonical_bytes(self._projection(),limit=METADATA_BYTES_LIMIT)


def _validate_source_parts(identity,dimensions,variables,coordinate_descriptors,attributes,arrays,coordinates):
    from ._resource_inputs import _inspection_cost
    _source_identity_check(identity)
    if type(attributes) is not MetadataValue: raise Refusal('invalid_source')
    _typed_map_validate(arrays,_ArrayMap)
    _typed_map_validate(coordinates,_CoordinateMap)
    try:
        inspection=OwnedMap._from_checked((('attributes',attributes._tagged),
            ('coordinate_descriptors',coordinate_descriptors),('dimensions',dimensions),
            ('source',OwnedMap(identity._projection())),('variables',variables),('version',2)))
        _inspection_cost(inspection)
        for name,desc in variables._items:
            if name in coordinate_descriptors or numeric_dtype(desc['dtype']) != desc['dtype']:
                raise Refusal('invalid_source')
        for name,desc in coordinate_descriptors._items:
            raw=desc['dtype']
            if raw != '|O' and _unicode_width(raw) is None:
                if raw.startswith('|S'):
                    digits=raw[2:]
                    if (not digits or len(digits)>4 or not digits.isascii() or
                            not digits.isdecimal() or digits[0]=='0' or int(digits)>4096):
                        raise Refusal('invalid_source')
                else: _dtype_info(raw,'invalid_source',coordinate=True)
        for name,child in arrays.items():
            _validate_array_child(child)
            if name not in variables: raise Refusal('invalid_source')
            desc=variables[name]
            if child.dtype!=desc['dtype'] or child.shape!=desc['shape']: raise Refusal('invalid_source')
        for name,child in coordinates.items():
            _validate_coordinate_child(child)
            if name not in coordinate_descriptors: raise Refusal('invalid_source')
            desc=coordinate_descriptors[name]; raw=desc['dtype']
            if len(child.values)!=dimensions[name]: raise Refusal('invalid_source')
            if raw=='|O':
                valid=(_unicode_width(child.dtype) is not None and
                       child.dtype=='<U'+str(max(1,max(len(label) for label in child.values))))
            elif raw.startswith('|S'): valid=child.dtype=='<U'+raw[2:]
            else: valid=child.dtype==raw
            if not valid: raise Refusal('invalid_source')
    except AttributeError:
        raise Refusal('invalid_source') from None


@dataclass(frozen=True, slots=True, init=False, eq=False)
class BoundPlan:
    """Immutable plan2 data with selected-only backing, never source authority.

    Structural construction performs no native/source reads or stock unit
    qualification. Every consuming public boundary rederives the estimates,
    measures the actual anchor and checks the applicable semantic bindings.
    """
    version: int
    formula_version: int
    source: SourceIdentity
    recipe: Recipe
    runtime: OwnedMap
    coordinates: _CoordinateMap
    selected: OwnedMap
    columns: tuple
    resource_binding: OwnedMap
    estimates: OwnedMap
    _source: SourceSnapshot

    def __init_subclass__(cls, **kwargs):
        raise TypeError('BoundPlan is final')

    def __init__(self, *, version, formula_version, source, recipe, runtime,
                 coordinates, selected, columns, resource_binding, estimates,
                 _source):
        _require_uninitialized(self, 'version', 'invalid_plan')
        from .plan import _check_plan_parts
        from .runtime import validate_runtime
        _check_plan_parts(version, formula_version, source, recipe, runtime,
                          coordinates, selected, columns, resource_binding,
                          estimates, _source)
        owned_runtime = validate_runtime(runtime)
        owned_selected = freeze(selected, code='invalid_plan')
        owned_columns = freeze(columns, code='invalid_plan')
        owned_binding = freeze(resource_binding, code='invalid_plan')
        owned_estimates = freeze(estimates, code='invalid_plan')
        for name, value in (('version', version), ('formula_version', formula_version),
                ('source', source), ('recipe', recipe), ('runtime', owned_runtime),
                ('coordinates', coordinates), ('selected', owned_selected),
                ('columns', owned_columns), ('resource_binding', owned_binding),
                ('estimates', owned_estimates), ('_source', _source)):
            object.__setattr__(self, name, value)

    def _projection(self):
        from .plan import _plan_projection
        return _plan_projection(self)

    def to_dict(self):
        from .plan import _serialize_plan
        return _serialize_plan(self, 'dict')

    def to_json(self):
        from .plan import _serialize_plan
        return _serialize_plan(self, 'bytes')

    def iter_json_chunks(self):
        # Admission and validation finish before constructing this iterator.
        # Its held plan is the same immutable object already included in Z.
        from .plan import _serialize_plan
        return _serialize_plan(self, 'chunks')
