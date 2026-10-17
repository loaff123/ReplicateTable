"""Real eager-memory temporary stages; no mocked filesystem/commit success.

Runtime fixture instrumentation is inherited from ReductionCase. Separate exact
profile integration runs establish genuine runtime qualification.
"""
import gc
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import PosixPath
import tempfile
from unittest.mock import patch

from replicatetable import _native_fs_generated as roots
from replicatetable import _native_workspace as workspace
from replicatetable._native_budget_state import LogicalOnlyBudget, _CancellationState
from replicatetable._bundle_models import PreparedReceipt
from replicatetable.errors import Refusal
from tests.unit.test_reduce import ReductionCase, dataset, recipe, column, stage


class BundleTransactionTests(ReductionCase):
    def setUp(self):
        super().setUp()
        self.assertIsNotNone(importlib.util.find_spec('replicatetable.bundle'),
                             'Real temporary bundle orchestration is absent')
        self.m = importlib.import_module('replicatetable.bundle')
        self.assertTrue(callable(getattr(self.m, '_prepare_memory_bundle', None)))
        self.native = importlib.import_module('replicatetable._native_stage')
        temporary = tempfile.TemporaryDirectory(prefix='rt-bundle-', dir='/tmp')
        self.addCleanup(temporary.cleanup)
        self.directory = PosixPath(temporary.name)
        self.final = self.directory / 'output.bundle'
        self.budget = LogicalOnlyBudget(_CancellationState())
        self.root = roots._prepare_stage_root(self.final, (), self.budget)
        self.addCleanup(roots._close_generated_root, self.root)
        workspace._create_generated_root(self.root, self.budget)
        self.stage_path = self.directory / self.root.name

    def simple(self):
        return self.run_case(dataset({'v': (('x',), [1., 2.], 'float64', None)},
            {'x': (['b', 'a'], '<U1')}), recipe(('x',)))

    def prepare(self, plan, result):
        writer, prepared = self.m._prepare_memory_bundle(plan, result, self.root, self.budget)
        self.addCleanup(self.native._close_stage_writer, writer, quiet=True)
        return writer, prepared

    def assert_files(self, plan, result, prepared):
        from replicatetable._bundle_payload import _payload_paths, _MemberStream
        paths = tuple(_payload_paths(plan))
        actual = tuple(sorted(str(path.relative_to(self.stage_path))
            for path in self.stage_path.rglob('*') if path.is_file()))
        self.assertEqual(actual, tuple(sorted((*paths, 'manifest.json'))))
        manifest_bytes = (self.stage_path / 'manifest.json').read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertNotIn('manifest.json', manifest['files'])
        total = 0
        for path in paths:
            raw = (self.stage_path / path).read_bytes()
            self.assertEqual(raw, b''.join(_MemberStream(plan, result, path)), path)
            self.assertEqual(manifest['files'][path], dict(
                size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
            total += len(raw)
        self.assertEqual(manifest['totals']['payload_bytes'], total)
        self.assertEqual(prepared.output_bytes, total + len(manifest_bytes))
        self.assertEqual(prepared.manifest_sha256, hashlib.sha256(manifest_bytes).hexdigest())
        self.assertEqual(prepared.result_sha256, hashlib.sha256(result.to_json()).hexdigest())
        self.assertIs(type(prepared), PreparedReceipt)
        self.assertFalse(self.root.committed)
        self.assertFalse(self.final.exists())

    def test_zero_stage_genuine_write_seal_readback_replay_and_actual_counters(self):
        source, plan, result = self.simple()
        writer, prepared = self.prepare(plan, result)
        self.assert_files(plan, result, prepared)
        self.assertEqual(writer.current_fd, -1)
        self.assertEqual(writer.support_fd, -1)
        self.assertIsNotNone(self.root.sealed_witness)
        self.assertEqual(prepared.source, source.identity)

    def test_two_stages_use_positional_members_despite_logical_name_collisions(self):
        _, plan, result = self.run_case(dataset({'v': (('x', 'r', 's'),
            [1., 2., 3., 4.], 'float64', None)},
            {'x': (['support'], '<U8'), 'r': ([1, 2], 'int64'), 's': ([1, 2], 'int64')}),
            recipe(('x',), [column('manifest.json', stages=[
                stage('table.csv', ('r',)), stage('plan.json', ('s',), 'max')])]))
        writer, prepared = self.prepare(plan, result)
        self.assert_files(plan, result, prepared)
        self.assertEqual(len(tuple(self.stage_path.rglob('*'))), 12)

    def test_exact_int_endpoints_float32_signed_zero_and_quoted_labels(self):
        labels = ['', 'a"b', 'a,b', 'a\rb', 'a\nb', '😀']
        _, plan, result = self.run_case(dataset({
            'v': (('x',), [-0., .1, 1., 2., float('nan'), 3.], 'float32', None),
            'i': (('x',), [-2**63, 2**63-1, 0, 1, 2, 3], 'int64', None),
            'u': (('x',), [2**64-1, 2**53+1, 0, 1, 2, 3], 'uint64', None)},
            {'x': (labels, '<U8')}), recipe(('x',), [column(), column('i', 'i'), column('u', 'u')]))
        writer, prepared = self.prepare(plan, result)
        self.assert_files(plan, result, prepared)

    def test_manifest_is_created_last_and_all_current_readers_close_before_replay(self):
        from replicatetable import _replay
        _, plan, result = self.simple()
        opened = []
        original_open = self.native._open_stage_member
        original_replay = _replay._require_exact_replay
        writers = []
        def open_member(writer, path, cap, budget):
            opened.append(path)
            if not writers: writers.append(writer)
            return original_open(writer, path, cap, budget)
        def replay(actual_plan, actual_source, actual_result):
            self.assertIs(actual_source, plan._source)
            self.assertIs(actual_plan, plan)
            self.assertIs(actual_result, result)
            self.assertEqual(writers[0].current_fd, -1)
            self.assertIsNotNone(self.root.sealed_witness)
            self.assertEqual(opened[-1], 'manifest.json')
            return original_replay(actual_plan, actual_source, actual_result)
        with patch.object(self.native, '_open_stage_member', open_member), \
                patch.object(_replay, '_require_exact_replay', replay):
            self.prepare(plan, result)
        self.assertEqual(len(opened), 7)

    def test_writer_never_builds_full_serialized_models_or_report(self):
        import replicatetable as rt
        from replicatetable import report, codec
        _, plan, result = self.simple()
        with patch.object(type(plan), 'to_json', side_effect=AssertionError('whole plan')), \
                patch.object(type(result), 'to_json', side_effect=AssertionError('whole result')), \
                patch.object(type(result), 'to_dict', side_effect=AssertionError('result forest')), \
                patch.object(report, '_collect_report', side_effect=AssertionError('whole report')):
            self.prepare(plan, result)

    def test_coherent_caller_result_forgery_refuses_exact_replay(self):
        from replicatetable import load_result
        _, plan, result = self.simple()
        raw = result.to_json().replace(b'"out":1.0', b'"out":9.0')
        self.assertNotEqual(raw, result.to_json())
        forged = load_result(raw, plan)
        error = self.refused('result_replay_mismatch', self.m._prepare_memory_bundle,
                             plan, forged, self.root, self.budget)
        self.assertFalse(self.final.exists())
        self.assertFalse(self.root.committed)

    def test_mutation_after_original_seal_refuses_before_replay(self):
        original = self.native._seal_stage
        def mutate(writer, budget):
            seal = original(writer, budget)
            (self.stage_path / 'table.csv').write_bytes(b'changed\n')
            return seal
        _, plan, result = self.simple()
        with patch.object(self.native, '_seal_stage', mutate):
            self.refused('bundle_changed', self.m._prepare_memory_bundle,
                         plan, result, self.root, self.budget)
        self.assertFalse(self.final.exists())

    def test_primary_ledger_failure_survives_close_failure_and_retires_frames(self):
        from replicatetable import _bundle_payload
        _, plan, result = self.simple()
        error = Refusal('estimated_memory_limit')
        old_close = self.native._close_stage_writer
        closed = []
        def close(writer, *, quiet=False):
            old_close(writer, quiet=quiet)
            closed.append(writer)
            raise OSError('secondary close')
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            with patch.object(_bundle_payload._PayloadLedger, 'feed', side_effect=error), \
                    patch.object(self.native, '_close_stage_writer', close):
                try:
                    self.m._prepare_memory_bundle(plan, result, self.root, self.budget)
                except Refusal as caught:
                    observed = caught
                else:
                    self.fail('Expected the exact injected refusal')
            self.assertEqual(observed.code, 'estimated_memory_limit')
            self.assertIs(observed, error)
            self.assertEqual(len(closed), 1)
            self.assertTrue(closed[0].retired)
            self.assertIsNone(error.__context__)
            self.assertIsNone(error.__cause__)
            trace = error.__traceback__
            while trace:
                self.assertNotIn(trace.tb_frame.f_code.co_name,
                    ('_prepare_memory_inner', '_emit_validate_inner', '_write_member',
                     '_emit_member_inner', '_batch_chunks', '_partial_bytes'))
                if trace.tb_frame.f_code.co_filename.endswith('/bundle.py'):
                    for name, value in trace.tb_frame.f_locals.items():
                        self.assertNotIsInstance(value, (bytearray, memoryview))
                        self.assertIsNot(value, plan)
                        self.assertIsNot(value, result)
                trace = trace.tb_next
        finally:
            if was_enabled: gc.enable()

    def test_arbitrary_caller_cause_notes_survive_same_object_cleanup(self):
        _, plan, result = self.simple()
        expected = KeyboardInterrupt('caller primary')
        caller_cause = ValueError('unrelated caller cause')
        expected.__cause__ = caller_cause
        expected.add_note('caller-owned note')
        original = self.native._close_stage_writer
        def close(writer, *, quiet=False):
            original(writer, quiet=quiet)
            raise expected
        observed = None
        with patch.object(self.native, '_append_stage_member', side_effect=expected), \
                patch.object(self.native, '_close_stage_writer', close):
            try:
                self.m._prepare_memory_bundle(plan, result, self.root, self.budget)
            except KeyboardInterrupt as caught:
                observed = caught
        self.assertIs(observed, expected)
        self.assertIs(observed.__cause__, caller_cause)
        self.assertEqual(observed.__notes__, ['caller-owned note'])
        trace = observed.__traceback__
        while trace:
            self.assertNotIn(trace.tb_frame.f_code.co_name,
                ('_prepare_memory_inner', '_emit_validate_inner', '_emit_member_inner', '_batch_chunks'))
            trace = trace.tb_next

    def test_unrelated_caller_except_context_survives_arbitrary_append_interruption(self):
        _, plan, result = self.simple()
        expected = KeyboardInterrupt('caller interruption')
        try:
            raise ValueError('unrelated active caller context')
        except ValueError as caller_context:
            with patch.object(self.native, '_append_stage_member', side_effect=expected):
                try:
                    self.m._prepare_memory_bundle(plan, result, self.root, self.budget)
                except KeyboardInterrupt as observed:
                    self.assertIs(observed, expected)
                    self.assertIs(observed.__context__, caller_context)
                else:
                    self.fail('Expected caller interruption')
