"""Owned canonical member streams and bounded structural byte comparison.

These private objects never open, write, seal or install a file. Their counters
prove only bytes observed by this layer. Real filesystem authority, source/runtime
binding and exact source replay belong to their separately qualified owners.
"""
import hashlib

from .codec import OwnedMap, utf8_length
from .errors import Refusal
from .plan import _plan_exact
from ._result import _result_exact, _result_chunks
from ._bundle_formats import (_iter_table_csv, _iter_support_csv,
    _iter_table_schema, _iter_support_schema, _plan_json_chunks,
    _recipe_json_chunks)
from ._resource_estimates import _EmissionBudget, _check_emission, _stage_path
from . import resources as r


_ROOTS = ('plan.json', 'recipe.json', 'report.html', 'result.json',
          'schema.json', 'table.csv')


def _paths(plan):
    yield from _ROOTS[:5]
    for ci, column in enumerate(plan.columns):
        for si in range(len(column['stages'])):
            yield _stage_path(ci, si)
            yield _stage_path(ci, si, True)
    yield 'table.csv'


def _payload_paths(plan):
    _plan_exact(plan)
    return _paths(plan)


def _locate(plan, path):
    if type(path) is not str:
        raise Refusal('invalid_bundle')
    utf8_length(path, 'invalid_bundle', maximum=r.BUNDLE_PATH_BYTES_LIMIT)
    if path in _ROOTS:
        return None, None
    for ci, column in enumerate(plan.columns):
        for si in range(len(column['stages'])):
            if path == _stage_path(ci, si) or path == _stage_path(ci, si, True):
                return ci, si
    raise Refusal('invalid_bundle')


def _budget(plan, path):
    _locate(plan, path)
    if path == 'recipe.json':
        key, kind, cap, group = 'recipe_json_bytes', 'recipe', r.RECIPE_BYTES_LIMIT, 0
    elif path == 'plan.json':
        key, kind, cap, group = 'plan_json_bytes', 'metadata', r.METADATA_BYTES_LIMIT, 0
    elif path == 'result.json':
        key, kind, cap, group = 'result_json_bytes', 'bundle', r.BUNDLE_BYTES_LIMIT, 0
    elif path == 'report.html':
        key, kind, cap, group = 'report_bytes', 'report', r.REPORT_BYTES_LIMIT, 0
    elif path == 'table.csv':
        key, kind, cap, group = 'table_csv_bytes', 'bundle', r.BUNDLE_BYTES_LIMIT, 0
    elif path.endswith('.schema.json') or path == 'schema.json':
        key, kind, cap, group = 'schema_json_bytes', 'metadata', r.METADATA_BYTES_LIMIT, 2
    else:
        key, kind, cap, group = 'stage_csv_bytes', 'bundle', r.BUNDLE_BYTES_LIMIT, 1
    return _EmissionBudget(path, kind, min(plan.estimates[key], cap), cap, group)


def _member_budget(plan, path):
    _plan_exact(plan)
    return _budget(plan, path)


def _counter(digest, size):
    return OwnedMap._from_checked((('sha256', digest), ('size_bytes', size)))


def _member_chunks(plan, result, path):
    from .admission import _required_inputs, _guard
    _plan_exact(plan)
    _result_exact(result)
    ci, si = _locate(plan, path)
    with _required_inputs(plan=plan, result=result):
        _guard('serialize')
        if path == 'recipe.json':
            yield from _recipe_json_chunks(plan.recipe)
            yield b'\n'
        elif path == 'plan.json':
            yield from _plan_json_chunks(plan)
        elif path == 'result.json':
            yield from _result_chunks(result)
        elif path == 'table.csv':
            yield from _iter_table_csv(plan, result)
        elif path == 'schema.json':
            yield from _iter_table_schema(plan)
        elif path == 'report.html':
            from .report import _iter_report
            yield from _iter_report(plan, result)
        elif path.endswith('.schema.json'):
            yield from _iter_support_schema(plan, ci, si)
        else:
            yield from _iter_support_csv(plan, result, ci, si)
        _guard('serialize')


def _detach(error):
    BaseException.__traceback__.__set__(error, None)
    BaseException.__context__.__set__(error, None)
    BaseException.__cause__.__set__(error, None)


class _MemberStream:
    """One complete owned emission boundary, including an unstarted throw."""
    __slots__ = ('_plan', '_result', '_path', '_inner', '_budget', '_hash',
                 '_size', '_closed', '_counter')

    def __init_subclass__(cls, **keywords):
        raise TypeError('Member streams are final')

    def __init__(self, plan, result, path):
        from .model import _require_uninitialized
        _require_uninitialized(self, '_closed', 'invalid_bundle')
        self._plan = plan
        self._result = result
        self._path = path
        self._inner = self._budget = self._hash = self._counter = None
        self._size = 0
        self._closed = False

    def __iter__(self): return self
    def __next__(self): return _stream_call(self, 'next')
    def close(self): return _stream_call(self, 'close')
    def throw(self, error): return _stream_call(self, 'throw', error)

    @property
    def counter(self):
        return _stream_call(self, 'counter')


def _retire_stream(stream):
    inner = stream._inner
    stream._plan = stream._result = stream._inner = None
    stream._budget = stream._hash = stream._path = None
    stream._closed = True
    if inner is not None:
        inner.close()


def _drive_stream(stream, operation, error):
    try:
        if operation == 'counter':
            if stream._counter is None:
                raise Refusal('invalid_bundle')
            return stream._counter
        if operation == 'close':
            _retire_stream(stream)
            return None
        if operation == 'throw':
            if not isinstance(error, BaseException):
                raise TypeError('throw requires an exception instance')
            raise error
        if stream._closed:
            raise StopIteration
        if stream._inner is None:
            stream._budget = _member_budget(stream._plan, stream._path)
            stream._hash = hashlib.sha256()
            stream._inner = _member_chunks(stream._plan, stream._result, stream._path)
        try:
            fragment = next(stream._inner)
        except StopIteration:
            stream._counter = _counter(stream._hash.hexdigest(), stream._size)
            _retire_stream(stream)
            raise
        if type(fragment) is not bytes or len(fragment) > r.SERIAL_BUFFER_BYTES:
            raise Refusal('invalid_bundle')
        count = _check_emission(stream._size, len(fragment), stream._budget)
        stream._hash.update(fragment)
        stream._size = count
        return fragment
    except BaseException:
        try:
            _retire_stream(stream)
        except BaseException as cleanup:
            _detach(cleanup)
        raise


def _stream_call(stream, operation, error=None):
    from .source import _owned_attempt, _raise_owned
    value, failure = _owned_attempt(_drive_stream, stream, operation, error)
    stream = error = None
    if failure is not None:
        _raise_owned(failure)
    return value


class _MemberMatcher:
    """Canonical typed duplication without external field/record allocation."""
    __slots__ = ('_stream', '_pending', '_offset', '_code', '_closed', '_counter')

    def __init_subclass__(cls, **keywords):
        raise TypeError('Member matchers are final')

    def __init__(self, plan, result, path):
        from .model import _require_uninitialized
        _require_uninitialized(self, '_closed', 'invalid_bundle')
        if type(path) is not str:
            raise Refusal('invalid_bundle')
        self._stream = _MemberStream(plan, result, path)
        self._pending = None
        self._offset = 0
        self._code = 'report_mismatch' if path == 'report.html' else 'invalid_bundle'
        self._closed = False
        self._counter = None

    def feed(self, fragment):
        from .source import _owned_attempt, _raise_owned
        value, error = _owned_attempt(_drive_matcher, self, 'feed', fragment)
        self = fragment = None
        if error is not None: _raise_owned(error)
        return value

    def finish(self): return _matcher_call(self, 'finish')
    def close(self): return _matcher_call(self, 'close')
    def throw(self, error): return _matcher_call(self, 'throw', error)


def _retire_matcher(matcher):
    stream = matcher._stream
    matcher._stream = matcher._pending = None
    matcher._offset = 0
    matcher._closed = True
    if stream is not None:
        stream.close()


def _expected_fragment(matcher):
    while True:
        try:
            fragment = next(matcher._stream)
        except StopIteration:
            return None
        if fragment:
            return fragment


def _drive_matcher(matcher, operation, fragment):
    try:
        if operation == 'close':
            _retire_matcher(matcher)
            return None
        if operation == 'throw':
            if not isinstance(fragment, BaseException):
                raise TypeError('throw requires an exception instance')
            raise fragment
        if matcher._closed:
            raise Refusal('invalid_bundle')
        if operation == 'finish':
            if matcher._pending is not None or _expected_fragment(matcher) is not None:
                raise Refusal(matcher._code)
            counter = matcher._stream.counter
            matcher._counter = counter
            _retire_matcher(matcher)
            return counter
        if type(fragment) is not bytes or len(fragment) > r.SERIAL_BUFFER_BYTES:
            raise Refusal('invalid_bundle')
        for actual in fragment:
            if matcher._pending is None:
                matcher._pending = _expected_fragment(matcher)
                matcher._offset = 0
                if matcher._pending is None:
                    raise Refusal(matcher._code)
            if actual != matcher._pending[matcher._offset]:
                raise Refusal(matcher._code)
            matcher._offset += 1
            if matcher._offset == len(matcher._pending):
                matcher._pending = None
                matcher._offset = 0
        return None
    except BaseException:
        try:
            _retire_matcher(matcher)
        except BaseException as cleanup:
            _detach(cleanup)
        raise


def _matcher_call(matcher, operation, argument=None):
    from .source import _owned_attempt, _raise_owned
    value, error = _owned_attempt(_drive_matcher, matcher, operation, argument)
    matcher = argument = None
    if error is not None: _raise_owned(error)
    return value


class _PayloadLedger:
    """Finite before-write counters; no filesystem or structural authority."""
    __slots__ = ('_plan', '_files', '_member', '_member_hash', '_member_size',
                 '_stage_bytes', '_schema_bytes', '_payload_bytes', '_bundle',
                 '_stage_budget', '_schema_budget', '_expected_count',
                 '_manifest_counter', '_bundle_bytes')

    def __init_subclass__(cls, **keywords):
        raise TypeError('Payload ledgers are final')

    def __init__(self, plan):
        from .model import _require_uninitialized
        _require_uninitialized(self, '_plan', 'invalid_bundle')
        _plan_exact(plan)
        self._plan = plan
        self._files = []
        self._member = self._member_hash = None
        self._member_size = self._stage_bytes = self._schema_bytes = self._payload_bytes = 0
        self._bundle_bytes = 0
        self._manifest_counter = None
        self._expected_count = 6 + 2*sum(len(column['stages']) for column in plan.columns)
        self._bundle = _EmissionBudget('bundle', 'bundle', plan.estimates['bundle_bytes'], r.BUNDLE_BYTES_LIMIT, 0)
        self._stage_budget = _EmissionBudget('stage', 'bundle', plan.estimates['stage_csv_bytes'], r.BUNDLE_BYTES_LIMIT, 1)
        # The schema aggregate is capped by the bundle. Individual schemas have
        # their independent16MiB metadata cap; the group can contain65 schemas.
        self._schema_budget = _EmissionBudget('schemas', 'bundle', plan.estimates['schema_json_bytes'], r.BUNDLE_BYTES_LIMIT, 2)

    @property
    def payload_bytes(self): return self._payload_bytes

    def begin(self, path):
        if self._member is not None or type(path) is not str:
            raise Refusal('invalid_bundle')
        budget = _budget(self._plan, path)
        if any(stored == path for stored, _ in self._files):
            raise Refusal('invalid_bundle')
        self._member = budget
        self._member_hash = hashlib.sha256()
        self._member_size = 0

    def begin_manifest(self):
        self.payload_files()
        if self._manifest_counter is not None:
            raise Refusal('invalid_bundle')
        self._member = _EmissionBudget('manifest.json', 'metadata',
            self._plan.estimates['manifest_json_bytes'], r.METADATA_BYTES_LIMIT, 0)
        self._member_hash = hashlib.sha256()
        self._member_size = 0

    def feed(self, fragment):
        if self._member is None or type(fragment) is not bytes or len(fragment) > r.SERIAL_BUFFER_BYTES:
            raise Refusal('invalid_bundle')
        size = len(fragment)
        member = _check_emission(self._member_size, size, self._member)
        total = _check_emission(self._bundle_bytes, size, self._bundle)
        stage = self._stage_bytes
        schemas = self._schema_bytes
        if self._member.group == 1:
            stage = _check_emission(stage, size, self._stage_budget)
        elif self._member.group == 2:
            schemas = _check_emission(schemas, size, self._schema_budget)
        self._member_hash.update(fragment)
        self._member_size = member
        self._bundle_bytes = total
        if self._member.path != 'manifest.json':
            self._payload_bytes = total
        self._stage_bytes = stage
        self._schema_bytes = schemas

    def end(self):
        if self._member is None:
            raise Refusal('invalid_bundle')
        counter = _counter(self._member_hash.hexdigest(), self._member_size)
        if self._member.path == 'manifest.json':
            self._manifest_counter = counter
        else:
            self._files.append((self._member.path, counter))
        self._member = self._member_hash = None
        self._member_size = 0
        return counter

    def payload_files(self):
        if self._member is not None or len(self._files) != self._expected_count:
            raise Refusal('invalid_bundle')
        if type(self._files) is list:
            self._files.sort(key=lambda pair: pair[0])
            self._files = tuple(self._files)
        return OwnedMap._from_checked(self._files)

    def finish(self):
        files = self.payload_files()
        if self._manifest_counter is None:
            raise Refusal('invalid_bundle')
        complete = OwnedMap._from_checked(tuple(sorted(
            (*files.items(), ('manifest.json', self._manifest_counter)))))
        return OwnedMap._from_checked((('bundle_bytes', self._bundle_bytes),
            ('files', complete), ('manifest_bytes', self._manifest_counter['size_bytes']),
            ('payload_bytes', self._payload_bytes),
            ('rows', self._plan.estimates['output_rows']),
            ('support_records', self._plan.estimates['support_records'])))
