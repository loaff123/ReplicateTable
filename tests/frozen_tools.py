"""Test-only provenance and historical-recipe adapter; no product imports."""
import copy
import hashlib
import json
from pathlib import Path


def verify_frozen(root, expected_manifest_sha256):
    root=Path(root)
    manifest_raw=(root/'freeze_sha256.json').read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != expected_manifest_sha256:
        raise ValueError('freeze manifest digest mismatch')
    manifest=json.loads(manifest_raw)
    # Both formats are envelopes, never flat filename-to-digest maps.
    artifacts=manifest['artifacts']
    expected_names=set(artifacts) | {'freeze_sha256.json'}
    actual_names={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual_names != expected_names:
        raise ValueError('frozen file membership mismatch')
    for relative, record in artifacts.items():
        raw=(root/relative).read_bytes()
        digest=record if type(record) is str else record['sha256']
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('artifact digest mismatch')
        if type(record) is dict and len(raw) != record['size_bytes']:
            raise ValueError('artifact length mismatch')
    return len(expected_names)


def _adapt(fixture):
    recipe=copy.deepcopy(fixture['recipe'])
    for column in recipe['columns']:
        for stage in column['stages']:
            if stage['op']=='weighted_mean' and 'weight_unit' not in stage:
                weight=fixture['data']['variables'][stage['weights']]
                if weight.get('units') is not None:
                    raise ValueError('adapter requires a verified unitless weight source')
                stage['weight_unit']=None
    return recipe


def _same_exact(left,right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return (list(left)==list(right) and
                all(_same_exact(left[key],right[key]) for key in left))
    if type(left) is list:
        return len(left)==len(right) and all(_same_exact(a,b) for a,b in zip(left,right))
    # JSON decimal signed zero should not silently change either.
    if type(left) is float:
        return left.hex()==right.hex()
    return left==right


def assert_adapter_diff(fixture, adapted):
    expected=_adapt(fixture)
    if not _same_exact(expected,adapted):
        raise ValueError('adapter changed something other than missing weight_unit:null')
    return sum(stage['op']=='weighted_mean' and 'weight_unit' not in stage
               for column in fixture['recipe']['columns'] for stage in column['stages'])


def adapt_legacy_recipe(fixture):
    """Return a fresh recipe; append only explicit historical null assertions."""
    result=_adapt(fixture)
    assert_adapter_diff(fixture,result)
    return result
