"""Adapted runtime unit controls. No absent source/plan success gates are claimed.

Recovered tests are provenance only. Full real-profile discovery is exercised
separately by the sealed-copy smoke evidence, not this small fixture suite.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from replicatetable.errors import Refusal
from replicatetable.codec import canonical_bytes as canonical_json, thaw
from replicatetable.runtime import validate_runtime

PINS = {'numpy':'2.3.5','pandas':'2.2.3','xarray':'2026.4.0','pint':'0.25.2',
        'h5py':'3.16.0','h5netcdf':'1.8.1','flexcache':'0.3','flexparser':'0.4',
        'platformdirs':'4.12.3','typing-extensions':'4.16.0','packaging':'26.3',
        'python-dateutil':'2.9.0.post0','pytz':'2026.5','tzdata':'2026.5','six':'1.17.0'}


def example():
    def summary(n=1): return {'sha256':'a'*64,'file_count':n,'size_bytes':n}
    return {'binding_version':1,'python':{'implementation':'cpython','version':'3.12.14',
        'build':['main','Aug 25 2026 14:00:49'],'compiler':'Clang 22.1.3 ',
        'abi':{'cache_tag':'cpython-312','soabi':'cpython-312-x86_64-linux-gnu','abiflags':'',
               'multiarch':'x86_64-linux-gnu','platform':'linux','machine':'x86_64',
               'pointer_bits':64,'byteorder':'little','debug':False,'gil_disabled':False,'optimization':0},
        'executable':{'sha256':'b'*64,'size_bytes':10},'core_libraries':{},'stdlib_code':summary()},
        'dependencies':{name:{'version':version,'payload':summary(),'metadata':summary(2)} for name,version in PINS.items()},
        'replicatetable':'0.1.0a1','resources':{'__init__.py':'c'*64},
        'pint':{'registry':'stock','default_unit_file':'default_en.txt',
                'resources':{'default_en.txt':'d'*64,'constants_en.txt':'e'*64}}}


class RuntimeSchemaTests(unittest.TestCase):
    def test_versioned_shape_is_deeply_immutable_and_roundtrips(self):
        original=example(); result=validate_runtime(original)
        self.assertEqual(thaw(result),original)
        original['python']['build'][0]='changed'
        self.assertEqual(result['python']['build'][0],'main')
        with self.assertRaises(TypeError): result['dependencies']['numpy']['version']='x'
        self.assertEqual(canonical_json(thaw(result)),canonical_json(example()))

    def assert_invalid(self,value):
        with self.assertRaises(Refusal) as caught: validate_runtime(value)
        self.assertEqual(caught.exception.code,'invalid_runtime')

    def test_all_mapping_levels_have_exact_fields_and_types(self):
        paths=[(),('python',),('python','abi'),('python','executable'),('python','stdlib_code'),
               ('dependencies',),('dependencies','numpy'),('dependencies','numpy','payload'),
               ('dependencies','numpy','metadata'),('pint',)]
        for path in paths:
            for mode in ('extra','missing','list'):
                value=example(); obj=value
                for key in path: obj=obj[key]
                if mode=='extra': obj['unknown']=1
                elif mode=='missing': obj.pop(next(iter(obj)))
                elif not path: value=[]
                else:
                    parent=value
                    for key in path[:-1]: parent=parent[key]
                    parent[path[-1]]=[]
                with self.subTest(path=path,mode=mode): self.assert_invalid(value)
        self.assert_invalid({'python':'3.12.14','dependencies':{},'replicatetable':'0.1.0a1','resources':{},'pint':{}})

    def test_exact_primitive_domains_and_private_text_refuse(self):
        cases=[(('binding_version',),True),(('binding_version',),2),
            (('python','implementation'),'pypy'),(('python','version'),'3.11.14'),
            (('python','build'),['main']), (('python','build'),['main','/private/build']),
            (('python','compiler'),'x\\y'),(('python','compiler'),'x\n'),(('python','compiler'),'é'*65),
            (('python','compiler'),'\ud800'),(('python','abi','pointer_bits'),True),
            (('python','abi','pointer_bits'),32),(('python','abi','platform'),'darwin'),
            (('python','abi','machine'),'aarch64'),(('python','abi','debug'),0),
            (('python','abi','debug'),True),(('python','abi','gil_disabled'),True),
            (('python','abi','optimization'),True),(('python','abi','optimization'),3),
            (('python','abi','cache_tag'),'cpython-313'),(('python','abi','soabi'),'wrong'),
            (('python','executable','sha256'),'A'*64),(('python','executable','size_bytes'),True),
            (('python','executable','size_bytes'),2**63),(('python','executable','size_bytes'),128*1024**2+1),
            (('dependencies','numpy','version'),'2.4.0'),(('dependencies','numpy','payload','file_count'),2049),
            (('dependencies','numpy','payload','file_count'),True),(('dependencies','numpy','payload','size_bytes'),-1),
            (('dependencies','numpy','metadata','file_count'),1)]
        for path,replacement in cases:
            value=example(); obj=value
            for key in path[:-1]: obj=obj[key]
            obj[path[-1]]=replacement
            with self.subTest(path=path,replacement=replacement): self.assert_invalid(value)

    def test_paths_maps_and_total_summary_bounds(self):
        for path in ('/private.py','../x.py','a//b.py','a/./b.py','a\\b.py','a\n.py','x.txt','x'*129+'.py'):
            value=example(); value['resources']={path:'a'*64}; self.assert_invalid(value)
        value=example(); value['python']['core_libraries']={'libpython'+str(i)+'.so':{'sha256':'a'*64,'size_bytes':1} for i in range(17)}; self.assert_invalid(value)
        value=example()
        for dep in value['dependencies'].values(): dep['payload']['file_count']=2048
        self.assert_invalid(value)
        value=example()
        for dep in value['dependencies'].values(): dep['payload']['size_bytes']=32*1024**2
        self.assert_invalid(value)
        value=example(); value['pint']['resources'].pop('constants_en.txt'); self.assert_invalid(value)

    def test_caps_are_checked_before_freezing(self):
        value=example(); value['resources']={f'{i}.py':'a'*64 for i in range(257)}
        with patch('replicatetable.runtime.freeze',side_effect=AssertionError('must not freeze')):
            self.assert_invalid(value)

class RuntimeInventoryTests(unittest.TestCase):
    def setUp(self):
        from replicatetable import runtime
        self.rt=runtime
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def put(self,name,content=b'abc'):
        path=self.root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(content); return path

    def scan(self,roots=('pkg',),kind='payload',budget=None,resource_map=False):
        return self.rt._inventory(str(self.root),roots,kind,budget or self.rt._ScanBudget(),resource_map=resource_map)

    def test_streamed_inventory_matches_canonical_json_and_sorted_unicode_names(self):
        self.put('pkg/z',b'last'); self.put('pkg/é.py',b'nonascii'); self.put('pkg/a',b'first')
        expected={name:{'sha256':hashlib.sha256(content).hexdigest(),'size_bytes':len(content)} for name,content in [('pkg/z',b'last'),('pkg/é.py',b'nonascii'),('pkg/a',b'first')]}
        result=self.scan()
        self.assertEqual(result,{'sha256':hashlib.sha256(canonical_json(expected)).hexdigest(),'file_count':3,'size_bytes':17})

    def test_relocation_exclusions_extras_and_restored_mtime_edits(self):
        import shutil
        file=self.put('pkg/native.so',b'old'); original=self.scan(); stat=file.stat()
        self.put('pkg/__pycache__/irrelevant.pyc'); self.put('pkg/other.pyc'); self.assertEqual(original,self.scan())
        copied=self.root/'relocated'; shutil.copytree(self.root/'pkg',copied/'pkg')
        self.assertEqual(original,self.rt._inventory(str(copied),('pkg',),'payload',self.rt._ScanBudget()))
        file.write_bytes(b'new'); os.utime(file,ns=(stat.st_atime_ns,stat.st_mtime_ns)); self.assertNotEqual(original,self.scan())
        self.put('pkg/unrecorded-resource',b'new'); self.assertEqual(self.scan()['file_count'],2)

    def test_hardlinks_have_two_occurrences_and_overlapping_roots_refuse(self):
        first=self.put('pkg/a',b'abc'); os.link(first,self.root/'pkg/b')
        budget=self.rt._ScanBudget(); result=self.scan(budget=budget)
        self.assertEqual((result['file_count'],result['size_bytes'],budget.files,budget.bytes),(2,6,2,6))
        for roots in (('pkg','pkg'),('pkg','pkg/a')):
            with self.assertRaises(Refusal) as caught: self.scan(roots)
            self.assertEqual(caught.exception.code,'runtime_identity_unavailable')

    def test_stdlib_and_metadata_selectors_are_explicit(self):
        names=['a.py','lib-dynload/x.so','lib-dynload/x.so.1','test/test_x.py','data.bin',
               'site-packages/x.py','dist-packages/x.py','config-abc/x.py','__pycache__/x.py','_sysconfigdata_a.py']
        for name in names: self.put('stdlib/'+name,b'x')
        result=self.scan(('stdlib',),'stdlib'); self.assertEqual(result['file_count'],4)
        for name in ['METADATA','WHEEL','entry_points.txt','top_level.txt','licenses/vendor/data',
                     'LiCeNsE.old','NOTICE.txt','COPYRIGHT','COPYING','RECORD','INSTALLER','REQUESTED','direct_url.json','cache/x']:
            self.put('metadata/'+name,b'x')
        result=self.rt._inventory(str(self.root/'metadata'),('',),'metadata',self.rt._ScanBudget()); self.assertEqual(result['file_count'],9)

    def test_required_roots_links_and_special_files_refuse_without_paths(self):
        self.put('pkg/a'); (self.root/'pkg/link').symlink_to(self.root/'pkg/a')
        for roots,code in [(('absent',),'runtime_artifact_missing'),(('pkg',),'runtime_identity_unavailable')]:
            with self.assertRaises(Refusal) as caught: self.scan(roots)
            self.assertEqual(caught.exception.code,code); self.assertNotIn(str(self.root),str(caught.exception))
        (self.root/'pkg/link').unlink(); os.mkfifo(self.root/'pkg/fifo')
        with self.assertRaises(Refusal) as caught: self.scan()
        self.assertEqual(caught.exception.code,'runtime_identity_unavailable')

    def test_file_and_total_bytes_preflight_before_read(self):
        self.put('pkg/a',b'abcd')
        for name,limit in [('FILE_BYTES_LIMIT',3),('BINDING_BYTES_LIMIT',3),('BINDING_FILES_LIMIT',0)]:
            with patch.object(self.rt,name,limit), patch.object(self.rt,'_hash_open_file',side_effect=AssertionError('must not read')):
                with self.assertRaises(Refusal) as caught: self.scan()
                self.assertEqual(caught.exception.code,'runtime_identity_limit')

    def test_incremental_file_directory_and_retained_name_caps(self):
        self.put('pkg/a'); self.put('pkg/dir/b')
        for name,limit in [('INVENTORY_FILES_LIMIT',1),('INVENTORY_DIRECTORIES_LIMIT',1),
                           ('BINDING_DIRECTORIES_LIMIT',1),('RETAINED_PATH_BYTES_LIMIT',4),('RELATIVE_PATH_BYTES_LIMIT',4)]:
            with patch.object(self.rt,name,limit):
                with self.assertRaises(Refusal) as caught: self.scan()
                self.assertEqual(caught.exception.code,'runtime_identity_limit')
        with patch.object(self.rt,'INVENTORY_FILES_LIMIT',2),patch.object(self.rt,'INVENTORY_DIRECTORIES_LIMIT',2):
            self.assertEqual(self.scan()['file_count'],2)

    def test_resource_maps_are_bounded_and_repeated_occurrences_are_charged(self):
        self.put('pkg/default_en.txt'); self.put('pkg/constants_en.txt')
        budget=self.rt._ScanBudget(); self.scan(budget=budget)
        result=self.rt._inventory(str(self.root/'pkg'),('',),'pint',budget,resource_map=True)
        self.assertEqual(set(result),{'default_en.txt','constants_en.txt'})
        self.assertEqual((budget.files,budget.bytes),(4,12))
        with patch.object(self.rt,'RESOURCE_FILES_LIMIT',1):
            with self.assertRaises(Refusal) as caught: self.scan(resource_map=True)
            self.assertEqual(caught.exception.code,'runtime_identity_limit')

    def test_streaming_uses_one_readinto_buffer_and_rejects_unstable_descriptor(self):
        import io
        budget=self.rt._ScanBudget()
        class Reader(io.BytesIO):
            calls=[]
            def read(self,*args): raise AssertionError('no full read')
            def readinto(self,b): self.calls.append((id(b),len(b))); return super().readinto(b)
        reader=Reader(b'x'*(65536+7))
        result=self.rt._hash_open_file(reader,65536+7,budget)
        self.assertEqual(result['sha256'],hashlib.sha256(b'x'*(65536+7)).hexdigest())
        self.assertEqual(set(reader.calls),{(id(budget.buffer),65536)})
        self.put('pkg/a')
        original=self.rt._hash_open_file
        def change(stream,size,budget):
            result=original(stream,size,budget); (self.root/'pkg/a').write_bytes(b'xyz'); return result
        with patch.object(self.rt,'_hash_open_file',side_effect=change):
            with self.assertRaises(Refusal) as caught: self.scan()
            self.assertEqual(caught.exception.code,'runtime_changed')

class RuntimeDiscoveryTests(unittest.TestCase):
    def setUp(self):
        from replicatetable import runtime
        self.rt=runtime

    def test_wrong_expected_binding_does_not_poison_actual_process(self):
        actual=example(); wrong=copy.deepcopy(actual); wrong['python']['executable']['sha256']='f'*64
        with patch.object(self.rt,'_discover_runtime',return_value=actual),patch.object(self.rt,'_PROCESS_BINDING',None),patch.object(self.rt,'_PROCESS_CHANGED',False):
            self.assertEqual(thaw(self.rt.runtime_identity()),actual)
            with self.assertRaises(Refusal) as caught: self.rt.require_runtime(wrong)
            self.assertEqual(caught.exception.code,'runtime_binding_mismatch')
            self.assertEqual(thaw(self.rt.require_runtime(actual)),actual)

    def test_live_change_is_terminal_even_if_files_are_restored(self):
        actual=example(); changed=copy.deepcopy(actual); changed['resources']['__init__.py']='f'*64
        with patch.object(self.rt,'_discover_runtime',side_effect=[actual,changed,actual]) as discover,patch.object(self.rt,'_PROCESS_BINDING',None),patch.object(self.rt,'_PROCESS_CHANGED',False):
            self.rt.runtime_identity()
            for _ in range(2):
                with self.assertRaises(Refusal) as caught: self.rt.runtime_identity()
                self.assertEqual(caught.exception.code,'runtime_changed')
            self.assertEqual(discover.call_count,2)

    def test_top_level_and_loaded_submodule_shadow_origins_refuse(self):
        import numpy,sys,types
        origin=numpy.__spec__.origin
        with patch.object(numpy.__spec__,'origin','/private/shadow/numpy/__init__.py'):
            with self.assertRaises(Refusal) as caught: self.rt._verify_module('numpy',os.path.dirname(origin))
            self.assertEqual(caught.exception.code,'runtime_import_origin_mismatch')
            self.assertNotIn('/private/',str(caught.exception))
        module=types.ModuleType('numpy.shadow'); module.__file__='/private/shadow.py'
        module.__spec__=__import__('importlib').machinery.ModuleSpec('numpy.shadow',loader=None,origin=module.__file__)
        with patch.dict(sys.modules,{'numpy.shadow':module}):
            with self.assertRaises(Refusal) as caught: self.rt._verify_module('numpy',os.path.dirname(origin))
            self.assertEqual(caught.exception.code,'runtime_import_origin_mismatch')

    def test_metadata_headers_are_bounded_exact_and_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'METADATA').write_bytes(b'Metadata-Version: 2.4\nName: NumPy\nVersion: 2.3.5\n\ntext')
            self.assertEqual(self.rt._metadata_identity(directory),('numpy','2.3.5'))
            for data in (b'Name: numpy\nVersion: 2.4.0\nName: other\n\n', b'Name: numpy\n\n', b'x'*8193):
                (root/'METADATA').write_bytes(data)
                with self.assertRaises(Refusal): self.rt._metadata_identity(directory)
            (root/'METADATA').unlink()
            with self.assertRaises(Refusal) as caught: self.rt._metadata_identity(directory)
            self.assertEqual(caught.exception.code,'runtime_artifact_missing')

class RuntimeRefinementTests(unittest.TestCase):
    def setUp(self):
        from replicatetable import runtime
        self.rt=runtime

    def test_c1_controls_refuse_and_metadata_special_names_are_root_only(self):
        value=example(); value['python']['compiler']='compiler\x85'
        with self.assertRaises(Refusal): validate_runtime(value)
        self.assertFalse(self.rt._selected_file('generated/METADATA','metadata'))
        self.assertTrue(self.rt._selected_file('licenses/vendor/data','metadata'))
        self.assertTrue(self.rt._selected_file('old/NOTICE.txt','metadata'))

    def test_missing_artifact_after_initial_binding_requires_restart(self):
        with patch.object(self.rt,'_discover_runtime',side_effect=[example(),Refusal('runtime_artifact_missing','missing'),example()]),patch.object(self.rt,'_PROCESS_BINDING',None),patch.object(self.rt,'_PROCESS_CHANGED',False):
            self.rt.runtime_identity()
            with self.assertRaises(Refusal): self.rt.runtime_identity()
            with self.assertRaises(Refusal) as caught: self.rt.runtime_identity()
            self.assertEqual(caught.exception.code,'runtime_changed')

    def test_stdlib_shadow_is_rejected_and_stock_generated_aliases_qualify(self):
        import json,sysconfig
        root=os.path.realpath(sysconfig.get_path('stdlib'))
        self.rt._verify_stdlib(root)
        with patch.object(json.__spec__,'origin','/private/json.py'):
            with self.assertRaises(Refusal) as caught: self.rt._verify_stdlib(root)
            self.assertEqual(caught.exception.code,'runtime_import_origin_mismatch')

    def test_stock_six_moves_is_the_only_accepted_originless_six_namespace(self):
        import six,sys,types
        self.rt._verify_module('six',os.path.realpath(six.__file__))
        fake=types.ModuleType('six.moves'); fake.__loader__=six.moves.__loader__
        with patch.dict(sys.modules,{'six.moves':fake}):
            with self.assertRaises(Refusal) as caught: self.rt._verify_module('six',os.path.realpath(six.__file__))
            self.assertEqual(caught.exception.code,'runtime_import_origin_mismatch')

class RuntimeAnchoringTests(unittest.TestCase):
    def test_scandir_uses_anchored_directory_descriptor(self):
        from replicatetable import runtime
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'pkg').mkdir(); (root/'pkg'/'x.py').write_bytes(b'x')
            scan=os.scandir; seen=[]
            def anchored(fd):
                self.assertIs(type(fd),int); seen.append(fd); return scan(fd)
            with patch.object(runtime.os,'scandir',side_effect=anchored):
                result=runtime._inventory(directory,('pkg',),'payload',runtime._ScanBudget())
            self.assertEqual(result['file_count'],1); self.assertTrue(seen)

class RuntimeFinalBoundaryTests(unittest.TestCase):
    def test_explicitly_excluded_sysconfig_symlink_is_ignored(self):
        from replicatetable import runtime
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'os.py').write_bytes(b'pass\n')
            (root/'_sysconfigdata_vendor.py').symlink_to(root/'absent')
            result=runtime._inventory(directory,('',),'stdlib',runtime._ScanBudget())
            self.assertEqual(result['file_count'],1)
            (root/'sitecustomize.py').symlink_to(root/'os.py')
            with self.assertRaises(Refusal) as caught: runtime._inventory(directory,('',),'stdlib',runtime._ScanBudget())
            self.assertEqual(caught.exception.code,'runtime_identity_unavailable')

    def test_originless_top_level_refuses_without_filesystem_type_error(self):
        from replicatetable import runtime
        import numpy
        with patch.object(numpy,'__spec__',None),patch.object(numpy,'__file__',None):
            with self.assertRaises(Refusal) as caught: runtime._verify_module('numpy','/missing/numpy')
            self.assertEqual(caught.exception.code,'runtime_import_origin_mismatch')

    def test_metadata_only_installer_changes_are_invariant_and_stable_changes_bind(self):
        from replicatetable import runtime
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('METADATA','WHEEL','LICENSE','entry_points.txt'): (root/name).write_bytes(b'old')
            def scan(): return runtime._inventory(directory,('',),'metadata',runtime._ScanBudget())
            before=scan()
            for name in ('RECORD','INSTALLER','REQUESTED','direct_url.json'): (root/name).write_bytes(b'/private/installer')
            self.assertEqual(before,scan())
            (root/'LICENSE').write_bytes(b'new'); self.assertNotEqual(before,scan())

    def test_selected_python_and_pint_definition_edits_change_identity(self):
        from replicatetable import runtime
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('os.py','default_en.txt','constants_en.txt'): (root/name).write_bytes(b'old')
            def scan(kind): return runtime._inventory(directory,('',),kind,runtime._ScanBudget())
            stdlib,pint=scan('stdlib'),scan('pint')
            (root/'os.py').write_bytes(b'new'); self.assertNotEqual(stdlib,scan('stdlib'))
            (root/'constants_en.txt').write_bytes(b'new'); self.assertNotEqual(pint,scan('pint'))

class RuntimeMetadataPreflightTests(unittest.TestCase):
    def test_oversized_identity_header_is_rejected_before_next_line(self):
        from replicatetable import runtime
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'METADATA').write_bytes(b'Name: '+b'x'*4000+b'\nVersion: 2.3.5\n\n')
            calls=[]; original=os.fdopen
            def instrument(*args,**kwargs):
                stream=original(*args,**kwargs); readline=stream.readline
                def counted(*args): calls.append(1); return readline(*args)
                stream.readline=counted
                return stream
            with patch.object(runtime.os,'fdopen',side_effect=instrument):
                with self.assertRaises(Refusal): runtime._metadata_identity(directory)
            self.assertEqual(len(calls),1)

class RuntimeCoreLibraryTests(unittest.TestCase):
    def core(self,paths,budget=None):
        import io,builtins
        from replicatetable import runtime
        lines=[]
        for index,path in enumerate(paths):
            st=path.stat()
            lines.append(f'{index+1:08x}-{index+2:08x} r-xp 00000000 {os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x} {st.st_ino} {path}\n'.encode())
        original=builtins.open
        def opened(path,*args,**kwargs):
            return io.BytesIO(b''.join(lines)) if path=='/proc/self/maps' else original(path,*args,**kwargs)
        with patch('builtins.open',side_effect=opened):
            return runtime._core_libraries(budget or runtime._ScanBudget())

    def test_repeated_mapping_segments_charge_one_image_and_alias_basenames_refuse(self):
        from replicatetable import runtime
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); first=root/'libpythonZ.so'; first.write_bytes(b'abc')
            second=root/'libpythonA.so'; os.link(first,second)
            budget=runtime._ScanBudget(); result=self.core([first,first],budget)
            self.assertEqual(list(result),['libpythonZ.so'])
            self.assertEqual((budget.files,budget.bytes),(1,3))
            self.assertEqual(result['libpythonZ.so']['sha256'],hashlib.sha256(b'abc').hexdigest())
            with self.assertRaises(Refusal) as caught: self.core([first,first,second])
            self.assertEqual(caught.exception.code,'runtime_identity_unavailable')

    def test_competing_images_with_same_basename_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            paths=[]
            for dirname in ('one','two'):
                path=Path(directory)/dirname/'libpython.so'; path.parent.mkdir(); path.write_bytes(dirname.encode()); paths.append(path)
            with self.assertRaises(Refusal) as caught: self.core(paths)
            self.assertEqual(caught.exception.code,'runtime_identity_unavailable')

class RuntimeTypingAliasTests(unittest.TestCase):
    def test_typing_generated_alias_requires_exact_stock_type_and_owner_source(self):
        import typing,types,sys,sysconfig
        from replicatetable import runtime
        root=os.path.realpath(sysconfig.get_path('stdlib'))
        runtime._verify_stdlib(root)
        fake=types.ModuleType('typing.io')
        with patch.object(typing,'io',fake,create=True),patch.dict(sys.modules,{'typing.io':fake}):
            with self.assertRaises(Refusal) as caught: runtime._verify_stdlib(root)
            self.assertEqual(caught.exception.code,'runtime_import_origin_mismatch')
        with patch.object(typing.__spec__,'origin','/private/shadow/typing.py'):
            with self.assertRaises(Refusal) as caught: runtime._verify_stdlib(root)
            self.assertEqual(caught.exception.code,'runtime_import_origin_mismatch')

class RuntimeRestartLatchReviewTests(unittest.TestCase):
    def test_actual_discovery_refusals_latch_after_qualified_baseline(self):
        from replicatetable import runtime
        for case,code in (('symlink','runtime_identity_unavailable'),('selected_files_cap','runtime_identity_limit')):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as directory:
                root=Path(directory); file=root/'module.py'; file.write_bytes(b'pass\n')
                def discover():
                    actual=example()
                    actual['resources']=runtime._inventory(str(root),('',),'product',runtime._ScanBudget(),resource_map=True)
                    return actual
                with patch.object(runtime,'_discover_runtime',side_effect=discover) as scan,patch.object(runtime,'_PROCESS_BINDING',None),patch.object(runtime,'_PROCESS_CHANGED',False),patch.object(runtime,'INVENTORY_FILES_LIMIT',2):
                    runtime.runtime_identity()
                    if case=='symlink': file.unlink(); file.symlink_to(root/'absent')
                    else:
                        (root/'extra1.py').write_bytes(b'pass\n'); (root/'extra2.py').write_bytes(b'pass\n')
                    with self.assertRaises(Refusal) as caught: runtime.runtime_identity()
                    self.assertEqual(caught.exception.code,code)
                    self.assertTrue(runtime._PROCESS_CHANGED)
                    if case=='symlink': file.unlink(); file.write_bytes(b'pass\n')
                    else: (root/'extra1.py').unlink(); (root/'extra2.py').unlink()
                    scans=scan.call_count
                    with self.assertRaises(Refusal) as caught: runtime.runtime_identity()
                    self.assertEqual(caught.exception.code,'runtime_changed')
                    self.assertEqual(scan.call_count,scans)

    def test_caller_expected_failures_never_enter_actual_failure_latch(self):
        from replicatetable import runtime
        with patch.object(runtime,'_discover_runtime',return_value=example()) as scan,patch.object(runtime,'_PROCESS_BINDING',None),patch.object(runtime,'_PROCESS_CHANGED',False):
            actual=runtime.runtime_identity(); malformed=example(); malformed.pop('binding_version')
            scans=scan.call_count
            with self.assertRaises(Refusal) as caught: runtime.require_runtime(malformed)
            self.assertEqual(caught.exception.code,'invalid_runtime'); self.assertEqual(scan.call_count,scans)
            wrong=example(); wrong['python']['executable']['sha256']='f'*64
            with self.assertRaises(Refusal) as caught: runtime.require_runtime(wrong)
            self.assertEqual(caught.exception.code,'runtime_binding_mismatch')
            self.assertFalse(runtime._PROCESS_CHANGED)
            self.assertEqual(runtime.require_runtime(actual),actual)

    def test_prebaseline_discovery_refusal_preserves_existing_retry_rule(self):
        from replicatetable import runtime
        with patch.object(runtime,'_discover_runtime',side_effect=[Refusal('runtime_identity_unavailable','unavailable'),example()]),patch.object(runtime,'_PROCESS_BINDING',None),patch.object(runtime,'_PROCESS_CHANGED',False):
            with self.assertRaises(Refusal) as caught: runtime.runtime_identity()
            self.assertEqual(caught.exception.code,'runtime_identity_unavailable')
            self.assertFalse(runtime._PROCESS_CHANGED)
            self.assertEqual(thaw(runtime.runtime_identity()),example())
        with patch.object(runtime,'_discover_runtime',side_effect=Refusal('runtime_changed','unstable')),patch.object(runtime,'_PROCESS_BINDING',None),patch.object(runtime,'_PROCESS_CHANGED',False):
            with self.assertRaises(Refusal): runtime.runtime_identity()
            self.assertTrue(runtime._PROCESS_CHANGED)
