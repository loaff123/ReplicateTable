"""File-size versus full-base boundaries, using closed synthetic observations.

No real128MiB file, native source or source-admission capacity is claimed.
"""
import unittest
from unittest.mock import patch
from replicatetable import _resource_inputs as i,_resource_estimates as e,resources as r
from replicatetable.codec import freeze,thaw
from replicatetable.model import Coordinate
from replicatetable.errors import Refusal
from tests.resource_helpers import synthetic_input,inspection,descriptor,recipe,stage


def accepted(call,*args,**kwargs):
    try:return call(*args,**kwargs)
    except Refusal as exc:raise AssertionError('Valid file byte boundary refused before combined admission: '+exc.code) from exc


def file_observation(size,template=None,source=None):
    template=synthetic_input() if template is None else template
    raw=thaw(template.source if source is None else source)
    raw['source']['kind']='file';raw['source']['size_bytes']=size
    source=freeze(raw)
    binding=accepted(i._file_binding,source,size)
    return accepted(i._CompilationInput,source,binding,template.recipe,template.coordinates,template.runtime,template.units)


class FileBaseBoundaryTests(unittest.TestCase):
    def assert_code(self,code,call,*args,**kwargs):
        with self.assertRaises(Refusal) as caught:call(*args,**kwargs)
        self.assertEqual(caught.exception.code,code)

    def test_actual_file_cap_equality_retains_full_base_for_compilation(self):
        full=file_observation(r.SOURCE_FILE_BYTES_LIMIT)
        descriptor=i._inspection_cost(full.source)
        self.assertEqual(full.source['source']['size_bytes'],r.SOURCE_FILE_BYTES_LIMIT)
        self.assertEqual(full.binding['base_bytes'],r.SOURCE_FILE_BYTES_LIMIT+r.MODEL_FIXED_BYTES+descriptor.object_bytes)
        self.assertGreater(full.binding['base_bytes'],r.SOURCE_MEMORY_BASE_LIMIT)
        estimated=e._estimate_compilation(full)
        self.assertEqual(estimated['source_base_bytes'],full.binding['base_bytes'])
        small=e._estimate_compilation(file_observation(4096))
        self.assertEqual(estimated['estimated_memory_bytes']-small['estimated_memory_bytes'],r.SOURCE_FILE_BYTES_LIMIT-4096)
        self.assertLessEqual(estimated['estimated_memory_bytes'],r.LOGICAL_JOURNEY_LIMIT)

    def test_file_cap_plus_one_precedes_descriptor_walk(self):
        raw=thaw(inspection(kind='file'));raw['source']['size_bytes']=r.SOURCE_FILE_BYTES_LIMIT+1;source=freeze(raw)
        with patch.object(i,'_inspection_cost',side_effect=AssertionError('metadata walked before file cap')):
            self.assert_code('source_bytes_limit',i._file_binding,source,r.SOURCE_FILE_BYTES_LIMIT+1)

    def test_file_incremental_metadata_reserve_uses_remaining_journey_domain(self):
        raw=thaw(inspection(kind='file'));raw['source']['size_bytes']=r.SOURCE_FILE_BYTES_LIMIT;source=freeze(raw)
        actual=i._inspection_cost;calls=[]
        def observe(value,**kwargs):
            calls.append(kwargs.copy())
            return actual(value,**kwargs)
        with patch.object(i,'_inspection_cost',side_effect=observe):binding=accepted(i._file_binding,source,r.SOURCE_FILE_BYTES_LIMIT)
        self.assertEqual(calls,[{'object_limit':r.LOGICAL_JOURNEY_LIMIT-r.SOURCE_FILE_BYTES_LIMIT-r.MODEL_FIXED_BYTES,
                                'object_code':'estimated_memory_limit'}])
        self.assertEqual(binding['descriptor_bytes'],actual(source).object_bytes)

    def test_file_metadata_cap_is_not_masked_by_a_memory_base_cap(self):
        # Each metadata value is individually admitted; their complete source
        # descriptor is over16MiB J. The file byte length itself is valid.
        source=inspection(kind='file',variables={'v':descriptor(
            attributes={'long':['x'*4096]*400},encoding={'long':['x'*4096]*400})})
        raw=thaw(source);raw['source']['size_bytes']=r.SOURCE_FILE_BYTES_LIMIT;source=freeze(raw)
        self.assert_code('metadata_bytes_limit',i._file_binding,source,r.SOURCE_FILE_BYTES_LIMIT)

    def test_standalone_and_anchor_checks_accept_file_full_base(self):
        inp=file_observation(r.SOURCE_FILE_BYTES_LIMIT);base=inp.binding['base_bytes']
        total=e._standalone_reservation(base,20,30,0,source_kind='file')
        self.assertEqual(total,r.RUNTIME_ALLOWANCE+base+r.CONTROL_STATE_BYTES+3*65536+65536+1434532+8081875)
        self.assert_code('source_bytes_limit',e._standalone_reservation,base,20,30,0)
        self.assert_code('metadata_bytes_limit',e._standalone_reservation,base,r.METADATA_BYTES_LIMIT+1,0,0,source_kind='file')
        self.assert_code('invalid_source',e._standalone_reservation,base,20,30,0,source_kind=True)
        self.assert_code('invalid_source',e._standalone_reservation,base,20,30,0,source_kind='unknown')
        # All individually bounded scalar quantities still fail their combined
        # journey, with the journey code rather than an invented source cap.
        self.assert_code('estimated_memory_limit',e._standalone_reservation,base,
            r.METADATA_BYTES_LIMIT,20*r.MIB,r.SELECTED_NUMERIC_BYTES_LIMIT,source_kind='file')
        estimates=e._estimate_compilation(inp)
        result=e._call_total(estimates['estimated_memory_bytes'],inp.binding,inp.binding,(),(),required_count=0,distinct_count=0)
        self.assertTrue(result['admitted']);self.assertEqual(result['extra_source_bytes'],0)
        changed=thaw(inp.binding);changed['base_bytes']-=1
        self.assert_code('source_resource_binding_mismatch',e._call_total,1,inp.binding,freeze(changed),(),(),required_count=0,distinct_count=0)

    def test_combined_file_estimate_still_refuses_oversized_journey(self):
        columns=[{'name':f'c{n}','source':'v','source_unit':None,'target_unit':None,'broadcast':[],
                  'stages':[stage('mean',('d',))]} for n in range(32)]
        template=synthetic_input({'d':1000},{'v':descriptor(('d',),(1000,))},
            {'d':Coordinate('<i8',list(range(1000)),list(range(1000)))},recipe((),columns))
        inp=file_observation(r.SOURCE_FILE_BYTES_LIMIT,template)
        top=e._derive_topology(inp);output=e._project_outputs(inp,top,e._project_plan0(inp,top))
        self.assertLess(output.bundle,r.BUNDLE_BYTES_LIMIT)
        self.assert_code('estimated_memory_limit',e._estimate_compilation,inp)

    def test_memory_base_equality_plus_one_and_extra_dataset_caps_unchanged(self):
        source=inspection();descriptor=i._inspection_cost(source)
        owner=i._owner_charge('variable','v',8,'ndarray',8,(640,),0)
        stock=r.SOURCE_MEMORY_BASE_LIMIT-r.MODEL_FIXED_BYTES-descriptor.object_bytes-648
        binding=i._memory_binding(source,(owner,),stock)
        self.assertEqual(binding['base_bytes'],r.SOURCE_MEMORY_BASE_LIMIT)
        self.assert_code('source_bytes_limit',i._memory_binding,source,(owner,),stock+1)
        self.assert_code('source_bytes_limit',i._fold_source_charge,r.SOURCE_MEMORY_BASE_LIMIT,1)
        self.assert_code('source_bytes_limit',e._call_total,1,binding,binding,(r.SOURCE_MEMORY_BASE_LIMIT+1,),(),required_count=2,distinct_count=2)
