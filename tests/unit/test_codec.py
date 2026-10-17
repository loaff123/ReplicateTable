"""Strict parsing must reject malformed/over-budget input before full decoding.

These tests detect permissive json.loads, coercing serializers, and unchecked
mapping/primitive callbacks, not a particular parser implementation.
"""
import json
import math
import subprocess
import sys
from types import MappingProxyType
import unittest

from replicatetable.codec import (canonical_bytes, iter_json_chunks, json_prepass,
                                 strict_loads, primitive_bounds)
from replicatetable.model import Refusal, freeze, thaw, OwnedMap, utf8_length, preflight_json


class Evil:
    def __eq__(self, other):
        raise AssertionError('equality callback')
    def __hash__(self):
        raise AssertionError('hash callback')
    def __iter__(self):
        raise AssertionError('iteration callback')
    def __str__(self):
        raise AssertionError('str callback')
    def __int__(self):
        raise AssertionError('int callback')


class EvilMap:
    def __getitem__(self, key):
        raise AssertionError('mapping callback')
    def __iter__(self):
        raise AssertionError('mapping iteration')
    def __len__(self):
        raise AssertionError('mapping length')


class CodecTests(unittest.TestCase):
    def refusal(self, expected_code, function, *args, **kwargs):
        with self.assertRaises(Refusal) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected_code)
        self.assertEqual(caught.exception.exit_code, 2)

    def test_canonical_typed_golden(self):
        value = {'z': -0.0, 'a': [-(2**63), 2**64-1, 9007199254740993, '', 'é😀', True, None], 'f': 1.0}
        expected = ('{"a":[-9223372036854775808,18446744073709551615,9007199254740993,"","é😀",true,null],"f":1.0,"z":-0.0}\n').encode()
        self.assertEqual(canonical_bytes(value), expected)
        self.assertEqual(b''.join(iter_json_chunks(value)), expected)
        parsed = strict_loads(expected)
        self.assertIs(type(parsed['a'][0]), int)
        self.assertIs(type(parsed['f']), float)
        self.assertEqual(math.copysign(1, parsed['z']), -1)
        self.assertEqual(strict_loads(b' \n[]\t\r '), [])

    def test_invalid_lexemes(self):
        for raw in (b'', b'\xef\xbb\xbf{}', b'\xff', b'"\xc0\xaf"', b'"\xed\xa0\x80"',
                    b'"\xf4\x90\x80\x80"', br'"\ud800"', br'"\udfff"', br'"\ud800x"',
                    br'"\ud800\u0041"', br'"\u000g"', b'"\n"', b'"\x00"', b'"\\x"',
                    b'NaN', b'Infinity', b'-Infinity', b'1e400', b'01', b'+1', b'.1', b'1.',
                    b'1e', b'1e+', b'--1', b'truex', b'[]{}', b'{"x":1,}', b'[1,]',
                    b'{1:2}', b'{"x" 1}', b'{"x":}', b'\v[]', b'\xc2\xa0[]'):
            with self.subTest(raw=raw):
                self.refusal('invalid_json', strict_loads, raw)

    def test_escaped_supplementary_and_controls(self):
        self.assertEqual(strict_loads(br'"\ud83d\ude00"'), '😀')
        self.assertEqual(strict_loads(br'"\u0000\b\f\n\r\t"'), '\0\b\f\n\r\t')
        self.assertEqual(canonical_bytes('\0\b\f\n\r\t'), br'"\u0000\b\f\n\r\t"'+b'\n')

    def test_duplicates_include_equivalent_escapes_and_nested_objects(self):
        for raw in (b'{"x":1,"x":2}', br'{"x":1,"\u0078":2}',
                    b'[{"a":{"b":1,"b":2}}]', '{"é":1,"\\u00e9":2}'.encode()):
            self.refusal('invalid_json', strict_loads, raw)
        self.assertEqual(strict_loads(b'[{"x":1},{"x":2}]'), [{'x':1}, {'x':2}])

    def test_depth_equality_and_plus_one(self):
        self.assertEqual(json_prepass(b'['*32+b'0'+b']'*32).max_depth, 32)
        self.refusal('invalid_json', strict_loads, b'['*33+b'0'+b']'*33)

    def test_numeric_token_ascii_and_range(self):
        for number in (-(2**63), 2**63-1, 2**64-1, 2**53+1):
            self.assertEqual(strict_loads(str(number).encode()), number)
        for raw in (str(-(2**63)-1).encode(), str(2**64).encode(), '١'.encode()):
            self.refusal('invalid_json', strict_loads, raw)
        self.assertEqual(strict_loads(b'0.'+b'0'*30), 0.0)
        self.refusal('invalid_json', strict_loads, b'0.'+b'0'*31)

    def test_raw_exact_type_and_byte_limit_precede_decode(self):
        for value in ('{}', bytearray(b'{}'), memoryview(b'{}'), Evil()):
            self.refusal('invalid_json', strict_loads, value)
        self.assertEqual(strict_loads(b'[]', limit=2), [])
        self.refusal('metadata_bytes_limit', strict_loads, b'\xff'*3, limit=2)

    def test_prepass_counters_bound_primitives_without_decode_forest(self):
        value = {'x': [0, True, None, '😀'], 'y': {'\0': -0.0}}
        raw = canonical_bytes(value)
        scan = json_prepass(raw)
        self.assertEqual(scan.raw_bytes, len(raw))
        self.assertEqual(scan.containers, 3)
        self.assertEqual(scan.entries, 7)
        self.assertEqual(scan.scalars, 8)  # keys are scalar occurrences
        self.assertEqual(scan.strings, 4)
        self.assertGreaterEqual(scan.object_bytes, primitive_bounds(value).object_bytes)
        # The budget applies during scan and before the unrestricted JSON decoder.
        self.refusal('estimated_memory_limit', strict_loads, b'[0,0,0]', object_limit=511)
        self.refusal('estimated_memory_limit', json_prepass, b'{"large key":0}', object_limit=511)

    def test_serializer_rejects_unsafe_exact_types(self):
        class Str(str): pass
        class Int(int): pass
        class Dict(dict): pass
        class List(list): pass
        for value in (Evil(), Str('x'), Int(1), Dict(x=1), List([1]),
                      MappingProxyType({'x':1}), MappingProxyType(EvilMap()),
                      float('nan'), float('inf'), 2**64, {'x':'\ud800'}):
            with self.subTest(type=type(value)):
                self.refusal('invalid_json', canonical_bytes, value)
        for value in ({1:'x'}, {Str('x'):1}):
            self.refusal('invalid_json', freeze, value)

    def test_owned_map_copies_and_never_keeps_proxy_backing(self):
        original = {'b': [1, {'x':'y'}], 'a': -0.0}
        owned = freeze(original)
        self.assertIs(type(owned), OwnedMap)
        self.assertIs(type(owned['b']), tuple)
        original['b'][1]['x'] = 'changed'
        original['new'] = True
        self.assertEqual(thaw(owned), {'a': -0.0, 'b': [1, {'x':'y'}]})
        with self.assertRaises((AttributeError, TypeError)):
            owned._items = ()
        self.refusal('invalid_json', freeze, MappingProxyType(EvilMap()))
        self.refusal('invalid_json', OwnedMap, MappingProxyType(EvilMap()))
        self.refusal('invalid_json', owned.__getitem__, Evil())
        self.assertEqual(canonical_bytes(owned), b'{"a":-0.0,"b":[1,{"x":"y"}]}\n')

    def test_primitive_bounds_and_incremental_utf8(self):
        self.assertEqual((primitive_bounds(None).json_bytes, primitive_bounds(None).object_bytes), (4,128))
        self.assertEqual(primitive_bounds(True).json_bytes, 5)
        self.assertEqual(primitive_bounds(0).json_bytes, 32)
        self.assertEqual(primitive_bounds('é😀').json_bytes, 38)
        self.assertEqual(primitive_bounds([]).object_bytes, 512)
        self.assertEqual(primitive_bounds({'a': []}).json_bytes, 13)
        self.assertEqual(primitive_bounds({'a': []}).object_bytes, 1284)
        self.assertEqual(utf8_length('é😀'), 6)
        self.refusal('invalid_json', utf8_length, '\ud800')
        self.refusal('label_bytes_limit', utf8_length, '😀', 'label_bytes_limit', maximum=3)
        self.assertEqual(preflight_json({'x': 0}, limit=100), 44)
        self.refusal('metadata_bytes_limit', preflight_json, {'x': 0}, limit=43, code='metadata_bytes_limit')

    def test_stdlib_only_parse_in_fresh_process(self):
        code = '''import sys
from replicatetable import parse_recipe
parse_recipe(b'{"version":1,"row_dims":[],"columns":[{"name":"x","source":"x","source_unit":null,"target_unit":null,"broadcast":[],"stages":[]}]}')
assert not ({'numpy','pandas','xarray','pint','h5py','h5netcdf'} & set(sys.modules))
'''
        completed = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
