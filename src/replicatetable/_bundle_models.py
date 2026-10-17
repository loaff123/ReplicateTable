"""Shared immutable v2 value schemas, with no native or commit authority.

The supervisor owns mutable outcome/child state and contextual exit status.
An ErrorEnvelope is only its readonly value. Receipts, hashes and check strings
do not prove acquisition, replay, actual reap, or an installed destination.
"""
from dataclasses import dataclass

from .codec import OwnedMap, _chunks, _string_chunks, exact_int
from .errors import Refusal, ComputationError
from .model import SourceIdentity, _require_uninitialized
from . import resources as r


_CHECK_NAMES = ('replay', 'report', 'runtime_binding', 'source_binding', 'structure')
_CHECK_STATES = ('not_attempted', 'passed', 'failed')
_FINDING_NAMES = ('code', 'exit_code', 'message')

# Literal representation of the frozen API-SCHEMAS section14. Product policy
# never reads a documentation file, test fixture or caller-supplied registry.
_REFUSAL_CODES = frozenset((
    'invalid_recipe', 'residual_dimension', 'unapproved_broadcast',
    'unsupported_later_stage_weights', 'missing_stage_policy',
    'recipe_bytes_limit', 'invalid_json', 'invalid_plan', 'invalid_plan_input',
    'plan_binding_mismatch', 'source_resource_binding_mismatch',
    'invalid_source', 'invalid_source_phase', 'source_fingerprint_mismatch',
    'source_changed', 'unsupported_source_storage',
    'unsupported_coordinate_encoding', 'unsupported_source_encoding',
    'missing_coordinate', 'missing_row_key', 'duplicate_row_key',
    'duplicate_coordinate', 'nonfinite_coordinate', 'invalid_coordinate',
    'missing_unit_assertion', 'source_unit_mismatch', 'weight_unit_mismatch',
    'invalid_weights', 'negative_weight', 'nonfinite_weight', 'invalid_unit',
    'unknown_unit', 'incompatible_unit', 'unsupported_unit_converter',
    'unsupported_offset_unit', 'invalid_unit_operation', 'nonfinite_value',
    'invalid_result', 'result_replay_mismatch', 'invalid_explanation_key',
    'row_key_not_found', 'invalid_explanation', 'key_bytes_limit',
    'source_bytes_limit', 'selected_numeric_bytes_limit',
    'coordinate_bytes_limit', 'label_bytes_limit', 'metadata_bytes_limit',
    'output_rows_limit', 'support_records_limit', 'work_cell_limit',
    'estimated_memory_limit', 'report_bytes_limit', 'explanation_bytes_limit',
    'bundle_bytes_limit', 'invalid_bundle', 'bundle_digest_mismatch',
    'bundle_changed', 'report_mismatch', 'unsafe_path', 'source_output_overlap',
    'output_exists', 'unsafe_output_stream', 'unsupported_atomic_commit',
    'invalid_runtime', 'runtime_dependency_missing', 'runtime_dependency_mismatch',
    'runtime_artifact_missing', 'runtime_import_origin_mismatch',
    'runtime_identity_unavailable', 'runtime_identity_limit', 'runtime_changed',
    'runtime_binding_mismatch', 'cli_usage',
))
_FAILURE_CODES = frozenset((
    'numeric_overflow', 'invalid_worker_response', 'worker_failed',
    'worker_memory_limit', 'operation_timeout', 'io_error',
    'resource_estimate_mismatch',
))


def _code_exits(code):
    if type(code) is not str or not 1 <= len(code) <= 128:
        raise Refusal('invalid_bundle')
    if code in _REFUSAL_CODES: return (2,)
    if code in _FAILURE_CODES: return (3,)
    if code == 'supervision_unavailable': return (2, 3)
    if code == 'interrupted': return (130, 143)
    raise Refusal('invalid_bundle')


def _map_fields(value, names):
    kind = type(value)
    if kind is dict:
        if len(value) != len(names): raise Refusal('invalid_bundle')
        if any(type(key) is not str or key not in names for key in value):
            raise Refusal('invalid_bundle')
    elif kind is OwnedMap:
        try: items = object.__getattribute__(value, '_items')
        except AttributeError: raise Refusal('invalid_bundle') from None
        if type(items) is not tuple or len(items) != len(names):
            raise Refusal('invalid_bundle')
        for index, pair in enumerate(items):
            if type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not str or pair[0] != names[index]:
                raise Refusal('invalid_bundle')
    else:
        raise Refusal('invalid_bundle')
    return value


def _checks_inner(value):
    _map_fields(value, _CHECK_NAMES)
    for name in _CHECK_NAMES:
        state = value[name]
        if type(state) is not str or state not in _CHECK_STATES:
            raise Refusal('invalid_bundle')
    if type(value) is OwnedMap: return value
    return OwnedMap._from_checked(tuple((name, value[name]) for name in _CHECK_NAMES))


def _finding_text(code, message):
    if type(code) is not str or not 1 <= len(code) <= 128:
        raise Refusal('invalid_bundle')
    if any(character not in 'abcdefghijklmnopqrstuvwxyz0123456789_' for character in code):
        raise Refusal('invalid_bundle')
    if type(message) is not str or not 1 <= len(message) <= 512:
        raise Refusal('invalid_bundle')
    if any(ord(character) < 32 or ord(character) >= 127 for character in message):
        raise Refusal('invalid_bundle')
    return _code_exits(code)


def _finding_inner(value):
    if value is None: return None
    _map_fields(value, _FINDING_NAMES)
    exits = _finding_text(value['code'], value['message'])
    if type(value['exit_code']) is not int or value['exit_code'] not in exits:
        raise Refusal('invalid_bundle')
    if type(value) is OwnedMap: return value
    return OwnedMap._from_checked(tuple((name, value[name]) for name in _FINDING_NAMES))


def _own_checks(checks):
    from .source import _owned_attempt, _raise_owned
    owned, error = _owned_attempt(_checks_inner, checks)
    checks = None
    if error is not None: _raise_owned(error)
    return owned


def _own_finding(finding):
    from .source import _owned_attempt, _raise_owned
    owned, error = _owned_attempt(_finding_inner, finding)
    finding = None
    if error is not None: _raise_owned(error)
    return owned


def _digest(value, *, nullable=False):
    if nullable and value is None: return
    if type(value) is not str or len(value) != 64 or any(char not in '0123456789abcdef' for char in value):
        raise Refusal('invalid_bundle')


def _source(value, *, nullable=False):
    if nullable and value is None: return
    if type(value) is not SourceIdentity: raise Refusal('invalid_bundle')
    try: kind, digest, size = value.kind, value.sha256, value.size_bytes
    except AttributeError: raise Refusal('invalid_bundle') from None
    if type(kind) is not str or kind not in ('memory', 'file'):
        raise Refusal('invalid_bundle')
    _digest(digest)
    exact_int(size, 'invalid_bundle')


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        raise Refusal('invalid_bundle')


def _boolean(value):
    if type(value) is not bool: raise Refusal('invalid_bundle')


def _validate_values(kind, values):
    exact_int(values[0], 'invalid_bundle', minimum=2, maximum=2)
    owned = list(values)  # At most ten borrowed field slots, never child copies.
    if kind is PlanReceipt:
        _enum(values[1], ('committed',))
        _digest(values[2])
        exact_int(values[3], 'invalid_bundle', maximum=r.METADATA_BYTES_LIMIT)
        _boolean(values[4])
    elif kind is PreparedReceipt:
        _enum(values[1], ('plan', 'bundle'))
        _source(values[2])
        for index in (3, 4, 6): _digest(values[index])
        if values[1] == 'plan':
            if values[5] is not None or values[7] is not None: raise Refusal('invalid_bundle')
            cap = r.METADATA_BYTES_LIMIT
        else:
            _digest(values[5]); _digest(values[7])
            cap = r.BUNDLE_BYTES_LIMIT
        exact_int(values[8], 'invalid_bundle', maximum=cap)
    elif kind is BundleReceipt:
        _enum(values[1], ('committed',))
        _source(values[2])
        for index in (3, 4, 5, 6, 7): _digest(values[index])
        exact_int(values[8], 'invalid_bundle', maximum=r.BUNDLE_BYTES_LIMIT)
        _boolean(values[9])
    elif kind is BundleVerification:
        _enum(values[1], ('verified', 'refused', 'failed', 'cancelled'))
        owned[2] = _checks_inner(values[2])
        _source(values[3], nullable=True)
        for index in (4, 5, 6): _digest(values[index], nullable=True)
        owned[7] = _finding_inner(values[7])
        _boolean(values[8])
        if values[8]: raise Refusal('invalid_bundle')
        if values[1] == 'verified':
            if (owned[7] is not None or any(values[index] is None for index in (3, 4, 5, 6))
                    or any(state != 'passed' for _, state in owned[2].items())):
                raise Refusal('invalid_bundle')
        else:
            if owned[7] is None: raise Refusal('invalid_bundle')
            exit_code = owned[7]['exit_code']
            if ((values[1] == 'refused' and exit_code != 2) or
                    (values[1] == 'failed' and exit_code != 3) or
                    (values[1] == 'cancelled' and exit_code not in (130, 143))):
                raise Refusal('invalid_bundle')
    elif kind is ErrorEnvelope:
        _enum(values[1], ('refused', 'failed', 'cancelled'))
        exits = _finding_text(values[2], values[3])
        if ((values[1] == 'refused' and 2 not in exits) or
                (values[1] == 'failed' and 3 not in exits) or
                (values[1] == 'cancelled' and 130 not in exits)):
            raise Refusal('invalid_bundle')
        owned[4] = _checks_inner(values[4])
        _boolean(values[5])
        if values[5] != (values[6] is not None): raise Refusal('invalid_bundle')
        if values[6] is not None:
            if type(values[6]) is not BundleReceipt and type(values[6]) is not PlanReceipt:
                raise Refusal('invalid_bundle')
            _read_model(values[6])
            if values[1] == 'cancelled' and not values[6].interrupted_after_commit:
                raise Refusal('invalid_bundle')
    else:
        raise Refusal('invalid_bundle')
    return tuple(owned)


def _construct(instance, kind, values):
    if type(instance) is not kind: raise Refusal('invalid_bundle')
    _require_uninitialized(instance, 'version', 'invalid_bundle')
    _install(instance, kind, _validate_values(kind, values))


def _install(instance, kind, values):
    # Every field was validated before the first assignment. The fixed range
    # and tuple backing are allocated before adopting any field.
    for index in range(len(_NAMES[kind])):
        object.__setattr__(instance, _NAMES[kind][index], values[index])


class _ValueModel:
    __slots__ = ()

    def iter_json_chunks(self):
        from .source import _owned_attempt, _raise_owned
        value, error = _owned_attempt(_new_value_stream, self)
        self = None
        if error is not None: _raise_owned(error)
        return value

    def to_json(self):
        from .source import _owned_attempt, _raise_owned
        value, error = _owned_attempt(_value_bytes, self)
        self = None
        if error is not None: _raise_owned(error)
        return value


@dataclass(frozen=True, slots=True, init=False, eq=False)
class PlanReceipt(_ValueModel):
    version: int
    status: str
    plan_sha256: str
    plan_bytes: int
    interrupted_after_commit: bool

    def __init_subclass__(cls, **keywords): raise TypeError('PlanReceipt is final')
    def __init__(self, *, version, status, plan_sha256, plan_bytes, interrupted_after_commit):
        from .source import _owned_attempt, _raise_owned
        _, error = _owned_attempt(_construct, self, PlanReceipt,
            (version, status, plan_sha256, plan_bytes, interrupted_after_commit))
        version = status = plan_sha256 = plan_bytes = interrupted_after_commit = None
        self = None
        if error is not None: _raise_owned(error)


@dataclass(frozen=True, slots=True, init=False, eq=False)
class PreparedReceipt(_ValueModel):
    version: int
    kind: str
    source: SourceIdentity
    recipe_sha256: str
    plan_sha256: str
    result_sha256: str | None
    runtime_sha256: str
    manifest_sha256: str | None
    output_bytes: int

    def __init_subclass__(cls, **keywords): raise TypeError('PreparedReceipt is final')
    def __init__(self, *, version, kind, source, recipe_sha256, plan_sha256,
                 result_sha256, runtime_sha256, manifest_sha256, output_bytes):
        from .source import _owned_attempt, _raise_owned
        _, error = _owned_attempt(_construct, self, PreparedReceipt,
            (version, kind, source, recipe_sha256, plan_sha256, result_sha256,
             runtime_sha256, manifest_sha256, output_bytes))
        version = kind = source = recipe_sha256 = plan_sha256 = None
        result_sha256 = runtime_sha256 = manifest_sha256 = output_bytes = None
        self = None
        if error is not None: _raise_owned(error)


@dataclass(frozen=True, slots=True, init=False, eq=False)
class BundleReceipt(_ValueModel):
    version: int
    status: str
    source: SourceIdentity
    recipe_sha256: str
    plan_sha256: str
    result_sha256: str
    runtime_sha256: str
    manifest_sha256: str
    bundle_bytes: int
    interrupted_after_commit: bool

    def __init_subclass__(cls, **keywords): raise TypeError('BundleReceipt is final')
    def __init__(self, *, version, status, source, recipe_sha256, plan_sha256,
                 result_sha256, runtime_sha256, manifest_sha256, bundle_bytes,
                 interrupted_after_commit):
        from .source import _owned_attempt, _raise_owned
        _, error = _owned_attempt(_construct, self, BundleReceipt,
            (version, status, source, recipe_sha256, plan_sha256, result_sha256,
             runtime_sha256, manifest_sha256, bundle_bytes, interrupted_after_commit))
        version = status = source = recipe_sha256 = plan_sha256 = result_sha256 = None
        runtime_sha256 = manifest_sha256 = bundle_bytes = interrupted_after_commit = None
        self = None
        if error is not None: _raise_owned(error)


@dataclass(frozen=True, slots=True, init=False, eq=False)
class BundleVerification(_ValueModel):
    version: int
    status: str
    checks: OwnedMap
    source: SourceIdentity | None
    plan_sha256: str | None
    result_sha256: str | None
    manifest_sha256: str | None
    finding: OwnedMap | None
    committed: bool

    def __init_subclass__(cls, **keywords): raise TypeError('BundleVerification is final')
    def __init__(self, *, version, status, checks, source, plan_sha256,
                 result_sha256, manifest_sha256, finding, committed):
        from .source import _owned_attempt, _raise_owned
        _, error = _owned_attempt(_construct, self, BundleVerification,
            (version, status, checks, source, plan_sha256, result_sha256,
             manifest_sha256, finding, committed))
        version = status = checks = source = plan_sha256 = None
        result_sha256 = manifest_sha256 = finding = committed = None
        self = None
        if error is not None: _raise_owned(error)


@dataclass(frozen=True, slots=True, init=False, eq=False)
class ErrorEnvelope(_ValueModel):
    version: int
    status: str
    code: str
    message: str
    checks: OwnedMap
    committed: bool
    receipt: BundleReceipt | PlanReceipt | None

    def __init_subclass__(cls, **keywords): raise TypeError('ErrorEnvelope is final')
    def __init__(self, *, version, status, code, message, checks, committed, receipt):
        from .source import _owned_attempt, _raise_owned
        _, error = _owned_attempt(_construct, self, ErrorEnvelope,
            (version, status, code, message, checks, committed, receipt))
        version = status = code = message = checks = committed = receipt = None
        self = None
        if error is not None: _raise_owned(error)


_NAMES = {
    PlanReceipt: ('version', 'status', 'plan_sha256', 'plan_bytes', 'interrupted_after_commit'),
    PreparedReceipt: ('version', 'kind', 'source', 'recipe_sha256', 'plan_sha256',
                     'result_sha256', 'runtime_sha256', 'manifest_sha256', 'output_bytes'),
    BundleReceipt: ('version', 'status', 'source', 'recipe_sha256', 'plan_sha256',
                    'result_sha256', 'runtime_sha256', 'manifest_sha256',
                    'bundle_bytes', 'interrupted_after_commit'),
    BundleVerification: ('version', 'status', 'checks', 'source', 'plan_sha256',
                        'result_sha256', 'manifest_sha256', 'finding', 'committed'),
    ErrorEnvelope: ('version', 'status', 'code', 'message', 'checks', 'committed', 'receipt'),
}
_ORDER = {kind: tuple(sorted(range(len(names)), key=names.__getitem__))
          for kind, names in _NAMES.items()}


def _read_model(model):
    kind = type(model)
    if (kind is not PlanReceipt and kind is not PreparedReceipt and
            kind is not BundleReceipt and kind is not BundleVerification and
            kind is not ErrorEnvelope):
        raise Refusal('invalid_bundle')
    try: values = tuple(object.__getattribute__(model, name) for name in _NAMES[kind])
    except AttributeError: raise Refusal('invalid_bundle') from None
    return _validate_values(kind, values)


def _source_chunks(source):
    yield b'{"kind":'
    yield from _chunks(source.kind)
    yield b',"sha256":'
    yield from _chunks(source.sha256)
    yield b',"size_bytes":'
    yield from _chunks(source.size_bytes)
    yield b'}'


def _model_chunks(model):
    """Direct existing-field walk; no root or nested projection forest."""
    values = _read_model(model)
    kind = type(model)
    yield b'{'
    for position, index in enumerate(_ORDER[kind]):
        if position: yield b','
        name = _NAMES[kind][index]
        value = values[index]
        yield from _string_chunks(name)
        yield b':'
        if name == 'source' and value is not None:
            yield from _source_chunks(value)
        elif name == 'receipt' and value is not None:
            yield from _model_chunks(value)
        else:
            yield from _chunks(value)
    yield b'}'


def _complete_chunks(model):
    yield from _model_chunks(model)
    yield b'\n'


def _value_bytes(model):
    length = 0
    for fragment in _complete_chunks(model):
        if len(fragment) > r.SERIAL_BUFFER_BYTES-length:
            # Each buffer fits one existing64KiB serial slot by this family's
            # closed field bounds. A violation is an internal estimate fault.
            raise ComputationError('resource_estimate_mismatch')
        length += len(fragment)
    output = bytearray(length)
    offset = 0
    for fragment in _complete_chunks(model):
        if len(fragment) > length-offset:
            raise ComputationError('resource_estimate_mismatch')
        end = offset + len(fragment)
        output[offset:end] = fragment
        offset = end
    if offset != length: raise ComputationError('resource_estimate_mismatch')
    return bytes(output)


def _new_value_stream(model):
    _read_model(model)
    return _ValueStream(model)


class _ValueStream:
    __slots__ = ('_model', '_inner', '_closed')
    def __init_subclass__(cls, **keywords): raise TypeError('Value streams are final')
    def __init__(self, model):
        self._model = model
        self._inner = None
        self._closed = False
    def __iter__(self): return self
    def __next__(self): return _value_call(self, 'next')
    def close(self): return _value_call(self, 'close')
    def throw(self, error): return _value_call(self, 'throw', error)


def _retire_value(stream):
    inner = stream._inner
    stream._model = stream._inner = None
    stream._closed = True
    if inner is not None: inner.close()


def _drive_value(stream, operation, error):
    try:
        if operation == 'close':
            _retire_value(stream)
            return None
        if operation == 'throw':
            if not isinstance(error, BaseException): raise TypeError('throw requires an exception instance')
            raise error
        if stream._closed: raise StopIteration
        if stream._inner is None:
            stream._inner = _complete_chunks(stream._model)
            stream._model = None
        return next(stream._inner)
    except BaseException:
        try: _retire_value(stream)
        except BaseException as cleanup:
            BaseException.__traceback__.__set__(cleanup, None)
            BaseException.__context__.__set__(cleanup, None)
            BaseException.__cause__.__set__(cleanup, None)
        raise


def _value_call(stream, operation, error=None):
    from .source import _owned_attempt, _raise_owned
    value, failure = _owned_attempt(_drive_value, stream, operation, error)
    stream = error = None
    if failure is not None: _raise_owned(failure)
    return value
