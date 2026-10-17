"""Boundary regressions found during B1 review, written before their fixes."""
import copy
from types import MappingProxyType
import unittest
from unittest.mock import patch
from replicatetable import Coordinate, Recipe, Refusal
from replicatetable.codec import OwnedMap, canonical_bytes, freeze, json_prepass, strict_loads
from replicatetable.model import MetadataValue
from tests.unit.test_codec import Evil, EvilMap
from tests.unit.test_models import recipe, stage


class BoundaryTests(unittest.TestCase):
    def refusal(self, expected_code, function, *args, **kwargs):
        with self.assertRaises(Refusal) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected_code)

    def test_v5_recipe_specific_boundaries_and_precedence(self):
        missing=stage(); del missing['missing']
        self.refusal('missing_stage_policy', Recipe.from_dict, recipe([missing]))
        no_count=copy.deepcopy(missing); del no_count['min_count']
        self.refusal('invalid_recipe', Recipe.from_dict, recipe([no_count]))
        malformed=copy.deepcopy(missing); malformed['min_count']=True
        self.refusal('invalid_recipe', Recipe.from_dict, recipe([malformed]))
        later=stage(True,name='other',dims=['sample']); del later['weight_unit']
        self.refusal('unsupported_later_stage_weights',Recipe.from_dict,recipe([stage(),later]))
        absent=copy.deepcopy(later); del absent['weights']
        self.refusal('unsupported_later_stage_weights',Recipe.from_dict,recipe([stage(),absent]))
        absent['op']=Evil()
        self.refusal('invalid_recipe',Recipe.from_dict,recipe([stage(),absent]))
        malformed=copy.deepcopy(later); malformed['weight_unit']=Evil()
        self.refusal('invalid_recipe',Recipe.from_dict,recipe([stage(),malformed]))
        policy=stage(True,name='other',dims=['sample']); del policy['missing']
        self.refusal('missing_stage_policy',Recipe.from_dict,recipe([stage(),policy]))
        # Well-formed broadcast content is resolved only against source grain.
        for broadcast in (['unknown'], ['b','a']):
            data=recipe(); data['row_dims']=['a','b']; data['columns'][0]['broadcast']=broadcast
            self.assertEqual(Recipe.from_dict(data).to_dict(),data)

    def test_v5_duplicate_row_role_and_all_exact_role_flags(self):
        self.refusal('duplicate_row_key',Coordinate,'<f8',[-0.0,0.0],[0,1],row=True)
        self.refusal('duplicate_coordinate',Coordinate,'<f8',[-0.0,0.0],[0,1],row=False)
        self.refusal('invalid_coordinate',Coordinate,'<i8',[1],[0],row=Evil())
        self.refusal('invalid_coordinate',Coordinate.from_fixed_bytes,'|S1',b'a',row=Evil())

    def test_owned_map_cannot_reinitialize_or_subclass(self):
        owned=freeze({'a':1})
        with self.assertRaises((AttributeError, TypeError)):
            owned.__init__({'a':2})
        self.assertEqual(owned['a'],1)
        with self.assertRaises(TypeError):
            type('Derived',(OwnedMap,),{})

    def test_canonical_cap_is_actual_and_owns_before_iterator_escape(self):
        value={'x':'a'}
        expected=b'{"x":"a"}\n'
        self.assertEqual(canonical_bytes(value,limit=len(expected)),expected)
        self.refusal('metadata_bytes_limit',canonical_bytes,value,limit=len(expected)-1)
        from replicatetable.codec import iter_json_chunks
        iterator=iter_json_chunks(value); value['x']='mutated'
        self.assertEqual(b''.join(iterator),expected)

    def test_full_decoder_is_not_called_for_failed_preflight(self):
        # Array grammar avoids the permitted one-key decoder used by map scan.
        with patch('replicatetable.codec.json.loads', side_effect=AssertionError('full decoder ran')):
            self.refusal('invalid_json',strict_loads,b'['*33+b'0'+b']'*33)
            self.refusal('invalid_json',strict_loads,b'[1e400]')
            self.refusal('estimated_memory_limit',strict_loads,b'[0]',object_limit=511)

    def test_fixed_width_projection_precedes_invalid_utf8_decode(self):
        # 250k width-1 labels fit raw bytes, but numeric32 permutation plus
        # strings exceed the canonical-coordinate cap. First byte is invalid.
        self.refusal('coordinate_bytes_limit',Coordinate.from_fixed_bytes,'|S1',b'\xff'*250000)

    def test_metadata_budget_rejects_before_visiting_later_poison(self):
        # 1024 strings already exceed conservative J of 16 MiB. The later
        # poison must never be examined to discover this established limit.
        self.refusal('metadata_bytes_limit',MetadataValue,[['x'*4096]*1024,Evil()])
        self.refusal('invalid_source',MetadataValue.from_dict,MappingProxyType(EvilMap()))
        self.refusal('invalid_source',MetadataValue.from_dict,{'type':Evil()})

    def test_coordinate_exact_elements_before_missing_or_finite_branches(self):
        self.refusal('invalid_coordinate',Coordinate,'<f8',[None,Evil()],[0,1])
        self.refusal('missing_coordinate',Coordinate,'<f8',[float('inf'),None],[0,1])

    def test_label_utf8_ceiling_has_its_own_code(self):
        self.assertEqual(Coordinate('<U4096',['😀'*1024],[0]).values,('😀'*1024,))
        self.refusal('label_bytes_limit',Coordinate,'<U4096',['😀'*1025],[0])

    def test_recipe_raw_cap_equality_then_plus_one_before_utf8(self):
        from replicatetable import parse_recipe
        raw=canonical_bytes(recipe())
        exact=raw+b' '*(1048576-len(raw))
        self.assertEqual(parse_recipe(exact).to_dict(),recipe())
        self.refusal('recipe_bytes_limit',parse_recipe,exact+b'\xff')
        for raw in ('{}',bytearray(b'{}'),MappingProxyType(EvilMap())):
            self.refusal('invalid_recipe',parse_recipe,raw)

    def test_single_scalar_and_32_columns_16_dimensions(self):
        data=recipe(); data['row_dims']=[]
        data['columns'][0]['stages']=[]
        self.assertEqual(Recipe.from_dict(data).row_dims,())
        data['row_dims']=['d'+str(n) for n in range(16)]
        data['columns']=[dict(data['columns'][0],name='c'+str(n)) for n in range(32)]
        self.assertEqual(len(Recipe.from_dict(data).columns),32)
        data['row_dims'].append('overflow')
        self.refusal('invalid_recipe',Recipe.from_dict,data)

    def test_selected_coordinate_does_not_invent_source_raw_allocation(self):
        # Canonical U width is semantic storage metadata. A selected model has
        # no authority to infer that a dense Unicode ndarray was allocated.
        labels=[str(n).zfill(3) for n in range(513)]
        coordinate=Coordinate('<U4096',labels,list(range(513)))
        self.assertEqual(coordinate.dtype,'<U4096')
        self.assertEqual(coordinate.values,tuple(labels))
        self.assertEqual(Coordinate.from_dict(coordinate.to_dict()).to_json(),coordinate.to_json())

    def test_coordinate_minimum_projection_precedes_element_scan(self):
        self.refusal('coordinate_bytes_limit',Coordinate,'<U1',[Evil()]*240000,list(range(240000)))

    def test_output_limit_precedes_immutable_forest_copy(self):
        value={'x':['large'*100 for _ in range(20)]}
        with patch('replicatetable.codec._freeze', side_effect=AssertionError('ownership copy before byte admission')):
            self.refusal('metadata_bytes_limit',canonical_bytes,value,limit=10)
        # Exact byte admission still wins over the larger conservative J bound.
        self.assertEqual(canonical_bytes({'x':0},limit=8),b'{"x":0}\n')
