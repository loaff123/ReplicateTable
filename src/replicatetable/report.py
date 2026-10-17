"""Escaped report-v2 streams and a separately admitted bytes convenience API.

The writer consumes _iter_report without whole-report buffers. render_report
uses canonical Baseline admission with only caller M live, count then exact
bytearray+bytes under 2L<=2M+6B. Hashing ends before these buffers; fill never
re-enters admission/serializers. These routines do not perform source replay.
"""
import hashlib
import html
import json

from .codec import _chunks
from .errors import ComputationError
from ._bundle_formats import (_models, _bounded_chunks, _recipe_json_chunks,
    _plan_json_chunks, _source_json_chunks)
from ._result import _result_chunks, _effective
from ._resource_estimates import _EmissionBudget, REPORT_NOTICE, REASONS, SUPPORT_HEADERS
from . import resources as r

# Concatenation is the reviewed 1917-byte test golden. Runtime never reads it.
_STATIC = (
    b'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ReplicateTable report</title><style>body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17212b;background:#fff}h1,h2{line-height:1.2}section{margin:2rem 0}pre,th,td{white-space:pre-wrap;overflow-wrap:anywhere}pre{padding:1rem;background:#f3f5f7}table{border-collapse:collapse;font-size:.9rem}th,td{border:1px solid #ccd3da;padding:.4rem;text-align:left;vertical-align:top}.scroll{overflow:auto}caption{text-align:left;margin:.5rem 0}</style></head><body><h1>ReplicateTable report</h1>\n<section id="scope"><h2>Scope and assurance</h2><p>User-selected aggregations. Declared repetition does not establish independent observations. Bundle verification checks source/runtime binding and exact same-engine replay; not independent numerical proof or authenticity.</p><p>',
    b'</p></section>\n<section id="identity"><h2>Source and canonical hashes</h2><pre>',
    b'</pre></section>\n<section id="grain"><h2>Grain, repetition and units</h2><p>Row dimensions are ordered. key:NN identifies that position in row_dims and in the CSV schema. Declared repetition is listed in each column\'s broadcast array.</p><pre>',
    b'</pre></section>\n<section id="totals"><h2>Complete totals and reason counts</h2><pre>',
    b'</pre></section>\n<section id="table"><h2>Table preview</h2><p>Each value column is followed by its reason array. null means a missing or failed output.</p>',
    b'</section>\n',
    b'<section id="limits"><h2>Limits</h2><p>Previews contain at most 100 rows and 100 records per stage. Totals include omitted records. Exact types, logical names, units and nullability are in the CSV schemas. CSV strings are data, not formulas to execute. Rendering alone performs no source replay. Inputs must remain stable; matching runtime hashes are not whole-OS attestation.</p></section>\n</body></html>\n',
)


def _text(value):
    for character in value:
        yield html.escape(character, quote=False).encode('utf-8')


def _display_key(value):
    if type(value) is str:
        yield b'"'
        for character in value:
            # One codepoint only: at most a 12-byte surrogate-pair display,
            # never a Unicode scalar-label or whole-document encoding.
            token = '\\u0020' if character == ' ' else json.dumps(character, ensure_ascii=True)[1:-1]
            yield html.escape(token, quote=False).encode('ascii')
        yield b'"'
    else:
        yield repr(value).encode('ascii')


def _html_json(chunks):
    for fragment in chunks:
        # Canonical scalar streams emit complete UTF-8 characters, never split
        # them. Fixed punctuation/numeric tokens are also bounded tiny chunks.
        yield from _text(fragment.decode('utf-8'))


def _number(value):
    yield b'null' if value is None else repr(value).encode('ascii')


def _digest(chunks, *, final_lf=False):
    digest = hashlib.sha256()
    for fragment in chunks:
        digest.update(fragment)
    if final_lf:
        digest.update(b'\n')
    return digest.hexdigest()


def _hashes(plan, result):
    # Each hash/iterator frame ends before the next; no serializer/freeze or
    # plan projection is called. Only four fixed digest strings escape.
    return (_digest(_recipe_json_chunks(plan.recipe), final_lf=True),
            _digest(_plan_json_chunks(plan)),
            _digest(_result_chunks(result)),
            _digest(_chunks(plan.runtime), final_lf=True))


def _identity_chunks(plan, digests):
    yield b'{"plan_sha256":'
    yield from _chunks(digests[1])
    yield b',"recipe_sha256":'
    yield from _chunks(digests[0])
    yield b',"result_sha256":'
    yield from _chunks(digests[2])
    yield b',"runtime_sha256":'
    yield from _chunks(digests[3])
    yield b',"source":'
    yield from _source_json_chunks(plan.source)
    yield b'}'


def _grain_chunks(plan):
    yield b'{"columns":['
    for index, column in enumerate(plan.columns):
        if index:
            yield b','
        yield b'{"broadcast":['
        for position, dimension in enumerate(column['broadcast']):
            if position:
                yield b','
            yield from _chunks(f'key:{plan.recipe.row_dims.index(dimension):02d}')
        yield b'],"effective_unit":'
        yield from _chunks(_effective(column))
        yield b',"name":'
        yield from _chunks(column['name'])
        yield b'}'
    yield b'],"row_dims":'
    yield from _chunks(plan.recipe.row_dims)
    yield b'}'


def _column_counts(result, name):
    counts = [0, 0, 0]
    for row in result.rows:
        for reason in row.reasons[name]:
            counts[REASONS.index(reason)] += 1
    return tuple(counts)


def _stage_counts(result, stage):
    counts = [0, 0, 0]
    start = stage['support_start']
    for offset in range(start, start + stage['support_count']):
        for reason in result.support[offset].reasons:
            counts[REASONS.index(reason)] += 1
    return tuple(counts)


def _reason_entry(column, counts, stage=None):
    yield b'{"column":'
    yield from _chunks(column)
    yield b',"insufficient_count":'
    yield from _chunks(counts[1])
    yield b',"missing_values":'
    yield from _chunks(counts[0])
    if stage is not None:
        yield b',"stage":'
        yield from _chunks(stage)
    yield b',"zero_weight":'
    yield from _chunks(counts[2])
    yield b'}'


def _totals_chunks(plan, result):
    yield b'{"column_reasons":['
    for index, column in enumerate(plan.columns):
        if index:
            yield b','
        counts = _column_counts(result, column['name'])
        yield from _reason_entry(column['name'], counts)
        counts = None
    yield b'],"stage_reasons":['
    first = True
    for column in plan.columns:
        for stage in column['stages']:
            if not first:
                yield b','
            first = False
            counts = _stage_counts(result, stage)
            yield from _reason_entry(column['name'], counts, stage['name'])
            counts = None
    yield b'],"totals":{"rows":'
    yield from _chunks(len(result.rows))
    yield b',"support_records":'
    yield from _chunks(len(result.support))
    yield b'}}'


def _key_header(plan, name):
    yield from _text(name)
    yield b' ['
    yield from _text(plan.coordinates[name].dtype)
    yield b']'


def _table_headers(plan, stage):
    dims = plan.recipe.row_dims if stage is None else stage['support_dims']
    for name in dims:
        yield b'<th>'
        yield from _key_header(plan, name)
        yield b'</th>'
    if stage is None:
        for column in plan.columns:
            for _ in range(2):
                yield b'<th>'
                yield from _text(column['name'])
                yield b'</th>'
    else:
        for name in SUPPORT_HEADERS:
            yield b'<th>'
            yield from _text(name)
            yield b'</th>'


def _row_cells(plan, row):
    for name in plan.recipe.row_dims:
        yield b'<td>'
        yield from _display_key(row.keys[name])
        yield b'</td>'
    for column in plan.columns:
        yield b'<td>'
        yield from _number(row.values[column['name']])
        yield b'</td><td>'
        yield from _html_json(_chunks(row.reasons[column['name']]))
        yield b'</td>'


def _support_cells(stage, record):
    for name in stage['support_dims']:
        yield b'<td>'
        yield from _display_key(record.keys[name])
        yield b'</td>'
    for name in SUPPORT_HEADERS:
        yield b'<td>'
        if name == 'reasons':
            yield from _html_json(_chunks(record.reasons))
        else:
            yield from _number(getattr(record, name))
        yield b'</td>'


def _preview_table(plan, result, stage=None):
    yield b'<div class="scroll"><table><thead><tr>'
    yield from _table_headers(plan, stage)
    yield b'</tr></thead><tbody>'
    if stage is None:
        for offset in range(min(r.REPORT_PREVIEW_LIMIT, len(result.rows))):
            yield b'<tr>'
            yield from _row_cells(plan, result.rows[offset])
            yield b'</tr>'
    else:
        start = stage['support_start']
        for offset in range(start, start + min(r.REPORT_PREVIEW_LIMIT, stage['support_count'])):
            yield b'<tr>'
            yield from _support_cells(stage, result.support[offset])
            yield b'</tr>'
    yield b'</tbody></table></div>'


def _report_chunks(plan, result, digests):
    """Only borrowed models, fixed digests and scalar fragments; no admission."""
    yield _STATIC[0]
    yield from _text(REPORT_NOTICE)
    yield _STATIC[1]
    yield from _html_json(_identity_chunks(plan, digests))
    yield _STATIC[2]
    yield from _html_json(_grain_chunks(plan))
    yield _STATIC[3]
    yield from _html_json(_totals_chunks(plan, result))
    yield _STATIC[4]
    yield from _preview_table(plan, result)
    yield _STATIC[5]
    for ci, column in enumerate(plan.columns):
        for si, stage in enumerate(column['stages']):
            # Only validated bounded integer positions enter the attribute.
            yield f'<section id="support-c{ci:02d}-s{si:02d}"><h2>'.encode('ascii')
            yield from _text(column['name'])
            yield b' / '
            yield from _text(stage['name'])
            yield b'</h2>'
            yield from _preview_table(plan, result, stage)
            yield b'</section>\n'
    yield _STATIC[6]


def _report_budget(plan):
    return _EmissionBudget('report.html', 'report', plan.estimates['report_bytes'],
                           r.REPORT_BYTES_LIMIT, 3)


def _iter_report(plan, result):
    """Writer route: complete before install; no convenience output buffers."""
    from .admission import _required_inputs, _guard
    from .runtime import require_runtime
    _models(plan, result)
    with _required_inputs(plan=plan, result=result):
        _guard('serialize')
        require_runtime(plan.runtime)
        digests = _hashes(plan, result)
        yield from _bounded_chunks(_report_chunks(plan, result, digests), _report_budget(plan))
        _guard('serialize')
        require_runtime(plan.runtime)


def _collect_report(plan, result, digests, length, budget):
    output = bytearray(length)
    offset = 0
    for fragment in _bounded_chunks(_report_chunks(plan, result, digests), budget):
        end = offset + len(fragment)
        if end > length:
            raise ComputationError('resource_estimate_mismatch')
        output[offset:end] = fragment
        offset = end
    if offset != length:
        raise ComputationError('resource_estimate_mismatch')
    return bytes(output)


def _render_report(plan, result):
    from .admission import _required_inputs, _guard
    from .runtime import require_runtime
    _models(plan, result)
    with _required_inputs(plan=plan, result=result):
        # Genuine canonical Baseline, not an E_build-only reservation.
        _guard('serialize')
        require_runtime(plan.runtime)
        digests = _hashes(plan, result)
        budget = _report_budget(plan)
        length = 0
        for fragment in _bounded_chunks(_report_chunks(plan, result, digests), budget):
            length += len(fragment)
        fragment = None
        if 2*length > 2*plan.estimates['result_objects_bytes'] + 6*plan.estimates['result_json_bytes']:
            raise ComputationError('resource_estimate_mismatch')
        output = _collect_report(plan, result, digests, length, budget)
        # Actual helper return retires the fill iterator and mutable buffer.
        _guard('serialize')
        require_runtime(plan.runtime)
        return output


def render_report(plan, result):
    from .source import _owned_attempt, _raise_owned
    output, error = _owned_attempt(_render_report, plan, result)
    plan = result = None
    if error is not None:
        _raise_owned(error)
    return output
