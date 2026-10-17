"""Private bounded stock-Pint operations; structural models import no science.

These models prove a finite primitive graph, never stock/source/runtime authority.
The enclosing semantic caller must establish its fresh runtime and admission gate.
"""
from dataclasses import dataclass
import math

from .codec import OwnedMap, freeze, thaw, primitive_bounds, canonical_bytes
from .errors import Refusal, ComputationError
from .model import validate_unit, validate_name, ArrayBuffer, _dtype_info
from .resources import JSON_INTEGER_MIN, JSON_INTEGER_MAX, SELECTED_NUMERIC_BYTES_LIMIT

_CODE = 'invalid_unit_operation'
MAX_GRAPH_NODES = 128
MAX_GRAPH_REFERENCES = 512
MAX_OPERATION_BYTES = 65536
_OPERATION_FIELDS = ('source_unit', 'target_unit', 'scale', 'offset',
                     'parsed_source', 'parsed_target', 'definition_graph')
_NODE_FIELDS = ('name', 'converter', 'scale', 'offset', 'is_base', 'reference')


def _number(value, *, positive=False):
    if (type(value) not in (int, float)
            or type(value) is int and not JSON_INTEGER_MIN <= value <= JSON_INTEGER_MAX
            or not math.isfinite(value) or positive and value <= 0):
        raise Refusal(_CODE)
    return value


def _fields(value, fields):
    if type(value) is OwnedMap:
        try:
            items = object.__getattribute__(value, '_items')
        except AttributeError:
            raise Refusal(_CODE) from None
        if type(items) is not tuple or len(items) != len(fields):
            raise Refusal(_CODE)
        previous = None
        for pair in items:
            if type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not str:
                raise Refusal(_CODE)
            key = pair[0]
            if key not in fields or previous is not None and key <= previous:
                raise Refusal(_CODE)
            previous = key
    elif type(value) is dict:
        if len(value) != len(fields) or any(type(k) is not str for k in value):
            raise Refusal(_CODE)
        if set(value) != set(fields):
            raise Refusal(_CODE)
    else:
        raise Refusal(_CODE)


def _terms(value):
    if type(value) not in (list, tuple) or len(value) > MAX_GRAPH_REFERENCES:
        raise Refusal(_CODE)
    previous = None
    for pair in value:
        if type(pair) not in (list, tuple) or len(pair) != 2:
            raise Refusal(_CODE)
        name, exponent = pair
        validate_name(name, _CODE)
        _number(exponent)
        if exponent == 0 or previous is not None and name <= previous:
            raise Refusal(_CODE)
        previous = name
    return value


def _derive(source, target, graph):
    """Derive affine coefficients from an already structurally checked graph."""
    by_name = {node['name']: node for node in graph}
    resolved = {}; visiting = set()

    def terms(parts):
        scale = 1.; dimensions = {}; offset_child = None
        for name, exponent in parts:
            child = resolve(name)
            if child[3]:
                if len(parts) != 1 or exponent != 1:
                    raise Refusal('unsupported_offset_unit')
                offset_child = child
            else:
                scale *= child[0] ** exponent
                _number(scale, positive=True)
                for dimension, power in child[2].items():
                    dimensions[dimension] = _number(dimensions.get(dimension, 0) + power * exponent)
        if offset_child is not None:
            return offset_child
        return scale, 0., {k: v for k, v in dimensions.items() if v != 0}, False

    def resolve(name):
        if name in resolved:
            return resolved[name]
        if name in visiting or name not in by_name:
            raise Refusal(_CODE)
        visiting.add(name)
        node = by_name[name]
        if node['is_base']:
            for dimension, _ in node['reference']:
                if not (dimension.startswith('[') and dimension.endswith(']')):
                    raise Refusal(_CODE)
            # Pint's empty dimension marker is neutral, but remains in the raw graph.
            reference = 1., 0., {d: p for d, p in node['reference'] if d != '[]'}, False
        else:
            reference = terms(node['reference'])
        scale = _number(node['scale'] * reference[0], positive=True)
        offset = _number(node['offset'] * reference[0] + reference[1])
        result = scale, offset, reference[2], reference[3] or node['converter'] == 'OffsetConverter'
        resolved[name] = result
        visiting.remove(name)
        return result

    try:
        a = terms(source); b = terms(target)
        if a[2] != b[2]:
            raise Refusal('incompatible_unit')
        scale = _number(a[0] / b[0], positive=True)
        offset = _number((a[1] - b[1]) / b[0])
        if len(resolved) != len(by_name):
            raise Refusal(_CODE)
        return float(scale), float(offset)
    except (OverflowError, ZeroDivisionError):
        raise Refusal(_CODE) from None
    finally:
        # Recursive local functions otherwise retain each other with GC disabled.
        terms = resolve = None


def _check_operation(source_unit, target_unit, scale, offset,
                     parsed_source, parsed_target, definition_graph):
    validate_unit(source_unit, _CODE); validate_unit(target_unit, _CODE)
    _number(scale, positive=True); _number(offset)
    graph = definition_graph
    if type(graph) not in (list, tuple) or len(graph) > MAX_GRAPH_NODES:
        raise Refusal(_CODE)
    count = 0; previous = None
    for node in graph:
        _fields(node, _NODE_FIELDS)
        name = node['name']; validate_name(name, _CODE)
        if previous is not None and name <= previous:
            raise Refusal(_CODE)
        previous = name
        converter = node['converter']
        if type(converter) is not str or converter not in ('ScaleConverter', 'OffsetConverter'):
            raise Refusal(_CODE)
        _number(node['scale'], positive=True); _number(node['offset'])
        if type(node['is_base']) is not bool or converter == 'ScaleConverter' and node['offset'] != 0:
            raise Refusal(_CODE)
        count += len(_terms(node['reference']))
        if count > MAX_GRAPH_REFERENCES:
            raise Refusal(_CODE)
    for parsed in (parsed_source, parsed_target):
        if parsed is not None:
            count += len(_terms(parsed))
            if count > MAX_GRAPH_REFERENCES:
                raise Refusal(_CODE)
    projection = dict(zip(_OPERATION_FIELDS, (source_unit, target_unit, scale, offset,
                          parsed_source, parsed_target, graph)))
    if primitive_bounds(projection, code=_CODE).json_bytes + 1 > MAX_OPERATION_BYTES:
        raise Refusal(_CODE)
    if source_unit is None:
        if parsed_source is not None or graph or scale != 1 or offset != 0:
            raise Refusal(_CODE)
        if target_unit is None:
            if parsed_target is not None:
                raise Refusal(_CODE)
        elif target_unit != 'dimensionless' or parsed_target != [] and parsed_target != ():
            raise Refusal(_CODE)
    else:
        if parsed_source is None or parsed_target is None:
            raise Refusal(_CODE)
        if target_unit is None and parsed_source != parsed_target:
            raise Refusal(_CODE)
        derived_scale, derived_offset = _derive(parsed_source, parsed_target, graph)
        if scale != derived_scale or offset != derived_offset:
            raise Refusal(_CODE)


@dataclass(frozen=True, slots=True, init=False)
class UnitOperation:
    source_unit: str | None
    target_unit: str | None
    scale: float
    offset: float
    parsed_source: tuple | None
    parsed_target: tuple | None
    definition_graph: tuple

    def __init__(self, source_unit, target_unit, scale, offset, parsed_source,
                 parsed_target, definition_graph):
        try:
            object.__getattribute__(self, 'source_unit')
        except AttributeError:
            pass
        else:
            raise Refusal(_CODE)
        _check_operation(source_unit, target_unit, scale, offset,
                         parsed_source, parsed_target, definition_graph)
        # Nothing owned is copied until full structural/algebraic coherence passes.
        source = None if parsed_source is None else tuple(tuple(t) for t in parsed_source)
        target = None if parsed_target is None else tuple(tuple(t) for t in parsed_target)
        graph = tuple(freeze({key: node[key] for key in _NODE_FIELDS}, code=_CODE)
                      for node in definition_graph)
        for name, value in zip(_OPERATION_FIELDS, (source_unit, target_unit, float(scale),
                                float(offset), source, target, graph)):
            object.__setattr__(self, name, value)

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict:
            raise Refusal(_CODE)
        _fields(value, _OPERATION_FIELDS)
        return cls(*(value[name] for name in _OPERATION_FIELDS))

    def _projection(self):
        return {name: object.__getattribute__(self, name) for name in _OPERATION_FIELDS}

    def to_dict(self):
        return thaw(self._projection())

    def to_json(self):
        return canonical_bytes(self._projection(), limit=MAX_OPERATION_BYTES)

    @property
    def effective_unit(self):
        return self.source_unit if self.target_unit is None else self.target_unit


# All scientific imports below are lazy and stay behind the private caller gate.
import re
import token as _token
import tokenize as _tokenize
from collections import ChainMap
from threading import get_ident
from _thread import RLock as _NativeRLock
from types import FunctionType, ModuleType
from functools import _lru_cache_wrapper
from abc import ABCMeta

# Native ownership closes the acquire-to-Python-bookkeeping interval.
# Context admission below still explicitly rejects reentry.
_stock_lock = _NativeRLock()
_stock_baseline = None
_stock_attempted = False
_stock_poisoned = False
_active_context = None
_CACHE_FIELDS = ('dimensional_equivalents', 'root_units', 'dimensionality',
                 'parse_unit', 'conversion_factor')
_STOCK_FIELDS = ('_caches', '_context_units', '_units_casei', '_base_units_cache',
                 '_contexts', '_groups', '_systems', '_prefixes', '_suffixes',
                 '_dimensions', '_defaults')
_ERROR_LINKS = tuple(BaseException.__dict__[name] for name in
                    ('__traceback__', '__context__', '__cause__'))
_LITERAL = re.compile(r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z', re.ASCII)


def _detach_owned_error(error):
    """Drop only this owned boundary's links, with no subclass setter hooks."""
    for descriptor in _ERROR_LINKS:
        descriptor.__set__(error, None)


def _return_or_raise(outcome):
    # No input array, private registry, parser, graph or normalization locals.
    if outcome[0]:
        return outcome[1]
    pending = [outcome[1]]
    del outcome
    # The raise operand is removed from our only retained container first.
    raise pending.pop()


def _capture_owned(function, *arguments):
    try:
        return True, function(*arguments)
    except BaseException as error:
        _detach_owned_error(error)
        return False, error


def _function(value, module, name, qualname=None):
    if type(value) is not FunctionType or value.__globals__ is not module.__dict__:
        raise Refusal(_CODE)
    for actual, expected in ((value.__module__, module.__name__), (value.__name__, name),
                             (value.__qualname__, name if qualname is None else qualname)):
        if type(actual) is not str or actual != expected:
            raise Refusal(_CODE)


def _class_profile(value, module, name, metaclass=type):
    if type(value) is not metaclass:
        raise Refusal(_CODE)
    for field, expected in (('__module__', module), ('__name__', name), ('__qualname__', name)):
        actual = type.__getattribute__(value, field)
        if type(actual) is not str or actual != expected:
            raise Refusal(_CODE)


def _parser_profile():
    from pint import pint_eval as pe, util
    from pint.facets.plain import registry as plain
    for module, name in ((pe, 'pint.pint_eval'), (util, 'pint.util'),
                         (plain, 'pint.facets.plain.registry')):
        if type(module) is not ModuleType or type(module.__name__) is not str or module.__name__ != name:
            raise Refusal(_CODE)
    _function(pe.plain_tokenizer, pe, 'plain_tokenizer')
    if pe.tokenizer is not pe.plain_tokenizer:
        raise Refusal(_CODE)
    _function(util.string_preprocessor, util, 'string_preprocessor')
    if plain.string_preprocessor is not util.string_preprocessor:
        raise Refusal(_CODE)
    _function(pe.build_eval_tree, pe, 'build_eval_tree')
    _function(pe._build_eval_tree, pe, '_build_eval_tree')
    if util.build_eval_tree is not pe.build_eval_tree or plain.build_eval_tree is not pe.build_eval_tree:
        raise Refusal(_CODE)
    _class_profile(pe.EvalTreeNode, 'pint.pint_eval', 'EvalTreeNode')
    _class_profile(util.ParserHelper, 'pint.util', 'ParserHelper', ABCMeta)
    method = type.__getattribute__(util.ParserHelper, '__dict__').get('from_string')
    if type(method) is not classmethod:
        raise Refusal(_CODE)
    helper = method.__func__
    if type(helper) is not _lru_cache_wrapper:
        raise Refusal(_CODE)
    _function(helper.__wrapped__, util, 'from_string', 'ParserHelper.from_string')
    if _lru_cache_wrapper.cache_info(helper).maxsize != 128:
        raise Refusal(_CODE)
    return pe, util


def _initial_stock_factory(pint):
    """Exact finite constructor/metaclass alias profile, not MRO attestation."""
    from pint.facets.plain import registry as plain
    if type(pint) is not ModuleType:
        raise Refusal(_CODE)
    registry_module = pint.__dict__.get('registry')
    if type(registry_module) is not ModuleType or type(plain) is not ModuleType:
        raise Refusal(_CODE)
    for module, expected in ((pint, 'pint'), (registry_module, 'pint.registry'),
                             (plain, 'pint.facets.plain.registry')):
        name = module.__dict__.get('__name__')
        if type(name) is not str or name != expected:
            raise Refusal(_CODE)
    metaclass = plain.__dict__.get('RegistryMeta')
    if type(metaclass) is not type:
        raise Refusal(_CODE)
    for name, expected in (('__module__', 'pint.facets.plain.registry'),
                           ('__name__', 'RegistryMeta'), ('__qualname__', 'RegistryMeta')):
        value = type.__getattribute__(metaclass, name)
        if type(value) is not str or value != expected:
            raise Refusal(_CODE)
    factory = pint.__dict__.get('UnitRegistry')
    if type(factory) is not metaclass or registry_module.__dict__.get('UnitRegistry') is not factory:
        raise Refusal(_CODE)
    for name, expected in (('__module__', 'pint.registry'),
                           ('__name__', 'UnitRegistry'), ('__qualname__', 'UnitRegistry')):
        value = type.__getattribute__(factory, name)
        if type(value) is not str or value != expected:
            raise Refusal(_CODE)
    return factory


def _registry_preprocessors(registry):
    from pint.facets.plain import registry as plain
    processors = registry.preprocessors
    if type(processors) is not list or len(processors) != 3:
        raise Refusal(_CODE)
    for function, pair in zip(processors, (('×', '*'), ('‰', ' permille '), ('%', ' percent '))):
        _function(function, plain, '<lambda>', 'GenericPlainRegistry.__init__.<locals>.<lambda>')
        # Finite metadata for the three specifically audited stock replacements.
        if function.__code__.co_consts != (None, *pair):
            raise Refusal(_CODE)


def _initialize_stock():
    global _stock_attempted, _stock_baseline, _stock_poisoned
    if _stock_poisoned:
        raise Refusal(_CODE)
    if _stock_baseline is not None:
        return _stock_baseline
    if _stock_attempted:
        raise Refusal(_CODE)
    _stock_attempted = True
    try:
        import pint
        from pint.facets.plain.registry import RegistryCache
        factory = _initial_stock_factory(pint)
        _parser_profile()
        if pint.__version__ != '0.25.2':
            raise Refusal('runtime_dependency_mismatch')
        registry = factory()
        if type(registry) is not factory:
            raise Refusal(_CODE)
        _registry_preprocessors(registry)
        unit_map = registry._units
        if type(unit_map) is not ChainMap or type(unit_map.maps) is not list or len(unit_map.maps) != 1 or type(unit_map.maps[0]) is not dict:
            raise Refusal(_CODE)
        cache = registry._cache
        if type(cache) is not RegistryCache or any(type(getattr(cache, f)) is not dict for f in _CACHE_FIELDS):
            raise Refusal(_CODE)
        if registry._caches != {(): cache} or registry._context_units or registry._base_units_cache or registry._active_ctx:
            raise Refusal(_CODE)
        fixed = tuple((name, getattr(registry, name), len(getattr(registry, name))) for name in _STOCK_FIELDS)
        cached = tuple((name, getattr(cache, name), len(getattr(cache, name))) for name in _CACHE_FIELDS)
        _stock_baseline = registry, unit_map, unit_map.maps, unit_map.maps[0], cache, fixed, cached, len(unit_map.maps[0])
        return _stock_baseline
    except BaseException:
        _stock_poisoned = True
        raise


def _restore_stock(context):
    """Finally-protected partial-entry and normal-exit restoration."""
    global _stock_poisoned
    if _stock_baseline is None:
        return
    registry, unit_map, maps, stock, cache, fixed, cached, stock_count = _stock_baseline
    established = False
    try:
        expected_layout = (registry._units is unit_map and unit_map.maps is maps
            and ((len(maps) == 2 and maps[0] is context._overlay and maps[1] is stock)
                 or (len(maps) == 1 and maps[0] is stock)))
        registry._cache = cache
        if maps and maps[0] is context._overlay:
            del maps[0]
        if not expected_layout:
            raise Refusal(_CODE)
        if len(stock) != stock_count or registry._cache is not cache:
            raise Refusal(_CODE)
        for name, original, size in fixed:
            if getattr(registry, name) is not original or len(original) != size:
                raise Refusal(_CODE)
        for name, original, size in cached:
            if getattr(cache, name) is not original or len(original) != size:
                raise Refusal(_CODE)
        if registry._active_ctx or registry._caches.get(()) is not cache:
            raise Refusal(_CODE)
        established = True
    finally:
        if not established:
            _stock_poisoned = True
        # Release only our known front overlay/cache, even on a poisoned exit.
        if maps and maps[0] is context._overlay:
            del maps[0]
        if registry._cache is context._cache:
            registry._cache = cache


def _lock_is_owned():
    return _NativeRLock._is_owned(_stock_lock)


def _has_active_owner(context):
    # Cleanup authority comes from this exact pass, not native ownership alone.
    return (type(context) is _StockUnitContext and _active_context is context
            and context._state == 'active' and context._owner == get_ident()
            and _lock_is_owned())


class _StockUnitContext:
    """One process-owned registry pass; only enclosing semantic callers use it."""
    __slots__ = ('_state', '_owner', '_attempts', '_registry', '_cache', '_overlay')

    def __init__(self):
        try:
            object.__getattribute__(self, '_state')
        except AttributeError:
            pass
        else:
            raise Refusal(_CODE)
        self._state = 'new'; self._owner = None; self._attempts = 0
        self._registry = self._cache = self._overlay = None

    def __enter__(self):
        global _active_context, _stock_poisoned
        # Reject preexisting ownership OUTSIDE cleanup: an inner refusal must
        # never release an outer same-thread pass's lock.
        if (type(self) is not _StockUnitContext or self._state != 'new'
                or _stock_poisoned or _active_context is not None or _lock_is_owned()):
            raise Refusal(_CODE)
        outcome = recovery = None
        try:
            if not _stock_lock.acquire(blocking=False):
                raise Refusal(_CODE)
            self._owner = get_ident(); self._state = 'entering'; _active_context = self
            outcome = _capture_owned(self._enter_owned)
            if not outcome[0]:
                _return_or_raise(outcome)
            return self
        except BaseException as error:
            # Native ownership is true even if interruption preceded the first
            # Python owner assignment. No acquisition flag can establish that.
            recovery = _capture_owned(self._recover_owned)
            if not recovery[0]:
                _stock_poisoned = True
                _capture_owned(self._recover_owned)
            _detach_owned_error(error)
            pending = [error]
        outcome = recovery = None
        return _return_or_raise((False, pending.pop()))

    def _enter_owned(self):
        baseline = _initialize_stock()
        from pint.facets.plain.registry import RegistryCache
        self._registry = baseline[0]
        self._overlay = {}
        self._cache = RegistryCache()
        baseline[2].insert(0, self._overlay)
        self._registry._cache = self._cache
        self._state = 'active'
        return self

    def _require_active(self):
        if (type(self) is not _StockUnitContext or self._state != 'active'
                or self._owner != get_ident() or _active_context is not self or _stock_poisoned):
            raise Refusal(_CODE)

    def _registry_for_attempt(self):
        self._require_active()
        return self._registry

    def _begin_attempt(self):
        self._require_active()
        if self._attempts >= 64:
            raise Refusal(_CODE)
        self._attempts += 1

    def _retire(self):
        global _active_context
        self._registry = self._cache = self._overlay = None
        self._owner = None; self._state = 'closed'; _active_context = None
        _stock_lock.release()

    def _recover_owned(self):
        """Bounded idempotent recovery for this pass, never a foreign lock."""
        global _stock_poisoned
        if not _lock_is_owned():
            return
        restored = _capture_owned(_restore_stock, self)
        if not restored[0]:
            _stock_poisoned = True
            # One bounded retry releases the known overlay after an interrupted
            # restore. A failed restore remains poisoned even if this succeeds.
            _capture_owned(_restore_stock, self)
        retired = _capture_owned(self._retire)
        if not retired[0]:
            _stock_poisoned = True
            if _lock_is_owned():
                _capture_owned(self._retire)

    def __exit__(self, error_type, error, traceback):
        global _stock_poisoned
        try:
            # This is the first executable exit region. If interruption precedes
            # the assignment, the handler re-establishes the same exact owner fact.
            valid_exit = _has_active_owner(self)
            _StockUnitContext._require_active(self)
            outcome = recovery = None
            outcome = _capture_owned(_restore_stock, self)
            if not outcome[0]:
                _stock_poisoned = True
                _capture_owned(_restore_stock, self)
            self._retire()
            if error is None:
                _return_or_raise(outcome)
            return False
        except BaseException as caught:
            try:
                allowed = valid_exit
            except UnboundLocalError:
                allowed = _has_active_owner(self)
            # None is authorized only by this invocation's established valid
            # exit: retirement may have cleared the active pointer before release.
            if (allowed and _lock_is_owned()
                    and (_active_context is self or _active_context is None)):
                recovery = _capture_owned(self._recover_owned)
                if not recovery[0]:
                    _stock_poisoned = True
                    _capture_owned(self._recover_owned)
            _detach_owned_error(caught)
            pending = [caught]
        outcome = recovery = None
        if allowed and error is not None:
            # Preserve an escaping body exception only for an authorized exit.
            # Inactive/foreign/wrong-thread calls still raise their own refusal.
            return False
        return _return_or_raise((False, pending.pop()))


def _normalized_text(raw):
    from pint import util
    text = raw
    for old, new in (('×', '*'), ('‰', ' permille '), ('%', ' percent ')):
        text = text.replace(old, new)
    # Transfer sole transformed ownership before the stock multi-step helper.
    pending = [text.strip()]
    del text
    return util.string_preprocessor(pending.pop())


def _literal(node):
    from pint.pint_eval import EvalTreeNode
    sign = 1
    if type(node) is not EvalTreeNode:
        raise Refusal('invalid_unit')
    if node.operator is not None:
        if node.right is not None or node.operator.string not in ('+', '-'):
            raise Refusal('invalid_unit')
        sign = -1 if node.operator.string == '-' else 1
        node = node.left
    if type(node) is not EvalTreeNode or node.operator is not None or node.right is not None or type(node.left) is not _tokenize.TokenInfo or node.left.type != _token.NUMBER:
        raise Refusal('invalid_unit')
    return _numeric_literal(node.left.string, sign)


def _numeric_literal(text, sign=1):
    if len(text) > 32 or not text.isascii() or _LITERAL.fullmatch(text) is None:
        raise Refusal('invalid_unit')
    try:
        value = int(text) if text.isdecimal() else float(text)
        value *= sign
        _number(value)
    except (ValueError, OverflowError):
        raise Refusal('invalid_unit') from None
    return value


def _guard_label(raw):
    """No evaluation; reserve 524288 bytes in the enclosing runtime allowance."""
    from .codec import utf8_length
    validate_unit(raw, 'invalid_unit')
    if raw is None:
        raise Refusal('invalid_unit')
    pe, _ = _parser_profile()
    raw_bytes = utf8_length(raw, 'invalid_unit', maximum=512)
    transformed_bound = min(16 * raw_bytes, 8192)
    text = _normalized_text(raw)
    if utf8_length(text, 'invalid_unit', maximum=transformed_bound) == 0:
        raise Refusal('invalid_unit')
    tokens = []; meaningful = 0; depth = 0; terminators = 0
    try:
        for current in pe.plain_tokenizer(text):
            if type(current) is not _tokenize.TokenInfo:
                raise Refusal(_CODE)
            kind, spelling = current.type, current.string
            if kind in (_token.NEWLINE, _token.ENDMARKER) and spelling == '':
                terminators += 1
                if terminators > 2:
                    raise Refusal('invalid_unit')
            else:
                if terminators:
                    raise Refusal('invalid_unit')
                meaningful += 1
                if meaningful > 128:
                    raise Refusal('invalid_unit')
                if kind == _token.OP:
                    if spelling not in ('(', ')', '*', '/', '**', '+', '-'):
                        raise Refusal('invalid_unit')
                    if spelling == '(':
                        depth += 1
                        if depth > 32:
                            raise Refusal('invalid_unit')
                    elif spelling == ')':
                        depth -= 1
                        if depth < 0:
                            raise Refusal('invalid_unit')
                elif kind == _token.NUMBER:
                    previous = len(tokens) - 1
                    while previous >= 0 and tokens[previous].string == '(':
                        previous -= 1
                    sign = -1 if previous >= 0 and tokens[previous].string == '-' else 1
                    _numeric_literal(spelling, sign)
                elif kind != _token.NAME:
                    raise Refusal('invalid_unit')
            tokens.append(current)
        if not meaningful or depth or not tokens or tokens[-1].type != _token.ENDMARKER:
            raise Refusal('invalid_unit')
        tree = pe.build_eval_tree(tokens)
    except (_tokenize.TokenError, SyntaxError, AssertionError, IndexError, RecursionError):
        raise Refusal('invalid_unit') from None
    # Complete structural walk comes before semantic grammar traversal.
    pending = [(tree, 1)]; count = 0
    while pending:
        node, depth = pending.pop(); count += 1
        if type(node) is not pe.EvalTreeNode or depth > 32 or count > 255:
            raise Refusal('invalid_unit')
        fields = node.__dict__
        if type(fields) is not dict or any(type(k) is not str for k in fields) or set(fields) != {'left', 'operator', 'right'}:
            raise Refusal(_CODE)
        if node.operator is not None and type(node.operator) is not _tokenize.TokenInfo:
            raise Refusal(_CODE)
        if node.right is not None:
            pending.append((node.right, depth+1)); pending.append((node.left, depth+1))
        elif node.operator is not None:
            pending.append((node.left, depth+1))
        elif type(node.left) is not _tokenize.TokenInfo:
            raise Refusal(_CODE)
    names = []; pending = [tree]
    while pending:
        node = pending.pop()
        if node.right is not None:
            operation = '' if node.operator is None else node.operator.string
            if operation == '**':
                _literal(node.right)
                pending.append(node.left)
            elif operation in ('', '*', '/'):
                pending.append(node.right); pending.append(node.left)
            else:
                raise Refusal('invalid_unit')
        elif node.operator is not None:
            raise Refusal('invalid_unit')
        elif node.left.type == _token.NAME:
            names.append(node.left.string)
        elif node.left.type != _token.NUMBER or _literal(node) != 1:
            raise Refusal('invalid_unit')
    single = tree
    if tree.right is not None and tree.operator is not None and tree.operator.string == '**' and _literal(tree.right) == 1:
        single = tree.left
    standalone = (single.right is None and single.operator is None and single.left.type == _token.NAME)
    return tuple(names), standalone


def _canonical_terms(container, registry):
    from pint.util import UnitsContainer
    if type(container) is not UnitsContainer or len(container) > MAX_GRAPH_REFERENCES:
        raise Refusal(_CODE)
    combined = {}
    for name, power in container.items():
        validate_name(name, _CODE); _number(power)
        canonical = name if name.startswith('[') else registry.get_name(name)
        validate_name(canonical, _CODE)
        combined[canonical] = _number(combined.get(canonical, 0) + power)
    return tuple(sorted((name, power) for name, power in combined.items() if power != 0))


def _closed_graph(registry, roots):
    from pint.facets.plain.definitions import ScaleConverter, UnitDefinition
    from pint.facets.nonmultiplicative.definitions import OffsetConverter
    from pint.delegates.txt_defparser.plain import UnitDefinition as ParsedDefinition
    nodes = {}; visiting = set(); references = len(roots)

    def visit(name):
        nonlocal references
        if name in visiting:
            raise Refusal(_CODE)
        if name in nodes:
            return
        if len(nodes) + len(visiting) >= MAX_GRAPH_NODES:
            raise Refusal(_CODE)
        visiting.add(name)
        definition = registry._units[name]
        if type(definition) not in (UnitDefinition, ParsedDefinition):
            raise Refusal(_CODE)
        converter = definition.converter
        if type(converter) not in (ScaleConverter, OffsetConverter):
            raise Refusal('unsupported_unit_converter')
        scale = _number(converter.scale, positive=True)
        offset = _number(converter.offset if type(converter) is OffsetConverter else 0.)
        reference = _canonical_terms(definition.reference, registry)
        references += len(reference)
        if references > MAX_GRAPH_REFERENCES:
            raise Refusal(_CODE)
        base = definition.is_base
        if type(base) is not bool:
            raise Refusal(_CODE)
        if not base:
            for child, _ in reference:
                visit(child)
        nodes[name] = dict(name=name, converter=type(converter).__name__, scale=scale,
                           offset=offset, is_base=base, reference=reference)
        visiting.remove(name)

    try:
        for name, _ in roots:
            visit(name)
        graph = tuple(nodes[name] for name in sorted(nodes))
        if primitive_bounds(graph, code=_CODE).json_bytes + 1 > MAX_OPERATION_BYTES:
            raise Refusal(_CODE)
        return graph
    finally:
        visit = None


def _qualify_raw_leaves(registry, guarded, weight=False):
    summary = {}; terms = 0
    for leaves, standalone in guarded:
        for leaf in leaves:
            terms += 1
            if terms > MAX_GRAPH_REFERENCES:
                raise Refusal(_CODE)
            canonical = registry.get_name(leaf)
            if canonical == '':
                continue
            graph = _closed_graph(registry, ((canonical, 1),))
            _derive(((canonical, 1),), ((canonical, 1),), graph)
            for node in graph:
                if node['converter'] == 'OffsetConverter' and (weight or not standalone):
                    raise Refusal('unsupported_offset_unit')
                name = node['name']
                if name not in summary:
                    if len(summary) >= MAX_GRAPH_NODES:
                        raise Refusal(_CODE)
                    terms += len(node['reference'])
                    if terms > MAX_GRAPH_REFERENCES:
                        raise Refusal(_CODE)
                    summary[name] = (node['converter'], len(node['reference']))
            del graph
            node = None


def _qualify_compute(source_unit, target_unit, context, weight):
    registry = context._registry_for_attempt()
    validate_unit(source_unit, 'invalid_unit'); validate_unit(target_unit, 'invalid_unit')
    if source_unit is None:
        if weight:
            return UnitOperation(None, 'dimensionless', 1., 0., None, (), ())
        if target_unit is not None:
            raise Refusal('missing_unit_assertion')
        return UnitOperation(None, None, 1., 0., None, None, ())
    _parser_profile(); _registry_preprocessors(registry)
    effective = source_unit if target_unit is None else target_unit
    guarded = (_guard_label(source_unit), _guard_label(effective))
    _qualify_raw_leaves(registry, guarded, weight)
    del guarded
    source = registry.parse_units(source_unit, as_delta=False)
    target = registry.parse_units(effective, as_delta=False)
    a = _canonical_terms(source._units, registry); b = _canonical_terms(target._units, registry)
    graph = _closed_graph(registry, a+b)
    scale, offset = _derive(a, b, graph)
    if weight and (offset != 0 or any(node['converter'] == 'OffsetConverter' for node in graph)):
        raise Refusal('unsupported_offset_unit')
    for value in (0., 1., -1., 1e6):
        expected = registry.Quantity(value, source).to(target).magnitude
        actual = scale * value + offset
        if type(expected) not in (int, float) or not math.isfinite(expected) or not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
            raise Refusal(_CODE)
    return UnitOperation(source_unit, target_unit, scale, offset, a, b, graph)


def _qualification_outcome(source_unit, target_unit, context, weight):
    import pint
    try:
        return True, _qualify_compute(source_unit, target_unit, context, weight)
    except Refusal as error:
        _detach_owned_error(error)
        return False, error
    except pint.errors.UndefinedUnitError as error:
        _detach_owned_error(error)
        return False, 'unknown_unit'
    except pint.errors.OffsetUnitCalculusError as error:
        _detach_owned_error(error)
        return False, 'unsupported_offset_unit'
    except (pint.errors.PintError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        _detach_owned_error(error)
        return False, _CODE
    except BaseException as error:
        _detach_owned_error(error)
        return False, error


def _qualification_result(outcome):
    if outcome[0]:
        return outcome[1]
    if type(outcome[1]) is str:
        raise Refusal(outcome[1])
    pending = [outcome[1]]
    del outcome
    raise pending.pop()


def qualify_conversion(source_unit, target_unit, *, context=None):
    """Private compiler seam; runtime/source/funding checks belong to the caller."""
    if context is None:
        with _StockUnitContext() as owned:
            return qualify_conversion(source_unit, target_unit, context=owned)
    if type(context) is not _StockUnitContext:
        raise Refusal(_CODE)
    context._begin_attempt()
    return _qualification_result(_qualification_outcome(source_unit, target_unit, context, False))


def qualify_weight_unit(unit, *, context=None):
    if context is None:
        with _StockUnitContext() as owned:
            return qualify_weight_unit(unit, context=owned)
    if type(context) is not _StockUnitContext:
        raise Refusal(_CODE)
    context._begin_attempt()
    return _qualification_result(_qualification_outcome(unit, 'dimensionless', context, True))


def _validated_buffer(buffer):
    if type(buffer) is not ArrayBuffer:
        raise Refusal('invalid_weights')
    try:
        dtype = object.__getattribute__(buffer, 'dtype')
        shape = object.__getattribute__(buffer, 'shape')
        data = object.__getattribute__(buffer, 'data')
    except AttributeError:
        raise Refusal('invalid_weights') from None
    info = _dtype_info(dtype, 'invalid_weights')
    if dtype != info[0] or type(shape) is not tuple or len(shape) > 16 or type(data) is not bytes:
        raise Refusal('invalid_weights')
    size = 1
    for length in shape:
        if type(length) is not int or not 1 <= length <= 67108864:
            raise Refusal('invalid_weights')
        if length > (SELECTED_NUMERIC_BYTES_LIMIT // 8) // size:
            raise Refusal('selected_numeric_bytes_limit')
        size *= length
    if len(data) != size * info[2]:
        raise Refusal('invalid_weights')
    return size


def _validated_operation(operation):
    if type(operation) is not UnitOperation:
        raise Refusal(_CODE)
    try:
        values = tuple(object.__getattribute__(operation, name) for name in _OPERATION_FIELDS)
    except AttributeError:
        raise Refusal(_CODE) from None
    _check_operation(*values)


def _require_same_operation(expected, actual):
    """Compare complete canonical operations at the enclosing semantic boundary.

    This comparator confers no source/runtime/stock authority. The caller must
    freshly qualify actual under that boundary before supplying it here.
    """
    _validated_operation(expected)
    _validated_operation(actual)
    if expected.to_json() != actual.to_json():
        raise Refusal(_CODE)
    return actual


def _validated_weight_operation(operation):
    _validated_operation(operation)
    if operation.target_unit != 'dimensionless' or operation.offset != 0:
        raise Refusal(_CODE)


def _validate_normalized(operation, buffer):
    _validated_weight_operation(operation)
    _validated_buffer(buffer)
    if buffer.dtype != 'float64':
        raise Refusal('invalid_weights')
    import numpy as np
    values = mask = None
    try:
        values = buffer.view()
        mask = np.isfinite(values)
        valid = bool(mask.all()); mask = None
        if not valid:
            raise Refusal('nonfinite_weight')
        mask = values < 0
        negative = bool(mask.any()); mask = None
        if negative:
            raise Refusal('negative_weight')
    finally:
        values = mask = None


@dataclass(frozen=True, slots=True, init=False)
class NormalizedWeights:
    operation: UnitOperation
    buffer: ArrayBuffer

    def __init__(self, operation, buffer):
        try:
            object.__getattribute__(self, 'operation')
        except AttributeError:
            pass
        else:
            raise Refusal('invalid_weights')
        _return_or_raise(_capture_owned(_validate_normalized, operation, buffer))
        object.__setattr__(self, 'operation', operation)
        object.__setattr__(self, 'buffer', buffer)

    @property
    def values(self):
        return self.buffer.view()


def _normalize_compute(buffer, operation):
    # Complete type/shape/float64-size qualification precedes any scientific use.
    _validated_buffer(buffer)
    _validated_weight_operation(operation)
    # The enclosing semantic pass already qualified/compared this operation.
    # Normalization consumes no Pint attempt and may run within its active pass.
    import numpy as np
    values = converted = mask = None
    try:
        values = buffer.view()
        mask = np.isfinite(values)
        valid = bool(mask.all()); mask = None
        if not valid:
            raise Refusal('nonfinite_weight')
        mask = values < 0
        negative = bool(mask.any()); mask = None
        if negative:
            raise Refusal('negative_weight')
        try:
            with np.errstate(over='raise', invalid='raise', divide='raise'):
                converted = values.astype('float64', copy=True)
                np.multiply(converted, operation.scale, out=converted)
        except FloatingPointError:
            raise ComputationError('numeric_overflow') from None
        mask = np.isfinite(converted)
        valid = bool(mask.all()); mask = None
        if not valid:
            raise ComputationError('numeric_overflow')
        output = ArrayBuffer('float64', converted.shape, converted.tobytes())
        converted = values = None
        # Final constructor masks start only after the mutable cast is gone.
        return NormalizedWeights(operation, output)
    finally:
        values = converted = mask = None


def normalize_weights(buffer, operation):
    """Private structural consumer; the caller freshly qualifies the operation."""
    return _return_or_raise(_capture_owned(_normalize_compute, buffer, operation))
