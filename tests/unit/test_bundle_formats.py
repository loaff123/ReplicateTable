"""Behavioral reds for typed, streaming bundle-v2 serialization.

Removing exact numeric tokens, positional headers, quote doubling, schema roles,
block offsets, per-fragment bounds or real result admission must fail these
checks. Sources/plans/results are genuine models; runtime fixture instrumentation
is inherited from ReductionCase and is not native/runtime qualification.
"""
import csv
import importlib
import importlib.util
import io
import json
from unittest.mock import patch

from replicatetable.codec import canonical_bytes
from replicatetable.errors import Refusal
from tests.unit.test_reduce import ReductionCase, dataset, recipe, column, stage


class BundleFormatTests(ReductionCase):
    def formats(self):
        name = 'replicatetable._bundle_formats'
        self.assertIsNotNone(importlib.util.find_spec(name), 'pure bundle formats are absent')
        return importlib.import_module(name)

    def result_case(self, ds, rec):
        source, plan = self.compiled(ds, rec)
        from replicatetable.reduce import execute
        return plan, execute(plan, source)

    def simple(self):
        return self.result_case(dataset({'v': (('x',), [1., 2.], 'float64', None)},
            {'x': (['b', 'a'], '<U1')}), recipe(('x',)))

    def test_positional_headers_preserve_all_colliding_logical_names(self):
        f = self.formats()
        columns = [column(name=n) for n in ('n_valid', 'stage', 'value', 'key:00')]
        plan, result = self.result_case(dataset({'v': (('n_valid',), [2], 'int64', None)},
            {'n_valid': ([7], 'int64')}), recipe(('n_valid',), columns))
        raw = b''.join(f._iter_table_csv(plan, result))
        self.assertEqual(raw, b'key:00,value:00,reasons:00,value:01,reasons:01,value:02,reasons:02,value:03,reasons:03\n7,2,[],2,[],2,[],2,[]\n')
        schema_raw = b''.join(f._iter_table_schema(plan))
        schema = json.loads(schema_raw)
        self.assertEqual(schema_raw, canonical_bytes(schema))
        self.assertEqual(set(schema), {'version', 'kind', 'row_dims', 'columns'})
        self.assertEqual(schema['row_dims'], ['n_valid'])
        self.assertEqual([v['name'] for v in schema['columns']],
                         ['n_valid', 'n_valid', 'n_valid', 'stage', 'stage', 'value', 'value', 'key:00', 'key:00'])
        self.assertEqual(schema['columns'][0], dict(position=0, header='key:00', role='key',
            name='n_valid', dtype='<i8', unit=None, nullable=False))

    def test_csv_keeps_int64_uint64_endpoints_and_float32_tokens(self):
        f = self.formats()
        plan, result = self.result_case(dataset({
            'i': (('x',), [-2**63, 2**63-1], 'int64', None),
            'u': (('x',), [2**64-1, 2**53+1], 'uint64', None),
            'v': (('x',), [-0., 0.1], 'float32', None)},
            {'x': ([2**64-1, 2**53+1], 'uint64')}),
            recipe(('x',), [column('i', 'i'), column('u', 'u'), column()]))
        lines = b''.join(f._iter_table_csv(plan, result)).decode().splitlines()
        self.assertEqual(lines[1], '9007199254740993,9223372036854775807,[],9007199254740993,[],0.10000000149011612,[]')
        self.assertEqual(lines[2], '18446744073709551615,-9223372036854775808,[],18446744073709551615,[],-0.0,[]')
        fields = json.loads(b''.join(f._iter_table_schema(plan)))['columns']
        self.assertEqual([fields[i]['dtype'] for i in (0, 1, 3, 5)], ['<u8', 'int64', 'uint64', 'float32'])
        self.assertEqual([fields[i]['nullable'] for i in (0, 1, 3, 5)], [False, False, False, True])

    def test_csv_quotes_strings_without_changing_empty_spaces_controls_or_unicode(self):
        f = self.formats()
        labels = ['', ' ', ' a  b ', 'a,b', 'a"b', 'a\rb', 'a\nb', 'a\tb', '<>&😀']
        plan, result = self.result_case(dataset({'v': (('x',), list(range(9)), 'int64', None)},
            {'x': (labels, '<U20')}), recipe(('x',)))
        fragments = tuple(f._iter_table_csv(plan, result))
        raw = b''.join(fragments)
        rows = list(csv.reader(io.StringIO(raw.decode(), newline='')))
        self.assertEqual([row[0] for row in rows[1:]], sorted(labels))
        self.assertIn(b'"",0,[]\n', raw)
        self.assertIn(b'" a  b "', raw)
        self.assertIn(b'"a""b"', raw)
        self.assertIn(b'"a\nb"', raw)
        self.assertNotIn(b'\\u0020', raw)
        self.assertLessEqual(max(map(len, fragments)), 32)

    def test_missing_float_uses_empty_field_and_canonical_reason_array(self):
        f = self.formats()
        plan, result = self.result_case(dataset({'v': (('x',), [float('nan'), -0.], 'float64', None)},
            {'x': ([1, 2], 'int64')}), recipe(('x',)))
        self.assertEqual(b''.join(f._iter_table_csv(plan, result)),
            b'key:00,value:00,reasons:00\n1,,"[""missing_values""]"\n2,-0.0,[]\n')

    def test_scalar_table_has_one_row_and_no_key_columns(self):
        f = self.formats()
        plan, result = self.result_case(dataset({'v': ((), [3], 'int64', None)}, {}), recipe())
        self.assertEqual(b''.join(f._iter_table_csv(plan, result)), b'value:00,reasons:00\n3,[]\n')
        self.assertEqual(json.loads(b''.join(f._iter_table_schema(plan)))['row_dims'], [])

    def test_support_block_uses_sorted_dimensions_and_exact_schema(self):
        f = self.formats()
        plan, result = self.result_case(dataset({'v': (('stage', 'n_valid', 'r'),
            list(range(8)), 'float64', 'kg')},
            {'stage': (['b', 'a'], '<U7'), 'n_valid': ([2, 1], 'int64'), 'r': ([0, 1], 'int64')}),
            recipe(('stage', 'n_valid'), [column('stage', source_unit='kg', stages=[stage('n_valid')])]))
        raw = b''.join(f._iter_support_csv(plan, result, 0, 0))
        self.assertTrue(raw.startswith(b'key:00,key:01,n_input,n_valid,n_positive_weight_valid,weight_total,weight_valid,reasons,value\n1,"a",2,2,2,2.0,2.0,[],6.5\n'))
        schema_raw = b''.join(f._iter_support_schema(plan, 0, 0))
        schema = json.loads(schema_raw)
        self.assertEqual(schema_raw, canonical_bytes(schema))
        self.assertEqual(set(schema), {'version', 'kind', 'column', 'stage', 'key_dims', 'unit', 'columns'})
        self.assertEqual((schema['column'], schema['stage'], schema['unit']), ('stage', 'n_valid', 'kg'))
        self.assertEqual(schema['key_dims'], ['n_valid', 'stage'])
        self.assertEqual([c['dtype'] for c in schema['columns']],
            ['<i8', '<U7', 'int64', 'int64', 'int64', 'float64', 'float64', 'reason-array', 'float64'])
        self.assertEqual([c['role'] for c in schema['columns']],
            ['key', 'key', 'count', 'count', 'count', 'weight', 'weight', 'reasons', 'value'])
        self.assertEqual([c['nullable'] for c in schema['columns']], [False]*8+[True])
        self.assertTrue(all(set(c) == {'position', 'header', 'role', 'name', 'dtype', 'nullable'} for c in schema['columns']))

    def test_stage_offsets_select_only_requested_column_and_stage(self):
        f = self.formats()
        plan, result = self.result_case(dataset({'v': (('r', 's'), [1., 3., 5., 7.], 'float64', None)},
            {'r': ([0, 1], 'int64'), 's': ([1, 0], 'int64')}),
            recipe((), [column('n_valid', stages=[stage('stage'), stage('value', ('s',))]),
                        column('stage', stages=[stage('n_valid', ('r', 's'), 'max')])]))
        raw = b''.join(f._iter_support_csv(plan, result, 0, 1))
        self.assertEqual(raw, b'n_input,n_valid,n_positive_weight_valid,weight_total,weight_valid,reasons,value\n2,2,2,2.0,2.0,[],4.0\n')
        raw = b''.join(f._iter_support_csv(plan, result, 1, 0))
        self.assertTrue(raw.endswith(b'4,4,4,4.0,4.0,[],7.0\n'))

    def test_weighted_support_emits_all_reasons_in_frozen_order(self):
        f = self.formats()
        plan, result = self.result_case(dataset({
            'v': (('r',), [float('nan'), 4.], 'float64', None),
            'w': (('r',), [0., 0.], 'float64', None)}, {'r': ([1, 2], 'int64')}),
            recipe((), [column(stages=[stage(op='weighted_mean', missing='propagate', min_count=2)])]))
        self.assertTrue(b''.join(f._iter_support_csv(plan, result, 0, 0)).endswith(
            b'2,1,0,0.0,0.0,"[""missing_values"",""insufficient_count"",""zero_weight""]",\n'))

    def test_formatters_do_not_call_whole_result_or_record_projection(self):
        f = self.formats(); plan, result = self.simple()
        from replicatetable._result import ComputationResult, RowRecord, SupportRecord
        with patch.object(ComputationResult, 'to_dict', side_effect=AssertionError('whole forest')), \
             patch.object(RowRecord, 'to_dict', side_effect=AssertionError('record projection')), \
             patch.object(SupportRecord, 'to_dict', side_effect=AssertionError('record projection')):
            self.assertTrue(b''.join(f._iter_table_csv(plan, result)))
            self.assertTrue(b''.join(f._iter_table_schema(plan)))

    def test_wrong_inputs_and_bool_stage_indices_refuse_before_emission(self):
        f = self.formats(); plan, result = self.simple()
        for bad in (None, object(), True):
            self.refused('invalid_plan_input', lambda: next(f._iter_table_csv(bad, result)))
            self.refused('invalid_result', lambda: next(f._iter_table_csv(plan, bad)))
        for ci, si in ((True, 0), (0, True), (-1, 0), (32, 0), (0, 2), (0, 0)):
            self.refused('invalid_bundle', lambda: next(f._iter_support_csv(plan, result, ci, si)))

    def test_each_emitted_file_is_below_existing_estimate(self):
        f = self.formats(); plan, result = self.simple()
        self.assertLessEqual(len(b''.join(f._iter_table_csv(plan, result))), plan.estimates['table_csv_bytes'])
        self.assertLessEqual(len(b''.join(f._iter_table_schema(plan))), plan.estimates['schema_json_bytes'])

    def test_fragment_budget_checks_equality_and_refuses_before_next_yield(self):
        f = self.formats()
        from replicatetable._resource_estimates import _EmissionBudget
        budget = _EmissionBudget('table.csv', 'bundle', 3, 10, 0)
        self.assertEqual(b''.join(f._bounded_chunks(iter((b'a', b'bc')), budget)), b'abc')
        fragments = f._bounded_chunks(iter((b'abc', b'd')), budget)
        self.assertEqual(next(fragments), b'abc')
        error = self.refused('resource_estimate_mismatch', next, fragments)
        self.assertEqual(error.exit_code, 3)
        hard = _EmissionBudget('report.html', 'report', 3, 3, 0)
        self.refused('report_bytes_limit', lambda: b''.join(f._bounded_chunks(iter((b'abcd',)), hard)))

    def test_borrowed_plan_walker_matches_canonical_bytes_without_projection(self):
        f = self.formats(); plan, _ = self.simple()
        expected = plan.to_json()
        from replicatetable.model import BoundPlan, Recipe
        with patch.object(BoundPlan, '_projection', side_effect=AssertionError('plan projection')), \
             patch.object(BoundPlan, 'to_json', side_effect=AssertionError('plan bytes')), \
             patch.object(BoundPlan, 'iter_json_chunks', side_effect=AssertionError('plan freeze')), \
             patch.object(Recipe, '_projection', side_effect=AssertionError('recipe projection')):
            self.assertEqual(b''.join(f._plan_json_chunks(plan)), expected)
