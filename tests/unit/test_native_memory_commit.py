"""Actual tmpfs no-replace installation; fixture metadata is not replay proof."""
import errno
import importlib
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from replicatetable import _native_fs_generated as roots
from replicatetable import _native_workspace as workspace
from replicatetable import _native_fs_profile as profile
from replicatetable import _native_stage as stage
from replicatetable import _native_supervisor as supervisor
from replicatetable._native_budget_state import _CancellationState, LogicalOnlyBudget
from replicatetable._bundle_models import PreparedReceipt, BundleReceipt
from replicatetable.model import SourceIdentity
from replicatetable.errors import Refusal


class MemoryCommitTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('replicatetable._native_commit')
        self.assertTrue(callable(getattr(self.m,'_install_memory_bundle',None)),
                        'Actual memory installer is missing')
        if not profile._PROFILE_SUPPORTED:
            self.skipTest('Requires positively qualified Linux6.18.44 tmpfs')
        temporary = tempfile.TemporaryDirectory(prefix='rt-memory-commit-',dir='/tmp')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.destination = self.directory/'result.bundle'
        self.cancel = _CancellationState()
        self.budget = LogicalOnlyBudget(self.cancel)
        self.outcome = supervisor._Outcome(self.cancel)
        self.root = roots._prepare_stage_root(self.destination,(),self.budget)
        self.addCleanup(roots._close_generated_root,self.root)
        workspace._create_generated_root(self.root,self.budget)
        self.writer = stage._begin_stage_writer(self.root,'bundle',self.budget)
        self.addCleanup(stage._close_stage_writer,self.writer,quiet=True)
        for name in ('plan.json','recipe.json','report.html','result.json','schema.json','table.csv','manifest.json'):
            stage._open_stage_member(self.writer,name,16,self.budget)
            stage._append_stage_member(self.writer,b'fixture\n',self.budget)
            stage._finish_stage_member(self.writer,self.budget)
        self.seal = stage._seal_stage(self.writer,self.budget)
        self.prepared = PreparedReceipt(version=2,kind='bundle',source=SourceIdentity('memory','0'*64,10),
            recipe_sha256='1'*64,plan_sha256='2'*64,result_sha256='3'*64,runtime_sha256='4'*64,
            manifest_sha256='5'*64,output_bytes=56)

    def install(self):
        return self.m._install_memory_bundle(self.writer,self.prepared,self.outcome,self.budget)

    def refusal(self,code,function,*args):
        with self.assertRaises(Refusal) as caught: function(*args)
        self.assertEqual(caught.exception.code,code)
        return caught.exception

    def test_real_noreplace_renames_original_directory_and_captures_receipt(self):
        before=os.fstat(self.root.fd)
        receipt=self.install()
        self.assertIs(type(receipt),BundleReceipt)
        self.assertEqual(receipt.status,'committed')
        self.assertEqual(receipt.bundle_bytes,56)
        self.assertFalse(receipt.interrupted_after_commit)
        final=os.stat(self.destination,follow_symlinks=False)
        self.assertEqual((final.st_dev,final.st_ino),(before.st_dev,before.st_ino))
        self.assertFalse((self.directory/self.root.name).exists())
        self.assertTrue(self.root.committed)
        self.assertTrue(self.outcome.committed)
        self.assertIs(self.outcome.receipt,receipt)
        self.assertEqual((self.destination/'result.json').read_bytes(),b'fixture\n')
        self.assertFalse(workspace._cleanup_empty_root(self.root))

    def test_existing_destination_created_during_syscall_is_preserved(self):
        original=self.m._rename_noreplace
        def race(*args):
            self.destination.write_bytes(b'preserve')
            return original(*args)
        with patch.object(self.m,'_rename_noreplace',side_effect=race):
            self.refusal('output_exists',self.install)
        self.assertEqual(self.destination.read_bytes(),b'preserve')
        self.assertFalse(self.outcome.committed)
        self.assertIsNone(self.outcome.receipt)
        self.assertTrue((self.directory/self.root.name).is_dir())

    def test_existing_directory_and_symlink_are_not_replaced(self):
        for kind in ('directory','symlink'):
            with self.subTest(kind=kind):
                if kind=='directory': self.destination.mkdir()
                else: self.destination.symlink_to(self.directory/'missing')
                before=os.lstat(self.destination)
                self.refusal('output_exists',self.install)
                after=os.lstat(self.destination)
                self.assertEqual((before.st_dev,before.st_ino),(after.st_dev,after.st_ino))
                if kind=='directory': self.destination.rmdir()
                else: self.destination.unlink()

    def test_pending_cooperative_cancellation_prevents_rename(self):
        self.cancel._latch(2)
        with patch.object(self.m,'_rename_noreplace',side_effect=AssertionError('rename after cancellation')):
            error=self.refusal('interrupted',self.install)
        self.assertEqual(error.exit_code,130)
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.outcome.committed)

    def test_late_cooperative_cancellation_reports_committed_interruption(self):
        original=self.m._rename_noreplace
        def late(*args):
            result=original(*args)
            self.cancel._latch(15)
            return result
        with patch.object(self.m,'_rename_noreplace',side_effect=late):
            error=self.refusal('interrupted',self.install)
        self.assertEqual(error.exit_code,143)
        self.assertTrue(self.outcome.committed)
        self.assertTrue(self.outcome.receipt.interrupted_after_commit)
        self.assertTrue(self.destination.is_dir())

    def test_exception_after_actual_syscall_reconciles_without_relabeling(self):
        original=self.m._rename_noreplace
        primary=KeyboardInterrupt('caller policy')
        def interrupted(*args):
            original(*args)
            raise primary
        with patch.object(self.m,'_rename_noreplace',side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt) as caught: self.install()
        self.assertIs(caught.exception,primary)
        self.assertTrue(self.destination.is_dir())
        self.assertTrue(self.outcome.committed)
        self.assertTrue(self.outcome.receipt.interrupted_after_commit)

    def test_exception_before_syscall_keeps_original_and_no_commit(self):
        primary=RuntimeError('caller exception')
        with patch.object(self.m,'_rename_noreplace',side_effect=primary):
            with self.assertRaises(RuntimeError) as caught: self.install()
        self.assertIs(caught.exception,primary)
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.outcome.committed)

    def test_repeated_interruption_during_reconciliation_preserves_destination(self):
        original=self.m._rename_noreplace
        primary=KeyboardInterrupt('first')
        def interrupted(*args):
            original(*args)
            raise primary
        with patch.object(self.m,'_rename_noreplace',side_effect=interrupted), \
             patch.object(self.m,'_reconcile_install',side_effect=KeyboardInterrupt('second')):
            with self.assertRaises(KeyboardInterrupt) as caught: self.install()
        self.assertIs(caught.exception,primary)
        self.assertTrue(self.destination.is_dir())
        self.assertFalse(workspace._cleanup_empty_root(self.root))

    def test_noop_syscall_cannot_claim_commit(self):
        with patch.object(self.m,'_rename_noreplace',return_value=0):
            self.refusal('unsupported_atomic_commit',self.install)
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.outcome.committed)

    def test_unsupported_syscall_has_no_fallback(self):
        with patch.object(self.m,'_rename_noreplace',return_value=errno.ENOSYS), \
             patch.object(os,'rename',side_effect=AssertionError('rename fallback')), \
             patch.object(os,'replace',side_effect=AssertionError('replace fallback')):
            self.refusal('unsupported_atomic_commit',self.install)
        self.assertFalse(self.destination.exists())

    def test_background_memory_thread_does_not_inherit_native_launch_preflight(self):
        values=[]
        def run():
            try: values.append(self.install())
            except BaseException as error: values.append(error)
        thread=threading.Thread(target=run)
        thread.start(); thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(values),1)
        self.assertIs(type(values[0]),BundleReceipt)
        self.assertTrue(self.destination.is_dir())

    def test_unfinished_writer_and_mismatched_budget_refuse_before_syscall(self):
        with patch.object(self.m,'_rename_noreplace',side_effect=AssertionError('bad authority')):
            other=LogicalOnlyBudget(_CancellationState())
            self.refusal('supervision_unavailable',self.m._install_memory_bundle,
                         self.writer,self.prepared,self.outcome,other)
            object.__setattr__(self.writer,'_finished',False)
            try: self.refusal('unsafe_path',self.install)
            finally: object.__setattr__(self.writer,'_finished',True)

    def test_changed_sealed_original_refuses_before_install(self):
        (self.directory/self.root.name/'result.json').write_bytes(b'changed\n')
        with patch.object(self.m,'_rename_noreplace',side_effect=AssertionError('changed original')):
            self.refusal('bundle_changed',self.install)
        self.assertFalse(self.destination.exists())
