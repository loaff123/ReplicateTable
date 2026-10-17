"""Ordinary owned-FD cleanup releases exception locals without forced GC."""
import errno
import os
from pathlib import PosixPath
import sys
import tempfile
import unittest
from unittest.mock import patch

from replicatetable import _native_fs_owners as owners
from replicatetable._native_budget_state import _CancellationState, LogicalOnlyBudget
from replicatetable.errors import Refusal


class OwnerCleanupLifetimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='replicatetable-owner-cleanup-')
        self.addCleanup(temporary.cleanup)
        self.directory = PosixPath(temporary.name)
        self.input = self.directory / 'input.bin'
        self.input.write_bytes(b'benign cleanup fixture')
        self.budget = LogicalOnlyBudget(_CancellationState())

    def assert_retired(self, owner, descriptors):
        self.assertTrue(owner.retired)
        self.assertEqual((owner.fd, owner.parent_fd), (-1, -1))
        for descriptor in descriptors:
            try:
                os.fstat(descriptor)
            except OSError as error:
                self.assertEqual(error.errno, errno.EBADF)
            else:
                self.fail('Original descriptor remains open')

    def assert_no_error_backreference(self, secondary):
        node = secondary.__traceback__
        found = False
        while node is not None:
            frame = node.tb_frame
            if frame.f_code is owners._close_owner.__code__:
                found = True
                self.assertIsNot(frame.f_locals.get('first_error'), secondary)
            node = node.tb_next
        self.assertTrue(found)

    def test_cleanup_clears_first_error_on_suppression_conversion_and_propagation(self):
        real_close = os.close
        for directory in (False, True):
            for mode in ('quiet', 'convert', 'propagate'):
                with self.subTest(directory=directory, mode=mode):
                    opener = owners._open_directory if directory else owners._open_regular
                    owner = opener(self.directory if directory else self.input, self.budget)
                    self.addCleanup(owners._close_quietly, owner)
                    descriptors = (owner.fd, owner.parent_fd)
                    closed = []
                    captured = []

                    def close_then_fail(descriptor):
                        self.assertIn(descriptor, descriptors)
                        real_close(descriptor)
                        closed.append(descriptor)
                        error = (RuntimeError('first fixture') if mode == 'propagate' and not captured
                                 else OSError(errno.EIO, 'close fixture'))
                        captured.append(error)
                        raise error

                    # Plain handlers are essential: unittest.assertRaises
                    # clears returned traceback frames and would mask this bug.
                    with patch.object(os, 'close', close_then_fail):
                        if mode == 'quiet':
                            owners._close_quietly(owner)
                        elif mode == 'convert':
                            try:
                                owners._close_owner(owner)
                            except Refusal as error:
                                self.assertEqual((error.code, error.exit_code), ('io_error', 3))
                            else:
                                self.fail('Expected operational close failure')
                        else:
                            try:
                                owners._close_owner(owner)
                            except RuntimeError as error:
                                self.assertIs(error, captured[0])
                            else:
                                self.fail('Expected original first failure')
                    self.assertEqual(tuple(closed), descriptors)
                    self.assertEqual(len(captured), 2)
                    self.assert_retired(owner, descriptors)
                    owners._close_owner(owner)
                    for secondary in captured:
                        self.assert_no_error_backreference(secondary)
        self.assertEqual(self.input.read_bytes(), b'benign cleanup fixture')

    def test_quiet_cleanup_keeps_the_active_primary_without_retaining_secondary(self):
        owner = owners._open_regular(self.input, self.budget)
        self.addCleanup(owners._close_quietly, owner)
        descriptors = (owner.fd, owner.parent_fd)
        captured = []
        real_close = os.close

        def close_then_fail(descriptor):
            self.assertIn(descriptor, descriptors)
            real_close(descriptor)
            error = OSError(errno.EIO, 'secondary fixture')
            captured.append(error)
            raise error

        try:
            raise RuntimeError('primary fixture')
        except RuntimeError as primary:
            with patch.object(os, 'close', close_then_fail):
                owners._close_quietly(owner)
            self.assertIs(sys.exception(), primary)
            self.assertEqual(str(primary), 'primary fixture')
        self.assertEqual(len(captured), 2)
        self.assert_retired(owner, descriptors)
        for secondary in captured:
            self.assert_no_error_backreference(secondary)
        self.assertEqual(self.input.read_bytes(), b'benign cleanup fixture')


if __name__ == '__main__':
    unittest.main()
