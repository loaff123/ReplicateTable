"""Public eager-memory bundle transactions require real installed output."""
import importlib
import hashlib
import json
from pathlib import PosixPath
import tempfile
import threading
from unittest.mock import patch

from replicatetable.errors import Refusal
from replicatetable._bundle_models import BundleReceipt
from tests.unit.test_reduce import ReductionCase, dataset, recipe


class BundlePublicWriteTests(ReductionCase):
    def setUp(self):
        super().setUp()
        self.m = importlib.import_module('replicatetable.bundle')
        self.assertTrue(callable(getattr(self.m, 'write_bundle', None)),
                        'Public memory transaction is absent')
        temporary = tempfile.TemporaryDirectory(prefix='rt-public-bundle-', dir='/tmp')
        self.addCleanup(temporary.cleanup)
        self.directory = PosixPath(temporary.name)
        self.destination = self.directory / 'output.bundle'

    def simple(self):
        return self.run_case(dataset({'v': (('x',), [1., 2.], 'float64', None)},
            {'x': (['b', 'a'], '<U1')}), recipe(('x',)))

    def test_public_success_is_an_actual_installed_bundle_with_bound_receipt(self):
        _, plan, result = self.simple()
        receipt = self.m.write_bundle(plan, result, self.destination)
        self.assertIs(type(receipt), BundleReceipt)
        self.assertEqual(receipt.status, 'committed')
        self.assertFalse(receipt.interrupted_after_commit)
        self.assertTrue(self.destination.is_dir())
        self.assertEqual((self.destination/'result.json').read_bytes(), result.to_json())
        raw = (self.destination/'manifest.json').read_bytes()
        manifest = json.loads(raw)
        self.assertEqual(receipt.manifest_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(receipt.bundle_bytes, len(raw)+manifest['totals']['payload_bytes'])
        self.assertEqual(list(self.directory.iterdir()), [self.destination])

    def test_existing_destination_is_not_overwritten_and_error_has_outcome(self):
        self.destination.write_bytes(b'original destination')
        _, plan, result = self.simple()
        error = self.refused('output_exists', self.m.write_bundle, plan, result, self.destination)
        self.assertEqual(self.destination.read_bytes(), b'original destination')
        self.assertFalse(error.envelope.committed)
        self.assertIsNone(error.envelope.receipt)

    def test_memory_path_does_not_import_managed_signal_or_worker_policy(self):
        from replicatetable import _native_supervisor as supervisor
        _, plan, result = self.simple()
        errors = []
        values = []
        def run():
            try: values.append(self.m.write_bundle(plan, result, self.destination))
            except BaseException as error: errors.append(error)
        with patch.object(supervisor, '_enter_signal_policy', side_effect=AssertionError('memory native signal policy')):
            thread = threading.Thread(target=run)
            thread.start()
            thread.join(120)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(values), 1)
        self.assertTrue(self.destination.is_dir())

    def test_replay_mismatch_retains_independent_completed_checks(self):
        from replicatetable import load_result
        _, plan, result = self.simple()
        forged = load_result(result.to_json().replace(b'"out":1.0', b'"out":9.0'), plan)
        error = self.refused('result_replay_mismatch', self.m.write_bundle, plan, forged, self.destination)
        self.assertEqual(dict(error.envelope.checks), {'structure':'passed', 'source_binding':'passed',
            'runtime_binding':'passed', 'report':'passed', 'replay':'failed'})
        self.assertFalse(self.destination.exists())

    def test_runtime_failure_inside_replay_stays_runtime_failure(self):
        from replicatetable import _replay
        _, plan, result = self.simple()
        error = Refusal('runtime_changed')
        with patch.object(_replay, '_require_exact_replay', side_effect=error):
            observed = self.refused('runtime_changed', self.m.write_bundle, plan, result, self.destination)
        self.assertEqual(observed.envelope.checks['runtime_binding'], 'failed')
        self.assertEqual(observed.envelope.checks['structure'], 'passed')
        self.assertEqual(observed.envelope.checks['replay'], 'not_attempted')
        self.assertFalse(self.destination.exists())

    def test_postcommit_close_failure_keeps_installed_output_and_receipt(self):
        from replicatetable import _native_fs_generated as roots
        _, plan, result = self.simple()
        original = roots._close_generated_root
        def close(root):
            original(root)
            raise OSError('injected postcommit close failure')
        with patch.object(roots, '_close_generated_root', close):
            error = self.refused('io_error', self.m.write_bundle, plan, result, self.destination)
        self.assertTrue(error.envelope.committed)
        self.assertEqual(error.exit_code, 3)
        self.assertIs(type(error.envelope.receipt), BundleReceipt)
        self.assertEqual((self.destination/'result.json').read_bytes(), result.to_json())

    def test_cooperative_cancellation_before_install_has_no_destination(self):
        from replicatetable import _native_commit as commit
        _, plan, result = self.simple()
        original = commit._install_memory_bundle
        def cancelled(writer, prepared, outcome, budget):
            outcome.cancellation._latch(2)
            return original(writer, prepared, outcome, budget)
        with patch.object(commit, '_install_memory_bundle', cancelled):
            error = self.refused('interrupted', self.m.write_bundle, plan, result, self.destination)
        self.assertEqual(error.exit_code, 130)
        self.assertFalse(error.envelope.committed)
        self.assertFalse(self.destination.exists())

    def test_asynchronous_python_exception_after_real_commit_keeps_caller_exception(self):
        from replicatetable import _native_commit as commit
        _, plan, result = self.simple()
        original = commit._rename_noreplace
        expected = KeyboardInterrupt('caller interruption fixture')
        def interrupt(*arguments):
            self.assertEqual(original(*arguments), 0)
            raise expected
        with patch.object(commit, '_rename_noreplace', interrupt):
            with self.assertRaises(KeyboardInterrupt) as raised:
                self.m.write_bundle(plan, result, self.destination)
        self.assertIs(raised.exception, expected)
        self.assertEqual((self.destination/'result.json').read_bytes(), result.to_json())
