"""Actual projection frames, not claimed native/parser-release evidence."""
import sys
import tracemalloc
import unittest
from unittest.mock import patch
from replicatetable import _resource_estimates as e, _resource_bounds as b
from tests.unit.test_native_budget_estimates import budget
from tests.unit.test_resource_coverage import maximum_input


class NativeBudgetLifetimeTests(unittest.TestCase):
    def test_new_path_projection_does_not_duplicate_root_path_tuple(self):
        class NoConcatenation(tuple):
            def __add__(self,other):raise AssertionError('duplicate path tuple')
        top=e._derive_topology(maximum_input())
        with patch.object(e,'ROOT_PAYLOADS',NoConcatenation(e.ROOT_PAYLOADS)):
            self.assertEqual(e._project_native_control(top,119930),(2913396,119930))

    def test_manifest_projection_is_not_reopened_with_trace_live(self):
        actual=e._manifest_cost;trace_live=False
        def trace(frame,event,arg):
            nonlocal trace_live
            if frame.f_code.co_filename==e.__file__ and frame.f_code.co_name=='_project_trace' and event=='return':
                trace_live=True
        def manifest(*args,**kwargs):
            self.assertFalse(trace_live,'output/manifest projection restarted with retained trace')
            return actual(*args,**kwargs)
        prior=sys.getprofile();sys.setprofile(trace)
        try:
            with patch.object(e,'_manifest_cost',manifest):
                self.assertEqual(e._estimate_compilation(maximum_input())['estimated_memory_bytes'],280995792)
        finally:sys.setprofile(prior)

    def test_current_generated_path_retires_before_next_path(self):
        top=e._derive_topology(maximum_input());actual=e._stage_path;seen=[]
        def path(ci,si,schema=False):
            caller=sys._getframe(1)
            try:
                if caller.f_code.co_name=='_project_native_control':
                    self.assertFalse('name' in caller.f_locals,'prior path still live')
                    self.assertFalse('pair' in caller.f_locals,'prior path pair still live')
                    seen.append((ci,si,schema))
            finally:del caller
            return actual(ci,si,schema)
        with patch.object(e,'_stage_path',path):e._project_native_control(top,119930)
        self.assertEqual(len(seen),128)

    def test_actual_new_frames_have_only_scalar_cost_state(self):
        m=budget();inp=maximum_input();depth=maximum=0;observed=0
        functions={'_project_native_control','_parent_bytes','_child_counts','_stage_witness_cost',
                   '_completion_cost','_control_ceiling','_transport_bytes','_wire_bytes'}
        def observe(frame,event,arg):
            nonlocal depth,maximum,observed
            if frame.f_code.co_filename not in (e.__file__,m.__file__,b.__file__):return
            if event=='call':depth+=1;maximum=max(maximum,depth)
            if event=='return':
                depth-=1
                if frame.f_code.co_name in functions:
                    observed+=1
                    for key,value in frame.f_locals.items():
                        if key=='top':continue
                        self.assertIsNot(type(value),list,(frame.f_code.co_name,key))
                        self.assertIsNot(type(value),dict,(frame.f_code.co_name,key))
                    if frame.f_code.co_name=='_project_native_control':
                        self.assertIs(type(arg),tuple);self.assertEqual(len(arg),2)
                        self.assertTrue(all(type(v) is int for v in arg))
        prior=sys.getprofile();sys.setprofile(observe)
        try:out=e._estimate_compilation(inp)
        finally:sys.setprofile(prior)
        self.assertGreaterEqual(observed,13);self.assertLessEqual(maximum,32)
        self.assertTrue(all(type(v) is int for _,v in out._items))
        # A named 32KiB finite projection overlay is below the phase difference;
        # this DOES NOT add that amount to CONTROL or any public estimate.
        self.assertLess(1163232+32768,1524052)
        self.assertEqual(1524052+129448,1653500)
        self.assertEqual(1653500+273564+15876+12664,1955604)

    def test_actual_projection_allocation_is_below_named_phase_overlay(self):
        top=e._derive_topology(maximum_input())
        tracemalloc.start()
        try:
            result=e._project_native_control(top,119930)
            current,peak=tracemalloc.get_traced_memory()
        finally:tracemalloc.stop()
        self.assertEqual(result,(2913396,119930))
        self.assertLess(current,32768);self.assertLess(peak,32768)
        # This is small Python projection evidence, never native RSS capacity.
