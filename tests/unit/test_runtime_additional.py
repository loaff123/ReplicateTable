"""Additional bounded runtime controls; these are not whole-journey evidence."""
from contextlib import contextmanager
import copy
import gc
import hashlib
import importlib.machinery
import io
import json
import os
from pathlib import Path
import sys
import sysconfig
import tempfile
import tracemalloc
import types
import unittest
from unittest.mock import patch

from replicatetable import runtime as rt
from replicatetable.codec import OwnedMap, canonical_bytes, freeze, preflight_json
from replicatetable.errors import Refusal
from tests.unit.test_runtime_binding import example
from tests.unit.test_runtime_repairs import RuntimeFixture
from tests.unit import test_runtime_repairs as repair_fixtures


class RuntimeAdditionalOrigins(RuntimeFixture):
    def test_dependency_custom_source_suffix_is_unqualified_even_if_payload_bound(self):
        owner=repair_fixtures.RuntimeOriginRepairs.module(self,'fixture_runtime',self.put('__init__.py'),True)
        child=repair_fixtures.RuntimeOriginRepairs.module(self,'fixture_runtime.child',self.put('custom.txt'))
        with patch.dict(sys.modules,{'fixture_runtime':owner,'fixture_runtime.child':child}):
            self.assert_code('runtime_import_origin_mismatch',rt._verify_module,'fixture_runtime',str(self.root))

    def test_stock_frozen_alias_must_be_identical_to_registered_owner(self):
        import importlib._bootstrap
        stock=importlib._bootstrap
        self.assertTrue(rt._stock_interpreter_module('importlib._bootstrap',stock))
        fake=types.ModuleType('importlib._bootstrap'); fake.__spec__=stock.__spec__; fake.__loader__=stock.__loader__
        self.assertFalse(rt._stock_interpreter_module('importlib._bootstrap',fake))
        with patch.dict(sys.modules,{'importlib._bootstrap':fake}):
            self.assert_code('runtime_import_origin_mismatch',rt._verify_stdlib,os.path.realpath(sysconfig.get_path('stdlib')))

    def test_six_moves_loader_and_owner_and_child_prefix_are_exact(self):
        import six,importlib
        importlib.import_module('six.moves')
        root=os.path.realpath(six.__file__)
        rt._verify_module('six',root)
        with patch.object(six.moves,'__loader__',None):
            self.assert_code('runtime_import_origin_mismatch',rt._verify_module,'six',root)
        fake=types.ModuleType('six.moves.fake'); fake.__spec__=importlib.machinery.ModuleSpec(fake.__name__,None)
        with patch.dict(sys.modules,{fake.__name__:fake}):
            self.assert_code('runtime_import_origin_mismatch',rt._verify_module,'six',root)
        with patch.object(six,'__path__',['/outside']):
            self.assert_code('runtime_import_origin_mismatch',rt._verify_module,'six',root)

    def test_symlink_root_ancestor_and_disappeared_selected_file_refuse(self):
        self.put('pkg/dir/x.py')
        (self.root/'alias').symlink_to(self.root/'pkg',target_is_directory=True)
        self.assert_code('runtime_identity_unavailable',rt._inventory,str(self.root),('alias',),'payload',rt._ScanBudget())
        self.assert_code('runtime_identity_unavailable',rt._inventory,str(self.root),('alias/dir',),'payload',rt._ScanBudget())
        original=rt._hash_relative
        def removed(root,name,budget):
            (Path(root)/name).unlink()
            return original(root,name,budget)
        with patch.object(rt,'_hash_relative',side_effect=removed):
            self.assert_code('runtime_changed',rt._inventory,str(self.root),('pkg',),'payload',rt._ScanBudget())


class RuntimeAdditionalMetadata(RuntimeFixture):
    def read(self,data):
        self.put('METADATA',data)
        return rt._metadata_identity(str(self.root))

    def test_header_raw_line_and_total_exact_boundaries(self):
        prefix=b'Name: NumPy\nVersion: 2.3.5\n'
        self.assertEqual(self.read(prefix+b'X'+b'a'*4094+b'\n\n'),('numpy','2.3.5'))
        self.assert_code('runtime_identity_limit',self.read,prefix+b'X'+b'a'*4095+b'\n\n')
        remaining=131072-len(prefix)-1
        body=(b'X'+b'a'*4094+b'\n')*(remaining//4096)
        tail=remaining%4096
        if tail: body+=b'X'+b'a'*(tail-2)+b'\n'
        self.assertEqual(len(prefix+body+b'\n'),131072)
        self.assertEqual(self.read(prefix+body+b'\n'),('numpy','2.3.5'))
        self.assert_code('runtime_identity_limit',self.read,prefix+body+b' \n')

    def test_metadata_only_bounded_line_reads_stop_at_header_terminator(self):
        data=b'Name: NumPy\r\nVersion: 2.3.5\r\n\r\n'+b'z'*32768
        self.put('METADATA',data); original=os.fdopen; calls=[]
        def wrapped(*a,**kw):
            stream=original(*a,**kw); readline=stream.readline
            def read(size):
                part=readline(size); calls.append((size,len(part))); return part
            stream.readline=read; return stream
        with patch.object(rt.os,'fdopen',side_effect=wrapped):
            self.assertEqual(rt._metadata_identity(str(self.root)),('numpy','2.3.5'))
        self.assertEqual(len(calls),3)
        self.assertEqual(sum(size for _,size in calls),len(data)-32768)
        self.assertEqual({request for request,_ in calls},{4097})

    def test_metadata_trimmed_identity_and_missing_duplicate_nonascii_cases(self):
        for bad in [b'Name: \nVersion: 2.3.5\n\n',b'Name: '+b'x'*129+b'\nVersion: 2.3.5\n\n',
                    b'Name: n\xff\nVersion: 2.3.5\n\n',b'Name: n\nVersion: 1\nVersion: 1\n\n',b'Version: 1\n\n']:
            self.assert_code('runtime_identity_unavailable',self.read,bad)
        self.assertEqual(self.read(b'Name: A_B.C\nVersion: '+b'1'*128+b'\n\n'),('a-b-c','1'*128))
        (self.root/'METADATA').unlink(); target=self.put('safe',b'Name: n\nVersion: 1\n\n')
        (self.root/'METADATA').symlink_to(target)
        self.assert_code('runtime_identity_unavailable',rt._metadata_identity,str(self.root))

    def test_metadata_fd_is_closed_on_fifo_and_parse_refusal(self):
        # Linux descriptor count is finite test instrumentation, not production
        # heap/state inspection or a process-memory attestation.
        before=len(os.listdir('/proc/self/fd'))
        os.mkfifo(self.root/'METADATA')
        self.assert_code('runtime_identity_unavailable',rt._metadata_identity,str(self.root))
        self.assertEqual(len(os.listdir('/proc/self/fd')),before)
        (self.root/'METADATA').unlink()
        self.assert_code('runtime_identity_unavailable',self.read,b'Name: n\n\n')
        self.assertEqual(len(os.listdir('/proc/self/fd')),before)


class RuntimeAdditionalCaps(RuntimeFixture):
    def test_whole_binding_scalar_equalities_and_plus_one_preincrement(self):
        budget=rt._ScanBudget()
        for _ in range(8192): budget.file()
        self.assert_code('runtime_identity_limit',budget.file)
        self.assertEqual(budget.files,8192)
        for _ in range(4096): budget.directory()
        self.assert_code('runtime_identity_limit',budget.directory)
        self.assertEqual(budget.directories,4096)
        budget.payload(128*1024**2); budget.payload(128*1024**2)
        self.assertEqual(budget.bytes,256*1024**2)
        self.assert_code('runtime_identity_limit',budget.payload,1)
        self.assertEqual(budget.bytes,256*1024**2)
        self.assert_code('runtime_identity_limit',rt._ScanBudget().payload,128*1024**2+1)

    def test_actual_inventory_files_names_retained_equality_and_plus_one(self):
        # 2048 * 64 UTF-8 bytes = the entire retained-name cap. Actual benign
        # names/files, not a scalar seam; this is still not whole-import RSS.
        for i in range(2048): self.put(f'{i:04}_'+('x'*59),b'')
        budget=rt._ScanBudget(); gc.collect(); tracemalloc.start()
        result=rt._inventory(str(self.root),('',),'payload',budget)
        current,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
        self.assertEqual((result['file_count'],budget.files,budget.bytes),(2048,2048,0))
        self.assertLess(peak+rt.HASH_BUFFER_BYTES,rt.SCANNER_SCRATCH_BOUND)
        self.put('extra',b'')
        with patch.object(rt,'_hash_open_file',side_effect=AssertionError('hash started')):
            self.assert_code('runtime_identity_limit',self.scan,'payload')
        (self.root/'extra').unlink()
        old=self.root/('0000_'+('x'*59)); old.rename(self.root/('0000_'+('x'*60)))
        self.assert_code('runtime_identity_limit',self.scan,'payload')

    def test_actual_directory_and_relative_name_equalities(self):
        # Root visit + 511 child directories is exactly 512.
        for i in range(511): (self.root/f'd{i}').mkdir()
        self.assertEqual(self.scan('payload')['file_count'],0)
        (self.root/'one_more').mkdir()
        self.assert_code('runtime_identity_limit',self.scan,'payload')
        with tempfile.TemporaryDirectory() as other:
            root=Path(other); (root/('x'*128)).write_bytes(b'a')
            self.assertEqual(rt._inventory(other,('',),'payload',rt._ScanBudget())['file_count'],1)
            (root/('y'*129)).write_bytes(b'a')
            self.assert_code('runtime_identity_limit',rt._inventory,other,('',),'payload',rt._ScanBudget())

    def test_real_resource_map_equality_and_plus_one(self):
        for i in range(256): self.put(f'{i}.py')
        def scan(): return rt._inventory(str(self.root),('',),'product',rt._ScanBudget(),resource_map=True)
        self.assertEqual(len(scan()),256)
        self.put('extra.py')
        with patch.object(rt,'_hash_open_file',side_effect=AssertionError('hash started')):
            self.assert_code('runtime_identity_limit',scan)

    def test_inventory_and_directory_frames_release_before_next_scan(self):
        self.put('a/x.py'); self.put('b/y.py'); original=rt._directory
        active=0; peak=0; stages=[]
        @contextmanager
        def directory(*args):
            nonlocal active,peak
            active+=1; peak=max(active,peak)
            try:
                with original(*args) as entries: yield entries
            finally: active-=1
        original_hash=rt._hash_relative
        def hashed(*args):
            self.assertEqual(active,0)
            return original_hash(*args)
        with patch.object(rt,'_directory',side_effect=directory),patch.object(rt,'_hash_relative',side_effect=hashed):
            first=rt._inventory(str(self.root),('a',),'payload',rt._ScanBudget())
            self.assertEqual(active,0)
            # The prior result is only the compact summary. No file-name list,
            # iterator, descriptor or inventory generator escapes its frame.
            self.assertEqual(set(first),{'sha256','file_count','size_bytes'})
            second=rt._inventory(str(self.root),('b',),'payload',rt._ScanBudget())
        self.assertEqual((active,peak),(0,1))
        self.assertEqual(first['file_count'],second['file_count'])


class RuntimeAdditionalLatch(RuntimeFixture):
    def test_every_actual_refusal_preserves_first_code_and_latches_after_witness(self):
        codes=['runtime_dependency_missing','runtime_dependency_mismatch','runtime_artifact_missing',
               'runtime_import_origin_mismatch','runtime_identity_unavailable','runtime_identity_limit',
               'runtime_changed','invalid_runtime','metadata_bytes_limit']
        for code in codes:
            with self.subTest(code=code),patch.object(rt,'_PROCESS_BINDING',None),patch.object(rt,'_PROCESS_CHANGED',False),\
                 patch.object(rt,'_discover_runtime',side_effect=[example(),Refusal(code),example()]) as scan:
                baseline=rt.runtime_identity()
                self.assertIs(type(baseline),OwnedMap)
                self.assert_code(code,rt.runtime_identity)
                self.assertTrue(rt._PROCESS_CHANGED)
                self.assert_code('runtime_changed',rt.runtime_identity)
                self.assertEqual(scan.call_count,2)

    def test_prebaseline_retry_and_wrong_owned_expectations_do_not_latch(self):
        for code in ['runtime_dependency_missing','runtime_dependency_mismatch','runtime_artifact_missing',
                     'runtime_import_origin_mismatch','runtime_identity_unavailable','runtime_identity_limit']:
            with self.subTest(code=code),patch.object(rt,'_PROCESS_BINDING',None),patch.object(rt,'_PROCESS_CHANGED',False),\
                 patch.object(rt,'_discover_runtime',side_effect=[Refusal(code),example(),example(),example()]):
                self.assert_code(code,rt.runtime_identity)
                self.assertFalse(rt._PROCESS_CHANGED)
                good=rt.runtime_identity(); bad=example(); bad['python']['executable']['sha256']='f'*64
                self.assert_code('runtime_binding_mismatch',rt.require_runtime,freeze(bad))
                self.assertFalse(rt._PROCESS_CHANGED)
                self.assertEqual(rt.require_runtime(good),good)

    def test_bad_expected_types_never_scan_or_change_existing_witness(self):
        for bad in [None,[],{},True,types.MappingProxyType(example())]:
            with patch.object(rt,'_PROCESS_BINDING',freeze(example())),patch.object(rt,'_PROCESS_CHANGED',False),\
                 patch.object(rt,'_discover_runtime',side_effect=AssertionError('scan started')):
                self.assert_code('invalid_runtime',rt.require_runtime,bad)
                self.assertFalse(rt._PROCESS_CHANGED)


class RuntimeAdditionalCore(RuntimeFixture):
    def run_core(self,raw,budget=None):
        import builtins
        original=builtins.open
        def opened(path,*a,**kw): return io.BytesIO(raw) if path=='/proc/self/maps' else original(path,*a,**kw)
        with patch('builtins.open',side_effect=opened): return rt._core_libraries(budget or rt._ScanBudget())

    def line(self,path,device=None,inode=None):
        st=path.stat(); device=device or f'{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}'
        return f'1000-2000 r-xp 0000 {device} {st.st_ino if inode is None else inode} {path}\n'.encode()

    def test_nonempty_synthetic_core_membership_limit_and_hashes(self):
        files=[self.put(f'libpython{i:02}.so',f'image{i}'.encode()) for i in range(17)]
        budget=rt._ScanBudget(); result=self.run_core(b''.join(self.line(p) for p in files[:16]),budget)
        self.assertEqual((len(result),budget.files),(16,16))
        self.assertEqual(result[files[0].name],{'sha256':hashlib.sha256(b'image0').hexdigest(),'size_bytes':6})
        self.assert_code('runtime_identity_limit',self.run_core,b''.join(self.line(p) for p in files))
        self.assertNotIn(str(self.root),canonical_bytes(result).decode())

    def test_stale_nonregular_mismatched_and_symlink_core_refuse(self):
        p=self.put('libpython.so'); raw=self.line(p)
        self.assert_code('runtime_identity_unavailable',self.run_core,self.line(p,inode=p.stat().st_ino+1))
        p.unlink(); self.assert_code('runtime_identity_unavailable',self.run_core,raw)
        target=self.put('target'); p.symlink_to(target)
        self.assert_code('runtime_identity_unavailable',self.run_core,self.line(p))
        p.unlink(); p.mkdir()
        self.assert_code('runtime_identity_unavailable',self.run_core,self.line(p))

    def test_proc_map_line_and_total_limits_and_payload_preflight(self):
        self.assertEqual(self.run_core(b'x'*8191+b'\n'),{})
        self.assert_code('runtime_identity_limit',self.run_core,b'x'*8192+b'\n')
        self.assertEqual(self.run_core((b'x'*8191+b'\n')*128),{})
        self.assert_code('runtime_identity_limit',self.run_core,(b'x'*8191+b'\n')*128+b'x\n')
        p=self.put('libpython.so',b'abcd')
        with patch.object(rt,'FILE_BYTES_LIMIT',3),patch.object(rt,'_hash_open_file',side_effect=AssertionError('read started')):
            self.assert_code('runtime_identity_limit',self.run_core,self.line(p))

    def test_core_content_change_preserves_specific_refusal(self):
        path=self.put('libpython.so',b'old'); raw=self.line(path); original=rt._hash_open_file
        def changed(stream,size,budget):
            result=original(stream,size,budget); path.write_bytes(b'new'); return result
        with patch.object(rt,'_hash_open_file',side_effect=changed):
            self.assert_code('runtime_changed',self.run_core,raw)

    def test_actual_executable_is_kernel_image_not_sys_executable(self):
        h=hashlib.sha256(); size=0
        with open('/proc/self/exe','rb') as stream:
            while data:=stream.read(65536): h.update(data); size+=len(data)
        budget=rt._ScanBudget()
        with patch.object(sys,'executable','/private/not-the-kernel-image'):
            result=rt._executable(budget)
        self.assertEqual(result,{'sha256':h.hexdigest(),'size_bytes':size})
        self.assertEqual((budget.files,budget.bytes),(1,size))
