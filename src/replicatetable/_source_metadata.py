"""Private finite raw-metadata bridge for the eager memory source boundary.

Pass one retains scalar counts only. The source scanner must visit *all* source
owners and metadata slots before finishing this barrier. Pass two constructs
one final immutable tagged forest; it grants no source or selection authority.
"""
import math
import re

from . import resources as r
from .codec import OwnedMap
from .errors import Refusal
from .model import MetadataValue, validate_unit
from ._resource_bounds import _JP, _Fold, _count, _literal_cost, _container_cost
from ._resource_inputs import _validate_metadata, _owned_cost
from ._source_stock import _array_owner


_CONTEXTS = ('root', 'data_attrs', 'data_encoding',
             'coordinate_attrs', 'coordinate_encoding')
_TOTALS = ('raw_bytes', 'json_bytes', 'object_bytes',
           'scalar_count', 'container_count')
_BUILT = ('_built_raw', '_built_json', '_built_objects',
          '_built_scalars', '_built_containers')
_LIMITS = ('_raw_limit', '_json_limit', '_object_limit',
           '_scalar_limit', '_container_limit')


class _MetadataState:
    """Call-local scalar ledger, never a retained raw value or capability."""
    __slots__ = ('base_bytes', 'raw_bytes', 'json_bytes', 'object_bytes',
                 'scalar_count', 'container_count', 'sealed', '_failed',
                 '_descriptor_json', '_descriptor_objects',
                 '_built_raw', '_built_json', '_built_objects',
                 '_built_scalars', '_built_containers',
                 '_raw_limit', '_json_limit', '_object_limit',
                 '_scalar_limit', '_container_limit')

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Metadata state is final')

    def __init__(self, *, base_bytes=0):
        try:
            object.__getattribute__(self, 'base_bytes')
        except AttributeError:
            pass
        else:
            raise Refusal('invalid_source')
        _count(base_bytes)
        _count(base_bytes, 'source_bytes_limit', limit=r.SOURCE_MEMORY_BASE_LIMIT)
        self.base_bytes = base_bytes
        for name in _TOTALS + _BUILT:
            setattr(self, name, 0)
        for name in _LIMITS:
            setattr(self, name, None)
        self.sealed = False
        self._failed = False
        self._descriptor_json = 0
        self._descriptor_objects = 0


def _state_exact(state):
    if type(state) is not _MetadataState:
        raise Refusal('invalid_source')
    try:
        for name in ('base_bytes', '_descriptor_json', '_descriptor_objects') + _TOTALS + _BUILT:
            _count(object.__getattribute__(state, name))
        for name in _LIMITS:
            value = object.__getattribute__(state, name)
            if value is not None:
                _count(value)
        if type(state.sealed) is not bool or type(state._failed) is not bool:
            raise Refusal('invalid_source')
    except AttributeError:
        raise Refusal('invalid_source') from None
    if state._failed:
        raise Refusal('invalid_source')
    _count(state.base_bytes, 'source_bytes_limit', limit=r.SOURCE_MEMORY_BASE_LIMIT)


def _context_exact(context):
    if type(context) is not str or context not in _CONTEXTS:
        raise Refusal('invalid_source')


def _charge(state, *, raw=0, j=0, p=0):
    """Preserve scientific owners and every earlier metadata increment."""
    raw_total = state.raw_bytes + raw
    json_total = state.json_bytes + j
    object_total = state.object_bytes + p
    if state.base_bytes + raw_total + object_total > r.SOURCE_MEMORY_BASE_LIMIT:
        raise Refusal('source_bytes_limit')
    if json_total + 1 > r.METADATA_BYTES_LIMIT:
        raise Refusal('metadata_bytes_limit')
    # The builder's second measurement bounds its allocations as well. These
    # optional scalar ceilings never certify a value that was not inspected.
    if ((state._raw_limit is not None and raw_total > state._raw_limit) or
            (state._json_limit is not None and json_total > state._json_limit) or
            (state._object_limit is not None and object_total > state._object_limit)):
        raise Refusal('invalid_source')
    state.raw_bytes = raw_total
    state.json_bytes = json_total
    state.object_bytes = object_total


def _scalar(state):
    count = state.scalar_count + 1
    if count > r.METADATA_SCALAR_LIMIT:
        raise Refusal('metadata_bytes_limit')
    if state._scalar_limit is not None and count > state._scalar_limit:
        raise Refusal('invalid_source')
    state.scalar_count = count


def _container(state, depth):
    count = state.container_count + 1
    if depth >= r.METADATA_DEPTH_LIMIT or count > r.METADATA_CONTAINER_LIMIT:
        raise Refusal('metadata_bytes_limit')
    if state._container_limit is not None and count > state._container_limit:
        raise Refusal('invalid_source')
    state.container_count = count


def _tag_cost(tag, value=None):
    """Exact symbolic outer tag cost; value is a scalar-only J/P pair."""
    fold = _Fold()
    fold.add(_literal_cost(tag), 'type')
    if value is not None:
        fold.add(value, 'items' if tag in ('map', 'list') else 'value')
    return fold.finish()


def _tag_prefix(state, tag, count):
    # The items tuple's child charges follow incrementally. A map's pair
    # tuples and keys are charged separately before visiting their values.
    pair = _tag_cost(tag, _container_cost(count, 0, 0))
    _charge(state, j=pair.json_bytes, p=pair.object_bytes)


def _owned_tag(tag, value=None):
    if tag == 'null':
        return OwnedMap._from_checked((('type', 'null'),))
    if tag in ('map', 'list'):
        return OwnedMap._from_checked((('items', value), ('type', tag)))
    return OwnedMap._from_checked((('type', tag), ('value', value)))


def _text_mode(context, key):
    if context == 'root':
        return 0
    coordinate = context in ('coordinate_attrs', 'coordinate_encoding')
    if key == 'units':
        return 2 if coordinate else 1
    if coordinate and key == 'calendar':
        return 3
    return 0


def _text_length(value, mode):
    # Also used for exact np.str_. Never request its dtype, buffer, item,
    # NumPy string representation or optional storage to discover its size.
    length = str.__len__(value)
    maximum = r.UNIT_BYTES_LIMIT if mode else r.LABEL_UTF8_BYTES_LIMIT
    if length > maximum or (mode in (1, 2) and length == 0):
        raise Refusal('invalid_source')
    return length


def _codepoint_width(codepoint, mode):
    if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
        raise Refusal('invalid_source')
    if mode in (1, 2) and ((codepoint < 32 and not (mode == 2 and codepoint == 9))
                          or 127 <= codepoint <= 159):
        raise Refusal('invalid_source')
    return (1 if codepoint < 128 else 2 if codepoint < 2048
            else 3 if codepoint < 65536 else 4)


def _match_scalar(tag, value, expected):
    # expected has already passed the complete owned-tag validator. Comparing
    # its tag first keeps exact int/float/bool and special-float types distinct.
    if expected['type'] != tag:
        raise Refusal('source_changed')
    if tag == 'null':
        return
    old = expected['value']
    if value != old:
        raise Refusal('source_changed')
    if tag == 'float' and value == 0.0 and math.copysign(1.0, value) != math.copysign(1.0, old):
        raise Refusal('source_changed')


def _match_text(value, expected):
    if expected['type'] != 'str':
        raise Refusal('source_changed')
    old = expected['value']
    length = str.__len__(value)
    if length != str.__len__(old):
        raise Refusal('source_changed')
    # Exact base methods work for both admitted str and np.str_, without
    # invoking NumPy equality or allocating a normalized string for matching.
    for position in range(length):
        if str.__getitem__(value, position) != str.__getitem__(old, position):
            raise Refusal('source_changed')


def _match_items(expected, tag, count):
    if expected['type'] != tag or len(expected['items']) != count:
        raise Refusal('source_changed')
    return expected['items']


def _text(state, value, mode, *, numpy_string=False, key=False, build=False, expected=None):
    length = _text_length(value, mode)
    if numpy_string:
        reserve = (max(512, str.__sizeof__(value) + object.__sizeof__(value) + 16)
                   + 128 + 4 * (length + 1))
        _charge(state, raw=reserve)
    else:
        _charge(state, raw=128)
    if key:
        _charge(state, j=2, p=128)
    else:
        pair = _tag_cost('str', _JP(2, 128))
        _charge(state, j=pair.json_bytes, p=pair.object_bytes)
    total = 0
    maximum = r.UNIT_BYTES_LIMIT if mode else r.LABEL_UTF8_BYTES_LIMIT
    for position in range(length):
        char = str.__getitem__(value, position)
        width = _codepoint_width(ord(char), mode)
        total += width
        if total > maximum:
            raise Refusal('invalid_source')
        _charge(state, raw=0 if numpy_string else 4 * width, j=6 * width, p=4 * width)
    if expected is not None:
        _match_text(value, expected)
        return None
    if not build:
        return None
    normalized = str.__str__(value) if numpy_string else value
    if type(normalized) is not str or str.__len__(normalized) != length:
        raise Refusal('invalid_source')
    # The prescribed base conversion preserves every codepoint, including
    # trailing NUL. Check content without producing another string copy.
    if numpy_string:
        for position in range(length):
            if str.__getitem__(normalized, position) != str.__getitem__(value, position):
                raise Refusal('invalid_source')
    return normalized if key else _owned_tag('str', normalized)


def _number(state, value, *, retained=True, build=False, expected=None):
    """One exact primitive, or one exact admitted NumPy scalar, at a time."""
    import numpy as np
    kind = type(value)
    if retained:
        _charge(state, raw=128)
    if kind is np.bool_:
        value = np.bool_.__bool__(value)
    elif kind in (np.int8, np.int16, np.int32, np.int64,
                  np.uint8, np.uint16, np.uint32, np.uint64):
        value = kind.__int__(value)
    elif kind in (np.float32, np.float64):
        value = kind.__float__(value)
    kind = type(value)
    if value is None:
        tag = 'null'
        pair = _tag_cost(tag)
    elif kind is bool:
        tag = 'bool'
        pair = _tag_cost(tag, _literal_cost(value))
    elif kind is int:
        tag = 'int'
        pair = _tag_cost(tag, _literal_cost(value))
    elif kind is float:
        if math.isfinite(value):
            tag = 'float'
        else:
            tag = 'float_special'
            value = 'nan' if math.isnan(value) else '+inf' if value > 0 else '-inf'
        pair = _tag_cost(tag, _literal_cost(value))
    else:
        raise Refusal('unsupported_source_storage')
    _charge(state, j=pair.json_bytes, p=pair.object_bytes)
    if expected is not None:
        _match_scalar(tag, value, expected)
        return None
    return _owned_tag(tag, value) if build else None


def _utf32(octets, position):
    return (octets[position] | octets[position + 1] << 8
            | octets[position + 2] << 16 | octets[position + 3] << 24)


def _unicode_scalar(state, octets, start, itemsize, *, build, expected=None):
    """Scan padded UTF32 without extracting a NumPy Unicode scalar."""
    end = start + itemsize
    while end > start and _utf32(octets, end - 4) == 0:
        end -= 4
    if (end - start) // 4 > r.LABEL_UTF8_BYTES_LIMIT:
        raise Refusal('invalid_source')
    _scalar(state)
    pair = _tag_cost('str', _JP(2, 128))
    _charge(state, j=pair.json_bytes, p=pair.object_bytes)
    total = 0
    for position in range(start, end, 4):
        width = _codepoint_width(_utf32(octets, position), 0)
        total += width
        if total > r.LABEL_UTF8_BYTES_LIMIT:
            raise Refusal('invalid_source')
        _charge(state, j=6 * width, p=4 * width)
    if expected is not None:
        if expected['type'] != 'str':
            raise Refusal('source_changed')
        old = expected['value']
        if str.__len__(old) != (end - start) // 4:
            raise Refusal('source_changed')
        for index, position in enumerate(range(start, end, 4)):
            codepoint = _utf32(octets, position)
            _codepoint_width(codepoint, 0)
            if codepoint != ord(str.__getitem__(old, index)):
                raise Refusal('source_changed')
        return None
    if not build:
        return None
    # The exact byte size, all codepoints, and every tagged P increment are
    # qualified before this allocation. No character list or padded scalar.
    buffer = bytearray(total)
    cursor = 0
    for position in range(start, end, 4):
        codepoint = _utf32(octets, position)
        width = _codepoint_width(codepoint, 0)
        if cursor + width > total:
            raise Refusal('invalid_source')
        if width == 1:
            buffer[cursor] = codepoint
        elif width == 2:
            buffer[cursor] = 0xC0 | (codepoint >> 6)
            buffer[cursor + 1] = 0x80 | (codepoint & 0x3F)
        elif width == 3:
            buffer[cursor] = 0xE0 | (codepoint >> 12)
            buffer[cursor + 1] = 0x80 | ((codepoint >> 6) & 0x3F)
            buffer[cursor + 2] = 0x80 | (codepoint & 0x3F)
        else:
            buffer[cursor] = 0xF0 | (codepoint >> 18)
            buffer[cursor + 1] = 0x80 | ((codepoint >> 12) & 0x3F)
            buffer[cursor + 2] = 0x80 | ((codepoint >> 6) & 0x3F)
            buffer[cursor + 3] = 0x80 | (codepoint & 0x3F)
        cursor += width
    if cursor != total:
        raise Refusal('invalid_source')
    normalized = buffer.decode('utf-8')
    del buffer
    return _owned_tag('str', normalized)


def _empty_unicode_scalar(state, *, build, expected=None):
    _scalar(state)
    pair = _tag_cost('str', _JP(2, 128))
    _charge(state, j=pair.json_bytes, p=pair.object_bytes)
    if expected is not None:
        _match_scalar('str', '', expected)
        return None
    return _owned_tag('str', '') if build else None


def _vector_scalar(state, array, position, *, build, expected=None):
    # _array_owner already established an exact native approved numeric/bool
    # vector and charged all backing. Only this single scalar is extracted.
    import numpy as np
    value = np.ndarray.__getitem__(array, position)
    if type(value) not in (np.bool_, np.int8, np.int16, np.int32, np.int64,
                           np.uint8, np.uint16, np.uint32, np.uint64,
                           np.float32, np.float64):
        raise Refusal('unsupported_source_storage')
    _scalar(state)
    return _number(state, value, retained=False, build=build, expected=expected)


def _vector(state, array, depth, *, build, expected=None):
    owner = _array_owner(array, metadata=True)
    _charge(state, raw=owner.terminal_bytes + owner.header_bytes)
    del owner
    _container(state, depth)
    count = array.size
    _tag_prefix(state, 'list', count)
    old_items = None if expected is None else _match_items(expected, 'list', count)
    if array.dtype.kind != 'U':
        if build:
            items = tuple(_vector_scalar(state, array, index, build=True)
                          for index in range(count))
            return _owned_tag('list', items)
        for index in range(count):
            _vector_scalar(state, array, index, build=False,
                           expected=None if old_items is None else old_items[index])
        return None
    itemsize = array.dtype.itemsize
    if type(itemsize) is not int or itemsize < 0 or itemsize % 4:
        raise Refusal('unsupported_source_storage')
    # Empty and U0 arrays must not acquire an unusable zero-sized byte view.
    if not count or not itemsize:
        if build:
            items = tuple(_empty_unicode_scalar(state, build=True) for _ in range(count))
            return _owned_tag('list', items)
        for index in range(count):
            _empty_unicode_scalar(state, build=False,
                                  expected=None if old_items is None else old_items[index])
        return None
    view = memoryview(array)
    octets = None
    try:
        octets = view.cast('B')
        if len(octets) != count * itemsize:
            raise Refusal('unsupported_source_storage')
        if build:
            items = tuple(_unicode_scalar(state, octets, index * itemsize,
                                          itemsize, build=True) for index in range(count))
            return _owned_tag('list', items)
        for index in range(count):
            _unicode_scalar(state, octets, index * itemsize, itemsize, build=False,
                            expected=None if old_items is None else old_items[index])
        return None
    finally:
        if octets is not None:
            octets.release()
        view.release()


def _map_item(state, value, key, depth, context, *, build, expected=None):
    # Recheck exact keys even after the separate complete-slot prepass; never
    # compare or look up a caller-supplied key subclass.
    if type(key) is not str:
        raise Refusal('invalid_source')
    _scalar(state)
    _charge(state, j=3, p=768)  # the final two-member (key, tag) tuple
    _text(state, key, 0, key=True, build=False)
    mode = _text_mode(context, key) if depth == 0 else 0
    child = _walk(state, value[key], depth + 1, mode=mode, build=build, expected=expected)
    return (key, child) if build else None


def _map(state, value, depth, context, *, build, empty_slot=False, expected=None):
    count = 0 if empty_slot else len(value)
    if count > r.METADATA_MAP_LIMIT:
        raise Refusal('metadata_bytes_limit')
    raw = 128 if empty_slot else max(512 + 128 * count, dict.__sizeof__(value) + 16)
    _charge(state, raw=raw)
    _container(state, depth)
    _tag_prefix(state, 'map', count)
    old_items = None if expected is None else _match_items(expected, 'map', count)
    if empty_slot:
        return _owned_tag('map', ()) if build else None
    # Validate *all* key classes before the bounded sort in the build pass.
    for key in value:
        if type(key) is not str:
            raise Refusal('invalid_source')
    if old_items is not None:
        for index, key in enumerate(sorted(value)):
            old_key, old_child = old_items[index]
            if key != old_key:
                raise Refusal('source_changed')
            _map_item(state, value, key, depth, context, build=False, expected=old_child)
        return None
    if build:
        items = tuple(_map_item(state, value, key, depth, context, build=True)
                      for key in sorted(value))
        return _owned_tag('map', items)
    for key in value:
        _map_item(state, value, key, depth, context, build=False)
    return None


def _sequence(state, value, depth, *, build, expected=None):
    count = len(value)
    if count > r.METADATA_SEQUENCE_LIMIT:
        raise Refusal('metadata_bytes_limit')
    _charge(state, raw=max(512 + 128 * count, type(value).__sizeof__(value) + 16))
    _container(state, depth)
    _tag_prefix(state, 'list', count)
    old_items = None if expected is None else _match_items(expected, 'list', count)
    if build:
        items = tuple(_walk(state, child, depth + 1, build=True) for child in value)
        return _owned_tag('list', items)
    for index, child in enumerate(value):
        _walk(state, child, depth + 1, build=False,
              expected=None if old_items is None else old_items[index])
    return None


def _walk(state, value, depth, *, mode=0, build=False, expected=None):
    import numpy as np
    kind = type(value)
    if kind not in (dict, list, tuple, np.ndarray, str, np.str_, type(None),
                    bool, int, float, np.bool_, np.int8, np.int16, np.int32, np.int64,
                    np.uint8, np.uint16, np.uint32, np.uint64, np.float32, np.float64):
        raise Refusal('unsupported_source_storage')
    if (build or expected is not None) and mode in (1, 2) and value is not None and kind not in (str, np.str_):
        raise Refusal('invalid_source')
    if kind is dict:
        result = _map(state, value, depth, 'root', build=build, expected=expected)
    elif kind in (list, tuple):
        result = _sequence(state, value, depth, build=build, expected=expected)
    elif kind is np.ndarray:
        result = _vector(state, value, depth, build=build, expected=expected)
    else:
        _scalar(state)
        if kind in (str, np.str_):
            return _text(state, value, mode, numpy_string=kind is np.str_,
                         build=build, expected=expected)
        result = _number(state, value, build=build, expected=expected)
    if mode in (1, 2) and value is not None:
        raise Refusal('invalid_source')
    return result


def _slot(state, raw_slot, context, *, build, expected=None):
    if raw_slot is not None and type(raw_slot) is not dict:
        raise Refusal('unsupported_source_storage')
    return _map(state, raw_slot, 0, context, build=build,
                empty_slot=raw_slot is None, expected=expected)


def _scan_metadata(state, raw_slot, *, context='root'):
    """Fold a raw slot without constructing strings, tags or child records."""
    _state_exact(state)
    if state.sealed:
        raise Refusal('invalid_source')
    try:
        _context_exact(context)
        before_j, before_p = state.json_bytes, state.object_bytes
        _slot(state, raw_slot, context, build=False)
        return _JP(state.json_bytes - before_j, state.object_bytes - before_p)
    except BaseException:
        state._failed = True
        raise


def _finish_metadata(state, *, descriptor_cost):
    """Seal after actual full-source observation and full descriptor projection.

    This arithmetic barrier is not evidence that its caller inspected every
    source slot. Only the owning source scanner can establish that schedule.
    """
    _state_exact(state)
    if state.sealed:
        raise Refusal('invalid_source')
    try:
        if type(descriptor_cost) is not _JP:
            raise Refusal('invalid_source')
        _count(descriptor_cost.json_bytes)
        _count(descriptor_cost.object_bytes)
        if (descriptor_cost.json_bytes < state.json_bytes or
                descriptor_cost.object_bytes < state.object_bytes):
            raise Refusal('invalid_source')
        if state.base_bytes + state.raw_bytes + descriptor_cost.object_bytes > r.SOURCE_MEMORY_BASE_LIMIT:
            raise Refusal('source_bytes_limit')
        if descriptor_cost.json_bytes + 1 > r.METADATA_BYTES_LIMIT:
            raise Refusal('metadata_bytes_limit')
        _count(state.scalar_count, 'metadata_bytes_limit', limit=r.METADATA_SCALAR_LIMIT)
        _count(state.container_count, 'metadata_bytes_limit', limit=r.METADATA_CONTAINER_LIMIT)
        state._descriptor_json = descriptor_cost.json_bytes
        state._descriptor_objects = descriptor_cost.object_bytes
        state.sealed = True
    except BaseException:
        state._failed = True
        raise


def _build_metadata(state, raw_slot, *, context='root'):
    """Adopt exactly one final tree after global and repeated local admission."""
    _state_exact(state)
    if not state.sealed:
        raise Refusal('invalid_source')
    try:
        _context_exact(context)
        # A late mutation in this slot fails before even its first tag. No
        # raw tree, normalized vector or per-entry facts survive this scan.
        measured = _MetadataState(base_bytes=state.base_bytes)
        _scan_metadata(measured, raw_slot, context=context)
        for total, built in zip(_TOTALS, _BUILT):
            if getattr(state, built) + getattr(measured, total) > getattr(state, total):
                raise Refusal('invalid_source')
        # Reserve every other raw/tag/descriptor term while constructing the
        # current slot. Each local increment is then checked against both the
        # full source subtotal and the just-measured slot's scalar ceilings.
        residue = (state.base_bytes + state.raw_bytes + state._descriptor_objects
                   - measured.raw_bytes - measured.object_bytes)
        building = _MetadataState(base_bytes=residue)
        for total, limit in zip(_TOTALS, _LIMITS):
            setattr(building, limit, getattr(measured, total))
        tagged = _slot(building, raw_slot, context, build=True)
        for total in _TOTALS:
            if getattr(building, total) != getattr(measured, total):
                raise Refusal('invalid_source')
        result = MetadataValue._from_owned_tagged(tagged)
        for total, built in zip(_TOTALS, _BUILT):
            setattr(state, built, getattr(state, built) + getattr(measured, total))
        return result
    except BaseException:
        state._failed = True
        raise


_REFERENCE_TIME = re.compile(
    r'\A[ \t]*[^ \t\r\n](?:[^\r\n]*?[^ \t\r\n])?'
    r'(?:[ \t]+(?i:since|after|from|ref)[ \t]+|[ \t]*@[ \t]*)'
    r'[+-]?[0-9]+-[0-9]+-[0-9]+'
    r'(?:(?:[ \t]+|T)[0-9]+:[0-9]+'
    r'(?::[0-9]+(?:\.[0-9]+)?)?'
    r'(?:[ \t]*(?:Z|[+-][0-9]{1,2}(?::?[0-9]{2})?))?)?[ \t]*\Z',
    re.ASCII)
_RAW_NUMERIC = ('|i1', '<i2', '<i4', '<i8', '|u1', '<u2', '<u4', '<u8', '<f4', '<f8')
_REASONS = ('calendar_metadata', 'reference_time_units', 'scale_factor_metadata',
            'add_offset_metadata', 'unsigned_metadata', 'fill_value_metadata',
            'missing_value_metadata')


def _declaration_dtype(dtype, coordinate):
    if type(dtype) is not str or type(coordinate) is not bool:
        raise Refusal('invalid_source')
    if dtype in _RAW_NUMERIC:
        return
    if coordinate:
        if dtype == '|O':
            return
        if (len(dtype) <= 6 and re.fullmatch(r'(?:<U|\|S)[1-9][0-9]*', dtype, re.ASCII)
                and int(dtype[2:]) <= 4096):
            return
    raise Refusal('invalid_source')


def _declaration_member(tag, name):
    for key, child in tag['items']:
        if key == name:
            return child
    return None


def _declaration_unit(tag, coordinate):
    child = _declaration_member(tag, 'units')
    if child is None or child['type'] == 'null':
        return None
    if child['type'] != 'str':
        raise Refusal('invalid_source')
    return validate_unit(child['value'], raw_coordinate=coordinate)


def _declaration_status(attributes_tag, encoding_tag, *, dtype, coordinate):
    """Recompute the finite v8 reasons from both owned declarations in place.

    The source scanner reserves the complete role-valid status projection
    before invoking this producer. This record is derived information only;
    it neither replaces raw declarations nor authorizes selected payload use.
    """
    _declaration_dtype(dtype, coordinate)
    if type(attributes_tag) is not OwnedMap or type(encoding_tag) is not OwnedMap:
        raise Refusal('invalid_source')
    counters = _Fold()
    total_j = 0
    # Validate complete tags and exact scalar types before any declaration
    # comparison. Do not untag, make a mutable dict, or reconstruct a model.
    for tag in (attributes_tag, encoding_tag):
        _validate_metadata(tag, counters)
        if tag['type'] != 'map':
            raise Refusal('invalid_source')
        total_j += _owned_cost(tag).json_bytes
        if total_j + 1 > r.METADATA_BYTES_LIMIT:
            raise Refusal('metadata_bytes_limit')
    bits = 0
    for tag in (attributes_tag, encoding_tag):
        units = _declaration_unit(tag, coordinate)
        if coordinate:
            calendar = _declaration_member(tag, 'calendar')
            if calendar is not None:
                if calendar['type'] == 'str':
                    from ._resource_bounds import _utf8
                    _utf8(calendar['value'], maximum=r.UNIT_BYTES_LIMIT)
                bits |= 1
            if units is not None and _REFERENCE_TIME.fullmatch(units) is not None:
                bits |= 2
        for key, bit in (('scale_factor', 4), ('add_offset', 8), ('_Unsigned', 16)):
            if _declaration_member(tag, key) is not None:
                bits |= bit
        for key, bit in (('_FillValue', 32), ('missing_value', 64)):
            child = _declaration_member(tag, key)
            if child is not None and not (
                    dtype in ('<f4', '<f8') and child['type'] == 'float_special'
                    and child['value'] == 'nan'):
                bits |= bit
    if not bits:
        return None
    reasons = tuple(reason for index, reason in enumerate(_REASONS) if bits & (1 << index))
    code = 'unsupported_coordinate_encoding' if coordinate else 'unsupported_source_encoding'
    return OwnedMap._from_checked((('code', code), ('reasons', reasons), ('status', 'unsupported')))


def _compare_metadata(state, raw_slot, expected_tag, *, context='root'):
    """Compare a qualified raw slot with an existing tree, retaining no copy.

    Like build, each successful call consumes one slot's scalar reservation.
    The caller may then reuse the immutable expected children by identity.
    Equal content is not evidence of source observation outside this slot.
    """
    _state_exact(state)
    if not state.sealed:
        raise Refusal('invalid_source')
    try:
        _context_exact(context)
        # Neither a malformed late raw value nor a malformed late expected
        # tag can be hidden by an earlier content mismatch.
        measured = _MetadataState(base_bytes=state.base_bytes)
        _scan_metadata(measured, raw_slot, context=context)
        for total, built in zip(_TOTALS, _BUILT):
            if getattr(state, built) + getattr(measured, total) > getattr(state, total):
                raise Refusal('invalid_source')
        if type(expected_tag) is not OwnedMap:
            raise Refusal('invalid_source')
        _validate_metadata(expected_tag, _Fold())
        if _owned_cost(expected_tag).json_bytes + 1 > r.METADATA_BYTES_LIMIT:
            raise Refusal('metadata_bytes_limit')
        residue = (state.base_bytes + state.raw_bytes + state._descriptor_objects
                   - measured.raw_bytes - measured.object_bytes)
        comparing = _MetadataState(base_bytes=residue)
        for total, limit in zip(_TOTALS, _LIMITS):
            setattr(comparing, limit, getattr(measured, total))
        _slot(comparing, raw_slot, context, build=False, expected=expected_tag)
        for total in _TOTALS:
            if getattr(comparing, total) != getattr(measured, total):
                raise Refusal('invalid_source')
        for total, built in zip(_TOTALS, _BUILT):
            setattr(state, built, getattr(state, built) + getattr(measured, total))
        return None
    except BaseException:
        state._failed = True
        raise
