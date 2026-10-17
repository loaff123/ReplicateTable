"""Finite regressions for the four independent B1 review findings."""
import copy
import struct
import unittest
from unittest.mock import patch

from replicatetable import ArrayBuffer, Coordinate, Recipe, Refusal, SourceIdentity
from replicatetable.codec import canonical_bytes, exact_int, json_prepass, strict_loads
from replicatetable.model import MetadataValue
from tests.unit.test_models import recipe


class Revision1Tests(unittest.TestCase):
    def refusal(self, code, function, *args, **kwargs):
        with self.assertRaises(Refusal) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code,code)
        return caught.exception

    def cases(self):
        columns=recipe()['columns']
        return [
            (SourceIdentity,('memory','a'*64,1),('file','b'*64,2),('bad',[],True),'invalid_source'),
            (Coordinate,('<i8',[1],[0]),('<i8',[2],[0]),('<i8',[2],[True]),'invalid_coordinate'),
            (ArrayBuffer,('int64',[1],struct.pack('<q',1)),('int64',[1],struct.pack('<q',2)),
             ('int64',[1],bytearray(struct.pack('<q',2))),'invalid_source'),
            (MetadataValue,({'x':[1]},),({'x':[2]},),({'x':bytearray(1)},),'invalid_source'),
            (Recipe,(1,['key:00'],columns),(1,[],columns),(True,[],columns),'invalid_recipe'),
        ]

    def snapshot(self, value):
        if type(value) is ArrayBuffer:
            return (value.dtype,value.shape,value.data)
        return value.to_json()

    def test_valid_and_invalid_repeat_initialization_cannot_change_any_model(self):
        for cls,valid,repeated,bad,code in self.cases():
            for candidate in (repeated,bad):
                with self.subTest(model=cls.__name__,candidate_type='valid' if candidate is repeated else 'invalid'):
                    instance=cls(*copy.deepcopy(valid)); original=self.snapshot(instance)
                    self.refusal(code,instance.__init__,*copy.deepcopy(candidate))
                    self.assertEqual(self.snapshot(instance),original)
                    if type(instance) is ArrayBuffer:
                        self.assertIs(type(instance.shape),tuple)
                        self.assertIs(type(instance.data),bytes)
                    if type(instance) is Recipe:
                        self.assertIs(type(instance.row_dims),tuple)
                        self.assertIs(type(instance.columns),tuple)

    def test_refused_buffer_repeat_never_inserts_writable_aliases(self):
        buffer=ArrayBuffer('int64',[1],struct.pack('<q',1))
        shape=[1]; raw=bytearray(struct.pack('<q',2))
        self.refusal('invalid_source',buffer.__init__,'int64',shape,raw)
        self.assertIsNot(buffer.shape,shape); self.assertIsNot(buffer.data,raw)
        shape[0]=9; raw[0]=99
        self.assertEqual(buffer.shape,(1,)); self.assertEqual(struct.unpack('<q',buffer.data),(1,))
        view=buffer.view()
        self.assertFalse(view.flags.writeable)
        with self.assertRaises(ValueError): view[0]=7

    def test_failed_first_initialization_leaves_no_fields_published(self):
        # Ordinary allocation/initialization separation, no pointer manipulation.
        for cls,valid,repeated,bad,code in self.cases():
            with self.subTest(model=cls.__name__):
                instance=cls.__new__(cls)
                self.refusal(code,instance.__init__,*copy.deepcopy(bad))
                for field in cls.__slots__:
                    self.assertFalse(hasattr(instance,field),field)
                instance.__init__(*copy.deepcopy(valid))
                self.assertEqual(self.snapshot(instance),self.snapshot(cls(*copy.deepcopy(valid))))

    def test_exact_int_range_parameters_are_exact_before_comparison(self):
        class Hook:
            def __gt__(self, other): raise AssertionError('comparison hook')
            def __lt__(self, other): raise AssertionError('comparison hook')
        class Integer(int): pass
        for bad in (Hook(),True,False,1.0,float('nan'),Integer(0),'0',None):
            with self.subTest(bound=type(bad)):
                self.refusal('invalid_source',exact_int,0,minimum=bad)
                self.refusal('invalid_source',exact_int,0,maximum=bad)
        self.refusal('invalid_source',exact_int,0,minimum=1,maximum=0)
        self.assertEqual(exact_int(-2**63,minimum=-2**63,maximum=2**64-1),-2**63)
        self.assertEqual(exact_int(2**64-1,minimum=-2**63,maximum=2**64-1),2**64-1)
        self.assertEqual(exact_int(0,minimum=0,maximum=0),0)

    def test_coordinate_limit_messages_identify_the_measured_subtype(self):
        cases=[
            ('Raw coordinate storage exceeds its byte limit.',Coordinate.from_fixed_bytes,('|S1',b'a'*(8*1048576+1))),
            ('Canonical coordinate representation exceeds its byte limit.',Coordinate.from_fixed_bytes,('|S1',b'a'*250000)),
            ('Coordinate label union exceeds its UTF-8 byte limit.',Coordinate,('<U4096',['a'*4096]*2049,list(range(2049)))),
        ]
        for expected,method,args in cases:
            with self.subTest(expected=expected):
                error=self.refusal('coordinate_bytes_limit',method,*args)
                self.assertEqual(error.message,expected)
                self.assertEqual(error.exit_code,2)
                self.assertTrue(error.message.isascii())

    def test_key_scratch_is_reserved_before_token_decode(self):
        raw=canonical_bytes({'a'*1024+'😀':0}).rstrip(b'\n')
        self.assertEqual(len(raw),1034)
        with patch('replicatetable.codec.json.loads',side_effect=AssertionError('unreserved key decode')):
            self.refusal('estimated_memory_limit',json_prepass,raw,object_limit=5008)

    def test_key_scan_peak_is_distinct_from_final_forest_p(self):
        raw=canonical_bytes({'a'*1024+'😀':0}).rstrip(b'\n')
        scan=json_prepass(raw)
        self.assertEqual(scan.object_bytes,5008)
        self.assertGreater(scan.scan_peak_bytes,scan.object_bytes)
        self.assertEqual(scan.key_scratch_bytes,(128+1030)+(128+4*1030))
        self.assertEqual(json_prepass(raw,object_limit=scan.scan_peak_bytes),scan)
        self.refusal('estimated_memory_limit',json_prepass,raw,object_limit=scan.scan_peak_bytes-1)

    def test_baseline_and_raw_admission_precedes_scanner_creation(self):
        limit=512*1048576
        with patch('replicatetable.codec._Scanner',side_effect=AssertionError('scanner constructed before remaining budget')):
            self.refusal('estimated_memory_limit',strict_loads,b'null',baseline_bytes=limit-3)
            self.refusal('estimated_memory_limit',json_prepass,b'null',baseline_bytes=limit-3)

    def test_full_decode_reserves_existing_five_n_plus_three_p(self):
        limit=512*1048576
        raw=b'[0]'; p=512+128+128
        baseline=limit-(5*len(raw)+3*p)
        self.assertEqual(strict_loads(raw,baseline_bytes=baseline),[0])
        with patch('replicatetable.codec.json.loads',side_effect=AssertionError('full decoder ran before model admission')):
            self.refusal('estimated_memory_limit',strict_loads,raw,baseline_bytes=baseline+1)

    def test_budget_parameters_cannot_suppress_standalone_runtime_baseline(self):
        baseline=130*1048576
        for bad in (True,0,baseline-1,float('nan'),object()):
            self.refusal('invalid_json',strict_loads,b'null',baseline_bytes=bad)
        self.assertEqual(strict_loads(b'null',baseline_bytes=baseline),None)

    def test_all_budget_arguments_are_exact_before_arithmetic(self):
        class Integer(int): pass
        class Hook:
            def __lt__(self, other): raise AssertionError('comparison hook')
            def __gt__(self, other): raise AssertionError('comparison hook')
            def __sub__(self, other): raise AssertionError('subtraction hook')
            def __rsub__(self, other): raise AssertionError('subtraction hook')
        for loader in (json_prepass,strict_loads):
            for name in ('limit','object_limit','baseline_bytes'):
                for bad in (True,1.0,float('nan'),Integer(130*1048576),Hook()):
                    with self.subTest(loader=loader.__name__,argument=name,bad_type=type(bad)):
                        self.refusal('invalid_json',loader,b'null',**{name:bad})
            self.refusal('invalid_json',loader,b'null',object_limit=-1)
            self.refusal('invalid_json',loader,b'null',object_limit=512*1048576+1)
            self.refusal('invalid_json',loader,b'null',baseline_bytes=512*1048576+1)

    def test_scan_peak_counters_cover_no_key_nested_and_escaped_controls(self):
        # Expected raw-string counters are independent literal calculations.
        for raw,forest,peak,scratch in (
            (b'null',128,128,0), (b'[]',512,512,0), (b'[0]',768,768,0),
            (b'{"a":{"b":0}}',1672,1815,271),
            (br'{"\u0061":0}',920,1088,296),
        ):
            with self.subTest(raw=raw):
                scan=json_prepass(raw)
                self.assertEqual(scan.object_bytes,forest)
                self.assertEqual(scan.scan_peak_bytes,peak)
                self.assertEqual(scan.key_scratch_bytes,scratch)

    def test_remaining_enclosing_budget_also_limits_key_scratch(self):
        raw=canonical_bytes({'a'*1024+'😀':0}).rstrip(b'\n')
        scan=json_prepass(raw)
        baseline=512*1048576-len(raw)-scan.scan_peak_bytes
        self.assertEqual(json_prepass(raw,baseline_bytes=baseline),scan)
        with patch('replicatetable.codec.json.loads',side_effect=AssertionError('key decoder exceeded enclosing budget')):
            self.refusal('estimated_memory_limit',json_prepass,raw,baseline_bytes=baseline+1)
