"""Private prospective arithmetic, never a native/source admission token."""
import unittest
from unittest.mock import patch
from replicatetable import _resource_estimates as e, resources as r
from replicatetable.errors import Refusal
from tests.unit.test_native_budget_estimates import budget, EXPECTED as REVIEWED

LIMIT = 536870912
W0 = 1434532
W136 = 2913396
N0 = 8375
D0 = 8081875


class NativeBudgetRouteTests(unittest.TestCase):
    def assert_code(self,code,fn,*args,**kwargs):
        with self.assertRaises(Refusal) as caught:fn(*args,**kwargs)
        self.assertEqual(caught.exception.code,code)

    def test_standalone_preserves_two_distinct_fixed_pools_and_held_state(self):
        m=budget();source=4096+10000+65536
        self.assertEqual(m._route_base(source,8,4096),138095300)
        self.assertEqual(m._route_base(source,8,4096,verify=True),139574164)
        self.assertEqual(m._standalone_guard(source,20,30,8,held_coordinates=4096,recipe_objects=8192),146185367)
        # Same K + R protects control and metadata; R/Q are outside the max.
        self.assertEqual(m._standalone_guard(source,2000000,1000000,8,held_coordinates=4096,recipe_objects=8192),151103492)
        self.assertEqual(e._standalone_reservation(1000,20,30,40),146094511)

    def test_raw_file_cap_is_separate_from_full_file_base(self):
        m=budget();full=r.SOURCE_FILE_BYTES_LIMIT+65536+10000
        self.assertGreater(m._route_base(full,0,0),r.SOURCE_MEMORY_BASE_LIMIT)
        self.assert_code('source_bytes_limit',m._route_base,full,0,0,source_kind='memory')
        self.assert_code('invalid_source',m._route_base,full,0,0,source_kind=True)

    def test_decoder_and_wire_exact_scalar_types_and_overflow(self):
        m=budget()
        for fn in (m._decoder_bytes,m._wire_bytes):
            self.assertGreater(fn(1,1),0)
            for pos in (0,1):
                for value in (True,1.0,-1,'1',None,r.COUNT_MAX+1):
                    args=[0,0];args[pos]=value
                    with self.subTest(fn=fn.__name__,pos=pos,value=value):
                        with self.assertRaises(Refusal):fn(*args)
            with self.assertRaises(Refusal):fn(r.COUNT_MAX,1)
        self.assertEqual(m._combined_guard(LIMIT-1,1),LIMIT)
        self.assert_code('estimated_memory_limit',m._combined_guard,LIMIT,1)
        for value in (True,1.0,-1,r.COUNT_MAX+1):
            with self.assertRaises(Refusal):m._combined_guard(value,0)

    def test_saved_plan_raw_retained_through_parse_recipe_and_bootstrap(self):
        m=budget();base=m._route_base(1000,0,0)
        raw=16*1048576;p=100000;recipe=10000
        self.assertEqual(m._saved_plan_parse_guard(base,raw,p,recipe_objects=recipe),base+raw+5*raw+3*p+recipe)
        self.assertEqual(m._load_plan_guard(base,raw,p,recipe,20,30),base+raw+p+recipe+D0)
        self.assert_code('metadata_bytes_limit',m._saved_plan_parse_guard,base,raw+1,p)
        self.assert_code('metadata_bytes_limit',m._load_plan_guard,base,raw+1,p,recipe,20,30)
        boundary=LIMIT-raw-5*raw-3*p-recipe
        self.assertEqual(m._saved_plan_parse_guard(boundary,raw,p,recipe_objects=recipe),LIMIT)
        self.assert_code('estimated_memory_limit',m._saved_plan_parse_guard,boundary+1,raw,p,recipe_objects=recipe)

    def test_later_canonical_guard_never_borrows_saved_estimates(self):
        m=budget();raw=16*1048576;p=100000;recipe=10000
        complete=LIMIT-raw-p-recipe
        self.assertEqual(m._canonical_route_guard(complete,raw_bytes=raw,saved_objects=p,recipe_objects=recipe),LIMIT)
        self.assert_code('estimated_memory_limit',m._canonical_route_guard,complete+1,raw_bytes=raw,saved_objects=p,recipe_objects=recipe)
        # R also persists for compile/prepare even if the plan borrows it.
        self.assertEqual(m._canonical_route_guard(LIMIT-recipe,recipe_objects=recipe),LIMIT)
        self.assert_code('estimated_memory_limit',m._canonical_route_guard,LIMIT-recipe+1,recipe_objects=recipe)
        for row in REVIEWED.values():
            x=row['new'];z=x['plan_objects_bytes']
            self.assertLessEqual(m._canonical_route_guard(x['estimated_memory_bytes'],raw_bytes=raw,saved_objects=z,recipe_objects=z),LIMIT)
        x=REVIEWED['maximum-control']['new'];z=x['plan_objects_bytes']
        self.assertEqual(m._canonical_route_guard(x['estimated_memory_bytes'],raw_bytes=raw,saved_objects=z,recipe_objects=z),303947416)

    def test_corrected_verify_plan_bootstrap_and_sequential_barrier_formula(self):
        m=budget();base=m._route_base(4096+10000+65536,8,4096,verify=True)
        self.assertEqual(m._verify_route_guard(base,20,30,8192,7345,16368),147656039)
        # Padded ordinary plan dominates; two separate summary occurrences.
        raw=16*1048576;p=100000;recipe=8192
        phase=5*raw+3*p+recipe+2*79640
        self.assertEqual(m._verify_route_guard(base,raw,p,recipe,7345,16368),base+phase)
        self.assertEqual(m._verify_route_guard(LIMIT-phase,raw,p,recipe,7345,16368),LIMIT)
        self.assert_code('estimated_memory_limit',m._verify_route_guard,LIMIT-phase+1,raw,p,recipe,7345,16368)
        self.assert_code('metadata_bytes_limit',m._verify_route_guard,base,raw+1,p,recipe,7345,16368)
        self.assert_code('metadata_bytes_limit',m._verify_route_guard,base,20,30,recipe,7346,16368)
        self.assertEqual(m._verify_summary_objects(),79640)

    def test_route_scalars_cannot_be_bool_subclass_or_unbounded(self):
        m=budget()
        class SubInt(int):pass
        calls=((m._route_base,[1000,8,4096]),
               (m._standalone_guard,[1000,20,30,8]),
               (m._saved_plan_parse_guard,[1000,20,30]),
               (m._load_plan_guard,[1000,20,30,40,50,60]),
               (m._verify_route_guard,[1000,20,30,40,50,60]))
        for fn,good in calls:
            for pos in range(len(good)):
                for value in (True,SubInt(1),1.0,-1,r.COUNT_MAX+1):
                    args=good.copy();args[pos]=value
                    with self.subTest(fn=fn.__name__,pos=pos,value=value):
                        with self.assertRaises(Refusal):fn(*args)
        for flag in (1,None,'yes'):
            with self.assertRaises(Refusal):m._route_base(1000,0,0,verify=flag)

    def test_fixed_pools_remain_separate_schedule_facts(self):
        m=budget()
        self.assertEqual(m._SOURCE_HEADER_BYTES,40200)
        self.assertEqual(m._COMMON_HEADER_BYTES,57923)
        self.assertEqual(m._SCANNER_COUNTER_BYTES,12664)
        self.assertEqual(m._CONTROL_PEAK_BYTES,1955604)
        self.assertLess(m._SOURCE_HEADER_BYTES,65536)
        self.assertLess(m._COMMON_HEADER_BYTES,65536)
        self.assertLess(m._CONTROL_PEAK_BYTES,r.CONTROL_STATE_BYTES)

    def test_public_call_diagnostic_still_has_only_three_byte_terms(self):
        from tests.resource_helpers import synthetic_input
        inp=synthetic_input();saved=inp.binding
        result=e._call_total(1000,saved,saved,(40,),(60,),required_count=3,distinct_count=2)
        self.assertEqual(result['total_bytes'],1100)
        self.assertEqual(set(result),{'version','formula_version','baseline_bytes','extra_source_bytes','cache_bytes','total_bytes','limit_bytes','admitted','required_dataset_count','distinct_dataset_count'})

    def test_padded_plan_bytes_use_existing_decoder_and_keep_actual_raw_length(self):
        # A real B1 strict parse of a bounded synthetic canonical plan shape.
        # This is not the future native load_plan or a source/runtime check.
        from replicatetable.codec import canonical_bytes,json_prepass,strict_loads,thaw
        from tests.resource_helpers import synthetic_input
        from tests.unit.test_resource_estimates import plan0_specimen
        m=budget();inp=synthetic_input(kind='file');top=e._derive_topology(inp)
        plan=plan0_specimen(inp,top);plan['estimates']=thaw(e._estimate_compilation(inp))
        canonical=canonical_bytes(plan);raw=canonical+b' '*(r.METADATA_BYTES_LIMIT-len(canonical))
        base=m._route_base(inp.binding['base_bytes'],0,0);recipe=10000
        scan=json_prepass(raw,baseline_bytes=base+len(raw)+recipe)
        self.assertEqual(scan.raw_bytes,16777216)
        expected=base+len(raw)+5*len(raw)+3*scan.object_bytes+recipe
        self.assertEqual(m._saved_plan_parse_guard(base,len(raw),scan.object_bytes,recipe_objects=recipe),expected)
        parsed=strict_loads(raw,baseline_bytes=base+len(raw)+recipe)
        self.assertEqual(parsed,plan)
        self.assertEqual(m._canonical_route_guard(1000,raw_bytes=len(raw)),16778216)
        with patch('replicatetable.codec._Scanner',side_effect=AssertionError('scan before raw cap')):
            self.assert_code('metadata_bytes_limit',json_prepass,raw+b' ')

    def test_legacy_standalone_wrapper_retains_explicit_route_inputs(self):
        base=e._standalone_reservation(1000,20,30,40)
        self.assertEqual(e._standalone_reservation(1000,20,30,40,held_coordinates=500,
            recipe_objects=600,raw_bytes=700,saved_objects=800),base+2600)
        for key in ('held_coordinates','recipe_objects','raw_bytes','saved_objects'):
            with self.assertRaises(Refusal):e._standalone_reservation(1000,20,30,40,**{key:True})

    def test_old_standalone_near_limit_omission_refuses_combined_guard(self):
        # Independent scalar witness: the old helper returned 512MiB-2 by
        # omitting W0/common fixed/three buffers. No actual file is claimed.
        source_base=134217728+65536+10000
        self.assertEqual(134217728+source_base+2*67108864+2097152+
                         5*16777216+3*16052986,536870910)
        self.assert_code('estimated_memory_limit',e._standalone_reservation,
                        source_base,16777216,16052986,67108864,source_kind='file')

    def test_all_route_scalar_types_are_checked_before_phase_arithmetic(self):
        m=budget()
        for fn in (m._decoder_bytes,m._wire_bytes):
            with patch.object(m,'_checked_mul',side_effect=AssertionError('multiply before type check')):
                with self.assertRaises(Refusal):fn(1,True)
        for fn,args in ((m._saved_plan_parse_guard,(True,20,30)),
                        (m._load_plan_guard,(True,20,30,40,50,60)),
                        (m._verify_route_guard,(True,20,30,40,50,60))):
            with patch.object(m,'_decoder_bytes',side_effect=AssertionError('decode arithmetic before type check')):
                with self.assertRaises(Refusal):fn(*args)
        with patch.object(m,'_sum_counts',side_effect=AssertionError('sum before type check')):
            with self.assertRaises(Refusal):m._canonical_route_guard(True,raw_bytes=20)
        with patch.object(m,'_route_base',side_effect=AssertionError('base before metadata type check')):
            with self.assertRaises(Refusal):m._standalone_guard(1000,True,30,0)

    def test_standalone_wrapper_checks_retained_raw_state_before_arithmetic(self):
        m=budget()
        for field in ('raw_bytes','saved_objects'):
            with self.subTest(field=field), patch.object(m,'_standalone_guard',
                    side_effect=AssertionError('standalone arithmetic before retained-state type check')):
                with self.assertRaises(Refusal):e._standalone_reservation(1000,20,30,40,**{field:True})
