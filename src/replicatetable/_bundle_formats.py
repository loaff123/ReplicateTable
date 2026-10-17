"""Pure, bounded bundle-v2 field streams over genuine immutable models.

No file mutation, parser, replay or numerical proof is implemented here. A
consumer must exhaust/close these private iterators and enforce aggregate stage
CSV/schema/bundle counters. Each member has its own before-yield byte guard.
Canonical plan hashing borrows fields directly; it never freezes a third plan
forest when explicit plan A and result-plan C already occupy both Z roles.
"""
from .codec import _chunks, _string_chunks, exact_int
from .errors import Refusal
from .plan import _plan_exact
from ._result import _result_exact, _effective
from ._resource_estimates import (_EmissionBudget, _check_emission,
    _table_header_field, _support_header_field, _stage_path, SUPPORT_HEADERS)
from . import resources as r


def _models(plan, result):
    _plan_exact(plan)
    _result_exact(result)


def _stage(plan, column_index, stage_index):
    exact_int(column_index, 'invalid_bundle', maximum=31)
    exact_int(stage_index, 'invalid_bundle', maximum=1)
    if column_index >= len(plan.columns):
        raise Refusal('invalid_bundle')
    column = plan.columns[column_index]
    if stage_index >= len(column['stages']):
        raise Refusal('invalid_bundle')
    return column, column['stages'][stage_index]


def _bounded_chunks(chunks, budget):
    count = 0
    for fragment in chunks:
        if type(fragment) is not bytes:
            raise Refusal('invalid_bundle')
        count = _check_emission(count, len(fragment), budget)
        yield fragment


def _csv_string(value):
    yield b'"'
    for character in value:
        yield b'""' if character == '"' else character.encode('utf-8')
    yield b'"'


def _csv_number(value):
    if value is not None:
        yield repr(value).encode('ascii')


def _csv_reasons(reasons):
    if not reasons:
        yield b'[]'
        return
    yield b'"'
    for fragment in _chunks(reasons):
        yield fragment.replace(b'"', b'""')
    yield b'"'


def _csv_key(value):
    if type(value) is str:
        yield from _csv_string(value)
    else:
        yield from _csv_number(value)


def _header_chunks(names):
    for position, name in enumerate(names):
        if position:
            yield b','
        yield name.encode('ascii')
    yield b'\n'


def _table_csv_chunks(plan, result):
    dims = plan.recipe.row_dims
    yield from _header_chunks(_table_header_field(i, len(dims), len(plan.columns))
                              for i in range(len(dims) + 2*len(plan.columns)))
    for row in result.rows:
        position = 0
        for name in dims:
            if position:
                yield b','
            yield from _csv_key(row.keys[name])
            position += 1
        for column in plan.columns:
            if position:
                yield b','
            yield from _csv_number(row.values[column['name']])
            yield b','
            yield from _csv_reasons(row.reasons[column['name']])
            position += 2
        yield b'\n'


def _support_csv_chunks(plan, result, column, stage):
    dims = stage['support_dims']
    yield from _header_chunks(_support_header_field(i, len(dims))
                              for i in range(len(dims) + 7))
    start = stage['support_start']
    for offset in range(start, start + stage['support_count']):
        record = result.support[offset]
        position = 0
        for name in dims:
            if position:
                yield b','
            yield from _csv_key(record.keys[name])
            position += 1
        for name in SUPPORT_HEADERS:
            if position:
                yield b','
            if name == 'reasons':
                yield from _csv_reasons(record.reasons)
            else:
                yield from _csv_number(getattr(record, name))
            position += 1
        yield b'\n'


def _iter_table_csv(plan, result):
    from .admission import _required_inputs, _guard
    _models(plan, result)
    with _required_inputs(plan=plan, result=result):
        _guard('serialize')
        budget = _EmissionBudget('table.csv', 'bundle',
            plan.estimates['table_csv_bytes'], r.BUNDLE_BYTES_LIMIT, 0)
        yield from _bounded_chunks(_table_csv_chunks(plan, result), budget)
        _guard('serialize')


def _iter_support_csv(plan, result, column_index, stage_index):
    from .admission import _required_inputs, _guard
    _models(plan, result)
    column, stage = _stage(plan, column_index, stage_index)
    with _required_inputs(plan=plan, result=result):
        _guard('serialize')
        budget = _EmissionBudget(_stage_path(column_index, stage_index), 'bundle',
            plan.estimates['stage_csv_bytes'], r.BUNDLE_BYTES_LIMIT, 1)
        yield from _bounded_chunks(_support_csv_chunks(plan, result, column, stage), budget)
        _guard('serialize')


def _schema_field(position, header, role, name, dtype, nullable, *, table, unit=None):
    # Insertion order is canonical. One current field dictionary, never a schema
    # forest, is owned; its primitive children borrow admitted scalar strings.
    field = dict(dtype=dtype, header=header, name=name, nullable=nullable,
                 position=position, role=role)
    if table:
        field['unit'] = unit
    return field


def _table_fields(plan):
    dims = plan.recipe.row_dims
    for position, name in enumerate(dims):
        yield _schema_field(position, _table_header_field(position, len(dims), len(plan.columns)),
            'key', name, plan.coordinates[name].dtype, False, table=True)
    position = len(dims)
    for column in plan.columns:
        for role in ('value', 'reasons'):
            yield _schema_field(position, _table_header_field(position, len(dims), len(plan.columns)),
                role, column['name'], column['output_dtype'] if role == 'value' else 'reason-array',
                role == 'value' and column['output_dtype'].startswith('float'), table=True,
                unit=_effective(column) if role == 'value' else None)
            position += 1


def _support_fields(plan, stage):
    dims = stage['support_dims']
    for position, name in enumerate(dims):
        yield _schema_field(position, _support_header_field(position, len(dims)),
            'key', name, plan.coordinates[name].dtype, False, table=False)
    for index, name in enumerate(SUPPORT_HEADERS):
        yield _schema_field(len(dims) + index, name,
            'count' if index < 3 else 'weight' if index < 5 else name,
            name, 'int64' if index < 3 else 'reason-array' if name == 'reasons' else 'float64',
            name == 'value', table=False)


def _field_array(fields):
    yield b'['
    first = True
    for field in fields:
        if not first:
            yield b','
        first = False
        yield from _chunks(field)
        field = None  # Release the previous field before requesting the next.
    yield b']'


def _table_schema_chunks(plan):
    yield b'{"columns":'
    yield from _field_array(_table_fields(plan))
    yield b',"kind":"table","row_dims":'
    yield from _chunks(plan.recipe.row_dims)
    yield b',"version":2}\n'


def _support_schema_chunks(plan, column, stage):
    yield b'{"column":'
    yield from _chunks(column['name'])
    yield b',"columns":'
    yield from _field_array(_support_fields(plan, stage))
    yield b',"key_dims":'
    yield from _chunks(stage['support_dims'])
    yield b',"kind":"support","stage":'
    yield from _chunks(stage['name'])
    yield b',"unit":'
    yield from _chunks(_effective(column))
    yield b',"version":2}\n'


def _iter_table_schema(plan):
    from .admission import _required_inputs, _guard
    _plan_exact(plan)
    with _required_inputs(plan=plan):
        _guard('serialize')
        budget = _EmissionBudget('schema.json', 'metadata',
            min(plan.estimates['schema_json_bytes'], r.METADATA_BYTES_LIMIT), r.METADATA_BYTES_LIMIT, 2)
        yield from _bounded_chunks(_table_schema_chunks(plan), budget)
        _guard('serialize')


def _iter_support_schema(plan, column_index, stage_index):
    from .admission import _required_inputs, _guard
    _plan_exact(plan)
    column, stage = _stage(plan, column_index, stage_index)
    with _required_inputs(plan=plan):
        _guard('serialize')
        budget = _EmissionBudget(_stage_path(column_index, stage_index, True), 'metadata',
            min(plan.estimates['schema_json_bytes'], r.METADATA_BYTES_LIMIT), r.METADATA_BYTES_LIMIT, 2)
        yield from _bounded_chunks(_support_schema_chunks(plan, column, stage), budget)
        _guard('serialize')


def _source_json_chunks(identity):
    yield b'{"kind":'
    yield from _chunks(identity.kind)
    yield b',"sha256":'
    yield from _chunks(identity.sha256)
    yield b',"size_bytes":'
    yield from _chunks(identity.size_bytes)
    yield b'}'


def _recipe_json_chunks(recipe):
    yield b'{"columns":'
    yield from _chunks(recipe.columns)
    yield b',"row_dims":'
    yield from _chunks(recipe.row_dims)
    yield b',"version":1}'


def _plan_json_chunks(plan):
    """Internal canonical walker; callers already own exact admission/context.

    A and C may occupy both plan forests. These references and the current
    Coordinate are borrowed. No projection, freeze or wrapper forest exists.
    """
    yield b'{"columns":'
    yield from _chunks(plan.columns)
    yield b',"coordinates":{'
    for position, (name, coordinate) in enumerate(plan.coordinates.items()):
        if position:
            yield b','
        yield from _string_chunks(name)
        yield b':{"dtype":'
        yield from _chunks(coordinate.dtype)
        yield b',"sorted_indices":'
        yield from _chunks(coordinate.sorted_indices)
        yield b',"values":'
        yield from _chunks(coordinate.values)
        yield b'}'
    yield b'},"estimates":'
    yield from _chunks(plan.estimates)
    yield b',"formula_version":2,"recipe":'
    yield from _recipe_json_chunks(plan.recipe)
    yield b',"resource_binding":'
    yield from _chunks(plan.resource_binding)
    yield b',"runtime":'
    yield from _chunks(plan.runtime)
    yield b',"selected":'
    yield from _chunks(plan.selected)
    yield b',"source":'
    yield from _source_json_chunks(plan.source)
    yield b',"version":2}\n'
