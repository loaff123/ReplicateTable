"""Strict bundle-v2 manifest metadata over actual bounded payload counters.

Constructors establish structure and byte bindings only. They do not establish
file acquisition, unchanged witnesses, source replay, or successful installation.
"""
from .codec import OwnedMap, _chunks, exact_int
from .errors import Refusal
from .plan import _plan_exact
from ._result import _result_exact
from ._bundle_payload import _paths, _budget
from ._resource_estimates import _EmissionBudget, _check_emission, _digest_counter, ASSURANCE
from ._resource_inputs import _owned_map, _fields
from . import resources as r


_MANIFEST_FIELDS = ('assurance', 'bundle_format', 'files', 'formula_version',
    'plan_sha256', 'recipe_sha256', 'result_sha256', 'runtime', 'runtime_sha256',
    'source', 'totals', 'version')


def _actual_files(plan, files):
    _owned_map(files, maximum=r.BUNDLE_PAYLOAD_LIMIT, code='invalid_bundle')
    expected = 6 + 2*sum(len(column['stages']) for column in plan.columns)
    if len(files) != expected:
        raise Refusal('invalid_bundle')
    bundle = _EmissionBudget('bundle', 'bundle', plan.estimates['bundle_bytes'], r.BUNDLE_BYTES_LIMIT, 0)
    stage = _EmissionBudget('stage', 'bundle', plan.estimates['stage_csv_bytes'], r.BUNDLE_BYTES_LIMIT, 1)
    schemas = _EmissionBudget('schemas', 'bundle', plan.estimates['schema_json_bytes'], r.BUNDLE_BYTES_LIMIT, 2)
    payload = stage_bytes = schema_bytes = 0
    for path in _paths(plan):
        if path not in files:
            raise Refusal('invalid_bundle')
        entry = _fields(files[path], ('sha256', 'size_bytes'), 'invalid_bundle')
        _digest_counter(entry['sha256'])
        exact_int(entry['size_bytes'], 'invalid_bundle')
        budget = _budget(plan, path)
        size = _check_emission(0, entry['size_bytes'], budget)
        payload = _check_emission(payload, size, bundle)
        if budget.group == 1:
            stage_bytes = _check_emission(stage_bytes, size, stage)
        elif budget.group == 2:
            schema_bytes = _check_emission(schema_bytes, size, schemas)
    return payload


def _make_manifest_inner(plan, result, files):
    from .admission import _required_inputs, _guard
    from .report import _hashes
    _plan_exact(plan)
    _result_exact(result)
    with _required_inputs(plan=plan, result=result):
        _guard('serialize')
        payload = _actual_files(plan, files)
        hashes = _hashes(plan, result)
        for index, path in enumerate(('recipe.json', 'plan.json', 'result.json')):
            if files[path]['sha256'] != hashes[index]:
                raise Refusal('bundle_digest_mismatch')
        source = OwnedMap._from_checked((('kind', plan.source.kind),
            ('sha256', plan.source.sha256), ('size_bytes', plan.source.size_bytes)))
        totals = OwnedMap._from_checked((('payload_bytes', payload),
            ('rows', len(result.rows)), ('support_records', len(result.support))))
        manifest = OwnedMap._from_checked((('assurance', ASSURANCE),
            ('bundle_format', 'replicatetable-bundle-v2'), ('files', files),
            ('formula_version', 2), ('plan_sha256', hashes[1]),
            ('recipe_sha256', hashes[0]), ('result_sha256', hashes[2]),
            ('runtime', plan.runtime), ('runtime_sha256', hashes[3]),
            ('source', source), ('totals', totals), ('version', 2)))
        _guard('serialize')
        return manifest


def _make_manifest(plan, result, files):
    from .source import _owned_attempt, _raise_owned
    manifest, error = _owned_attempt(_make_manifest_inner, plan, result, files)
    plan = result = files = None
    if error is not None: _raise_owned(error)
    return manifest


def _manifest_budget(plan):
    return _EmissionBudget('manifest.json', 'metadata',
        plan.estimates['manifest_json_bytes'], r.METADATA_BYTES_LIMIT, 0)


def _manifest_chunks(plan, manifest):
    """Borrowed writer stream; the real writer owns close/error sanitation."""
    from .admission import _required_inputs, _guard
    _plan_exact(plan)
    _fields(manifest, _MANIFEST_FIELDS, 'invalid_bundle')
    with _required_inputs(plan=plan):
        _guard('serialize')
        budget = _manifest_budget(plan)
        count = 0
        for fragment in _chunks(manifest):
            count = _check_emission(count, len(fragment), budget)
            yield fragment
        _check_emission(count, 1, budget)
        yield b'\n'
        _guard('serialize')


def _dict_fields(value, fields):
    if type(value) is not dict or len(value) != len(fields):
        raise Refusal('invalid_bundle')
    if any(type(key) is not str or key not in fields for key in value):
        raise Refusal('invalid_bundle')
    return value


def _declared_files(parsed, actual):
    if type(parsed) is not dict or len(parsed) != len(actual):
        raise Refusal('invalid_bundle')
    for name, entry in actual.items():
        if name not in parsed:
            raise Refusal('invalid_bundle')
        declared = _dict_fields(parsed[name], ('sha256', 'size_bytes'))
        _digest_counter(declared['sha256'])
        exact_int(declared['size_bytes'], 'invalid_bundle')
        if declared['sha256'] != entry['sha256'] or declared['size_bytes'] != entry['size_bytes']:
            raise Refusal('bundle_digest_mismatch')


def _decode_manifest(raw, bound):
    from . import codec
    # The enclosing genuine canonical guard plus N<=manifest bound funds this
    # exact965N control decode inside transport_reserve_bytes. Its manifest N
    # is one of N_control's explicit alternatives. The codec's standalone guard
    # remains an additional check, not a replacement or a subtracted baseline.
    try:
        return codec.strict_loads(raw, limit=bound,
            object_limit=min(r.LOGICAL_JOURNEY_LIMIT, 320*len(raw)))
    except Refusal as error:
        if error.code == 'invalid_json':
            raise Refusal('invalid_bundle') from None
        raise


def _same_manifest_bytes(raw, manifest):
    offset = 0
    iterator = _chunks(manifest)
    try:
        for fragment in iterator:
            for byte in fragment:
                if offset == len(raw) or raw[offset] != byte:
                    raise Refusal('invalid_bundle')
                offset += 1
        if offset + 1 != len(raw) or raw[offset] != 10:
            raise Refusal('invalid_bundle')
    finally:
        iterator.close()


def _load_manifest_inner(raw, plan, result, files):
    from .admission import _required_inputs, _guard
    _plan_exact(plan)
    _result_exact(result)
    if type(raw) is not bytes:
        raise Refusal('invalid_bundle')
    with _required_inputs(plan=plan, result=result):
        _guard('serialize')
        _check_emission(0, len(raw), _manifest_budget(plan))
        # Independent actual file counters and hashes become expected values;
        # decoded declarations are never acquisition or size/hash authority.
        manifest = _make_manifest_inner(plan, result, files)
        parsed = _dict_fields(_decode_manifest(raw, plan.estimates['manifest_json_bytes']), _MANIFEST_FIELDS)
        _declared_files(parsed['files'], files)
        _dict_fields(parsed['totals'], ('rows', 'support_records', 'payload_bytes'))
        for value in parsed['totals'].values(): exact_int(value, 'invalid_bundle')
        _same_manifest_bytes(raw, manifest)
        return manifest


def _load_manifest(raw, plan, result, files):
    from .source import _owned_attempt, _raise_owned
    manifest, error = _owned_attempt(_load_manifest_inner, raw, plan, result, files)
    raw = plan = result = files = None
    if error is not None: _raise_owned(error)
    return manifest
