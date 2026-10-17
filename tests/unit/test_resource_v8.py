"""Approved v8 finite status-cost adapter only, not a declaration classifier."""
import itertools
import unittest
from replicatetable import _resource_inputs as i,_resource_estimates as e
from replicatetable.codec import freeze,thaw,primitive_bounds,canonical_bytes
from replicatetable.model import MetadataValue
from replicatetable.errors import Refusal
from tests.resource_helpers import descriptor,inspection,synthetic_input

REASONS=('calendar_metadata','reference_time_units','scale_factor_metadata','add_offset_metadata',
         'unsigned_metadata','fill_value_metadata','missing_value_metadata')


class ResourceV8Tests(unittest.TestCase):
    def test_all_158_role_valid_subsets_and_costs(self):
        self.assertTrue(hasattr(i,'_selection_status_cost'),'v8 closed role-qualified cost adapter missing')
        count=0
        for coordinate,reasons,expected in ((True,REASONS,(1203,4616)),(False,REASONS[2:],(951,3940))):
            self.assertEqual(i._selection_status_cost(None,coordinate=coordinate),i._JP(4,128))
            for n in range(1,len(reasons)+1):
                for subset in itertools.combinations(reasons,n):
                    obj=freeze({'status':'unsupported','code':'unsupported_coordinate_encoding' if coordinate else 'unsupported_source_encoding','reasons':subset})
                    cost=i._selection_status_cost(obj,coordinate=coordinate);ref=primitive_bounds(obj)
                    self.assertEqual((cost.json_bytes,cost.object_bytes),(ref.json_bytes,ref.object_bytes))
                    self.assertLessEqual(len(canonical_bytes(obj)),cost.json_bytes+1);count+=1
            full=freeze({'status':'unsupported','code':'unsupported_coordinate_encoding' if coordinate else 'unsupported_source_encoding','reasons':reasons})
            pair=i._selection_status_cost(full,coordinate=coordinate)
            self.assertEqual((pair.json_bytes,pair.object_bytes),expected)
        self.assertEqual(count,158)

    def test_status_exact_fields_role_order_enum(self):
        good={'status':'unsupported','code':'unsupported_source_encoding','reasons':['scale_factor_metadata']}
        for delta in ({'extra':0},{'status':True},{'code':'unsupported_coordinate_encoding'},
                      {'reasons':[]},{'reasons':['calendar_metadata']},{'reasons':['bogus']},
                      {'reasons':['scale_factor_metadata','scale_factor_metadata']},
                      {'reasons':['missing_value_metadata','fill_value_metadata']}):
            bad=good|delta
            s=inspection(variables={'v':descriptor(status=bad)})
            with self.assertRaises(Refusal):i._inspection_cost(s)

    def test_raw_attrs_encoding_and_status_charged_separately(self):
        status={'status':'unsupported','code':'unsupported_source_encoding','reasons':list(REASONS[2:])}
        raw={'scale_factor':1,'add_offset':0,'_Unsigned':False,'_FillValue':1.0,'missing_value':[float('nan')]}
        a=inspection(variables={'v':descriptor(attributes=raw,encoding=raw,status=status)})
        b=inspection(variables={'v':descriptor(attributes=raw,encoding=raw)})
        pa=i._inspection_cost(a);pb=i._inspection_cost(b)
        self.assertEqual((pa.json_bytes-pb.json_bytes,pa.object_bytes-pb.object_bytes),(951-4,3940-128))
        before=canonical_bytes(a);i._inspection_cost(a);self.assertEqual(canonical_bytes(a),before)
        self.assertEqual(pa.object_bytes,primitive_bounds(a).object_bytes)

    def test_tagged_metadata_shape_is_closed_without_thaw(self):
        src=thaw(inspection());src['variables']['v']['attributes']={'type':'null','value':1}
        with self.assertRaises(Refusal):i._inspection_cost(freeze(src))
        src=thaw(inspection());src['variables']['v']['encoding']={'type':'float','value':'nan'}
        with self.assertRaises(Refusal):i._inspection_cost(freeze(src))

    def test_status_bearing_api_projections_and_plan_no_synthetic_fields(self):
        self.assertTrue(hasattr(e,'_api_projection'),'per-kind closed projection missing')
        inp=synthetic_input();base=thaw(inp.source)
        base['variables']['v']['selection_status']={'status':'unsupported','code':'unsupported_source_encoding','reasons':list(REASONS[2:])}
        source=freeze(base)
        changed=i._CompilationInput(source,i._memory_binding(source,(),512),inp.recipe,inp.coordinates,inp.runtime,inp.units)
        top=e._derive_topology(inp);other=e._derive_topology(changed)
        p=e._project_plan0(inp,top);q=e._project_plan0(changed,other)
        # resource-binding scalar values change, fixed numeric projections do not.
        self.assertEqual(p,q)
        for kind in ('descriptor','prepared','materialized'):
            a=e._api_projection(inp,top,p,kind);b=e._api_projection(changed,other,q,kind)
            self.assertEqual((b.json_bytes-a.json_bytes,b.object_bytes-a.object_bytes),(947,3812))
        self.assertEqual(e._api_projection(inp,top,p,'plan'),e._api_projection(changed,other,q,'plan'))
