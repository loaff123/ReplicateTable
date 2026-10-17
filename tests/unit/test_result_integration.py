"""Integration intended reds over actual result/plan/source ownership.

No synthetic budget or result carrier is used. These controls require the
existing lexer and primitive decoder, original A/B/C closure, and actual
parser/adoption frame release. The explicit runtime fixture is inherited
ordering/schema instrumentation, not actual-runtime qualification.
"""
import gc
import json
import sys
import unittest
import weakref
from unittest.mock import patch

import replicatetable as rt
from replicatetable import codec, admission
from replicatetable.codec import canonical_bytes
from replicatetable.model import ArrayBuffer
from tests.unit.test_results import ResultCase
from tests.unit.test_reduce import dataset, recipe, column, stage


class ResultIntegrationTests(ResultCase):
    def capture_exception(self, function, *arguments):
        # Unlike assertRaises, this preserves the escaping traceback for the
        # owned-frame lifetime checks below.
        try:
            function(*arguments)
        except BaseException as error:
            return error
        self.fail('expected an escaping exception')

    def test_loader_uses_shared_scanner_and_one_full_primitive_decode(self):
        _, plan = self.direct_plan()
        value = self.direct_value(); raw = canonical_bytes(value)
        original_init = codec._Scanner.__init__
        original_loads = codec.json.loads
        scans = []; full_decodes = []
        def scan(scanner, *arguments, **keywords):
            scans.append(True)
            return original_init(scanner, *arguments, **keywords)
        def decode(text, *arguments, **keywords):
            if text.startswith('{'): full_decodes.append(True)
            return original_loads(text, *arguments, **keywords)
        with patch.object(codec._Scanner, '__init__', scan), \
             patch.object(codec.json, 'loads', decode), \
             patch.object(codec, 'strict_loads', side_effect=AssertionError('generic baseline used for result slots')):
            result = self.api('load_result')(raw, plan)
        self.assertEqual(scans, [True])
        self.assertEqual(full_decodes, [True])
        self.assertEqual(result.to_json(), raw)

    def test_decoded_key_limit_precedes_key_slice_and_full_parse(self):
        _, plan = self.direct_plan()
        # Both are 129 decoded ASCII bytes. The second is also beyond the
        # 770-byte raw-key ceiling, despite its small decoded representation.
        for key in (b'k' * 129, b'\\u006b' * 129):
            original = codec.json.loads
            def decode(text, *arguments, **keywords):
                if text.startswith('{') or (text.startswith('"') and len(text) > 130):
                    raise AssertionError('oversized result key reached decoding')
                return original(text, *arguments, **keywords)
            with self.subTest(escaped=key.startswith(b'\\')), patch.object(codec.json, 'loads', decode):
                self.refused('invalid_result', self.api('load_result'), b'{"'+key+b'":0}', plan)

    def test_escaped_scalar_widths_share_the_same_result_model_budget(self):
        label = 'é🙂\n"' * 40
        _, plan = self.compiled(dataset({'v': (('x',), [3.], 'float64', None)},
            {'x': ([label], '<U160')}), recipe(('x',)))
        value = dict(version=1, row_dims=['x'], units={'out': None}, support=[],
            rows=[dict(keys={'x': label}, values={'out': 3.}, reasons={'out': []})])
        utf8 = canonical_bytes(value)
        escaped = (json.dumps(value, ensure_ascii=True, sort_keys=True,
                              separators=(',', ':'))+'\n').encode('ascii')
        self.assertGreater(len(escaped), len(utf8))
        plain = self.api('load_result')(utf8, plan)
        other = self.api('load_result')(escaped, plan)
        self.assertEqual(plain.to_json(), other.to_json())
        self.assertEqual(other.rows[0].keys['x'], label)

    def test_caller_result_and_all_three_datasets_survive_full_decode(self):
        a, plan_a = self.direct_plan(); b, _ = self.direct_plan(); c, plan_c = self.direct_plan()
        caller = self.result(plan_c, self.direct_value())
        raw = canonical_bytes(self.direct_value())
        original = codec.json.loads; observed = []
        def decode(text, *arguments, **keywords):
            if text.startswith('{'):
                active = admission._ACTIVE.get()
                self.assertIs(active.plan, plan_a)
                self.assertIs(active.result, caller)
                self.assertEqual((active.required_dataset_count, active.distinct_dataset_count), (3, 3))
                for handle in (a._handle, b._handle, c._handle):
                    self.assertTrue(any(handle is known for known in active.datasets))
                observed.append(True)
            return original(text, *arguments, **keywords)
        with admission._required_inputs(plan=plan_a, snapshot=b, result=caller) as outer:
            with patch.object(codec.json, 'loads', decode):
                loaded = self.api('load_result')(raw, plan_a)
            self.assertIs(admission._ACTIVE.get(), outer)
            self.assertIs(loaded._plan, plan_a)
            # Serializing caller C must keep anchor A and the full original
            # closure; it cannot silently reanchor to C or discard B.
            self.assertEqual(caller.to_json(), raw)
            self.assertIs(admission._ACTIVE.get(), outer)
        self.assertEqual(observed, [True])
        self.assertIs(caller._plan, plan_c)

    def test_nested_call_cannot_replace_original_caller_result_slot(self):
        a, plan_a = self.direct_plan(); b, _ = self.direct_plan(); _, plan_c = self.direct_plan()
        caller = self.result(plan_c, self.direct_value())
        replacement = self.result(plan_a, self.direct_value())
        with admission._required_inputs(plan=plan_a, snapshot=b, result=caller) as outer:
            self.refused('invalid_plan_input', self.api('inspect_call_admission'),
                         plan_a, a, result=replacement)
            self.assertIs(admission._ACTIVE.get(), outer)
            self.assertIs(outer.result, caller)

    def test_parsed_forest_has_no_retained_helper_reference_after_adoption(self):
        _, plan = self.direct_plan()
        raw = canonical_bytes(self.direct_value())
        original = codec.json.loads; retained = []
        def decode(text, *arguments, **keywords):
            result = original(text, *arguments, **keywords)
            if text.startswith('{'): retained.append(result)
            return result
        enabled = gc.isenabled(); gc.disable()
        try:
            with patch.object(codec.json, 'loads', decode):
                result = self.api('load_result')(raw, plan)
            self.assertEqual(result.rows[0].values['out'], 4.)
            self.assertEqual(len(retained), 1)
            self.assertEqual(sys.getrefcount(retained[0]), 2)
            self.assertEqual(sys.getrefcount(retained[0]['rows']), 2)
            self.assertEqual(sys.getrefcount(retained[0]['rows'][0]), 2)
        finally:
            if enabled: gc.enable()

    def test_retained_refusal_releases_parsed_result_forest(self):
        _, plan = self.direct_plan()
        value = self.direct_value(); value['rows'][0]['keys']['x'] = 99
        raw = canonical_bytes(value)
        original = codec.json.loads; retained = []
        def decode(text, *arguments, **keywords):
            result = original(text, *arguments, **keywords)
            if text.startswith('{'): retained.append(result)
            return result
        enabled = gc.isenabled(); gc.disable()
        try:
            with patch.object(codec.json, 'loads', decode):
                error = self.capture_exception(self.api('load_result'), raw, plan)
            self.assertIsInstance(error, rt.Refusal)
            self.assertEqual(error.code, 'invalid_result')
            self.assertIsNotNone(error.__traceback__)
            self.assertIsNone(error.__cause__); self.assertIsNone(error.__context__)
            self.assertEqual(len(retained), 1)
            self.assertEqual(sys.getrefcount(retained[0]), 2)
            self.assertEqual(sys.getrefcount(retained[0]['rows']), 2)
        finally:
            if enabled: gc.enable()

    def test_retained_cancellation_keeps_identity_and_releases_parse_frames(self):
        _, plan = self.direct_plan(); raw = canonical_bytes(self.direct_value())
        original = codec.json.loads; retained = []; setters = []
        class Cancel(BaseException):
            def __setattr__(self, name, value):
                setters.append(name)
                return super().__setattr__(name, value)
        cancellation = Cancel('stop')
        def decode(text, *arguments, **keywords):
            result = original(text, *arguments, **keywords)
            if text.startswith('{'): retained.append(result)
            return result
        enabled = gc.isenabled(); gc.disable()
        try:
            with patch.object(codec.json, 'loads', decode), \
                 patch.object(self.api('RowRecord'), '__init__', side_effect=cancellation):
                caught = self.capture_exception(self.api('load_result'), raw, plan)
            self.assertIs(caught, cancellation)
            self.assertIsNotNone(cancellation.__traceback__)
            self.assertIsNone(cancellation.__cause__); self.assertIsNone(cancellation.__context__)
            self.assertEqual(setters, [])
            self.assertEqual(len(retained), 1)
            self.assertEqual(sys.getrefcount(retained[0]), 2)
        finally:
            if enabled: gc.enable()

    def detached_chunk_iterator(self):
        source, plan = self.direct_plan()
        reference = weakref.ref(source._handle)
        result = self.result(plan, self.direct_value())
        return result.iter_json_chunks(), reference

    def test_partial_chunk_iterator_borrows_one_result_and_close_releases_it(self):
        enabled = gc.isenabled(); gc.disable()
        try:
            iterator, reference = self.detached_chunk_iterator()
            self.assertIsNone(admission._ACTIVE.get())
            self.assertIsInstance(next(iterator), bytes)
            self.assertIsNone(admission._ACTIVE.get())
            self.assertIsNotNone(reference())
            # A suspended iterator leaves no active admission context behind.
            other, _ = self.direct_plan()
            self.assertIsNone(admission._ACTIVE.get())
            iterator.close()
            self.assertIsNone(reference())
            self.assertIsNone(admission._ACTIVE.get())
        finally:
            if enabled: gc.enable()

    def test_chunk_iterator_error_preserves_identity_and_releases_borrowed_result(self):
        import replicatetable._result as result_module
        writes = []
        class Cancel(BaseException):
            def __setattr__(self, name, value):
                writes.append(name)
                return super().__setattr__(name, value)
        cancellation = Cancel('stop')
        enabled = gc.isenabled(); gc.disable()
        try:
            iterator, reference = self.detached_chunk_iterator()
            next(iterator)
            def consume():
                for fragment in iterator:
                    self.assertIsNone(admission._ACTIVE.get())
            with patch.object(result_module, '_record_chunks', side_effect=cancellation):
                error = self.capture_exception(consume)
            self.assertIs(error, cancellation)
            self.assertIsNotNone(error.__traceback__)
            self.assertIsNone(error.__cause__); self.assertIsNone(error.__context__)
            self.assertEqual(writes, [])
            self.assertIsNone(reference())
            self.assertIsNone(admission._ACTIVE.get())
            iterator.close()
            self.direct_plan()
        finally:
            if enabled: gc.enable()

    def test_full_decode_cache_growth_refuses_before_final_adoption(self):
        import numpy as np
        ds = dataset({'v': (('x',), [2., 4.], 'float64', None)},
                     {'x': ([2, 1], 'int64')}).assign_coords(
                         y=('y', [1]), z=('z', [1]), q=('q', [1]))
        _, plan = self.compiled(ds, recipe(('x',)))
        raw = canonical_bytes(self.direct_value())
        original = codec.json.loads; changed = []
        def decode(text, *arguments, **keywords):
            parsed = original(text, *arguments, **keywords)
            if text.startswith('{'):
                # One actual benign owner is conservatively charged in each
                # of three known existing Index caches, without alias credit.
                owner = np.zeros(124*1024*1024, dtype='uint8')
                mask = owner[:1].view('bool')
                for name in ('y', 'z', 'q'):
                    index = ds._indexes[name].index
                    object.__getattribute__(index, '__dict__')['_cache']['_isnan'] = mask
                changed.append(True)
            return parsed
        with patch.object(codec.json, 'loads', decode), \
             patch.object(self.api('RowRecord'), '__init__',
                          side_effect=AssertionError('record adoption preceded the fresh guard')):
            error = self.capture_exception(self.api('load_result'), raw, plan)
        self.assertEqual(changed, [True])
        self.assertIsInstance(error, rt.Refusal)
        self.assertEqual(error.code, 'estimated_memory_limit')

    def test_unstarted_chunk_throw_releases_borrowed_result_with_traceback_retained(self):
        writes = []
        class Cancel(BaseException):
            def __setattr__(self, name, value):
                writes.append(name)
                return super().__setattr__(name, value)
        cancellation = Cancel('stop before first next')
        enabled = gc.isenabled(); gc.disable()
        try:
            iterator, reference = self.detached_chunk_iterator()
            error = self.capture_exception(iterator.throw, cancellation)
            self.assertIs(error, cancellation)
            self.assertIsNotNone(error.__traceback__)
            self.assertIsNone(error.__cause__); self.assertIsNone(error.__context__)
            self.assertEqual(writes, [])
            self.assertIsNone(reference())
            self.assertIsNone(admission._ACTIVE.get())
            iterator.close()
            self.direct_plan()
        finally:
            if enabled: gc.enable()

    def test_numeric_failure_tracebacks_do_not_retain_new_selected_buffers(self):
        class Cancel(BaseException):
            pass
        for overflow in (True, False):
            values = [1e308, 1e308] if overflow else [1., 3.]
            source, plan = self.compiled(dataset({'v': (('r',), values, 'float64', None)},
                {'r': ([0, 1], 'int64')}), recipe(columns=[column(stages=[stage()])]))
            retained = []; original = ArrayBuffer.__init__
            cancellation = Cancel('stop during record construction')
            def buffer_init(buffer, dtype, shape, data):
                original(buffer, dtype, shape, data)
                retained.append(data)
            enabled = gc.isenabled(); gc.disable()
            try:
                with patch.object(ArrayBuffer, '__init__', buffer_init):
                    if overflow:
                        error = self.capture_exception(self.api('execute'), plan, source)
                        self.assertIsInstance(error, rt.ComputationError)
                        self.assertEqual(error.code, 'numeric_overflow')
                    else:
                        with patch.object(self.api('SupportRecord'), '__init__', side_effect=cancellation):
                            error = self.capture_exception(self.api('execute'), plan, source)
                        self.assertIs(error, cancellation)
                self.assertIsNotNone(error.__traceback__)
                self.assertIsNone(error.__cause__); self.assertIsNone(error.__context__)
                self.assertTrue(retained)
                for raw in retained:
                    self.assertEqual(sys.getrefcount(raw), 3)
            finally:
                if enabled: gc.enable()


if __name__ == '__main__':
    unittest.main()
