"""Finite regressions for the four recovered runtime review blockers."""
import copy
from contextlib import ExitStack
import hashlib
import importlib.machinery
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from replicatetable import runtime as rt
from replicatetable.codec import OwnedMap, canonical_bytes, freeze, thaw
from replicatetable.errors import Refusal
from tests.unit.test_runtime_binding import example


class RuntimeMapRepairs(unittest.TestCase):
    def invalid_before_work(self, value):
        with patch.object(rt, 'freeze', side_effect=AssertionError('freeze called')), \
             patch.object(rt, 'preflight_json', side_effect=AssertionError('preflight called')), \
             patch.object(rt, '_discover_runtime', side_effect=AssertionError('discovery called')), \
             patch.object(rt, '_PROCESS_CHANGED', False):
            with self.assertRaises(Refusal) as caught:
                rt.require_runtime(value)
            self.assertEqual(caught.exception.code, 'invalid_runtime')
            self.assertFalse(rt._PROCESS_CHANGED)

    def test_nonexact_keys_at_every_map_refuse_without_callbacks(self):
        calls=[]
        class Key(str):
            def __hash__(self): calls.append('hash'); return str.__hash__(self)
            def __eq__(self, other): calls.append('eq'); return str.__eq__(self, other)
        paths=[(), ('python',), ('python','abi'), ('python','executable'),
               ('python','stdlib_code'), ('dependencies',), ('dependencies','numpy'),
               ('dependencies','numpy','payload'), ('resources',), ('pint',),
               ('pint','resources'), ('python','core_libraries')]
        for path in paths:
            value=example()
            if path==('python','core_libraries'):
                value['python']['core_libraries']={'libpython.so':{'sha256':'a'*64,'size_bytes':1}}
            target=value
            for name in path: target=target[name]
            name=next(iter(target)); item=target.pop(name); target[Key(name)]=item
            calls.clear()
            with self.subTest(path=path):
                self.invalid_before_work(value)
                self.assertEqual(calls, [])

    def test_arbitrary_proxies_refuse_without_mapping_callbacks(self):
        calls=[]
        class Mapping:
            def __len__(self): calls.append('len'); return 6
            def __iter__(self): calls.append('iter'); return iter(example())
            def __getitem__(self, key): calls.append('get'); return example()[key]
            def keys(self): calls.append('keys'); return example().keys()
        for proxy in (types.MappingProxyType(Mapping()), types.MappingProxyType(example())):
            calls.clear()
            with self.subTest(kind=type(proxy)):
                self.invalid_before_work(proxy)
                self.assertEqual(calls, [])
        value=example(); value['resources']=types.MappingProxyType(value['resources'])
        self.invalid_before_work(value)

    def test_exact_owned_maps_reuse_safe_immutable_backing(self):
        value=example(); owned=freeze(value)
        checked=rt.validate_runtime(owned)
        self.assertIs(checked, owned)
        self.assertIs(type(checked), OwnedMap)
        self.assertEqual(canonical_bytes(checked), canonical_bytes(value))
        value['python']['build'][0]='changed'
        self.assertEqual(checked['python']['build'][0], 'main')

    def test_malformed_owned_backing_refuses_without_callbacks_or_aliases(self):
        calls=[]
        class Hook:
            def __len__(self): calls.append('len'); return 1
            def __iter__(self): calls.append('iter'); return iter(())
        for backing in (Hook(), [('binding_version',1)], (('binding_version',),)):
            forged=OwnedMap._from_checked(backing)
            self.invalid_before_work(forged)
        value=example(); forged=OwnedMap._from_checked(tuple(sorted(value.items())))
        self.invalid_before_work(forged)  # caller-mutable child dicts are never owned backing
        self.assertEqual(calls, [])

    def test_nested_owned_key_types_order_and_mutable_aliases_refuse(self):
        calls=[]
        class Key(str):
            def __eq__(self, other): calls.append('eq'); return str.__eq__(self,other)
            def __hash__(self): calls.append('hash'); return str.__hash__(self)
        for backing in (((Key('__init__.py'),'a'*64),),
                        (('z.py','a'*64),('a.py','a'*64)),
                        (('a.py','a'*64),('a.py','a'*64))):
            value=example(); value['resources']=OwnedMap._from_checked(backing)
            self.invalid_before_work(value)
        self.assertEqual(calls,[])
        for path,replacement in [(('python','abi','optimization'),True),
                                 (('python','compiler'),'x'*129),
                                 (('python','compiler'),'\ud800'),
                                 (('python','executable','sha256'),'X'*64),
                                 (('python','abi','soabi'),'wrong')]:
            value=example(); item=value
            for key in path[:-1]: item=item[key]
            item[path[-1]]=replacement
            self.invalid_before_work(value)

    def test_resources_256_equality_257_refusal_and_preflight_before_freeze(self):
        value=example(); value['resources']={f'{i:03}.py':'a'*64 for i in range(256)}
        actual=rt.validate_runtime(value)
        self.assertEqual(len(actual['resources']),256)
        value['resources']['extra.py']='a'*64
        self.invalid_before_work(value)
        value=example(); events=[]; original=rt.preflight_json
        def preflight(*args,**kwargs): events.append('preflight'); return original(*args,**kwargs)
        original_freeze=rt.freeze
        def frozen(*args,**kwargs): events.append('freeze'); return original_freeze(*args,**kwargs)
        with patch.object(rt,'preflight_json',side_effect=preflight),patch.object(rt,'freeze',side_effect=frozen):
            actual=rt.validate_runtime(value)
        self.assertEqual(events,['preflight','freeze'])
        expected=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()+b'\n'
        self.assertEqual(canonical_bytes(actual),expected)


class RuntimeFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def put(self, name, data=b'x'):
        path=self.root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data); return path

    def assert_code(self, code, fn, *args, **kwargs):
        with self.assertRaises(Refusal) as caught: fn(*args, **kwargs)
        self.assertEqual(caught.exception.code,code)
        self.assertEqual(caught.exception.exit_code,2)
        self.assertNotIn(str(self.root),str(caught.exception))

    def scan(self, kind):
        return rt._inventory(str(self.root),('',),kind,rt._ScanBudget())

    def assert_inventory(self,kind,names):
        expected={name:{'sha256':hashlib.sha256((self.root/name).read_bytes()).hexdigest(),
                        'size_bytes':(self.root/name).stat().st_size} for name in names}
        actual=self.scan(kind)
        self.assertEqual(actual,{'sha256':hashlib.sha256(canonical_bytes(expected)).hexdigest(),
                                 'file_count':len(names),'size_bytes':sum(x['size_bytes'] for x in expected.values())})


class RuntimeSelectorRepairs(RuntimeFixture):
    def test_payload_exclusions_depend_on_entry_type(self):
        selected=['__pycache__','assets.pyc/data','modules.pyo/code.py']
        for name in selected+['ignored.pyc','ignored.pyo']: self.put(name)
        self.assert_inventory('payload',selected)
        for name in selected:
            before=self.scan('payload'); p=self.root/name; st=p.stat(); p.write_bytes(b'y')
            os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
            self.assertNotEqual(before,self.scan('payload'))
        (self.root/'__pycache__').unlink(); self.put('__pycache__/ignored.py')
        self.assert_inventory('payload',selected[1:])

    def test_stdlib_directory_and_file_exclusions_are_separate(self):
        for name in ['config-example.py','config-example/ignored.py','data.pyc/inside.py',
                     'mod.pyo/inside.py','ignored.pyc','_sysconfigdata_vendor.py']:
            self.put(name)
        self.assert_inventory('stdlib',['config-example.py','data.pyc/inside.py','mod.pyo/inside.py'])

    def test_excluded_looking_links_and_special_files_refuse(self):
        for kind,name in [('payload','__pycache__'),('payload','ignored.pyc'),
                          ('stdlib','config-hidden'),('stdlib','ignored.pyo')]:
            with self.subTest(kind=kind,name=name):
                p=self.root/name; p.symlink_to(self.root/'absent')
                self.assert_code('runtime_identity_unavailable',self.scan,kind); p.unlink()
                os.mkfifo(p)
                self.assert_code('runtime_identity_unavailable',self.scan,kind); p.unlink()
        (self.root/'_sysconfigdata_vendor.py').symlink_to(self.root/'absent')
        self.put('os.py')
        self.assert_inventory('stdlib',['os.py'])

    def test_metadata_license_tree_is_not_bytecode_or_cache_filtered(self):
        names=['METADATA','WHEEL','entry_points.txt','top_level.txt','licenses/vendor/data',
               'licenses/LICENSE.pyc','licenses/__pycache__/legal.pyo','LiCeNsE','old/NOTICE',
               'nested/licenses/arbitrary.pyc']
        for name in names+['generated/METADATA','RECORD','INSTALLER','REQUESTED','direct_url.json']:
            self.put(name)
        self.assert_inventory('metadata',names)


class RuntimeOriginRepairs(RuntimeFixture):
    def module(self,name,path,package=False):
        module=types.ModuleType(name); module.__file__=str(path)
        spec=importlib.machinery.ModuleSpec(name,loader=None,origin=str(path),is_package=package)
        if package:
            module.__path__=[str(path.parent)]; spec.submodule_search_locations=module.__path__[:]
        module.__spec__=spec
        return module

    def package(self,name='fixture_runtime'):
        path=self.put('__init__.py'); return self.module(name,path,True)

    def verify(self,owner,children,kind='payload'):
        mods={owner.__name__:owner,**children}
        # Explicit kind is the adapted private selector seam; old recovered
        # default is exercised without it except for actual product namespace.
        with patch.dict(sys.modules,mods): rt._verify_module(owner.__name__,str(self.root))

    def test_product_extension_is_rejected_because_only_python_is_bound(self):
        # Isolate sys.modules so this fixture does not mix the real package.
        owner=self.package('replicatetable'); child=self.module('replicatetable.native',self.put('native.so'))
        with patch.object(rt.sys,'modules',{'replicatetable':owner,'replicatetable.native':child}):
            self.assert_code('runtime_import_origin_mismatch',rt._verify_module,'replicatetable',str(self.root))

    def test_present_selected_origins_pass_but_absent_excluded_links_refuse(self):
        owner=self.package()
        child=self.module('fixture_runtime.child',self.put('a.pyc/child.py'))
        self.verify(owner,{'fixture_runtime.child':child})
        for name in ['absent.py','__pycache__/child.py']:
            if name.startswith('__'): self.put(name)
            child=self.module('fixture_runtime.child',self.root/name)
            self.assert_code('runtime_import_origin_mismatch',self.verify,owner,{'fixture_runtime.child':child})
        self.put('real.py'); (self.root/'link.py').symlink_to(self.root/'real.py')
        child=self.module('fixture_runtime.child',self.root/'link.py')
        self.assert_code('runtime_import_origin_mismatch',self.verify,owner,{'fixture_runtime.child':child})

    def test_nested_packages_require_one_matching_in_root_path(self):
        owner=self.package(); child=self.module('fixture_runtime.nested',self.put('nested/__init__.py'),True)
        self.verify(owner,{'fixture_runtime.nested':child})
        child.__path__.append('/external/root')
        self.assert_code('runtime_import_origin_mismatch',self.verify,owner,{'fixture_runtime.nested':child})
        calls=[]
        class PathHook:
            def __fspath__(self): calls.append('fspath'); return str(self.root)
        child.__path__=[PathHook()]; child.__spec__.submodule_search_locations=[PathHook()]
        self.assert_code('runtime_import_origin_mismatch',self.verify,owner,{'fixture_runtime.nested':child})
        self.assertEqual(calls,[])

    def test_dependency_declared_frozen_and_builtin_children_refuse(self):
        owner=self.package()
        for origin in ('frozen','built-in'):
            child=types.ModuleType('fixture_runtime.fake')
            child.__spec__=importlib.machinery.ModuleSpec(child.__name__,None,origin=origin)
            self.assert_code('runtime_import_origin_mismatch',self.verify,owner,{child.__name__:child})

    def test_fake_stdlib_builtin_and_frozen_refuse_but_stock_passes(self):
        import sysconfig
        root=os.path.realpath(sysconfig.get_path('stdlib'))
        rt._verify_stdlib(root)
        for origin in ('frozen','built-in'):
            fake=types.ModuleType('json.fake'); fake.__spec__=importlib.machinery.ModuleSpec('json.fake',None,origin=origin)
            with patch.dict(sys.modules,{'json.fake':fake}):
                self.assert_code('runtime_import_origin_mismatch',rt._verify_stdlib,root)

    def test_typing_owner_cannot_escape_file_binding_by_claiming_frozen(self):
        import typing,sysconfig
        root=os.path.realpath(sysconfig.get_path('stdlib'))
        with patch.object(typing.__spec__,'origin','frozen'),patch.object(typing,'__file__',None):
            self.assert_code('runtime_import_origin_mismatch',rt._verify_stdlib,root)


class RuntimeMetadataRepairs(RuntimeFixture):
    def test_fifo_metadata_refuses_promptly_without_a_writer(self):
        os.mkfifo(self.root/'METADATA')
        code='from replicatetable.runtime import _metadata_identity\nfrom replicatetable.errors import Refusal\nimport sys\ntry: _metadata_identity(sys.argv[1])\nexcept Refusal as e: print(e.code)\n'
        try:
            run=subprocess.run([sys.executable,'-B','-c',code,str(self.root)],capture_output=True,text=True,timeout=2)
        except subprocess.TimeoutExpired:
            self.fail('METADATA acquisition blocked on a stable FIFO')
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(run.stdout.strip(),'runtime_identity_unavailable')
        self.assertNotIn(str(self.root),run.stdout+run.stderr)

    def test_metadata_acquisition_is_nonblocking_and_regular_before_read(self):
        self.put('METADATA',b'Name: NumPy\nVersion: 2.3.5\n\n')
        original=os.open; flags=[]
        def opened(path, mode, *args, **kwargs):
            if path=='METADATA': flags.append(mode)
            return original(path,mode,*args,**kwargs)
        with patch.object(rt.os,'open',side_effect=opened):
            self.assertEqual(rt._metadata_identity(str(self.root)),('numpy','2.3.5'))
        self.assertEqual(len(flags),1)
        self.assertTrue(flags[0]&os.O_NONBLOCK)
        self.assertTrue(flags[0]&os.O_NOFOLLOW)
        (self.root/'METADATA').unlink(); (self.root/'METADATA').mkdir()
        self.assert_code('runtime_identity_unavailable',rt._metadata_identity,str(self.root))
