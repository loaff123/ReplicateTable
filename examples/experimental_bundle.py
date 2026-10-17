"""Run after installation with a qualified CPython profile on Linux 6.18.44 x86_64.

This example uses real runtime qualification. The final comparison is explicit
same-engine replay of the reloaded saved plan/result, not independent proof.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import numpy as np
import xarray as xr
import replicatetable as rt

values = np.array([[1., 3.], [4., 8.]], dtype='float64')
labels = np.array(['alpha', 'beta'], dtype='<U5')
replicates = np.array([1, 2], dtype='int64')
ds = xr.Dataset({'temperature': xr.Variable(('sample','replicate'), values, attrs={'units': None})},
    coords=xr.Coordinates({'sample': ('sample', labels), 'replicate': ('replicate', replicates)}, indexes={}))
source = rt.snapshot_dataset(ds)
recipe = rt.Recipe(1, ['sample'], [dict(name='mean', source='temperature', source_unit=None,
    target_unit=None, broadcast=[], stages=[dict(name='replicate mean', dims=['replicate'],
    op='mean', missing='skip', min_count=1)])])
plan = rt.compile_plan(source, recipe)
result = rt.execute(plan, source)
assert [row.values['mean'] for row in result.iter_rows()] == [2.0, 6.0]
with tempfile.TemporaryDirectory(prefix='replicatetable-memory-example-', dir='/tmp') as parent:
    destination = Path(parent) / 'results.bundle'
    receipt = rt.write_bundle(plan, result, destination)
    saved_plan = rt.load_plan((destination/'plan.json').read_bytes(), source)
    saved_result = rt.load_result((destination/'result.json').read_bytes(), saved_plan)
    replay = rt.execute(saved_plan, source)
    assert saved_result.to_json() == replay.to_json()
    verified = rt.verify_bundle(source, destination)
    assert verified.status == 'verified'
    assert all(state == 'passed' for state in verified.checks.values())
    actual = (destination/'manifest.json').read_bytes()
    assert hashlib.sha256(actual).hexdigest() == receipt.manifest_sha256
    print(json.dumps({'status': receipt.status, 'bundle_bytes': receipt.bundle_bytes,
                      'saved_result_rows': len(saved_result.rows),
                      'verification_status': verified.status,
                      'verification_checks': dict(verified.checks),
                      'exact_saved_result_replay': True,
                      'manifest_sha256': receipt.manifest_sha256}, sort_keys=True))
