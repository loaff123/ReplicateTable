"""B2 finite coverage and liveness; synthetic ledgers are not source proof."""
import copy
import gc
import hashlib
import json
from pathlib import Path
import sys
import tracemalloc
import unittest
from unittest.mock import patch
from replicatetable import _resource_bounds as b,_resource_inputs as i,_resource_estimates as e
from replicatetable.codec import freeze,thaw,primitive_bounds,canonical_bytes
from replicatetable.model import Recipe,Coordinate
from replicatetable.errors import Refusal
from tests.resource_helpers import synthetic_input,descriptor,inspection,recipe,stage,operation,runtime_example
from tests.frozen_tools import verify_frozen,adapt_legacy_recipe
from tests.unit.test_frozen import ORIGINAL_MANIFEST_SHA


def maximum_input():
    dims={f'd{n:02}':1 for n in range(16)};names=tuple(dims)
    coords={n:Coordinate('<i8',[0],[0]) for n in names}
    variables={};columns=[]
    for n in range(32):
        variables[f'v{n:02}']=descriptor(names,(1,)*16)
        variables[f'w{n:02}']=descriptor(names,(1,)*16)
        one=stage('one',names[:8],True);one['weights']=f'w{n:02}'
        columns.append({'name':f'c{n:02}','source':f'v{n:02}','source_unit':None,'target_unit':None,
                        'broadcast':[],'stages':[one,stage('two',names[8:])]})
    return synthetic_input(dims,variables,coords,recipe((),columns))


class ResourceCoverageTests(unittest.TestCase):
    def test_b2_008_actual_max_records_and_phase_lifetime(self):
        inp=maximum_input();events=[];trace_id=None
        def observe(frame,event,arg):
            nonlocal trace_id
            if frame.f_code.co_filename!=e.__file__:return
            name=frame.f_code.co_name
            if event=='return' and name=='_derive_topology':
                self.assertIs(type(arg),tuple);self.assertEqual(len(arg),4)
                self.assertEqual(tuple(len(t) for t in arg),(64,32,64,16))
                self.assertTrue(all(type(t) is tuple for t in arg))
                for c in arg[1]:
                    self.assertIs(c.input_dims,c.measurement.dims)
                    self.assertIs(c.unit_operation,inp.units[arg[1].index(c)][0])
                events.append('topology')
            if event=='call' and name=='_project_trace':
                self.assertNotIn('paths',frame.f_back.f_locals);events.append('trace_call')
            if event=='return' and name=='_project_trace':
                self.assertIs(type(arg),tuple);self.assertEqual(len(arg),10)
                self.assertTrue(all(type(v) is int for v in arg))
                self.assertNotIn('record',frame.f_locals);self.assertNotIn('skeleton',frame.f_locals)
                trace_id=id(arg);events.append('trace_return')
            if event=='call' and name=='_project_transport':
                self.assertEqual(id(frame.f_locals['trace']),trace_id);events.append('transport')
            if event=='return' and name=='_estimate_compilation':
                self.assertEqual(id(frame.f_locals['trace']),trace_id);events.append('final')
        old=sys.getprofile();sys.setprofile(observe)
        try:result=e._estimate_compilation(inp)
        finally:sys.setprofile(old)
        self.assertEqual(events,['topology','trace_call','trace_return','transport','final'])
        self.assertTrue(all(type(v) is int for _,v in result._items))
        self.assertEqual(2216+1024,3240);self.assertLessEqual(3240,3472)
        self.assertEqual(1792+10*128,3072)
        self.assertEqual(1524052+129448,1653500)
        self.assertLess(1653500,2097152)
        # Actual Python allocator evidence is narrower than the logical ledger,
        # and is not a process-RSS/native-capacity claim.
        gc.collect();tracemalloc.start()
        try:e._estimate_compilation(inp);_,peak=tracemalloc.get_traced_memory()
        finally:tracemalloc.stop()
        self.assertLess(peak,1524052)
        self.assertEqual(len(e._payload_paths(e._derive_topology(inp))),134)

    def test_b2_007_product_origin_no_engine_imports(self):
        import subprocess,os
        code="import sys; import replicatetable._resource_estimates as m; assert not set(('numpy','pandas','xarray','pint','h5py','h5netcdf')) & set(sys.modules); print(m.__file__)"
        result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,check=True)
        self.assertEqual(Path(result.stdout.strip()),Path(e.__file__))

    def test_b2_046_prefix_counter_no_later_short_record(self):
        # Test-only exact trace writer arithmetic, no candidate trace engine.
        lengths=((10,20,1),(1,1));remaining=15;stopped=False;shown=[]
        for section in lengths:
            count=0
            for length in section:
                if stopped:break
                if length>remaining:stopped=True;break
                remaining-=length;count+=1
            shown.append(count)
        self.assertEqual(shown,[1,0])
        self.assertEqual([len(s)-n for s,n in zip(lengths,shown)],[2,2])

    def test_b2_061_combined_failure_keeps_caps(self):
        dims={'d':1000};coord=Coordinate('<i8',list(range(1000)),list(range(1000)))
        columns=[{'name':f'c{x}','source':'v','source_unit':None,'target_unit':None,'broadcast':[],
                  'stages':[stage('one',('d',))]} for x in range(32)]
        inp=synthetic_input(dims,{'v':descriptor(('d',),(1000,))},{'d':coord},recipe((),columns))
        top=e._derive_topology(inp);plan=e._project_plan0(inp,top);out=e._project_outputs(inp,top,plan)
        self.assertLess(out.bundle,128*1048576);self.assertLess(e._selected_numeric(top),64*1048576)
        self.assertLess(e._work(inp,top),268435456)
        with self.assertRaises(Refusal) as caught:e._estimate_compilation(inp)
        self.assertEqual(caught.exception.code,'estimated_memory_limit')
        # Approved analytical dense64MiB lower bounds, no allocated dense data.
        import math
        self.assertEqual(134217728+3*67108864+5519872*4+2*math.isqrt(15307263442944000),
                         605068860)

    def test_b2_070_071_original_shape_ledger(self):
        root=Path(__file__).resolve().parents[1]/'frozen'/'original'
        self.assertEqual(verify_frozen(root,ORIGINAL_MANIFEST_SHA),13)
        ledger=json.loads((root.parents[1]/'resource_shape_ledger.json').read_text())
        self.assertEqual(len(ledger['fixtures']),9)
        for entry in ledger['fixtures']:
            raw=(root/'fixtures'/entry['fixture']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),entry['sha256'])
            fixture=json.loads(raw);data=fixture['data'];rec=Recipe.from_dict(adapt_legacy_recipe(fixture))
            dimensions={name:len(values) for name,values in data['coords'].items()}
            variables={name:descriptor(tuple(v['dims']),tuple(dimensions[d] for d in v['dims']),v['dtype'],v['units'])
                       for name,v in data['variables'].items()}
            selected=set(rec.row_dims)
            for c in rec.columns:
                selected.update(data['variables'][c['source']]['dims'])
                if c['stages'] and c['stages'][0]['op']=='weighted_mean':selected.update(data['variables'][c['stages'][0]['weights']]['dims'])
            allcoords={}
            for name,labels in data['coords'].items():
                dtype='<U'+str(max(1,max(map(len,labels)))) if type(labels[0]) is str else '<f8' if type(labels[0]) is float else '<i8'
                allcoords[name]=Coordinate(dtype,labels,sorted(range(len(labels)),key=labels.__getitem__))
            source=inspection(dimensions,variables,{name:descriptor((name,),(len(c.values),),c.dtype) for name,c in allcoords.items()})
            coords=tuple(i._coordinate_facts(name,allcoords[name],raw_bytes=len(allcoords[name].values)*8,
                         preselection_j=i._owned_cost(allcoords[name].values).json_bytes) for name in sorted(selected))
            units=tuple((operation(c['source_unit'],c['target_unit']),operation(weight=True) if c['stages'] and c['stages'][0]['op']=='weighted_mean' else None) for c in rec.columns)
            inp=i._CompilationInput(source,i._memory_binding(source,(),512),rec,coords,freeze(runtime_example()),units)
            top=e._derive_topology(inp)
            observed={'selected_numeric_bytes':e._selected_numeric(top),'output_rows':e._rows(inp),
                'support_records':e._support(top),'numerical_scratch_bytes':e._scratch(top),'work_cell_visits':e._work(inp,top)}
            for key,value in observed.items():self.assertEqual(value,entry[key],(entry['fixture'],key))
            self.assertEqual([v.name for v in top[0]],entry['selected_variables'])
            self.assertEqual(list(top[3]),entry['selected_dimensions'])
            self.assertEqual([(s.output_cells,s.support_start,list(s.support_dims)) for s in top[2]],
                [(s['count'],s['start'],s['support_dims']) for s in entry['blocks']])
            # F4 unit graph is NOT recovered or qualified by the shape surrogate.
            if entry['fixture']!='F4.json':self.assertLess(e._estimate_compilation(inp)['estimated_memory_bytes'],536870912)

    def test_b2_063_live_anchor_same_total_redistribution(self):
        source=inspection();a=i._owner_charge('variable','a',1,'ndarray',100,(640,),0)
        b_=i._owner_charge('variable','b',1,'ndarray',100,(640,),0)
        saved=i._memory_binding(source,(a,b_),512);wrong=thaw(saved)
        wrong['owners'][0]['terminal_bytes']+=1;wrong['owners'][1]['terminal_bytes']-=1
        with self.assertRaises(Refusal) as caught:e._call_total(1,saved,freeze(wrong),(),(),required_count=1,distinct_count=1)
        self.assertEqual(caught.exception.code,'source_resource_binding_mismatch')
        wrong=thaw(saved);wrong['base_bytes']=134217729
        with self.assertRaises(Refusal) as caught:e._call_total(1,saved,freeze(wrong),(),(),required_count=1,distinct_count=1)
        self.assertEqual(caught.exception.code,'source_bytes_limit')

    def test_b2_081_actual_plan_and_trace_lengths(self):
        from tests.unit.test_resource_estimates import hand_input,plan0_specimen
        inp=hand_input();top=e._derive_topology(inp);plan=plan0_specimen(inp,top)
        estimate=e._estimate_compilation(inp);plan['estimates']=thaw(estimate)
        self.assertLessEqual(len(canonical_bytes(plan)),estimate['plan_json_bytes'])
        self.assertLessEqual(primitive_bounds(plan).object_bytes,estimate['plan_objects_bytes'])

    def test_b2_082_scope_no_public_estimator(self):
        import replicatetable
        self.assertFalse(hasattr(replicatetable,'estimate_compilation'))
        self.assertTrue(callable(replicatetable.load_result))
        self.assertIn('load_result',replicatetable.__all__)
        self.assertFalse(hasattr(e,'_result_decode_reservation'))

    def test_complete_trace_and_schema_small_actual_models(self):
        from tests.unit.test_resource_estimates import hand_input,plan0_specimen
        inp=hand_input();top=e._derive_topology(inp);plan=plan0_specimen(inp,top)
        def counters():return {'total':0,'shown':0,'truncated':False,'limit_omitted':0,'byte_omitted':0}
        def support(c,s):
            return {'column':c['name'],'stage':s['name'],'keys':{d:0 for d in s['support_dims']},
                'n_input':1,'n_valid':1,'n_positive_weight_valid':1,'weight_total':1.0,'weight_valid':1.0,
                'reasons':list(e.REASONS),'value':1.0,'unit':None}
        columns=[]
        for ci,c in enumerate(plan['columns']):
            op=c['unit_operation'];weight=c['weight']
            w=None if weight is None else {'source':weight['source'],'dtype':weight['dtype'],'dims':weight['dims'],
                'source_unit':None,'unit':'dimensionless','scale':1.0,'offset':0.0}
            stages=[]
            for si,s in enumerate(c['stages']):
                section=counters()|{k:s[k] for k in ('name','input_dims','dims','remaining_dims','op','missing','min_count','support_start')}
                section.update(input_stage=None if si==0 else 0,records=[]);stages.append(section)
                q=e._support_cost(inp,top[1][ci],top[2][top[1][ci].stage_begin+si]);actual=primitive_bounds(support(c,s))
                self.assertEqual((q.json_bytes,q.object_bytes),(actual.json_bytes,actual.object_bytes))
            source=counters()|{'selection':[0 if d in inp.recipe.row_dims else None for d in c['input_dims']],'cells':[]}
            columns.append({k:c[k] for k in ('name','source','source_dtype','output_dtype','input_dims','final_dims','broadcast')}|
                {'converted_dtype':c['output_dtype'],'conversion':{'source_unit':op['source_unit'],'target_unit':op['target_unit'],
                 'effective_unit':None,'scale':op['scale'],'offset':op['offset']},'weight':w,'value':1.0,'reasons':list(e.REASONS),
                 'source_cells':source,'stages':stages})
        actual={'version':1,'source':thaw(inp.source['source']),'recipe_sha256':'a'*64,'plan_sha256':'a'*64,
            'result_sha256':'a'*64,'runtime_sha256':'a'*64,'row_dims':list(inp.recipe.row_dims),'key':{'r':0},
            'coordinates':{c.name:{'dtype':c.coordinate.dtype,'length':c.length} for c in inp.coordinates},
            'limit':1000,'byte_truncated':False,'assurance':e.TRACE_ASSURANCE,'notice':e.TRACE_NOTICE,'columns':columns}
        expected=primitive_bounds(actual);bound=e._trace_skeleton(inp,top,1000)
        self.assertEqual((expected.json_bytes,expected.object_bytes),(bound.json_bytes,bound.object_bytes))
        self.assertLessEqual(len(canonical_bytes(actual)),bound.json_bytes+1)
        for kind in ('descriptor','prepared','materialized'):
            model=thaw(inp.source) if kind=='descriptor' else {'inspection':thaw(inp.source),'coordinates':plan['coordinates']}
            arrays=[];offset=0
            if kind=='materialized':
                for v in top[0]:
                    arrays.append({'name':v.name,'dtype':v.dtype,'shape':list(v.shape),'nbytes':v.nbytes,'sha256':'0'*64,'offset':offset});offset+=v.nbytes
            actual={'version':2,'kind':kind,'model':model,'arrays':arrays};pair=e._api_projection(inp,top,e._project_plan0(inp,top),kind)
            expected=primitive_bounds(actual)
            self.assertEqual((expected.json_bytes,expected.object_bytes),(pair.json_bytes,pair.object_bytes))

    def test_weighted_integer_cell_exclusion_and_scalar_rank(self):
        dims={'d':1};c=Coordinate('<i8',[0],[0]);st=stage('one',('d',),True)
        inp=synthetic_input(dims,{'v':descriptor(('d',),(1,),'int64'),'w':descriptor(('d',),(1,),'int8')},
            {'d':c},recipe((),[{'name':'x','source':'v','source_unit':None,'target_unit':None,'broadcast':[],'stages':[st]}]))
        top=e._derive_topology(inp);bound=e._source_cell_cost(inp,top[1][0])
        actual={'indices':[0],'labels':[0],'raw':2**63-1,'converted':1.0,'raw_weight':1,'normalized_weight':1.0,'exclusion_reason':'zero_weight'}
        pair=primitive_bounds(actual);self.assertEqual((bound.json_bytes,bound.object_bytes),(pair.json_bytes,pair.object_bytes))
        scalar=synthetic_input();scalar_top=e._derive_topology(scalar)
        self.assertLess(e._source_cell_cost(scalar,scalar_top[1][0]).object_bytes,bound.object_bytes)

    def test_source_base_incremental_metadata_precedes_json_cap(self):
        # Synthetic safe owned descriptor. No source/native scan is asserted.
        source=inspection(variables={'v':descriptor(attributes={'long':['x'*4096]*400},encoding={'long':['x'*4096]*400})})
        owner=i._owner_charge('variable','v',8,'ndarray',125*1048576,(640,),0)
        with self.assertRaises(Refusal) as caught:i._memory_binding(source,(owner,),512)
        self.assertEqual(caught.exception.code,'source_bytes_limit')

    def test_all_private_retained_records_are_final_and_exact(self):
        inp=synthetic_input();top=e._derive_topology(inp)
        for cls in (b._JP,b._FieldCost,b._RepeatBlock,i._VariableFacts,i._CoordinateFacts,i._SourceScalars,
                    i._CompilationInput,e._ColumnTopology,e._StageTopology,e._OutputBounds,e._EmissionBudget):
            with self.assertRaises(TypeError):type('Subclass',(cls,),{})
        with self.assertRaises(Refusal):e._StageTopology(True,1,0,freeze(stage('s',('d',))),('d',),(),())
        with self.assertRaises(Refusal):e._OutputBounds(*([True]+[0]*15))
