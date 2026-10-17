"""Strict, bounded stdlib-only JSON and immutable primitive ownership.

The lexical pass retains at most 32 container frames, active object-key sets,
and one bounded key token. It never retains a value forest. Its counters are
available to transport admission before strict_loads creates decoded objects.
No MappingProxyType or user-defined mapping is a trusted primitive container.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import json
import math

from .errors import Refusal, ComputationError
from .resources import (BUNDLE_BYTES_LIMIT, COUNT_MAX, JSON_DEPTH_LIMIT,
    JSON_INTEGER_MAX, JSON_INTEGER_MIN, JSON_NUMERIC_TOKEN_LIMIT,
    LOGICAL_JOURNEY_LIMIT, METADATA_BYTES_LIMIT, RUNTIME_ALLOWANCE,
    CONTROL_STATE_BYTES)


DEFAULT_PARSE_BASELINE_BYTES = RUNTIME_ALLOWANCE + CONTROL_STATE_BYTES


def exact_int(value, code='invalid_source', *, minimum=0, maximum=COUNT_MAX):
    if type(value) is not int or type(minimum) is not int or type(maximum) is not int:
        raise Refusal(code)
    if minimum > maximum or value < minimum or value > maximum:
        raise Refusal(code)
    return value


def utf8_length(value, code='invalid_json', *, maximum=None):
    """Count strict UTF-8 without allocating an encoded copy."""
    if type(value) is not str:
        raise Refusal(code)
    if maximum is not None:
        exact_int(maximum, code)
    total = 0
    for character in value:
        n = ord(character)
        if 0xD800 <= n <= 0xDFFF:
            raise Refusal(code)
        total += 1 if n < 0x80 else 2 if n < 0x800 else 3 if n < 0x10000 else 4
        if maximum is not None and total > maximum:
            raise Refusal(code)
    return total


def _mapping_items(value, code='invalid_json'):
    if type(value) is OwnedMap:
        return value._items
    if type(value) is not dict:
        raise Refusal(code)
    # Do not set(), sort(), look up, or compare keys until every key is exact.
    for key in value:
        utf8_length(key, code)
    return value.items()


@dataclass(frozen=True, slots=True)
class PrimitiveBounds:
    json_bytes: int
    object_bytes: int


def primitive_bounds(value, *, code='invalid_json', object_limit=LOGICAL_JOURNEY_LIMIT):
    """Frozen J/P, no aliases credited; JSON count excludes document LF."""
    exact_int(object_limit, code, maximum=LOGICAL_JOURNEY_LIMIT)
    used = 0

    def charge(amount):
        nonlocal used
        if amount > object_limit - used:
            raise Refusal('estimated_memory_limit')
        used += amount

    def visit(item, depth):
        kind = type(item)
        if item is None:
            charge(128); return 4
        if kind is bool:
            charge(128); return 5
        if kind is int:
            exact_int(item, code, minimum=JSON_INTEGER_MIN, maximum=JSON_INTEGER_MAX)
            charge(128); return 32
        if kind is float:
            if not math.isfinite(item):
                raise Refusal(code)
            charge(128); return 32
        if kind is str:
            n = utf8_length(item, code)
            charge(128 + 4*n); return 6*n + 2
        if kind not in (dict, list, tuple, OwnedMap):
            raise Refusal(code)
        if depth >= JSON_DEPTH_LIMIT:
            raise Refusal(code)
        count = len(item)
        charge(512 + 128*count)
        length = 2 + max(0, count-1)
        if kind in (dict, OwnedMap):
            for key, child in _mapping_items(item, code):
                length += visit(key, depth+1) + 1 + visit(child, depth+1)
        else:
            for child in item:
                length += visit(child, depth+1)
        return length

    try:
        length = visit(value, 0)
        return PrimitiveBounds(length, used)
    finally:
        # The recursive visitor closes over its own cell. Break that private
        # cycle on success and refusal without depending on caller cyclic GC.
        visit = None
        charge = None


class OwnedMap(Mapping):
    """Final immutable tuple-backed map of owned exact JSON primitives.

    Public construction accepts exact dict. _from_checked is only called with
    validated immutable children created in this module, never caller mappings.
    """
    __slots__ = ('_items',)

    def __init_subclass__(cls, **kwargs):
        raise TypeError('OwnedMap cannot be subclassed')

    def __init__(self, value):
        if hasattr(self, '_items'):
            raise AttributeError('OwnedMap is immutable')
        if type(value) is not dict:
            raise Refusal('invalid_json')
        primitive_bounds(value)
        object.__setattr__(self, '_items', tuple(
            (key, _freeze(value[key])) for key in sorted(value)))

    @classmethod
    def _from_checked(cls, items):
        instance = object.__new__(cls)
        object.__setattr__(instance, '_items', items)
        return instance

    def __setattr__(self, name, value):
        raise AttributeError('OwnedMap is immutable')

    def __delattr__(self, name):
        raise AttributeError('OwnedMap is immutable')

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return (key for key, _ in self._items)

    def __getitem__(self, key):
        if type(key) is not str:
            raise Refusal('invalid_json')
        for stored, value in self._items:
            if stored == key:
                return value
        raise KeyError(key)

    def items(self):
        return self._items

    def __eq__(self, other):
        # Never return NotImplemented to an arbitrary reflected equality hook.
        return type(other) is OwnedMap and self._items == other._items

    __hash__ = None


def _freeze(value):
    kind = type(value)
    if kind is OwnedMap:
        return value
    if kind is dict:
        return OwnedMap._from_checked(tuple((key, _freeze(value[key])) for key in sorted(value)))
    if kind in (tuple, list):
        return tuple(_freeze(item) for item in value)
    return value


def freeze(value, *, code='invalid_json'):
    primitive_bounds(value, code=code)
    return _freeze(value)


def _thaw(value):
    if type(value) is OwnedMap:
        return {key: _thaw(item) for key, item in value.items()}
    if type(value) is dict:
        return {key: _thaw(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_thaw(item) for item in value]
    return value


def thaw(value):
    primitive_bounds(value)
    return _thaw(value)


def preflight_json(value, *, limit, code='metadata_bytes_limit'):
    exact_int(limit, code, maximum=BUNDLE_BYTES_LIMIT)
    length = primitive_bounds(value).json_bytes + 1
    if length > limit:
        raise Refusal(code)
    return length


@dataclass(frozen=True, slots=True)
class JsonPreflight:
    raw_bytes: int
    max_depth: int
    containers: int
    entries: int
    scalars: int
    strings: int
    string_utf8_bytes_bound: int
    json_bytes_bound: int
    object_bytes: int
    scan_peak_bytes: int
    key_scratch_bytes: int


@dataclass(frozen=True, slots=True, init=False)
class _ResultDecodeContext:
    """Private result slots derived only from real freshly admitted inputs."""
    plan: object
    raw: bytes
    model_limit: int
    raw_limit: int
    scan_limit: int

    def __init_subclass__(cls, **kwargs): raise TypeError('Result decode context is final')
    def __init__(self, plan, raw):
        from .admission import _ACTIVE, _guard
        try: object.__getattribute__(self, 'plan')
        except AttributeError: pass
        else: raise Refusal('invalid_plan_input')
        active = _ACTIVE.get()
        if active is None or active.plan is not plan or type(raw) is not bytes:
            raise Refusal('invalid_plan_input')
        _guard('serialize')
        model_limit = plan.estimates['result_objects_bytes']
        raw_limit = plan.estimates['result_json_bytes']
        if len(raw) > BUNDLE_BYTES_LIMIT: raise Refusal('bundle_bytes_limit')
        if len(raw) > raw_limit: raise Refusal('invalid_result')
        for name, value in (('plan', plan), ('raw', raw), ('model_limit', model_limit),
                            ('raw_limit', raw_limit), ('scan_limit', model_limit+4*len(raw))):
            object.__setattr__(self, name, value)


class _Scanner:
    __slots__ = ('raw', 'size', 'position', 'object_limit', 'objects', 'containers',
                 'entries', 'scalars', 'strings', 'string_bytes', 'depth',
                 'scan_peak_bytes', 'key_scratch_bytes', 'exact_objects',
                 'decoded_utf8', 'result_context')

    def __init__(self, raw, object_limit, result_context=None):
        if result_context is not None:
            from .admission import _ACTIVE
            active = _ACTIVE.get()
            if (type(result_context) is not _ResultDecodeContext or
                    active is None or active.plan is not result_context.plan or
                    raw is not result_context.raw or type(object_limit) is not int or
                    object_limit != result_context.scan_limit):
                raise Refusal('invalid_plan_input')
        self.raw = raw
        self.size = len(raw)
        self.position = 0
        self.object_limit = object_limit
        self.objects = self.containers = self.entries = self.scalars = 0
        self.strings = self.string_bytes = self.depth = 0
        self.scan_peak_bytes = self.key_scratch_bytes = 0
        self.exact_objects = self.decoded_utf8 = 0
        self.result_context = result_context

    def charge(self, amount, exact_amount=None):
        if amount > self.object_limit - self.objects:
            raise Refusal('estimated_memory_limit')
        exact_amount = amount if exact_amount is None else exact_amount
        if (self.result_context is not None and
                exact_amount > self.result_context.model_limit-self.exact_objects):
            raise Refusal('estimated_memory_limit')
        self.objects += amount
        self.exact_objects += exact_amount
        self.scan_peak_bytes = max(self.scan_peak_bytes, self.objects)

    def reserve_key_scratch(self, token_length):
        # Final decoded-key P is already persistent in self.objects. Separately
        # reserve the byte slice and widest decoded JSON token BEFORE slicing.
        # This conservatively covers both slice+token and token+decoded-key
        # lifetimes without spending the final key allowance twice.
        scratch = (128 + token_length) + (128 + 4*token_length)
        if self.result_context is not None:
            if token_length > 770 or scratch > 4106: raise Refusal('invalid_result')
        elif scratch > self.object_limit - self.objects:
            raise Refusal('estimated_memory_limit')
        self.scan_peak_bytes = max(self.scan_peak_bytes, self.objects + scratch)
        self.key_scratch_bytes = max(self.key_scratch_bytes, scratch)

    def space(self):
        while self.position < self.size and self.raw[self.position] in (9, 10, 13, 32):
            self.position += 1

    def bad(self):
        raise Refusal('invalid_json')

    def string(self, *, key=False):
        start = self.position
        self.position += 1
        decoded = 0
        while self.position < self.size:
            b = self.raw[self.position]
            if b == 34:
                inner = self.position-start-1
                if self.result_context is not None and key and (decoded > 128 or inner+2 > 770):
                    raise Refusal('invalid_result')
                # All scalar/key charges precede allocating a decoded key.
                self.charge(128 + 4*inner, 128 + 4*decoded)
                self.decoded_utf8 = decoded
                self.scalars += 1; self.strings += 1; self.string_bytes += inner
                self.position += 1
                return start, self.position, 6*inner+2
            if b < 32:
                self.bad()
            if b == 92:
                self.position += 1
                if self.position >= self.size:
                    self.bad()
                escape = self.raw[self.position]
                if escape in b'"\\/bfnrt':
                    self.position += 1
                    decoded += 1
                    continue
                if escape != 117:
                    self.bad()
                codepoint = self.hex4(self.position+1)
                self.position += 5
                if 0xD800 <= codepoint <= 0xDBFF:
                    if self.raw[self.position:self.position+2] != b'\\u':
                        self.bad()
                    low = self.hex4(self.position+2)
                    if not 0xDC00 <= low <= 0xDFFF:
                        self.bad()
                    self.position += 6
                    decoded += 4
                elif 0xDC00 <= codepoint <= 0xDFFF:
                    self.bad()
                else:
                    decoded += 1 if codepoint < 0x80 else 2 if codepoint < 0x800 else 3
                continue
            if b < 128:
                self.position += 1
                decoded += 1
                continue
            # Exact UTF-8 ranges reject overlong encodings, surrogates and >U+10FFFF.
            if 0xC2 <= b <= 0xDF:
                width, low, high = 2, 0x80, 0xBF
            elif 0xE0 <= b <= 0xEF:
                width = 3
                low = 0xA0 if b == 0xE0 else 0x80
                high = 0x9F if b == 0xED else 0xBF
            elif 0xF0 <= b <= 0xF4:
                width = 4
                low = 0x90 if b == 0xF0 else 0x80
                high = 0x8F if b == 0xF4 else 0xBF
            else:
                self.bad()
            end = self.position + width
            if end > self.size or not low <= self.raw[self.position+1] <= high:
                self.bad()
            for index in range(self.position+2, end):
                if not 0x80 <= self.raw[index] <= 0xBF:
                    self.bad()
            self.position = end
            decoded += width
        self.bad()

    def hex4(self, start):
        if start+4 > self.size:
            self.bad()
        result = 0
        for position in range(start, start+4):
            character = self.raw[position]
            if 48 <= character <= 57:
                value = character-48
            elif 65 <= character <= 70:
                value = character-55
            elif 97 <= character <= 102:
                value = character-87
            else:
                self.bad()
            result = 16*result+value
        return result

    def number(self):
        start = self.position
        p, raw, size = start, self.raw, self.size
        if raw[p] == 45:
            p += 1
        if p >= size:
            self.bad()
        if raw[p] == 48:
            p += 1
        elif 49 <= raw[p] <= 57:
            while p < size and 48 <= raw[p] <= 57:
                p += 1
                if p-start > JSON_NUMERIC_TOKEN_LIMIT:
                    self.bad()
        else:
            self.bad()
        floating = False
        if p < size and raw[p] == 46:
            floating = True; p += 1
            first = p
            while p < size and 48 <= raw[p] <= 57:
                p += 1
                if p-start > JSON_NUMERIC_TOKEN_LIMIT:
                    self.bad()
            if p == first:
                self.bad()
        if p < size and raw[p] in (69, 101):
            floating = True; p += 1
            if p < size and raw[p] in (43, 45):
                p += 1
            first = p
            while p < size and 48 <= raw[p] <= 57:
                p += 1
                if p-start > JSON_NUMERIC_TOKEN_LIMIT:
                    self.bad()
            if p == first:
                self.bad()
        if p-start > JSON_NUMERIC_TOKEN_LIMIT:
            self.bad()
        self.charge(128)
        token = raw[start:p]  # Already <=32 bytes.
        number = float(token) if floating else int(token)
        if floating:
            if not math.isfinite(number):
                self.bad()
        elif not JSON_INTEGER_MIN <= number <= JSON_INTEGER_MAX:
            self.bad()
        self.position = p
        self.scalars += 1
        return 32

    def value(self, depth=0):
        self.space()
        if self.position >= self.size:
            self.bad()
        byte = self.raw[self.position]
        if byte == 34:
            return self.string()[2]
        if byte in (91, 123):
            if depth >= JSON_DEPTH_LIMIT:
                self.bad()
            self.depth = max(self.depth, depth+1)
            self.charge(512); self.containers += 1
            self.position += 1
            closing = 93 if byte == 91 else 125
            keys = set() if byte == 123 else None
            self.space()
            if self.position < self.size and self.raw[self.position] == closing:
                self.position += 1
                return 2
            length, count = 2, 0
            while True:
                self.charge(128); self.entries += 1
                if count:
                    length += 1
                self.space()
                if keys is not None:
                    if self.position >= self.size or self.raw[self.position] != 34:
                        self.bad()
                    start, end, key_bound = self.string(key=True)
                    self.reserve_key_scratch(end-start)
                    # Only this one key is decoded; values remain unmaterialized.
                    key = json.loads(self.raw[start:end].decode('utf-8'))
                    # The slice/token are now gone; only final-key P remains.
                    if key in keys:
                        self.bad()
                    keys.add(key)
                    self.space()
                    if self.position >= self.size or self.raw[self.position] != 58:
                        self.bad()
                    self.position += 1
                    length += key_bound + 1
                length += self.value(depth+1)
                count += 1
                self.space()
                if self.position >= self.size:
                    self.bad()
                punctuation = self.raw[self.position]
                self.position += 1
                if punctuation == closing:
                    return length
                if punctuation != 44:
                    self.bad()
        if byte == 45 or 48 <= byte <= 57:
            return self.number()
        for literal, length in ((b'null', 4), (b'true', 5), (b'false', 5)):
            if self.raw.startswith(literal, self.position):
                self.charge(128); self.scalars += 1
                self.position += len(literal)
                return length
        self.bad()


def json_prepass(raw, *, limit=METADATA_BYTES_LIMIT,
                 limit_code='metadata_bytes_limit', object_limit=LOGICAL_JOURNEY_LIMIT,
                 baseline_bytes=DEFAULT_PARSE_BASELINE_BYTES):
    """Scan under a remaining peak budget, including transient key scratch.

    baseline_bytes is already-live known state, excluding raw and this decode;
    it includes at least runtime/control allowance. object_limit is a further
    scan-peak cap, not permission to exceed the remaining journey domain.
    """
    if type(raw) is not bytes:
        raise Refusal('invalid_json')
    exact_int(limit, 'invalid_json', maximum=BUNDLE_BYTES_LIMIT)
    exact_int(object_limit, 'invalid_json', maximum=LOGICAL_JOURNEY_LIMIT)
    exact_int(baseline_bytes, 'invalid_json', minimum=DEFAULT_PARSE_BASELINE_BYTES,
              maximum=LOGICAL_JOURNEY_LIMIT)
    if len(raw) > limit:
        raise Refusal(limit_code)
    remaining = LOGICAL_JOURNEY_LIMIT - baseline_bytes - len(raw)
    if remaining < 0:
        raise Refusal('estimated_memory_limit')
    scanner = _Scanner(raw, min(object_limit, remaining))
    length = scanner.value()
    scanner.space()
    if scanner.position != len(raw):
        raise Refusal('invalid_json')
    return JsonPreflight(len(raw), scanner.depth, scanner.containers, scanner.entries,
                         scanner.scalars, scanner.strings, scanner.string_bytes,
                         length, scanner.objects, scanner.scan_peak_bytes,
                         scanner.key_scratch_bytes)


def strict_loads(raw, *, limit=METADATA_BYTES_LIMIT,
                 limit_code='metadata_bytes_limit', object_limit=LOGICAL_JOURNEY_LIMIT,
                 baseline_bytes=DEFAULT_PARSE_BASELINE_BYTES):
    """Standalone/metadata decode with prior scan and 5N+3P reservation.

    Result callers instead use the private actual-input slot entry below with
    this same lexer and full primitive decoder. No generic-baseline subtraction
    is used to manufacture room for a fourth forest.
    """
    scan = json_prepass(raw, limit=limit, limit_code=limit_code,
                        object_limit=object_limit, baseline_bytes=baseline_bytes)
    if baseline_bytes + 5*scan.raw_bytes + 3*scan.object_bytes > LOGICAL_JOURNEY_LIMIT:
        raise Refusal('estimated_memory_limit')
    return _decode_primitive(raw)


def _decode_primitive(raw):
    # Called only after the SAME complete lexical/UTF-8/domain prepass. Decoded
    # str prevents json.loads from autodetecting UTF-16/32 or a BOM.
    try:
        return json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeError, RecursionError):
        raise Refusal('invalid_json') from None


def _result_prepass(raw, context):
    """No forest: exact decoded P<=M, existing escaped P_scan<=M+4N."""
    scanner = _Scanner(raw, context.scan_limit, context)
    length = scanner.value()
    scanner.space()
    if scanner.position != len(raw): raise Refusal('invalid_json')
    return JsonPreflight(len(raw), scanner.depth, scanner.containers, scanner.entries,
        scanner.scalars, scanner.strings, scanner.string_bytes, length,
        scanner.objects, scanner.scan_peak_bytes, scanner.key_scratch_bytes)


def _strict_result_loads(raw, plan):
    """Bare result1 decode in the actual CALLER/PARSE/FINAL reservation.

    CALLER and every original source handle stay in the enclosing input scope.
    Scan is at most caller M+raw N+P_scan <=2M+5N; full decoding is at most
    caller M+parse M+5N. Final one-record adoption happens after this helper
    returns and fits caller M+parse M+final M+N. All are within unchanged
    3M+6B, with key/context scratch in the existing common fixed pool.
    """
    from .admission import _required_inputs, _guard
    with _required_inputs(plan=plan):
        context = _ResultDecodeContext(plan, raw)
        _result_prepass(raw, context)
        # Scanner/key-set frames ended before a fresh source/cache guard and
        # before the one full primitive forest is created.
        _guard('serialize')
        return _decode_primitive(raw)


_ESCAPES = {'"': b'\\"', '\\': b'\\\\', '\b': b'\\b', '\f': b'\\f',
            '\n': b'\\n', '\r': b'\\r', '\t': b'\\t'}


def _string_chunks(value):
    yield b'"'
    for character in value:
        escaped = _ESCAPES.get(character)
        if escaped is not None:
            yield escaped
        elif ord(character) < 32:
            yield ('\\u%04x' % ord(character)).encode('ascii')
        else:
            yield character.encode('utf-8')
    yield b'"'


def _chunks(value):
    kind = type(value)
    if value is None:
        yield b'null'
    elif kind is bool:
        yield b'true' if value else b'false'
    elif kind in (int, float):
        yield repr(value).encode('ascii')
    elif kind is str:
        yield from _string_chunks(value)
    elif kind in (OwnedMap, dict):
        yield b'{'
        # During the exact-size prewalk dict insertion order is sufficient;
        # emission uses the independently owned, Unicode-sorted map.
        for index, (key, child) in enumerate(value.items()):
            if index:
                yield b','
            yield from _string_chunks(key)
            yield b':'
            yield from _chunks(child)
        yield b'}'
    else:
        yield b'['
        for index, child in enumerate(value):
            if index:
                yield b','
            yield from _chunks(child)
        yield b']'


def _prepare_output(value, limit, code):
    exact_int(limit, code, maximum=BUNDLE_BYTES_LIMIT)
    # First qualify exact primitive types and projected immutable ownership.
    # Count actual emitted bytes before cloning any mutable container forest.
    primitive_bounds(value)
    length = 1  # final LF
    for fragment in _chunks(value):
        if len(fragment) > limit-length:
            raise Refusal(code)
        length += len(fragment)
    if length > limit:
        raise Refusal(code)
    return _freeze(value), length


def iter_json_chunks(value, *, limit=METADATA_BYTES_LIMIT, code='metadata_bytes_limit'):
    # An outer ordinary function makes ownership happen before exposing iterator.
    owned, _ = _prepare_output(value, limit, code)

    def generate():
        yield from _chunks(owned)
        yield b'\n'
    return generate()


def canonical_bytes(value, *, limit=METADATA_BYTES_LIMIT, code='metadata_bytes_limit'):
    owned, length = _prepare_output(value, limit, code)
    output = bytearray(length)
    offset = 0
    for fragment in _chunks(owned):
        end = offset + len(fragment)
        output[offset:end] = fragment
        offset = end
    output[offset] = 10
    return bytes(output)
