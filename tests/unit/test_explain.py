"""RowExplanation intended reds and genuine eager-source journeys.

The schema fixtures are structural inputs, not accounting or numerical proof.
Integration tests use actual BoundPlan, SourceSnapshot, ComputationResult,
fresh runtime checks, stock unit qualification and the original A/B/C closure.

Frozen operation schedule: validate exact key/limit and held identity/phase;
keep caller A/B/C charged; replay actual B and exhaust/close both full result
streams in a helper that returns before tracing; reserve the complete empty
metadata skeleton; materialize B once more; own one current immutable display
record and one column's raw/normalized views; release trace materialization;
recheck consumed B, runtime and full admission; finalize builders bottom-up
with only one record-list pointer copy; return owned primitives only. Original
result-plan C can occupy the second Z, so hash streams never freeze a plan.
"""
import copy
import gc
import hashlib
import importlib
import importlib.util
import json
import math
import sys
import unittest
import weakref
from unittest.mock import patch

import replicatetable as rt
from replicatetable.errors import Refusal
from replicatetable.codec import canonical_bytes, OwnedMap
from replicatetable.model import ArrayBuffer
from tests.unit.test_reduce import dataset, recipe, column, stage


ASSURANCE = 'Exact source-bound same-engine replay completed before tracing.'
NOTICE = ('Displayed cells are a bounded prefix. Complete membership is defined by selectors, '
          'support offsets, and the source, plan, and result hashes. Replay is not independent numerical proof.')
ROOT_FIELDS = {'version','source','recipe_sha256','plan_sha256','result_sha256','runtime_sha256',
               'row_dims','key','coordinates','limit','byte_truncated','assurance','notice','columns'}


def structural_example():
    return dict(version=1, source=dict(kind='memory', sha256='0'*64, size_bytes=10),
        recipe_sha256='1'*64, plan_sha256='2'*64, result_sha256='3'*64, runtime_sha256='4'*64,
        row_dims=['x'], key={'x': 2}, coordinates={'x': {'dtype':'<i8','length':1}},
        limit=1, byte_truncated=False, assurance=ASSURANCE, notice=NOTICE, columns=[dict(
        name='out', source='v', source_dtype='int64', converted_dtype='int64', output_dtype='int64',
        input_dims=['x'], final_dims=['x'], broadcast=[], conversion=dict(source_unit=None,
        target_unit=None, effective_unit=None, scale=1., offset=0.), weight=None, value=9, reasons=[],
        source_cells=dict(total=1,shown=1,truncated=False,limit_omitted=0,byte_omitted=0,
            selection=[0],cells=[dict(indices=[0],labels=[2],raw=9,converted=9,raw_weight=None,
                normalized_weight=None,exclusion_reason=None)]), stages=[])])


class Poison:
    def __eq__(self, other): raise AssertionError('equality before exact type')
    def __bool__(self): raise AssertionError('truth before exact type')
    def __iter__(self): raise AssertionError('iteration before exact type')


class ExplainCase(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('replicatetable.explain'),
                             'bounded row explanation implementation is absent')
        self.e = importlib.import_module('replicatetable.explain')
    def refused(self, code, function, *arguments, **keywords):
        with self.assertRaises(Refusal) as caught: function(*arguments, **keywords)
        self.assertEqual(caught.exception.code, code)
        return caught.exception
    def run_case(self, ds, rec):
        source = rt.snapshot_dataset(ds)
        plan = rt.compile_plan(source, rec)
        return source, plan, rt.execute(plan, source)
    def explained(self, ds, rec, key, limit=1000):
        source, plan, result = self.run_case(ds, rec)
        output = self.e.explain_row(plan, source, result, key, limit=limit)
        return source, plan, result, output, json.loads(output.to_json())


class ExplanationAPITests(ExplainCase):
    def test_private_module_exposes_exact_callable_surface(self):
        self.assertTrue(callable(getattr(self.e, 'explain_row', None)))
        self.assertTrue(callable(getattr(self.e, 'RowExplanation', None)))


class ExplanationModelTests(ExplainCase):
    def test_exact_schema_owned_backing_and_scalar_serialization(self):
        value = structural_example(); output = self.e.RowExplanation(**value)
        wanted = canonical_bytes(value)
        value['columns'][0]['source_cells']['cells'][0]['raw'] = 300
        self.assertEqual(output.to_json(), wanted)
        self.assertEqual(b''.join(output.iter_json_chunks()), wanted)
        self.assertEqual(output._serialized_size, len(wanted))
        self.assertEqual(output._byte_limit, 8*1024*1024)
        self.assertEqual(set(json.loads(wanted)), ROOT_FIELDS)
        self.assertIs(type(output.columns), tuple)
        self.assertIs(type(output.key), OwnedMap)
        self.assertFalse(hasattr(output, 'to_dict'))
        with self.assertRaises((AttributeError, TypeError)): output.limit = 2
        with self.assertRaises(TypeError): type('Subclass', (self.e.RowExplanation,), {})
    def test_reinitialization_is_atomic_before_replacement_hooks(self):
        output = self.e.RowExplanation(**structural_example()); before = output.to_json()
        self.refused('invalid_explanation', output.__init__, **{name:Poison() for name in ROOT_FIELDS})
        self.assertEqual(output.to_json(), before)
    def test_exact_types_precede_equality_in_every_repaired_role(self):
        paths = [('assurance',),('notice',),('limit',),('byte_truncated',),
            ('columns',0,'conversion','scale'),('columns',0,'source_cells','cells',0,'exclusion_reason'),
            ('columns',0,'source_cells','cells',0,'normalized_weight')]
        for path in paths:
            value = structural_example(); target = value
            for key in path[:-1]: target = target[key]
            target[path[-1]] = Poison()
            with self.subTest(path=path): self.refused('invalid_explanation', self.e.RowExplanation, **value)
    def test_direct_integer_raw_converted_and_value_cannot_be_null(self):
        for field in ('raw','converted','value'):
            value = structural_example(); col = value['columns'][0]
            if field == 'value': col[field] = None; col['reasons'] = ['missing_values']
            else: col['source_cells']['cells'][0][field] = None
            with self.subTest(field=field): self.refused('invalid_explanation', self.e.RowExplanation, **value)
    def test_stored_unicode_width_applies_to_key_and_source_labels(self):
        for place in ('key','label'):
            value = structural_example(); value['coordinates']['x']['dtype'] = '<U1'
            value['key']['x'] = 'a'; value['columns'][0]['source_cells']['cells'][0]['labels'] = ['a']
            if place == 'key': value['key']['x'] = 'ab'
            else: value['columns'][0]['source_cells']['cells'][0]['labels'] = ['ab']
            self.refused('invalid_explanation', self.e.RowExplanation, **value)
    def test_empty_or_unknown_mandatory_metadata_refuses(self):
        for path, replacement in ((('columns',), []), (('coordinates',), {}),
                (('assurance',), ''), (('source',), {}), (('row_dims',), [])):
            value = structural_example(); value[path[0]] = replacement
            self.refused('invalid_explanation', self.e.RowExplanation, **value)
        value = structural_example(); value['extra'] = 1
        with self.assertRaises(TypeError): self.e.RowExplanation(**value)
    def test_section_omissions_and_physical_selection_are_exact(self):
        for field, replacement in (('shown',0),('total',2),('byte_omitted',1),
                                    ('limit_omitted',1),('truncated',True),('selection',[None])):
            value = structural_example(); value['columns'][0]['source_cells'][field] = replacement
            self.refused('invalid_explanation', self.e.RowExplanation, **value)
    def test_constructor_rejects_oversize_before_owned_copy(self):
        value = structural_example(); value['notice'] = 'z'*(8*1024*1024+1)
        with patch.object(self.e, '_adopt_tree', side_effect=AssertionError('copy before admission')):
            self.refused('invalid_explanation', self.e.RowExplanation, **value)


class ExplanationJourneyTests(ExplainCase):
    def direct(self, dtype='int64', values=(2**63-1,2**53+1), labels=(2,1), label_dtype='int64'):
        return self.run_case(dataset({'v':(('x',),values,dtype,None)}, {'x':(labels,label_dtype)}), recipe(('x',)))
    def test_direct_exact_integer_typed_key_and_complete_hashes(self):
        cases=(('int64',(2**63-1,2**53+1),(-2**63,2**63-1),2**63-1,1),
               ('uint64',(2**64-1,2**53+1),(2**64-1,2**53+1),2**64-1,0))
        for dtype,values,labels,key,index in cases:
            with self.subTest(dtype=dtype):
                source,plan,result=self.direct(dtype,values,labels,dtype)
                output=self.e.explain_row(plan,source,result,{'x':key},limit=1)
                value=json.loads(output.to_json()); col=value['columns'][0]; wanted=values[index]
                self.assertEqual(value['key'],{'x':key}); self.assertIs(type(value['key']['x']),int)
                self.assertEqual(col['value'],wanted)
                self.assertEqual(col['source_cells']['cells'][0],dict(indices=[index],labels=[key],raw=wanted,
                    converted=wanted,raw_weight=None,normalized_weight=None,exclusion_reason=None))
                for field,raw in (('recipe_sha256',plan.recipe.to_json()),('plan_sha256',plan.to_json()),
                                 ('result_sha256',result.to_json()),('runtime_sha256',canonical_bytes(plan.runtime))):
                    self.assertEqual(value[field],hashlib.sha256(raw).hexdigest())
                self.assertEqual(value['source'],source.identity.to_dict())
                self.assertEqual(value['assurance'],ASSURANCE); self.assertEqual(value['notice'],NOTICE)
    def test_stored_signed_zero_empty_unicode_whitespace_and_exact_key_types(self):
        for labels, dtype, query in (([-0.],'float64',0.),([''],'<U1',''),([' é🙂 '],'<U4',' é🙂 ')):
            source,plan,result = self.direct(values=(3,),labels=labels,label_dtype=dtype)
            output = self.e.explain_row(plan,source,result,{'x':query},limit=1)
            stored = json.loads(output.to_json())['key']['x']
            self.assertIs(type(stored),type(labels[0]))
            if type(stored) is float: self.assertEqual(stored.hex(),labels[0].hex())
            else: self.assertEqual(stored,labels[0])
        source,plan,result = self.direct(values=(3,),labels=('a',),label_dtype='<U1')
        self.refused('row_key_not_found',self.e.explain_row,plan,source,result,{'x':'aa'},limit=1)
        self.refused('invalid_explanation_key',self.e.explain_row,plan,source,result,{'x':1},limit=1)
    def test_key_and_limit_refuse_before_replay(self):
        source,plan,result = self.direct()
        with patch('replicatetable._replay._require_exact_replay',side_effect=AssertionError('invalid input replay')):
            for key in ({'x':1.},{'x':True},{'x':float('nan')},{'x':1,'extra':2},[],Poison()):
                self.refused('invalid_explanation_key',self.e.explain_row,plan,source,result,key,limit=1)
            for limit in (None,0,1001,True,1.,Poison()):
                self.refused('invalid_explanation',self.e.explain_row,plan,source,result,{'x':1},limit=limit)
    def test_zero_positive_and_missing_weights_and_affine_conversion(self):
        _,_,_,_,value = self.explained(dataset({
            'v':(('r',),[10.,20.,float('nan'),30.],'float64','degC'),
            'w':(('r',),[0.,25.,50.,25.],'float64','percent')}, {'r':([3,1,4,2],'int64')}),
            recipe(columns=[column(source_unit='degC',target_unit='kelvin',stages=[
                stage(op='weighted_mean',weight_unit='percent')])]),{},limit=4)
        col=value['columns'][0]; cells=col['source_cells']['cells']; support=col['stages'][0]['records'][0]['record']
        self.assertEqual([c['indices'] for c in cells],[[0],[1],[2],[3]])
        self.assertEqual([c['normalized_weight'] for c in cells],[0.,.25,.5,.25])
        self.assertEqual([c['exclusion_reason'] for c in cells],['zero_weight',None,'missing_value',None])
        self.assertEqual(cells[0]['converted'],283.15); self.assertIsNone(cells[2]['converted'])
        self.assertEqual((support['n_input'],support['n_valid'],support['n_positive_weight_valid']),(4,3,2))
        self.assertEqual((support['weight_total'],support['weight_valid']),(1.,.5))
        self.assertAlmostEqual(col['value'],298.15)
    def test_two_stage_failed_intermediate_offsets_and_omitted_membership(self):
        _,_,_,_,value = self.explained(dataset({'v':(('rep','r'),[1.,float('nan'),4.,6.],'float64',None)},
            {'rep':([9,2],'int64'),'r':([7,1],'int64')}),recipe(columns=[column(stages=[
                stage('first',missing='propagate'),stage('second',('rep',))])]),{},limit=1)
        col=value['columns'][0]; first,second=col['stages']
        self.assertEqual(col['value'],5.); self.assertEqual(col['reasons'],[])
        self.assertEqual((first['total'],first['shown'],first['limit_omitted']),(2,1,1))
        self.assertEqual((first['support_start'],second['support_start']),(0,2))
        self.assertEqual(first['records'][0]['membership'],[1,None])
        self.assertEqual(first['records'][0]['support_index'],0)
        self.assertEqual(second['records'][0]['support_index'],2)
        self.assertEqual(second['records'][0]['membership'],[None])
        self.assertEqual(second['records'][0]['record']['n_valid'],1)
    def test_scalar_and_broadcast_sections_remain_complete_at_limit(self):
        _,_,_,_,value=self.explained(dataset({'v':((),[4],'int64',None)},
            {'x':(['b','a'],'<U1')}),recipe(('x',),[column(broadcast=('x',))]),{'x':'a'},limit=1)
        col=value['columns'][0]; self.assertEqual(col['broadcast'],['x'])
        self.assertEqual(col['source_cells']['selection'],[])
        self.assertEqual(col['source_cells']['cells'][0]['indices'],[])
        self.assertEqual(value['coordinates'],{'x':dict(dtype='<U1',length=2)})
    def test_replay_rejects_coherent_forge_before_trace_materialization(self):
        source,plan,result=self.direct(); raw=result.to_dict(); raw['rows'][0]['values']['out']=123
        forged=rt.ComputationResult(_plan=plan,**raw)
        with patch.object(self.e,'_trace_memory',side_effect=AssertionError('trace before replay')):
            self.refused('result_replay_mismatch',self.e.explain_row,plan,source,forged,{'x':1},limit=1)
    def test_equivalent_distinct_abc_handles_and_no_full_plan_projection(self):
        a,plan_a,result_a=self.direct(); b,_,_=self.direct(); c,plan_c,result_c=self.direct()
        from replicatetable import admission
        original=admission._guard; seen=[]
        def guard(*arguments,**keywords):
            active=admission._ACTIVE.get()
            self.assertIs(active.plan,plan_a); self.assertIs(active.result,result_c)
            self.assertEqual((active.required_dataset_count,active.distinct_dataset_count),(3,3))
            for handle in (a._handle,b._handle,c._handle): self.assertTrue(any(handle is x for x in active.datasets))
            seen.append(True); return original(*arguments,**keywords)
        with patch.object(admission,'_guard',guard), \
             patch('replicatetable.plan._plan_projection',side_effect=AssertionError('third plan projection')), \
             patch('replicatetable.codec.freeze',side_effect=AssertionError('full freeze')), \
             patch('replicatetable.codec.thaw',side_effect=AssertionError('full thaw')):
            output=self.e.explain_row(plan_a,b,result_c,{'x':1},limit=1)
        self.assertTrue(seen); self.assertEqual(json.loads(output.to_json())['columns'][0]['value'],2**53+1)
    def test_actual_supplied_source_and_exact_selection_are_consumed(self):
        a,plan,result=self.direct(); b,_,_=self.direct()
        b._handle._variables['v']._data[1]=70
        self.refused('source_changed',self.e.explain_row,plan,b,result,{'x':1},limit=1)
        materialized=rt.materialize_source(a,plan)
        result2=self.e.explain_row(plan,materialized,result,{'x':1},limit=1)
        self.assertEqual(json.loads(result2.to_json())['columns'][0]['value'],2**53+1)
    def test_replay_buffers_die_before_trace_and_return_retains_no_dataset(self):
        source,plan,result=self.direct(); retained=[]; original=ArrayBuffer.__init__; calls=[]
        def init(buffer,dtype,shape,data): original(buffer,dtype,shape,data); retained.append(data)
        original_trace=self.e._trace_memory
        def trace(*arguments):
            for raw in retained: self.assertEqual(sys.getrefcount(raw),3)
            calls.append(True); return original_trace(*arguments)
        handle=weakref.ref(source._handle)
        enabled=gc.isenabled(); gc.disable()
        try:
            with patch.object(ArrayBuffer,'__init__',init),patch.object(self.e,'_trace_memory',trace):
                output=self.e.explain_row(plan,source,result,{'x':1},limit=1)
            self.assertTrue(calls)
            for raw in retained: self.assertEqual(sys.getrefcount(raw),3)
            del source,plan,result
            self.assertIsNone(handle())
            self.assertTrue(output.to_json())
        finally:
            if enabled: gc.enable()
    def test_owned_cancellation_clears_new_arrays_and_private_frames(self):
        source,plan,result=self.direct(); retained=[]; writes=[]; original=ArrayBuffer.__init__
        class Cancel(BaseException):
            def __setattr__(self,name,value): writes.append(name); return super().__setattr__(name,value)
        cancellation=Cancel('stop')
        def init(buffer,dtype,shape,data): original(buffer,dtype,shape,data); retained.append(data)
        # A MagicMock would retain ndarray arguments in its call history and
        # private type/proxy cycle while GC is disabled. The owned operation
        # must not clear that unrelated test cache. Use a plain injector.
        def fail_cell(*arguments): raise cancellation
        error=None; enabled=gc.isenabled(); gc.disable()
        try:
            with patch.object(ArrayBuffer,'__init__',init), \
                 patch.object(self.e,'_source_cell',fail_cell):
                try: self.e.explain_row(plan,source,result,{'x':1},limit=1)
                except BaseException as caught: error=caught
            self.assertIs(error,cancellation); self.assertEqual(writes,[])
            self.assertIsNone(error.__cause__); self.assertIsNone(error.__context__)
            self.assertTrue(retained)
            for raw in retained: self.assertEqual(sys.getrefcount(raw),3)
        finally:
            if enabled: gc.enable()


if __name__=='__main__': unittest.main()
