"""Real temporary stage members; no semantic replay, worker or commit claim."""
import ctypes
import errno
import fcntl
import importlib
import os
from pathlib import PosixPath
import sys
import tempfile
import unittest
from unittest.mock import patch

from replicatetable import _native_fs_generated as roots
from replicatetable import _native_workspace as workspace
from replicatetable import _native_fs_profile as profile
from replicatetable._native_budget_state import _CancellationState, LogicalOnlyBudget
from replicatetable.errors import Refusal


ROOT_PAYLOADS = ('plan.json', 'recipe.json', 'report.html', 'result.json', 'schema.json', 'table.csv')


class StageMemberTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('replicatetable._native_stage')
        for name in ('_StageWriter', '_StageWitness', '_begin_stage_writer', '_open_stage_member',
                     '_append_stage_member', '_finish_stage_member', '_seal_stage',
                     '_open_stage_read', '_read_stage_chunk', '_close_stage_member', '_close_stage_writer'):
            self.assertTrue(callable(getattr(self.m, name, None)), 'Missing stage interface: ' + name)
        if not profile._PROFILE_SUPPORTED:
            self.skipTest('Native stage success requires experimental Linux6.18.44 tmpfs profile')
        temporary = tempfile.TemporaryDirectory(prefix='rt-stage-', dir='/tmp')
        self.addCleanup(temporary.cleanup)
        self.directory = PosixPath(temporary.name)
        self.final = self.directory / 'output.bundle'
        self.source = self.directory / 'input.bin'
        self.source.write_bytes(b'owned source stays unchanged')
        self.cancellation = _CancellationState()
        self.budget = LogicalOnlyBudget(self.cancellation)
        self.root = roots._prepare_stage_root(self.final, (), self.budget)
        self.addCleanup(roots._close_generated_root, self.root)
        workspace._create_generated_root(self.root, self.budget)
        self.stage_path = self.directory / self.root.name

    def writer(self, kind='bundle'):
        writer = self.m._begin_stage_writer(self.root, kind, self.budget)
        self.addCleanup(self.m._close_stage_writer, writer, quiet=True)
        return writer

    def refuse(self, code, function, *args, **kwargs):
        with self.assertRaises(Refusal) as caught:
            function(*args, **kwargs)
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def write(self, writer, path, data=b'{}'):
        self.m._open_stage_member(writer, path, len(data), self.budget)
        self.m._append_stage_member(writer, data, self.budget)
        return self.m._finish_stage_member(writer, self.budget)

    def finish_bundle(self, writer, *, support=False):
        for name in ROOT_PAYLOADS:
            self.write(writer, name)
        if support:
            self.write(writer, 'support/c00-s00.csv', b'a\n')
            self.write(writer, 'support/c00-s00.schema.json')
        self.write(writer, 'manifest.json')
        return self.m._seal_stage(writer, self.budget)

    def closed(self, fd):
        with self.assertRaises(OSError) as caught:
            os.fstat(fd)
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_factory_requires_actual_empty_stage_not_a_scalar_record(self):
        for root in (object(), object.__new__(roots._GeneratedRoot)):
            self.refuse('unsafe_path', self.m._begin_stage_writer, root, 'bundle', self.budget)
        prepared = roots._prepare_stage_root(self.directory / 'other', (), self.budget)
        self.addCleanup(roots._close_generated_root, prepared)
        self.refuse('unsafe_path', self.m._begin_stage_writer, prepared, 'bundle', self.budget)
        (self.stage_path / 'unknown').write_bytes(b'owned fixture')
        self.refuse('invalid_bundle', self.m._begin_stage_writer, self.root, 'bundle', self.budget)
        self.assertFalse(self.final.exists())

    def test_closed_classes_refuse_constructor_reinit_partial_and_mutation(self):
        self.refuse('unsafe_path', self.m._StageWriter)
        writer = self.writer()
        self.refuse('unsafe_path', writer.__init__)
        with self.assertRaises(AttributeError):
            writer._kind = 'plan'
        partial = object.__new__(self.m._StageWriter)
        self.refuse('unsafe_path', self.m._open_stage_member,
                    partial, 'plan.json', 2, self.budget)

    def test_plan_stages_exactly_one_file_and_never_final_output(self):
        writer = self.writer('plan')
        witness = self.write(writer, 'plan.json', b'{"version":2}\n')
        self.assertEqual(witness.size, 14)
        seal = self.m._seal_stage(writer, self.budget)
        self.assertEqual(tuple(entry.path for entry in seal.entries), ('plan.json',))
        self.assertEqual(seal.directory.inode, self.root.created_identity.inode)
        self.assertFalse(self.root.committed)
        self.assertFalse(self.final.exists())
        self.assertEqual(self.source.read_bytes(), b'owned source stays unchanged')

    def test_plan_rejects_bundle_members_before_open(self):
        writer = self.writer('plan')
        with patch.object(os, 'open', side_effect=AssertionError('invalid plan path open')):
            self.refuse('unsafe_path', self.m._open_stage_member,
                        writer, 'recipe.json', 2, self.budget)

    def test_member_path_types_ranges_and_levels_are_closed(self):
        writer = self.writer()
        class PathHook:
            def __fspath__(self): raise AssertionError('fspath callback')
        for path in ('../plan.json', '/plan.json', 'support/../plan.json',
                     'support/c32-s00.csv', 'support/c00-s02.csv', 'support/c0-s00.csv',
                     'support/extra/name.csv', 'unknown', PosixPath('plan.json'), PathHook()):
            with self.subTest(path=type(path).__name__), \
                    patch.object(os, 'open', side_effect=AssertionError('invalid path open')):
                self.refuse('unsafe_path', self.m._open_stage_member, writer, path, 2, self.budget)

    def test_member_caps_are_checked_before_creation_or_emission(self):
        writer = self.writer('plan')
        for cap in (True, -1, 1.0, '3', 2**63):
            with self.subTest(cap=cap), patch.object(os, 'open', side_effect=AssertionError('invalid cap open')):
                self.refuse(None, self.m._open_stage_member, writer, 'plan.json', cap, self.budget)
        self.m._open_stage_member(writer, 'plan.json', 2, self.budget)
        with patch.object(os, 'write', side_effect=AssertionError('over-cap write')):
            self.refuse('resource_estimate_mismatch', self.m._append_stage_member,
                        writer, b'abc', self.budget)
        self.assertEqual(os.fstat(writer.current_fd).st_size, 0)

    def test_exclusive_member_creation_does_not_adopt_existing_entry(self):
        writer = self.writer()
        existing = self.stage_path / 'plan.json'
        existing.write_bytes(b'existing owned fixture')
        self.refuse('io_error', self.m._open_stage_member, writer, 'plan.json', 64, self.budget)
        self.assertEqual(existing.read_bytes(), b'existing owned fixture')

    def test_symlink_and_hardlink_are_not_write_authority(self):
        writer = self.writer()
        path = self.stage_path / 'plan.json'
        path.symlink_to(self.source)
        self.refuse(None, self.m._open_stage_member, writer, 'plan.json', 64, self.budget)
        self.assertEqual(self.source.read_bytes(), b'owned source stays unchanged')

    def test_current_file_is_registered_before_fstat_setup_failure(self):
        writer = self.writer('plan')
        actual_open, actual_fstat = os.open, os.fstat
        acquired = []
        def opening(path, flags, *args, **kwargs):
            fd = actual_open(path, flags, *args, **kwargs)
            if path == 'plan.json': acquired.append(fd)
            return fd
        def observed(fd):
            if fd in acquired:
                self.assertEqual(writer.current_fd, fd)
                raise OSError(errno.EIO, 'stage setup fixture')
            return actual_fstat(fd)
        with patch.object(os, 'open', opening), patch.object(os, 'fstat', observed):
            self.refuse('io_error', self.m._open_stage_member, writer, 'plan.json', 2, self.budget)
        self.assertEqual(len(acquired), 1)
        self.m._close_stage_writer(writer)
        self.closed(acquired[0])
        self.assertFalse(self.final.exists())

    def test_only_one_member_can_be_current(self):
        writer = self.writer()
        self.m._open_stage_member(writer, 'plan.json', 2, self.budget)
        original_fd = writer.current_fd
        self.refuse('unsafe_path', self.m._open_stage_member,
                    writer, 'recipe.json', 2, self.budget)
        self.assertEqual(writer.current_fd, original_fd)
        self.assertFalse((self.stage_path / 'recipe.json').exists())

    def test_short_writes_complete_once_and_zero_progress_refuses(self):
        writer = self.writer('plan')
        self.m._open_stage_member(writer, 'plan.json', 6, self.budget)
        actual_write = os.write
        calls = []
        def short(fd, data):
            calls.append(fd)
            return actual_write(fd, data[:2])
        with patch.object(os, 'write', short):
            self.m._append_stage_member(writer, b'abcdef', self.budget)
        self.assertEqual(len(calls), 3)
        self.assertEqual((self.stage_path / 'plan.json').read_bytes(), b'abcdef')
        witness = self.m._finish_stage_member(writer, self.budget)
        self.assertEqual(witness.size, 6)
        self.assertEqual(writer.current_fd, -1)

    def test_zero_progress_is_one_attempt_and_no_seal(self):
        writer = self.writer('plan')
        self.m._open_stage_member(writer, 'plan.json', 2, self.budget)
        with patch.object(os, 'write', return_value=0) as written:
            error = self.refuse('io_error', self.m._append_stage_member, writer, b'{}', self.budget)
        self.assertEqual(error.exit_code, 3)
        self.assertEqual(written.call_count, 1)
        self.assertEqual(writer.sealed_count, 0)

    def test_short_prefix_cancellation_preserves_prefix_and_aborts(self):
        writer = self.writer('plan')
        self.m._open_stage_member(writer, 'plan.json', 6, self.budget)
        actual_write = os.write
        calls = []
        def cancel(fd, data):
            calls.append(fd)
            count = actual_write(fd, data[:2])
            self.cancellation._latch(2)
            return count
        with patch.object(os, 'write', cancel):
            error = self.refuse('interrupted', self.m._append_stage_member,
                                writer, b'abcdef', self.budget)
        self.assertEqual(error.exit_code, 130)
        self.assertEqual(len(calls), 1)
        self.assertEqual((self.stage_path / 'plan.json').read_bytes(), b'ab')
        self.assertEqual(writer.sealed_count, 0)
        self.assertFalse(self.final.exists())

    def test_hardlink_added_after_acquisition_refuses_before_write(self):
        writer = self.writer('plan')
        self.m._open_stage_member(writer, 'plan.json', 2, self.budget)
        os.link(self.stage_path / 'plan.json', self.directory / 'owned-alias')
        self.refuse('unsafe_path', self.m._append_stage_member, writer, b'{}', self.budget)
        self.assertEqual((self.stage_path / 'plan.json').read_bytes(), b'')

    def test_manifest_is_last_and_requires_payload_members(self):
        writer = self.writer()
        self.refuse('invalid_bundle', self.m._open_stage_member,
                    writer, 'manifest.json', 2, self.budget)
        seal = self.finish_bundle(writer)
        self.assertEqual(len(seal.entries), 7)
        self.refuse('unsafe_path', self.m._open_stage_member,
                    writer, 'support/c00-s00.csv', 2, self.budget)
        self.assertIs(self.root.sealed_witness, seal.directory)

    def test_support_root_and_children_seal_after_manifest(self):
        writer = self.writer()
        original_root = self.root.created_identity
        seal = self.finish_bundle(writer, support=True)
        self.assertEqual(len(seal.entries), 10)
        self.assertEqual(sum(os.path.isdir(self.stage_path / entry.path) for entry in seal.entries), 1)
        self.assertEqual(seal.directory.inode, original_root.inode)
        support = next(entry for entry in seal.entries if entry.path == 'support')
        self.assertEqual(support.witness.inode, os.stat(self.stage_path / 'support').st_ino)
        self.assertEqual(writer.current_fd, -1)
        self.assertEqual(writer.support_fd, -1)

    def test_incomplete_support_pair_cannot_become_complete_seal(self):
        writer = self.writer()
        for name in ROOT_PAYLOADS: self.write(writer, name)
        self.write(writer, 'support/c00-s00.csv', b'a\n')
        self.refuse('invalid_bundle', self.m._open_stage_member,
                    writer, 'manifest.json', 2, self.budget)
        self.assertIsNone(self.root.sealed_witness)

    def test_extra_actual_entry_refuses_and_leaves_stage(self):
        writer = self.writer('plan')
        self.write(writer, 'plan.json')
        (self.stage_path / 'extra').write_bytes(b'owned extra')
        self.refuse('invalid_bundle', self.m._seal_stage, writer, self.budget)
        self.assertIsNone(self.root.sealed_witness)
        self.m._close_stage_writer(writer)
        self.assertTrue((self.stage_path / 'extra').exists())
        self.assertFalse(self.final.exists())

    def test_original_child_replacement_does_not_refresh_expected_seal(self):
        writer = self.writer('plan')
        witness = self.write(writer, 'plan.json')
        path = self.stage_path / 'plan.json'
        path.rename(self.directory / 'original-plan')
        path.write_bytes(b'{}')
        self.refuse('bundle_changed', self.m._seal_stage, writer, self.budget)
        self.assertEqual(witness.inode, os.stat(self.directory / 'original-plan').st_ino)

    def test_readback_requires_whole_stage_seal(self):
        writer = self.writer('plan')
        self.write(writer, 'plan.json')
        self.refuse('unsafe_path', self.m._open_stage_read, writer, 'plan.json', self.budget)
        self.m._seal_stage(writer, self.budget)
        self.m._open_stage_read(writer, 'plan.json', self.budget)
        self.assertEqual(fcntl.fcntl(writer.current_fd, fcntl.F_GETFL) & os.O_ACCMODE, os.O_RDONLY)
        self.assertEqual(self.m._read_stage_chunk(writer, 1, self.budget), b'{')
        self.assertEqual(self.m._read_stage_chunk(writer, 2, self.budget), b'}')
        self.assertEqual(self.m._read_stage_chunk(writer, 2, self.budget), b'')
        self.m._close_stage_member(writer)
        self.assertEqual(writer.current_fd, -1)

    def test_changed_sealed_member_refuses_readback(self):
        writer = self.writer('plan')
        self.write(writer, 'plan.json')
        self.m._seal_stage(writer, self.budget)
        (self.stage_path / 'plan.json').write_bytes(b'changed')
        self.refuse('bundle_changed', self.m._open_stage_read, writer, 'plan.json', self.budget)

    def test_read_count_types_and_maximum_are_checked_before_read(self):
        writer = self.writer('plan')
        self.write(writer, 'plan.json')
        self.m._seal_stage(writer, self.budget)
        self.m._open_stage_read(writer, 'plan.json', self.budget)
        for count in (True, 0, -1, 65537, 1.0):
            with self.subTest(count=count), patch.object(os, 'read', side_effect=AssertionError('invalid count read')):
                self.refuse(None, self.m._read_stage_chunk, writer, count, self.budget)

    def test_maximum_namespace_has_135_files_and_136_entries(self):
        writer = self.writer()
        for path in ROOT_PAYLOADS: self.write(writer, path)
        for column in range(32):
            for stage in range(2):
                self.write(writer, f'support/c{column:02d}-s{stage:02d}.csv', b'x\n')
                self.write(writer, f'support/c{column:02d}-s{stage:02d}.schema.json')
        self.write(writer, 'manifest.json')
        seal = self.m._seal_stage(writer, self.budget)
        self.assertEqual(len(seal.entries), 136)
        self.assertEqual(sum(entry.path != 'support' for entry in seal.entries), 135)

    def test_writer_close_retires_owned_cells_and_keeps_borrowed_root(self):
        writer = self.writer()
        self.m._open_stage_member(writer, 'support/c00-s00.csv', 2, self.budget)
        current, support = writer.current_fd, writer.support_fd
        self.m._close_stage_writer(writer)
        self.closed(current)
        self.closed(support)
        self.assertTrue(writer.retired)
        os.fstat(self.root.fd)
        self.m._close_stage_writer(writer)
        self.assertTrue((self.stage_path / 'support/c00-s00.csv').exists())
        self.assertFalse(self.final.exists())

    def test_control_header_scalars_and_list_tuple_transition_fit_existing_terms(self):
        writer = self.writer()
        self.assertEqual(len(self.m._StageWriter.__slots__), 15)
        self.assertLessEqual(sys.getsizeof(writer), 160)
        state = sys.getsizeof(writer)
        state += sum(sys.getsizeof(value) for value in (135, 128*1024*1024,
                     128*1024*1024, 128*1024*1024, 128*1024*1024))
        state += sys.getsizeof('bundle') + sys.getsizeof('failed')
        state += sys.getsizeof(True) + sys.getsizeof(False)
        self.assertLessEqual(state, 512)
        values = []
        empty_header = list.__sizeof__([])
        for size in range(137):
            capacity = (list.__sizeof__(values) - empty_header) // ctypes.sizeof(ctypes.c_void_p)
            self.assertLessEqual(capacity, 2*size + 8)
            self.assertLessEqual(sys.getsizeof(values) + sys.getsizeof(tuple(values)), 512 + 128*size)
            if size < 136: values.append(None)


if __name__ == '__main__':
    unittest.main()
