"""Fresh bounded stock grammar and pre-cancellation qualification regressions."""
import gc
import importlib.util
import math
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from replicatetable.errors import Refusal
from replicatetable import units


class StockUnitTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(units, 'qualify_conversion'), 'Stock qualification is absent')

    def refused(self, source, target, code):
        with self.assertRaises(Refusal) as caught:
            units.qualify_conversion(source, target)
        self.assertEqual(caught.exception.code, code)
        self.assertIsNone(caught.exception.__context__)
        self.assertIsNone(caught.exception.__cause__)
        return caught.exception

    def test_original_affine_multiplicative_labels(self):
        for source, target, scale, offset in (
                ('ms', 's', .001, 0.), ('s', 'ms', 1000., 0.),
                ('degC', 'K', 1., 273.15), ('degF', 'degC', 5/9, -160/9),
                ('m/s', 'km/h', 3.6, 0.), ('delta_degC', 'K', 1., 0.),
                ('second', None, 1., 0.), (None, None, 1., 0.)):
            with self.subTest(source=source, target=target):
                op = units.qualify_conversion(source, target)
                self.assertTrue(math.isclose(op.scale, scale, rel_tol=1e-12, abs_tol=1e-12))
                self.assertTrue(math.isclose(op.offset, offset, rel_tol=1e-12, abs_tol=1e-12))
                self.assertEqual((op.source_unit, op.target_unit), (source, target))
                self.assertEqual(units.UnitOperation.from_dict(op.to_dict()), op)

    def test_stock_empty_dimension_marker_is_semantically_dimensionless(self):
        for source,target,scale in (('rad','dimensionless',1.),('steradian','1',1.),
                ('degree','dimensionless',math.pi/180),('count','dimensionless',1.),
                ('radian**2','radian',1.)):
            with self.subTest(source=source,target=target):
                operation=units.qualify_conversion(source,target)
                self.assertTrue(math.isclose(operation.scale,scale,rel_tol=1e-12))
                self.assertEqual(operation.offset,0.)
                self.assertTrue(any(('[]',1) in node['reference'] for node in operation.definition_graph))
                self.assertEqual(units.UnitOperation.from_dict(operation.to_dict()),operation)
        for source,scale in (('radian',1.),('count',1.),('steradian',1.),('degree',math.pi/180)):
            with self.subTest(weight=source):
                operation=units.qualify_weight_unit(source)
                self.assertTrue(math.isclose(operation.scale,scale,rel_tol=1e-12))
                self.assertEqual(operation.target_unit,'dimensionless')
                self.assertTrue(any(('[]',1) in node['reference'] for node in operation.definition_graph))

    def test_original_unknown_incompatible_and_missing_assertion_controls(self):
        self.refused('not_a_known_unit', 'not_a_known_unit', 'unknown_unit')
        self.refused('kg', 's', 'incompatible_unit')
        self.refused(None, 's', 'missing_unit_assertion')

    def test_allowed_normalization_aliases_literal_powers_and_spaces(self):
        for source, target in (('meter per second', 'm/s'), ('m s**-1', 'm/s'),
                ('m^2', 'meter**2'), ('m²', 'meter**2'), ('m ** +0.5', 'meter**0.5'),
                ('m ** (-0.5)', 'meter**-0.5'), ('m×s', 'meter*second'),
                ('1/m', 'meter**-1'), ('(degC)**(+1)', 'degC'),
                ('%', 'percent'), ('‰', 'permille'), ('degree_Celsius', 'degC')):
            with self.subTest(source=source):
                op = units.qualify_conversion(source, target)
                self.assertEqual((op.scale, op.offset), (1., 0.))
        op = units.qualify_conversion('g_0', 'meter/second**2')
        self.assertEqual(op.scale, 9.80665)
        self.assertEqual([node['name'] for node in op.definition_graph], ['meter', 'second', 'standard_gravity'])

    def test_raw_canceled_leaves_are_qualified(self):
        for source, code in (('not_a_known_unit/not_a_known_unit', 'unknown_unit'),
                             ('dB/dB', 'unsupported_unit_converter'),
                             ('neper/neper', 'unsupported_unit_converter'),
                             ('degC/degC', 'unsupported_offset_unit')):
            self.refused(source, 'dimensionless', code)
        op = units.qualify_conversion('meter/meter', 'dimensionless')
        self.assertEqual(op.definition_graph, ())
        self.assertEqual(op.parsed_source, ())

    def test_offset_whole_syntax_is_single_name_or_one_literal_one_power(self):
        for source in ('degC*1', '1*degC', 'degC/1', 'degC**2', 'degC**0',
                       '(degC**1)**1', 'degC * meter/meter', 'degF/degF'):
            with self.subTest(source=source): self.refused(source, None, 'unsupported_offset_unit')
        for source in ('degC', '((degC))', '(degC)**(1)', 'degC**1.0'):
            self.assertEqual(units.qualify_conversion(source, 'K').offset, 273.15)

    def test_arithmetic_exponents_refuse_before_evaluate(self):
        import pint.pint_eval as pe
        for source in ('meter ** (2 ** 3)', 'meter ** (1 / 2)', 'meter**(1+1)',
                       '-meter', 'meter+meter', '2*meter', 'meter//second', '[length]'):
            with self.subTest(source=source), patch.object(pe.EvalTreeNode, 'evaluate', side_effect=AssertionError('evaluation before guard')):
                self.refused(source, source, 'invalid_unit')

    def test_raw_utf8_and_numeric_token_domain_guards(self):
        for source in ('m'+' '*512, 'm**'+'1'*33, 'm**1e309', 'm**18446744073709551616',
                       'm**-9223372036854775809', 'm\t', 'm\x00'):
            with self.subTest(source=source[:20]): self.refused(source, None, 'invalid_unit')
        self.assertEqual(units.qualify_conversion('m'+' '*511, 'm').scale, 1.)

    def test_parenthesis_depth_and_tree_depth_are_distinct(self):
        self.assertEqual(units.qualify_conversion('('*32+'m'+')'*32, 'm').scale, 1.)
        self.refused('('*33+'m'+')'*33, 'm', 'invalid_unit')
        self.assertEqual(units.qualify_conversion('*'.join(['m']*32), 'm**32').scale, 1.)
        self.refused('*'.join(['m']*33), 'm**33', 'invalid_unit')

    def test_guard_returns_only_bounded_leaf_names_and_syntax_fact(self):
        import pint.pint_eval as pe
        with patch.object(pe.EvalTreeNode, 'evaluate', side_effect=AssertionError('guard evaluated')):
            self.assertEqual(units._guard_label('((degC))**(+1)'), (('degC',), True))
            self.assertEqual(units._guard_label('m*m/m'), (('m', 'm', 'm'), False))

    def test_parse_receives_original_text_only_after_guard_frame_releases(self):
        import pint
        original = pint.UnitRegistry.parse_units
        calls = []
        def capture(registry, text, *args, **kwargs):
            frame = sys._getframe()
            while frame:
                self.assertNotEqual(frame.f_code.co_name, '_guard_label')
                frame = frame.f_back
            calls.append((text, kwargs))
            return original(registry, text, *args, **kwargs)
        with patch.object(pint.UnitRegistry, 'parse_units', capture):
            units.qualify_conversion('m per s', 'm/s')
        self.assertEqual(calls[:2], [('m per s', {'as_delta': False}), ('m/s', {'as_delta': False})])

    def test_stock_dimension_mismatch_precedes_quantity_conversion(self):
        with units._StockUnitContext() as ctx:
            registry = ctx._registry_for_attempt()
            with patch.object(registry.Quantity, 'to', side_effect=AssertionError('incompatible conversion invoked')):
                with self.assertRaises(Refusal) as caught: units.qualify_conversion('m', 's', context=ctx)
            self.assertEqual(caught.exception.code, 'incompatible_unit')

    def test_raw_aggregate_alias_occurrences_count_before_final_graph(self):
        # Finite scalar seam lowers only this test's admission limit, never production caps.
        with patch.object(units, 'MAX_GRAPH_REFERENCES', 4):
            self.refused('m*m/m', 'm', 'invalid_unit_operation')
        self.assertEqual(units.qualify_conversion('m*m/m', 'm').scale, 1.)

    def test_numeric_domain_refuses_before_stock_tree_builder(self):
        import pint.pint_eval as pe
        builder_code = pe.build_eval_tree.__code__
        for source in ('m**18446744073709551616', 'm**-9223372036854775809', 'm**1e309'):
            calls = []
            def observed(frame, event, arg):
                if event == 'call' and frame.f_code is builder_code: calls.append(1)
            previous = sys.getprofile(); sys.setprofile(observed)
            try: self.refused(source, None, 'invalid_unit')
            finally: sys.setprofile(previous)
            self.assertFalse(calls, source)

    def test_meaningful_token128_boundary_precedes_tree_builder(self):
        expression = 'm'
        for unused in range(5): expression = '(' + expression + '*' + expression + ')'
        # 32 leaves, 31 binary operators, 62 parentheses, **, +, 1 = 128.
        expression += '**+1'
        self.assertEqual(units.qualify_conversion(expression, 'm**32').scale, 1.)
        self.refused(expression + ' 1', 'm**32', 'invalid_unit')

    def test_aggregate_graph_limits_at_exact_and_one_over_scalar_seam(self):
        with patch.object(units, 'MAX_GRAPH_NODES', 3), patch.object(units, 'MAX_GRAPH_REFERENCES', 7):
            self.assertEqual(units.qualify_conversion('standard_gravity','m/s**2').scale, 9.80665)
        with patch.object(units, 'MAX_GRAPH_NODES', 2):
            self.refused('standard_gravity','m/s**2','invalid_unit_operation')
        with patch.object(units, 'MAX_GRAPH_REFERENCES', 6):
            self.refused('standard_gravity','m/s**2','invalid_unit_operation')

    def test_offset_weight_lineage_refuses_as_offset_normalization(self):
        with self.assertRaises(Refusal) as caught: units.qualify_weight_unit('degC')
        self.assertEqual(caught.exception.code, 'unsupported_offset_unit')

    def test_initial_tree_metadata_rejects_nonstring_without_comparison_hook(self):
        code = '''
import pint
from pint import pint_eval as pe
from replicatetable import units
from replicatetable.errors import Refusal
calls=[]
class Trap:
 def __eq__(self,other): calls.append(1); raise AssertionError('metadata comparison hook')
class Foreign: pass
Foreign.__module__=Trap()
pe.EvalTreeNode=Foreign
try: units.qualify_conversion('s','s')
except Refusal as error: assert error.code=='invalid_unit_operation'
else: raise AssertionError('foreign tree accepted')
assert not calls
'''
        result=subprocess.run([sys.executable,'-B','-c',code],env=os.environ.copy(),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_parserhelper_replacement_refuses_before_initial_callback(self):
        code = '''
import pint
from pint import util
from replicatetable import units
from replicatetable.errors import Refusal
calls=[]
def trap(*a,**k): calls.append(1); raise AssertionError('replacement helper invoked')
trap.cache_parameters=lambda:{'maxsize':128,'typed':False}
util.ParserHelper.from_string=classmethod(trap)
try: units.qualify_conversion('s','s')
except Refusal as error: assert error.code=='invalid_unit_operation'
else: raise AssertionError('replacement accepted')
assert not calls
'''
        result=subprocess.run([sys.executable,'-B','-c',code],env=os.environ.copy(),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_factory_and_parser_alias_substitutions_refuse_before_callback(self):
        for target in ('factory_root', 'factory_pair', 'factory_class_pair', 'factory_meta_pair', 'factory_class_root', 'plain', 'tokenizer', 'both_tokenizers', 'preprocessor', 'builder', 'util_builder'):
            code = '''
from unittest.mock import patch
import pint
from pint import pint_eval as pe, util
from replicatetable import units
from replicatetable.errors import Refusal
called=[]
def trap(*a, **k): called.append(True); raise AssertionError('callback invoked')
TARGET=%r
if TARGET=='factory_root': pint.UnitRegistry=trap
elif TARGET=='factory_pair': pint.UnitRegistry=pint.registry.UnitRegistry=trap
elif TARGET in ('factory_class_pair','factory_class_root'):
 class Foreign:
  def __init__(self): trap()
 pint.UnitRegistry=Foreign
 if TARGET=='factory_class_pair': pint.registry.UnitRegistry=Foreign
elif TARGET=='factory_meta_pair':
 class ForeignMeta(type):
  def __call__(self,*a,**k): trap()
 class Foreign(metaclass=ForeignMeta): pass
 pint.UnitRegistry=pint.registry.UnitRegistry=Foreign
elif TARGET=='plain': pe.plain_tokenizer=trap
elif TARGET=='tokenizer': pe.tokenizer=trap
elif TARGET=='both_tokenizers': pe.tokenizer=pe.plain_tokenizer=trap
elif TARGET=='preprocessor': util.string_preprocessor=trap
elif TARGET=='builder': pe.build_eval_tree=trap
else: util.build_eval_tree=trap
try: units.qualify_conversion('s','s')
except Refusal as exc: assert exc.code=='invalid_unit_operation',exc.code
else: raise AssertionError('substitution accepted')
assert not called
''' % target
            with self.subTest(target=target):
                result = subprocess.run([sys.executable, '-B', '-c', code], env=os.environ.copy(), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)


def run_guard_probe():
    """Measure the complete guard, including in-flight stock helper allocations."""
    import tracemalloc
    from pint import pint_eval as pe, util
    expression='m'
    for unused in range(5): expression='('+expression+'*'+expression+')'
    expression+='**+1'
    labels=(('raw512','m'+' '*511), ('utf8_512','µ'*256),
            ('tokens128',expression), ('tokens129',expression+' 1'),
            ('preprocess_expansion','%'*512), ('parentheses32','('*32+'m'+')'*32),
            ('tree_depth_reject','*'.join(['m']*64)), ('power_tree_reject','m'+'**1'*63))
    units._guard_label('m')
    results=[]
    for name,label in labels:
        counts=[0,0,0,0,0]
        builder=pe._build_eval_tree.__code__
        preprocessor=util.string_preprocessor.__code__
        tokenizer=pe.plain_tokenizer.__code__
        def observe(frame,event,arg):
            if frame.f_code is builder:
                if event=='call':
                    counts[0]+=1; counts[1]=max(counts[0],counts[1])
                elif event=='return': counts[0]-=1
            if event=='call' and frame.f_code is preprocessor: counts[2]+=1
            if event=='call' and frame.f_code is tokenizer: counts[3]+=1
        previous=sys.getprofile(); tracemalloc.start(); before=tracemalloc.get_traced_memory()[0]
        sys.setprofile(observe)
        try:
            try: units._guard_label(label)
            except Refusal as error: status=error.code
            else: status='accepted'
            current,peak=tracemalloc.get_traced_memory()
        finally:
            sys.setprofile(previous); tracemalloc.stop()
        assert peak-before <= 524288, (name,peak-before)
        assert counts[1] <=128 and counts[0]==0, (name,counts)
        results.append(dict(case=name,raw_utf8=len(label.encode('utf8')),status=status,
                            traced_peak_bytes=peak-before,remaining_bytes=current-before,
                            maximum_builder_frames=counts[1],preprocessor_calls=counts[2],
                            tokenizer_resumptions=counts[3]))
    return results


class GuardScratchTests(unittest.TestCase):
    def test_complete_guard_peak_fits_reserved_scratch(self):
        self.assertEqual(len(run_guard_probe()),8)


if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='guard':
        import json
        print(json.dumps(run_guard_probe(),indent=2))
    else:
        unittest.main()
