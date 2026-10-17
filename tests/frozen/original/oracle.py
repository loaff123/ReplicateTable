"""Throwaway independent scalar/Fraction oracle for frozen ReplicateTable cases.

No array library, dataframe library, unit package, or candidate imports.
The fixed expected records were hand-authored before this evaluator.
Run `python oracle.py --verify` or `python oracle.py fixtures/F1.json`.
"""
from fractions import Fraction
from itertools import product
from pathlib import Path
import argparse
import hashlib
import json
import math


ROOT = Path(__file__).resolve().parent
# Deliberately finite and independent of the candidate's generic unit library.
FROZEN_CONVERSIONS = {
    (None, None): (Fraction(1), Fraction(0)),
    ('ms', 's'): (Fraction(1, 1000), Fraction(0)),
    ('degC', 'K'): (Fraction(1), Fraction(27315, 100)),
    ('ms', 'ms'): (Fraction(1), Fraction(0)),
    ('s', 's'): (Fraction(1), Fraction(0)),
    ('degC', 'degC'): (Fraction(1), Fraction(0)),
    ('K', 'K'): (Fraction(1), Fraction(0)),
}


def fraction_or_missing(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('non-numeric data in frozen input')
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return Fraction(str(value))


def typed_key(value):
    # In particular: no conversion of identifiers to float.
    return type(value).__name__, value


def mapping_key(keys):
    return tuple((name, typed_key(keys[name])) for name in sorted(keys))


def decode_variable(variable, coords, scale=Fraction(1), offset=Fraction(0)):
    dims = list(variable['dims'])
    grid = list(product(*(coords[dim] for dim in dims)))
    if len(grid) != len(variable['values']):
        raise ValueError('source length mismatch')
    cells = {}
    for key, value in zip(grid, variable['values']):
        value = fraction_or_missing(value)
        cells[key] = None if value is None else value * scale + offset
    return dims, cells


def scalar_sum(values):
    total = Fraction(0)
    for value in values:
        total += value
    return total


def reduce_stage(column_name, stage, dims, cells, coords, weight_source, unit):
    remaining = [dim for dim in dims if dim not in stage['dims']]
    output = {}
    output_reasons = {}
    records = []
    for remaining_key in product(*(coords[dim] for dim in remaining)):
        fixed = dict(zip(remaining, remaining_key))
        inputs = []
        weights = []
        for reduced_key in product(*(coords[dim] for dim in stage['dims'])):
            complete = dict(fixed)
            complete.update(zip(stage['dims'], reduced_key))
            inputs.append(cells[tuple(complete[dim] for dim in dims)])
            if weight_source is None:
                weights.append(Fraction(1))
            else:
                weight_dims, weight_cells = weight_source
                weight = weight_cells[tuple(complete[dim] for dim in weight_dims)]
                if weight is None or weight < 0:
                    raise ValueError('invalid weight in oracle input')
                weights.append(weight)
        n_input = len(inputs)
        valid = [(value, weight) for value, weight in zip(inputs, weights) if value is not None]
        n_valid = len(valid)
        n_positive = len([1 for value, weight in valid if weight > 0])
        weight_total = scalar_sum(weights)
        weight_valid = scalar_sum(weight for value, weight in valid)
        reasons = []
        if stage['missing'] == 'propagate' and n_valid < n_input:
            reasons.append('missing_values')
        if n_valid < stage['min_count']:
            reasons.append('insufficient_count')
        if stage['op'] == 'weighted_mean' and weight_valid == 0:
            reasons.append('zero_weight')
        if reasons:
            value = None
        elif stage['op'] in ('mean', 'weighted_mean'):
            value = scalar_sum(value * weight for value, weight in valid) / weight_valid
        elif stage['op'] == 'min':
            value = min(value for value, weight in valid)
        elif stage['op'] == 'max':
            value = max(value for value, weight in valid)
        else:
            raise ValueError('unsupported oracle operation')
        output[remaining_key] = value
        output_reasons[remaining_key] = reasons
        records.append({
            'column': column_name, 'stage': stage['name'], 'keys': fixed,
            'n_input': n_input, 'n_valid': n_valid,
            'n_positive_weight_valid': n_positive,
            'weight_total': weight_total, 'weight_valid': weight_valid,
            'reasons': reasons, 'value': value, 'unit': unit,
        })
    records.sort(key=lambda record: mapping_key(record['keys']))
    return remaining, output, output_reasons, records


def evaluate(fixture):
    data, recipe = fixture['data'], fixture['recipe']
    coords, variables = data['coords'], data['variables']
    row_dims = recipe['row_dims']
    if recipe['version'] != 1:
        raise ValueError('unsupported recipe version')
    for dim, values in coords.items():
        exact_values = [(type(value).__name__, value) for value in values]
        if len(exact_values) != len(set(exact_values)):
            raise ValueError('duplicate coordinate')
        if any(value is None for value in values):
            raise ValueError('missing coordinate')
    completed = {}
    units = {}
    support = []
    for column in recipe['columns']:
        source = variables[column['source']]
        unit = source['units']
        if unit is not None and column.get('source_unit') != unit:
            raise ValueError('source unit assertion mismatch')
        target = column.get('target_unit') or unit
        scale, offset = FROZEN_CONVERSIONS[(unit, target)]
        units[column['name']] = target
        dims, cells = decode_variable(source, coords, scale, offset)
        reasons = {key: [] for key in cells}
        for stage_index, stage in enumerate(column['stages']):
            if stage['missing'] not in ('skip', 'propagate'):
                raise ValueError('missing explicit valid missing policy')
            if type(stage['min_count']) is not int or stage['min_count'] < 1:
                raise ValueError('min_count must be integer >= 1')
            if not stage['dims'] or len(stage['dims']) != len(set(stage['dims'])):
                raise ValueError('invalid reduced dimensions')
            if not set(stage['dims']).issubset(dims):
                raise ValueError('stage reduces absent dimensions')
            weight_source = None
            if stage['op'] == 'weighted_mean':
                if stage_index != 0:
                    raise ValueError('only first-stage source weights supported')
                weight_source = decode_variable(variables[stage['weights']], coords)
                if not set(weight_source[0]).issubset(dims):
                    raise ValueError('weight dimensions must be subset of input')
            dims, cells, reasons, records = reduce_stage(
                column['name'], stage, dims, cells, coords, weight_source, target)
            support.extend(records)
        if not set(dims).issubset(row_dims):
            raise ValueError('residual dimension')
        if set(column['broadcast']) != set(row_dims) - set(dims):
            raise ValueError('unapproved or extraneous broadcast')
        completed[column['name']] = (dims, cells, reasons)
    rows = []
    grid = sorted(product(*(coords[dim] for dim in row_dims)),
                  key=lambda key: tuple(typed_key(value) for value in key))
    for row_key in grid:
        keys = dict(zip(row_dims, row_key))
        values = {}
        reasons = {}
        for column in recipe['columns']:
            name = column['name']
            dims, cells, cell_reasons = completed[name]
            key = tuple(keys[dim] for dim in dims)
            values[name] = cells[key]
            reasons[name] = cell_reasons[key]
        rows.append({'keys': keys, 'values': values, 'reasons': reasons})
    result = {'row_dims': row_dims, 'units': units, 'rows': rows, 'support': support}
    result['exact'] = {
        'rows': [{'keys': row['keys'], 'values': {name: rational(value) for name, value in row['values'].items()}} for row in rows],
        'support': [{'column': record['column'], 'stage': record['stage'], 'keys': record['keys'],
                     **{name: rational(record[name]) for name in ('weight_total', 'weight_valid', 'value')}}
                    for record in support],
    }
    for row in rows:
        row['values'] = {name: numeric(value) for name, value in row['values'].items()}
    for record in support:
        for name in ('weight_total', 'weight_valid', 'value'):
            record[name] = numeric(record[name])
    return result


def rational(value):
    return None if value is None else str(value)


def numeric(value):
    return None if value is None else float(value)


def verify():
    expected = json.loads((ROOT / 'frozen_expected.json').read_text())
    outputs = {}
    for path in sorted((ROOT / 'fixtures').glob('*.json')):
        fixture = json.loads(path.read_text())
        result = evaluate(fixture)
        assert result == expected['cases'][fixture['id']], 'frozen mismatch: ' + fixture['id']
        outputs[fixture['id']] = result
        print('PASS', fixture['id'], 'rows=' + str(len(result['rows'])), 'support=' + str(len(result['support'])))
    assert outputs['F1'] == outputs['F6'], 'replay differs'
    assert outputs['F5'] == outputs['F5_permuted'], 'permutation differs'
    assert outputs['F3']['rows'] == outputs['F3_scaled']['rows'], 'weight scaling changes values'
    for before, after in zip(outputs['F3']['support'], outputs['F3_scaled']['support']):
        ratio = 7 if before['stage'] != 'replicates' else 1
        for field in ('weight_total', 'weight_valid'):
            assert after[field] == before[field] * ratio, 'weight scaling support differs'
    manifest_path = ROOT / 'freeze_sha256.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for path, digest in manifest['artifacts'].items():
            actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            assert actual == digest, 'frozen artifact changed: ' + path
        print('PASS immutable artifact hashes:', len(manifest['artifacts']))
    print('PASS all frozen values, support, units, exact keys, rationals and metamorphic controls')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', nargs='?', type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        verify()
    elif args.fixture:
        print(json.dumps(evaluate(json.loads(args.fixture.read_text())), indent=2, allow_nan=False))
    else:
        parser.error('provide --verify or a fixture path')
