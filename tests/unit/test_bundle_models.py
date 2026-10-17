"""Test-first shared value schemas, without native/commit authority."""
import gc
import importlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

from replicatetable.codec import OwnedMap, canonical_bytes, strict_loads
from replicatetable.errors import Refusal
from replicatetable.model import SourceIdentity


CHECKS = ('structure', 'source_binding', 'runtime_binding', 'replay', 'report')


class EqualityTrap:
    def __eq__(self, other): raise AssertionError('unqualified equality')


class BundleValueTests(unittest.TestCase):
    def implementation(self):
        name = 'replicatetable._bundle_models'
        self.assertIsNotNone(importlib.util.find_spec(name), 'shared immutable bundle value models are absent')
        return importlib.import_module(name)

    def source(self): return SourceIdentity('memory', '0'*64, 50)
    def checks(self, state='not_attempted'): return dict.fromkeys(CHECKS, state)

    def bundle_arguments(self):
        return dict(version=2, status='committed', source=self.source(),
            recipe_sha256='1'*64, plan_sha256='2'*64, result_sha256='3'*64,
            runtime_sha256='4'*64, manifest_sha256='5'*64, bundle_bytes=50,
            interrupted_after_commit=False)

    def verification_arguments(self):
        return dict(version=2, status='verified', checks=self.checks('passed'),
            source=self.source(), plan_sha256='2'*64, result_sha256='3'*64,
            manifest_sha256='5'*64, finding=None, committed=False)

    def refused(self, function, *arguments, **keywords):
        with self.assertRaises(Refusal) as caught: function(*arguments, **keywords)
        self.assertEqual(caught.exception.code, 'invalid_bundle')
        return caught.exception

    def test_all_five_models_have_exact_canonical_field_shapes(self):
        module = self.implementation()
        bundle = module.BundleReceipt(**self.bundle_arguments())
        plan = module.PlanReceipt(version=2, status='committed', plan_sha256='2'*64,
            plan_bytes=40, interrupted_after_commit=False)
        prepared = module.PreparedReceipt(version=2, kind='bundle', source=self.source(),
            recipe_sha256='1'*64, plan_sha256='2'*64, result_sha256='3'*64,
            runtime_sha256='4'*64, manifest_sha256='5'*64, output_bytes=50)
        verified = module.BundleVerification(**self.verification_arguments())
        error = module.ErrorEnvelope(version=2, status='failed', code='io_error',
            message='Operation did not complete.', checks=self.checks(), committed=True, receipt=bundle)
        for model, fields in ((bundle, self.bundle_arguments()),
                (plan, dict(version=2,status=0,plan_sha256=0,plan_bytes=0,interrupted_after_commit=0)),
                (prepared, dict(version=0,kind=0,source=0,recipe_sha256=0,plan_sha256=0,result_sha256=0,runtime_sha256=0,manifest_sha256=0,output_bytes=0)),
                (verified, self.verification_arguments()),
                (error, dict(version=0,status=0,code=0,message=0,checks=0,committed=0,receipt=0))):
            raw = model.to_json()
            parsed = json.loads(raw)
            self.assertEqual(set(parsed), set(fields))
            self.assertEqual(raw, canonical_bytes(parsed))
            self.assertEqual(b''.join(model.iter_json_chunks()), raw)
            self.assertFalse(hasattr(model, 'to_dict'))

    def test_checks_are_exact_owned_and_input_mutation_has_no_effect(self):
        module = self.implementation()
        mutable = self.checks()
        owned = module._own_checks(mutable)
        self.assertIs(type(owned), OwnedMap)
        self.assertIs(module._own_checks(owned), owned)
        mutable['replay'] = 'passed'
        self.assertEqual(owned['replay'], 'not_attempted')
        with self.assertRaises((TypeError, AttributeError)): owned['replay'] = 'passed'

    def test_checks_refuse_missing_extra_and_nonexact_state_before_equality(self):
        module = self.implementation()
        for change in (None, [], {**self.checks(), 'extra':'passed'},
                       {name:'passed' for name in CHECKS[:-1]},
                       {**self.checks(), 'replay': EqualityTrap()},
                       {**self.checks(), 'replay': True},
                       {**self.checks(), 'replay':'unknown'}):
            self.refused(module._own_checks, change)

    def test_finding_ownership_and_exact_exit_domain(self):
        module = self.implementation()
        original = dict(code='io_error', message='Operation did not complete.', exit_code=3)
        finding = module._own_finding(original)
        self.assertIs(module._own_finding(finding), finding)
        original['message'] = 'Changed.'
        self.assertEqual(finding['message'], 'Operation did not complete.')
        self.assertIsNone(module._own_finding(None))
        for exit_code in (True, 0, 1, 4, 129, 144, EqualityTrap()):
            self.refused(module._own_finding, {**original, 'exit_code':exit_code})
        for field, value in (('code', EqualityTrap()), ('code', 'Upper'),
                             ('message', 'bad\nmessage'), ('message', 'x'*513)):
            self.refused(module._own_finding, {**original, field:value})

    def test_receipt_requires_exact_version_boolean_hash_count_and_source(self):
        module = self.implementation()
        for field, value in (('version', True), ('status', EqualityTrap()),
                ('source', EqualityTrap()), ('plan_sha256', 'A'*64),
                ('bundle_bytes', True), ('bundle_bytes', 128*1024*1024+1),
                ('interrupted_after_commit', 1)):
            self.refused(module.BundleReceipt, **{**self.bundle_arguments(), field:value})

    def test_plan_receipt_uses_plan_byte_cap(self):
        module = self.implementation()
        args = dict(version=2, status='committed', plan_sha256='2'*64,
            plan_bytes=16*1024*1024, interrupted_after_commit=False)
        self.assertEqual(module.PlanReceipt(**args).plan_bytes, 16*1024*1024)
        self.refused(module.PlanReceipt, **{**args, 'plan_bytes':16*1024*1024+1})

    def test_prepared_receipt_has_kind_specific_nullability_without_committed_flag(self):
        module = self.implementation()
        args = dict(version=2, kind='plan', source=self.source(), recipe_sha256='1'*64,
            plan_sha256='2'*64, result_sha256=None, runtime_sha256='4'*64,
            manifest_sha256=None, output_bytes=40)
        prepared = module.PreparedReceipt(**args)
        self.assertFalse(hasattr(prepared, 'status'))
        self.assertFalse(hasattr(prepared, 'committed'))
        for changed in ({'kind':'bundle'}, {'result_sha256':'3'*64},
                        {'manifest_sha256':'5'*64}, {'kind':EqualityTrap()}):
            self.refused(module.PreparedReceipt, **{**args, **changed})

    def test_verified_requires_every_check_and_all_bindings(self):
        module = self.implementation()
        for field, value in (('checks', self.checks()), ('source', None),
                            ('plan_sha256', None), ('result_sha256', None),
                            ('manifest_sha256', None), ('committed', True),
                            ('finding',dict(code='io_error',message='Failed.',exit_code=3))):
            self.refused(module.BundleVerification, **{**self.verification_arguments(), field:value})

    def test_failed_verification_preserves_progress_and_explicit_exit(self):
        module = self.implementation()
        checks = self.checks(); checks['structure'] = checks['source_binding'] = 'passed'
        checks['runtime_binding'] = 'failed'
        args = dict(version=2,status='refused',checks=checks,source=self.source(),
            plan_sha256='2'*64,result_sha256='3'*64,manifest_sha256='5'*64,
            finding=dict(code='runtime_changed',message='Runtime changed.',exit_code=2),committed=False)
        value = module.BundleVerification(**args)
        self.assertEqual(dict(value.checks), checks)
        self.assertEqual(value.finding['code'], 'runtime_changed')
        self.refused(module.BundleVerification, **{**args,'status':'failed'})
        self.refused(module.BundleVerification, **{**args,'finding':None})

    def test_early_cancelled_verification_may_leave_checks_unattempted(self):
        module = self.implementation()
        for exit_code in (130, 143):
            value = module.BundleVerification(version=2,status='cancelled',checks=self.checks(),
                source=None,plan_sha256=None,result_sha256=None,manifest_sha256=None,
                finding=dict(code='interrupted',message='Operation was interrupted.',exit_code=exit_code),
                committed=False)
            self.assertEqual(value.finding['exit_code'], exit_code)
            self.assertTrue(all(state == 'not_attempted' for state in value.checks.values()))

    def test_error_envelope_borrows_exact_committed_receipt_and_has_no_exit_field(self):
        module = self.implementation()
        receipt = module.BundleReceipt(**self.bundle_arguments())
        args = dict(version=2,status='failed',code='io_error',message='Operation did not complete.',
                    checks=self.checks(),committed=True,receipt=receipt)
        error = module.ErrorEnvelope(**args)
        self.assertIs(error.receipt, receipt)
        self.assertFalse(hasattr(error, 'exit_code'))
        for change in ({'committed':False}, {'receipt':None}, {'committed':1},
                       {'receipt':json.loads(receipt.to_json())}):
            self.refused(module.ErrorEnvelope, **{**args, **change})

    def test_contextual_supervision_failure_is_not_reclassified_by_value_model(self):
        module = self.implementation()
        for status in ('refused', 'failed'):
            error = module.ErrorEnvelope(version=2,status=status,code='supervision_unavailable',
                message='Native worker startup failed; worker termination could not be confirmed.',
                checks=self.checks(),committed=False,receipt=None)
            self.assertEqual(error.status, status)
            self.assertEqual(error.code, 'supervision_unavailable')

    def test_models_are_final_readonly_and_reinitialization_is_atomic(self):
        module = self.implementation()
        args = self.bundle_arguments()
        value = module.BundleReceipt(**args)
        original = value.to_json()
        with self.assertRaises((AttributeError, TypeError)): value.status = 'failed'
        with self.assertRaises(TypeError): type('Child', (module.BundleReceipt,), {})
        self.refused(value.__init__, **{**args, 'status':EqualityTrap()})
        self.assertEqual(value.to_json(), original)
        with self.assertRaises(TypeError): module.BundleReceipt(*args.values())

    def test_failed_late_validation_keeps_model_uninitialized(self):
        module = self.implementation()
        value = object.__new__(module.BundleReceipt)
        self.refused(value.__init__, **{**self.bundle_arguments(), 'interrupted_after_commit':1})
        self.assertFalse(hasattr(value, 'version'))
        self.assertFalse(hasattr(value, 'source'))

    def test_model_headers_and_owned_progress_fit_existing_small_record_projections(self):
        module = self.implementation()
        receipt = module.BundleReceipt(**self.bundle_arguments())
        checks = module._own_checks(self.checks())
        finding = module._own_finding(dict(code='io_error',message='x'*512,exit_code=3))
        self.assertLessEqual(sys.getsizeof(receipt), 512)
        def owned_size(value):
            total = sys.getsizeof(value) + sys.getsizeof(value._items)
            for pair in value.items():
                total += sys.getsizeof(pair) + sum(sys.getsizeof(item) for item in pair)
            return total
        self.assertLessEqual(owned_size(checks), 2892)
        self.assertLessEqual(owned_size(finding), 4304)

    def test_retained_failed_constructor_exception_releases_owned_arguments(self):
        module = self.implementation()
        source = self.source()
        arguments = self.bundle_arguments(); arguments['source'] = source
        arguments['interrupted_after_commit'] = EqualityTrap()
        before = sys.getrefcount(source)
        enabled = gc.isenabled()
        gc.disable()
        try:
            caught = None
            try: module.BundleReceipt(**arguments)
            except Refusal as error: caught = error
            self.assertIsNotNone(caught)
            self.assertEqual(sys.getrefcount(source), before)
            self.assertIsNone(caught.__context__)
            self.assertIsNone(caught.__cause__)
        finally:
            if enabled: gc.enable()

    def test_unknown_model_kind_refuses_before_metaclass_hash_or_equality(self):
        module = self.implementation()
        hooks = []
        class Meta(type):
            def __hash__(cls):
                hooks.append('hash')
                return 0
            def __eq__(cls, other):
                hooks.append('equality')
                return False
        class Other(metaclass=Meta): pass
        value = Other()
        hooks.clear()
        self.refused(module.BundleReceipt.to_json, value)
        self.assertEqual(hooks, [])

    def test_unknown_receipt_kind_refuses_before_metaclass_equality(self):
        module = self.implementation()
        hooks = []
        class Meta(type):
            def __eq__(cls, other):
                hooks.append('equality')
                return False
        class Other(metaclass=Meta): pass
        value = Other()
        hooks.clear()
        self.refused(module.ErrorEnvelope, version=2,status='failed',code='io_error',
            message='Operation did not complete.',checks=self.checks(),committed=True,receipt=value)
        self.assertEqual(hooks, [])

    def test_finding_rejects_wrong_code_exit_categories_before_and_after_decode(self):
        module = self.implementation()
        for code, exit_code in (('runtime_changed',3), ('io_error',2), ('interrupted',2),
                                ('supervision_unavailable',130), ('unlisted_code',2)):
            original = dict(code=code,message='Operation did not complete.',exit_code=exit_code)
            decoded = strict_loads(canonical_bytes(original))
            for origin, value in (('constructor',original), ('decoder',decoded)):
                with self.subTest(code=code,origin=origin): self.refused(module._own_finding, value)

    def test_error_envelope_rejects_wrong_code_status_before_and_after_decode(self):
        module = self.implementation()
        for code, status in (('runtime_changed','failed'), ('io_error','refused'),
                             ('interrupted','refused'), ('supervision_unavailable','cancelled'),
                             ('unlisted_code','failed')):
            original = dict(version=2,status=status,code=code,message='Operation did not complete.',
                checks=self.checks(),committed=False,receipt=None)
            decoded = strict_loads(canonical_bytes(original))
            for origin, value in (('constructor',original), ('decoder',decoded)):
                with self.subTest(code=code,origin=origin): self.refused(module.ErrorEnvelope, **value)

    def test_verification_cannot_relabel_runtime_refusal_as_operational_failure(self):
        module = self.implementation()
        original = dict(version=2,status='failed',checks=self.checks(),source=None,
            plan_sha256=None,result_sha256=None,manifest_sha256=None,committed=False,
            finding=dict(code='runtime_changed',message='Runtime changed.',exit_code=3))
        for origin, value in (('constructor',original), ('decoder',strict_loads(canonical_bytes(original)))):
            with self.subTest(origin=origin): self.refused(module.BundleVerification, **value)

    def test_every_frozen_code_category_has_positive_value_and_decoder_coverage(self):
        module = self.implementation()
        # The unchanged normative table is independent test authority. Product
        # code must not read this document or derive policy from test fixtures.
        document = (Path(__file__).resolve().parents[2] / 'docs/contracts/API-SCHEMAS.md').read_text()
        section = document.split('## 14. Bounded stable refusal/error code table\n',1)[1].split('\n## 15.',1)[0]
        categories = {}
        for line in section.splitlines():
            if not line.startswith('- '): continue
            header = line[2:].split(':',1)[0]
            if header.startswith('supervision_unavailable '):
                exit_code = 2 if 'exit2' in header else 3
                categories.setdefault('supervision_unavailable',set()).add(exit_code)
            elif header.startswith('interrupted '):
                categories['interrupted'] = {130,143}
            elif header.endswith('(all2)'):
                for code in header[:-6].strip().split(', '): categories[code] = {2}
            else:
                for code, exit_text in re.findall(r'\b([a-z][a-z0-9_]+) \(([23])\)',header):
                    categories[code] = {int(exit_text)}
        self.assertGreater(len(categories), 60)
        self.assertEqual(categories['supervision_unavailable'], {2,3})
        self.assertEqual(categories['interrupted'], {130,143})
        for code, exits in categories.items():
            for exit_code in exits:
                status = 'refused' if exit_code == 2 else 'failed' if exit_code == 3 else 'cancelled'
                finding = dict(code=code,message='Operation did not complete.',exit_code=exit_code)
                envelope = dict(version=2,status=status,code=code,message='Operation did not complete.',
                    checks=self.checks(),committed=False,receipt=None)
                with self.subTest(code=code,exit_code=exit_code):
                    self.assertEqual(module._own_finding(finding)['exit_code'], exit_code)
                    self.assertEqual(module._own_finding(strict_loads(canonical_bytes(finding)))['exit_code'], exit_code)
                    self.assertEqual(module.ErrorEnvelope(**envelope).status, status)
                    self.assertEqual(module.ErrorEnvelope(**strict_loads(canonical_bytes(envelope))).status, status)

    def test_committed_cancellation_requires_interrupted_receipt_for_both_kinds(self):
        module = self.implementation()
        for kind, arguments in ((module.BundleReceipt,self.bundle_arguments()),
                (module.PlanReceipt,dict(version=2,status='committed',plan_sha256='2'*64,
                    plan_bytes=40,interrupted_after_commit=False))):
            envelope = dict(version=2,status='cancelled',code='interrupted',
                message='Operation was interrupted.',checks=self.checks(),committed=True)
            with self.subTest(kind=kind.__name__, interrupted=False):
                self.refused(module.ErrorEnvelope, **envelope,receipt=kind(**arguments))
            receipt = kind(**{**arguments,'interrupted_after_commit':True})
            with self.subTest(kind=kind.__name__, interrupted=True):
                self.assertIs(module.ErrorEnvelope(**envelope,receipt=receipt).receipt, receipt)
            # A later observed interruption must not replace an earlier IO
            # finding, even when the retained committed receipt records it.
            earlier_io = {**envelope,'status':'failed','code':'io_error'}
            with self.subTest(kind=kind.__name__, earlier_io=True):
                self.assertEqual(module.ErrorEnvelope(**earlier_io,receipt=receipt).code, 'io_error')

    def test_constructor_install_interruption_retires_validated_fields(self):
        module = self.implementation()
        receipt = module.BundleReceipt(**self.bundle_arguments())
        cases = (
            (module.PlanReceipt, dict(version=2,status='committed',
                plan_sha256=''.join(['a']*64),plan_bytes=40,interrupted_after_commit=False), 'plan_sha256'),
            (module.PreparedReceipt, dict(version=2,kind='bundle',source=self.source(),
                recipe_sha256='1'*64,plan_sha256='2'*64,result_sha256='3'*64,
                runtime_sha256='4'*64,manifest_sha256='5'*64,output_bytes=50), 'source'),
            (module.BundleReceipt, self.bundle_arguments(), 'source'),
            (module.BundleVerification, self.verification_arguments(), 'source'),
            (module.ErrorEnvelope, dict(version=2,status='failed',code='io_error',
                message='Operation did not complete.',checks=self.checks(),
                committed=True,receipt=receipt), 'receipt'),
        )
        original_install = module._install
        for kind, arguments, observed_field in cases:
            for phase in ('before_assignment', 'after_assignment'):
                with self.subTest(kind=kind.__name__, phase=phase):
                    interruption = KeyboardInterrupt()
                    def interrupted_install(instance, model_kind, values):
                        if phase == 'after_assignment':
                            original_install(instance, model_kind, values)
                        raise interruption
                    observed = arguments[observed_field]
                    before = sys.getrefcount(observed)
                    enabled = gc.isenabled()
                    gc.disable()
                    try:
                        caught = None
                        with patch.object(module, '_install', interrupted_install):
                            try: kind(**arguments)
                            except KeyboardInterrupt as error: caught = error
                        self.assertIs(caught, interruption)
                        self.assertIsNone(caught.__context__)
                        self.assertIsNone(caught.__cause__)
                        self.assertEqual(sys.getrefcount(observed), before)
                    finally:
                        if enabled: gc.enable()
