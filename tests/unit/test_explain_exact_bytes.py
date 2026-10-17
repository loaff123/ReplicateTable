"""Unchanged-cap explanation boundaries with explicit evidence scopes.

The skeleton case is a conservative scalar upper-bound proof, not a claim
that mutually inconsistent schema maxima form an admitted scientific model.
The byte case uses real eager sources, stock units, compile/execute/replay,
then separately checks the public standalone explanation constructor.
"""
import json
from unittest.mock import patch

from tests.unit.test_explain import ExplainCase, ASSURANCE, NOTICE
from tests.unit.test_reduce import dataset, recipe, column, stage


CAP = 8 * 1024 * 1024


def _string_bound(utf8_bytes):
    return 6 * utf8_bytes + 2


def _list_bound(count, child):
    return 2 + max(count - 1, 0) + count * child


def _map_bound(fields):
    return 2 + max(len(fields) - 1, 0) + sum(
        _string_bound(len(name.encode('utf-8'))) + 1 + child
        for name, child in fields.items())


def _repeated_map_bound(count, key, value):
    return 2 + max(count - 1, 0) + count * (key + 1 + value)


def _mandatory_skeleton_bound():
    """Exact J arithmetic over a componentwise superset; no output forest."""
    number = 32
    name = _string_bound(128)
    unit = _string_bound(512)
    names = _list_bound(16, name)
    numeric_dtype = _string_bound(7)
    coordinate_dtype = _string_bound(6)
    digest = _string_bound(64)
    reasons = 4 + sum(_string_bound(len(value)) for value in
                      ('missing_values', 'insufficient_count', 'zero_weight'))
    counters = dict(total=number, shown=number, truncated=5,
                    limit_omitted=number, byte_omitted=number)
    source = _map_bound(dict(kind=_string_bound(6), sha256=digest,
                            size_bytes=number))
    coordinate = _map_bound(dict(dtype=coordinate_dtype, length=number))
    coordinates = _repeated_map_bound(16, name, coordinate)
    key = _repeated_map_bound(16, name, _string_bound(4096))
    source_section = _map_bound(dict(counters, selection=_list_bound(16, number), cells=2))
    conversion = _map_bound(dict(source_unit=unit, target_unit=unit,
                                effective_unit=unit, scale=number, offset=number))
    weight = _map_bound(dict(source=name, dtype=numeric_dtype, dims=names,
                            source_unit=unit, unit=_string_bound(13),
                            scale=number, offset=number))
    stage_section = _map_bound(dict(counters, name=name, input_dims=names,
        dims=names, remaining_dims=names, op=_string_bound(13),
        missing=_string_bound(9), min_count=number, input_stage=number,
        support_start=number, records=2))
    stages = _list_bound(2, stage_section)
    col = _map_bound(dict(name=name, source=name, source_dtype=numeric_dtype,
        converted_dtype=numeric_dtype, output_dtype=numeric_dtype,
        input_dims=names, final_dims=names, broadcast=names,
        conversion=conversion, weight=weight, value=number, reasons=reasons,
        source_cells=source_section, stages=stages))
    columns = _list_bound(32, col)
    root = _map_bound(dict(version=number, source=source, recipe_sha256=digest,
        plan_sha256=digest, result_sha256=digest, runtime_sha256=digest,
        row_dims=names, key=key, coordinates=coordinates, limit=number,
        byte_truncated=5, assurance=_string_bound(512), notice=_string_bound(512),
        columns=columns))
    return dict(source=source, coordinate=coordinate, coordinates=coordinates,
        key=key, source_section=source_section, conversion=conversion,
        weight=weight, stage_section=stage_section, stages=stages,
        column=col, columns=columns, root_with_lf=root + 1)


def _json_size(value):
    """Independent test-only exact byte counter, without whole Unicode JSON."""
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True,
                              separators=(',', ':'), allow_nan=False)
    return 1 + sum(len(fragment.encode('utf-8')) for fragment in encoder.iterencode(value))


class ExplanationExactByteBoundaryTests(ExplainCase):
    def test_valid_mandatory_skeleton_has_finite_bound_below_eight_mib(self):
        self.assertLessEqual(len(ASSURANCE.encode('utf-8')), 512)
        self.assertLessEqual(len(NOTICE.encode('utf-8')), 512)
        bounds = _mandatory_skeleton_bound()
        self.assertEqual(bounds, dict(source=589, coordinate=145, coordinates=14673,
            key=405601, source_section=1041, conversion=9589, weight=16644,
            stage_section=38959, stages=77921, column=144979, columns=4639361,
            root_with_lf=5081142))
        self.assertLess(bounds['root_with_lf'], CAP)
        print('mandatory skeleton conservative J upper bound:', bounds['root_with_lf'],
              '; unchanged cap:', CAP, '; margin:', CAP - bounds['root_with_lf'])

    def _actual_trace(self, first_unit, second_unit, second_name, *, keep_bytes=False):
        """Return only output bytes/scalars after real source/model frames end."""
        labels = ['a' * 4095 + '1', 'a' * 4095 + '2']
        ds = dataset({'v': (('r', 's'), [1.] * 1000, 'float64', first_unit),
                      second_name: (('r', 's'), [1.] * 1000, 'float64', second_unit)},
                     {'r': (list(range(500)), 'int64'), 's': (labels, '<U4096')})
        rec = recipe(columns=[
            column('one', 'v', source_unit=first_unit, target_unit=first_unit,
                   stages=[stage(dims=('r', 's'))]),
            column('two', second_name, source_unit=second_unit, target_unit=second_unit,
                   stages=[stage(dims=('r', 's'))])])
        source, plan, result = self.run_case(ds, rec)
        constructed = 0
        original = self.e._source_cell
        def observe(*arguments):
            nonlocal constructed
            constructed += 1
            return original(*arguments)
        with patch.object(self.e, '_source_cell', observe):
            output = self.e.explain_row(plan, source, result, {}, limit=1000)
        sections = tuple((section['total'], section['shown'], section['limit_omitted'],
                          section['byte_omitted']) for col in output.columns
                         for section in (col['source_cells'],) + col['stages'])
        shown_cells = sum(col['source_cells']['shown'] for col in output.columns)
        self.assertEqual(constructed, shown_cells + 1)
        self.assertTrue(output.byte_truncated)
        raw = output.to_json()
        facts = dict(length=len(raw), sections=sections,
                     size_digits=len(str(output.source['size_bytes'])),
                     estimated_memory_bytes=plan.estimates['estimated_memory_bytes'])
        self.assertLessEqual(facts['estimated_memory_bytes'], 512 * 1024 * 1024)
        return (raw if keep_bytes else None), facts

    def test_actual_producer_and_standalone_exact_eight_mib_and_one_more(self):
        _, base = self._actual_trace('meter', 'meter', 'vv')
        self.assertEqual(base['sections'], ((1000, 1000, 0, 0), (1, 1, 0, 0),
                                           (1000, 984, 0, 16), (1, 0, 0, 1)))
        gap = CAP - base['length']
        # Four displayed raw-unit occurrences in column one, three in two.
        # Leading ASCII spaces are valid bounded stock-Pint unit spelling.
        choices = ((a, b) for a in range(508) for b in range(508) if 4*a + 3*b == gap)
        padding = next(choices, None)
        self.assertIsNotNone(padding, 'valid bounded unit padding cannot reach exact cap')
        a, b = padding
        first_unit, second_unit = ' ' * a + 'meter', ' ' * b + 'meter'
        self.assertLessEqual(len(first_unit), 512)
        self.assertLessEqual(len(second_unit), 512)
        raw, equal = self._actual_trace(first_unit, second_unit, 'vv', keep_bytes=True)
        self.assertEqual(equal['size_digits'], base['size_digits'])
        self.assertEqual(equal['sections'], base['sections'])
        self.assertEqual(equal['length'], CAP)
        # The helper has returned, so no Dataset/source/plan/result survives
        # into this separate standalone constructor check.
        value = json.loads(raw)
        raw = None
        self.assertEqual(_json_size(value), CAP)
        standalone = self.e.RowExplanation(**value)
        self.assertEqual(standalone._serialized_size, CAP)
        self.assertEqual(sum(map(len, standalone.iter_json_chunks())), CAP)
        value = standalone = None

        # Only the second measurement name gains one serialized metadata byte.
        # All changing identities remain fixed-width hashes. Its source-size
        # decimal width is explicitly checked, rather than assumed unchanged.
        raw, overflow = self._actual_trace(first_unit, second_unit, 'vvv', keep_bytes=True)
        self.assertEqual(overflow['size_digits'], equal['size_digits'])
        self.assertEqual(overflow['sections'], ((1000, 1000, 0, 0), (1, 1, 0, 0),
                                               (1000, 983, 0, 17), (1, 0, 0, 1)))
        value = json.loads(raw)
        raw = None
        section = value['columns'][1]['source_cells']
        # Restore the actual next physical cell in this genuine new source.
        # This is a valid locally coherent prefix under its own full hashes.
        section['cells'].append(dict(indices=[491, 1], labels=[491, 'a' * 4095 + '2'],
            raw=1., converted=1., raw_weight=None, normalized_weight=1., exclusion_reason=None))
        section['shown'] += 1
        section['byte_omitted'] -= 1
        self.assertEqual(_json_size(value), CAP + 1)
        adopted = False
        def forbidden_copy(*arguments, **keywords):
            nonlocal adopted
            adopted = True
            raise AssertionError('owned tree allocated before explanation byte cap')
        with patch.object(self.e, '_adopt_tree', forbidden_copy):
            self.refused('explanation_bytes_limit', self.e.RowExplanation, **value)
        self.assertFalse(adopted)
        print('genuine exact explanation byte boundary:', dict(base=base, equality=equal,
              first_byte_overflow=overflow, padding=padding, rejected_model_bytes=CAP + 1))
