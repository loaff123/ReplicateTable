"""Original and public-supplement bytes cannot silently drift.

The test-only adapter may append only missing weight_unit:null for a verified
historical unitless weight source. It cannot alter the frozen recipe or order.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1] / 'frozen'
ORIGINAL_MANIFEST_SHA='e060c086701f2661c250cb70b7570573a16d00efe5d5d2f8e72790484ca9c167'
SUPPLEMENT_MANIFEST_SHA='7470ca7af3bd4942d911e40d0f66bf16b8d6d135964d2b4e31665df5e646e9fb'


class FrozenTests(unittest.TestCase):
    def tools(self):
        spec=importlib.util.find_spec('tests.frozen_tools')
        self.assertIsNotNone(spec, 'A1 frozen validator and exact-diff adapter are absent')
        from tests import frozen_tools
        return frozen_tools

    def test_verify_both_frozen_envelopes_and_manifest_bytes(self):
        tools=self.tools()
        self.assertEqual(tools.verify_frozen(ROOT/'original',ORIGINAL_MANIFEST_SHA),13)
        self.assertEqual(tools.verify_frozen(ROOT/'supplemental',SUPPLEMENT_MANIFEST_SHA),7)

    def test_historical_flat_manifest_lookup_is_wrong(self):
        # Regression of the historical harness mistake, without its private path.
        manifest=json.loads((ROOT/'original'/'freeze_sha256.json').read_bytes())
        with self.assertRaises(KeyError):
            _=manifest['fixtures/F1.json']
        self.assertEqual(manifest['artifacts']['fixtures/F1.json'],
                         '5be327ba2a4dfad6c442601ccff9993b05ee5efb0a870bc958854e5d589ec436')
        self.tools().verify_frozen(ROOT/'original',ORIGINAL_MANIFEST_SHA)

    def test_one_byte_temporary_copy_mutation_refuses(self):
        tools=self.tools()
        import shutil
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'original'
            shutil.copytree(ROOT/'original',root)
            path=root/'fixtures/F1.json'
            raw=path.read_bytes(); path.write_bytes(b'!'+raw[1:])
            with self.assertRaisesRegex(ValueError,'artifact digest mismatch'):
                tools.verify_frozen(root,ORIGINAL_MANIFEST_SHA)

    def test_adapter_preserves_original_files_types_values_and_order(self):
        tools=self.tools()
        before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file()}
        total_insertions=0
        for path in sorted((ROOT/'original'/'fixtures').glob('*.json')):
            fixture=json.loads(path.read_bytes())
            original=copy.deepcopy(fixture)
            adapted=tools.adapt_legacy_recipe(fixture)
            self.assertEqual(fixture,original)
            self.assertIsNot(adapted,fixture['recipe'])
            total_insertions += tools.assert_adapter_diff(fixture,adapted)
            for old,new in zip(fixture['recipe']['columns'],adapted['columns']):
                self.assertIsNot(old,new)
                self.assertEqual(list(old),list(new))
                for a,b in zip(old['stages'],new['stages']):
                    self.assertIsNot(a,b)
                    expected=list(a)+(['weight_unit'] if a['op']=='weighted_mean' and 'weight_unit' not in a else [])
                    self.assertEqual(list(b),expected)
        self.assertGreater(total_insertions,0)
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_adapter_rejects_other_changes_and_nonunitless_missing_assertion(self):
        tools=self.tools()
        fixture=json.loads((ROOT/'original'/'fixtures/F3.json').read_bytes())
        correct=tools.adapt_legacy_recipe(fixture)
        wrong=copy.deepcopy(correct); wrong['row_dims'].reverse()
        with self.assertRaisesRegex(ValueError,'adapter changed'):
            tools.assert_adapter_diff(fixture,wrong)
        wrong=copy.deepcopy(correct); wrong['columns'][0]['name']='changed'
        with self.assertRaisesRegex(ValueError,'adapter changed'):
            tools.assert_adapter_diff(fixture,wrong)
        wrong={key:correct[key] for key in reversed(correct)}
        with self.assertRaisesRegex(ValueError,'adapter changed'):
            tools.assert_adapter_diff(fixture,wrong)
        weighted=next(stage for c in fixture['recipe']['columns'] for stage in c['stages'] if stage['op']=='weighted_mean')
        fixture['data']['variables'][weighted['weights']]['units']='percent'
        with self.assertRaisesRegex(ValueError,'unitless'):
            tools.adapt_legacy_recipe(fixture)

    def test_original_individual_shape_and_recipe_limits(self):
        # Independent scalar counting, no candidate engine or formula estimator.
        self.tools()
        for path in (ROOT/'original'/'fixtures').glob('*.json'):
            fixture=json.loads(path.read_bytes()); data=fixture['data']; recipe=fixture['recipe']
            lengths={name:len(labels) for name,labels in data['coords'].items()}
            self.assertLessEqual(len(lengths),16)
            self.assertLessEqual(len(data['variables']),64)
            self.assertLessEqual(len(recipe['columns']),32)
            self.assertLessEqual(len(recipe['row_dims']),16)
            import math
            rows=math.prod(lengths[d] for d in recipe['row_dims'])
            self.assertLessEqual(rows,100000)
            support=0
            work=sum(n*(1+(max(2,n)-1).bit_length()) for n in lengths.values())
            for column in recipe['columns']:
                self.assertLessEqual(len(column['stages']),2)
                variable=data['variables'][column['source']]
                dims=list(variable['dims'])
                size=math.prod(lengths[d] for d in dims)
                self.assertLessEqual(len(dims),16); self.assertLessEqual(size,67108864)
                weights=0
                if column['stages'] and column['stages'][0]['op']=='weighted_mean':
                    weight=data['variables'][column['stages'][0]['weights']]
                    weights=math.prod(lengths[d] for d in weight['dims'])
                work+=4*size+3*weights
                for stage in column['stages']:
                    dims=[d for d in dims if d not in stage['dims']]
                    remaining=math.prod(lengths[d] for d in dims)
                    work+=12*size+8*remaining; support+=remaining; size=remaining
            work+=4*rows*len(recipe['columns'])+8*support
            self.assertLessEqual(support,1000000)
            self.assertLessEqual(work,268435456)

    def test_current_supplement_v2_and_preserved_v1_code_only_delta(self):
        tools=self.tools()
        self.assertEqual(tools.verify_frozen(ROOT/'supplemental-v2',
            'f0ffb2312d10d7baab90b0d4a7a43f9d49c54f39d10efb60e0189daa5db6f9aa'),7)
        self.assertEqual((ROOT/'supplemental'/'fixtures.json').read_bytes(),
                         (ROOT/'supplemental-v2'/'fixtures.json').read_bytes())
        before=json.loads((ROOT/'supplemental'/'expected.json').read_bytes())
        after=json.loads((ROOT/'supplemental-v2'/'expected.json').read_bytes())
        self.assertEqual(before['cases']['R15_weighted_second_stage']['code'],'invalid_recipe')
        self.assertEqual(after['cases']['R15_weighted_second_stage']['code'],'unsupported_later_stage_weights')
        expected=copy.deepcopy(before)
        expected['cases']['R15_weighted_second_stage']['code']='unsupported_later_stage_weights'
        self.assertEqual(expected,after)
