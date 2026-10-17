"""Owned stock pass, restoration, cancellation and normalization lifetimes."""
import gc
import os
import subprocess
import sys
import threading
import unittest
import weakref
from unittest.mock import patch

import numpy as np
from replicatetable import units
from replicatetable.model import ArrayBuffer
from replicatetable.errors import Refusal, ComputationError


def run_isolated(case):
    code = '''import gc, weakref
import numpy as np
import pint
from unittest.mock import patch
from replicatetable import units
from replicatetable.model import ArrayBuffer
from replicatetable.errors import Refusal
''' + case
    return subprocess.run([sys.executable, '-B', '-c', code], env=os.environ.copy(), capture_output=True, text=True)


class UnitContextTests(unittest.TestCase):
    def test_context_restores_exact_baseline_and_releases_operation_cache(self):
        with units._StockUnitContext() as context:
            baseline = units._stock_baseline
            registry, mapping, maps, stock, original = baseline[:5]
            before_stock = dict(stock)
            before_cache = {name: dict(getattr(original, name)) for name in units._CACHE_FIELDS}
            operation_cache = weakref.ref(context._cache)
            self.assertIs(maps[0], context._overlay)
            self.assertIs(maps[1], stock)
            self.assertIs(registry._caches[()], original)
            units.qualify_conversion('femtometer', 'meter', context=context)
        self.assertIsNone(operation_cache())
        self.assertIs(registry._units, mapping); self.assertIs(mapping.maps, maps)
        self.assertEqual(len(maps), 1); self.assertIs(maps[0], stock)
        self.assertIs(registry._cache, original)
        self.assertEqual(stock, before_stock)
        self.assertEqual(before_cache, {name: dict(getattr(original, name)) for name in units._CACHE_FIELDS})
        self.assertIsNone(context._registry); self.assertIsNone(context._overlay)

    def test_context_overlap_reentry_reuse_inactive_and_wrong_thread_refuse(self):
        context = units._StockUnitContext()
        with self.assertRaises(Refusal): context._begin_attempt()
        with context:
            self.assertEqual(units._stock_lock._recursion_count(),1)
            with self.assertRaises(Refusal): context.__enter__()
            with self.assertRaises(Refusal): units._StockUnitContext().__enter__()
            self.assertEqual(units._stock_lock._recursion_count(),1)
            errors = []
            def other():
                for call in (context._begin_attempt, lambda: context.__exit__(None,None,None)):
                    try: call()
                    except Refusal as error: errors.append(error.code)
            thread = threading.Thread(target=other); thread.start(); thread.join()
            self.assertEqual(errors, ['invalid_unit_operation']*2)
            self.assertEqual(units.qualify_conversion('s', 's', context=context).scale, 1.)
        with self.assertRaises(Refusal): context.__enter__()
        with self.assertRaises(Refusal): context.__exit__(None,None,None)

    def test_unrelated_memory_thread_does_not_block_private_unit_pass(self):
        stop = threading.Event(); started = threading.Event()
        def idle(): started.set(); stop.wait()
        thread = threading.Thread(target=idle); thread.start(); started.wait()
        try: self.assertEqual(units.qualify_conversion('s','ms').scale, 1000.)
        finally: stop.set(); thread.join()

    def test_attempt64_succeeds_65_refuses_including_failed_and_weight_attempts(self):
        with units._StockUnitContext() as context:
            for _ in range(21):
                units.qualify_conversion(None, None, context=context)
                units.qualify_weight_unit(None, context=context)
                with self.assertRaises(Refusal): units.qualify_conversion('unknown_unit_x', None, context=context)
            units.qualify_conversion('s', 's', context=context)
            self.assertEqual(context._attempts, 64)
            with patch.object(units, '_qualification_outcome', side_effect=AssertionError('attempt65 reached science')):
                with self.assertRaises(Refusal): units.qualify_weight_unit(None, context=context)

    def test_initialization_interruption_poisoned_and_never_retried(self):
        result = run_isolated('''
calls=[]
original=pint.UnitRegistry.__init__
def failing(self,*a,**k):
 calls.append(1)
 original(self,*a,**k)
 raise KeyboardInterrupt('cancel')
with patch.object(pint.UnitRegistry,'__init__',failing):
 try: units.qualify_conversion('s','s')
 except KeyboardInterrupt as error: assert error.__context__ is None
 else: raise AssertionError('cancel suppressed')
 for unused in range(2):
  try: units.qualify_conversion('s','s')
  except Refusal as error: assert error.code=='invalid_unit_operation'
  else: raise AssertionError('poison reused')
assert calls==[1]
assert not units._stock_lock._is_owned()
''')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_interrupted_first_import_poisons_private_initialization(self):
        result = run_isolated('''
import builtins
original=builtins.__import__; calls=[]
def interrupted(name,*args,**kwargs):
 if name=='pint.facets.plain.registry':
  calls.append(1)
  raise KeyboardInterrupt('initial import')
 return original(name,*args,**kwargs)
with patch.object(builtins,'__import__',interrupted):
 try: units.qualify_conversion('s','s')
 except KeyboardInterrupt: pass
 else: raise AssertionError('interruption suppressed')
 assert units._stock_attempted and units._stock_poisoned
 assert not units._stock_lock._is_owned()
 try: units.qualify_conversion('s','s')
 except Refusal as error: assert error.code=='invalid_unit_operation'
 else: raise AssertionError('initialization retried')
assert calls==[1]
''')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_restoration_failure_preserves_primary_and_poisoned_state(self):
        for expression in ("Refusal('primary_refusal')", "KeyboardInterrupt('cancel')"):
            result = run_isolated('''
primary=%s
try:
 with units._StockUnitContext() as context:
  registry=context._registry_for_attempt(); cache_ref=weakref.ref(context._cache)
  registry._units.maps.append({})
  raise primary
except BaseException as error:
 assert error is primary
 assert units._stock_poisoned and not units._stock_lock._is_owned()
 assert context._cache is None and cache_ref() is None
else: raise AssertionError('primary suppressed')
try: units.qualify_conversion('s','s')
except Refusal as error: assert error.code=='invalid_unit_operation'
else: raise AssertionError('poison reused')
''' % expression)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_dependency_failures_and_guard_frames_release_with_gc_disabled(self):
        was_enabled = gc.isenabled(); gc.disable()
        try:
            errors = []
            for source, target, code in (('m ** (','s','invalid_unit'), ('unknown_x','s','unknown_unit'),
                    ('dB/dB','dimensionless','unsupported_unit_converter'), ('m','s','incompatible_unit')):
                with units._StockUnitContext() as context:
                    cache_ref = weakref.ref(context._cache)
                    try: units.qualify_conversion(source,target,context=context)
                    except Refusal as error:
                        self.assertEqual(error.code, code); errors.append(error)
                self.assertIsNone(cache_ref())
            for error in errors:
                self.assertIsNone(error.__context__); self.assertIsNone(error.__cause__)
                frame = error.__traceback__
                while frame:
                    self.assertNotIn(frame.tb_frame.f_code.co_name, ('_qualification_outcome','_qualify_compute','_guard_label','_closed_graph','_derive'))
                    frame = frame.tb_next
        finally:
            if was_enabled: gc.enable()

    def test_owned_refusal_and_cancellation_identity_preserved_without_setter_hooks(self):
        for base in (Refusal, KeyboardInterrupt):
            hooks = []
            class Escaping(base):
                armed = False
                def __setattr__(self, name, value):
                    if self.armed: hooks.append(name); raise AssertionError('exception setter hook')
                    super().__setattr__(name,value)
            error = Escaping('private_refusal' if base is Refusal else 'cancel')
            error.armed = True; refs=[]
            with units._StockUnitContext() as context:
                registry = context._registry_for_attempt()
                def fail(*args, **kwargs):
                    owned = np.arange(100, dtype='float64'); refs.append(weakref.ref(owned))
                    raise error
                with patch.object(registry.Quantity, 'to', fail):
                    try: units.qualify_conversion('s','ms',context=context)
                    except BaseException as caught: self.assertIs(caught, error)
                    else: self.fail('failure suppressed')
            self.assertIsNone(refs[0]()); self.assertFalse(hooks)
            self.assertIsNone(error.__context__); self.assertIsNone(error.__cause__)

    def test_thin_owned_reraise_does_not_create_exception_self_cycle(self):
        class MarkerError(Exception):
            pass
        def invoke():
            pending = [MarkerError('marker')]
            reference = weakref.ref(pending[0])
            try: units._return_or_raise((False, pending.pop()))
            except MarkerError: pass
            return reference
        enabled = gc.isenabled(); gc.disable()
        try:
            self.assertIsNone(invoke()())
        finally:
            if enabled: gc.enable()

    def test_private_context_reinitialization_is_refused(self):
        context = units._StockUnitContext()
        with self.assertRaises(Refusal): context.__init__()

    def test_faulted_restoration_releases_owned_overlay_even_when_poisoned(self):
        result = run_isolated('''
context=units._StockUnitContext(); context.__enter__()
registry=context._registry_for_attempt(); original_maps=registry._units.maps
original_stock=original_maps[1]
try:
 original_maps.append({})
 context.__exit__(None,None,None)
except Refusal:
 assert context._overlay is None
 assert len(original_maps)==2 and original_maps[0] is original_stock
 assert units._stock_poisoned and not units._stock_lock._is_owned()
else: raise AssertionError('restoration corruption accepted')
''')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_one_shot_entry_and_exit_boundary_cancellation_cleans_owned_state(self):
        # Adapted from the independent review's unchanged entry/exit witnesses.
        for phase in ('entry_setup','entry_tail','entry_return','exit_gate','exit_bookkeeping',
                      'exit_owner_snapshot','exit_gate_body_refusal','exit_bookkeeping_body_refusal',
                      'exit_tail','exit_retire'):
            code = '''
import inspect,sys
phase=%r
body_primary=Refusal('primary_body') if phase.endswith('_body_refusal') else None
phase=phase.removesuffix('_body_refusal')
with units._StockUnitContext() as warm:
 units.qualify_conversion('s','s',context=warm)
registry,mapping,maps,stock,baseline=units._stock_baseline[:5]
context=units._StockUnitContext(); primary=KeyboardInterrupt('one-shot boundary')
entry=units._StockUnitContext.__enter__.__code__
exit_code=units._StockUnitContext.__exit__.__code__
retire=units._StockUnitContext._retire.__code__
entry_lines,start=inspect.getsourcelines(units._StockUnitContext.__enter__)
setup_line=next(start+i for i,line in enumerate(entry_lines) if 'self._owner = get_ident()' in line)
return_line=next(start+i for i,line in enumerate(entry_lines) if line.strip().startswith('return '))
exit_lines,exit_start=inspect.getsourcelines(units._StockUnitContext.__exit__)
gate_line=next(exit_start+i for i,line in enumerate(exit_lines) if '_require_active(' in line)
bookkeeping_line=next(exit_start+i for i,line in enumerate(exit_lines) if 'outcome = recovery = None' in line)
owner_line=next((exit_start+i for i,line in enumerate(exit_lines) if 'valid_exit = _has_active_owner(self)' in line),gate_line)
armed=False; triggers=0; body=False; references=[]
def one_shot(frame,event,arg):
 global armed,triggers
 if event=='return' and frame.f_code is units._StockUnitContext._enter_owned.__code__ and phase=='entry_tail': armed=True
 if event=='return' and frame.f_code is units._restore_stock.__code__ and phase=='exit_tail': armed=True
 trigger=(event=='line' and ((phase=='entry_setup' and frame.f_code is entry and frame.f_lineno==setup_line)
  or (phase=='entry_return' and frame.f_code is entry and frame.f_lineno==return_line)
  or (phase=='entry_tail' and armed and frame.f_code is entry)
  or (phase=='exit_gate' and frame.f_code is exit_code and frame.f_lineno==gate_line)
  or (phase=='exit_bookkeeping' and frame.f_code is exit_code and frame.f_lineno==bookkeeping_line)
  or (phase=='exit_owner_snapshot' and frame.f_code is exit_code and frame.f_lineno==owner_line)
  or (phase=='exit_tail' and armed and frame.f_code is exit_code)
  or (phase=='exit_retire' and frame.f_code is retire)))
 if trigger:
  triggers+=1; sys.settrace(None)
  if context._cache is not None: references.append(weakref.ref(context._cache))
  raise primary
 return one_shot
gc.disable();sys.settrace(one_shot)
try:
 with context:
  body=True
  if body_primary is not None: raise body_primary
except BaseException as error: assert error is (primary if body_primary is None else body_primary),(type(error),phase)
else: raise AssertionError('cancellation not observed')
finally: sys.settrace(None)
assert triggers==1 and body==phase.startswith('exit'),(phase,triggers,body)
assert context._state=='closed' and units._active_context is None
assert context._registry is None and context._cache is None and context._overlay is None
assert all(reference() is None for reference in references)
assert registry._units is mapping and mapping.maps is maps and len(maps)==1 and maps[0] is stock
assert registry._cache is baseline and not units._stock_poisoned
owned=getattr(units._stock_lock,'_is_owned',None)
assert owned is None or not owned()
assert units._stock_lock.acquire(blocking=False)
units._stock_lock.release()
assert primary.__context__ is None and primary.__cause__ is None
assert units.qualify_conversion('s','s').scale==1.
''' % phase
            with self.subTest(phase=phase):
                result=run_isolated(code)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_foreign_exit_cannot_clean_unregistered_same_thread_acquisition(self):
        result=run_isolated('''
import inspect,sys
with units._StockUnitContext() as closed:
 units.qualify_conversion('s','s',context=closed)
outer=units._StockUnitContext(); foreign=units._StockUnitContext(); visits=[]
lines,start=inspect.getsourcelines(units._StockUnitContext.__enter__)
line=next(start+i for i,text in enumerate(lines) if 'self._owner = get_ident()' in text)
def probe(frame,event,arg):
 if event=='line' and frame.f_code is units._StockUnitContext.__enter__.__code__ and frame.f_lineno==line:
  sys.settrace(None);visits.append(1)
  assert units._active_context is None and units._stock_lock._is_owned()
  for context in (foreign,closed):
   try: context.__exit__(Refusal,Refusal('not_an_authority'),None)
   except Refusal as error: assert error.code=='invalid_unit_operation'
   else: raise AssertionError('foreign exit accepted')
   assert units._active_context is None and units._stock_lock._is_owned()
   assert units._stock_lock._recursion_count()==1
 return probe
sys.settrace(probe)
try:
 with outer: assert units.qualify_conversion('ms','s',context=outer).scale==.001
finally: sys.settrace(None)
assert visits==[1] and units._active_context is None and not units._stock_lock._is_owned()
''')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_with_body_caller_exception_links_are_not_sanitized(self):
        cause = RuntimeError('caller cause'); caller = ValueError('caller')
        try:
            with units._StockUnitContext(): raise caller from cause
        except ValueError as caught:
            self.assertIs(caught, caller); self.assertIs(caught.__cause__, cause)


class UnitWeightTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(units, 'normalize_weights'), 'Bounded ArrayBuffer normalization is absent')

    def buffer(self, values, dtype='float64'):
        array = np.array(values, dtype=dtype)
        return ArrayBuffer(array.dtype.name, array.shape, array.tobytes())

    def test_finite_nonnegative_percent_weights_are_owned_immutable(self):
        for label in ('percent','%'):
            raw = self.buffer([0,25,75], 'int64'); operation = units.qualify_weight_unit(label)
            result = units.normalize_weights(raw, operation)
            np.testing.assert_array_equal(result.values, [0,.25,.75])
            self.assertEqual(result.operation, operation)
            self.assertEqual(result.buffer.dtype,'float64')
            with self.assertRaises(ValueError): result.values.setflags(write=True)
            view=result.values; view.shape=(3,1)
            self.assertEqual(result.values.shape,(3,))
            np.testing.assert_array_equal(raw.view(),[0,25,75])
        self.assertEqual(units.qualify_weight_unit(None).parsed_target, ())

    def test_all_negative_and_nonfinite_weights_refuse_even_if_unused(self):
        operation=units.qualify_weight_unit(None)
        for value, code in ((-1.,'negative_weight'),(float('nan'),'nonfinite_weight'),(float('inf'),'nonfinite_weight')):
            with self.assertRaises(Refusal) as caught: units.normalize_weights(self.buffer([value]),operation)
            self.assertEqual(caught.exception.code,code)

    def test_bare_array_and_poisoned_buffer_refuse_before_science(self):
        operation=units.qualify_weight_unit(None)
        values=[np.ones(3), object.__new__(ArrayBuffer)]
        for field, value in (('dtype',object()),('shape',(True,)),('data',bytearray(8))):
            buffer=self.buffer([1.]); object.__setattr__(buffer,field,value); values.append(buffer)
        for value in values:
            with self.subTest(kind=type(value)), patch.object(units,'qualify_weight_unit',side_effect=AssertionError('invalid source reached qualification')):
                with self.assertRaises(Refusal): units.normalize_weights(value,operation)

    def test_enclosing_boundary_compares_coherent_forged_operation(self):
        self.assertTrue(hasattr(units,'_require_same_operation'), 'Enclosing operation comparison is absent')
        raw=units.qualify_weight_unit('percent').to_dict()
        raw['source_unit']='dimensionless'
        forged=units.UnitOperation.from_dict(raw)
        actual=units.qualify_weight_unit(forged.source_unit)
        with self.assertRaises(Refusal) as caught: units._require_same_operation(forged,actual)
        self.assertEqual(caught.exception.code,'invalid_unit_operation')

    def test_enclosing_comparison_preserves_numeric_types_and_signed_zero(self):
        self.assertTrue(hasattr(units,'_require_same_operation'), 'Enclosing operation comparison is absent')
        for label, change in ((None, 'zero'), ('percent', 'exponent')):
            raw = units.qualify_weight_unit(label).to_dict()
            if change == 'zero': raw['offset'] = -0.0
            else: raw['parsed_source'][0][1] = 1.0
            operation = units.UnitOperation.from_dict(raw)
            with self.subTest(change=change):
                with self.assertRaises(Refusal) as caught:
                    units._require_same_operation(operation, units.qualify_weight_unit(label))
                self.assertEqual(caught.exception.code, 'invalid_unit_operation')

    def test_normalization_consumes_existing_operation_after_all64_attempts(self):
        with units._StockUnitContext() as context:
            for unused in range(32):
                units.qualify_conversion(None,None,context=context)
                operation=units.qualify_weight_unit(None,context=context)
            self.assertEqual(context._attempts,64)
            self.assertIs(units._require_same_operation(operation,operation),operation)
            try: result=units.normalize_weights(self.buffer([0.,1.]),operation)
            except Refusal as error: self.fail('Already-qualified consumer opened another pass: '+error.code)
            np.testing.assert_array_equal(result.values,[0.,1.])
            self.assertIs(result.operation,operation)
            self.assertEqual(context._attempts,64)

    def test_weight_normalization_overflow_releases_owned_cast_and_masks(self):
        operation=units.qualify_weight_unit('1 / percent'); refs=[]
        original=np.multiply
        def observe(*args,**kwargs):
            refs.append(weakref.ref(kwargs['out']))
            return original(*args,**kwargs)
        was_enabled=gc.isenabled(); gc.disable()
        try:
            with patch.object(np,'multiply',observe):
                try: units.normalize_weights(self.buffer([2.**1023]),operation)
                except ComputationError as error: retained=error
                else: self.fail('finite overflow accepted')
            self.assertEqual(retained.code,'numeric_overflow'); self.assertEqual(retained.exit_code,3)
            self.assertIsNone(retained.__context__); self.assertIsNone(retained.__cause__)
            self.assertTrue(refs); self.assertTrue(all(ref() is None for ref in refs))
            frame=retained.__traceback__
            while frame:
                if frame.tb_frame.f_globals.get('__name__')=='replicatetable.units':
                    self.assertFalse(any(type(value) is np.ndarray for value in frame.tb_frame.f_locals.values()))
                frame=frame.tb_next
        finally:
            if was_enabled: gc.enable()


def run_retention_probe(mode, contexts=640, attribution=False):
    """Fixed bookkeeping, matched real-context control; no heap walk/collection."""
    import json
    import resource
    import tracemalloc
    from array import array
    from pint.util import ParserHelper
    if mode not in ('production', 'control'):
        raise ValueError('unknown probe mode')
    with units._StockUnitContext() as context:
        units.qualify_conversion('s', 's', context=context)
    registry, mapping, maps, stock, original = units._stock_baseline[:5]
    stock_before = dict(stock)
    cache_fields = tuple((name, getattr(original, name), dict(getattr(original, name))) for name in units._CACHE_FIELDS)
    casei = {key: frozenset(value) for key,value in registry._units_casei.items()}
    fixed = tuple((name, getattr(registry,name), len(getattr(registry,name))) for name in units._STOCK_FIELDS)
    cases = (('ms','s',None), ('degF','degC',None), ('standard_gravity','m/s**2',None),
             ('g_0','meter/second**2',None), ('femtometer','meter',None),
             ('percent','dimensionless',None), ('m**0.5','centimeter**0.5',None),
             ('delta_degC','K',None), ('not_a_known_unit','s','unknown_unit'),
             ('dB/dB','dimensionless','unsupported_unit_converter'),
             ('degC/degC','dimensionless','unsupported_offset_unit'),
             ('m','s','incompatible_unit'), ('m ** (','s','invalid_unit'),
             ('meter ** (2 ** 3)','m**8','invalid_unit'),
             ('m/m','dimensionless',None), ('degC**1','K',None))

    def invoke(source, target, code, context):
        if mode == 'production':
            return units.qualify_conversion(source, target, context=context)
        context._begin_attempt()
        if code is not None:
            raise Refusal(code)
        return None

    def unchanged():
        assert registry._units is mapping and mapping.maps is maps
        assert len(maps)==1 and maps[0] is stock and stock==stock_before
        assert registry._cache is original
        assert registry._caches == {(): original}
        assert not registry._context_units and not registry._base_units_cache and not registry._active_ctx
        assert casei == {key:frozenset(value) for key,value in registry._units_casei.items()}
        for name, value, length in fixed:
            assert getattr(registry,name) is value and len(value)==length
        for name, value, before in cache_fields:
            assert getattr(original,name) is value and value==before

    milestones = (0, contexts//8-1, contexts//4-1, contexts//2-1, 3*contexts//4-1, contexts-1)
    observations = array('Q', [0]*24); index=0; errors=[]; late=None
    enabled = gc.isenabled(); gc.disable(); tracemalloc.start()
    try:
        for step in range(contexts):
            with units._StockUnitContext() as context:
                for attempt in range(64):
                    source, target, expected = cases[attempt % len(cases)]
                    try: result = invoke(source,target,expected,context)
                    except Refusal as error:
                        assert expected == error.code
                        if step == 0: errors.append(error)
                    else:
                        assert expected is None
                        del result
                reference = weakref.ref(context._cache)
            assert reference() is None
            unchanged()
            if step in milestones:
                observations[index] = 64*(step+1)
                current, peak = tracemalloc.get_traced_memory()
                observations[index+1]=current; observations[index+2]=peak
                observations[index+3]=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                index += 4
                del current, peak
            if attribution and step==contexts//2-1:
                late=tracemalloc.take_snapshot()
        final=tracemalloc.take_snapshot() if attribution else None
        assert all(error.__context__ is None and error.__cause__ is None for error in errors)
        result=dict(mode=mode, python=sys.version, calls=contexts*64,
                    observations=list(observations), live_operation_caches=int(reference() is not None),
                    retained_first_pass_errors=len(errors), audited_baseline_unchanged=True,
                    parser_cache=ParserHelper.from_string.cache_info()._asdict())
        if attribution:
            result['late_growth_by_site']=[str(item) for item in final.compare_to(late,'lineno')[:18]]
        return result
    finally:
        tracemalloc.stop()
        if enabled: gc.enable()


if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='retention':
        import json
        print(json.dumps(run_retention_probe(sys.argv[2], int(sys.argv[3]), len(sys.argv)>4), indent=2))
    else:
        unittest.main()
