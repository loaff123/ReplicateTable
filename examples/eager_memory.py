"""Explicit pooling, source-bound results, saved models, report and row trace.

Run after installing ReplicateTable and its pinned dependencies:
    python examples/eager_memory.py [NEW_OUTPUT_DIRECTORY]

This uses only public eager-memory APIs. Ordinary Python writes loose exports;
it does not call the experimental atomic bundle filesystem backend.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import xarray as xr
import replicatetable as rt


def run(output_directory):
    # Each second replicate has one observed sample, while the first has three.
    # Pooling all observations gives15; equal weighting of replicate means gives20.
    values = np.array([[[10., 10., 10.], [30., np.nan, np.nan]],
                       [[110., 110., 110.], [130., np.nan, np.nan]]], dtype='float64')
    dataset = xr.Dataset(
        {'response': (('experiment', 'replicate', 'sample'), values)},
        coords=xr.Coordinates({
            'experiment': ('experiment', np.array(['a', 'b'], dtype='<U1')),
            'replicate': ('replicate', np.array([0, 1], dtype='int64')),
            'sample': ('sample', np.array([0, 1, 2], dtype='int64')),
        }, indexes={}),
    )

    def mean(name, dims):
        return {'name': name, 'dims': dims, 'op': 'mean', 'missing': 'skip', 'min_count': 1}

    def column(name, stages):
        return {'name': name, 'source': 'response', 'source_unit': None,
                'target_unit': None, 'broadcast': [], 'stages': stages}

    declaration = {'version': 1, 'row_dims': ['experiment'], 'columns': [
        column('pooled', [mean('all_samples', ['replicate', 'sample'])]),
        column('equal_replicate', [mean('within_replicate', ['sample']),
                                   mean('across_replicates', ['replicate'])]),
    ]}
    recipe = rt.parse_recipe(json.dumps(declaration).encode('utf-8'))
    source = rt.snapshot_dataset(dataset)
    plan = rt.compile_plan(source, recipe)
    result = rt.execute(plan, source)

    # Hand-derived expectations and ordinary xarray controls are explicit.
    expected = [(15.0, 20.0), (115.0, 120.0)]
    observed = [(row.values['pooled'], row.values['equal_replicate'])
                for row in result.iter_rows()]
    assert observed == expected
    pooled = dataset.response.mean(dim=['replicate', 'sample'], skipna=True)
    equal = dataset.response.mean(dim='sample', skipna=True).mean(dim='replicate', skipna=True)
    assert pooled.values.tolist() == [15.0, 115.0]
    assert equal.values.tolist() == [20.0, 120.0]

    saved_plan = plan.to_json()
    saved_result = result.to_json()
    reloaded_plan = rt.load_plan(saved_plan, source)
    reloaded_result = rt.load_result(saved_result, reloaded_plan)
    replayed = rt.execute(reloaded_plan, source)
    assert reloaded_result.to_json() == replayed.to_json() == saved_result

    report = rt.render_report(plan, result)
    explanation = rt.explain_row(plan, source, result, {'experiment': 'a'}, limit=20)
    trace = json.loads(explanation.to_json())
    assert {column['name']: column['value'] for column in trace['columns']} == {
        'pooled': 15.0, 'equal_replicate': 20.0,
    }

    # This is deliberately an ordinary, non-transactional export example.
    # Refuse an existing directory so running the demo cannot overwrite it.
    output_directory.mkdir(parents=True, exist_ok=False)
    for name, payload in (
        ('recipe.json', recipe.to_json()), ('plan.json', saved_plan),
        ('result.json', saved_result), ('report.html', report),
        ('explanation.json', explanation.to_json()),
    ):
        with (output_directory / name).open('xb') as stream:
            stream.write(payload)

    # The stored plan is bound to the original content, not only its shape.
    dataset['response'].values[0, 0, 0] = 11.0
    try:
        rt.execute(plan, source)
    except rt.Refusal as error:
        assert error.code == 'source_changed', error.code
    else:
        raise AssertionError('A changed source was accepted under its old plan')
    finally:
        dataset['response'].values[0, 0, 0] = 10.0

    print(json.dumps({
        'workflow': 'eager-memory compute/report/explain',
        'rows': [row.to_dict() for row in result.iter_rows()],
        'same_engine_saved_result_replay': True,
        'changed_source_rejected': True,
        'xarray_controls_match': True,
        'report': str(output_directory / 'report.html'),
        'experimental_bundle_backend_used': False,
        'assurance': 'Source-bound consistency; not independent numerical proof or authenticity.',
    }, sort_keys=True))
    # Reusable demonstration models let qualification test refusal boundaries
    # without repeating the complete scientific journey.
    return source, plan, result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', type=Path,
                        default=Path('replicatetable-example-output'),
                        help='New directory for five loose example exports; must not already exist')
    run(parser.parse_args().output)
