"""B2 formula projections only. Synthetic complete metadata, no native admission."""
import importlib
import unittest
from unittest.mock import patch
from replicatetable.codec import primitive_bounds,canonical_bytes,thaw,OwnedMap
from replicatetable.model import Coordinate
from replicatetable.errors import Refusal
from tests.resource_helpers import synthetic_input,descriptor,recipe,stage


def estimates():
    name='replicatetable._resource_estimates'
    assert importlib.util.find_spec(name) is not None,'B2 estimator module is missing'
    return importlib.import_module(name)


def hand_input():
    dims={'r':2,'a':3,'b':4}
    coords={n:Coordinate('<i8',list(range(v)),list(range(v))) for n,v in dims.items()}
    vars={'v':descriptor(('r','a','b'),(2,3,4)), 'w':descriptor(('a',),(3,)),
          'd':descriptor(('r',),(2,))}
    rec=recipe(('r',),[
        {'name':'first','source':'v','source_unit':None,'target_unit':None,'broadcast':[],
         'stages':[stage('one',('b',),True),stage('two',('a',))]},
        {'name':'second','source':'d','source_unit':None,'target_unit':None,'broadcast':[],'stages':[]}])
    return synthetic_input(dims,vars,coords,rec)


def plan0_specimen(inp,top):
    columns=[]
    for c in top[1]:
        stages=[]
        for s in top[2][c.stage_begin:c.stage_begin+c.stage_count]:
            sr=thaw(s.recipe_stage)
            sr.update(input_dims=list(s.input_dims),input_shape=[inp.source['dimensions'][d] for d in s.input_dims],
                remaining_dims=list(s.remaining_dims),remaining_shape=[inp.source['dimensions'][d] for d in s.remaining_dims],
                support_dims=list(s.support_dims),support_count=s.output_cells,support_start=s.support_start)
            # CompiledStage intentionally excludes weighted recipe-only fields.
            sr.pop('weights',None);sr.pop('weight_unit',None);stages.append(sr)
        weight=None if c.weight is None else {'source':c.weight.name,'dtype':c.weight.dtype,
            'dims':list(c.weight.dims),'shape':list(c.weight.shape),'unit_operation':thaw(c.weight_unit_operation)}
        columns.append({'name':c.recipe_column['name'],'source':c.measurement.name,
            'source_dtype':c.measurement.dtype,'input_dims':list(c.input_dims),
            'input_shape':list(c.measurement.shape),'final_dims':list(c.final_dims),
            'broadcast':list(c.broadcast),'output_dtype':c.output_dtype,
            'unit_operation':thaw(c.unit_operation),'weight':weight,'stages':stages})
    return {'version':2,'formula_version':2,'source':thaw(inp.source['source']),
        'recipe':inp.recipe.to_dict(),'runtime':thaw(inp.runtime),
        'coordinates':{f.name:f.coordinate.to_dict() for f in inp.coordinates},
        'selected':{'variables':[v.name for v in top[0]], 'dimensions':list(top[3]),
                    'numeric_bytes':estimates()._selected_numeric(top)},'columns':columns,'resource_binding':thaw(inp.binding)}


class ResourceEstimateTests(unittest.TestCase):
    def test_b2_011_union_no_per_column_double_charge(self):
        m=estimates(); inp=hand_input(); t=m._derive_topology(inp)
        self.assertEqual([v.name for v in t[0]],['d','v','w'])
        self.assertEqual(m._selected_numeric(t),8*(24+3+2))
        self.assertEqual(t[3],('a','b','r'))

    def test_b2_012_selected_coordinate_union_and_missing(self):
        m=estimates(); inp=synthetic_input({'r':1},{'v':descriptor()}, {},
            recipe(('r',),[{'name':'x','source':'v','source_unit':None,'target_unit':None,'broadcast':['r'],'stages':[]}]))
        with self.assertRaises(Refusal) as e:m._derive_topology(inp)
        self.assertEqual(e.exception.code,'missing_row_key')

    def test_b2_013_scalar(self):
        m=estimates(); inp=synthetic_input();t=m._derive_topology(inp)
        self.assertEqual((m._rows(inp),m._support(t),m._scratch(t),m._work(inp,t),m._selected_numeric(t)),(1,0,32,8,8))
        self.assertEqual(t[3],())

    def test_b2_014_hand_work_scratch_offsets(self):
        m=estimates();inp=hand_input();t=m._derive_topology(inp)
        self.assertEqual((m._rows(inp),m._support(t),m._scratch(t),m._work(inp,t)),(2,8,3760,642))
        self.assertEqual([(s.input_cells,s.output_cells,s.support_start) for s in t[2]],[(24,6,0),(6,2,6)])
        self.assertEqual(t[2][0].remaining_dims,('r','a'))
        self.assertEqual(t[2][0].support_dims,('a','r'))

    def test_b2_015_residual_before_broadcast(self):
        m=estimates(); c=Coordinate('<i8',[0],[0]); inp=synthetic_input({'d':1},{'v':descriptor(('d',),(1,))},{'d':c})
        with self.assertRaises(Refusal) as e:m._derive_topology(inp)
        self.assertEqual(e.exception.code,'residual_dimension')

    def test_b2_032_plan_projection_actual_numeric_slack(self):
        m=estimates(); inp=hand_input();top=m._derive_topology(inp)
        plan0=plan0_specimen(inp,top);pair=m._project_plan0(inp,top);p=primitive_bounds(plan0)
        self.assertEqual((pair.json_bytes,pair.object_bytes),(p.json_bytes,p.object_bytes))
        bound=pair.json_bytes+1+m.ESTIMATE_COST.json_bytes+1
        actual=plan0|{'estimates':{k:2 if k=='formula_version' else 2**63-1 for k in m.ESTIMATE_KEYS}}
        self.assertEqual(primitive_bounds(actual).json_bytes+1-bound,57)
        self.assertLessEqual(len(canonical_bytes(actual)),bound-364)
        self.assertEqual(31+30*13,421)

    def test_b2_033_result_projection_scalar(self):
        m=estimates(); inp=synthetic_input();t=m._derive_topology(inp)
        p=m._project_result(inp,t)
        reasons=['missing_values','insufficient_count','zero_weight']
        actual={'version':1,'row_dims':[],'units':{'out':None},'rows':[{'keys':{},'values':{'out':1.0},'reasons':{'out':reasons}}],'support':[]}
        bound=primitive_bounds(actual)
        self.assertEqual(p.json_bytes,bound.json_bytes)
        self.assertEqual(p.object_bytes,bound.object_bytes+136)

    def test_b2_034_positional_header_collision(self):
        m=estimates()
        self.assertEqual(tuple(m._table_header_field(i,1,2) for i in range(5)),('key:00','value:00','reasons:00','value:01','reasons:01'))
        self.assertEqual(len(set(tuple(m._table_header_field(i,16,32) for i in range(80)))),80)
        self.assertEqual(len(tuple(m._support_header_field(i,16) for i in range(23))),23)

    def test_b2_035_csv_field_formula(self):
        m=estimates()
        self.assertEqual(m._csv_record_bound((2,32,0)),37)
        for s in ('','a,b','"','\n','😀'):
            import csv,io
            out=io.StringIO(newline='');csv.writer(out,lineterminator='\n',quoting=csv.QUOTE_ALL).writerow([s])
            self.assertLessEqual(len(out.getvalue().encode()),m._csv_string(s)+1)

    def test_b2_036_manifest_full_runtime_paths(self):
        m=estimates();inp=hand_input();t=m._derive_topology(inp)
        paths=m._payload_paths(t)
        self.assertEqual(len(paths),10)
        self.assertNotIn('manifest.json',paths)
        full=m._manifest_cost(inp,t,include_runtime=True);bare=m._manifest_cost(inp,t,include_runtime=False)
        runtime=m._runtime_cost(inp.runtime);key=m._literal_cost('runtime')
        self.assertEqual(full.object_bytes-bare.object_bytes,128+key.object_bytes+runtime.object_bytes)

    def test_b2_037_receipts_include_finding(self):
        m=estimates();inp=synthetic_input()
        shapes=m._receipt_costs(inp.source['source'])
        self.assertEqual(len(shapes),4)
        self.assertGreater(shapes[0].object_bytes,512+128*10)
        self.assertGreater(m._finding_cost().json_bytes,6*512)

    def test_b2_038_bundle_sum_paths(self):
        m=estimates();inp=hand_input();t=m._derive_topology(inp);p=m._project_plan0(inp,t);o=m._project_outputs(inp,t,p)
        self.assertEqual(o.bundle,sum((o.recipe_json,o.plan_json,o.result_json,o.table_csv,o.stage_csv,o.schema_json,o.report,o.manifest_json)))
        self.assertEqual(len('support/c31-s01.schema.json'.encode()),27)

    def test_b2_040_report_notice_and_display(self):
        m=estimates();self.assertEqual(len(m.REPORT_NOTICE.encode()),222)
        import json,html
        for s in ('',' ','"<&','😀'):
            displayed=html.escape(json.dumps(s,ensure_ascii=True).replace(' ','\\u0020'),quote=False).encode()
            self.assertLessEqual(len(displayed),6*len(s.encode())+2)

    def test_b2_041_report_preview_coefficients(self):
        m=estimates()
        x=m._preview_bound(99,10,20);y=m._preview_bound(100,10,20)
        self.assertEqual(y-x,52)
        self.assertEqual(m._preview_bound(101,10,20),y)
        self.assertEqual(x,512+10+99*(32+20))

    def test_b2_042_trace_skeleton_all_fields(self):
        m=estimates();inp=hand_input();t=m._derive_topology(inp)
        sk=m._trace_skeleton(inp,t,1000)
        self.assertGreater(sk.object_bytes,10000)
        tr=m._project_trace(inp,t,limit=1000)
        self.assertEqual(tr[0],sk.json_bytes+1)
        self.assertEqual(tr[1],sk.object_bytes+1024)
        self.assertEqual(tr[5],12+3+1+1)

    def test_b2_043_cell_dtype_tight(self):
        m=estimates()
        costs=[]
        for dtype in ('int64','float64'):
            inp=synthetic_input({'d':1},{'v':descriptor(('d',),(1,),dtype)},
                {'d':Coordinate('<i8',[0],[0])},recipe((),[{'name':'x','source':'v','source_unit':None,
                    'target_unit':None,'broadcast':[],'stages':[stage('s',('d',))]}]))
            t=m._derive_topology(inp);costs.append(m._source_cell_cost(inp,t[1][0]))
        self.assertEqual((costs[0].object_bytes,costs[1].object_bytes),(4752,4804))
        self.assertEqual(costs[1].json_bytes-costs[0].json_bytes,76)

    def test_b2_044_trace_limit_compilation_fixed(self):
        m=estimates();inp=hand_input();t=m._derive_topology(inp)
        a=m._project_trace(inp,t,limit=1);b=m._project_trace(inp,t,limit=1000)
        self.assertLess(a[5],b[5])
        for limit in (0,1001,True):
            with self.assertRaises(Refusal):m._project_trace(inp,t,limit=limit)

    def test_b2_045_trace_components_exact(self):
        m=estimates();inp=hand_input();t=m._derive_topology(inp);tr=m._project_trace(inp,t,limit=1000)
        self.assertEqual(tr[4],tr[1]+tr[6]+512+128*tr[5]+8*tr[5]+
            tr[7]+5*tr[8]+256+32768+tr[9])
        self.assertEqual(tr[9],5519872)

    def test_b2_047_wrapper_trace_counted_once(self):
        m=estimates();shell=m._api_shell('explanation')
        self.assertEqual((shell.json_bytes,shell.object_bytes),(251,2436))
        result=m._api_shell('result')
        self.assertLess(result.object_bytes,65536)

    def test_b2_048_complete_formula_and_transport(self):
        m=estimates();inp=synthetic_input();e=m._estimate_compilation(inp)
        self.assertIs(type(e),OwnedMap)
        self.assertEqual(tuple(sorted(e)),tuple(sorted(m.ESTIMATE_KEYS)))
        self.assertEqual(e['verify_bytes'],e['common_bytes']+3*e['result_objects_bytes']+6*e['result_json_bytes'])
        self.assertEqual(e['explain_bytes'],e['verify_bytes']+e['trace_objects_bytes']+3*e['trace_bytes'])
        self.assertEqual(e['estimated_memory_bytes'],e['explain_bytes'])
        self.assertGreater(e['transport_reserve_bytes'],e['selected_numeric_bytes'])

    def test_b2_007_no_serializer_or_forest_copy_during_estimation(self):
        m=estimates();inp=hand_input()
        with (patch('replicatetable.codec.canonical_bytes',side_effect=AssertionError('serialization')),
             patch('replicatetable.codec.freeze',side_effect=AssertionError('copy')),
             patch('replicatetable.codec.thaw',side_effect=AssertionError('copy'))):
            self.assertEqual(m._estimate_compilation(inp)['work_cell_visits'],642)

    def test_b2_049_standalone_equation(self):
        m=estimates()
        self.assertEqual(m._standalone_reservation(1000,20,30,40),134217728+1000+2*40+2097152+3*65536+65536+1434532+8081875)
        self.assertEqual(m._framed_size(20,40),84)

    def test_b2_050_parent_reservation_boundaries(self):
        m=estimates();base=134217728+2097152+3*65536
        self.assertEqual(m._parent_reservation((10,20),100,2),base+965*30+100+1024)
        cap=(536870912-base)//965
        rem=536870912-base-965*cap
        self.assertEqual(m._parent_reservation((cap,),rem,0),536870912)
        with self.assertRaises(Refusal):m._parent_reservation((cap,),rem+1,0)
        with self.assertRaises(Refusal):m._parent_reservation((16*1048576,),0,0)

    def test_b2_051_052_repaired_scan_and_nonresult_reservation(self):
        m=estimates();raw=b'{"'+b'x'*1028+b'":0}'
        self.assertEqual(len(raw),1034)
        scan=m._nonresult_prepass(raw,metadata_limit=1048576,baseline_bytes=136314880)
        self.assertEqual((scan.object_bytes,scan.key_scratch_bytes,scan.scan_peak_bytes),(5008,5406,10286))
        # Scan equality is independent of the full decode reservation.
        from replicatetable.codec import json_prepass
        self.assertEqual(json_prepass(raw,object_limit=10286).scan_peak_bytes,10286)
        with self.assertRaises(Refusal):json_prepass(raw,object_limit=10285)
        self.assertEqual(m._nonresult_decode_bytes(scan),5*1034+3*5008)
        self.assertEqual(m._result_slot_reservation(100,20,40),3*100+6*20+40)
        with self.assertRaises(Refusal):m._result_slot_reservation(100,20,40,validator_forests=1)

    def test_b2_062_anchor_full_equality_and_caches(self):
        m=estimates(); inp=synthetic_input();saved=inp.binding
        result=m._call_total(536870812,saved,saved,(40,),(60,),required_count=3,distinct_count=2)
        self.assertTrue(result['admitted']);self.assertEqual(result['total_bytes'],536870912)
        result=m._call_total(536870812,saved,saved,(40,),(61,),required_count=3,distinct_count=2)
        self.assertFalse(result['admitted'])
        from replicatetable.codec import freeze,thaw
        for diff in (-1,1):
            wrong=thaw(saved);wrong['base_bytes']+=diff
            with self.assertRaises(Refusal) as e:m._call_total(1,saved,freeze(wrong),(),(),required_count=1,distinct_count=1)
            self.assertEqual(e.exception.code,'source_resource_binding_mismatch')
        with self.assertRaises(Refusal):m._call_total(1,saved,saved,(),(536870913,),required_count=1,distinct_count=1)

    def test_b2_080_emission_precedence_and_exact_counter(self):
        m=estimates();budget=m._EmissionBudget('report.html','report',10,20,0)
        self.assertEqual(m._check_emission(8,2,budget),10)
        with self.assertRaises(Refusal) as e:m._check_emission(10,11,budget)
        self.assertEqual((e.exception.code,e.exception.exit_code),('resource_estimate_mismatch',3))
        budget=m._EmissionBudget('report.html','report',20,20,0)
        with self.assertRaises(Refusal) as e:m._check_emission(20,1,budget)
        self.assertEqual((e.exception.code,e.exception.exit_code),('report_bytes_limit',2))

    def test_b2_080_complete_actual_counter_membership_and_totals(self):
        m=estimates();inp=synthetic_input();top=m._derive_topology(inp)
        output=m._project_outputs(inp,top,m._project_plan0(inp,top))
        self.assertTrue(hasattr(m,'_finish_emission'),'Missing exact actual-counter completion gate')
        from replicatetable.codec import freeze,thaw
        files=freeze({name:{'size_bytes':1,'sha256':'0'*64} for name in m._payload_paths(top)+('manifest.json',)})
        estimate_map=m._estimate_compilation(inp)
        budgets=tuple(m._EmissionBudget(n,'report' if n=='report.html' else 'recipe' if n=='recipe.json' else 'metadata' if n in ('plan.json','schema.json') else 'bundle',
            size,cap,0) for n,size,cap in [('recipe.json',output.recipe_json,1048576),('plan.json',output.plan_json,16777216),('result.json',output.result_json,134217728),
                ('table.csv',output.table_csv,134217728),('schema.json',output.schema_json,16777216),('report.html',output.report,8388608)])
        del top
        counters=m._finish_emission(budgets,estimate_map,files,rows=1,support_records=0)
        self.assertIs(counters['files'],files)
        self.assertEqual((counters['payload_bytes'],counters['manifest_bytes'],counters['bundle_bytes']),(6,1,7))
        wrong=thaw(files);wrong['report.html']['size_bytes']=output.report+1
        with self.assertRaises(Refusal) as e:m._finish_emission(budgets,estimate_map,freeze(wrong),rows=1,support_records=0)
        self.assertEqual(e.exception.code,'resource_estimate_mismatch')
        with self.assertRaises(Refusal):m._finish_emission(budgets,estimate_map,files,rows=2,support_records=0)
        wrong=thaw(files);wrong['extra.json']={'size_bytes':1,'sha256':'0'*64}
        with self.assertRaises(Refusal):m._finish_emission(budgets,estimate_map,freeze(wrong),rows=1,support_records=0)
