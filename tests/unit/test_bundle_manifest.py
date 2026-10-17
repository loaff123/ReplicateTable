"""Supplemental manifest structure, actual-counter and shared-codec tests.

Wrong membership, claimed sizes/digests, canonical structure and type coercion
must refuse. These pure tests confer no file witness, replay or commit authority.
"""
import hashlib
import importlib
import importlib.util
import json
from unittest.mock import patch

from replicatetable.codec import OwnedMap, canonical_bytes
from tests.unit.test_reduce import ReductionCase, dataset, recipe, column, stage


class ManifestTests(ReductionCase):
    def implementation(self):
        name = 'replicatetable._bundle_manifest'
        self.assertIsNotNone(importlib.util.find_spec(name), 'bounded bundle manifest layer is absent')
        return importlib.import_module(name)

    def simple(self):
        return self.run_case(dataset({'v': (('x',), [1., 2.], 'float64', None)},
            {'x': ([2, 1], 'int64')}), recipe(('x',)))

    def payload(self, plan, result):
        from replicatetable._bundle_payload import _MemberStream, _payload_paths, _PayloadLedger
        ledger = _PayloadLedger(plan)
        for path in _payload_paths(plan):
            ledger.begin(path)
            for fragment in _MemberStream(plan, result, path): ledger.feed(fragment)
            ledger.end()
        return ledger.payload_files()

    def test_manifest_exact_shape_sorted_files_and_no_self_length_cycle(self):
        module = self.implementation()
        _, plan, result = self.simple()
        files = self.payload(plan, result)
        manifest = module._make_manifest(plan, result, files)
        raw = b''.join(module._manifest_chunks(plan, manifest))
        parsed = json.loads(raw)
        self.assertEqual(raw, canonical_bytes(parsed))
        self.assertEqual(set(parsed), {'version', 'bundle_format', 'formula_version', 'source',
            'recipe_sha256', 'plan_sha256', 'result_sha256', 'runtime', 'runtime_sha256',
            'files', 'totals', 'assurance'})
        self.assertEqual(parsed['bundle_format'], 'replicatetable-bundle-v2')
        self.assertEqual(parsed['totals'], {'rows': 2, 'support_records': 0,
            'payload_bytes': sum(entry['size_bytes'] for entry in files.values())})
        self.assertNotIn('manifest.json', parsed['files'])
        self.assertIs(manifest['runtime'], plan.runtime)
        self.assertIs(manifest['files'], files)

    def test_manifest_model_hashes_bind_complete_actual_plan_recipe_result(self):
        module = self.implementation()
        _, plan, result = self.simple()
        files = self.payload(plan, result)
        value = module._make_manifest(plan, result, files)
        self.assertEqual(value['plan_sha256'], hashlib.sha256(plan.to_json()).hexdigest())
        self.assertEqual(value['recipe_sha256'], hashlib.sha256(plan.recipe.to_json()).hexdigest())
        self.assertEqual(value['result_sha256'], hashlib.sha256(result.to_json()).hexdigest())
        forged = {name: dict(record) for name, record in files.items()}
        forged['result.json']['sha256'] = 'f'*64
        self.refused('bundle_digest_mismatch', module._make_manifest, plan, result, OwnedMap(forged))

    def test_manifest_loader_reuses_strict_codec_and_returns_no_parsed_runtime(self):
        module = self.implementation()
        _, plan, result = self.simple()
        files = self.payload(plan, result)
        manifest = module._make_manifest(plan, result, files)
        raw = b''.join(module._manifest_chunks(plan, manifest))
        from replicatetable import codec
        with patch.object(codec, 'strict_loads', wraps=codec.strict_loads) as decoder:
            returned = module._load_manifest(raw, plan, result, files)
        self.assertEqual(decoder.call_count, 1)
        self.assertIs(returned['runtime'], plan.runtime)
        self.assertIs(returned['files'], files)
        self.assertEqual(b''.join(module._manifest_chunks(plan, returned)), raw)

    def test_manifest_refuses_unknown_missing_duplicate_and_noncanonical_json(self):
        module = self.implementation()
        _, plan, result = self.simple()
        files = self.payload(plan, result)
        value = module._make_manifest(plan, result, files)
        raw = b''.join(module._manifest_chunks(plan, value))
        parsed = json.loads(raw)
        cases = [raw.replace(b'"version":2', b'"version":2,"version":2'),
                 raw[:-1], b' '+raw, raw+b'\n', raw.replace(b'"version":2', b'"version":true')]
        extra = dict(parsed, extra=0)
        missing = dict(parsed); del missing['assurance']
        cases += [canonical_bytes(extra), canonical_bytes(missing)]
        for changed in cases:
            self.refused('invalid_bundle', module._load_manifest, changed, plan, result, files)

    def test_manifest_refuses_digest_size_and_totals_corruption_separately(self):
        module = self.implementation()
        _, plan, result = self.simple()
        files = self.payload(plan, result)
        raw = b''.join(module._manifest_chunks(plan, module._make_manifest(plan, result, files)))
        for field, changed, code in (('sha256', 'f'*64, 'bundle_digest_mismatch'),
                                     ('size_bytes', 1, 'bundle_digest_mismatch'),
                                     ('size_bytes', True, 'invalid_bundle')):
            parsed = json.loads(raw)
            parsed['files']['table.csv'][field] = changed
            self.refused(code, module._load_manifest, canonical_bytes(parsed), plan, result, files)
        parsed = json.loads(raw); parsed['totals']['rows'] = 3
        self.refused('invalid_bundle', module._load_manifest, canonical_bytes(parsed), plan, result, files)

    def test_manifest_membership_comes_from_plan_including_every_stage_pair(self):
        module = self.implementation()
        _, plan, result = self.run_case(dataset({'v': (('r',), [1., 2.], 'float64', None)},
            {'r': ([1, 2], 'int64')}), recipe((), [column(stages=[stage()])]))
        files = self.payload(plan, result)
        for wrong in ({name: dict(record) for name, record in files.items() if not name.endswith('.schema.json')},
                      {**{name: dict(record) for name, record in files.items()}, 'extra.csv': {'sha256':'0'*64, 'size_bytes':0}}):
            self.refused('invalid_bundle', module._make_manifest, plan, result, OwnedMap(wrong))

    def test_manifest_last_member_counter_accounts_actual_whole_bundle(self):
        module = self.implementation()
        from replicatetable._bundle_payload import _PayloadLedger, _MemberStream, _payload_paths
        _, plan, result = self.simple()
        ledger = _PayloadLedger(plan)
        for path in _payload_paths(plan):
            ledger.begin(path)
            for fragment in _MemberStream(plan, result, path): ledger.feed(fragment)
            ledger.end()
        payload = ledger.payload_bytes
        manifest = module._make_manifest(plan, result, ledger.payload_files())
        ledger.begin_manifest()
        raw = b''.join(module._manifest_chunks(plan, manifest))
        for offset in range(0, len(raw), 65536): ledger.feed(raw[offset:offset+65536])
        counter = ledger.end()
        totals = ledger.finish()
        self.assertEqual(counter['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(totals['bundle_bytes'], payload+len(raw))
        self.assertEqual(totals['manifest_bytes'], len(raw))
        self.assertEqual(totals['payload_bytes'], payload)
        self.assertEqual(len(totals['files']), 7)
        self.assertNotIn('manifest.json', manifest['files'])
        self.refused('invalid_bundle', ledger.begin_manifest)
