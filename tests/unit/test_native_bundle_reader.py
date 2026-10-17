"""Genuine anchored external bundle acquisition, not semantic bundle validity."""
import errno
import fcntl
import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from replicatetable import _native_fs_profile as profile
from replicatetable._native_budget_state import _CancellationState, LogicalOnlyBudget
from replicatetable.errors import Refusal

ROOTS=('plan.json','recipe.json','report.html','result.json','schema.json','table.csv','manifest.json')

class ExistingBundleReaderTests(unittest.TestCase):
    def setUp(self):
        self.m=importlib.import_module('replicatetable._native_bundle_reader')
        for name in ('_BundleReader','_open_bundle_reader','_open_bundle_member','_read_bundle_chunk',
                     '_close_bundle_member','_recheck_bundle_reader','_close_bundle_reader'):
            self.assertTrue(callable(getattr(self.m,name,None)),'Missing genuine reader: '+name)
        if not profile._PROFILE_SUPPORTED:self.skipTest('Exact Linux6.18.44 tmpfs profile required')
        temporary=tempfile.TemporaryDirectory(prefix='rt-existing-bundle-',dir='/tmp')
        self.addCleanup(temporary.cleanup);self.parent=Path(temporary.name);self.directory=self.parent/'bundle'
        self.directory.mkdir()
        for name in ROOTS:(self.directory/name).write_bytes((name+'\n').encode())
        self.cancel=_CancellationState();self.budget=LogicalOnlyBudget(self.cancel)

    def reader(self):
        value=self.m._open_bundle_reader(self.directory,self.budget)
        self.addCleanup(self.m._close_bundle_reader,value,quiet=True);return value
    def refused(self,code,function,*args):
        with self.assertRaises(Refusal) as caught:function(*args)
        self.assertEqual(caught.exception.code,code);return caught.exception
    def contents(self,reader,path):
        self.m._open_bundle_member(reader,path,self.budget);parts=[]
        try:
            while data:=self.m._read_bundle_chunk(reader,7,self.budget):parts.append(data)
        finally:self.m._close_bundle_member(reader)
        return b''.join(parts)

    def test_real_original_directory_and_readonly_members(self):
        reader=self.reader();before=os.stat(self.directory)
        self.assertEqual(reader.directory_witness.inode,before.st_ino)
        self.assertEqual(set(e.path for e in reader.entries),set(ROOTS))
        self.assertEqual(reader.total_bytes,sum((self.directory/x).stat().st_size for x in ROOTS))
        self.m._open_bundle_member(reader,'result.json',self.budget)
        self.assertEqual(fcntl.fcntl(reader.current_fd,fcntl.F_GETFL)&os.O_ACCMODE,os.O_RDONLY)
        self.m._close_bundle_member(reader)
        self.assertEqual(self.contents(reader,'result.json'),b'result.json\n')
        self.m._recheck_bundle_reader(reader,self.budget)

    def test_every_fixed_support_pair_and136_entry_maximum(self):
        (self.directory/'support').mkdir()
        for column in range(32):
            for stage in range(2):
                for suffix in ('.csv','.schema.json'):
                    (self.directory/'support'/f'c{column:02d}-s{stage:02d}{suffix}').write_bytes(b'x')
        reader=self.reader();self.assertEqual(len(reader.entries),136)
        self.assertEqual(self.contents(reader,'support/c31-s01.csv'),b'x')
        self.assertEqual(self.contents(reader,'support/c31-s01.schema.json'),b'x')

    def test_missing_extra_wrongkind_and_unpaired_members_refuse(self):
        (self.directory/'plan.json').unlink();self.refused('invalid_bundle',self.reader)
        (self.directory/'plan.json').write_bytes(b'x')
        (self.directory/'unknown').write_bytes(b'x');self.refused('invalid_bundle',self.reader)
        (self.directory/'unknown').unlink()
        (self.directory/'result.json').unlink();(self.directory/'result.json').mkdir()
        self.refused('invalid_bundle',self.reader);(self.directory/'result.json').rmdir();(self.directory/'result.json').write_bytes(b'x')
        (self.directory/'support').mkdir();(self.directory/'support/c00-s00.csv').write_bytes(b'x')
        self.refused('invalid_bundle',self.reader)

    def test_symlink_hardlink_and_symlinked_root_refuse(self):
        member=self.directory/'result.json';member.unlink();member.symlink_to(self.directory/'plan.json')
        self.refused('unsafe_path',self.reader);member.unlink();os.link(self.directory/'plan.json',member)
        self.refused('unsafe_path',self.reader);member.unlink()
        alias=self.parent/'alias';alias.symlink_to(self.directory)
        self.refused('unsafe_path',self.m._open_bundle_reader,alias,self.budget)

    def test_changed_original_file_even_equal_size_is_not_refreshed(self):
        reader=self.reader();member=self.directory/'result.json';old=member.stat();member.write_bytes(b'X'*old.st_size)
        os.utime(member,ns=(old.st_atime_ns,old.st_mtime_ns))
        self.refused('bundle_changed',self.m._open_bundle_member,reader,'result.json',self.budget)

    def test_replaced_root_and_support_are_detected(self):
        (self.directory/'support').mkdir()
        for suffix in ('.csv','.schema.json'):(self.directory/'support'/('c00-s00'+suffix)).write_bytes(b'x')
        reader=self.reader();(self.directory/'support').rename(self.directory/'old-support');(self.directory/'support').mkdir()
        self.refused('bundle_changed',self.m._recheck_bundle_reader,reader,self.budget)
        self.directory.rename(self.parent/'moved');self.directory.mkdir()
        self.refused('bundle_changed',self.m._open_bundle_member,reader,'plan.json',self.budget)

    def test_read_requires_known_member_single_current_and_exact_bounded_count(self):
        reader=self.reader()
        for path in ('../plan.json','/plan.json','support/c32-s00.csv','unknown'):
            self.refused('unsafe_path',self.m._open_bundle_member,reader,path,self.budget)
        self.m._open_bundle_member(reader,'plan.json',self.budget)
        self.refused('unsafe_path',self.m._open_bundle_member,reader,'result.json',self.budget)
        for count in (0,65537,True,1.):self.refused('unsafe_path',self.m._read_bundle_chunk,reader,count,self.budget)
        self.m._close_bundle_member(reader)

    def test_truncation_and_shortened_eof_refuse(self):
        reader=self.reader();self.m._open_bundle_member(reader,'plan.json',self.budget)
        (self.directory/'plan.json').write_bytes(b'')
        self.refused('bundle_changed',self.m._read_bundle_chunk,reader,65536,self.budget)

    def test_hard_format_cap_and_total_bundle_cap_precede_read(self):
        with (self.directory/'report.html').open('r+b') as stream:stream.truncate(8*1024*1024+1)
        with patch.object(os,'read',side_effect=AssertionError('payload before cap')):
            self.refused('report_bytes_limit',self.reader)

    def test_cancellation_before_acquisition_and_retirement_idempotence(self):
        self.cancel._latch(2);self.refused('interrupted',self.reader)
        self.cancel=_CancellationState();self.budget=LogicalOnlyBudget(self.cancel)
        reader=self.reader();self.m._open_bundle_member(reader,'plan.json',self.budget);fd=reader.current_fd
        self.m._close_bundle_reader(reader);self.m._close_bundle_reader(reader)
        self.assertTrue(reader.retired)
        with self.assertRaises(OSError) as caught:os.fstat(fd)
        self.assertEqual(caught.exception.errno,errno.EBADF)
        self.assertTrue((self.directory/'plan.json').exists())

    def test_failure_after_open_retires_registered_fd_without_foreign_close(self):
        reader=self.reader();before=set(os.listdir('/proc/self/fd'));original=os.fstat
        def fail(fd):
            if reader.current_fd==fd and fd>=0:raise OSError(errno.EIO,'fixture')
            return original(fd)
        with patch.object(os,'fstat',side_effect=fail):
            self.refused('io_error',self.m._open_bundle_member,reader,'plan.json',self.budget)
        self.assertEqual(reader.current_fd,-1)
        self.assertEqual(set(os.listdir('/proc/self/fd')),before)

    def test_no_following_or_creating_unknown_entries_during_recheck(self):
        reader=self.reader();(self.directory/'new').write_bytes(b'x')
        self.refused('bundle_changed',self.m._recheck_bundle_reader,reader,self.budget)
        self.assertEqual((self.directory/'new').read_bytes(),b'x')
