"""B2 scalar-only tests. No source/native admission claim."""
import importlib
import math
import unittest
from unittest.mock import patch
from replicatetable import codec
from replicatetable.errors import Refusal


def core():
    name = 'replicatetable._resource_bounds'
    assert importlib.util.find_spec(name) is not None, 'B2 symbolic bounds module is missing'
    return importlib.import_module(name)


class ResourceBoundsTests(unittest.TestCase):
    def test_b2_001_literal_closed_form(self):
        for value,j,p in [(None,4,128),(False,5,128),(True,5,128),
                (-(2**63),32,128),(2**64-1,32,128),(-0.0,32,128),('',2,128),
                ('abc',20,140),('"\n',14,136),('😀',26,144)]:
            b=core()._literal_cost(value)
            assert (b.json_bytes,b.object_bytes)==(j,p)
            assert codec.primitive_bounds(value).json_bytes==j
            assert len(codec.canonical_bytes(value))<=j+1


    def test_b2_002_containers_occurrences(self):
        m=core(); n=m._literal_cost(1)
        assert m._list_cost(())==m._JP(2,512)
        assert m._map_cost(())==m._JP(2,512)
        assert m._map_cost((m._FieldCost('x',n),m._FieldCost('y',n)))==m._JP(85,1288)
        assert m._list_cost((n,n))==m._JP(67,1024)


    def test_b2_003_repeat_is_scalar(self):
        m=core(); n=m._literal_cost(1)
        m.range=lambda *args: self.fail('cardinality expansion')
        for k in (0,1,2,100000):
            assert m._repeat_cost(k,n)==m._JP(2+max(0,k-1)+32*k,512+256*k)
        assert m._concat_repeats_cost((m._RepeatBlock(2,n),m._RepeatBlock(3,n)))==m._repeat_cost(5,n)


    def test_b2_004_exact_types_before_hooks(self):
        m=core()
        class Trap:
            def __eq__(self,other): raise AssertionError('equality hook')
            def __int__(self): raise AssertionError('conversion hook')
            def __len__(self): raise AssertionError('length hook')
        for x in (True,1.0,Trap(),-1,2**63):
            with self.assertRaises(Refusal): m._checked_add(x,0,limit=2**63-1,code='work_cell_limit')
        for x in (Trap(),float('nan'),float('inf')):
            with self.assertRaises(Refusal): m._literal_cost(x)
        with self.assertRaises(Refusal): m._map_cost((m._FieldCost('x',m._JP(1,1)),m._FieldCost('x',m._JP(1,1))))


    def test_b2_005_checked_arithmetic_boundaries(self):
        m=core()
        for cap in (0,1,100,2**63-1):
            assert m._checked_add(cap,0,limit=cap,code='work_cell_limit')==cap
            with self.assertRaises(Refusal) as e: m._checked_add(cap,1,limit=cap,code='work_cell_limit')
            assert e.exception.code=='work_cell_limit'
        assert m._checked_mul(0,2**63-1,limit=0,code='work_cell_limit')==0
        with self.assertRaises(Refusal): m._checked_mul(0,2**63,limit=0,code='work_cell_limit')
        assert m._checked_mul(2,50,limit=100,code='work_cell_limit')==100
        with self.assertRaises(Refusal): m._checked_mul(2,51,limit=100,code='work_cell_limit')


    def test_b2_006_shape_and_log(self):
        m=core()
        for shape,product in [((),1),((1,),1),((2,3),6),((1,)*16,1)]:
            assert m._shape_product(shape)==product
        for shape in ((0,),(True,),(67108865,),(67108864,2),(1,)*17):
            with self.assertRaises(Refusal): m._shape_product(shape)
        assert [m._ceil_log2_ge2(x) for x in (1,2,3,4,7,8,9,67108864)]==[1,1,2,2,3,3,4,26]


    def test_b2_032_exact_estimate_block(self):
        m=core()
        assert len(m.ESTIMATE_KEYS)==31 and len(set(m.ESTIMATE_KEYS))==31
        assert m.ESTIMATE_COST==m._JP(4357,14576)
        assert m.QUERY_ENVELOPE_BYTES==5519872


    def test_b2_060_frozen_cap_equality_plus_one(self):
        m=core()
        for key,(cap,code) in m._CAPS.items():
            assert m._check_cap(key,cap)==cap
            with self.assertRaises(Refusal) as e: m._check_cap(key,cap+1)
            assert e.exception.code==code
