import importlib
import unittest
from unittest.mock import patch
from replicatetable.codec import OwnedMap, primitive_bounds, freeze, canonical_bytes
from replicatetable.model import Coordinate, MetadataValue
from replicatetable.errors import Refusal
from tests.resource_helpers import descriptor,inspection,recipe,stage,synthetic_input,runtime_example


def inputs():
    name='replicatetable._resource_inputs'
    assert importlib.util.find_spec(name) is not None,'B2 input walker module is missing'
    return importlib.import_module(name)


class ResourceInputTests(unittest.TestCase):
    def test_b2_010_dtype_widths(self):
        m=inputs()
        for dtype,size in [('int8',1),('uint8',1),('int16',2),('uint16',2),('int32',4),
                           ('uint32',4),('int64',8),('uint64',8),('float32',4),('float64',8)]:
            f=m._variable_facts('x',freeze(descriptor(('d',),(3,),dtype)),freeze({'d':3}))
            self.assertEqual((f.itemsize,f.cells,f.nbytes),(size,3,3*size))
        with self.assertRaises(Refusal): m._variable_facts('x',freeze(descriptor(dtype='object')),freeze({}))

    def test_b2_016_coordinate_maxima_borrow_owned_backing(self):
        m=inputs(); c=Coordinate('<U8',['','😀 "&'],[0,1])
        f=m._coordinate_facts('d',c,raw_bytes=64,preselection_j=64)
        self.assertIs(f.coordinate,c)
        self.assertEqual((f.max_utf8,f.sum_utf8),(7,7))
        self.assertEqual((f.max_label_j,f.max_label_p),(44,156))
        self.assertEqual(f.selected_j,primitive_bounds(c._projection()).json_bytes+1)
        self.assertEqual(f.coordinate_p,primitive_bounds(c._projection()).object_bytes)
        k=m._key_bound(('d',),(f,))
        for label in c.values:
            p=primitive_bounds({'d':label})
            self.assertLessEqual(p.json_bytes,k.json_bytes)
            self.assertLessEqual(p.object_bytes,k.object_bytes)

    def test_b2_017_raw_storage_not_inferred_from_coordinate(self):
        m=inputs(); c=Coordinate('<U4096',['a'],[0])
        a=m._coordinate_facts('d',c,raw_bytes=16384,preselection_j=8)
        b=m._coordinate_facts('d',c,raw_bytes=4096,preselection_j=8)
        self.assertEqual((a.raw_bytes,b.raw_bytes),(16384,4096))
        self.assertEqual(a.selected_j,b.selected_j)

    def test_b2_018_predecode_fixed_width_boundary(self):
        m=inputs()
        self.assertEqual(m._fixed_coordinate_preflight('|S4',2),(8,55,8))
        self.assertEqual(m._fixed_coordinate_preflight('<U4',2),(32,199,32))
        with self.assertRaises(Refusal) as e: m._fixed_coordinate_preflight('|S4096',513)
        self.assertEqual(e.exception.code,'coordinate_bytes_limit')

    def test_b2_019_coordinate_passes_independently_capped(self):
        m=inputs(); c=Coordinate('<i8',[1],[0])
        fs=tuple(m._coordinate_facts(n,c,raw_bytes=4194304,preselection_j=4194304) for n in ('a','b'))
        totals=m._coordinate_totals(fs)
        self.assertEqual(totals.raw_coordinate_j,8388608)
        self.assertEqual(totals.coordinate_raw,8388608)
        bad=fs+(m._coordinate_facts('c',c,raw_bytes=1,preselection_j=1),)
        with self.assertRaises(Refusal) as e: m._coordinate_totals(bad)
        self.assertEqual(e.exception.code,'coordinate_bytes_limit')

    def test_b2_020_incremental_owner_charges(self):
        m=inputs()
        header=m._header_charge(1,96)
        self.assertEqual(header,640)
        own=m._owner_charge('variable','v',8,'ndarray',8*1024**2,(header,),0)
        self.assertEqual(own['terminal_bytes'],8*1024**2)
        self.assertEqual(own['header_bytes'],640)
        own2=m._owner_charge('variable','w',8,'ndarray',8*1024**2,(header,),0)
        b=m._memory_binding(inspection(),(own,own2),512)
        self.assertEqual(b['base_bytes'],2*(8*1024**2+640)+512+65536+b['descriptor_bytes'])
        bytes_owner=m._owner_charge('variable','v',8,'bytes',10,(header,)*32,0)
        self.assertEqual(bytes_owner['terminal_bytes'],138)
        with self.assertRaises(Refusal): m._owner_charge('variable','v',8,'ndarray',1,(header,)*33,0)
        with self.assertRaises(Refusal) as e: m._fold_source_charge(134217728,1)
        self.assertEqual(e.exception.code,'source_bytes_limit')

    def test_b2_021_file_base_uses_actual_file_size(self):
        m=inputs();from replicatetable.codec import thaw
        raw=thaw(inspection(kind='file'));raw['source']['size_bytes']=1;s=freeze(raw)
        b=m._file_binding(s,1)
        self.assertEqual(b['base_bytes'],1+65536+b['descriptor_bytes'])
        raw['source']['size_bytes']=134217728;s=freeze(raw)
        full=m._file_binding(s,134217728)
        self.assertEqual(full['base_bytes'],134217728+65536+full['descriptor_bytes'])
        raw['source']['size_bytes']=134217729;s=freeze(raw)
        with self.assertRaises(Refusal) as e:m._file_binding(s,134217729)
        self.assertEqual(e.exception.code,'source_bytes_limit')

    def test_b2_030_full_inspection_counts_tags(self):
        m=inputs(); s=inspection({'d':1},{'v':descriptor(attributes={'a':[None,float('nan'),'😀']})},
            {'d':descriptor(('d',),(1,),'<i8',status={'status':'unsupported',
                'code':'unsupported_coordinate_encoding','reasons':['calendar_metadata']})})
        self.assertEqual(m._inspection_cost(s),m._owned_cost(s))
        p=primitive_bounds(s)
        self.assertEqual((m._inspection_cost(s).json_bytes,m._inspection_cost(s).object_bytes),
                         (p.json_bytes,p.object_bytes))
        self.assertLessEqual(len(canonical_bytes(s)),p.json_bytes+1)

    def test_b2_031_runtime_exact_owned_backing(self):
        m=inputs(); runtime=freeze(runtime_example()); p=primitive_bounds(runtime)
        with patch('replicatetable.codec.thaw',side_effect=AssertionError('copy')):
            cost=m._runtime_cost(runtime)
        self.assertEqual((cost.json_bytes,cost.object_bytes),(p.json_bytes,p.object_bytes))
        with self.assertRaises(Refusal): m._runtime_cost(runtime_example())

    def test_b2_004_owned_walk_rejects_hooks(self):
        m=inputs()
        class Evil:
            def __eq__(self,o): raise AssertionError('hook')
        with self.assertRaises(Refusal): m._owned_cost(Evil())
        with self.assertRaises(Refusal): m._owned_cost({'x':1})

    def test_record_constructors_refuse_nonexact_fields(self):
        m=inputs()
        with self.assertRaises(Refusal):m._VariableFacts(True,1,8,'v','float64',(),())
        c=Coordinate('<i8',[0],[0])
        with self.assertRaises(Refusal):m._CoordinateFacts(True,32,128,0,0,8,34,100,1000,32,'d',c)
        with self.assertRaises(Refusal):m._SourceScalars(source_base=True)

    def test_inspection_source_identity_closed_shape(self):
        m=inputs(); s=inspection();from replicatetable.codec import thaw
        bad=thaw(s);bad['source']['extra']=1
        with self.assertRaises(Refusal):m._inspection_cost(freeze(bad))
