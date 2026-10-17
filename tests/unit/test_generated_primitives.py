"""Deterministic small independent parser/canonical comparisons, not qualification."""
import json
import math
import random
import unittest
from replicatetable import Refusal
from replicatetable.codec import canonical_bytes, json_prepass, primitive_bounds, strict_loads
from replicatetable.model import MetadataValue


class GeneratedPrimitiveTests(unittest.TestCase):
    def test_small_primitive_roundtrips_and_prepass_bounds(self):
        rng=random.Random(168023)
        scalars=[None,False,True,-2**63,2**64-1,2**53+1,0,1,0.0,-0.0,1e-320,
                 1.7976931348623157e308,'','"\\\0\n\t','é😀','\U0010ffff','\x85']
        def value(depth):
            if depth==0 or rng.randrange(3)==0: return rng.choice(scalars)
            if rng.randrange(2): return [value(depth-1) for _ in range(rng.randrange(5))]
            return {key:value(depth-1) for key in rng.sample(['a','z','é','😀','\0','"'],rng.randrange(5))}
        for _ in range(300):
            original=value(4)
            expected=(json.dumps(original,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
            actual=canonical_bytes(original)
            self.assertEqual(actual,expected)
            self.assertEqual(canonical_bytes(strict_loads(actual)),actual)
            scan=json_prepass(actual)
            bound=primitive_bounds(original)
            self.assertGreaterEqual(scan.object_bytes,bound.object_bytes)
            self.assertGreaterEqual(scan.json_bytes_bound,bound.json_bytes)

    def test_typed_metadata_nonfinite_roundtrip_and_nested_tag_strings(self):
        originals=[None,True,False,1,1.0,-0.0,'nan','+inf','-inf',float('nan'),float('inf'),float('-inf'),
                   {'type':'float_special','value':'nan'}, [{'type':'null'}]]
        encodings=set()
        for original in originals:
            model=MetadataValue(original)
            raw=model.to_json()
            self.assertNotIn(raw,encodings)
            encodings.add(raw)
            decoded=MetadataValue.from_dict(strict_loads(raw))
            self.assertEqual(decoded.to_json(),raw)
            self.assertEqual(MetadataValue(decoded.to_python()).to_json(),raw)

    def test_unicode_depth_and_numeric_contract_boundaries(self):
        for scalar in ('"é"','"😀"','"\\ud83d\\ude00"','"\\u0000"','18446744073709551615','-0.0'):
            raw=scalar.encode()
            nested=b'['*32+raw+b']'*32
            self.assertEqual(canonical_bytes(strict_loads(nested)),canonical_bytes(json.loads(nested)))
            with self.assertRaises(Refusal): strict_loads(b'['+nested+b']')
