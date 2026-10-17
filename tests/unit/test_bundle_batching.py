"""Three-lane batching against real stage appends; no commit assertion."""
import gc
import hashlib
import importlib
import os
from pathlib import PosixPath
import sys
import tempfile
import unittest
from unittest.mock import patch

from replicatetable import _native_fs_generated as roots
from replicatetable import _native_workspace as workspace
from replicatetable._native_budget_state import LogicalOnlyBudget, _CancellationState
from replicatetable.errors import Refusal


class Charges:
    """Test observation only; grants no source, path, stage or commit authority."""
    def __init__(self):
        self.count = 0
        self.sha = hashlib.sha256()
        self.last = None
    def feed(self, chunk):
        self.count += len(chunk)
        self.sha.update(chunk)
        self.last = chunk


class BundleBatchingTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('replicatetable.bundle')
        self.native = importlib.import_module('replicatetable._native_stage')
        temporary = tempfile.TemporaryDirectory(prefix='rt-batch-', dir='/tmp')
        self.addCleanup(temporary.cleanup)
        self.directory = PosixPath(temporary.name)
        self.budget = LogicalOnlyBudget(_CancellationState())
        self.root = roots._prepare_stage_root(self.directory / 'output', (), self.budget)
        self.addCleanup(roots._close_generated_root, self.root)
        workspace._create_generated_root(self.root, self.budget)
        self.writer = self.native._begin_stage_writer(self.root, 'plan', self.budget)
        self.addCleanup(self.native._close_stage_writer, self.writer, quiet=True)

    def test_empty_partial_exact_full_and_crossing_fragments_have_exact_real_bytes(self):
        # Each independent temp setup uses actual exclusive stage acquisition.
        cases = ((), (b'',), (b'abc',), (b'x'*65536,),
                 (b'ab', b'x'*65536, b'y'*65536, b'z'))
        for number, fragments in enumerate(cases):
            if number:
                self.native._close_stage_writer(self.writer)
                roots._close_generated_root(self.root)
                self.root = roots._prepare_stage_root(self.directory / ('output'+str(number)), (), self.budget)
                self.addCleanup(roots._close_generated_root, self.root)
                workspace._create_generated_root(self.root, self.budget)
                self.writer = self.native._begin_stage_writer(self.root, 'plan', self.budget)
                self.addCleanup(self.native._close_stage_writer, self.writer, quiet=True)
            expected = b''.join(fragments)
            self.native._open_stage_member(self.writer, 'plan.json', len(expected), self.budget)
            charge = Charges()
            observed = []
            original = self.native._append_stage_member
            def append(writer, chunk, budget):
                self.assertIs(charge.last, chunk)
                self.assertLessEqual(len(chunk), 65536)
                self.assertGreater(len(chunk), 0)
                observed.append(len(chunk))
                charge.last = None
                return original(writer, chunk, budget)
            with patch.object(self.native, '_append_stage_member', append):
                self.m._batch_chunks(self.writer, iter(fragments), charge, self.budget)
            witness = self.native._finish_stage_member(self.writer, self.budget)
            self.assertEqual(witness.size, len(expected))
            self.assertEqual(charge.count, len(expected))
            self.assertEqual(charge.sha.hexdigest(), hashlib.sha256(expected).hexdigest())
            self.assertEqual((self.directory/self.root.name/'plan.json').read_bytes(), expected)
            self.assertEqual(observed, [65536]*(len(expected)//65536) + ([len(expected)%65536] if len(expected)%65536 else []))

    def test_nonexact_or_overlong_fragments_refuse_before_any_append(self):
        self.native._open_stage_member(self.writer, 'plan.json', 200000, self.budget)
        for bad in (bytearray(b'x'), 'x', b'x'*65537):
            charge = Charges()
            with self.subTest(kind=type(bad).__name__), \
                    patch.object(self.native, '_append_stage_member', side_effect=AssertionError('bad fragment append')):
                with self.assertRaises(Refusal) as raised:
                    self.m._batch_chunks(self.writer, iter((bad,)), charge, self.budget)
                self.assertEqual(raised.exception.code, 'invalid_bundle')
                self.assertEqual(charge.count, 0)
        self.assertEqual(os.fstat(self.writer.current_fd).st_size, 0)

    def test_bounded_short_writes_do_not_repeat_precharge(self):
        expected = b'abcdefghi'
        self.native._open_stage_member(self.writer, 'plan.json', len(expected), self.budget)
        charge = Charges()
        original = os.write
        writes = []
        def short(fd, data):
            writes.append(fd)
            return original(fd, data[:2])
        with patch.object(os, 'write', short):
            self.m._batch_chunks(self.writer, iter((expected,)), charge, self.budget)
        self.assertEqual(len(writes), 5)
        self.assertEqual(charge.count, len(expected))
        self.assertEqual((self.directory/self.root.name/'plan.json').read_bytes(), expected)

    def test_partial_conversion_headers_and_managed_control_fit_existing_cells(self):
        backing = bytearray(65536)
        whole = memoryview(backing)
        prefix = whole[:7]
        try:
            self.assertLessEqual(sys.getsizeof(backing)-len(backing), 128)
            self.assertLessEqual(sys.getsizeof(bytes(backing))-len(backing), 128)
            self.assertLessEqual(sys.getsizeof(whole), 512)
            self.assertLessEqual(sys.getsizeof(prefix), 512)
            refs = gc.get_referents(whole)
            self.assertEqual(len(refs), 1)
            self.assertLessEqual(sys.getsizeof(refs[0]), 512)
            self.assertEqual(gc.get_referents(refs[0]), [backing])
        finally:
            prefix.release()
            whole.release()
        self.assertEqual(self.m._partial_bytes(backing, 7), bytes(7))
        backing.extend(b'x')  # No outstanding conversion view remains.
