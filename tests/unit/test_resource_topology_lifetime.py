"""B2-L1: observe construction, not merely the returned table shape.

Test probes retain only integers/type names. They never store frames, builders,
records or iterators after an observation. No production heap walk is used.
"""
import builtins
import sys
import types
import unittest
from unittest.mock import patch
from replicatetable import _resource_estimates as e
from replicatetable import _resource_inputs as i
from tests.resource_helpers import synthetic_input
from tests.unit.test_resource_coverage import maximum_input
from tests.unit.test_resource_estimates import hand_input

_TABLE_CLASSES=(i._VariableFacts,e._ColumnTopology,e._StageTopology)
_TABLE_NAMES=('variables','columns','stages')
_CHECK_NAMES=('_rows','_support','_selected_numeric','_work','_scratch')


def _is_record_table(value):
    return type(value) in (list,tuple) and len(value)>0 and type(value[0]) in _TABLE_CLASSES


class TopologyLifetimeRepairTests(unittest.TestCase):
    def test_no_parallel_record_table_at_actual_tuple_construction(self):
        # Replacing the module's constructor name observes the moment both the
        # input and result exist. Deleting a builder AFTER tuple(list) cannot
        # pass this test. Rank16 dimension-sort/finalization scratch is allowed.
        for factory in (maximum_input,hand_input,synthetic_input):
            with self.subTest(factory=factory.__name__):
                inp=factory();observations=[]
                def construct(iterable=()):
                    caller=sys._getframe(1)
                    if caller.f_code.co_filename==e.__file__:
                        for name in _TABLE_NAMES:
                            if caller.f_locals.get(name) is iterable:
                                self.assertIsNot(type(iterable),list,
                                    f'{name} list remains live at its tuple finalization')
                        self.assertFalse(type(iterable) is list and _is_record_table(iterable),
                                         'record-table list supplied to tuple constructor')
                    result=builtins.tuple(iterable)
                    if _is_record_table(result):
                        # An exact existing tuple is borrowed by identity; a
                        # bounded internal producer may fill the sole new table.
                        self.assertTrue(result is iterable or type(iterable) is types.GeneratorType)
                        for value in caller.f_locals.values():
                            if _is_record_table(value) and value is not result:
                                self.assertFalse(len(value)==len(result) and
                                    all(a is b for a,b in zip(value,result)),
                                    'parallel table still holds the identical record occurrences')
                        observations.append((type(result[0]).__name__,len(result),type(iterable).__name__))
                    del caller
                    return result
                with patch.object(e,'tuple',construct,create=True):
                    top=e._derive_topology(inp)
                self.assertIs(type(top),tuple)
                self.assertEqual(len(top),4)
                self.assertTrue(any(name=='_VariableFacts' for name,_,_ in observations))
                self.assertTrue(any(name=='_ColumnTopology' for name,_,_ in observations))
                if top[2]:self.assertTrue(any(name=='_StageTopology' for name,_,_ in observations))

    def test_final_cardinality_calls_and_return_borrow_same_tables(self):
        inp=maximum_input();events=[]
        def observe(frame,event,arg):
            if frame.f_code.co_filename!=e.__file__:return
            if event=='call' and frame.f_code.co_name in _CHECK_NAMES:
                parent=frame.f_back
                if parent is not None and parent.f_code.co_name=='_derive_topology' and 'top' in parent.f_locals:
                    top=parent.f_locals['top']
                    for position,name in enumerate(_TABLE_NAMES+('dimensions',)):
                        self.assertIs(parent.f_locals[name],top[position],name)
                        self.assertIs(type(parent.f_locals[name]),tuple,name)
                    events.append(frame.f_code.co_name)
            if event=='return' and frame.f_code.co_name=='_derive_topology':
                self.assertEqual(tuple(len(t) for t in arg),(64,32,64,16))
                for position,name in enumerate(_TABLE_NAMES+('dimensions',)):
                    self.assertIs(frame.f_locals[name],arg[position],name)
                events.append('return')
        old=sys.getprofile();sys.setprofile(observe)
        try:top=e._derive_topology(inp)
        finally:sys.setprofile(old)
        self.assertEqual(events,list(_CHECK_NAMES)+['return'])
        for c in top[1]:
            self.assertIs(c.measurement.dims,inp.source['variables'][c.measurement.name]['dims'])
            self.assertIs(c.measurement.shape,inp.source['variables'][c.measurement.name]['shape'])
            self.assertIs(c.input_dims,c.measurement.dims)
            if c.stage_count==2:
                first,second=top[2][c.stage_begin:c.stage_begin+2]
                self.assertIs(second.input_dims,first.remaining_dims)
                self.assertIs(c.final_dims,second.remaining_dims)

    def test_no_record_list_during_bounded_producer_yields(self):
        inp=maximum_input();record_events=0
        def observe(frame,event,arg):
            nonlocal record_events
            if frame.f_code.co_filename!=e.__file__ or event not in ('call','return'):return
            current=frame
            while current is not None and current.f_code.co_filename==e.__file__:
                for value in current.f_locals.values():
                    self.assertFalse(type(value) is list and _is_record_table(value),
                                     'mutable record-table builder survived in an active resource frame')
                current=current.f_back
            if event=='return' and type(arg) in _TABLE_CLASSES:record_events+=1
        old=sys.getprofile();sys.setprofile(observe)
        try:e._derive_topology(inp)
        finally:sys.setprofile(old)
        self.assertGreaterEqual(record_events,128)  # 64 stage +32 column yields, plus resumed constructor returns

    def test_producer_workspaces_stay_inside_existing_walker_reserve(self):
        # Charge fixed frame-local names/container slots and every scalar
        # counter occurrence, borrowing existing model/table references. This
        # is conservative workspace accounting, not tracemalloc/RSS credit.
        inp=maximum_input();maximum_slots=maximum_charge=0
        def observe(frame,event,arg):
            nonlocal maximum_slots,maximum_charge
            if event not in ('call','return') or not frame.f_globals.get('__name__','').startswith('replicatetable.'):return
            slots=charge=0;current=frame
            while current is not None and current.f_globals.get('__name__','').startswith('replicatetable.'):
                local=current.f_locals
                amount=512+128*len(local)+sum(128+4*len(name.encode()) for name in local)
                amount+=128*sum(type(value) in (int,bool) for value in local.values())
                # A large Python producer frame occupies multiple fixed
                # eight-field walker slots; no extra allowance is introduced.
                slots+=(amount+3383)//3384;charge+=amount
                current=current.f_back
            maximum_slots=max(maximum_slots,slots);maximum_charge=max(maximum_charge,charge)
        old=sys.getprofile();sys.setprofile(observe)
        try:e._derive_topology(inp)
        finally:sys.setprofile(old)
        self.assertLessEqual(maximum_slots,32)
        self.assertLessEqual(maximum_charge,32*3384)
