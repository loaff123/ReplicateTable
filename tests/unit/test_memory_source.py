"""Fresh eager-source implementation regressions, not recovered test evidence.

Slice 1 protects exact structural ownership and phase ordering. Removing an
exact-type guard, accepting descriptor overlap, or retaining a superset of the
selected dimensions must make these tests fail before any scientific callback.
"""
import importlib
import unittest
from unittest.mock import patch

import replicatetable as rt
from replicatetable.codec import OwnedMap
from replicatetable.model import MetadataValue, Recipe, SourceIdentity, Coordinate, ArrayBuffer
from replicatetable.errors import Refusal
from replicatetable._resource_inputs import _owned_map, _variable_facts


class Poison:
    def __eq__(self, other): raise AssertionError('unqualified equality')
    def __lt__(self, other): raise AssertionError('unqualified ordering')
    def __len__(self): raise AssertionError('unqualified length')
    def __iter__(self): raise AssertionError('unqualified iteration')
    def __bool__(self): raise AssertionError('unqualified truth')


def descriptor(dims=('x',), shape=(2,), dtype='float64'):
    empty = MetadataValue({})._tagged
    return OwnedMap._from_checked(tuple(sorted(dict(dims=dims, shape=shape,
        dtype=dtype, unit=None, attributes=empty, encoding=empty,
        selection_status=None).items())))


def recipe(source='a', rows=('x',), weights=None):
    stages=[] if weights is None else [dict(name='mean',dims=['r'],op='weighted_mean',
        missing='skip',min_count=1,weights=weights,weight_unit=None)]
    return Recipe.from_dict(dict(version=1,row_dims=list(rows),columns=[dict(name='value',
        source=source,source_unit=None,target_unit=None,broadcast=[],stages=stages)]))


class StructuralSourceTests(unittest.TestCase):
    def source(self):
        self.assertTrue(hasattr(rt, 'SourceSnapshot'), 'SourceSnapshot API is missing')
        return importlib.import_module('replicatetable.source')

    def refusal(self, code, call, *args, **kwargs):
        with self.assertRaises(Refusal) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def snapshot(self, **changes):
        source=self.source()
        args=dict(identity=SourceIdentity('memory','a'*64,123), dimensions={'x':2},
            variables={'a':descriptor()}, coordinate_descriptors={'x':descriptor(dtype='<i8')},
            attributes=MetadataValue({}), arrays={}, coordinates={}, _handle=None)
        args.update(changes)
        return source.SourceSnapshot(**args)

    def test_public_surface_separates_eager_and_unimplemented_native(self):
        self.source()
        for name in ('SourceSnapshot','ComputationResult','RowRecord','SupportRecord',
                     'execute','load_result','write_bundle','verify_bundle',
                     'render_report','explain_row','RowExplanation','BundleReceipt','BundleVerification'):
            self.assertIn(name,rt.__all__)
        self.assertFalse(hasattr(rt,'inspect_source'))
        for name in ('write_bundle','verify_bundle','render_report','explain_row'):
            self.assertTrue(callable(getattr(rt,name)))

    def test_snapshot_is_immutable_shallow_descriptor_projection(self):
        snapshot=self.snapshot()
        projection=snapshot._projection()
        self.assertIs(projection['dimensions'],snapshot.dimensions)
        self.assertIs(projection['variables'],snapshot.variables)
        self.assertIs(projection['attributes'],snapshot.attributes._tagged)
        self.assertFalse(hasattr(snapshot,'to_dict'))
        self.assertEqual(set(projection),{'version','source','dimensions','variables','coordinate_descriptors','attributes'})
        with self.assertRaises((AttributeError,TypeError)):
            snapshot.arrays={}
        self.refusal('invalid_source',snapshot.__init__, identity=Poison(),dimensions=Poison(),
            variables=Poison(),coordinate_descriptors=Poison(),attributes=Poison(),
            arrays=Poison(),coordinates=Poison(),_handle=Poison())

    def test_snapshot_exact_children_and_disjoint_descriptors(self):
        for field in ('identity','dimensions','variables','coordinate_descriptors','attributes','arrays','coordinates'):
            self.refusal('invalid_source',self.snapshot,**{field:Poison()})
        self.refusal('invalid_source',self.snapshot,variables={'x':descriptor()})
        self.refusal('invalid_source',self.snapshot,dimensions={'x':Poison()})
        self.refusal('invalid_source',self.snapshot,variables={'a':descriptor(dtype='<f8')})
        self.refusal('invalid_source',self.snapshot,variables={'a':descriptor(shape=(1,))})

    def test_metadata_adoption_preserves_one_owned_tree(self):
        tagged=MetadataValue({'key':[1,'two',None]})._tagged
        adopt=getattr(MetadataValue,'_from_owned_tagged',None)
        self.assertTrue(callable(adopt),'in-place owned metadata adoption is missing')
        with patch.object(MetadataValue,'from_dict',side_effect=AssertionError('reconstruction')), \
             patch.object(MetadataValue,'to_python',side_effect=AssertionError('untagging')):
            result=adopt(tagged)
        self.assertIs(result._tagged,tagged)
        self.refusal('invalid_source',adopt,{'type':'null'})
        self.refusal('invalid_source',adopt,OwnedMap._from_checked((('type',Poison()),)))

    def test_typed_maps_own_keys_share_models_and_refuse_reinitialization(self):
        source=self.source()
        coord=Coordinate('<i8',[2,1],[1,0]); buffer=ArrayBuffer('float64',(2,),b'\0'*16)
        for cls,child in ((source._CoordinateMap,coord),(source._ArrayMap,buffer)):
            original={'x':child}; result=cls(original); original.clear()
            self.assertIs(result['x'],child)
            self.assertEqual(tuple(result),('x',))
            self.refusal('invalid_source',cls,{'x':Poison()})
            self.refusal('invalid_source',result.__init__,Poison())
            with self.assertRaises(TypeError): type('Subclass',(cls,),{})

    def test_selection_includes_weight_dimensions_and_exact_union(self):
        source=self.source()
        snapshot=self.snapshot(dimensions={'x':2,'r':3,'unused':1},
            variables={'a':descriptor(('x','r'),(2,3)),'w':descriptor(('r',),(3,))},
            coordinate_descriptors={})
        selected=source._select(snapshot,recipe(weights='w'))
        self.assertEqual(selected.variables,('a','w'))
        self.assertEqual(selected.dimensions,('r','x'))
        self.assertEqual(selected.row_dims,('x',))
        self.refusal('invalid_recipe',source._select,snapshot,Poison())
        self.refusal('invalid_source',source._select,snapshot,recipe(source='missing'))

    def test_exact_phase_and_held_identity_precedence(self):
        source=self.source(); base=self.snapshot(); selection=source._select(base,recipe())
        source._selection_snapshot(base,selection)
        prepared=self.snapshot(coordinates={'x':Coordinate('<i8',[1,2],[0,1])})
        source._selection_snapshot(prepared,selection)
        materialized=self.snapshot(coordinates={'x':Coordinate('<i8',[1,2],[0,1])},
            arrays={'a':ArrayBuffer('float64',(2,),b'\0'*16)})
        source._selection_snapshot(materialized,selection)
        extra=self.snapshot(dimensions={'x':2,'y':1},
            coordinate_descriptors={'x':descriptor(dtype='<i8'),'y':descriptor(('y',),(1,),'<i8')},
            coordinates={'y':Coordinate('<i8',[0],[0])})
        self.refusal('invalid_source_phase',source._selection_snapshot,extra,selection)
        self.refusal('source_fingerprint_mismatch',source._selection_snapshot,extra,selection,
            expected=SourceIdentity('memory','b'*64,123))
        self.refusal('invalid_source',source._selection_snapshot,extra,selection,expected=Poison())
        self.refusal('invalid_source',source._selection_snapshot,base,Poison())

    def test_missing_owned_backing_is_bounded_refusal(self):
        self.refusal('invalid_source',_owned_map,object.__new__(OwnedMap))

    def test_dimension_values_qualify_before_descriptor_equality(self):
        dimensions=OwnedMap._from_checked((('x',Poison()),))
        self.refusal('invalid_source',_variable_facts,'a',descriptor(),dimensions)


class StructuralReviewRegressions(unittest.TestCase):
    """Independent candidate01 review: forged exact objects are not authority."""
    source=StructuralSourceTests.source
    snapshot=StructuralSourceTests.snapshot
    refusal=StructuralSourceTests.refusal
    def forged(self,cls,**fields):
        result=object.__new__(cls)
        for name,value in fields.items(): object.__setattr__(result,name,value)
        return result

    def test_forged_typed_maps_refuse_mutable_backing_duck_children_and_hooks(self):
        source=self.source()
        class Duck:
            dtype='float64';shape=(2,);data=b'\0'*16
        class Hook:
            @property
            def dtype(self): raise AssertionError('unqualified dtype property')
        for backing in ([('a',ArrayBuffer('float64',(2,),b'\0'*16))],
                        (('a',Duck()),),(('a',Hook()),),((Poison(),Poison()),),
                        (('a',ArrayBuffer('float64',(2,),b'\0'*16)),)*2):
            self.refusal('invalid_source',self.snapshot,arrays=self.forged(source._ArrayMap,_items=backing))
        self.refusal('invalid_source',self.snapshot,arrays=object.__new__(source._ArrayMap))

    def test_partial_snapshot_and_poison_descriptor_refuse_before_access(self):
        source=self.source();base=self.snapshot()
        fields={name:getattr(base,name) for name in base.__slots__}
        del fields['attributes']
        partial=self.forged(source.SourceSnapshot,**fields)
        self.refusal('invalid_source',source._selection_snapshot,partial,source._select(base,recipe()))
        class DescriptorHook:
            def __getitem__(self,key): raise AssertionError('descriptor callback')
        fields={name:getattr(base,name) for name in base.__slots__}
        fields['variables']=OwnedMap._from_checked((('a',DescriptorHook()),))
        partial=self.forged(source.SourceSnapshot,**fields)
        self.refusal('invalid_source',source._select,partial,recipe())

    def test_recipe_version_and_nested_exactness_before_selection(self):
        source=self.source();base=self.snapshot();valid=recipe()
        for fields in (dict(row_dims=valid.row_dims,columns=valid.columns),
                       dict(version=Poison(),row_dims=valid.row_dims,columns=valid.columns),
                       dict(version=2,row_dims=valid.row_dims,columns=valid.columns)):
            self.refusal('invalid_recipe',source._select,base,self.forged(Recipe,**fields))

    def test_forged_coordinate_preserves_canonical_and_utf8_caps(self):
        source=self.source()
        labels=tuple(range(130000))
        forged=self.forged(Coordinate,dtype='<i8',values=labels,sorted_indices=labels)
        self.refusal('coordinate_bytes_limit',source._CoordinateMap,{'x':forged})

    def test_raw_object_selected_dtype_is_exact_u_max(self):
        self.refusal('invalid_source',self.snapshot,
            coordinate_descriptors={'x':descriptor(dtype='|O')},
            coordinates={'x':Coordinate('<U8',['a','b'],[0,1])})

    def test_materialized_numeric_union_has_no_distinct_name_alias_credit(self):
        buffer=ArrayBuffer('float64',(2048,2112),b'\0'*(2048*2112*8))
        self.refusal('selected_numeric_bytes_limit',self.snapshot,
            dimensions={'x':2048,'y':2112},coordinate_descriptors={},
            variables={'a':descriptor(('x','y'),(2048,2112)),
                       'b':descriptor(('x','y'),(2048,2112))},
            arrays={'a':buffer,'b':buffer})

    def test_selected_coordinate_union_has_no_distinct_name_alias_credit(self):
        labels=tuple(range(70000));coord=Coordinate('<i8',labels,labels)
        self.refusal('coordinate_bytes_limit',self.snapshot,
            dimensions={'x':70000,'y':70000},variables={},
            coordinate_descriptors={'x':descriptor(('x',),(70000,),'<i8'),
                                    'y':descriptor(('y',),(70000,),'<i8')},
            coordinates={'x':coord,'y':coord})

    def test_adopting_coordinate_does_not_copy_permutation(self):
        import tracemalloc
        source=self.source();labels=tuple(range(70000));coord=Coordinate('<i8',labels,labels)
        tracemalloc.start()
        try:
            result=source._CoordinateMap({'x':coord})
            current,peak=tracemalloc.get_traced_memory()
        finally: tracemalloc.stop()
        self.assertIs(result['x'],coord)
        self.assertLess(peak,131072,'whole permutation copy during model adoption')

    def test_complete_descriptor_cap_precedes_any_owned_descriptor_freeze(self):
        import replicatetable.model as model
        from replicatetable.codec import thaw
        metadata=MetadataValue({f'k{i:02}':'x'*4096 for i in range(64)})._tagged
        raw=thaw(descriptor());raw['attributes']=thaw(metadata)
        variables={f'v{i:02}':raw for i in range(11)}
        base=self.snapshot()
        args={name:getattr(base,name) for name in base.__slots__}
        args['variables']=variables
        with patch.object(model,'freeze',side_effect=AssertionError('descriptor allocation before admission')):
            self.refusal('metadata_bytes_limit',model.SourceSnapshot,**args)

    def test_raw_object_rejects_numeric_selected_coordinate_before_label_lengths(self):
        for coord in (Coordinate('<i8',[1,2],[0,1]),Coordinate('<f8',[1.0,2.0],[0,1])):
            self.refusal('invalid_source',self.snapshot,
                coordinate_descriptors={'x':descriptor(dtype='|O')},coordinates={'x':coord})

    def test_private_selection_rechecks_membership_and_exact_dimension_union(self):
        source=self.source();base=self.snapshot()
        for selection in (source._Selection(('missing',),('x',),()),
                          source._Selection(('a',),(),()),
                          source._Selection(('a',),('ghost','x'),()),
                          source._Selection(('a',),('x','y'),())):
            self.refusal('invalid_source',source._selection_snapshot,base,selection)
        wider=self.snapshot(dimensions={'x':2,'y':1})
        self.refusal('invalid_source',source._selection_snapshot,wider,
                     source._Selection(('a',),('x','y'),()))
class MemoryOwnerTests(unittest.TestCase):
    """The scientific owner must be fully charged before any payload use."""
    def owner_function(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('replicatetable._source_stock'),
                             'audited owner implementation is missing')
        module=importlib.import_module('replicatetable._source_stock')
        self.assertTrue(callable(getattr(module,'_array_owner',None)))
        return module._array_owner

    def refusal(self,code,call,*args,**kwargs):
        with self.assertRaises(Refusal) as caught: call(*args,**kwargs)
        self.assertEqual(caught.exception.code,code)

    def test_one_cell_view_charges_whole_eight_mib_array_and_bytes(self):
        import numpy as np
        owner=self.owner_function()
        backing=np.zeros(1024*1024,dtype='float64')
        fact=owner(backing[:1])
        self.assertEqual(fact.logical_bytes,8)
        self.assertEqual(fact.terminal_bytes,8*1024*1024)
        self.assertGreaterEqual(fact.header_bytes,1280)
        raw=b'\0'*(8*1024*1024)
        view=np.frombuffer(raw,dtype='float64',count=1)
        fact=owner(view)
        self.assertEqual(fact.terminal_bytes,len(raw)+128)
        self.assertEqual(fact.logical_bytes,8)

    def test_f_owner_readonly_and_singleton_zero_negative_strides(self):
        import numpy as np
        owner=self.owner_function()
        backing=np.zeros((4,5),order='F')
        view=backing.reshape(-1,order='A')[:1]
        view.flags.writeable=False
        self.assertEqual(owner(view).terminal_bytes,160)
        for stride in (0,-8):
            view=np.ndarray((1,),dtype='int64',buffer=b'\0'*8,strides=(stride,))
            self.assertEqual(owner(view).logical_bytes,8)
        self.refusal('unsupported_source_storage',owner,np.arange(8)[::2])

    def test_hidden_object_owner_and_nonowning_object_coordinate_refuse(self):
        import numpy as np
        owner=self.owner_function()
        backing=np.array(['x'],dtype=object)
        disguised=np.ndarray((1,),dtype='int64',buffer=backing)
        self.refusal('unsupported_source_storage',owner,disguised)
        self.refusal('unsupported_source_storage',owner,backing[:],object_coordinate=True)
        self.refusal('unsupported_source_storage',owner,backing)
        fact=owner(backing,object_coordinate=True)
        self.assertGreaterEqual(fact.terminal_bytes,backing.nbytes+132)

    def test_object_all_elements_qualify_including_unselected_sentinels(self):
        import numpy as np
        owner=self.owner_function()
        accepted=np.array(['a',None,float('nan'),float('inf'),float('-inf')],dtype=object)
        self.assertGreater(owner(accepted,object_coordinate=True).terminal_bytes,accepted.nbytes)
        for value in (b'a',1,1.0,Poison(),np.str_('a'),np.float64(float('nan'))):
            values=np.empty(1,dtype=object); values[0]=value
            self.refusal('unsupported_source_storage',owner,values,object_coordinate=True)

    def test_subclass_memmap_and_hidden_memmap_refuse_before_payload(self):
        import numpy as np
        import tempfile
        owner=self.owner_function()
        class Subclass(np.ndarray): pass
        self.refusal('unsupported_source_storage',owner,np.arange(1).view(Subclass))
        with tempfile.TemporaryFile() as file:
            file.write(b'\0'*16);file.flush()
            mapped=np.memmap(file,dtype='int64',mode='r',shape=(2,))
            try:
                self.refusal('unsupported_source_storage',owner,mapped)
                view=np.ndarray((1,),dtype='int64',buffer=mapped)
                self.refusal('unsupported_source_storage',owner,view)
            finally: mapped._mmap.close()

    def test_metadata_vectors_allow_wide_unicode_and_empty_but_reject_zero_dim(self):
        import numpy as np
        owner=self.owner_function()
        for data in (np.array(['a'],dtype='U16384'),np.array([],dtype='U0'),np.array([],dtype='int64')):
            self.assertEqual(owner(data,metadata=True).logical_bytes,data.nbytes)
        for data in (np.array(1),np.zeros((1,1)),np.array(['a'],dtype='S1'),np.array([1j]),
                     np.array([1],dtype='>i8'),np.array([object()]),np.array(['2020'],dtype='datetime64[Y]')):
            self.refusal('unsupported_source_storage',owner,data,metadata=True)




class PreflightAndOwnerReviewRegressions(unittest.TestCase):
    source=StructuralSourceTests.source
    snapshot=StructuralSourceTests.snapshot
    refusal=StructuralSourceTests.refusal

    def test_aggregate_metadata_scalar_cap_precedes_descriptor_freeze(self):
        import replicatetable.model as model
        from replicatetable.codec import thaw
        raw=thaw(descriptor())
        raw['attributes']=thaw(MetadataValue({'a':[None]*1024,'b':[None]*1024})._tagged)
        base=self.snapshot();args={name:getattr(base,name) for name in base.__slots__}
        args['variables']={f'v{i:02}':raw for i in range(33)}
        with patch.object(model,'freeze',side_effect=AssertionError('allocation before aggregate metadata admission')):
            self.refusal('metadata_bytes_limit',model.SourceSnapshot,**args)

    def test_metadata_container_cap_precedes_descriptor_freeze(self):
        import replicatetable.model as model
        from replicatetable.codec import thaw
        raw=thaw(descriptor())
        raw['attributes']={'type':'list','items':[{'type':'null'}]*1025}
        base=self.snapshot();args={name:getattr(base,name) for name in base.__slots__}
        args['variables']={'a':raw}
        with patch.object(model,'freeze',side_effect=AssertionError('allocation before metadata sequence admission')):
            self.refusal('metadata_bytes_limit',model.SourceSnapshot,**args)

    def test_invalid_phase_precedes_selected_numeric_limit(self):
        source=self.source();length=9*1024*1024
        snapshot=self.snapshot(dimensions={'x':length,'y':1},
            variables={'a':descriptor(('x',),(length,))},
            coordinate_descriptors={'y':descriptor(('y',),(1,),'<i8')},
            coordinates={'y':Coordinate('<i8',[0],[0])})
        selection=source._Selection(('a',),('x',),())
        self.refusal('invalid_source_phase',source._selection_snapshot,snapshot,selection)
        self.refusal('source_fingerprint_mismatch',source._selection_snapshot,snapshot,selection,
            expected=SourceIdentity('memory','b'*64,1))

    def test_metadata_vector_length_uses_metadata_limit_code(self):
        import numpy as np
        from replicatetable._source_stock import _array_owner
        self.refusal('metadata_bytes_limit',_array_owner,np.zeros(1025),metadata=True)

    def test_multibyte_object_label_limit_uses_label_code(self):
        import numpy as np
        from replicatetable._source_stock import _array_owner
        allowed=np.empty(1,dtype=object);allowed[0]='😀'*1024
        self.assertGreater(_array_owner(allowed,object_coordinate=True).terminal_bytes,4096)
        rejected=np.empty(1,dtype=object);rejected[0]='😀'*1025
        self.refusal('label_bytes_limit',_array_owner,rejected,object_coordinate=True)

    def test_labeled_owner_chain_metadata_seam_pins_32_depth_and_cycle(self):
        from replicatetable._source_stock import _owner_chain_next
        seen=()
        for identity in range(32): seen=_owner_chain_next(seen,identity)
        self.assertEqual(len(seen),32)
        self.refusal('unsupported_source_storage',_owner_chain_next,seen,32)
        self.refusal('unsupported_source_storage',_owner_chain_next,(1,2,3),2)
        self.refusal('unsupported_source_storage',_owner_chain_next,(Poison(),),3)

    def test_opaque_terminal_accepts_all_plain_numeric_owner_families(self):
        import numpy as np
        from replicatetable._source_stock import _array_owner
        for dtype in ('float16','longdouble','clongdouble'):
            owner=np.zeros(4,dtype=dtype)
            view=owner.view('uint8')
            self.assertEqual(_array_owner(view).terminal_bytes,owner.nbytes)
            self.refusal('unsupported_source_storage',_array_owner,owner)

    def test_owned_recipe_requalification_preserves_narrow_stage_codes(self):
        from replicatetable.codec import freeze
        source=self.source();snapshot=self.snapshot()
        for stages,code in (([dict(name='s',dims=['r'],op='mean',min_count=1)],'missing_stage_policy'),
            ([dict(name='s',dims=['r'],op='mean',min_count=1,missing='skip'),
              dict(name='t',dims=['z'],op='weighted_mean',min_count=1,missing='skip')],
             'unsupported_later_stage_weights')):
            raw=dict(version=1,row_dims=['x'],columns=[dict(name='value',source='a',
                source_unit=None,target_unit=None,broadcast=[],stages=stages)])
            self.refusal(code,Recipe.from_dict,raw)
            owned=freeze(raw);forged=object.__new__(Recipe)
            for name,value in owned.items(): object.__setattr__(forged,name,value)
            self.refusal(code,source._select,snapshot,forged)
# Separate existing-model regressions; append after the existing source tests.
# Intentionally unexecuted. Checkpoint complete source/tests before every run.

class SourceMetadataPreflightRegressionTests(unittest.TestCase):
    """Public exact-dict descriptors must fail before the first freeze."""
    refusal = StructuralSourceTests.refusal

    def arguments(self, attributes, encoding=None, count=1):
        from replicatetable.codec import thaw
        base = StructuralSourceTests.snapshot(self)
        args = {name: getattr(base, name) for name in base.__slots__}
        raw = thaw(descriptor())
        raw['attributes'] = attributes
        if encoding is not None: raw['encoding'] = encoding
        args['variables'] = {'v%02d' % index: raw for index in range(count)}
        return args

    source = StructuralSourceTests.source

    def refuse_before_freeze(self, code, args):
        import replicatetable.model as model
        with patch.object(model, 'freeze',
                          side_effect=AssertionError('descriptor frozen before metadata admission')):
            self.refusal(code, model.SourceSnapshot, **args)

    def test_global_metadata_scalar_cap_is_checked_before_first_descriptor_freeze(self):
        tag = {'type': 'map', 'items': [['v', {'type': 'list',
               'items': [{'type': 'null'}]*1024}]]}
        # 33 variables, two independent locations, 1024 nulls each: >65536.
        # Reused test objects still count every occurrence, with no alias credit.
        self.refuse_before_freeze('metadata_bytes_limit', self.arguments(tag, tag, count=33))

    def test_single_metadata_sequence_limit_is_checked_before_first_freeze(self):
        tag = {'type': 'map', 'items': [['v', {'type': 'list',
               'items': [{'type': 'null'}]*1025}]]}
        self.refuse_before_freeze('metadata_bytes_limit', self.arguments(tag))

    def test_metadata_depth_limit_is_checked_before_first_freeze(self):
        tag = {'type': 'null'}
        for _ in range(8): tag = {'type': 'list', 'items': [tag]}
        tag = {'type': 'map', 'items': [['v', tag]]}
        self.refuse_before_freeze('metadata_bytes_limit', self.arguments(tag))

    def test_invalid_tag_shape_is_checked_before_first_freeze(self):
        tag = {'type': 'map', 'items': [['v', {'type': 'list', 'items': {}}]]}
        self.refuse_before_freeze('invalid_source', self.arguments(tag))
# Append-only proposed fragment for tests/unit/test_memory_source.py.
# Intentionally unexecuted: parent must checkpoint all source/tests before runs.
# Imports below are stdlib; candidate imports occur only after explicit API asserts.

class FiniteMemoryMetadataTests(unittest.TestCase):
    """Private metadata boundary reds; real Dataset orchestration comes later."""

    refusal = StructuralSourceTests.refusal

    def bridge(self):
        import importlib.util
        name = 'replicatetable._source_metadata'
        self.assertIsNotNone(importlib.util.find_spec(name),
                             'finite source metadata bridge is missing')
        module = importlib.import_module(name)
        for attr in ('_MetadataState', '_scan_metadata', '_finish_metadata',
                     '_build_metadata', '_declaration_status'):
            self.assertTrue(callable(getattr(module, attr, None)),
                            'finite metadata API is missing: ' + attr)
        return module

    def state(self, base_bytes=0):
        return self.bridge()._MetadataState(base_bytes=base_bytes)

    def finish(self, state):
        from replicatetable._resource_bounds import _JP
        # Private arithmetic fixture only, not a fabricated Inspection/source.
        self.bridge()._finish_metadata(state, descriptor_cost=
            _JP(state.json_bytes, state.object_bytes))

    def metadata(self, raw, context='root'):
        module = self.bridge(); state = module._MetadataState(base_bytes=0)
        module._scan_metadata(state, raw, context=context)
        self.finish(state)
        return module._build_metadata(state, raw, context=context)

    def no_tags(self):
        from contextlib import ExitStack
        stack = ExitStack()
        for target, name in ((OwnedMap, '_from_checked'),
                             (MetadataValue, '_from_owned_tagged'),
                             (MetadataValue, '__init__')):
            stack.enter_context(patch.object(target, name,
                side_effect=AssertionError('tag/model allocation during raw prepass')))
        return stack

    @staticmethod
    def member(model, key):
        return dict(model._tagged['items'])[key]

    def test_api_is_explicit_and_private(self):
        self.bridge()
        for name in ('_MetadataState', '_scan_metadata', '_finish_metadata',
                     '_build_metadata', '_declaration_status'):
            self.assertFalse(hasattr(rt, name), 'private metadata helper was exported')

    def test_global_prepass_seals_before_first_build(self):
        module = self.bridge(); state = self.state()
        first = {'early': ['ok', 1]}; later = {'late': 'also ok'}
        with self.no_tags():
            module._scan_metadata(state, first, context='root')
            self.refusal('invalid_source', module._build_metadata, state, first)
            module._scan_metadata(state, later, context='data_attrs')
            self.finish(state)
        self.assertTrue(state.sealed)
        self.assertEqual(module._build_metadata(state, first).to_python(), first)
        self.refusal('invalid_source', module._scan_metadata, state, {})
        self.refusal('invalid_source', self.finish, state)

    def test_late_bad_raw_value_is_before_any_tag_and_never_seals(self):
        import numpy as np
        module = self.bridge()
        bad_unicode = np.array([0x110000], dtype='<u4').view('<U1')
        cases = (({'late': Poison()}, 'unsupported_source_storage'),
                 ({'late': '\ud800'}, 'invalid_source'),
                 ({'late': bad_unicode}, 'invalid_source'),
                 ({'late': 'é' * 2049}, 'invalid_source'))
        for later, code in cases:
            with self.subTest(code=code, raw_type=type(later['late'])):
                state = self.state()
                with self.no_tags():
                    module._scan_metadata(state, {'early': np.str_('ready')})
                    self.refusal(code, module._scan_metadata, state, later,
                                 context='data_encoding')
                self.assertFalse(state.sealed)
                self.refusal('invalid_source', module._build_metadata,
                             state, {'early': 'ready'})

    def test_state_has_no_retained_inputs_or_tree(self):
        import numpy as np
        import weakref
        module = self.bridge(); state = self.state()
        vector = np.arange(3, dtype='int64'); reference = weakref.ref(vector)
        raw = {'v': vector}
        with self.no_tags(): module._scan_metadata(state, raw)
        del raw, vector
        self.assertIsNone(reference(), 'metadata state retained a source owner')
        self.assertFalse(hasattr(state, '__dict__'))
        for cls in type(state).__mro__:
            for slot in getattr(cls, '__slots__', ()):
                if slot != '__weakref__':
                    self.assertIn(type(getattr(state, slot)), (int, bool, type(None)), slot)

    def test_none_and_empty_slots_equal_tags_but_actual_capacity_is_charged(self):
        module = self.bridge()
        roomy = {i: i for i in range(256)}
        for key in tuple(roomy): del roomy[key]
        states = [self.state() for _ in range(3)]
        values = (None, {}, roomy)
        for state, raw in zip(states, values):
            module._scan_metadata(state, raw); self.finish(state)
        tags = [module._build_metadata(state, raw)._tagged
                for state, raw in zip(states, values)]
        self.assertEqual(tags[0], tags[1]); self.assertEqual(tags[1], tags[2])
        self.assertEqual((states[0].json_bytes, states[0].object_bytes),
                         (states[1].json_bytes, states[1].object_bytes))
        self.assertEqual(states[1].raw_bytes, max(512, dict.__sizeof__(values[1]) + 16))
        self.assertEqual(states[2].raw_bytes, max(512, dict.__sizeof__(roomy) + 16))
        self.assertGreater(states[2].raw_bytes, states[1].raw_bytes)
        explicit = self.metadata({'_FillValue': None})
        self.assertEqual(self.member(explicit, '_FillValue')['type'], 'null')

    def test_raw_np_string_reserve_replaces_generic_scalar_and_nuls_survive(self):
        import numpy as np
        module = self.bridge(); value = np.str_('é\0z\0'); raw = {'s': value}
        state = self.state(); module._scan_metadata(state, raw)
        length = str.__len__(value)
        reserve = max(512, str.__sizeof__(value) + object.__sizeof__(value) + 16) + 128 + 4*(length+1)
        expected = max(640, dict.__sizeof__(raw)+16) + 132 + reserve
        self.assertEqual(state.raw_bytes, expected)
        self.finish(state); result = module._build_metadata(state, raw)
        normalized = self.member(result, 's')['value']
        self.assertIs(type(normalized), str); self.assertEqual(normalized, 'é\0z\0')

    def test_numpy_scalar_classes_preserve_exact_types_integer_endpoints_and_signed_zero(self):
        import math
        import numpy as np
        values = {'b': np.bool_(True), 'i64': np.int64(-(2**63)),
                  'u64': np.uint64(2**64-1), 'f32': np.float32(0.1),
                  'negative_zero': np.float64(-0.0), 's': np.str_('plain')}
        for cls in (np.int8, np.int16, np.int32, np.uint8, np.uint16, np.uint32):
            values[cls.__name__] = cls(7)
        result = self.metadata(values)
        expected = {'b': ('bool', True), 'i64': ('int', -(2**63)),
                    'u64': ('int', 2**64-1), 'f32': ('float', float(np.float32(0.1))),
                    'negative_zero': ('float', -0.0), 's': ('str', 'plain')}
        for cls in (np.int8, np.int16, np.int32, np.uint8, np.uint16, np.uint32):
            expected[cls.__name__] = ('int', 7)
        for key, (tag, value) in expected.items():
            actual = self.member(result, key)
            self.assertEqual(actual['type'], tag)
            self.assertIs(type(actual['value']), type(value))
            self.assertEqual(actual['value'], value)
        self.assertEqual(math.copysign(1, self.member(result, 'negative_zero')['value']), -1)

    def test_special_float_tags_do_not_collide_with_strings_or_maps(self):
        import numpy as np
        raw = {'nan': np.float32(float('nan')), 'pos': np.float64(float('inf')),
               'neg': float('-inf'), 'text': 'nan',
               'collision': {'type': 'float_special', 'value': 'nan'}}
        result = self.metadata(raw)
        for key, marker in (('nan', 'nan'), ('pos', '+inf'), ('neg', '-inf')):
            self.assertEqual(dict(self.member(result, key).items()),
                             {'type': 'float_special', 'value': marker})
        self.assertEqual(self.member(result, 'text')['type'], 'str')
        self.assertEqual(self.member(result, 'collision')['type'], 'map')

    def test_unadopted_classes_and_bad_keys_refuse_without_hooks(self):
        import numpy as np
        class StrSubclass(str):
            def __str__(self): raise AssertionError('string callback')
            def __len__(self): raise AssertionError('length callback')
        class ArraySubclass(np.ndarray):
            def __getitem__(self, key): raise AssertionError('array callback')
        class DictSubclass(dict):
            def items(self): raise AssertionError('mapping callback')
        rejected = (b'a', 1j, np.bytes_('a'), np.longdouble(1), np.complex64(1),
                    np.float16(1), np.datetime64('2020'), np.timedelta64(1, 'D'), StrSubclass('x'),
                    DictSubclass(a=1), np.arange(1).view(ArraySubclass), Poison())
        module = self.bridge()
        for value in rejected:
            with self.subTest(raw_type=type(value)), self.no_tags():
                self.refusal('unsupported_source_storage', module._scan_metadata,
                             self.state(), {'v': value})
        for key in (1, np.str_('key'), StrSubclass('key')):
            with self.no_tags():
                self.refusal('invalid_source', module._scan_metadata, self.state(), {key: None})
        for value in (-(2**63)-1, 2**64):
            self.refusal('invalid_source', module._scan_metadata, self.state(), {'v': value})

    def test_vectors_keep_list_tags_and_full_owner_capacity_per_occurrence(self):
        import numpy as np
        from replicatetable._source_stock import _array_owner
        module = self.bridge(); backing = np.zeros(1024*1024, dtype='float64')
        vector = backing[:1]; vector.flags.writeable = False
        owner = _array_owner(vector, metadata=True)
        state = self.state(); module._scan_metadata(state, {'v': vector})
        first = state.raw_bytes
        self.assertGreaterEqual(first, owner.terminal_bytes + owner.header_bytes)
        module._scan_metadata(state, {'v': vector}, context='data_encoding')
        self.assertEqual(state.raw_bytes, 2*first, 'shared owners received alias credit')
        self.finish(state)
        self.assertEqual(self.member(module._build_metadata(state, {'v': vector}), 'v')['type'], 'list')
        for raw in ([float('nan')], (float('nan'),), np.array([float('nan')])):
            tag = self.member(self.metadata({'v': raw}), 'v')
            self.assertEqual(tag['type'], 'list')
            self.assertEqual(tag['items'][0]['type'], 'float_special')
        bools = self.member(self.metadata({'v': np.array([True, False])}), 'v')
        self.assertEqual([child['type'] for child in bools['items']], ['bool', 'bool'])

    def test_vector_shape_dtype_and_size_gate_precedes_element_conversion(self):
        import numpy as np
        module = self.bridge()
        bad = (np.array(1), np.zeros((1, 1)), np.arange(4)[::2],
               np.array([1], dtype='>i8'), np.array([b'x'], dtype='S1'),
               np.array([object()]), np.array([1j]), np.array(['2020'], dtype='datetime64[Y]'),
               np.array([(1,)], dtype=[('x', 'i8')]),
               np.array([1], dtype=np.dtype('i8', metadata={'x': 1})))
        for value in bad:
            with self.subTest(dtype=value.dtype, shape=value.shape), self.no_tags():
                self.refusal('unsupported_source_storage', module._scan_metadata,
                             self.state(), {'v': value})

        with self.no_tags():
            self.refusal('metadata_bytes_limit', module._scan_metadata,
                         self.state(), {'v': np.arange(1025)})

    def test_raw_owner_and_retained_subtotal_hit_source_cap_before_normalization(self):
        import numpy as np
        from replicatetable import resources as r
        from replicatetable._source_stock import _array_owner
        module = self.bridge(); backing = np.zeros(1024*1024, dtype='float64')
        vector = backing[:1]; owner = _array_owner(vector, metadata=True)
        subtotal = r.SOURCE_MEMORY_BASE_LIMIT - owner.terminal_bytes - owner.header_bytes + 1
        with self.no_tags():
            self.refusal('source_bytes_limit', module._scan_metadata,
                         self.state(subtotal), {'v': vector})
        # A late oversized string cannot replace the earlier source-cap refusal.
        with self.no_tags():
            self.refusal('source_bytes_limit', module._scan_metadata,
                         self.state(r.SOURCE_MEMORY_BASE_LIMIT-1), {'v': np.str_('ok'), 'z': 'x'*4097})

    def test_wide_unicode_uses_actual_contents_and_no_padded_scalar_scratch(self):
        import numpy as np
        import tracemalloc
        module = self.bridge()
        for width in (4097, 16384, 262144):
            raw = {'v': np.array(['a\0b', 'é'], dtype='U' + str(width))}
            state = self.state()
            tracemalloc.start()
            try:
                with self.no_tags(): module._scan_metadata(state, raw)
                _, peak = tracemalloc.get_traced_memory()
            finally: tracemalloc.stop()
            self.assertLess(peak, 262144, 'padding-sized scalar/normalized vector during pass1')
            self.finish(state)
            tracemalloc.start()
            try:
                result = module._build_metadata(state, raw)
                _, peak = tracemalloc.get_traced_memory()
            finally: tracemalloc.stop()
            self.assertLess(peak, 262144, 'padding-sized scalar/character forest during pass2')
            self.assertEqual(result.to_python(), {'v': ['a\0b', 'é']})

    def test_empty_and_nonempty_u0_never_request_byte_views(self):
        import numpy as np
        module = self.bridge()
        raw_values = (np.ndarray((0,), dtype='U16384'), np.ndarray((3,), dtype='U0'),
                      np.ndarray((0,), dtype='int64'))
        self.assertEqual(raw_values[1].dtype.itemsize, 0, 'fixture must really be nonempty U0')
        for vector in raw_values:
            state = self.state(); raw = {'v': vector}
            with patch('builtins.memoryview', side_effect=AssertionError('empty/U0 buffer view')):
                module._scan_metadata(state, raw); self.finish(state)
                result = module._build_metadata(state, raw)
            self.assertEqual(result.to_python(), {'v': ['']*len(vector)})

    def test_unicode_codeunit_validation_utf8_limits_and_trailing_padding(self):
        import numpy as np
        module = self.bridge()
        valid = np.array([ord('a'), 0, ord('b'), 0, 0], dtype='<u4').view('<U5')
        self.assertEqual(self.metadata({'v': valid}).to_python(), {'v': ['a\0b']})
        for codepoint in (0xD800, 0xDFFF, 0x110000, 0xFFFFFFFF):
            raw = {'v': np.array([codepoint], dtype='<u4').view('<U1')}
            with self.no_tags(), patch('builtins.chr', side_effect=AssertionError('invalid UTF32 normalized')):
                self.refusal('invalid_source', module._scan_metadata, self.state(), raw)
        for text in ('x'*4096, 'é'*2048, '\U0001f600'*1024):
            for value in (text, np.str_(text), np.array([text], dtype='U16384')):
                state = self.state()
                with self.no_tags(): module._scan_metadata(state, {'v': value})
        for text in ('x'*4097, 'é'*2049, '\U0001f600'*1025, '\udfff'):
            for value in (text, np.str_(text), np.array([text], dtype='U16384')):
                with self.no_tags():
                    self.refusal('invalid_source', module._scan_metadata, self.state(), {'v': value})

    def test_contextual_units_calendar_and_root_independence(self):
        import numpy as np
        module = self.bridge()
        for context in ('data_attrs', 'data_encoding', 'coordinate_attrs', 'coordinate_encoding'):
            self.metadata({'units': np.str_('m'*512)}, context)
            for value in (np.str_('m'*513), '', 1, ['m'], 'm\0', '\ud800'):
                with self.no_tags():
                    self.refusal('invalid_source', module._scan_metadata, self.state(),
                                 {'units': value}, context=context)
        self.metadata({'units': 'days\tsince\t2000-01-01'}, 'coordinate_attrs')
        self.refusal('invalid_source', module._scan_metadata, self.state(),
                     {'units': 'days\tsince\t2000-01-01'}, context='data_attrs')
        self.metadata({'calendar': np.str_('x'*512)}, 'coordinate_encoding')
        self.refusal('invalid_source', module._scan_metadata, self.state(),
                     {'calendar': np.str_('x'*513)}, context='coordinate_encoding')
        self.metadata({'units': 1, 'calendar': 'x'*4096}, 'root')
        self.metadata({'nested': {'units': 1, 'calendar': 'x'*4096}}, 'coordinate_attrs')

    def test_global_scalar_and_container_limits_survive_slot_boundaries(self):
        from replicatetable import resources as r
        module = self.bridge(); scalars = self.state(); containers = self.state()
        with self.no_tags():
            for _ in range(64): module._scan_metadata(scalars, {'v': [0]*1023})
            self.assertEqual(scalars.scalar_count, r.METADATA_SCALAR_LIMIT)
            self.refusal('metadata_bytes_limit', module._scan_metadata, scalars, {'x': None})
            for _ in range(8): module._scan_metadata(containers, {'v': [[] for _ in range(1022)]})
            self.assertEqual(containers.container_count, r.METADATA_CONTAINER_LIMIT)
            self.refusal('metadata_bytes_limit', module._scan_metadata, containers, {})

    def test_depth_collection_and_global_json_caps_precede_tag_build(self):
        module = self.bridge(); valid = 0
        for _ in range(7): valid = [valid]
        with self.no_tags():
            module._scan_metadata(self.state(), {'v': valid})
            self.refusal('metadata_bytes_limit', module._scan_metadata, self.state(), {'v': [valid]})
            module._scan_metadata(self.state(), {str(i): None for i in range(64)})
            self.refusal('metadata_bytes_limit', module._scan_metadata, self.state(),
                         {str(i): None for i in range(65)})
            self.refusal('metadata_bytes_limit', module._scan_metadata, self.state(), {'v': [0]*1025})
            state = self.state(); raw = {'v': ['x'*4096]*256}
            module._scan_metadata(state, raw); module._scan_metadata(state, raw, context='data_attrs')
            self.refusal('metadata_bytes_limit', module._scan_metadata, state, raw, context='data_encoding')

    def test_tag_jp_matches_final_tree_and_finish_charges_full_descriptor(self):
        from replicatetable.codec import primitive_bounds
        from replicatetable._resource_bounds import _JP
        from replicatetable import resources as r
        module = self.bridge(); raw = {'nested': [1, None, {'é': True}], 's': 'é\0'}
        state = self.state(); measured = module._scan_metadata(state, raw)
        self.finish(state); result = module._build_metadata(state, raw)
        actual = primitive_bounds(result._tagged)
        self.assertEqual((measured.json_bytes, measured.object_bytes),
                         (actual.json_bytes, actual.object_bytes))
        self.assertEqual((state.json_bytes, state.object_bytes),
                         (actual.json_bytes, actual.object_bytes))
        # Labeled scalar projection seams: never evidence of source inspection.
        state = self.state(); module._scan_metadata(state, {})
        self.refusal('invalid_source', module._finish_metadata, state,
                     descriptor_cost=_JP(0, 0))
        state = self.state(); module._scan_metadata(state, {})
        self.refusal('metadata_bytes_limit', module._finish_metadata, state,
                     descriptor_cost=_JP(r.METADATA_BYTES_LIMIT, state.object_bytes))
        state = self.state(); module._scan_metadata(state, {})
        self.refusal('source_bytes_limit', module._finish_metadata, state,
                     descriptor_cost=_JP(state.json_bytes, r.SOURCE_MEMORY_BASE_LIMIT))

    def test_mutated_raw_entries_are_revalidated_before_pass2_normalization(self):
        import numpy as np
        module = self.bridge()
        bad_utf32 = np.array([0x110000], dtype='<u4').view('<U1')
        for value, code in ((Poison(), 'unsupported_source_storage'),
                            (np.array(1), 'unsupported_source_storage'),
                            (bad_utf32, 'invalid_source'), ('x'*4097, 'invalid_source'),
                            ([0]*1025, 'metadata_bytes_limit')):
            raw = {'early': np.str_('ready'), 'late': None}; state = self.state()
            module._scan_metadata(state, raw); self.finish(state)
            raw['late'] = value
            with self.no_tags():
                self.refusal(code, module._build_metadata, state, raw)

    def test_source_cap_equality_and_one_byte_excess_are_incremental(self):
        import numpy as np
        from replicatetable import resources as r
        module = self.bridge(); raw = {'s': np.str_('é')}
        measured = self.state(); module._scan_metadata(measured, raw)
        baseline = r.SOURCE_MEMORY_BASE_LIMIT - measured.raw_bytes - measured.object_bytes
        # Scalar-only descriptor projection fixture, no source-authority claim.
        state = self.state(baseline)
        with self.no_tags():
            module._scan_metadata(state, raw); self.finish(state)
            self.refusal('source_bytes_limit', module._scan_metadata,
                         self.state(baseline+1), raw)

    def test_builder_adopts_one_owned_tree_without_python_or_mutable_tag_roundtrip(self):
        import numpy as np
        import replicatetable.model as model
        module = self.bridge(); raw = {'v': np.array(['a', 'é'], dtype='U16384')}
        state = self.state(); module._scan_metadata(state, raw); self.finish(state)
        with patch.object(MetadataValue, '__init__', side_effect=AssertionError('model reconstruction')), \
             patch.object(MetadataValue, 'from_dict', side_effect=AssertionError('tag reconstruction')), \
             patch.object(MetadataValue, 'to_python', side_effect=AssertionError('untagging')), \
             patch.object(model, 'freeze', side_effect=AssertionError('mutable mirror freezing')):
            result = module._build_metadata(state, raw)
        self.assertIs(type(result), MetadataValue); self.assertIs(type(result._tagged), OwnedMap)
        self.assertEqual(result.to_python(), {'v': ['a', 'é']})

    def status(self, attrs=None, encoding=None, dtype='<f8', coordinate=False):
        module = self.bridge()
        return module._declaration_status(self.metadata(attrs)._tagged,
            self.metadata(encoding)._tagged, dtype=dtype, coordinate=coordinate)

    def test_nan_only_declarations_preserve_scalar_vs_container_and_conflicts(self):
        import numpy as np
        for value in (float('nan'), np.float32(float('nan')), np.float64(float('nan'))):
            for dtype in ('<f4', '<f8'):
                self.assertIsNone(self.status({'_FillValue': value}, {'missing_value': value}, dtype))
            for dtype in ('<i8', '<u8', '<U8', '|S8', '|O'):
                status = self.status({'_FillValue': value}, dtype=dtype, coordinate=True)
                self.assertEqual(status['reasons'], ('fill_value_metadata',))
        rejected = (0, 0.0, float('inf'), float('-inf'), False, None, 'nan', [], {},
                    [float('nan')], (float('nan'),), np.array([float('nan')]))
        for value in rejected:
            for attrs, encoding in (({'_FillValue': value}, None),
                                    (None, {'_FillValue': value}),
                                    ({'_FillValue': float('nan')}, {'_FillValue': value})):
                status = self.status(attrs, encoding)
                self.assertEqual(status['reasons'], ('fill_value_metadata',))
                self.assertEqual(status['code'], 'unsupported_source_encoding')
        self.assertIsNone(self.status({'_fillvalue': 0, 'Scale_factor': 1, 'calendar': None}))

    def test_declaration_reason_order_role_scope_and_exact_inputs(self):
        attrs = {'calendar': None, 'units': 'days\tsince\t2000-01-01', 'scale_factor': 1,
                 'add_offset': 0, '_Unsigned': False, '_FillValue': None, 'missing_value': 'nan'}
        reasons = ('calendar_metadata', 'reference_time_units', 'scale_factor_metadata',
                   'add_offset_metadata', 'unsigned_metadata', 'fill_value_metadata', 'missing_value_metadata')
        status = self.status(attrs, attrs, coordinate=True)
        self.assertEqual(status['reasons'], reasons)
        self.assertEqual(status['code'], 'unsupported_coordinate_encoding')
        self.assertEqual(status['status'], 'unsupported')
        data_attrs = dict(attrs); data_attrs['units'] = 'm'
        self.assertEqual(self.status(data_attrs, data_attrs)['reasons'], reasons[2:])
        module = self.bridge(); empty = self.metadata(None)._tagged
        for kwargs in ({'dtype': Poison(), 'coordinate': False},
                       {'dtype': '<f8', 'coordinate': Poison()}):
            self.refusal('invalid_source', module._declaration_status, empty, empty, **kwargs)
        self.refusal('invalid_source', module._declaration_status,
                     {'type': 'map', 'items': []}, empty, dtype='<f8', coordinate=False)
        bad = OwnedMap._from_checked((('items', ()), ('type', Poison())))
        self.refusal('invalid_source', module._declaration_status,
                     bad, empty, dtype='<f8', coordinate=False)
"""UNEXECUTED proposed source-stock unittest fragment, 2026-10-07.

This file has not been imported, compiled, or run. Back up the COMPLETE candidate
source and tests before every candidate run. This fragment deliberately excludes
metadata normalization, semantic identity, runtime, and public source integration.

Desired seams: _stock_prepass(ds) -> final slot-backed record with exactly
(stock_headers, cache_bytes, owners); _stock_cursor(ds, name) -> final slot-backed
record with exactly (data, dims, shape, dtype, attrs, encoding).

Each test states the production regression it is intended to catch. Dependency
fixture setup may populate state; the candidate measurement phase must not.
"""
import importlib
import struct
import unittest
import weakref
from contextlib import ExitStack
from unittest.mock import patch

import numpy as np
import pandas as pd
import xarray as xr
from xarray.core.variable import Variable, IndexVariable
from xarray.namedarray.core import NamedArray
from xarray.core.indexing import PandasIndexingAdapter
from xarray.core.indexes import PandasIndex
from pandas._libs import index as libindex, hashtable as ht
from pandas._libs.internals import BlockValuesRefs

from replicatetable.codec import OwnedMap
from replicatetable.errors import Refusal
from replicatetable import resources as r


class StockPoison:
    def __getattribute__(self, name): raise AssertionError('unqualified attribute')
    def __iter__(self): raise AssertionError('unqualified iteration')
    def __len__(self): raise AssertionError('unqualified length')
    def __bool__(self): raise AssertionError('unqualified truth')
    def __eq__(self, other): raise AssertionError('unqualified equality')
    def __str__(self): raise AssertionError('unqualified string conversion')
    def __sizeof__(self): raise AssertionError('unqualified sizing')


def member(cls, name, value):
    return cls.__dict__[name].__get__(value, type(value))


def set_member(cls, name, value, replacement):
    cls.__dict__[name].__set__(value, replacement)


def own_dict(value):
    return object.__getattribute__(value, '__dict__')


def h_container(value):
    cls = type(value)
    assert cls in (dict, list, tuple, set)
    return max(512 + 128 * len(value), cls.__sizeof__(value) + 16)


def p_string(value):
    assert type(value) is str
    return 128 + 4 * len(value.encode('utf-8'))


def array_charge(value):
    """Independent test oracle for benign fixture arrays, never source authority."""
    total = 0
    current = value
    seen = set()
    while type(current) is np.ndarray:
        assert id(current) not in seen and len(seen) < 32
        seen.add(id(current))
        total += max(512 + 128 * current.ndim,
                     np.ndarray.__sizeof__(current) -
                     (current.nbytes if current.flags.owndata else 0))
        if current.base is None:
            assert current.flags.owndata
            return total + current.nbytes
        current = current.base
    assert type(current) is bytes
    return total + len(current) + 128


def index_parts(ds, name='x'):
    var = member(xr.Dataset, '_variables', ds)[name]
    adapter = member(Variable, '_data', var)
    idx = member(PandasIndexingAdapter, 'array', adapter)
    wrapper = member(xr.Dataset, '_indexes', ds)[name]
    return var, adapter, idx, wrapper


def dataset_state(ds):
    """Identity/capacity snapshot of already-present, benign fixture state."""
    root = []
    for key in ('_attrs', '_close', '_coord_names', '_dims', '_encoding', '_indexes', '_variables'):
        value = member(xr.Dataset, key, ds)
        capacity = type(value).__sizeof__(value) if type(value) in (dict, list, set, tuple) else None
        root.append((key, id(value), capacity))
    try:
        cache = member(xr.Dataset, '_cache', ds)
    except AttributeError:
        root.append(('_cache_absent',))
    else:
        root.append(('_cache', id(cache), len(cache), dict.__sizeof__(cache),
                     tuple((key, id(value)) for key, value in cache.items())))
    rows = []
    for name, var in member(xr.Dataset, '_variables', ds).items():
        data = member(Variable, '_data', var)
        row = [name, id(var), id(data)]
        if type(data) is PandasIndexingAdapter:
            idx = member(PandasIndexingAdapter, 'array', data)
            state = own_dict(idx)
            cache = state['_cache']
            row.extend((id(idx), tuple((key, id(value)) for key, value in state.items()),
                        dict.__sizeof__(state), id(cache), dict.__sizeof__(cache),
                        tuple((key, id(value)) for key, value in cache.items())))
            refs = state['_references']
            if type(refs) is BlockValuesRefs:
                values = member(BlockValuesRefs, 'referenced_blocks', refs)
                row.append((id(values), list.__sizeof__(values), tuple(id(v) for v in values),
                            member(BlockValuesRefs, 'clear_counter', refs)))
            if '_engine' in cache:
                engine = cache['_engine']
                row.append((id(member(libindex.IndexEngine, 'values', engine)),
                            id(member(libindex.IndexEngine, 'mask', engine)),
                            id(member(libindex.IndexEngine, 'mapping', engine))))
        rows.append(tuple(row))
    return tuple(root), tuple(rows)


class StockPrepassTests(unittest.TestCase):
    def stock(self):
        module = importlib.import_module('replicatetable._source_stock')
        self.assertTrue(callable(getattr(module, '_stock_prepass', None)),
                        'finite stock prepass is missing')
        self.assertTrue(callable(getattr(module, '_stock_cursor', None)),
                        'single borrowed stock cursor is missing')
        return module

    def scan(self, ds): return self.stock()._stock_prepass(ds)
    def cursor(self, ds, name): return self.stock()._stock_cursor(ds, name)

    def refusal(self, code, call, *args, **kwargs):
        with self.assertRaises(Refusal) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def direct(self, coordinate=None):
        if coordinate is None: coordinate = np.array([2, 1, 3], dtype='int32')
        ds=xr.Dataset({'a': (('x',), np.arange(len(coordinate), dtype='float64'))},
            coords=xr.Coordinates({'x': (('x',), coordinate)}, indexes={}))
        # Fixture setup: xarray otherwise erases immediate object ownership.
        set_member(Variable,'_data',member(xr.Dataset,'_variables',ds)['x'],coordinate)
        return ds

    def indexed(self, values=None):
        if values is None: values = np.array(['alpha', 'beta', 'gamma'], dtype='U13')
        ds=xr.Dataset({'a': (('x',), np.arange(len(values), dtype='float64'))},
                      coords={'x': values})
        if type(values) is np.ndarray and values.dtype.kind=='O':
            # Fixture setup, never production coercion: require actual owned backing.
            _,_,index,_=index_parts(ds)
            own_dict(index)['_data']=values
        return ds

    def owner(self, facts, kind, name):
        matches = tuple(value for value in facts.owners
                        if value['kind'] == kind and value['name'] == name)
        self.assertEqual(len(matches), 1)
        return matches[0]

    def assert_no_payload_prepass(self, ds, code='unsupported_source_storage'):
        module = self.stock()
        # The proposed phase design completes ALL topology before owner walking.
        with patch.object(module, '_array_owner', side_effect=AssertionError('owner before topology')):
            self.refusal(code, module._stock_prepass, ds)

    def test_result_is_one_sorted_primitive_owner_tuple_and_two_scalars(self):
        # Regression: retain a descriptor forest or raw source/index/array in facts.
        ds = self.direct()
        facts = self.scan(ds)
        self.assertEqual(set(type(facts).__slots__), {'stock_headers', 'cache_bytes', 'owners'})
        self.assertIs(type(facts.stock_headers), int)
        self.assertIs(type(facts.cache_bytes), int)
        self.assertGreater(facts.stock_headers, 0)
        self.assertIs(type(facts.owners), tuple)
        self.assertEqual(tuple((v['kind'], v['name']) for v in facts.owners),
                         (('coordinate', 'x'), ('variable', 'a')))
        for owner in facts.owners:
            self.assertIs(type(owner), OwnedMap)
            self.assertEqual(set(owner), {'kind', 'name', 'terminal_bytes', 'header_bytes', 'logical_bytes'})
            for key in ('terminal_bytes', 'header_bytes', 'logical_bytes'):
                self.assertIs(type(owner[key]), int)
        with self.assertRaises((AttributeError, TypeError)): facts.owners = ()

    def test_cursor_borrows_only_one_current_raw_value_and_metadata(self):
        # Regression: copies payload/metadata or retains Dataset/all variables.
        ds = self.direct()
        variables = member(xr.Dataset, '_variables', ds)
        raw_attrs = {'units': 'm'}; raw_encoding = {'_FillValue': None}
        set_member(Variable, '_attrs', variables['a'], raw_attrs)
        set_member(Variable, '_encoding', variables['a'], raw_encoding)
        self.scan(ds)
        value = self.cursor(ds, 'a')
        self.assertEqual(set(type(value).__slots__), {'data', 'dims', 'shape', 'dtype', 'attrs', 'encoding'})
        self.assertIs(value.data, member(Variable, '_data', variables['a']))
        self.assertIs(value.dims, member(Variable, '_dims', variables['a']))
        self.assertEqual(value.shape, (3,))
        self.assertEqual(value.dtype, '<f8')
        self.assertIs(value.attrs, raw_attrs)
        self.assertIs(value.encoding, raw_encoding)

    def test_exact_dataset_variable_indexvariable_and_missing_slots(self):
        # Regression: accept subclasses, partial exact instances, or duck variables.
        class DatasetSubclass(xr.Dataset): __slots__ = ()
        self.refusal('unsupported_source_storage', self.scan, DatasetSubclass())
        self.refusal('unsupported_source_storage', self.scan, object.__new__(xr.Dataset))
        for replacement in (StockPoison(), object.__new__(Variable), object.__new__(IndexVariable)):
            ds = self.direct()
            member(xr.Dataset, '_variables', ds)['a'] = replacement
            self.assert_no_payload_prepass(ds)
        for cls in (Variable, IndexVariable):
            ds = self.direct()
            raw = member(xr.Dataset, '_variables', ds)['x']
            replacement = cls(('x',), np.array([2, 1, 3], dtype='int32'))
            # Direct slot replacement avoids constructor-created adapter assumptions.
            set_member(Variable, '_data', replacement, member(Variable, '_data', raw))
            member(xr.Dataset, '_variables', ds)['x'] = replacement
            self.scan(ds)

    def test_all_three_namedarray_shadows_refuse_before_any_owner(self):
        # Regression: inspect active Variable slots but ignore retained base slots.
        for slot in ('_attrs', '_data', '_dims'):
            ds = self.direct()
            variable = member(xr.Dataset, '_variables', ds)['a']
            set_member(NamedArray, slot, variable, StockPoison())
            self.assert_no_payload_prepass(ds)

    def test_exact_root_containers_and_close_none_are_required(self):
        # Regression: generic mapping/set access or unknown retained close callback.
        class DictSubclass(dict): pass
        class SetSubclass(set): pass
        for slot, replacement in (('_variables', DictSubclass()), ('_dims', DictSubclass()),
                                  ('_indexes', DictSubclass()), ('_coord_names', SetSubclass()),
                                  ('_close', StockPoison())):
            ds = self.direct(); set_member(xr.Dataset, slot, ds, replacement)
            self.assert_no_payload_prepass(ds)

    def test_root_encoding_none_or_exact_empty_only_before_any_owner(self):
        # Regression: discard or defer unsupported unbound root encoding.
        class DictSubclass(dict): pass
        for value in (None, {}):
            ds = self.direct(); set_member(xr.Dataset, '_encoding', ds, value)
            self.scan(ds)
            self.assertIs(member(xr.Dataset, '_encoding', ds), value)
        for value in ({'source': StockPoison()}, DictSubclass(), [], StockPoison()):
            ds = self.direct(); set_member(xr.Dataset, '_encoding', ds, value)
            self.assert_no_payload_prepass(ds)
            self.assertIs(member(xr.Dataset, '_encoding', ds), value)

    def test_root_empty_encoding_retained_capacity_is_base_not_cache(self):
        # Regression: root encoding backing is free or incorrectly assigned to C.
        ds = self.direct(); small = {}; large = dict.fromkeys(range(1000))
        for key in range(1000): del large[key]  # Fixture setup only.
        set_member(xr.Dataset, '_encoding', ds, small); before = self.scan(ds)
        set_member(xr.Dataset, '_encoding', ds, large); after = self.scan(ds)
        self.assertEqual(after.stock_headers - before.stock_headers, h_container(large) - h_container(small))
        self.assertEqual(after.cache_bytes, before.cache_bytes)
        self.assertEqual(after.owners, before.owners)

    def test_raw_attrs_and_variable_encoding_costs_are_left_to_metadata_bridge(self):
        # Regression: traverse raw metadata here or charge it again before bridge.
        ds = self.direct(); before = self.scan(ds)
        set_member(xr.Dataset, '_attrs', ds, {'opaque': StockPoison()})
        for variable in member(xr.Dataset, '_variables', ds).values():
            set_member(Variable, '_attrs', variable, {'opaque': StockPoison()})
            set_member(Variable, '_encoding', variable, {'opaque': StockPoison()})
        after = self.scan(ds)
        self.assertEqual(after.stock_headers, before.stock_headers)
        self.assertEqual(after.cache_bytes, before.cache_bytes)
        self.assertEqual(after.owners, before.owners)

    def test_missing_dataset_cache_does_not_resolve_same_named_variable(self):
        # Regression: getattr(ds, '_cache') invokes Dataset.__getattr__ fallback.
        ds = xr.Dataset({'_cache': (('x',), np.array([1.0]))})
        with patch.object(xr.Dataset, '__getattr__', side_effect=AssertionError('Dataset fallback')):
            first = self.scan(ds); second = self.scan(ds)
        self.assertEqual(first.cache_bytes, 0)
        self.assertEqual(first.owners, second.owners)
        with self.assertRaises(AttributeError): member(xr.Dataset, '_cache', ds)
        self.owner(first, 'variable', '_cache')

    def test_dataset_empty_cache_is_charged_only_to_c_without_capacity_changes(self):
        # Regression: ignore retained empty capacity or mutate/populate the cache.
        ds = self.direct(); absent = self.scan(ds)
        for cache in ({}, dict.fromkeys(range(1000))):
            for key in tuple(cache): del cache[key]  # Fixture setup only.
            set_member(xr.Dataset, '_cache', ds, cache)
            state = dataset_state(ds); facts = self.scan(ds)
            self.assertEqual(facts.cache_bytes - absent.cache_bytes, h_container(cache))
            self.assertEqual(facts.stock_headers, absent.stock_headers)
            self.assertEqual(facts.owners, absent.owners)
            self.assertEqual(dataset_state(ds), state)

    def test_nonempty_or_nonexact_dataset_cache_refuses_without_mutation(self):
        # Regression: clear/compact or ignore an unknown Dataset cache.
        class DictSubclass(dict): pass
        for cache in ({'unknown': StockPoison()}, DictSubclass(), StockPoison()):
            ds = self.direct(); set_member(xr.Dataset, '_cache', ds, cache)
            self.assert_no_payload_prepass(ds)
            self.assertIs(member(xr.Dataset, '_cache', ds), cache)
            if type(cache) is dict: self.assertEqual(tuple(cache), ('unknown',))

    def test_late_auxiliary_scalar_and_multidimensional_coordinates_precede_all_owners(self):
        # Regression: read an early object payload before complete membership check.
        for dims, payload in ((('x',), np.zeros(3)), ((), np.array(1.0)),
                              (('x', 'y'), np.zeros((3, 2)))):
            ds = self.direct(np.array(['a', 'b', 'c'], dtype=object))
            variables = member(xr.Dataset, '_variables', ds)
            variables['zz_aux'] = Variable(dims, payload)
            member(xr.Dataset, '_coord_names', ds).add('zz_aux')
            if 'y' in dims: member(xr.Dataset, '_dims', ds)['y'] = 2
            self.assert_no_payload_prepass(ds)

    def test_complete_dimension_variable_and_membership_topology_precedes_owners(self):
        # Regression: accept mismatched variable dimensions/shapes or dangling names.
        cases = ('missing_coord', 'missing_dimension', 'shape_mismatch', 'duplicate_dims', 'unknown_index')
        for case in cases:
            ds = self.direct(); variables = member(xr.Dataset, '_variables', ds)
            if case == 'missing_coord': member(xr.Dataset, '_coord_names', ds).add('ghost')
            elif case == 'missing_dimension': member(xr.Dataset, '_dims', ds).pop('x')
            elif case == 'shape_mismatch': member(xr.Dataset, '_dims', ds)['x'] = 4
            elif case == 'duplicate_dims': set_member(Variable, '_dims', variables['a'], ('x', 'x'))
            else: member(xr.Dataset, '_indexes', ds)['ghost'] = StockPoison()
            code='unsupported_source_storage' if case=='unknown_index' else 'invalid_source'
            self.assert_no_payload_prepass(ds,code)

    def test_direct_numpy_numeric_unicode_fixed_s_and_object_sentinels(self):
        # Regression: require indexes, erase fixed width, or require selected labels.
        values = (np.array([1, 2, 3], dtype='int16'), np.array([1, 2, 3], dtype='float32'),
                  np.array(['a', 'bb', 'c'], dtype='U13'), np.array([b'a', b'bb', b'c'], dtype='S7'),
                  np.array(['a', None, float('nan')], dtype=object))
        for raw in values:
            ds = self.direct(raw); facts = self.scan(ds); cursor = self.cursor(ds, 'x')
            self.assertIs(cursor.data, raw)
            self.assertEqual(cursor.dtype, raw.dtype.str)
            self.assertEqual(self.owner(facts, 'coordinate', 'x')['logical_bytes'], raw.nbytes)
            self.assertEqual(member(xr.Dataset, '_indexes', ds), {})

    def test_direct_object_must_be_immediately_owned_and_every_label_qualified(self):
        # Regression: follow an object view or accept bytes/finite scalars/duck labels.
        poisoned=np.empty(3,dtype=object)
        poisoned[0]='a';poisoned[1]=StockPoison();poisoned[2]='c'
        for raw in (np.array(['a', 'b', 'c'], dtype=object)[:],
                    np.array(['a', b'b', 'c'], dtype=object),
                    np.array(['a', 1, 'c'], dtype=object),
                    poisoned):
            self.refusal('unsupported_source_storage', self.scan, self.direct(raw))

    def test_index_wrappers_preserve_numeric_dtype_and_original_unicode_width(self):
        # Regression: infer descriptor dtype/Unicode width from selected label values.
        for values, expected in ((np.array([1, 2, 3], dtype='int16'), '<i2'),
                                 (np.array([1, 2, 3], dtype='float32'), '<f4'),
                                 (np.array(['a', 'b', 'c'], dtype='U13'), '<U13'),
                                 (np.array(['a', None, float('inf')], dtype=object), '|O')):
            ds = self.indexed(values); facts = self.scan(ds)
            _, _, idx, _ = index_parts(ds)
            cursor = self.cursor(ds, 'x')
            self.assertIs(cursor.data, own_dict(idx)['_data'])
            self.assertEqual(cursor.dtype, expected)
            self.assertEqual(self.owner(facts, 'coordinate', 'x')['logical_bytes'], cursor.data.nbytes)

    def test_indexed_unicode_proof_requires_every_label_to_fit_width(self):
        # Regression: accept original-width evidence inconsistent with raw labels.
        ds = self.indexed(np.array(['too long', 'b', 'c'], dtype=object))
        _, adapter, _, wrapper = index_parts(ds)
        set_member(PandasIndexingAdapter, '_dtype', adapter, np.dtype('U2'))
        set_member(PandasIndex, 'coord_dtype', wrapper, np.dtype('U2'))
        self.refusal('invalid_coordinate', self.scan, ds)

    def test_empty_adapter_and_wrapper_dicts_and_matching_state_required(self):
        # Regression: ignore hidden wrapper dicts or mismatched adapter/index proof.
        for case in ('adapter_dict', 'wrapper_dict', 'dtype', 'dim', 'index', 'wrapper_type'):
            ds = self.indexed(); _, adapter, idx, wrapper = index_parts(ds)
            if case == 'adapter_dict': own_dict(adapter)['extra'] = StockPoison()
            elif case == 'wrapper_dict': own_dict(wrapper)['extra'] = StockPoison()
            elif case == 'dtype': set_member(PandasIndex, 'coord_dtype', wrapper, np.dtype('U12'))
            elif case == 'dim': set_member(PandasIndex, 'dim', wrapper, 'other')
            elif case == 'index': set_member(PandasIndex, 'index', wrapper, pd.Index(['a', 'b', 'c']))
            else: member(xr.Dataset, '_indexes', ds)['x'] = StockPoison()
            self.assert_no_payload_prepass(ds)

    def test_index_extra_fields_name_id_and_backing_type_are_exact(self):
        # Regression: silently allow a broadened Index layout or unsafe hidden state.
        for case in ('extra', 'name', 'id', 'backing', 'missing'):
            ds = self.indexed(); _, _, idx, _ = index_parts(ds); state = own_dict(idx)
            if case == 'extra': state['extra'] = StockPoison()
            elif case == 'name': state['_name'] = StockPoison()
            elif case == 'id': state['_id'] = StockPoison()
            elif case == 'backing': state['_data'] = StockPoison()
            else: del state['_references']
            self.assert_no_payload_prepass(ds)

    def test_range_cursor_uses_scalar_range_and_zero_scientific_allocation(self):
        # Regression: materialize RangeIndex or invent retained 8*length payload.
        ds = self.indexed(pd.RangeIndex(2, 11, 3))
        _, _, idx, _ = index_parts(ds); state = own_dict(idx)
        before = dataset_state(ds); facts = self.scan(ds); cursor = self.cursor(ds, 'x')
        owner = self.owner(facts, 'coordinate', 'x')
        self.assertEqual((owner['terminal_bytes'], owner['header_bytes'], owner['logical_bytes']), (0, 0, 24))
        self.assertIs(cursor.data, state['_range'])
        self.assertEqual((cursor.dims, cursor.shape, cursor.dtype), (('x',), (3,), '<i8'))
        self.assertNotIn('_data', state['_cache'])
        self.assertEqual(dataset_state(ds), before)

    def test_range_signed64_scalar_state_and_references_none(self):
        # Regression: use int64 casting, unbounded range state, or accept refs on Range.
        for replacement in (range(2**63, 2**63 + 3), range(-2**63 - 1, -2**63 + 2),
                            range(0, 3, 2**63), StockPoison()):
            ds = self.indexed(pd.RangeIndex(3)); _, _, idx, _ = index_parts(ds)
            own_dict(idx)['_range'] = replacement
            self.refusal('unsupported_source_storage', self.scan, ds)
        ds = self.indexed(pd.RangeIndex(3)); _, _, idx, _ = index_parts(ds)
        own_dict(idx)['_references'] = own_dict(pd.Index([1, 2, 3]))['_references']
        self.refusal('unsupported_source_storage', self.scan, ds)

    def test_full_eight_mib_owner_and_each_shared_variable_occurrence_are_charged(self):
        # Regression: charge logical view bytes or grant cross-name alias credit.
        backing = np.zeros(1024 * 1024, dtype='float64'); view = backing[:1]
        ds = xr.Dataset({'a': (('x',), view), 'b': (('x',), view)})
        facts = self.scan(ds)
        for name in ('a', 'b'):
            owner = self.owner(facts, 'variable', name)
            self.assertEqual(owner['terminal_bytes'], 8 * 1024 * 1024)
            self.assertEqual(owner['logical_bytes'], 8)
            self.assertGreaterEqual(owner['header_bytes'], 1280)
        self.assertEqual(sum(value['terminal_bytes'] for value in facts.owners), 16 * 1024 * 1024)

    def test_duplicate_scientific_owners_keep_original_source_subtotal_live(self):
        # Regression: release/subtract previous owners or replace them by logical views.
        backing = np.zeros(1024 * 1024, dtype='float64')
        ds = xr.Dataset({'v%02d' % i: (('x',), backing[:1]) for i in range(17)})
        self.refusal('source_bytes_limit', self.scan, ds)

    def test_properties_and_cache_creating_accessors_are_never_called(self):
        # Regression: switch audited descriptor reads to convenience properties.
        datasets = (self.direct(), self.indexed(), self.indexed(pd.RangeIndex(3)))
        with ExitStack() as stack:
            for cls, name in ((Variable, 'data'), (Variable, 'values'), (pd.Index, '_engine'),
                              (pd.RangeIndex, '_data')):
                stack.enter_context(patch.object(cls, name,
                    property(lambda self: (_ for _ in ()).throw(AssertionError('unsafe property')))))
            for ds in datasets:
                before = dataset_state(ds)
                self.scan(ds); self.cursor(ds, 'x')
                self.assertEqual(dataset_state(ds), before)


class StockCacheTests(unittest.TestCase):
    stock=StockPrepassTests.stock
    scan=StockPrepassTests.scan
    cursor=StockPrepassTests.cursor
    refusal=StockPrepassTests.refusal
    direct=StockPrepassTests.direct
    indexed=StockPrepassTests.indexed
    owner=StockPrepassTests.owner
    assert_no_payload_prepass=StockPrepassTests.assert_no_payload_prepass
    FAMILIES = (('Int8', 'int8'), ('Int16', 'int16'), ('Int32', 'int32'), ('Int64', 'int64'),
                ('UInt8', 'uint8'), ('UInt16', 'uint16'), ('UInt32', 'uint32'), ('UInt64', 'uint64'),
                ('Float32', 'float32'), ('Float64', 'float64'), ('Object', 'object'))

    def test_all_eleven_existing_engine_and_mapping_families_exact_delta_and_no_mutation(self):
        # Regression: omit a native family/header/body or create a mapping while sizing.
        for prefix, dtype in self.FAMILIES:
            with self.subTest(family=prefix):
                ds = self.indexed(np.array(['c', 'a', 'b'] if dtype == 'object' else [3, 1, 2], dtype=dtype))
                _, _, idx, _ = index_parts(ds); state = own_dict(idx); cache = state['_cache']
                baseline = self.scan(ds); old_h = h_container(cache)
                # Fixture setup ONLY: the next property deliberately allocates the engine.
                engine = idx._engine
                self.assertIs(type(engine), getattr(libindex, prefix + 'Engine'))
                self.assertIsNone(member(libindex.IndexEngine, 'mapping', engine))
                before = dataset_state(ds); unmapped = self.scan(ds)
                expected_engine = (h_container(cache) - old_h + p_string('_engine') +
                                   512 + object.__sizeof__(engine) + 16)
                self.assertEqual(unmapped.cache_bytes - baseline.cache_bytes, expected_engine)
                self.assertEqual(dataset_state(ds), before)
                self.assertEqual(unmapped.stock_headers, baseline.stock_headers)
                self.assertEqual(unmapped.owners, baseline.owners)
                # Fixture setup ONLY: this stock lookup deliberately allocates mapping.
                idx.get_loc('a' if dtype == 'object' else 1)
                mapping = member(libindex.IndexEngine, 'mapping', engine)
                table = getattr(ht, 'PyObjectHashTable' if prefix == 'Object' else prefix + 'HashTable')
                self.assertIs(type(mapping), table)
                diagnostic = table.get_state(mapping)  # Test-only, audited read-only diagnostic.
                key_width = struct.calcsize('P') if prefix == 'Object' else np.dtype(dtype).itemsize
                buckets = diagnostic['n_buckets']
                native = (4 * 4 + 3 * struct.calcsize('P') + max(1, buckets >> 5) * 4 +
                          buckets * (key_width + struct.calcsize('n')))
                self.assertEqual(table.sizeof(mapping, deep=False), native)
                before = dataset_state(ds)
                for _ in range(3):
                    mapped = self.scan(ds)
                    self.assertEqual(mapped.cache_bytes - unmapped.cache_bytes,
                                     object.__sizeof__(mapping) + 16 + native)
                self.assertEqual(table.get_state(mapping), diagnostic)
                self.assertEqual(dataset_state(ds), before)

    def test_index_reference_capacity_dead_entries_and_counter_are_charged_without_compaction(self):
        # Regression: call ref()/has_reference(), drop dead refs, or ignore list capacity.
        ds = self.indexed(np.array([1, 2, 3], dtype='int64'))
        _, _, idx, _ = index_parts(ds); refs = own_dict(idx)['_references']
        values = member(BlockValuesRefs, 'referenced_blocks', refs)
        baseline = self.scan(ds)
        old_charge = 512 + h_container(values) + sum(max(128, object.__sizeof__(v) + 16) for v in values) + 128
        # Fixture setup ONLY: retain dead weakrefs and excess list capacity.
        class Referent: pass
        live = [Referent() for _ in range(64)]
        extra = [weakref.ref(value) for value in live]
        values.extend(extra)
        del live
        new_charge = 512 + h_container(values) + sum(max(128, object.__sizeof__(v) + 16) for v in values) + 128
        before = dataset_state(ds); measured = self.scan(ds)
        self.assertEqual(measured.cache_bytes - baseline.cache_bytes, new_charge - old_charge)
        self.assertEqual(dataset_state(ds), before)

    def test_unknown_reference_state_and_callback_refuse_without_calling(self):
        # Regression: accept callback-bearing refs or unknown bookkeeping containers.
        class Referent: pass
        class ListSubclass(list): pass
        for case in ('refs', 'counter_negative', 'entry', 'callback'):
            ds = self.indexed(np.array([1, 2, 3], dtype='int64'))
            _, _, idx, _ = index_parts(ds); state = own_dict(idx); refs = state['_references']
            callbacks = []; referent = Referent()
            if case == 'refs': state['_references'] = StockPoison()
            elif case == 'counter_negative': set_member(BlockValuesRefs, 'clear_counter', refs, -1)
            elif case == 'entry': member(BlockValuesRefs, 'referenced_blocks', refs).append(StockPoison())
            else: member(BlockValuesRefs, 'referenced_blocks', refs).append(weakref.ref(referent, lambda value: callbacks.append(value)))
            self.refusal('unsupported_source_storage', self.scan, ds)
            self.assertEqual(callbacks, [])

    def test_unknown_cache_key_wrong_engine_and_different_values_refuse(self):
        # Regression: broaden finite cache keys/families or charge a hidden engine array.
        for case in ('unknown_key', 'engine_object', 'wrong_family', 'other_values'):
            ds = self.indexed(np.array([1, 2, 3], dtype='int64'))
            _, _, idx, _ = index_parts(ds); cache = own_dict(idx)['_cache']
            if case == 'unknown_key': cache['unreviewed'] = StockPoison()
            elif case == 'engine_object': cache['_engine'] = StockPoison()
            elif case == 'wrong_family': cache['_engine'] = pd.Index(np.array([1, 2, 3], dtype='float64'))._engine
            else: cache['_engine'] = pd.Index(np.array([1, 2, 3], dtype='int64'))._engine
            before = tuple((k, id(v)) for k, v in cache.items()), dict.__sizeof__(cache)
            self.refusal('unsupported_source_storage', self.scan, ds)
            self.assertEqual((tuple((k, id(v)) for k, v in cache.items()), dict.__sizeof__(cache)), before)

    def test_only_finite_stored_semantic_cache_values_are_accepted(self):
        # Regression: coerce unknown values or inspect properties to rederive flags.
        allowed = {'dtype': np.dtype('int64'), 'inferred_type': 'integer', 'is_unique': True,
                   'is_monotonic_increasing': True, 'is_monotonic_decreasing': False,
                   '_is_multi': False, '_na_value': float('nan'), 'hasnans': False,
                   '_can_hold_na': False, '_should_fallback_to_positional': False}
        ds = self.indexed(np.array([1, 2, 3], dtype='int64'))
        _, _, idx, _ = index_parts(ds); cache = own_dict(idx)['_cache']
        cache.update(allowed)  # Fixture setup ONLY.
        before = dataset_state(ds); self.scan(ds)
        self.assertEqual(dataset_state(ds), before)
        for key in allowed:
            previous = cache[key]; cache[key] = StockPoison()
            self.refusal('unsupported_source_storage', self.scan, ds)
            cache[key] = previous

    def test_range_existing_data_is_c_only_and_scalar_semantics_remain_authoritative(self):
        # Regression: turn an existing derived cache into source payload or free it.
        ds = self.indexed(pd.RangeIndex(2, 11, 3)); _, _, idx, _ = index_parts(ds)
        cache = own_dict(idx)['_cache']; baseline = self.scan(ds); old_h = h_container(cache)
        idx.to_numpy()  # Fixture setup ONLY: allocate exact RangeIndex _data.
        data = cache['_data']; before = dataset_state(ds); cached = self.scan(ds)
        self.assertEqual(cached.cache_bytes - baseline.cache_bytes,
                         h_container(cache) - old_h + p_string('_data') + array_charge(data))
        self.assertEqual(cached.stock_headers, baseline.stock_headers)
        self.assertEqual(cached.owners, baseline.owners)
        self.assertIs(self.cursor(ds, 'x').data, own_dict(idx)['_range'])
        self.assertEqual(dataset_state(ds), before)

    def test_range_cached_data_rejects_wrong_dtype_shape_owner_and_unknown_mask(self):
        # Regression: accept a derived non-owned/non-native/wrong-size cache.
        for data in (np.arange(3, dtype='int32'), np.arange(4, dtype='int64'),
                     np.arange(3, dtype='int64')[:], np.arange(3, dtype='>i8'), StockPoison()):
            ds = self.indexed(pd.RangeIndex(3)); _, _, idx, _ = index_parts(ds)
            own_dict(idx)['_cache']['_data'] = data
            self.refusal('unsupported_source_storage', self.scan, ds)
        ds = self.indexed(pd.RangeIndex(3)); _, _, idx, _ = index_parts(ds)
        own_dict(idx)['_cache']['_isnan'] = np.zeros(3, dtype='bool')
        self.refusal('unsupported_source_storage', self.scan, ds)

    def test_existing_numeric_bool_and_object_uint8_missingness_owner_routes(self):
        # Regression: charge mask logical bytes only or reject proved uint8 terminal.
        for values in (np.array([1.0, float('nan'), 3.0]), np.array(['a', None, 'c'], dtype=object)):
            ds = self.indexed(values); _, _, idx, _ = index_parts(ds)
            # Fixture setup ONLY: isna also caches this bool; establish it first.
            idx._can_hold_na
            cache = own_dict(idx)['_cache']; baseline = self.scan(ds); old_h = h_container(cache)
            idx.isna()  # Fixture setup ONLY: existing stock _isnan.
            mask = cache['_isnan']; before = dataset_state(ds); facts = self.scan(ds)
            self.assertEqual(facts.cache_bytes - baseline.cache_bytes,
                             h_container(cache) - old_h + p_string('_isnan') + array_charge(mask))
            self.assertEqual(facts.stock_headers, baseline.stock_headers)
            self.assertEqual(facts.owners, baseline.owners)
            self.assertEqual(dataset_state(ds), before)

    def test_missingness_rejects_bytes_terminal_unknown_dtype_rank_and_shape(self):
        # Regression: borrow general ndarray source routes for the narrower mask gate.
        masks = (np.frombuffer(b'\0\0\0', dtype='bool'), np.zeros(3, dtype='uint8'),
                 np.zeros((1, 3), dtype='bool'), np.zeros(2, dtype='bool'),
                 np.zeros(3, dtype='int16').view('bool')[:3], StockPoison())
        for mask in masks:
            ds = self.indexed(np.array([1, 2, 3], dtype='int64')); _, _, idx, _ = index_parts(ds)
            own_dict(idx)['_cache']['_isnan'] = mask
            self.refusal('unsupported_source_storage', self.scan, ds)

    def test_cache_owner_above_source_limit_uses_journey_domain_and_repeated_charges(self):
        # Regression: apply scientific 128MiB cap to C, or deduplicate shared masks.
        # Genuine one-byte logical mask backed by one ~128MiB allocation. No
        # enormous physical fixture is needed: the same terminal is charged by name.
        backing = np.zeros(r.SOURCE_MEMORY_BASE_LIMIT + 1, dtype='uint8')
        mask = backing[:1].view('bool')
        ds = xr.Dataset(coords={'x': np.array([1], dtype='int64')})
        _, _, idx, _ = index_parts(ds); own_dict(idx)['_cache']['_isnan'] = mask
        facts = self.scan(ds)
        self.assertGreater(facts.cache_bytes, r.SOURCE_MEMORY_BASE_LIMIT)
        self.assertLess(facts.cache_bytes, r.LOGICAL_JOURNEY_LIMIT)
        self.assertLess(facts.stock_headers + sum(v['terminal_bytes'] + v['header_bytes'] for v in facts.owners),
                        r.SOURCE_MEMORY_BASE_LIMIT)
        ds = xr.Dataset(coords={name: np.array([1], dtype='int64') for name in ('w', 'x', 'y', 'z')})
        for name in ('w', 'x', 'y', 'z'):
            _, _, idx, _ = index_parts(ds, name); own_dict(idx)['_cache']['_isnan'] = mask
        self.refusal('estimated_memory_limit', self.scan, ds)


class ExistingMetadataComparisonTests(unittest.TestCase):
    bridge=FiniteMemoryMetadataTests.bridge
    state=FiniteMemoryMetadataTests.state
    finish=FiniteMemoryMetadataTests.finish
    no_tags=FiniteMemoryMetadataTests.no_tags
    refusal=StructuralSourceTests.refusal

    def compare_function(self):
        module=self.bridge()
        self.assertTrue(callable(getattr(module,'_compare_metadata',None)),
                        'incremental existing metadata comparison is missing')
        return module._compare_metadata

    def test_equal_raw_metadata_compares_without_a_parallel_tag_forest(self):
        import numpy as np
        compare=self.compare_function();module=self.bridge()
        raw={'unicode':np.array(['a','é'],dtype='U16384'),'number':np.int64(7)}
        expected=MetadataValue({'unicode':['a','é'],'number':7})._tagged
        state=self.state();module._scan_metadata(state,raw);self.finish(state)
        with self.no_tags(),patch.object(module,'_build_metadata',side_effect=AssertionError('parallel tag build')):
            self.assertIsNone(compare(state,raw,expected))

    def test_typed_scalar_and_signed_zero_mismatch_is_source_changed(self):
        compare=self.compare_function();module=self.bridge()
        for actual,old in ((1.0,1),(0.0,-0.0),('ab','cd'),([1],{'a':1})):
            raw={'v':actual};expected=MetadataValue({'v':old})._tagged
            state=self.state();module._scan_metadata(state,raw);self.finish(state)
            with self.no_tags(): self.refusal('source_changed',compare,state,raw,expected)

    def test_raw_and_expected_shapes_are_qualified_before_comparison(self):
        compare=self.compare_function();module=self.bridge();state=self.state()
        raw={'v':None};module._scan_metadata(state,raw);self.finish(state)
        expected=MetadataValue({'v':None})._tagged
        raw['v']=Poison()
        with self.no_tags():
            self.refusal('unsupported_source_storage',compare,state,raw,expected)
        self.refusal('invalid_source',compare,state,{},object.__new__(OwnedMap))


class EagerMemorySourceApiTests(unittest.TestCase):
    """Source behavior with labelled runtime instrumentation; no plan stand-ins."""
    refusal=StructuralSourceTests.refusal

    def api(self):
        self.assertTrue(callable(getattr(rt,'snapshot_dataset',None)),
                        'eager snapshot_dataset API is missing')
        self.assertTrue(callable(getattr(rt,'prepare_source',None)),
                        'eager prepare_source API is missing')
        module=importlib.import_module('replicatetable.source')
        for name in ('_materialize_memory','recheck_source','_snapshot_memory'):
            self.assertTrue(callable(getattr(module,name,None)),name+' is missing')
        return module

    def dataset(self, values=None, labels=None):
        import numpy as np
        import xarray as xr
        if values is None: values=np.array([1.0,2.0],dtype='float64')
        if labels is None: labels=np.array([2,1],dtype='int64')
        ds=xr.Dataset({'a':(('x',),values)},
            coords=xr.Coordinates({'x':(('x',),labels)},indexes={}))
        # Explicit supported storage fixture, not source-adapter mutation.
        ds._variables['x']._data=labels
        return ds

    def runtime(self):
        # Test-only ordering instrumentation. The separate fresh-runtime test
        # below calls the real gate; this context does not claim runtime proof.
        return patch('replicatetable.runtime.runtime_identity',return_value=None)

    def test_public_memory_surface_and_descriptor_only_snapshot(self):
        self.api();ds=self.dataset()
        with self.runtime(): snapshot=rt.snapshot_dataset(ds)
        self.assertIs(type(snapshot),rt.SourceSnapshot)
        self.assertIs(snapshot._handle,ds)
        self.assertEqual(tuple(snapshot.arrays),())
        self.assertEqual(tuple(snapshot.coordinates),())
        self.assertEqual(snapshot.variables['a']['dtype'],'float64')
        self.assertEqual(snapshot.coordinate_descriptors['x']['dtype'],'<i8')
        self.assertTrue(callable(rt.execute))
        self.assertFalse(hasattr(rt,'inspect_source'))

    def test_numeric_identity_exact_framed_stream(self):
        import hashlib,json,struct
        self.api();ds=self.dataset()
        with self.runtime(): snapshot=rt.snapshot_dataset(ds)
        projection=json.loads(snapshot.to_json());del projection['source']
        def canonical(value):
            return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
        raw=canonical({'format':'replicatetable-memory-source-v2','descriptor':projection})
        for kind,name,dtype,payload in (('coordinate','x','<i8',struct.pack('<qq',2,1)),
                                       ('variable','a','float64',struct.pack('<dd',1.0,2.0))):
            header=canonical({'kind':kind,'name':name,'dtype':dtype,'shape':[2]})
            raw+=len(header).to_bytes(8,'big')+header+len(payload).to_bytes(8,'big')+payload
        self.assertEqual(snapshot.identity.sha256,hashlib.sha256(raw).hexdigest())
        self.assertEqual(snapshot.identity.size_bytes,len(raw))

    def test_identity_excludes_owner_capacity_and_dataset_empty_cache(self):
        import numpy as np
        import xarray as xr
        self.api();owner=np.zeros(1024*1024,dtype='float64');owner[:2]=[1,2]
        ds=self.dataset(owner[:2]);other=self.dataset()
        with self.runtime():
            first=rt.snapshot_dataset(ds);equal=rt.snapshot_dataset(other)
            self.assertEqual(first.identity,equal.identity)
            xr.Dataset.__dict__['_cache'].__set__(ds,{})
            cached=rt.snapshot_dataset(ds)
        self.assertEqual(first.identity,cached.identity)

    def test_preparation_returns_only_exact_selected_coordinates(self):
        import numpy as np
        import xarray as xr
        self.api();ds=self.dataset()
        ds['unused']=(('y',),np.array([9.0]))
        ds=ds.assign_coords(xr.Coordinates({'y':(('y',),np.array([None],dtype=object))},indexes={}))
        ds._variables['y']._data=np.array([None],dtype=object)
        with self.runtime():
            original=rt.snapshot_dataset(ds);prepared=rt.prepare_source(original,recipe())
        self.assertEqual(tuple(prepared.coordinates),('x',))
        self.assertEqual(tuple(prepared.arrays),())
        self.assertEqual(prepared.coordinates['x'].values,(2,1))
        self.assertEqual(prepared.coordinates['x'].sorted_indices,(1,0))
        self.assertEqual(tuple(original.coordinates),())
        self.assertIs(prepared.dimensions,original.dimensions)
        self.assertIs(prepared.variables,original.variables)

    def test_prepared_reuse_requires_actual_source_recheck(self):
        self.api();ds=self.dataset()
        with self.runtime():
            original=rt.snapshot_dataset(ds);prepared=rt.prepare_source(original,recipe())
            again=rt.prepare_source(prepared,recipe())
            self.assertIs(again.coordinates['x'],prepared.coordinates['x'])
            ds._variables['a']._data[0]=3.0
            self.refusal('source_changed',rt.prepare_source,prepared,recipe())

    def test_private_materialization_owns_bytes_and_consumes_supplied_b(self):
        self.api();a=self.dataset();b=self.dataset()
        with self.runtime():
            source_a=rt.snapshot_dataset(a);source_b=rt.snapshot_dataset(b)
            result=self.api()._materialize_memory(source_b,recipe())
        self.assertEqual(source_a.identity,source_b.identity)
        self.assertIs(result._handle,b)
        self.assertEqual(tuple(result.arrays),('a',))
        self.assertEqual(tuple(result.coordinates),('x',))
        buffer=result.arrays['a'];view=buffer.view()
        self.assertFalse(view.flags.writeable)
        self.assertEqual(tuple(view),(1.0,2.0))
        b._variables['a']._data[:]=[8.0,9.0]
        self.assertEqual(tuple(buffer.view()),(1.0,2.0))

    def test_missing_coordinate_role_codes(self):
        import numpy as np
        import xarray as xr
        self.api();ds=xr.Dataset({'a':(('x',),np.array([1.0,2.0]))})
        with self.runtime():
            source=rt.snapshot_dataset(ds)
            self.refusal('missing_row_key',rt.prepare_source,source,recipe())
            self.refusal('missing_coordinate',rt.prepare_source,source,recipe(rows=()))

    def test_object_missing_duplicate_and_nonfinite_coordinate_roles(self):
        import numpy as np
        self.api()
        for labels,row_code,other_code in (([None,'a'],'missing_row_key','missing_coordinate'),
            (['a','a'],'duplicate_row_key','duplicate_coordinate'),
            ([float('inf'),'a'],'nonfinite_coordinate','nonfinite_coordinate')):
            raw=np.empty(2,dtype=object)
            raw[0]=labels[0];raw[1]=labels[1]
            with self.runtime():
                source=rt.snapshot_dataset(self.dataset(labels=raw))
                self.refusal(row_code,rt.prepare_source,source,recipe())
                self.refusal(other_code,rt.prepare_source,source,recipe(rows=()))

    def test_selected_encoding_guard_precedes_runtime_and_coordinate_allocation(self):
        self.api();ds=self.dataset();ds._variables['x']._attrs={'calendar':None}
        with self.runtime(): source=rt.snapshot_dataset(ds)
        with patch('replicatetable.runtime.runtime_identity',side_effect=AssertionError('runtime before declaration')), \
             patch.object(Coordinate,'__init__',side_effect=AssertionError('coordinate before declaration')):
            self.refusal('unsupported_coordinate_encoding',rt.prepare_source,source,recipe())

    def test_deleted_derived_status_cannot_enable_selected_packing(self):
        self.api();ds=self.dataset();ds._variables['a']._attrs={'scale_factor':1}
        with self.runtime(): source=rt.snapshot_dataset(ds)
        desc=dict(source.variables['a'].items());desc['selection_status']=None
        args={name:getattr(source,name) for name in source.__slots__};args['variables']={'a':OwnedMap(desc)}
        forged=rt.SourceSnapshot(**args)
        with self.runtime(): self.refusal('unsupported_source_encoding',rt.prepare_source,forged,recipe())

    def test_raw_object_unicode_and_fixed_s_routes_keep_distinct_identity(self):
        import numpy as np
        self.api();datasets=(self.dataset(labels=np.array(['a','b'],dtype=object)),
            self.dataset(labels=np.array(['a','b'],dtype='U8')),
            self.dataset(labels=np.array([b'a',b'b'],dtype='S8')))
        with self.runtime():
            snapshots=[rt.snapshot_dataset(ds) for ds in datasets]
            prepared=[rt.prepare_source(snap,recipe()) for snap in snapshots]
        self.assertEqual([snap.coordinate_descriptors['x']['dtype'] for snap in snapshots],['|O','<U8','|S8'])
        self.assertEqual([snap.coordinates['x'].dtype for snap in prepared],['<U1','<U8','<U8'])
        self.assertEqual(len({snap.identity.sha256 for snap in snapshots}),3)

    def test_unselected_data_and_metadata_are_bound_in_identity(self):
        import numpy as np
        self.api();ds=self.dataset();ds['unused']=(('y',),np.array([9.0]))
        with self.runtime():
            old=rt.snapshot_dataset(ds)
            ds._variables['unused']._data[0]=10.0
            self.refusal('source_changed',self.api().recheck_source,old)
            current=rt.snapshot_dataset(ds)
            self.assertNotEqual(current.identity,old.identity)
            ds._attrs={'label':'changed'}
            self.refusal('source_changed',self.api().recheck_source,current)

    def test_wrong_values_and_invalid_phase_do_not_reach_source_reads(self):
        self.api()
        self.refusal('invalid_source',rt.snapshot_dataset,Poison())
        with self.runtime(): source=rt.snapshot_dataset(self.dataset())
        self.refusal('invalid_recipe',rt.prepare_source,source,Poison())
        wider=StructuralSourceTests.snapshot(self,dimensions={'x':2,'y':1},
            coordinate_descriptors={'x':descriptor(dtype='<i8'),'y':descriptor(('y',),(1,),'<i8')},
            coordinates={'y':Coordinate('<i8',[0],[0])})
        with patch('replicatetable._source_stock._stock_prepass',side_effect=AssertionError('source before phase')):
            self.refusal('invalid_source_phase',rt.prepare_source,wider,recipe())

    source=StructuralSourceTests.source

    def test_owned_exception_detaches_only_owned_links_preserving_identity_and_cancellation(self):
        import gc,weakref
        import numpy as np
        module=self.api();ds=self.dataset();setter_calls=[]
        class Cancel(KeyboardInterrupt):
            def __setattr__(self,name,value):
                setter_calls.append(name);super().__setattr__(name,value)
        unrelated=ValueError('unrelated caller error')
        original_links=(unrelated.__traceback__,unrelated.__context__,unrelated.__cause__)
        for failure in (Refusal('invalid_coordinate'),KeyboardInterrupt(),Cancel()):
            refs=[]
            def failed_operation(dataset):
                owned=np.ones(128,dtype='float64');refs.append(weakref.ref(owned))
                raise failure from unrelated
            setter_calls.clear();was_enabled=gc.isenabled();gc.disable()
            try:
                caught=None
                with patch.object(module,'_snapshot_memory',failed_operation):
                    try: rt.snapshot_dataset(ds)
                    except BaseException as error: caught=error
                self.assertIs(caught,failure)
                self.assertIsNone(refs[0]())
                self.assertIsNone(caught.__context__);self.assertIsNone(caught.__cause__)
                self.assertEqual(setter_calls,[])
                self.assertEqual((unrelated.__traceback__,unrelated.__context__,unrelated.__cause__),original_links)
                if isinstance(failure,Refusal): self.assertEqual(caught.code,'invalid_coordinate')
            finally:
                if was_enabled: gc.enable()

    def test_real_fresh_runtime_gate_on_small_eager_source(self):
        self.api()
        # This one uses the actual pinned runtime gate without instrumentation.
        snapshot=rt.snapshot_dataset(self.dataset())
        self.assertEqual(snapshot.identity.kind,'memory')
        self.assertEqual(tuple(snapshot.arrays),())


class RetainedSourceAuthorityTests(unittest.TestCase):
    api=EagerMemorySourceApiTests.api
    dataset=EagerMemorySourceApiTests.dataset
    runtime=EagerMemorySourceApiTests.runtime
    refusal=StructuralSourceTests.refusal

    def test_recheck_validates_retained_array_bytes_against_actual_source(self):
        module=self.api();ds=self.dataset()
        with self.runtime():
            initial=rt.snapshot_dataset(ds)
            materialized=module._materialize_memory(initial,recipe())
            fields={name:getattr(materialized,name) for name in materialized.__slots__}
            fields['arrays']={'a':ArrayBuffer('float64',(2,),b'\0'*16)}
            forged=rt.SourceSnapshot(**fields)
            self.refusal('invalid_source',module.recheck_source,forged)

    def test_recheck_validates_retained_coordinates_against_actual_source(self):
        module=self.api();ds=self.dataset()
        with self.runtime():
            initial=rt.snapshot_dataset(ds);prepared=rt.prepare_source(initial,recipe())
            fields={name:getattr(prepared,name) for name in prepared.__slots__}
            fields['coordinates']={'x':Coordinate('<i8',[3,4],[0,1])}
            forged=rt.SourceSnapshot(**fields)
            self.refusal('invalid_source',module.recheck_source,forged)

    def test_retained_selection_budget_is_guarded_before_runtime_on_recheck(self):
        import numpy as np
        import xarray as xr
        module=self.api()
        ds=xr.Dataset({'a':(('i','j'),np.ones((4096,256),dtype='float64'))},
            coords=xr.Coordinates({'i':(('i',),np.arange(4096)),
                                   'j':(('j',),np.arange(256))},indexes={}))
        ds=ds.assign_coords({name:(name,np.array([1],dtype='int64')) for name in ('x','y','z')})
        rec=Recipe.from_dict(dict(version=1,row_dims=[],columns=[dict(name='value',source='a',
            source_unit=None,target_unit=None,broadcast=[],stages=[dict(name='reduce',dims=['i','j'],
            op='mean',missing='skip',min_count=1)])]))
        with self.runtime():
            original=rt.snapshot_dataset(ds);materialized=module._materialize_memory(original,rec)
        # A genuine shared cache owner, charged conservatively for three named
        # indexes. Caller-selected 8MiB plus coordinates remain live explicitly.
        backing=np.zeros(124*1024*1024,dtype='uint8');mask=backing[:1].view('bool')
        for name in ('x','y','z'):
            index=ds._indexes[name].index
            object.__getattribute__(index,'__dict__')['_cache']['_isnan']=mask
        with patch('replicatetable.runtime.runtime_identity',side_effect=AssertionError('runtime before complete retained-input admission')):
            self.refusal('estimated_memory_limit',module.recheck_source,materialized)


class SourceAdmissionReviewTests(unittest.TestCase):
    api=EagerMemorySourceApiTests.api
    dataset=EagerMemorySourceApiTests.dataset
    runtime=EagerMemorySourceApiTests.runtime
    refusal=StructuralSourceTests.refusal

    def test_retained_recipe_cost_is_additive_at_every_source_guard(self):
        from replicatetable import admission
        from replicatetable._resource_inputs import _recipe_cost
        self.api();ds=self.dataset()
        recipes=[Recipe.from_dict(dict(version=1,row_dims=['x'],columns=[dict(
            name='c'+str(i)+'x'*120,source='a',source_unit=None,target_unit=None,
            broadcast=[],stages=[]) for i in range(n)])) for n in (1,32)]
        observations=[];real=admission._guard
        with self.runtime():
            snap=rt.snapshot_dataset(ds)
            for rec in recipes:
                calls=[]
                def guard(phase,*,baseline=None):
                    calls.append(baseline);return real(phase,baseline=baseline)
                with patch.object(admission,'_guard',guard): rt.prepare_source(snap,rec)
                observations.append(calls)
        delta=_recipe_cost(recipes[1]).object_bytes-_recipe_cost(recipes[0]).object_bytes
        self.assertGreater(delta,0);self.assertEqual(len(observations[0]),len(observations[1]))
        for first,second in zip(*observations): self.assertEqual(second-first,delta)

    def test_final_guard_keeps_complete_new_output_and_retained_input_reservation(self):
        from replicatetable import admission
        module=self.api();ds=self.dataset();real=admission._guard
        with self.runtime():
            snap=rt.snapshot_dataset(ds)
            for operation in (rt.prepare_source,module._materialize_memory):
                calls=[]
                def guard(phase,*,baseline=None):
                    calls.append(baseline);return real(phase,baseline=baseline)
                with patch.object(admission,'_guard',guard): result=operation(snap,recipe())
                self.assertGreaterEqual(calls[-1],max(calls[:-1]))
            # A prepared return does not release the original materialized input.
            calls=[]
            with patch.object(admission,'_guard',guard): rt.prepare_source(result,recipe())
            self.assertGreaterEqual(calls[-1],max(calls[:-1]))

    def test_coordinate_semantics_resolve_each_dimension_in_role_order(self):
        import numpy as np
        import xarray as xr
        self.api()
        for rows in (['x','y'],['y','x'],[]):
            for late in (float('nan'),float('inf')):
                with self.subTest(rows=rows,late=late):
                    x=np.array([1,1],dtype='int64');y=np.array([late,2.0],dtype='float64')
                    ds=xr.Dataset({'a':(('x','y'),np.ones((2,2)))},coords=xr.Coordinates(
                        {'x':(('x',),x),'y':(('y',),y)},indexes={}))
                    ds._variables['x']._data=x;ds._variables['y']._data=y
                    stages=[] if rows else [dict(name='reduce',dims=['x','y'],op='mean',missing='skip',min_count=1)]
                    rec=Recipe.from_dict(dict(version=1,row_dims=rows,columns=[dict(name='value',source='a',
                        source_unit=None,target_unit=None,broadcast=[],stages=stages)]))
                    expected=('missing_row_key' if np.isnan(late) else 'nonfinite_coordinate') if rows==['y','x'] else (
                        'duplicate_row_key' if rows else 'duplicate_coordinate')
                    with self.runtime():
                        snap=rt.snapshot_dataset(ds)
                        self.refusal(expected,rt.prepare_source,snap,rec)


class SourceReservationPoolTests(unittest.TestCase):
    api=EagerMemorySourceApiTests.api
    dataset=EagerMemorySourceApiTests.dataset
    runtime=EagerMemorySourceApiTests.runtime

    def test_standalone_pays_source_and_common_fixed_pools(self):
        from replicatetable import admission,resources as r
        module=self.api();ds=self.dataset();calls=[];real=admission._guard
        def guard(phase,*,baseline=None):
            calls.append(baseline);return real(phase,baseline=baseline)
        prepass=module._memory_prepass(ds)
        binding=module._current_binding(prepass)
        frame=module._api_frame_cost(prepass.descriptor_cost)
        required=(r.RUNTIME_ALLOWANCE+binding['base_bytes']+5*(frame.json_bytes+1)+3*frame.object_bytes+
            r.CONTROL_STATE_BYTES+prepass.stock.cache_bytes+r.MODEL_FIXED_BYTES+3*r.SERIAL_BUFFER_BYTES)
        with self.runtime(),patch.object(admission,'_guard',guard): rt.snapshot_dataset(ds)
        self.assertGreaterEqual(min(calls),required)

    def test_retained_coordinate_projection_uses_coordinate_not_metadata_member_limit(self):
        module=self.api()
        # 131073 unique four-byte labels fit selected-coordinate 8MiB J/P
        # boundaries but exceed the metadata walker's unrelated tuple cap.
        count=131073
        values=[''.join(chr(97+(i//power)%26) for power in (26**3,26**2,26,1)) for i in range(count)]
        coordinate=Coordinate('<U4',values,list(range(count)))
        snapshot=rt.SourceSnapshot(identity=SourceIdentity('memory','a'*64,123),dimensions={'x':count},
            variables={'a':descriptor(('x',),(count,))},
            coordinate_descriptors={'x':descriptor(('x',),(count,),'<U4')},attributes=MetadataValue({}),
            arrays={},coordinates={'x':coordinate},_handle=None)
        _,cost,_,numeric=module._retained_projection(snapshot)
        self.assertLess(cost.json_bytes,8*1024*1024);self.assertEqual(numeric,0)


class SourceTopologyComparisonTests(unittest.TestCase):
    api=EagerMemorySourceApiTests.api
    dataset=EagerMemorySourceApiTests.dataset
    runtime=EagerMemorySourceApiTests.runtime
    refusal=StructuralSourceTests.refusal

    def test_disappeared_source_members_are_source_changed_before_selection(self):
        module=self.api()
        for name in ('x','a'):
            for operation in (rt.prepare_source,module._materialize_memory,module.recheck_source):
                with self.subTest(name=name,operation=operation.__name__):
                    ds=self.dataset()
                    with self.runtime():
                        snapshot=rt.snapshot_dataset(ds)
                        del ds[name]
                        args=() if operation is module.recheck_source else (recipe(),)
                        self.refusal('source_changed',operation,snapshot,*args)
