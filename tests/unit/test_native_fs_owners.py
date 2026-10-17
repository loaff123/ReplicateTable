"""Intended reds for bounded original anchored ownership, no payload authority."""
import errno
import importlib
import os
import pathlib
import stat
import tempfile
import unittest
from unittest.mock import patch

from replicatetable.errors import Refusal
from replicatetable._native_budget_state import _CancellationState, LogicalOnlyBudget, Deadline


class NativeFilesystemOwnerTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('replicatetable._native_fs_owners')
        for name in ('_FileWitness', '_Identity', '_FileOwner', '_DirectoryOwner',
                     '_open_regular', '_open_directory', '_recheck_owner',
                     '_close_owner', '_same_inode'):
            self.assertTrue(callable(getattr(self.m, name, None)),
                            'Approved anchored-owner interface is missing: ' + name)
        self.temp = tempfile.TemporaryDirectory(prefix='replicatetable-owner-')
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.path = self.root / 'input'
        self.path.write_bytes(b'benign owned fixture')
        self.budget = LogicalOnlyBudget(_CancellationState())

    def refuse(self, code, function, *args, **kwargs):
        with self.assertRaises(Refusal) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn(self.temp.name, caught.exception.message)
        return caught.exception

    def open_file(self, path=None):
        owner = self.m._open_regular(self.path if path is None else path, self.budget)
        self.addCleanup(self.m._close_owner, owner)
        return owner

    def assert_closed(self, descriptor):
        with self.assertRaises(OSError) as caught:
            os.fstat(descriptor)
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_file_witness_has_exact_scalar_domains_and_no_acquisition_claim(self):
        witness = self.m._FileWitness((1 << 64)-1, (1 << 64)-1, (1 << 64)-1,
                                      (1 << 63)-1, (1 << 63)-1, -(1 << 63), (1 << 63)-1)
        self.assertEqual(witness.mtime_ns, -(1 << 63))
        self.assertEqual(witness.inode, (1 << 64)-1)
        fields = (0, 1, stat.S_IFREG, 1, 0, 0, 0)
        for index in range(7):
            for bad in (True, 1.0, None, '1'):
                values = list(fields); values[index] = bad
                self.refuse('unsafe_path', self.m._FileWitness, *values)
        for index in range(5):
            values = list(fields); values[index] = -1
            self.refuse('unsafe_path', self.m._FileWitness, *values)
        for index, value in ((0,1 << 64), (1,1 << 64), (2,1 << 64),
                             (3,1 << 63), (4,1 << 63), (5,-(1 << 63)-1), (6,1 << 63)):
            values = list(fields); values[index] = value
            self.refuse('unsafe_path', self.m._FileWitness, *values)
        self.refuse('unsafe_path', self.m._recheck_owner, witness, self.budget,
                    changed_code='source_changed')

    def test_witness_and_identity_are_immutable_and_cannot_reinitialize(self):
        witness = self.m._FileWitness(0, 1, stat.S_IFREG, 1, 0, 0, 0)
        identity = self.m._Identity(0, 1, stat.S_IFDIR)
        for value in (witness, identity):
            with self.assertRaises(AttributeError):
                value.inode = 2
            with self.assertRaises(AttributeError):
                value.extra = 1
            self.assertFalse(hasattr(value, '__dict__'))
        self.refuse('unsafe_path', witness.__init__, 0, 2, stat.S_IFREG, 1, 0, 0, 0)
        self.refuse('unsafe_path', identity.__init__, 0, 2, stat.S_IFDIR)
        self.assertEqual(witness.inode, 1)
        self.assertEqual(identity.inode, 1)

    def test_acquisition_records_original_file_entry_and_parent_without_reading(self):
        original = self.path.read_bytes()
        with patch.object(os, 'read', side_effect=AssertionError('payload read')):
            owner = self.open_file()
        self.assertIs(type(owner), self.m._FileOwner)
        actual = os.fstat(owner.fd)
        self.assertEqual(owner.fd_witness.inode, actual.st_ino)
        self.assertEqual(owner.entry_witness, owner.fd_witness)
        self.assertEqual(owner.fd_witness.size, len(original))
        self.assertEqual(owner.name, 'input')
        self.assertEqual(owner.normalized_path, str(self.path))
        self.assertIs(owner._argument, self.path)
        self.assertEqual(owner.parent_identity.inode, os.stat(self.root).st_ino)
        self.assertEqual(self.path.read_bytes(), original)
        self.m._recheck_owner(owner, self.budget, changed_code='source_changed')

    def test_relative_owner_keeps_only_absolute_revalidation_description(self):
        original_cwd = os.open('.', os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.chdir(self.root)
            value = pathlib.PosixPath('./input')
            owner = self.open_file(value)
        finally:
            os.fchdir(original_cwd); os.close(original_cwd)
        self.assertEqual(owner.normalized_path, str(self.path))
        self.assertIs(owner._argument, value)
        self.m._recheck_owner(owner, self.budget, changed_code='source_changed')

    def test_relative_raw_absolute_join_cap_precedes_normalization_and_open(self):
        with patch.object(os, 'open', side_effect=AssertionError('unadmitted open')):
            self.refuse('unsafe_path', self.m._open_regular, './' * 2047, self.budget)

    def test_absolute_input_does_not_require_a_current_directory(self):
        original_cwd = os.open('.', os.O_RDONLY | os.O_DIRECTORY)
        abandoned = self.root / 'abandoned'; abandoned.mkdir()
        try:
            os.chdir(abandoned)
            abandoned.rmdir()
            owner = self.open_file(self.path)
        finally:
            os.fchdir(original_cwd); os.close(original_cwd)
        self.assertEqual(owner.normalized_path, str(self.path))
        self.m._recheck_owner(owner, self.budget, changed_code='source_changed')

    def test_symlink_leaf_and_ancestor_refuse(self):
        leaf = self.root / 'leaf'; leaf.symlink_to(self.path)
        parent = self.root / 'parent'; parent.symlink_to(self.root, target_is_directory=True)
        self.refuse('unsafe_path', self.m._open_regular, leaf, self.budget)
        self.refuse('unsafe_path', self.m._open_regular, parent / 'input', self.budget)
        self.refuse('unsafe_path', self.m._open_directory, parent, self.budget)

    def test_fifo_and_directory_refuse_without_blocking_open(self):
        fifo = self.root / 'fifo'; os.mkfifo(fifo)
        original_open = os.open
        def checked_open(name, flags, *args, **kwargs):
            self.assertTrue(flags & os.O_NOFOLLOW)
            self.assertTrue(flags & os.O_NONBLOCK)
            return original_open(name, flags, *args, **kwargs)
        with patch.object(os, 'open', checked_open):
            self.refuse('unsafe_path', self.m._open_regular, fifo, self.budget)
            self.refuse('unsafe_path', self.m._open_regular, self.root, self.budget)

    def test_unaliased_hardlinked_input_is_admitted_and_aliases_are_detected(self):
        other = self.root / 'hardlink'; os.link(self.path, other)
        first = self.open_file()
        second = self.open_file(other)
        self.assertEqual(first.fd_witness.nlink, 2)
        self.assertTrue(self.m._same_inode(first.fd_witness, second.fd_witness))
        different = self.root / 'different'; different.write_bytes(b'benign')
        third = self.open_file(different)
        self.assertFalse(self.m._same_inode(first.fd_witness, third.fd_witness))
        self.refuse('unsafe_path', self.m._same_inode, object(), third.fd_witness)

    def test_added_hardlink_changes_original_witness_without_refresh(self):
        owner = self.open_file(); original = owner.fd_witness
        os.link(self.path, self.root / 'added-link')
        self.refuse('source_changed', self.m._recheck_owner, owner, self.budget,
                    changed_code='source_changed')
        self.assertIs(owner.fd_witness, original)
        self.assertEqual(owner.fd_witness.nlink, 1)

    def test_original_file_content_stat_change_is_not_adopted(self):
        owner = self.open_file(); original = owner.fd_witness
        self.path.write_bytes(b'changed benign bytes')
        self.refuse('source_changed', self.m._recheck_owner, owner, self.budget,
                    changed_code='source_changed')
        self.assertIs(owner.fd_witness, original)

    def test_same_name_replacement_fails_entry_binding_and_is_never_removed(self):
        owner = self.open_file(); original = owner.fd_witness
        old = self.root / 'old-input'; self.path.rename(old)
        self.path.write_bytes(b'replacement')
        self.refuse('source_changed', self.m._recheck_owner, owner, self.budget,
                    changed_code='source_changed')
        self.assertIs(owner.fd_witness, original)
        self.m._close_owner(owner)
        self.assertEqual(self.path.read_bytes(), b'replacement')
        self.assertTrue(old.exists())

    def test_absolute_rewalk_rejects_replaced_ancestor_with_original_parent_still_open(self):
        sub = self.root / 'sub'; sub.mkdir()
        source = sub / 'input'; source.write_bytes(b'original')
        owner = self.open_file(source)
        moved = self.root / 'moved'; sub.rename(moved)
        sub.mkdir(); (sub / 'input').write_bytes(b'new')
        self.refuse('source_changed', self.m._recheck_owner, owner, self.budget,
                    changed_code='source_changed')
        self.assertEqual(os.fstat(owner.fd).st_ino, owner.fd_witness.inode)
        self.assertEqual(os.fstat(owner.parent_fd).st_ino, owner.parent_identity.inode)

    def test_parent_directory_content_changes_do_not_replace_identity_authority(self):
        owner = self.open_file(); original = owner.parent_identity
        (self.root / 'sibling').write_bytes(b'new harmless sibling')
        self.m._recheck_owner(owner, self.budget, changed_code='source_changed')
        self.assertIs(owner.parent_identity, original)

    def test_directory_itself_retains_full_original_witness(self):
        directory = self.root / 'bundle'; directory.mkdir()
        owner = self.m._open_directory(directory, self.budget)
        self.addCleanup(self.m._close_owner, owner)
        self.assertIs(type(owner), self.m._DirectoryOwner)
        self.assertTrue(stat.S_ISDIR(owner.fd_witness.mode))
        original = owner.fd_witness
        (directory / 'extra').write_bytes(b'new child')
        self.refuse('bundle_changed', self.m._recheck_owner, owner, self.budget,
                    changed_code='bundle_changed')
        self.assertIs(owner.fd_witness, original)

    def test_close_releases_ownership_and_does_not_close_later_reused_fd(self):
        owner = self.open_file(); descriptors = (owner.fd, owner.parent_fd)
        self.m._close_owner(owner)
        self.assertTrue(owner.retired)
        self.assertEqual(owner.fd, -1); self.assertEqual(owner.parent_fd, -1)
        self.assertIsNone(owner._argument)
        self.assertIsNone(owner.normalized_path)
        for descriptor in descriptors:
            self.assert_closed(descriptor)
        foreign = os.open(self.path, os.O_RDONLY)
        try:
            self.assertIn(foreign, descriptors)
            self.m._close_owner(owner)
            self.assertTrue(stat.S_ISREG(os.fstat(foreign).st_mode))
        finally:
            os.close(foreign)
        self.assertTrue(self.path.exists())

    def test_owner_reinitialization_and_unacquired_values_refuse_without_close(self):
        owner = self.open_file(); descriptor = owner.fd
        self.refuse('unsafe_path', owner.__init__)
        self.assertEqual(os.fstat(descriptor).st_ino, owner.fd_witness.inode)
        self.refuse('unsafe_path', self.m._recheck_owner, object.__new__(self.m._FileOwner),
                    self.budget, changed_code='source_changed')
        self.refuse('unsafe_path', self.m._close_owner, object())
        self.refuse('unsafe_path', self.m._recheck_owner, owner, self.budget,
                    changed_code='unapproved_message')
        with self.assertRaises(AttributeError):
            owner.fd = 123

    def test_fstat_setup_failure_closes_every_immediately_registered_fd(self):
        original_open, original_fstat = os.open, os.fstat
        opened = []; regular = set()
        def opened_fd(name, flags, *args, **kwargs):
            descriptor = original_open(name, flags, *args, **kwargs)
            opened.append(descriptor)
            if not flags & os.O_DIRECTORY:
                regular.add(descriptor)
            return descriptor
        def failed_stat(descriptor):
            if descriptor in regular:
                raise OSError(errno.EIO, 'benign setup failure')
            return original_fstat(descriptor)
        with patch.object(os, 'open', opened_fd), patch.object(os, 'fstat', failed_stat):
            self.refuse('io_error', self.m._open_regular, self.path, self.budget)
        self.assertTrue(regular)
        for descriptor in set(opened):
            self.assert_closed(descriptor)

    def test_primary_cancellation_survives_secondary_close_error(self):
        class Cancel(BaseException):
            pass
        marker = Cancel('owned test cancellation')
        original_open, original_fstat, original_close = os.open, os.fstat, os.close
        opened = []; regular = set(); close_failed = False
        def opened_fd(name, flags, *args, **kwargs):
            descriptor = original_open(name, flags, *args, **kwargs); opened.append(descriptor)
            if not flags & os.O_DIRECTORY:
                regular.add(descriptor)
            return descriptor
        def cancelled_stat(descriptor):
            if descriptor in regular:
                raise marker
            return original_fstat(descriptor)
        def close_then_fail(descriptor):
            nonlocal close_failed
            original_close(descriptor)
            if descriptor in regular and not close_failed:
                close_failed = True
                raise OSError(errno.EIO, 'benign close failure after retire')
        with patch.object(os, 'open', opened_fd), patch.object(os, 'fstat', cancelled_stat), \
             patch.object(os, 'close', close_then_fail):
            with self.assertRaises(Cancel) as caught:
                self.m._open_regular(self.path, self.budget)
        self.assertIs(caught.exception, marker)
        self.assertTrue(close_failed)
        for descriptor in set(opened):
            self.assert_closed(descriptor)

    def test_close_reentry_is_idempotent_during_the_actual_close(self):
        owner = self.open_file(); original_close = os.close; seen = []
        def reentered_close(descriptor):
            seen.append(descriptor)
            self.m._close_owner(owner)
            original_close(descriptor)
        with patch.object(os, 'close', reentered_close):
            self.m._close_owner(owner)
        self.assertEqual(len(seen), 2)
        self.assertEqual(len(set(seen)), 2)

    def test_budget_failure_precedes_any_acquisition_and_logical_route_has_no_clock(self):
        cancelled = _CancellationState(); cancelled._latch(15)
        with patch.object(os, 'open', side_effect=AssertionError('acquisition before checkpoint')):
            failure = self.refuse('interrupted', self.m._open_regular, self.path,
                                   LogicalOnlyBudget(cancelled))
            self.assertEqual(failure.exit_code, 143)
            self.refuse('operation_timeout', self.m._open_regular, self.path,
                        Deadline(0, _CancellationState()))
        budget_module = importlib.import_module('replicatetable._native_budget_state')
        with patch.object(budget_module, 'monotonic_ns', side_effect=AssertionError('logical clock')):
            owner = self.open_file()
            self.m._recheck_owner(owner, self.budget, changed_code='source_changed')
            self.m._close_owner(owner)
