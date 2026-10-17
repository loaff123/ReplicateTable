"""Physical qualification of the reviewed format/report schedule.

These tests qualify concrete iterator headers and frame/exception retirement;
they are not whole-process RSS, native maximum-capacity or browser evidence.
The finite observer inspects only this test's owned generator stack and named
iterator fields, never arbitrary caller/source referents. Its own added frame
locals dictionaries are conservatively included in the observed headers.
"""
import hashlib
import importlib
import importlib.util
import sys
import types
from unittest.mock import patch

from tests.unit import test_bundle_formats as format_tests
from tests.unit.test_reduce import ReductionCase, dataset, recipe, column, stage


class FormatLifetimeTests(ReductionCase):
    result_case = format_tests.BundleFormatTests.result_case
    simple = format_tests.BundleFormatTests.simple

    def modules(self):
        for name in ('replicatetable._bundle_formats', 'replicatetable.report'):
            self.assertIsNotNone(importlib.util.find_spec(name), 'format/report implementation is absent')
        return (importlib.import_module('replicatetable._bundle_formats'),
                importlib.import_module('replicatetable.report'))

    def stack_headers(self, root):
        pending = [root]; seen = set(); total = 0
        while pending:
            generator = pending.pop()
            if id(generator) in seen:
                continue
            seen.add(id(generator))
            self.assertLessEqual(len(seen), 32)
            self.assertIs(type(generator), types.GeneratorType)
            total += sys.getsizeof(generator)
            frame = generator.gi_frame
            if frame is not None:
                total += sys.getsizeof(frame)
                local = frame.f_locals
                total += sys.getsizeof(local)
                # Closed finite iterator roles; other values are borrowed
                # admitted model/scalar fields, not hidden iterator registries.
                for name in ('chunks', 'fields', 'names'):
                    value = local.get(name)
                    if type(value) is types.GeneratorType:
                        pending.append(value)
            child = generator.gi_yieldfrom
            if type(child) is types.GeneratorType:
                pending.append(child)
        return total

    def test_combined_stream_headers_and_finite_scalar_ledger_fit_65536(self):
        formats, report = self.modules()
        plan, result = self.result_case(dataset({'v': (('x', 'r'), [1., 3., 5., 7.], 'float64', 'kg')},
            {'x': ([' a  b ', '<>&😀'], '<U30'), 'r': ([1, 0], 'int64')}),
            recipe(('x',), [column('n_valid', source_unit='kg', stages=[stage('stage')])]))
        # Four digests: C(4)+4*P(str64)=2560. List/tuple counts overlap<=2560.
        # One exact hash object<=1024, token/encoding<=2048, shallow scalar /
        # function/iterator remainder8192. Rounded total16384 is conservative.
        self.assertLessEqual(sys.getsizeof(hashlib.sha256()), 1024)
        maximum = 0
        streams = (formats._iter_table_csv(plan, result), formats._iter_support_csv(plan, result, 0, 0),
            formats._iter_table_schema(plan), formats._iter_support_schema(plan, 0, 0),
            formats._plan_json_chunks(plan), report._iter_report(plan, result))
        for stream in streams:
            try:
                for _ in stream:
                    maximum = max(maximum, self.stack_headers(stream))
            finally:
                stream.close()
        self.assertLessEqual(maximum + 16384, 65536, maximum)
        print('format/report observed generator+frame+observer-dict peak:', maximum,
              'finite scalar reserve:', 16384, 'combined:', maximum + 16384)

    def test_hash_once_then_fill_without_hash_or_admission_and_final_guard_after_return(self):
        _, report = self.modules(); plan, result = self.simple()
        from replicatetable import admission
        original_hashes = report._hashes
        original_collect = report._collect_report
        original_guard = admission._guard
        state = dict(hashes=0, filling=False, collect_returned=False, guards=0)

        def hashes(*arguments):
            self.assertFalse(state['filling'])
            state['hashes'] += 1
            return original_hashes(*arguments)

        def collect(*arguments):
            self.assertEqual(state['hashes'], 1)
            state['filling'] = True
            try:
                output = original_collect(*arguments)
            finally:
                state['filling'] = False
            state['collect_returned'] = True
            return output

        def guard(*arguments, **keywords):
            self.assertFalse(state['filling'])
            state['guards'] += 1
            if state['hashes']:
                self.assertTrue(state['collect_returned'])
            return original_guard(*arguments, **keywords)

        with patch.object(report, '_hashes', side_effect=hashes), \
             patch.object(report, '_collect_report', side_effect=collect), \
             patch.object(admission, '_guard', side_effect=guard):
            output = report.render_report(plan, result)
        self.assertIs(type(output), bytes)
        self.assertEqual((state['hashes'], state['guards']), (1, 2))
        self.assertTrue(state['collect_returned'])

    def test_partial_fill_cancellation_releases_owned_frames_and_preserves_exception(self):
        _, report = self.modules(); plan, result = self.simple()
        from replicatetable import admission
        original = report._report_chunks
        calls = 0
        cancellation = KeyboardInterrupt('owned report cancellation test')

        def chunks(*arguments):
            nonlocal calls
            calls += 1
            if calls == 2:
                yield b'<'
                raise cancellation
            yield from original(*arguments)

        before_plan = sys.getrefcount(plan)
        before_result = sys.getrefcount(result)
        caught = None
        with patch.object(report, '_report_chunks', new=chunks):
            try:
                report.render_report(plan, result)
            except BaseException as error:
                caught = error  # Keep the real escaping traceback untouched.
            else:
                self.fail('partial fill did not cancel')
        self.assertIs(caught, cancellation)
        self.assertEqual(calls, 2)
        self.assertIsNone(admission._ACTIVE.get())
        self.assertIsNone(cancellation.__context__)
        self.assertIsNone(cancellation.__cause__)
        self.assertEqual(sys.getrefcount(plan), before_plan)
        self.assertEqual(sys.getrefcount(result), before_result)
        traceback = cancellation.__traceback__
        while traceback is not None:
            self.assertNotIn(traceback.tb_frame.f_code.co_name,
                             ('_collect_report', '_render_report', '_report_chunks', 'chunks'))
            traceback = traceback.tb_next

    def test_closing_each_stream_retires_its_required_input_context(self):
        formats, report = self.modules(); plan, result = self.simple()
        from replicatetable import admission
        for stream in (formats._iter_table_csv(plan, result), formats._iter_table_schema(plan),
                       report._iter_report(plan, result)):
            self.assertIsNone(admission._ACTIVE.get())
            next(stream)
            self.assertIsNotNone(admission._ACTIVE.get())
            stream.close()
            self.assertIsNone(admission._ACTIVE.get())
