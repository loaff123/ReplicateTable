"""Report-v2 intended reds: safe exact display, complete totals and bounded output.

These checks use real compiler/reducer/result interfaces with the same explicitly
instrumented runtime as ReductionCase. They do not establish browser QA, source
replay, native execution, practical maxima or scientific correctness.
"""
import hashlib
from html.parser import HTMLParser
import importlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from replicatetable.codec import canonical_bytes
from tests.unit import test_bundle_formats as format_tests
from tests.unit.test_reduce import ReductionCase, dataset, recipe, column, stage


class TextTree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []; self.tags = []; self.cells = []; self._cell = None
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if 'id' in dict(attrs): self.ids.append(dict(attrs)['id'])
        if tag in ('td', 'th'): self._cell = []
    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self._cell is not None:
            self.cells.append(''.join(self._cell)); self._cell = None
    def handle_data(self, value):
        if self._cell is not None: self._cell.append(value)


class ReportTests(ReductionCase):
    result_case = format_tests.BundleFormatTests.result_case
    simple = format_tests.BundleFormatTests.simple

    def report(self):
        name = 'replicatetable.report'
        self.assertIsNotNone(importlib.util.find_spec(name), 'static report renderer is absent')
        return importlib.import_module(name)

    def test_coordinate_display_is_ascii_json_with_every_space_visible(self):
        report = self.report()
        labels = ['', ' ', ' a  b ', 'a\tb', 'a\nb', 'a\rb', '<>&"\\😀']
        plan, result = self.result_case(dataset({'v': (('stage',), list(range(7)), 'int64', None)},
            {'stage': (labels, '<U30')}), recipe(('stage',)))
        raw = report.render_report(plan, result)
        parser = TextTree(); parser.feed(raw.decode())
        self.assertIn('stage [<U30]', parser.cells)
        expected = [json.dumps(value, ensure_ascii=True).replace(' ', '\\u0020') for value in sorted(labels)]
        self.assertEqual(parser.cells[3::3], expected)
        self.assertNotIn('😀', raw.decode())
        self.assertIn(b'&lt;&gt;&amp;', raw)
        self.assertNotIn(b'&quot;', raw)
        self.assertIn(b'\\ud83d\\ude00', raw)
        fragments = tuple(report._display_key('<>&"\\😀\t\n  '))
        self.assertLessEqual(max(map(len, fragments)), 12)
        self.assertEqual(b''.join(fragments).decode(), '"&lt;&gt;&amp;\\"\\\\\\ud83d\\ude00\\t\\n\\u0020\\u0020"')

    def test_signed_zero_and_exact_numeric_labels_are_visible(self):
        report = self.report()
        for labels, dtype, token in (([-0.], 'float64', '-0.0'),
                                     ([2**64-1], 'uint64', '18446744073709551615')):
            plan, result = self.result_case(dataset({'v': (('x',), [-0.], 'float32', None)},
                {'x': (labels, dtype)}), recipe(('x',)))
            parser = TextTree(); parser.feed(report.render_report(plan, result).decode())
            self.assertIn(token, parser.cells)
            self.assertIn('-0.0', parser.cells)

    def test_report_is_self_contained_escaped_and_has_exact_section_ids(self):
        report = self.report()
        plan, result = self.result_case(dataset({'v': (('r',), [2., 4.], 'float64', None)},
            {'r': ([0, 1], 'int64')}), recipe((), [column('<img src=x onerror=1>', stages=[stage('<script>')])]))
        raw = report.render_report(plan, result)
        parser = TextTree(); parser.feed(raw.decode())
        self.assertEqual(parser.ids, ['scope', 'identity', 'grain', 'totals', 'table', 'support-c00-s00', 'limits'])
        self.assertEqual(sum(tag == 'style' for tag, _ in parser.tags), 1)
        self.assertFalse(any(tag in ('script', 'img', 'iframe', 'form', 'link') for tag, _ in parser.tags))
        self.assertFalse(any(set(attrs) & {'src', 'href', 'onload', 'onclick', 'style'} for _, attrs in parser.tags))
        self.assertIn(b'&lt;img src=x onerror=1&gt;', raw)
        self.assertIn(b'&lt;script&gt;', raw)
        self.assertTrue(raw.startswith(b'<!doctype html>\n'))
        self.assertTrue(raw.endswith(b'</html>\n'))
        self.assertEqual(raw, report.render_report(plan, result))

    def test_hashes_are_canonical_and_no_whole_result_projection_is_used(self):
        report = self.report(); plan, result = self.simple()
        expected = [plan.source.sha256, hashlib.sha256(plan.recipe.to_json()).hexdigest(),
                    hashlib.sha256(plan.to_json()).hexdigest(),
                    hashlib.sha256(result.to_json()).hexdigest(),
                    hashlib.sha256(canonical_bytes(plan.runtime)).hexdigest()]
        from replicatetable._result import ComputationResult, RowRecord, SupportRecord
        with patch.object(ComputationResult, 'to_dict', side_effect=AssertionError('whole forest')), \
             patch.object(ComputationResult, 'to_json', side_effect=AssertionError('whole bytes')), \
             patch.object(RowRecord, 'to_dict', side_effect=AssertionError('row projection')), \
             patch.object(SupportRecord, 'to_dict', side_effect=AssertionError('support projection')):
            raw = report.render_report(plan, result)
        for digest in expected: self.assertIn(digest.encode(), raw)

    def test_full_reason_totals_include_omitted_preview_rows(self):
        report = self.report()
        plan, result = self.result_case(dataset({'v': (('x',), [1.]*100+[float('nan')], 'float64', None)},
            {'x': (list(range(101)), 'int64')}), recipe(('x',)))
        raw = report.render_report(plan, result)
        self.assertIn(b'"rows":101', raw)
        self.assertIn(b'"support_records":0', raw)
        self.assertIn(b'"missing_values":1', raw)
        parser = TextTree(); parser.feed(raw.decode())
        self.assertEqual(sum(tag == 'tr' for tag, _ in parser.tags), 101)  # header + 100 preview
        self.assertNotIn('100', parser.cells[3::3])

    def test_full_stage_reason_totals_include_omitted_support_records(self):
        report = self.report()
        plan, result = self.result_case(dataset({'v': (('x', 'r'), [1.]*100+[float('nan')], 'float64', None)},
            {'x': (list(range(101)), 'int64'), 'r': ([0], 'int64')}),
            recipe(('x',), [column(stages=[stage(min_count=2, missing='propagate')])]))
        raw = report.render_report(plan, result)
        self.assertIn(b'"support_records":101', raw)
        self.assertIn(b'"insufficient_count":101', raw)
        self.assertIn(b'"missing_values":1', raw)
        parser = TextTree(); parser.feed(raw.decode())
        self.assertEqual(sum(tag == 'tr' for tag, _ in parser.tags), 202)

    def test_grain_broadcast_units_and_missingness_are_explicit(self):
        report = self.report()
        plan, result = self.result_case(dataset({'v': ((), [float('nan')], 'float64', 'kg')},
            {'n_valid': ([' ', 'a'], '<U8')}),
            recipe(('n_valid',), [column('n_valid', source_unit='kg', broadcast=('n_valid',))]))
        raw = report.render_report(plan, result)
        self.assertIn(b'n_valid', raw)
        self.assertIn(b'"effective_unit":"kg"', raw)
        self.assertIn(b'"broadcast":["key:00"]', raw)
        self.assertIn(b'"row_dims":["n_valid"]', raw)
        self.assertIn(b'missing_values', raw)
        self.assertIn(b'>null</td>', raw)
        self.assertIn(b'Declared repetition', raw)

    def test_frozen_static_template_and_display_notice(self):
        report = self.report()
        actual = b''.join(report._STATIC)
        golden = Path(__file__).resolve().parents[1] / 'golden' / 'report-v2-static.html'
        self.assertTrue(golden.is_file(), 'reviewed static report golden is absent')
        self.assertEqual(actual, golden.read_bytes())
        self.assertLessEqual(len(actual), 32768)
        self.assertEqual(len(report.REPORT_NOTICE.encode()), 222)
        self.assertIn(b'not independent numerical proof', actual)
        self.assertIn(b'CSV strings are data', actual)

    def test_existing_result_envelope_dominates_both_report_buffers(self):
        report = self.report()
        names = tuple('&'*127+chr(65+i) for i in range(16))
        columns = [column('c'+str(i), broadcast=names) for i in range(32)]
        plan, result = self.result_case(dataset({'v': ((), [2.], 'float64', None)},
            {name: ([''], '<U1') for name in names}), recipe(names, columns))
        raw = report.render_report(plan, result)
        self.assertLessEqual(2*len(raw), 2*plan.estimates['result_objects_bytes']+6*plan.estimates['result_json_bytes'])
        self.assertLessEqual(len(raw), plan.estimates['report_bytes'])

    def test_wrong_result_or_mismatched_real_plan_refuses(self):
        report = self.report(); plan, result = self.simple()
        self.refused('invalid_plan_input', report.render_report, None, result)
        self.refused('invalid_result', report.render_report, plan, None)
        other, _ = self.result_case(dataset({'v': (('x',), [8., 9.], 'float64', None)},
            {'x': (['b', 'a'], '<U1')}), recipe(('x',)))
        self.refused('plan_binding_mismatch', report.render_report, other, result)

    def test_writer_iterator_streams_identical_bytes_without_output_buffer(self):
        report = self.report(); plan, result = self.simple()
        expected = report.render_report(plan, result)
        with patch.object(report, '_collect_report', side_effect=AssertionError('eager writer')):
            self.assertEqual(b''.join(report._iter_report(plan, result)), expected)
        self.assertLessEqual(sum(map(len, report._STATIC)), 2048)

    def test_distinct_matching_result_plan_uses_no_third_plan_forest(self):
        report = self.report(); plan, _ = self.simple(); other, result = self.simple()
        self.assertIsNot(plan, other)
        self.assertIs(result._plan, other)
        expected = report.render_report(plan, result)
        from replicatetable.model import BoundPlan
        with patch.object(BoundPlan, '_projection', side_effect=AssertionError('third plan projection')), \
             patch.object(BoundPlan, 'to_json', side_effect=AssertionError('whole plan bytes')), \
             patch.object(BoundPlan, 'iter_json_chunks', side_effect=AssertionError('third plan forest')):
            self.assertEqual(report.render_report(plan, result), expected)
