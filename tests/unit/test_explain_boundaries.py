"""Further row-explanation constructor, real-cap and failure controls.

The byte-stop journey uses genuine admitted models and the unchanged 8 MiB
cap. It neither patches budgets nor introduces a numerical or runtime oracle.
"""
import copy
import gc
import json
import sys
from unittest.mock import patch

import replicatetable as rt
from replicatetable.errors import Refusal
from replicatetable import admission
from tests.unit.test_explain import ExplainCase, Poison, structural_example
from tests.unit.test_reduce import dataset, recipe, column, stage


def staged_example(weighted=False):
    value=structural_example(); value['row_dims']=[]; value['key']={}
    value['coordinates']={'r':dict(dtype='<i8',length=2)}
    col=value['columns'][0]
    col.update(source_dtype='float64',converted_dtype='float64',output_dtype='float64',
        input_dims=['r'],final_dims=[],value=3. if weighted else 2.)
    col['source_cells'].update(total=2,shown=1,truncated=True,limit_omitted=1,
        byte_omitted=0,selection=[None])
    cell=col['source_cells']['cells'][0]
    cell.update(indices=[0],labels=[2],raw=1.,converted=1.,normalized_weight=1.)
    if weighted:
        col['weight']=dict(source='w',dtype='float64',dims=['r'],source_unit='percent',
                           unit='dimensionless',scale=.01,offset=0.)
        cell.update(raw_weight=0.,normalized_weight=0.,exclusion_reason='zero_weight')
    record=dict(column='out',stage='first',keys={},n_input=2,n_valid=2,
        n_positive_weight_valid=1 if weighted else 2,weight_total=1. if weighted else 2.,
        weight_valid=1. if weighted else 2.,reasons=[],value=col['value'],unit=None)
    col['stages']=[dict(total=1,shown=1,truncated=False,limit_omitted=0,byte_omitted=0,
        name='first',input_dims=['r'],dims=['r'],remaining_dims=[],
        op='weighted_mean' if weighted else 'mean',missing='skip',min_count=1,
        input_stage=None,support_start=0,records=[dict(support_index=0,record=record,membership=[None])])]
    return value


class ExplanationBoundaryTests(ExplainCase):
    def test_stage_operator_weight_unit_and_implicit_weights_are_exact_before_hooks(self):
        for path in (('stages',0,'op'),('weight','unit'),('source_cells','cells',0,'normalized_weight')):
            value=staged_example(weighted=True); target=value['columns'][0]
            for key in path[:-1]: target=target[key]
            target[path[-1]]=Poison()
            self.refused('invalid_explanation',self.e.RowExplanation,**value)
        value=staged_example(); value['columns'][0]['source_cells']['cells'][0]['normalized_weight']=True
        self.refused('invalid_explanation',self.e.RowExplanation,**value)
    def test_shown_stage_policy_counts_and_final_linkage_are_validated(self):
        valid=staged_example(); self.assertTrue(self.e.RowExplanation(**valid).to_json())
        changes=(('n_input',1),('n_valid',1),('n_positive_weight_valid',1),
                 ('weight_total',1.),('weight_valid',1.),('value',7.),('reasons',['missing_values']))
        for field,replacement in changes:
            value=staged_example(); value['columns'][0]['stages'][0]['records'][0]['record'][field]=replacement
            with self.subTest(field=field): self.refused('invalid_explanation',self.e.RowExplanation,**value)
        value=staged_example(); value['columns'][0]['stages'][0]['min_count']=3
        self.refused('invalid_explanation',self.e.RowExplanation,**value)
    def test_membership_offsets_raw_missingness_and_exclusion_are_checked(self):
        for field,replacement in (('support_index',1),('membership',[0])):
            value=staged_example(); value['columns'][0]['stages'][0]['records'][0][field]=replacement
            self.refused('invalid_explanation',self.e.RowExplanation,**value)
        for field,replacement in (('raw',None),('converted',None),('exclusion_reason','zero_weight')):
            value=staged_example(); value['columns'][0]['source_cells']['cells'][0][field]=replacement
            self.refused('invalid_explanation',self.e.RowExplanation,**value)
        weighted=staged_example(True); self.assertTrue(self.e.RowExplanation(**weighted).to_json())
        weighted['columns'][0]['source_cells']['cells'][0]['exclusion_reason']=None
        self.refused('invalid_explanation',self.e.RowExplanation,**weighted)
    def test_public_constructor_owns_tuple_children_containing_mutable_fields(self):
        value=staged_example(); value['columns']=tuple(value['columns'])
        value['columns'][0]['stages']=tuple(value['columns'][0]['stages'])
        output=self.e.RowExplanation(**value); before=output.to_json()
        value['columns'][0]['stages'][0]['records'][0]['record']['value']=900.
        self.assertEqual(output.to_json(),before)
    def test_stream_throw_before_and_after_first_next_retires_owned_frames(self):
        output=self.e.RowExplanation(**staged_example())
        for started in (False,True):
            stream=output.iter_json_chunks()
            if started: next(stream)
            failure=RuntimeError('owned test interruption'); caught=None
            try: stream.throw(failure)
            except BaseException as error: caught=error
            self.assertIs(caught,failure); self.assertTrue(stream._closed)
            self.assertIsNone(stream._data); self.assertIsNone(stream._inner)
            self.assertIsNone(failure.__cause__); self.assertIsNone(failure.__context__)
            with self.assertRaises(StopIteration): next(stream)
    def test_full_replay_rejects_forgery_in_an_unrequested_row(self):
        source,plan,result=self.run_case(dataset({'v':(('x',),[2.,4.],'float64',None)},
            {'x':([2,1],'int64')}),recipe(('x',)))
        raw=result.to_dict(); raw['rows'][1]['values']['out']=90.
        forged=rt.ComputationResult(_plan=plan,**raw)
        self.refused('result_replay_mismatch',self.e.explain_row,plan,source,forged,{'x':1},limit=1)
    def test_replay_preserves_actual_runtime_refusal_and_cancellation_identity(self):
        source,plan,result=self.run_case(dataset({'v':((),[3.],'float64',None)},{}),recipe())
        from replicatetable._replay import _require_exact_replay
        for failure in (Refusal('runtime_changed'),KeyboardInterrupt('cancel')):
            caught=None
            with admission._required_inputs(plan=plan,snapshot=source,result=result), \
                 patch('replicatetable.reduce.execute',side_effect=failure):
                try: _require_exact_replay(plan,source,result)
                except BaseException as error: caught=error
            self.assertIs(caught,failure)
            self.assertIsNone(failure.__context__); self.assertIsNone(failure.__cause__)
            if isinstance(failure,Refusal): self.assertEqual(failure.code,'runtime_changed')
    def test_actual_eight_mib_byte_stop_keeps_exact_all_section_counts(self):
        labels=['a'*4095+'1','a'*4095+'2']
        ds=dataset({'v':(('r','s'),[1.]*1000,'float64',None)},
                   {'r':(list(range(500)),'int64'),'s':(labels,'<U4096')})
        rec=recipe(columns=[column('one',stages=[stage(dims=('r','s'))]),
                            column('two',stages=[stage(dims=('r','s'))])])
        source,plan,result=self.run_case(ds,rec)
        made=[]; original=self.e._source_cell
        def cell(*arguments): made.append(True); return original(*arguments)
        with patch.object(self.e,'_source_cell',cell):
            output=self.e.explain_row(plan,source,result,{},limit=1000)
        raw=output.to_json(); value=json.loads(raw); cap=8*1024*1024
        self.assertLessEqual(len(raw),cap); self.assertLess(cap-len(raw),5000)
        self.assertTrue(value['byte_truncated'])
        sections=[section for col in value['columns'] for section in [col['source_cells']]+col['stages']]
        stopped=False
        for section in sections:
            self.assertEqual(section['total'],section['shown']+section['limit_omitted']+section['byte_omitted'])
            self.assertEqual(section['limit_omitted'],max(section['total']-1000,0))
            if stopped: self.assertEqual(section['shown'],0)
            if section['byte_omitted']: stopped=True
        shown=sum(col['source_cells']['shown'] for col in value['columns'])
        self.assertEqual(len(made),shown+1)
        self.assertEqual(value['columns'][0]['source_cells']['shown'],1000)
        self.assertEqual(value['columns'][0]['stages'][0]['shown'],1)
        self.assertEqual(value['columns'][1]['stages'][0]['shown'],0)
        print('explanation actual cap journey:',len(raw),'bytes; admitted estimate:',
              plan.estimates['estimated_memory_bytes'],'; section total/shown/limit/byte:',
              [(s['total'],s['shown'],s['limit_omitted'],s['byte_omitted']) for s in sections])
    def test_shown_failed_intermediate_keeps_its_policy_and_final_uses_last_stage(self):
        source,plan,result=self.run_case(dataset({'v':(('rep','r'),[1.,float('nan'),4.,6.],'float64',None)},
            {'rep':([9,2],'int64'),'r':([7,1],'int64')}),recipe(columns=[column(stages=[
                stage('first',missing='propagate'),stage('second',('rep',))])]))
        value=json.loads(self.e.explain_row(plan,source,result,{},limit=2).to_json())
        col=value['columns'][0]; first,second=col['stages']
        self.assertEqual(first['records'][0]['record']['value'],5.)
        self.assertIsNone(first['records'][1]['record']['value'])
        self.assertEqual(first['records'][1]['record']['reasons'],['missing_values'])
        self.assertEqual(second['records'][0]['record']['n_valid'],1)
        self.assertEqual(col['value'],5.); self.assertEqual(col['reasons'],[])
    def test_canonical_support_prefix_and_physical_membership_have_distinct_orders(self):
        source,plan,result=self.run_case(dataset({'v':(('z','x','a'),list(range(8)),'float64',None)},
            {'z':([4,3],'int64'),'x':([9,2],'int64'),'a':([8,1],'int64')}),
            recipe(('x',),[column(stages=[stage('first',('z',)),stage('second',('a',))])]))
        value=json.loads(self.e.explain_row(plan,source,result,{'x':2},limit=2).to_json())
        col=value['columns'][0]; first,second=col['stages']
        self.assertEqual(col['source_cells']['selection'],[None,1,None])
        self.assertEqual([cell['indices'] for cell in col['source_cells']['cells']],[[0,1,0],[0,1,1]])
        self.assertEqual([entry['support_index'] for entry in first['records']],[0,2])
        self.assertEqual([entry['membership'] for entry in first['records']],[[None,1,1],[None,1,0]])
        self.assertEqual([entry['record']['value'] for entry in first['records']],[5.,4.])
        self.assertEqual(second['support_start'],4)
        self.assertEqual(second['records'][0]['membership'],[1,None])
        self.assertEqual(col['value'],4.5)
    def test_null_unit_conversions_cannot_claim_nonidentity_coefficients(self):
        value=staged_example(); value['columns'][0]['conversion']['scale']=2.
        self.refused('invalid_explanation',self.e.RowExplanation,**value)
        value=staged_example(True); value['columns'][0]['weight']['source_unit']=None
        self.refused('invalid_explanation',self.e.RowExplanation,**value)
    def test_constructor_row_grain_ceiling_equality_and_one_more(self):
        value=structural_example(); col=value['columns'][0]
        col.update(input_dims=[],final_dims=[],broadcast=['x'])
        col['source_cells']['selection']=[]
        col['source_cells']['cells'][0].update(indices=[],labels=[])
        value['coordinates']['x']['length']=100000
        self.assertTrue(self.e.RowExplanation(**value).to_json())
        value['coordinates']['x']['length']=100001
        self.refused('invalid_explanation',self.e.RowExplanation,**value)
    def test_constructor_complete_support_ceiling_equality_and_one_more(self):
        for length in (999999,1000000):
            value=staged_example(); value['byte_truncated']=True
            value['coordinates']={'r':dict(dtype='<i8',length=2),'s':dict(dtype='<i8',length=length)}
            col=value['columns'][0]; col['input_dims']=['r','s']
            col['source_cells'].update(total=2*length,shown=0,truncated=True,
                limit_omitted=2*length-1,byte_omitted=1,selection=[None,None],cells=[])
            first=col['stages'][0]
            first.update(total=length,shown=0,truncated=True,limit_omitted=length-1,byte_omitted=1,
                         input_dims=['r','s'],remaining_dims=['s'],records=[])
            second=copy.deepcopy(first)
            second.update(name='second',total=1,limit_omitted=0,input_dims=['s'],dims=['s'],
                          remaining_dims=[],input_stage=0,support_start=length)
            col['stages'].append(second)
            if length==999999: self.assertTrue(self.e.RowExplanation(**value).to_json())
            else: self.refused('invalid_explanation',self.e.RowExplanation,**value)
    def test_replay_iterator_cleanup_cannot_replace_established_mismatch(self):
        source,plan,result=self.run_case(dataset({'v':((),[3.],'float64',None)},{}),recipe())
        raw=result.to_dict(); raw['rows'][0]['values']['out']=7.
        forged=rt.ComputationResult(_plan=plan,**raw)
        from replicatetable import _result
        from replicatetable._replay import _require_exact_replay
        original=_result._result_chunks; cleanup_errors=[]
        class BrokenClose:
            def __init__(self,value): self.inner=original(value)
            def __iter__(self): return self
            def __next__(self): return next(self.inner)
            def close(self):
                self.inner.close(); error=Refusal('invalid_result'); cleanup_errors.append(error); raise error
        with admission._required_inputs(plan=plan,snapshot=source,result=forged), \
             patch.object(_result,'_result_chunks',BrokenClose):
            self.refused('result_replay_mismatch',_require_exact_replay,plan,source,forged)
        self.assertEqual(len(cleanup_errors),2)
        for error in cleanup_errors:
            self.assertIsNone(error.__traceback__); self.assertIsNone(error.__context__)
    def test_observed_scalar_stream_headers_fit_existing_traversal_reserve(self):
        import types
        output=self.e.RowExplanation(**staged_example())
        stream=output.iter_json_chunks(); peak=frames_peak=0
        try:
            for fragment in stream:
                self.assertLessEqual(len(fragment),32)
                pending=[stream._inner]; count=total=0
                while pending:
                    iterator=pending.pop()
                    if iterator is None: continue
                    self.assertIs(type(iterator),types.GeneratorType)
                    count+=1; total+=sys.getsizeof(iterator)
                    frame=iterator.gi_frame
                    if frame is not None:
                        total+=sys.getsizeof(frame)+sys.getsizeof(frame.f_locals)
                    child=iterator.gi_yieldfrom
                    if type(child) is types.GeneratorType: pending.append(child)
                peak=max(peak,total); frames_peak=max(frames_peak,count)
        finally: stream.close()
        self.assertLessEqual(frames_peak,32)
        self.assertLessEqual(peak+sys.getsizeof(stream),32*(512+4*128))
        print('explanation observed stream frames:',frames_peak,'headers with observer:',peak,
              'iterator header:',sys.getsizeof(stream),'traversal reserve:',32768)
    def test_owned_refusal_releases_trace_views_without_changing_error_identity(self):
        from replicatetable.model import ArrayBuffer
        source,plan,result=self.run_case(dataset({'v':((),[3.],'float64',None)},{}),recipe())
        retained=[]; original=ArrayBuffer.__init__; failure=Refusal('invalid_explanation'); caught=None
        def init(buffer,dtype,shape,data): original(buffer,dtype,shape,data); retained.append(data)
        def fail_cell(*arguments): raise failure
        enabled=gc.isenabled(); gc.disable()
        try:
            with patch.object(ArrayBuffer,'__init__',init),patch.object(self.e,'_source_cell',fail_cell):
                try: self.e.explain_row(plan,source,result,{},limit=1)
                except BaseException as error: caught=error
            self.assertIs(caught,failure); self.assertEqual(failure.code,'invalid_explanation')
            self.assertIsNone(failure.__context__); self.assertIsNone(failure.__cause__)
            for raw in retained: self.assertEqual(sys.getrefcount(raw),3)
        finally:
            if enabled: gc.enable()
    def test_indexed_row_membership_leaves_existing_pandas_cache_untouched(self):
        import numpy as np
        import pandas as pd
        import xarray as xr
        ds=xr.Dataset({'v':('x',np.array([2.,4.]))},coords={'x':np.array([2,1])})
        source,plan,result=self.run_case(ds,recipe(('x',)))
        index=ds._indexes['x'].index
        cache=index.__dict__['_cache']; before=dict(cache)
        with patch.object(pd.Index,'get_loc',side_effect=AssertionError('row membership used pandas lookup')):
            output=self.e.explain_row(plan,source,result,{'x':1},limit=1)
        self.assertEqual(json.loads(output.to_json())['columns'][0]['value'],4.)
        self.assertEqual(set(cache),set(before))
        for name,value in before.items(): self.assertIs(cache[name],value)
    def test_owned_close_failure_is_not_suppressed_by_unrelated_caller_except(self):
        source,plan,result=self.run_case(dataset({'v':((),[3.],'float64',None)},{}),recipe())
        from replicatetable import _result
        from replicatetable._replay import _require_exact_replay
        original=_result._result_chunks; cleanup_errors=[]; caught=None; caller_error=None
        class BrokenClose:
            def __init__(self,value): self.inner=original(value)
            def __iter__(self): return self
            def __next__(self): return next(self.inner)
            def close(self):
                self.inner.close(); error=Refusal('invalid_result'); cleanup_errors.append(error); raise error
        try: raise LookupError('unrelated caller error')
        except LookupError as unrelated:
            caller_error=unrelated
            original_traceback=unrelated.__traceback__
            with admission._required_inputs(plan=plan,snapshot=source,result=result), \
                 patch.object(_result,'_result_chunks',BrokenClose):
                try: _require_exact_replay(plan,source,result)
                except BaseException as error: caught=error
            self.assertIs(unrelated.__traceback__,original_traceback)
        self.assertTrue(cleanup_errors)
        self.assertIs(caught,cleanup_errors[0])
        self.assertEqual(caught.code,'invalid_result')
        # Python reattaches the caller's active exception at the final raise.
        # It is suppressed, unchanged caller state, not an owned private frame.
        self.assertIs(caught.__context__,caller_error)
        self.assertTrue(caught.__suppress_context__); self.assertIsNone(caught.__cause__)
        current=caught.__traceback__; depth=0
        while current is not None:
            depth+=1; self.assertLessEqual(depth,16)
            self.assertNotIn(current.tb_frame.f_code.co_name,
                ('_compare_replay','_retire_replay_streams','_execute_memory','_compute_records','_owned_attempt'))
            if current.tb_frame.f_code.co_name=='_require_exact_replay':
                for name in ('plan','source','result'): self.assertIsNone(current.tb_frame.f_locals[name])
            current=current.tb_next
    def test_measurement_and_weight_dtypes_require_canonical_numeric_names(self):
        value=structural_example()
        for field in ('source_dtype','converted_dtype','output_dtype'): value['columns'][0][field]='<i8'
        self.refused('invalid_explanation',self.e.RowExplanation,**value)
        value=staged_example(True); value['columns'][0]['weight']['dtype']='<f8'
        self.refused('invalid_explanation',self.e.RowExplanation,**value)
    def test_stored_key_lookup_follows_fresh_full_required_input_admission(self):
        source,plan,result=self.run_case(dataset({'v':(('x',),[3.],'float64',None)},
                                              {'x':([2],'int64')}),recipe(('x',)))
        guarded=[]; original_guard=admission._guard; original_query=self.e._query
        def guard(*arguments,**keywords):
            value=original_guard(*arguments,**keywords); guarded.append(True); return value
        def query(*arguments):
            active=admission._ACTIVE.get()
            self.assertTrue(guarded,'stored-key allocation preceded complete fresh admission')
            self.assertIsNotNone(active); self.assertIs(active.plan,plan); self.assertIs(active.result,result)
            self.assertEqual(active.required_dataset_count,3)
            return original_query(*arguments)
        with patch.object(admission,'_guard',guard),patch.object(self.e,'_query',query):
            output=self.e.explain_row(plan,source,result,{'x':2},limit=1)
        self.assertEqual(json.loads(output.to_json())['key'],{'x':2})
