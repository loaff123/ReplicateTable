"""External eager-memory verification reads real installed/altered bundles."""
import hashlib
import importlib
import json
from pathlib import PosixPath
import tempfile
from unittest.mock import patch

import replicatetable as rt
from replicatetable._bundle_models import BundleVerification
from replicatetable.errors import Refusal
from tests.unit.test_reduce import ReductionCase, dataset, recipe


class BundleVerifyTests(ReductionCase):
    def setUp(self):
        super().setUp()
        self.m = importlib.import_module('replicatetable.bundle')
        self.assertTrue(callable(getattr(self.m, 'verify_bundle', None)),
                        'Public external memory bundle verification is absent')
        temporary = tempfile.TemporaryDirectory(prefix='rt-verify-', dir='/tmp')
        self.addCleanup(temporary.cleanup)
        self.directory = PosixPath(temporary.name)
        self.destination = self.directory/'output.bundle'
        self.source, self.plan, self.result = self.run_case(dataset(
            {'v': (('x',), [1., 2.], 'float64', None)},
            {'x': (['b', 'a'], '<U1')}), recipe(('x',)))
        self.receipt = self.m.write_bundle(self.plan, self.result, self.destination)

    def test_actual_saved_bundle_has_all_five_independent_checks_passed(self):
        report = self.m.verify_bundle(self.source, self.destination)
        self.assertIs(type(report), BundleVerification)
        self.assertEqual(report.status, 'verified')
        self.assertTrue(all(value == 'passed' for value in report.checks.values()))
        self.assertFalse(report.committed)
        self.assertIsNone(report.finding)
        self.assertEqual(report.source, self.source.identity)
        self.assertEqual(report.plan_sha256, self.receipt.plan_sha256)
        self.assertEqual(report.result_sha256, self.receipt.result_sha256)
        self.assertEqual(report.manifest_sha256, self.receipt.manifest_sha256)

    def test_plan_membership_rejects_extra_known_complete_support_pair(self):
        support = self.destination/'support'
        support.mkdir()
        (support/'c00-s00.csv').write_bytes(b'x\n')
        (support/'c00-s00.schema.json').write_bytes(b'{}\n')
        report = self.m.verify_bundle(self.source, self.destination)
        self.assertEqual(report.status, 'refused')
        self.assertEqual(report.finding['code'], 'invalid_bundle')
        self.assertEqual(report.checks['structure'], 'failed')
        self.assertEqual(report.checks['replay'], 'not_attempted')

    def mutate_report(self, coherent):
        path = self.destination/'report.html'
        path.write_bytes(path.read_bytes()+b'changed')
        if coherent:
            from replicatetable.codec import canonical_bytes
            manifest_path = self.destination/'manifest.json'
            manifest = json.loads(manifest_path.read_bytes())
            manifest['files']['report.html'] = {'size_bytes': path.stat().st_size,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            manifest['totals']['payload_bytes'] = sum(item['size_bytes'] for item in manifest['files'].values())
            manifest_path.write_bytes(canonical_bytes(manifest))

    def test_report_change_with_stale_digest_fails_structure(self):
        self.mutate_report(False)
        report = self.m.verify_bundle(self.source, self.destination)
        self.assertEqual(report.finding['code'], 'bundle_digest_mismatch')
        self.assertEqual(report.checks['structure'], 'failed')
        self.assertEqual(report.checks['report'], 'not_attempted')

    def test_coherent_report_digest_does_not_replace_regeneration(self):
        self.mutate_report(True)
        report = self.m.verify_bundle(self.source, self.destination)
        self.assertEqual(report.finding['code'], 'report_mismatch')
        self.assertEqual(report.checks['structure'], 'passed')
        self.assertEqual(report.checks['report'], 'failed')
        self.assertEqual(report.checks['replay'], 'not_attempted')

    def test_coherent_result_files_manifest_and_report_still_require_replay(self):
        from replicatetable._bundle_payload import _MemberStream, _payload_paths, _PayloadLedger
        from replicatetable._bundle_manifest import _make_manifest, _manifest_chunks
        forged = rt.load_result(self.result.to_json().replace(b'"out":1.0', b'"out":9.0'), self.plan)
        ledger = _PayloadLedger(self.plan)
        for path in _payload_paths(self.plan):
            ledger.begin(path)
            raw = b''.join(_MemberStream(self.plan, forged, path))
            (self.destination/path).write_bytes(raw)
            ledger.feed(raw)
            ledger.end()
        manifest = _make_manifest(self.plan, forged, ledger.payload_files())
        (self.destination/'manifest.json').write_bytes(b''.join(_manifest_chunks(self.plan, manifest)))
        report = self.m.verify_bundle(self.source, self.destination)
        self.assertEqual(report.finding['code'], 'result_replay_mismatch')
        self.assertEqual(dict(report.checks), {'structure':'passed', 'source_binding':'passed',
            'runtime_binding':'passed', 'report':'passed', 'replay':'failed'})

    def test_replay_uses_exact_supplied_equivalent_source(self):
        from replicatetable import _replay
        supplied = rt.snapshot_dataset(dataset({'v': (('x',), [1., 2.], 'float64', None)},
            {'x': (['b', 'a'], '<U1')}))
        original = _replay._require_exact_replay
        seen = []
        def replay(plan, source, result):
            self.assertIs(source, supplied)
            seen.append(source)
            return original(plan, source, result)
        with patch.object(_replay, '_require_exact_replay', replay):
            report = self.m.verify_bundle(supplied, self.destination)
        self.assertEqual(report.status, 'verified')
        self.assertEqual(len(seen), 1)

    def test_runtime_failure_nested_in_replay_preserves_original_code_and_checks(self):
        from replicatetable import _replay
        with patch.object(_replay, '_require_exact_replay', side_effect=Refusal('runtime_changed')):
            report = self.m.verify_bundle(self.source, self.destination)
        self.assertEqual(report.status, 'refused')
        self.assertEqual(report.finding['code'], 'runtime_changed')
        self.assertEqual(report.checks['runtime_binding'], 'failed')
        self.assertEqual(report.checks['structure'], 'passed')
        self.assertEqual(report.checks['replay'], 'not_attempted')

    def test_different_actual_source_is_a_source_binding_refusal(self):
        other = rt.snapshot_dataset(dataset({'v': (('x',), [9., 2.], 'float64', None)},
            {'x': (['b', 'a'], '<U1')}))
        report = self.m.verify_bundle(other, self.destination)
        self.assertEqual(report.status, 'refused')
        self.assertEqual(report.finding['code'], 'source_fingerprint_mismatch')
        self.assertEqual(report.checks['source_binding'], 'failed')
        self.assertEqual(report.checks['replay'], 'not_attempted')

    def test_saved_plan_runtime_mismatch_is_not_generic_bundle_corruption(self):
        from replicatetable import runtime
        with patch.object(runtime, 'require_runtime', side_effect=Refusal('runtime_binding_mismatch')):
            report = self.m.verify_bundle(self.source, self.destination)
        self.assertEqual(report.finding['code'], 'runtime_binding_mismatch')
        self.assertEqual(report.checks['runtime_binding'], 'failed')
        self.assertEqual(report.checks['replay'], 'not_attempted')

    def test_mutation_during_replay_is_caught_by_final_original_reader_recheck(self):
        from replicatetable import _replay
        original = _replay._require_exact_replay
        def replay(plan, source, result):
            digest = original(plan, source, result)
            (self.destination/'table.csv').write_bytes(b'late mutation')
            return digest
        with patch.object(_replay, '_require_exact_replay', replay):
            report = self.m.verify_bundle(self.source, self.destination)
        self.assertEqual(report.finding['code'], 'bundle_changed')
        self.assertEqual(report.checks['structure'], 'failed')
        self.assertEqual(report.checks['replay'], 'passed')
