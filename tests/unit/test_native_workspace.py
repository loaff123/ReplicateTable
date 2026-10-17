"""Actual owned temporary entries; no worker, scientific read or commit claim."""
import errno
import fcntl
import importlib
import os
from pathlib import PosixPath
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from replicatetable import _native_fs_generated as roots
from replicatetable import _native_fs_owners as owners
from replicatetable._native_budget_state import _CancellationState, LogicalOnlyBudget
from replicatetable.errors import Refusal


def fd_snapshot():
    result = {}
    for text in os.listdir('/proc/self/fd'):
        fd = int(text)
        try:
            observed = os.fstat(fd)
        except OSError as error:
            if error.errno == errno.EBADF:
                continue
            raise
        result[fd] = (observed.st_dev, observed.st_ino, observed.st_mode)
    return result


class WorkspaceBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('replicatetable._native_workspace')
        for name in ('_WorkspaceMember', '_create_generated_root', '_create_workspace_member',
                     '_write_workspace_input', '_seal_workspace_input', '_workspace_protocol_fd',
                     '_capture_workspace_output_witness', '_recheck_workspace_member',
                     '_remove_workspace_member', '_close_workspace_member', '_cleanup_empty_root'):
            self.assertTrue(callable(getattr(self.m, name, None)), 'Missing frozen interface: ' + name)
        profile = importlib.import_module('replicatetable._native_fs_profile')
        if not profile._PROFILE_SUPPORTED:
            self.skipTest('Native workspace success requires experimental Linux6.18.44 tmpfs profile')
        temporary = tempfile.TemporaryDirectory(prefix='replicatetable-workspace-', dir='/tmp')
        self.addCleanup(temporary.cleanup)
        self.directory = PosixPath(temporary.name)
        self.input = self.directory / 'input.bin'
        self.input.write_bytes(b'protected benign fixture')
        self.output = self.directory / 'output.bundle'
        self.budget = LogicalOnlyBudget(_CancellationState())
        os.urandom(1)

    def refuse(self, code, function, *args):
        with self.assertRaises(Refusal) as caught:
            function(*args)
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def stage(self):
        root = roots._prepare_stage_root(self.output, (), self.budget)
        self.addCleanup(roots._close_generated_root, root)
        return root

    def workspace(self, *, create=True):
        root = roots._prepare_workspace_root(self.stage(), (), self.budget)
        self.addCleanup(roots._close_generated_root, root)
        if create:
            self.m._create_generated_root(root, self.budget)
        return root

    def member(self, root, role):
        member = self.m._create_workspace_member(root, role, self.budget)
        self.addCleanup(self.m._close_workspace_member, member)
        return member

    def member_path(self, root, member):
        return self.directory / root.name / member.name

    def seal_input(self, root, member, data=b'{}'):
        self.m._write_workspace_input(root, member, data, 1024, self.budget)
        self.m._seal_workspace_input(root, member, self.budget)

    def closed(self, fd):
        try:
            os.fstat(fd)
        except OSError as error:
            self.assertEqual(error.errno, errno.EBADF)
        else:
            self.fail('Owned descriptor remains open')

    def test_prepared_record_does_not_stand_in_for_real_acquisition(self):
        root = self.workspace(create=False)
        self.assertFalse((self.directory / root.name).exists())
        self.refuse('unsafe_path', self.m._create_workspace_member,
                    root, 'request.json', self.budget)
        self.assertIsNone(root.created_identity)
        self.assertEqual(root.fd, -1)

    def test_actual_workspace_directory_has_original_identity_and_readonly_fd(self):
        root = self.workspace()
        path = self.directory / root.name
        self.assertTrue(path.is_dir())
        observed = os.fstat(root.fd)
        self.assertEqual((observed.st_dev, observed.st_ino, observed.st_mode),
                         (root.created_identity.device, root.created_identity.inode,
                          root.created_identity.mode))
        self.assertEqual(fcntl.fcntl(root.fd, fcntl.F_GETFL) & os.O_ACCMODE, os.O_RDONLY)
        self.assertEqual(stat.S_IMODE(observed.st_mode) & 0o077, 0)
        self.assertIsNone(root.sealed_witness)
        self.assertFalse(root.committed)
        self.assertFalse(self.output.exists())

    def test_actual_stage_creation_is_not_child_seal_or_install(self):
        root = self.stage()
        self.m._create_generated_root(root, self.budget)
        self.assertTrue((self.directory / root.name).is_dir())
        self.assertIsNotNone(root.created_identity)
        self.assertIsNone(root.sealed_witness)
        self.assertFalse(root.committed)
        self.assertFalse(self.output.exists())
        self.refuse('unsafe_path', self.m._create_workspace_member,
                    root, 'request.json', self.budget)

    def test_generated_stage_name_cannot_create_the_final_destination_early(self):
        final = self.directory / ('.replicatetable-stage-' + '42' * 16)
        root = None
        outcome = None
        try:
            with patch.object(os, 'urandom', return_value=b'\x42' * 16):
                try:
                    root = roots._prepare_stage_root(final, (), self.budget)
                    self.m._create_generated_root(root, self.budget)
                except Refusal as error:
                    outcome = (error.code, error.exit_code)
        finally:
            if root is not None:
                roots._close_generated_root(root)
        self.assertFalse(final.exists(), 'Temporary stage appeared at final destination')
        self.assertEqual(outcome, ('io_error', 3))
        self.assertEqual(self.input.read_bytes(), b'protected benign fixture')

    def test_generated_workspace_name_cannot_create_the_final_destination_early(self):
        final = self.directory / ('.replicatetable-work-' + '43' * 16)
        root = None
        outcome = None
        with patch.object(os, 'urandom', return_value=b'\x43' * 16):
            stage = roots._prepare_stage_root(final, (), self.budget)
            self.addCleanup(roots._close_generated_root, stage)
            try:
                try:
                    root = roots._prepare_workspace_root(stage, (), self.budget)
                    self.m._create_generated_root(root, self.budget)
                except Refusal as error:
                    outcome = (error.code, error.exit_code)
            finally:
                if root is not None:
                    roots._close_generated_root(root)
        self.assertFalse(final.exists(), 'Temporary workspace appeared at final destination')
        self.assertEqual(outcome, ('io_error', 3))
        self.assertEqual(self.input.read_bytes(), b'protected benign fixture')

    def test_root_creation_is_exclusive_and_never_adopts_an_existing_entry(self):
        root = self.workspace(create=False)
        path = self.directory / root.name
        path.mkdir()
        marker = path / 'marker'
        marker.write_bytes(b'pre-existing fixture')
        self.refuse('io_error', self.m._create_generated_root, root, self.budget)
        self.assertIsNone(root.created_identity)
        self.assertFalse(self.m._cleanup_empty_root(root))
        self.assertEqual(marker.read_bytes(), b'pre-existing fixture')

    def test_second_creation_refuses_without_refreshing_root_identity(self):
        root = self.workspace()
        original = root.created_identity
        self.refuse('unsafe_path', self.m._create_generated_root, root, self.budget)
        self.assertIs(root.created_identity, original)

    def test_changed_parent_path_refuses_before_mkdir(self):
        parent = self.directory / 'parent'
        parent.mkdir()
        stage = roots._prepare_stage_root(parent / 'out', (), self.budget)
        self.addCleanup(roots._close_generated_root, stage)
        parent.rename(self.directory / 'original-parent')
        parent.mkdir()
        with patch.object(os, 'mkdir', side_effect=AssertionError('changed parent mkdir')):
            self.refuse('unsafe_path', self.m._create_generated_root, stage, self.budget)

    def test_cancelled_or_invalid_budget_precedes_creation(self):
        root = self.workspace(create=False)
        cancellation = _CancellationState()
        cancellation._latch(2)
        with patch.object(os, 'mkdir', side_effect=AssertionError('forbidden mkdir')):
            error = self.refuse('interrupted', self.m._create_generated_root,
                                root, LogicalOnlyBudget(cancellation))
            self.assertEqual(error.exit_code, 130)
            self.refuse('supervision_unavailable', self.m._create_generated_root, root, object())

    def test_opened_root_fd_is_registered_before_fstat_failure(self):
        root = self.workspace(create=False)
        real_open, real_fstat = os.open, os.fstat
        acquired = []

        def opened(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            if path == root.name and kwargs.get('dir_fd') == root.parent_fd:
                acquired.append(fd)
            return fd

        def fail_setup(fd):
            if fd in acquired:
                self.assertEqual(root.fd, fd)
                raise OSError(errno.EIO, 'root setup fixture')
            return real_fstat(fd)

        with patch.object(os, 'open', opened), patch.object(os, 'fstat', fail_setup):
            self.refuse('io_error', self.m._create_generated_root, root, self.budget)
        self.assertEqual(len(acquired), 1)
        parent_fd = root.parent_fd
        roots._close_generated_root(root)
        self.closed(parent_fd)
        self.closed(acquired[0])
        self.assertEqual(self.input.read_bytes(), b'protected benign fixture')

    def test_all_four_members_are_real_exclusive_single_link_files(self):
        root = self.workspace()
        identity = root.created_identity
        names = ('request.json', 'completion.json', 'control.json', 'payload.bin')
        for name in names:
            member = self.member(root, name)
            observed = os.fstat(member.fd)
            parent = os.fstat(member.parent_fd)
            self.assertTrue(stat.S_ISREG(observed.st_mode))
            self.assertEqual((observed.st_size, observed.st_nlink), (0, 1))
            self.assertEqual((parent.st_dev, parent.st_ino), (identity.device, identity.inode))
            self.assertEqual((member.created_identity.device, member.created_identity.inode),
                             (observed.st_dev, observed.st_ino))
            self.assertEqual(member.name, name)
            self.assertIsNone(member.witness)
            self.assertFalse(member.retired)
        self.assertEqual(set(os.listdir(root.fd)), set(names))
        self.assertIs(root.created_identity, identity)

    def test_member_role_is_exact_before_io(self):
        root = self.workspace()

        class Text(str):
            def __eq__(self, other):
                raise AssertionError('subclass comparison')

        with patch.object(os, 'open', side_effect=AssertionError('bad role open')):
            for value in ('../request.json', 'support', 'unknown', b'request.json', Text('request.json')):
                self.refuse('unsafe_path', self.m._create_workspace_member, root, value, self.budget)

    def test_member_setup_failure_closes_new_cells_and_keeps_root_authority(self):
        root = self.workspace()
        before = fd_snapshot()
        original = root.created_identity
        real_open, real_fstat, real_init = os.open, os.fstat, owners._FDCell.__init__
        cells, acquired = [], []

        def initialized(cell):
            real_init(cell)
            cells.append(cell)

        def opened(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            if path == 'request.json':
                acquired.append(fd)
            return fd

        def failed_fstat(fd):
            if fd in acquired:
                self.assertTrue(any(owners._cell_fd(cell) == fd for cell in cells))
                raise OSError(errno.EIO, 'member setup fixture')
            return real_fstat(fd)

        with (patch.object(owners._FDCell, '__init__', initialized),
              patch.object(os, 'open', opened), patch.object(os, 'fstat', failed_fstat)):
            self.refuse('io_error', self.m._create_workspace_member,
                        root, 'request.json', self.budget)
        self.assertEqual(len(acquired), 1)
        self.assertEqual(fd_snapshot(), before)
        self.assertIs(root.created_identity, original)
        self.assertFalse(root.retired)
        os.fstat(root.fd)
        self.assertFalse(self.m._cleanup_empty_root(root))

    def test_existing_member_and_symlink_are_not_replaced(self):
        root = self.workspace()
        member = self.member(root, 'request.json')
        original = member.created_identity
        self.refuse(None, self.m._create_workspace_member, root, 'request.json', self.budget)
        self.assertEqual(os.fstat(member.fd).st_ino, original.inode)
        (self.directory / root.name / 'control.json').symlink_to(self.input)
        self.refuse(None, self.m._create_workspace_member, root, 'control.json', self.budget)
        self.assertEqual(self.input.read_bytes(), b'protected benign fixture')

    def test_member_is_closed_immutable_and_not_scalar_acquisition(self):
        root = self.workspace()
        member = self.member(root, 'request.json')
        self.assertFalse(hasattr(member, '__dict__'))
        for name in ('fd', 'witness', 'name', 'extra'):
            with self.assertRaises(AttributeError):
                setattr(member, name, 1)
        self.refuse('unsafe_path', self.m._WorkspaceMember)
        self.refuse('unsafe_path', member.__init__)
        with self.assertRaises(TypeError):
            type('DerivedMember', (self.m._WorkspaceMember,), {})
        partial = object.__new__(self.m._WorkspaceMember)
        self.refuse('unsafe_path', self.m._close_workspace_member, partial)

    def test_member_parent_authority_cannot_be_swapped_for_another_root(self):
        root, other = self.workspace(), self.workspace()
        member = self.member(root, 'request.json')
        self.refuse('unsafe_path', self.m._write_workspace_input,
                    other, member, b'{}', 1024, self.budget)
        self.assertEqual(self.member_path(root, member).read_bytes(), b'')

    def test_input_sink_enforces_real_size_cap_and_short_writes(self):
        root = self.workspace()
        member = self.member(root, 'request.json')
        real_write = os.write
        calls = []

        def short_write(fd, data):
            calls.append(fd)
            return real_write(fd, data[:2])

        with patch.object(os, 'write', short_write):
            self.m._write_workspace_input(root, member, b'abcdef', 6, self.budget)
        self.assertGreater(len(calls), 1)
        self.assertEqual(self.member_path(root, member).read_bytes(), b'abcdef')
        with patch.object(os, 'write', side_effect=AssertionError('cap overflow write')):
            self.refuse(None, self.m._write_workspace_input, root, member, b'g', 6, self.budget)

    def test_input_sink_rejects_nonbytes_oversize_and_invalid_caps_before_write(self):
        root = self.workspace()
        member = self.member(root, 'control.json')
        with patch.object(os, 'write', side_effect=AssertionError('invalid sink write')):
            for data, limit in ((bytearray(b'x'), 1), ('x', 1), (b'x' * 65537, 65537),
                                (b'x', True), (b'x', -1), (b'x', 16 * 1024 * 1024 + 1)):
                self.refuse(None, self.m._write_workspace_input,
                            root, member, data, limit, self.budget)

    def test_input_sink_forbids_output_roles_and_nonappend_cursor(self):
        root = self.workspace()
        output = self.member(root, 'payload.bin')
        self.refuse('unsafe_path', self.m._write_workspace_input,
                    root, output, b'x', 1, self.budget)
        member = self.member(root, 'request.json')
        self.m._write_workspace_input(root, member, b'abc', 3, self.budget)
        os.lseek(member.fd, 0, os.SEEK_SET)
        self.refuse('unsafe_path', self.m._write_workspace_input,
                    root, member, b'x', 4, self.budget)
        self.assertEqual(self.member_path(root, member).read_bytes(), b'abc')

    def test_input_seal_reopens_readonly_against_the_original_inode(self):
        root = self.workspace()
        member = self.member(root, 'request.json')
        original = member.created_identity
        old_fd = member.fd
        closed = []
        opened = []
        real_close, real_open = os.close, os.open

        def observed_close(fd):
            closed.append(fd)
            return real_close(fd)

        def observed_open(path, flags, *args, **kwargs):
            if path == member.name:
                self.assertIn(old_fd, closed)
                self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
                opened.append(path)
            return real_open(path, flags, *args, **kwargs)

        self.m._write_workspace_input(root, member, b'{"ok":1}', 1024, self.budget)
        with patch.object(os, 'close', observed_close), patch.object(os, 'open', observed_open):
            self.m._seal_workspace_input(root, member, self.budget)
        self.assertEqual(opened, [member.name])
        self.assertIs(member.created_identity, original)
        self.assertEqual(fcntl.fcntl(member.fd, fcntl.F_GETFL) & os.O_ACCMODE, os.O_RDONLY)
        self.assertEqual(os.read(member.fd, 64), b'{"ok":1}')
        self.assertIsNotNone(member.witness)
        self.m._recheck_workspace_member(root, member, self.budget)
        self.refuse('unsafe_path', self.m._write_workspace_input,
                    root, member, b'x', 1024, self.budget)

    def test_failed_readonly_reopen_never_exposes_input_role(self):
        root = self.workspace()
        member = self.member(root, 'control.json')
        self.m._write_workspace_input(root, member, b'{}', 2, self.budget)
        real_open = os.open

        def failed_open(path, flags, *args, **kwargs):
            if path == member.name:
                raise OSError(errno.EIO, 'reopen fixture')
            return real_open(path, flags, *args, **kwargs)

        with patch.object(os, 'open', failed_open):
            self.refuse('io_error', self.m._seal_workspace_input, root, member, self.budget)
        self.refuse('unsafe_path', self.m._workspace_protocol_fd,
                    root, member, member.name, self.budget)
        self.m._close_workspace_member(member)
        self.assertFalse(root.retired)
        os.fstat(root.fd)

    def test_protocol_borrow_checks_exact_role_and_actual_access(self):
        root = self.workspace()
        request = self.member(root, 'request.json')
        self.refuse('unsafe_path', self.m._workspace_protocol_fd,
                    root, request, 'request.json', self.budget)
        self.seal_input(root, request)
        self.assertEqual(self.m._workspace_protocol_fd(root, request, 'request.json', self.budget),
                         request.fd)
        self.refuse('unsafe_path', self.m._workspace_protocol_fd,
                    root, request, 'control.json', self.budget)
        for name in ('completion.json', 'payload.bin'):
            member = self.member(root, name)
            self.assertEqual(self.m._workspace_protocol_fd(root, member, name, self.budget), member.fd)
            os.write(member.fd, b'x')
            self.refuse('unsafe_path', self.m._workspace_protocol_fd,
                        root, member, name, self.budget)

    def test_stable_input_recheck_never_refreshes_expected_witness(self):
        root = self.workspace()
        member = self.member(root, 'request.json')
        self.seal_input(root, member)
        original = member.witness
        self.member_path(root, member).write_bytes(b'changed fixture')
        self.refuse('unsafe_path', self.m._recheck_workspace_member, root, member, self.budget)
        self.assertIs(member.witness, original)

    def test_single_link_rule_applies_before_writes_or_seals(self):
        root = self.workspace()
        member = self.member(root, 'request.json')
        os.link(self.member_path(root, member), self.directory / 'owned-alias')
        self.refuse('unsafe_path', self.m._write_workspace_input,
                    root, member, b'x', 1, self.budget)
        self.refuse('unsafe_path', self.m._seal_workspace_input, root, member, self.budget)

    def test_output_witness_capture_is_bounded_and_does_not_claim_reap(self):
        # This fixture has no worker; its own writes are already quiescent.
        root = self.workspace()
        member = self.member(root, 'completion.json')
        os.write(member.fd, b'{"ready":true}')
        self.refuse(None, self.m._capture_workspace_output_witness,
                    root, member, 1, self.budget)
        self.assertIsNone(member.witness)
        self.m._capture_workspace_output_witness(root, member, 1024, self.budget)
        original = member.witness
        self.m._recheck_workspace_member(root, member, self.budget)
        os.write(member.fd, b' ')
        self.refuse('unsafe_path', self.m._capture_workspace_output_witness,
                    root, member, 1024, self.budget)
        self.assertIs(member.witness, original)
        self.assertFalse(root.committed)

    def test_unsealed_members_and_nonempty_roots_are_left_as_residue(self):
        root = self.workspace()
        member = self.member(root, 'request.json')
        self.assertFalse(self.m._remove_workspace_member(root, member))
        self.assertFalse(self.m._cleanup_empty_root(root))
        self.assertTrue(self.member_path(root, member).exists())

    def test_sealed_owned_member_removal_then_empty_root_cleanup_are_real(self):
        root = self.workspace()
        member = self.member(root, 'control.json')
        self.seal_input(root, member)
        path = self.member_path(root, member)
        self.assertTrue(self.m._remove_workspace_member(root, member))
        self.assertFalse(path.exists())
        self.m._close_workspace_member(member)
        root_path = self.directory / root.name
        self.assertTrue(self.m._cleanup_empty_root(root))
        self.assertFalse(root_path.exists())
        self.assertFalse(self.output.exists())

    def test_replaced_member_is_not_removed(self):
        root = self.workspace()
        member = self.member(root, 'request.json')
        self.seal_input(root, member)
        path = self.member_path(root, member)
        path.rename(path.with_name('original-request'))
        path.write_bytes(b'replacement')
        self.assertFalse(self.m._remove_workspace_member(root, member))
        self.assertEqual(path.read_bytes(), b'replacement')

    def test_changed_sealed_content_is_not_removed(self):
        root = self.workspace()
        member = self.member(root, 'control.json')
        self.seal_input(root, member)
        path = self.member_path(root, member)
        path.write_bytes(b'changed')
        self.assertFalse(self.m._remove_workspace_member(root, member))
        self.assertEqual(path.read_bytes(), b'changed')

    def test_replaced_root_is_not_removed_or_traversed(self):
        root = self.workspace()
        path = self.directory / root.name
        path.rename(self.directory / 'original-workspace')
        path.mkdir()
        marker = path / 'marker'
        marker.write_bytes(b'replacement')
        self.assertFalse(self.m._cleanup_empty_root(root))
        self.assertEqual(marker.read_bytes(), b'replacement')

    def test_cleanup_after_cancellation_starts_no_new_budget(self):
        root = self.workspace()
        self.budget._cancellation._latch(15)
        with patch('replicatetable._native_budget_state.monotonic_ns',
                   side_effect=AssertionError('cleanup clock')):
            self.assertTrue(self.m._cleanup_empty_root(root))
        roots._close_generated_root(root)

    def test_member_close_is_fd_only_idempotent_and_reentry_safe(self):
        root = self.workspace()
        member = self.member(root, 'request.json')
        descriptors = (member.fd, member.parent_fd)
        real_close = os.close
        replacements = []

        def closed_then_reentered(fd):
            real_close(fd)
            if fd == descriptors[0] and not replacements:
                replacements.append(os.open(self.input, os.O_RDONLY))
                self.m._close_workspace_member(member)

        try:
            with patch.object(os, 'close', closed_then_reentered):
                self.m._close_workspace_member(member)
            self.assertTrue(member.retired)
            self.assertEqual((member.fd, member.parent_fd), (-1, -1))
            self.assertEqual(len(replacements), 1)
            self.assertEqual(os.fstat(replacements[0]).st_ino, os.stat(self.input).st_ino)
            self.m._close_workspace_member(member)
            os.fstat(replacements[0])
            os.fstat(root.fd)
            self.assertTrue((self.directory / root.name / 'request.json').exists())
        finally:
            for fd in replacements:
                real_close(fd)

    def test_logical_io_route_does_not_read_clock(self):
        with patch('replicatetable._native_budget_state.monotonic_ns',
                   side_effect=AssertionError('logical route clock')):
            root = self.workspace()
            member = self.member(root, 'request.json')
            self.seal_input(root, member)
            self.m._recheck_workspace_member(root, member, self.budget)
            self.assertTrue(self.m._remove_workspace_member(root, member))
            self.m._close_workspace_member(member)
            self.assertTrue(self.m._cleanup_empty_root(root))

    def test_zero_progress_write_fails_after_one_attempt(self):
        root = self.workspace()
        member = self.member(root, 'request.json')
        with patch.object(os, 'write', return_value=0) as written:
            error = self.refuse('io_error', self.m._write_workspace_input,
                                root, member, b'ab', 2, self.budget)
        self.assertEqual(error.exit_code, 3)
        self.assertEqual(written.call_count, 1)
        self.assertEqual(os.fstat(member.fd).st_size, 0)
        self.assertIsNone(member.witness)

    def test_short_prefix_then_cancel_performs_no_second_write(self):
        root = self.workspace()
        member = self.member(root, 'control.json')
        cancellation = _CancellationState()
        budget = LogicalOnlyBudget(cancellation)
        actual_write = os.write
        calls = []

        def short_then_cancel(fd, data):
            calls.append(fd)
            count = actual_write(fd, data[:2])
            cancellation._latch(15)
            return count

        with patch.object(os, 'write', short_then_cancel):
            error = self.refuse('interrupted', self.m._write_workspace_input,
                                root, member, b'abcdef', 6, budget)
        self.assertEqual(error.exit_code, 143)
        self.assertEqual(calls, [member.fd])
        self.assertEqual(os.pread(member.fd, 3, 0), b'ab')
        self.assertEqual(os.fstat(member.fd).st_size, 2)
        self.assertIsNone(member.witness)

    def test_seal_close_failure_retires_writer_and_never_reopens(self):
        root = self.workspace()
        member = self.member(root, 'request.json')
        self.m._write_workspace_input(root, member, b'{}', 2, self.budget)
        write_fd = member.fd
        actual_close = os.close
        closed = []

        def close_and_fail(fd):
            closed.append(fd)
            actual_close(fd)
            if fd == write_fd:
                raise OSError(errno.EIO, 'owned close fixture')

        with patch.object(os, 'close', close_and_fail), patch.object(os, 'open') as opened:
            error = self.refuse('io_error', self.m._seal_workspace_input,
                                root, member, self.budget)
            self.assertFalse(opened.called)
        self.assertEqual(error.exit_code, 3)
        self.assertEqual(closed, [write_fd])
        self.assertEqual(member.fd, -1)
        self.refuse('unsafe_path', self.m._workspace_protocol_fd,
                    root, member, 'request.json', self.budget)
        os.fstat(root.fd)

    def test_output_cap_types_boundary_and_original_seal(self):
        root = self.workspace()
        member = self.member(root, 'payload.bin')
        os.write(member.fd, b'abc')
        for cap in (True, -1, 1.0, '3', 2**63):
            with self.subTest(cap=cap), patch.object(os, 'fstat', side_effect=AssertionError('invalid cap IO')):
                self.refuse('memory_limit', self.m._capture_workspace_output_witness,
                            root, member, cap, self.budget)
            self.assertIsNone(member.witness)
        self.refuse('memory_limit', self.m._capture_workspace_output_witness,
                    root, member, 2, self.budget)
        self.assertIsNone(member.witness)
        self.m._capture_workspace_output_witness(root, member, 3, self.budget)
        original = member.witness
        self.assertEqual(original.size, 3)
        self.m._capture_workspace_output_witness(root, member, 3, self.budget)
        self.assertIs(member.witness, original)
        os.write(member.fd, b'd')
        self.refuse('unsafe_path', self.m._capture_workspace_output_witness,
                    root, member, 4, self.budget)
        self.assertIs(member.witness, original)

    def test_empty_root_cleanup_uses_anchored_rmdir_without_scan(self):
        root = self.workspace()
        actual_rmdir = os.rmdir
        before = fd_snapshot()
        calls = []
        def removing(name, *args, **kwargs):
            self.assertEqual((name, kwargs['dir_fd']), (root.name, root.parent_fd))
            self.assertEqual(fd_snapshot(), before)
            calls.append(name)
            return actual_rmdir(name, *args, **kwargs)
        with patch.object(os, 'scandir', side_effect=AssertionError('preliminary scan')), \
                patch.object(os, 'rmdir', removing):
            self.assertTrue(self.m._cleanup_empty_root(root))
        self.assertEqual(calls, [root.name])
        self.assertEqual(fd_snapshot(), before)
        self.assertFalse((self.directory / root.name).exists())

    def test_nonempty_root_cleanup_attempt_leaves_residue_without_scan(self):
        root = self.workspace()
        member = self.member(root, 'request.json')
        actual_rmdir = os.rmdir
        before = fd_snapshot()
        with patch.object(os, 'scandir', side_effect=AssertionError('preliminary scan')), \
                patch.object(os, 'rmdir', wraps=actual_rmdir) as removed:
            self.assertFalse(self.m._cleanup_empty_root(root))
            self.assertEqual(removed.call_count, 1)
        self.assertEqual(fd_snapshot(), before)
        self.assertTrue(self.member_path(root, member).exists())

    def test_root_cleanup_errors_leave_residue_and_preserve_primary(self):
        root = self.workspace()
        primary = Refusal('invalid_recipe')
        for code in (errno.ENOTEMPTY, errno.EEXIST, errno.EIO):
            with self.subTest(errno=code):
                try:
                    raise primary
                except Refusal as active:
                    with patch.object(os, 'scandir', side_effect=AssertionError('preliminary scan')), \
                            patch.object(os, 'rmdir', side_effect=OSError(code, 'owned rmdir fixture')):
                        self.assertFalse(self.m._cleanup_empty_root(root))
                    self.assertIs(sys.exception(), active)
                    self.assertIs(active, primary)
                self.assertTrue((self.directory / root.name).exists())

    def test_replaced_root_cleanup_never_attempts_rmdir(self):
        root = self.workspace()
        path = self.directory / root.name
        path.rename(self.directory / 'original-root')
        path.mkdir()
        with patch.object(os, 'rmdir') as removed:
            self.assertFalse(self.m._cleanup_empty_root(root))
            self.assertFalse(removed.called)
        self.assertTrue(path.is_dir())

    def test_partial_root_cleanup_leaves_unopened_acquisition_as_residue(self):
        root = self.workspace(create=False)
        actual_open = os.open
        def failing(path, flags, *args, **kwargs):
            if path == root.name:
                raise OSError(errno.EIO, 'owned root open fixture')
            return actual_open(path, flags, *args, **kwargs)
        with patch.object(os, 'open', failing):
            self.refuse('io_error', self.m._create_generated_root, root, self.budget)
        self.assertIsNotNone(root.created_identity)
        self.assertEqual(root.fd, -1)
        with patch.object(os, 'rmdir') as removed:
            self.assertFalse(self.m._cleanup_empty_root(root))
            self.assertFalse(removed.called)
        self.assertTrue((self.directory / root.name).is_dir())

    def test_cancelled_root_cleanup_is_finite_and_does_not_read_clock(self):
        root = self.workspace()
        self.budget._cancellation._latch(2)
        # This owned fixture has no worker; its entries are already quiescent.
        with patch.object(os, 'scandir', side_effect=AssertionError('preliminary scan')), \
                patch('replicatetable._native_budget_state.monotonic_ns',
                      side_effect=AssertionError('cleanup clock')):
            self.assertTrue(self.m._cleanup_empty_root(root))
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
