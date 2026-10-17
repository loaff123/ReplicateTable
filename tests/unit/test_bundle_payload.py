"""Supplemental bounded payload/typed duplication tests, never OS proof.

Removing exact canonical comparison, owning error cleanup, positional path
membership or aggregate byte checks must fail these tests. Fixture runtime
instrumentation is explicitly inherited from the real-source ReductionCase.
"""
import hashlib
import importlib
import importlib.util
import sys
from unittest.mock import patch

from replicatetable.errors import Refusal
from tests.unit.test_reduce import ReductionCase, dataset, recipe, column, stage


class PayloadTests(ReductionCase):
    def implementation(self):
        name = 'replicatetable._bundle_payload'
        self.assertIsNotNone(importlib.util.find_spec(name), 'owned bundle payload layer is absent')
        return importlib.import_module(name)

    def simple(self):
        return self.run_case(dataset({'v': (('x',), [1., 2.], 'float64', None)},
            {'x': (['b', 'a'], '<U1')}), recipe(('x',)))

    def test_plan_derives_exact_sorted_payload_members(self):
        module = self.implementation()
        _, plan, _ = self.run_case(dataset({'v': (('x', 'r'), [1., 2.], 'float64', None)},
            {'x': ([1], 'int64'), 'r': ([1, 2], 'int64')}),
            recipe(('x',), [column(stages=[stage()])]))
        self.assertEqual(tuple(module._payload_paths(plan)), ('plan.json', 'recipe.json',
            'report.html', 'result.json', 'schema.json', 'support/c00-s00.csv',
            'support/c00-s00.schema.json', 'table.csv'))
        for path in ('manifest.json', '../table.csv', 'support/c00-s01.csv',
                     'support/c0-s0.csv', 'other', 1, True):
            self.refused('invalid_bundle', module._member_budget, plan, path)

    def test_owned_stream_hashes_actual_complete_bytes_and_retires_models(self):
        module = self.implementation()
        _, plan, result = self.simple()
        iterator = module._MemberStream(plan, result, 'table.csv')
        raw = b''.join(iterator)
        self.assertEqual(raw, b'key:00,value:00,reasons:00\n"a",2.0,[]\n"b",1.0,[]\n')
        self.assertEqual(dict(iterator.counter), dict(sha256=hashlib.sha256(raw).hexdigest(),
                                                     size_bytes=len(raw)))
        self.assertIsNone(iterator._plan)
        self.assertIsNone(iterator._result)
        self.assertIsNone(iterator._inner)

    def test_every_payload_stream_matches_existing_canonical_member_bytes(self):
        module = self.implementation()
        _, plan, result = self.simple()
        from replicatetable._bundle_formats import _iter_table_csv, _iter_table_schema
        from replicatetable.report import _iter_report
        expected = {'plan.json': plan.to_json(), 'recipe.json': plan.recipe.to_json(),
                    'result.json': result.to_json(),
                    'table.csv': b''.join(_iter_table_csv(plan, result)),
                    'schema.json': b''.join(_iter_table_schema(plan)),
                    'report.html': b''.join(_iter_report(plan, result))}
        for path, raw in expected.items():
            self.assertEqual(b''.join(module._MemberStream(plan, result, path)), raw, path)

    def test_typed_comparison_preserves_endpoints_float32_and_quoted_labels(self):
        module = self.implementation()
        labels = ['', 'a"b', 'a,b', 'a\rb', 'a\nb', '<>&😀']
        _, plan, result = self.run_case(dataset({
            'v': (('x',), [-0., .1, 1., 2., float('nan'), 3.], 'float32', None),
            'i': (('x',), [-2**63, 2**63-1, 0, 1, 2, 3], 'int64', None),
            'u': (('x',), [2**64-1, 2**53+1, 0, 1, 2, 3], 'uint64', None)},
            {'x': (labels, '<U8')}), recipe(('x',), [column(), column('i', 'i'), column('u', 'u')]))
        raw = b''.join(module._MemberStream(plan, result, 'table.csv'))
        for stride in (1, 2, 7, 65536):
            matcher = module._MemberMatcher(plan, result, 'table.csv')
            for offset in range(0, len(raw), stride): matcher.feed(raw[offset:offset+stride])
            self.assertEqual(matcher.finish()['sha256'], hashlib.sha256(raw).hexdigest())
        for changed in (raw.replace(b'-0.0', b'0.0'), raw.replace(b'18446744073709551615', b'18446744073709551616'),
                        raw.replace(b'""', b'', 1), raw.replace(b'0.10000000149011612', b'0.1'),
                        raw.replace(b'\n', b'\r\n', 1)):
            matcher = module._MemberMatcher(plan, result, 'table.csv')
            self.refused('invalid_bundle', matcher.feed, changed)

    def test_matching_requires_full_document_no_trailer_and_exact_schema(self):
        module = self.implementation()
        _, plan, result = self.simple()
        for path in ('table.csv', 'schema.json'):
            raw = b''.join(module._MemberStream(plan, result, path))
            matcher = module._MemberMatcher(plan, result, path)
            matcher.feed(raw[:-1])
            self.refused('invalid_bundle', matcher.finish)
            matcher = module._MemberMatcher(plan, result, path)
            self.refused('invalid_bundle', matcher.feed, raw+b'\n')
        raw = b''.join(module._MemberStream(plan, result, 'schema.json'))
        matcher = module._MemberMatcher(plan, result, 'schema.json')
        self.refused('invalid_bundle', matcher.feed, raw.replace(b'<U1', b'<U2'))

    def test_report_mismatch_has_its_separate_finding(self):
        module = self.implementation()
        _, plan, result = self.simple()
        matcher = module._MemberMatcher(plan, result, 'report.html')
        self.refused('report_mismatch', matcher.feed, b'changed')

    def test_matcher_rejects_oversized_and_nonexact_fragment_before_allocation(self):
        module = self.implementation()
        _, plan, result = self.simple()
        for fragment in (b'a'*65537, bytearray(b'a'), 'a', None):
            matcher = module._MemberMatcher(plan, result, 'table.csv')
            self.refused('invalid_bundle', matcher.feed, fragment)

    def test_closed_or_failed_stream_cannot_report_a_complete_counter(self):
        module = self.implementation()
        _, plan, result = self.simple()
        iterator = module._MemberStream(plan, result, 'table.csv')
        next(iterator)
        iterator.close()
        self.refused('invalid_bundle', lambda: iterator.counter)
        self.assertIsNone(iterator._plan)
        self.assertIsNone(iterator._result)

    def test_prestart_throw_preserves_identity_and_releases_owned_models(self):
        module = self.implementation()
        _, plan, result = self.simple()
        iterator = module._MemberStream(plan, result, 'table.csv')
        error = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt) as caught: iterator.throw(error)
        self.assertIs(caught.exception, error)
        self.assertIsNone(iterator._plan)
        self.assertIsNone(iterator._result)
        self.assertIsNone(iterator._inner)

    def test_post_yield_and_final_guard_failure_retire_owned_iterator(self):
        module = self.implementation()
        _, plan, result = self.simple()
        iterator = module._MemberStream(plan, result, 'table.csv')
        error = Refusal('estimated_memory_limit')
        from replicatetable import admission
        original = admission._guard
        resumed = False
        def guard(*arguments, **keywords):
            if resumed: raise error
            return original(*arguments, **keywords)
        # Install before generator-local imports capture the guard. Trigger
        # only after a real emitted fragment, at the next final guard.
        with patch('replicatetable.admission._guard', new=guard):
            next(iterator)
            resumed = True
            with self.assertRaises(Refusal) as caught: list(iterator)
        self.assertIs(caught.exception, error)
        self.assertIsNone(iterator._plan)
        self.assertIsNone(iterator._result)
        self.assertIsNone(iterator._inner)

    def test_incomplete_counter_refusal_retires_models_even_when_error_is_retained(self):
        module = self.implementation()
        _, plan, result = self.simple()
        before_plan, before_result = sys.getrefcount(plan), sys.getrefcount(result)
        iterator = module._MemberStream(plan, result, 'table.csv')
        caught = None
        try: iterator.counter
        except Refusal as error: caught = error
        self.assertIsNotNone(caught)
        self.assertEqual(caught.code, 'invalid_bundle')
        self.assertIsNone(iterator._plan)
        self.assertIsNone(iterator._result)
        self.assertEqual(sys.getrefcount(plan), before_plan)
        self.assertEqual(sys.getrefcount(result), before_result)

    def test_retained_post_yield_cancellation_has_no_owned_model_or_context_links(self):
        module = self.implementation()
        _, plan, result = self.simple()
        from replicatetable import admission
        before_plan, before_result = sys.getrefcount(plan), sys.getrefcount(result)
        cancellation = KeyboardInterrupt()
        iterator = module._MemberStream(plan, result, 'table.csv')
        next(iterator)
        caught = None
        try: iterator.throw(cancellation)
        except BaseException as error: caught = error
        self.assertIs(caught, cancellation)
        self.assertIsNone(admission._ACTIVE.get())
        self.assertIsNone(caught.__context__)
        self.assertIsNone(caught.__cause__)
        self.assertEqual(sys.getrefcount(plan), before_plan)
        self.assertEqual(sys.getrefcount(result), before_result)

    def test_payload_ledger_requires_each_exact_member_once_and_hashes_bytes(self):
        module = self.implementation()
        _, plan, result = self.simple()
        ledger = module._PayloadLedger(plan)
        self.refused('invalid_bundle', ledger.payload_files)
        total = 0
        for path in module._payload_paths(plan):
            ledger.begin(path)
            raw = b''.join(module._MemberStream(plan, result, path))
            for offset in range(0, len(raw), 11): ledger.feed(raw[offset:offset+11])
            self.assertEqual(ledger.end()['sha256'], hashlib.sha256(raw).hexdigest())
            total += len(raw)
        self.assertEqual(len(ledger.payload_files()), 6)
        self.assertEqual(ledger.payload_bytes, total)
        self.refused('invalid_bundle', ledger.begin, 'table.csv')
        self.refused('invalid_bundle', ledger.begin, 'support')

    def test_aggregate_schema_and_stage_budgets_fail_before_counter_mutation(self):
        module = self.implementation()
        _, plan, _ = self.run_case(dataset({'v': (('r',), [1., 2.], 'float64', None)},
            {'r': ([1, 2], 'int64')}), recipe((), [column(stages=[stage()]),
                column('second', stages=[stage()])]))
        # Scalar-only arithmetic seam: this does not claim an emitted valid file.
        for paths, estimate in ((('schema.json', 'support/c00-s00.schema.json'), 'schema_json_bytes'),
                                (('support/c00-s00.csv', 'support/c01-s00.csv'), 'stage_csv_bytes')):
            ledger = module._PayloadLedger(plan)
            ledger.begin(paths[0])
            remaining = plan.estimates[estimate]
            while remaining:
                amount = min(65536, remaining)
                ledger.feed(b' '*amount)
                remaining -= amount
            ledger.end()
            ledger.begin(paths[1])
            before = ledger.payload_bytes
            error = self.refused('resource_estimate_mismatch', ledger.feed, b'x')
            self.assertEqual(error.exit_code, 3)
            self.assertEqual(ledger.payload_bytes, before)
