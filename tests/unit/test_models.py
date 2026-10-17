"""Pins recipe structure, immutable typed keys, and bounded byte storage.

Detects coercion, mutable aliases, unsupported sentinel admission, and unsafe
set/lookup/equality before exact primitive qualification.
"""
import copy
import math
import struct
from types import MappingProxyType
import unittest

from replicatetable import parse_recipe, Recipe, SourceIdentity, Coordinate, ArrayBuffer, Refusal
from replicatetable.codec import canonical_bytes
from replicatetable.model import (OwnedMap, exact_int, numeric_dtype, validate_name,
                                  validate_unit, MetadataValue, descriptor_object_scalar)
from tests.unit.test_codec import Evil, EvilMap


def stage(weighted=False, name='stage', dims=None):
    value = dict(name=name, dims=['replicate'] if dims is None else dims,
                 op='weighted_mean' if weighted else 'mean', missing='skip', min_count=1)
    if weighted:
        value.update(weights='weight', weight_unit=None)
    return value


def recipe(stages=None):
    return dict(version=1, row_dims=['key:00'], columns=[dict(name='value',source='n_valid',
        source_unit=None,target_unit=None,broadcast=[],stages=[] if stages is None else stages)])


class ModelTests(unittest.TestCase):
    def refusal(self, expected_code, function, *args, **kwargs):
        with self.assertRaises(Refusal) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected_code)

    def test_zero_one_two_stages_and_logical_name_namespaces(self):
        for stages in ([], [stage()], [stage(True), stage(name='value',dims=['sample'])]):
            obj = recipe(stages)
            obj['columns'][0]['name'] = 'key:00'
            model = parse_recipe(canonical_bytes(obj))
            self.assertEqual(model.to_dict(), obj)
            self.assertEqual(model.to_json(), canonical_bytes(obj))
            self.assertEqual(model.row_dims, ('key:00',))
            self.assertIs(type(model.columns[0]), OwnedMap)

    def test_recipe_owns_fresh_backing(self):
        value = recipe([stage()])
        saved = copy.deepcopy(value)
        model = Recipe.from_dict(value)
        value['columns'][0]['stages'][0]['dims'].append('mutated')
        value['row_dims'].clear()
        self.assertEqual(model.to_dict(), saved)
        copied = model.to_dict()
        copied['columns'].clear()
        self.assertEqual(model.to_dict(), saved)
        with self.assertRaises((AttributeError, TypeError)):
            model.row_dims = ()

    def test_recipe_duplicate_unknown_missing_exact_fields(self):
        base = recipe([stage(True)])
        for path in ((), ('columns',0), ('columns',0,'stages',0)):
            for operation in ('extra','missing'):
                value = copy.deepcopy(base)
                node = value
                for key in path: node = node[key]
                if operation == 'extra': node['surprise'] = 1
                else: del node[next(iter(node))]
                self.refusal('invalid_recipe', Recipe.from_dict, value)
        self.refusal('invalid_json', parse_recipe, b'{"version":1,"version":1}')
        self.refusal('invalid_recipe', parse_recipe, b'{}')

    def test_recipe_wrong_types_before_callbacks(self):
        self.refusal('invalid_recipe', Recipe.from_dict, MappingProxyType(EvilMap()))
        for field in ('version', 'row_dims', 'columns'):
            value = recipe(); value[field] = Evil()
            self.refusal('invalid_recipe', Recipe.from_dict, value)
        for field in ('name','source','source_unit','target_unit','broadcast','stages'):
            value=recipe(); value['columns'][0][field]=Evil()
            self.refusal('invalid_recipe', Recipe.from_dict, value)
        for field in ('name','dims','op','missing','min_count','weights','weight_unit'):
            value=recipe([stage(True)]); value['columns'][0]['stages'][0][field]=Evil()
            self.refusal('invalid_recipe', Recipe.from_dict, value)
        class Key(str):
            def __eq__(self, other): raise AssertionError('key equality')
            __hash__ = str.__hash__
        bad={Key('version'):1,'row_dims':[],'columns':[]}
        self.refusal('invalid_recipe', Recipe.from_dict, bad)

    def test_recipe_structural_topology_refusals(self):
        bad=[]
        obj=recipe(); obj['version']=True; bad.append(obj)
        obj=recipe(); obj['row_dims']=['a','a']; bad.append(obj)
        obj=recipe(); obj['row_dims']=tuple(obj['row_dims']); bad.append(obj)
        obj=recipe(); obj['columns']=[]; bad.append(obj)
        obj=recipe(); obj['columns']*=33; bad.append(obj)
        obj=recipe(); obj['columns']*=2; bad.append(obj)
        obj=recipe([stage(),stage(name='other',dims=['r2']),stage(name='third',dims=['r3'])]); bad.append(obj)
        obj=recipe([stage(),stage(name='stage',dims=['r2'])]); bad.append(obj)
        obj=recipe([stage(),stage(name='other')]); bad.append(obj)
        obj=recipe([stage(dims=['key:00'])]); bad.append(obj)
        obj=recipe([stage(dims=[])]); bad.append(obj)
        obj=recipe([stage(dims=['a','a'])]); bad.append(obj)
        obj=recipe(); obj['columns'][0]['broadcast']=['key:00','key:00']; bad.append(obj)
        for min_count in (True,0,67108865,1.0,'1'):
            obj=recipe([stage()]); obj['columns'][0]['stages'][0]['min_count']=min_count; bad.append(obj)
        for field, value in (('op','sum'),('missing','omit'),('weights','x'),('weight_unit',None)):
            obj=recipe([stage()]); obj['columns'][0]['stages'][0][field]=value; bad.append(obj)
        obj=recipe([stage(True)]); del obj['columns'][0]['stages'][0]['weight_unit']; bad.append(obj)
        for value in bad:
            with self.subTest(value=value): self.refusal('invalid_recipe', Recipe.from_dict, value)

    def test_primitive_name_and_unit_rules(self):
        for name in ('n_valid','stage','value','key:00','a " <>& 😀','é'*64):
            self.assertEqual(validate_name(name), name)
        for value in ('', 'é'*65, 'a/b', 'a\\b', '\x00', '\x1f', '\x7f','\x85','\ud800', Evil(), True):
            self.refusal('invalid_source', validate_name, value)
        self.assertIsNone(validate_unit(None))
        self.assertEqual(validate_unit('m/s'), 'm/s')
        self.assertEqual(validate_unit('x'*512), 'x'*512)
        for value in ('','x'*513,'s\tsince','\ud800', True, Evil()):
            self.refusal('invalid_source', validate_unit, value)
        self.assertEqual(validate_unit('s\tsince 2000-1-1', raw_coordinate=True), 's\tsince 2000-1-1')
        self.refusal('invalid_source', exact_int, True, 'invalid_source')
        self.assertEqual(exact_int(2**63-1, 'invalid_source'), 2**63-1)
        self.refusal('invalid_source', exact_int, 2**63, 'invalid_source')

    def test_source_identity_exact_and_immutable(self):
        data=dict(kind='memory',sha256='a'*64,size_bytes=2**63-1)
        identity=SourceIdentity.from_dict(data)
        self.assertEqual(identity.to_json(), canonical_bytes(data))
        for field, value in (('kind',Evil()),('sha256',Evil()),('size_bytes',True),('size_bytes',-1),('kind','url'),('sha256','A'*64)):
            candidate=dict(data); candidate[field]=value
            self.refusal('invalid_source', SourceIdentity.from_dict, candidate)
        self.refusal('invalid_source', SourceIdentity.from_dict, MappingProxyType(EvilMap()))

    def test_numeric_coordinate_types_ranges_width_and_order(self):
        examples = [('|i1', [-128,127], [0,1]), ('|u1',[255,0],[1,0]),
                    ('<i2',[-32768,32767],[0,1]), ('<u2',[65535],[0]),
                    ('<i4',[-2**31,2**31-1],[0,1]), ('<u4',[2**32-1],[0]),
                    ('<i8',[2**53+1,-2**63,2**63-1],[1,0,2]), ('<u8',[2**64-1,2**53+1],[1,0]),
                    ('<f4',[16777216.0,-0.0,0.5],[1,2,0]), ('<f8',[-0.0,1.5],[0,1]),
                    ('<U4',['😀','', 'é'],[1,2,0])]
        for dtype, values, order in examples:
            with self.subTest(dtype=dtype):
                coordinate=Coordinate(dtype,values,order)
                self.assertEqual(coordinate.dtype,dtype)
                self.assertEqual(coordinate.values,tuple(values))
                self.assertEqual(coordinate.sorted_indices,tuple(order))
                self.assertEqual(coordinate.to_json(),canonical_bytes(dict(dtype=dtype,values=values,sorted_indices=order)))
        coordinate=Coordinate('<f8',[-0.0],[0])
        self.assertEqual(math.copysign(1,coordinate.values[0]),-1)

    def test_coordinate_refusals_before_sort_or_lookup(self):
        cases=[('int64',[1],[0]),('>i8',[1],[0]),('<U0',[''],[0]),('<U4097',['x'],[0]),
               ('<i8',[True],[0]),('<i8',[1.0],[0]),('<u8',[-1],[0]),('<i8',[2**63],[0]),
               ('<f8',[1],[0]),('<f4',[0.1],[0]),('<U1',['ab'],[0]),('<U2',[b'x'],[0]),
               ('<U1',['\ud800'],[0]),('<i8',[Evil()],[0]),
               ('<i8',[],[]),('<i8',[1],[True]),('<i8',[2,1],[0,1]),('<i8',[1,2],[0,0]),
               ('<i8',[1,2],[0]),('<i8',[1,2],[0,Evil()])]
        for dtype,values,order in cases:
            self.refusal('invalid_coordinate',Coordinate,dtype,values,order)
        for values in ([1,1],): self.refusal('duplicate_coordinate',Coordinate,'<i8',values,[0,1])
        self.refusal('duplicate_coordinate',Coordinate,'<f8',[0.0,-0.0],[0,1])
        for value in (None,float('nan')):
            self.refusal('missing_coordinate',Coordinate,'<f8',[value],[0])
            self.refusal('missing_row_key',Coordinate,'<f8',[value],[0],row=True)
        for value in (float('inf'),float('-inf')):
            self.refusal('nonfinite_coordinate',Coordinate,'<f8',[value],[0])

    def test_fixed_s_decode_is_separate_exact_raw_bytes_route(self):
        coordinate=Coordinate.from_fixed_bytes('|S4', b'a\0b\0'+b'\xc3\xa9\0\0')
        self.assertEqual(coordinate.dtype,'<U4')
        self.assertEqual(coordinate.values,('a\0b','é'))
        self.assertEqual(coordinate.sorted_indices,(0,1))
        for dtype,raw in (('|S0',b''),('|S4097',b'x'),('|S4',b'x'),('|S1',b'\xff'),('|S1',bytearray(b'a'))):
            self.refusal('invalid_coordinate',Coordinate.from_fixed_bytes,dtype,raw)
        self.refusal('coordinate_bytes_limit',Coordinate.from_fixed_bytes,'|S1',b'a'*(8*1024*1024+1))

    def test_coordinate_input_lists_are_not_retained(self):
        values=['a','b']; order=[0,1]
        coordinate=Coordinate('<U3',values,order)
        values[0]='changed'; order.reverse()
        self.assertEqual(coordinate.values,('a','b'))
        self.assertEqual(coordinate.sorted_indices,(0,1))

    def test_array_buffer_shape_dtype_size_then_readonly_views(self):
        buffer=ArrayBuffer('uint64',[2],struct.pack('<QQ',2**64-1,2**53+1))
        self.assertEqual(buffer.dtype,'uint64')
        self.assertEqual(buffer.shape,(2,))
        self.assertEqual(buffer.nbytes,16)
        self.assertEqual(buffer.data,struct.pack('<QQ',2**64-1,2**53+1))
        # NumPy need not be installed to run the stdlib foundation tests.
        import importlib.util
        if importlib.util.find_spec('numpy') is not None:
            a,b=buffer.view(),buffer.view()
            self.assertIsNot(a,b)
            self.assertFalse(a.flags.writeable)
            self.assertEqual(a.tolist(),[2**64-1,2**53+1])
            with self.assertRaises(ValueError): a.setflags(write=True)
        self.assertEqual(ArrayBuffer('float64',[],struct.pack('<d',float('nan'))).nbytes,8)
        for dtype,shape,data in (('object',[1],b'12345678'),('>i8',[1],b'12345678'),('int64',[True],b'12345678'),
                                 ('int64',[0],b''),('int64',[1],b''),('int64',[1],bytearray(8)),
                                 ('int64',Evil(),b''),('int64',[1]*17,b'12345678')):
            self.refusal('invalid_source',ArrayBuffer,dtype,shape,data)
        self.refusal('selected_numeric_bytes_limit',ArrayBuffer,'float64',[67108864],b'')
        self.assertEqual(numeric_dtype('<i8'),'int64')
        self.assertEqual(numeric_dtype('float32'),'float32')

    def test_metadata_tags_are_injective_and_owned(self):
        data={'null':None,'str':'nan','nan':float('nan'),'inf':float('inf'),'neg':float('-inf'),
              'bool':True,'int':2**64-1,'float':-0.0,'list':[{'type':'null'},'😀']}
        tagged=MetadataValue(data)
        projection=tagged.to_dict()
        self.assertEqual(projection['type'],'map')
        items=dict(projection['items'])
        self.assertEqual(items['nan'],{'type':'float_special','value':'nan'})
        self.assertEqual(items['str'],{'type':'str','value':'nan'})
        self.assertEqual(items['null'],{'type':'null'})
        self.assertEqual(MetadataValue.from_dict(projection).to_json(),tagged.to_json())
        data['list'].append('mutated')
        self.assertEqual(len(dict(tagged.to_dict()['items'])['list']['items']),2)
        for value in (Evil(), {'x': Evil()}, MappingProxyType(EvilMap()), {'x':b'bytes'}, {'x':'a'*4097}):
            self.refusal('invalid_source',MetadataValue,value)
        for raw in ({'type':'null','value':None}, {'type':Evil()}, {'type':'float_special','value':Evil()},
                    {'type':'float','value':1}, {'type':'map','items':[['x',{'type':'null'}],['x',{'type':'null'}]]}):
            self.refusal('invalid_source',MetadataValue.from_dict,raw)
        self.assertEqual(descriptor_object_scalar(None).to_dict(),{'type':'null'})
        self.assertEqual(descriptor_object_scalar('nan').to_dict(),{'type':'str','value':'nan'})
        self.assertEqual(descriptor_object_scalar(float('nan')).to_dict(),{'type':'float_special','value':'nan'})
        for value in (b'nan',1,1.0,True,Evil()):
            self.refusal('unsupported_source_storage',descriptor_object_scalar,value)

    def test_metadata_ancillary_limits(self):
        self.assertIsInstance(MetadataValue({'x': ['a']*1024}),MetadataValue)
        for value in ({str(i):0 for i in range(65)}, ['a']*1025):
            self.refusal('metadata_bytes_limit',MetadataValue,value)
        value=0
        for _ in range(8): value=[value]
        self.assertIsInstance(MetadataValue(value),MetadataValue)
        self.refusal('metadata_bytes_limit',MetadataValue,[value])
