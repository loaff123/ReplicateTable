"""Prepared generated roots, without creation, worker or commit authority."""
import errno
import fcntl
import importlib
import os
import pathlib
import stat
import tempfile
import unittest
from unittest.mock import patch

from replicatetable.errors import Refusal
from replicatetable import _native_fs_owners as owners
from replicatetable._native_budget_state import _CancellationState, LogicalOnlyBudget


def fd_snapshot():
    result = {}
    for name in os.listdir('/proc/self/fd'):
        descriptor = int(name)
        try:
            observed = os.fstat(descriptor)
        except OSError as error:
            if error.errno == errno.EBADF:
                continue
            raise
        result[descriptor] = (observed.st_dev, observed.st_ino, observed.st_mode)
    return result


class PreparedGeneratedRootTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('replicatetable._native_fs_generated')
        for name in ('_GeneratedRoot', '_prepare_stage_root', '_prepare_workspace_root',
                     '_recheck_root_parent', '_close_generated_root',
                     '_parent_ancestor_steps'):
            self.assertTrue(callable(getattr(self.m, name, None)),
                            'Frozen generated-root interface is missing: ' + name)
        self.temp = tempfile.TemporaryDirectory(prefix='replicatetable-prepared-root-')
        self.addCleanup(self.temp.cleanup)
        self.directory = pathlib.PosixPath(self.temp.name)
        self.input_path = self.directory / 'input.bin'
        self.input_path.write_bytes(b'benign owned input')
        self.output_path = self.directory / 'result.bundle'
        self.budget = LogicalOnlyBudget(_CancellationState())
        # Stock entropy setup finishes before any product-owned FD comparison.
        os.urandom(1)

    def refuse(self, code, function, *args):
        with self.assertRaises(Refusal) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn(self.temp.name, caught.exception.message)
        return caught.exception

    def stage(self, path=None, protected=()):
        value = self.output_path if path is None else path
        root = self.m._prepare_stage_root(value, protected, self.budget)
        self.addCleanup(self.m._close_generated_root, root)
        return root

    def workspace(self, stage=None, protected=()):
        root = self.m._prepare_workspace_root(stage, protected, self.budget)
        self.addCleanup(self.m._close_generated_root, root)
        return root

    def input_owner(self, path=None, directory=False):
        value = self.input_path if path is None else path
        opener = owners._open_directory if directory else owners._open_regular
        owner = opener(value, self.budget)
        self.addCleanup(owners._close_owner, owner)
        return owner

    def assert_closed(self, descriptor):
        with self.assertRaises(OSError) as caught:
            os.fstat(descriptor)
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def assert_prepared(self, root, kind):
        self.assertIs(type(root), self.m._GeneratedRoot)
        self.assertEqual(root.kind, kind)
        self.assertEqual(root.fd, -1)
        self.assertIsNone(root.created_identity)
        self.assertIsNone(root.sealed_witness)
        self.assertFalse(root.committed)
        self.assertFalse(root.retired)
        parent = os.fstat(root.parent_fd)
        self.assertTrue(stat.S_ISDIR(parent.st_mode))
        self.assertEqual(root.parent_identity.device, parent.st_dev)
        self.assertEqual(root.parent_identity.inode, parent.st_ino)
        self.assertEqual(root.parent_identity.mode, parent.st_mode)
        self.assertEqual(fcntl.fcntl(root.parent_fd, fcntl.F_GETFL) & os.O_ACCMODE,
                         os.O_RDONLY)
        self.assertTrue(fcntl.fcntl(root.parent_fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC)

    def test_stage_has_one_parent_anchor_and_no_created_root_or_payload_read(self):
        before = set(os.listdir(self.directory))
        with (patch.object(os, 'mkdir', side_effect=AssertionError('root creation')),
              patch.object(os, 'read', side_effect=AssertionError('payload read')),
              patch.object(os, 'urandom', return_value=b'\x01' * 16)):
            root = self.stage()
        self.assert_prepared(root, 'stage')
        self.assertIs(root.original_argument, self.output_path)
        self.assertEqual(root.path_description, str(self.directory))
        self.assertEqual(root.destination_name, 'result.bundle')
        self.assertEqual(root.name, '.replicatetable-stage-' + '01' * 16)
        self.assertEqual(set(os.listdir(self.directory)), before)
        self.assertEqual(self.input_path.read_bytes(), b'benign owned input')
        self.assertFalse(self.output_path.exists())

    def test_workspace_duplicates_stage_parent_without_a_second_path_description(self):
        stage = self.stage()
        before = set(os.listdir(self.directory))
        with patch.object(os, 'mkdir', side_effect=AssertionError('root creation')):
            work = self.workspace(stage)
        self.assert_prepared(work, 'workspace')
        self.assertNotEqual(work.parent_fd, stage.parent_fd)
        self.assertEqual(work.parent_identity, stage.parent_identity)
        self.assertIsNone(work.original_argument)
        self.assertIsNone(work.path_description)
        self.assertIsNone(work.destination_name)
        self.assertRegex(work.name, r'\A\.replicatetable-work-[0-9a-f]{32}\Z')
        self.assertEqual(len(work.name), 53)
        self.assertEqual(set(os.listdir(self.directory)), before)

    def test_standalone_workspace_uses_fixed_tmp_and_ignores_tmpdir(self):
        with (patch.dict(os.environ, {'TMPDIR': str(self.directory)}),
              patch.object(os, 'mkdir', side_effect=AssertionError('root creation'))):
            work = self.workspace()
        self.assert_prepared(work, 'workspace')
        self.assertEqual(work.original_argument, '/tmp')
        self.assertEqual(work.path_description, '/tmp')
        self.assertIsNone(work.destination_name)
        actual = os.stat('/tmp', follow_symlinks=False)
        self.assertEqual((work.parent_identity.device, work.parent_identity.inode),
                         (actual.st_dev, actual.st_ino))

    def test_relative_and_double_slash_parent_descriptions_keep_frozen_meaning(self):
        original_cwd = os.open('.', os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.chdir(self.directory)
            argument = pathlib.PosixPath('./result.bundle')
            root = self.stage(argument)
        finally:
            os.fchdir(original_cwd)
            os.close(original_cwd)
        self.assertIs(root.original_argument, argument)
        self.assertEqual(root.path_description, str(self.directory))
        double = self.stage('/' + str(self.output_path))
        self.assertEqual(double.path_description, '/' + str(self.directory))
        self.m._recheck_root_parent(root, self.budget)
        self.m._recheck_root_parent(double, self.budget)

    def test_absolute_preparation_does_not_need_a_current_directory(self):
        original_cwd = os.open('.', os.O_RDONLY | os.O_DIRECTORY)
        abandoned = self.directory / 'abandoned'
        abandoned.mkdir()
        try:
            os.chdir(abandoned)
            abandoned.rmdir()
            root = self.stage()
        finally:
            os.fchdir(original_cwd)
            os.close(original_cwd)
        self.assertEqual(root.path_description, str(self.directory))

    def test_path_domain_and_raw_joined_caps_precede_open_or_entropy(self):
        class PathHook:
            def __fspath__(self):
                raise AssertionError('arbitrary fspath')

        with (patch.object(os, 'open', side_effect=AssertionError('unadmitted open')),
              patch.object(os, 'urandom', side_effect=AssertionError('unadmitted entropy'))):
            for value in (PathHook(), b'path', True, '/a\x00b', '/a\ud800', 'a' * 4096):
                self.refuse('unsafe_path', self.m._prepare_stage_root, value, (), self.budget)
            self.refuse('unsafe_path', self.m._prepare_stage_root, './' * 2047, (), self.budget)

    def test_protected_input_inode_alias_refuses_before_entropy(self):
        alias = self.directory / 'alias.bin'
        os.link(self.input_path, alias)
        source = self.input_owner()
        with patch.object(os, 'urandom', side_effect=AssertionError('unadmitted entropy')):
            self.refuse('source_output_overlap', self.m._prepare_stage_root,
                        alias, (source,), self.budget)
        self.assertEqual(source.fd_witness.nlink, 2)
        self.assertEqual(alias.read_bytes(), b'benign owned input')

    def test_ordinary_source_parent_can_also_be_the_output_parent(self):
        source = self.input_owner()
        root = self.stage(protected=(source,))
        self.assertEqual(root.parent_identity, source.parent_identity)
        self.assertEqual(self.input_path.read_bytes(), b'benign owned input')
        self.assert_prepared(root, 'stage')

    def test_dotdot_can_leave_a_protected_directory_before_the_actual_parent(self):
        protected_path = self.directory / 'protected'
        safe_path = self.directory / 'safe'
        protected_path.mkdir()
        safe_path.mkdir()
        protected = self.input_owner(protected_path, directory=True)
        absolute = str(self.directory) + '/protected/../safe/out'
        relative = 'protected/../safe/out'
        arguments = (absolute, pathlib.PosixPath(absolute),
                     '/' + absolute, pathlib.PosixPath('/' + absolute),
                     relative, pathlib.PosixPath(relative))
        original_cwd = os.open('.', os.O_RDONLY | os.O_DIRECTORY)
        before = set(os.listdir(self.directory))
        try:
            os.chdir(self.directory)
            for index, argument in enumerate(arguments):
                with self.subTest(case=index):
                    root = self.stage(argument, (protected,))
                    work = self.workspace(root, (protected,))
                    try:
                        self.assert_prepared(root, 'stage')
                        self.assertEqual(root.parent_identity.inode, os.stat(safe_path).st_ino)
                        expected = str(self.directory) + '/protected/../safe'
                        if index in (2, 3):
                            expected = '/' + expected
                        self.assertEqual(root.path_description, expected)
                        self.assertEqual(root.destination_name, 'out')
                        self.assertIsNone(work.path_description)
                        self.assertNotEqual(work.parent_fd, root.parent_fd)
                        self.assertEqual(work.parent_identity, root.parent_identity)
                        self.assertFalse(protected.retired)
                    finally:
                        self.m._close_generated_root(work)
                        self.m._close_generated_root(root)
        finally:
            os.fchdir(original_cwd)
            os.close(original_cwd)
        self.assertEqual(set(os.listdir(self.directory)), before)
        self.assertEqual(self.input_path.read_bytes(), b'benign owned input')

    def test_dotdot_ending_inside_the_protected_directory_still_refuses(self):
        protected_path = self.directory / 'protected'
        protected_path.mkdir()
        (self.directory / 'safe').mkdir()
        protected = self.input_owner(protected_path, directory=True)
        for suffix in ('safe/../protected/out', 'protected/../protected/out'):
            argument = str(self.directory) + '/' + suffix
            with patch.object(os, 'urandom', side_effect=AssertionError('unadmitted entropy')):
                self.refuse('source_output_overlap', self.m._prepare_stage_root,
                            argument, (protected,), self.budget)

    def test_symlink_followed_by_dotdot_is_not_lexically_cancelled(self):
        protected_path = self.directory / 'protected'
        protected_path.mkdir()
        (self.directory / 'safe').mkdir()
        (self.directory / 'link').symlink_to(protected_path, target_is_directory=True)
        argument = str(self.directory) + '/link/../safe/out'
        self.refuse('unsafe_path', self.m._prepare_stage_root, argument, (), self.budget)

    def test_workspace_rechecks_its_supplied_protection_set(self):
        stage = self.stage()
        protected = self.input_owner(self.directory, directory=True)
        with patch.object(os, 'urandom', side_effect=AssertionError('unadmitted entropy')):
            self.refuse('source_output_overlap', self.m._prepare_workspace_root,
                        stage, (protected,), self.budget)
        self.assertFalse(stage.retired)
        os.fstat(stage.parent_fd)

    def test_ancestor_step_bound_is_derived_from_the_complete_admitted_description(self):
        cases = {'/': 0, '//': 0, '/..': 0, '/../..': 0,
                 '/a': 1, '/a/b': 2, '/a/../b': 2, '//a/../b': 2,
                 '/../a/../b/..': 2, '/é/文': 2}
        maximum = '/' + 'a/' * 2046 + 'a'
        self.assertEqual(len(maximum), 4094)
        cases[maximum] = 2047
        cases[maximum + 'a'] = 2047
        cases['/' + maximum] = 2047
        with patch.object(os, 'open', side_effect=AssertionError('pure bound opened a path')):
            for path, expected in cases.items():
                actual = self.m._parent_ancestor_steps(path)
                self.assertIs(type(actual), int)
                self.assertEqual(actual, expected)
            for path in (None, True, pathlib.PosixPath('/a'), 'a/b', '/a//b',
                         '/a/./b', '/bad\x00', '/bad\ud800', maximum + 'aa'):
                self.refuse('unsafe_path', self.m._parent_ancestor_steps, path)

    def test_protected_directory_and_descendants_refuse_without_mutation(self):
        bundle = self.directory / 'protected'
        nested = bundle / 'inner'
        nested.mkdir(parents=True)
        protected = self.input_owner(bundle, directory=True)
        before = os.stat(bundle)
        for target in (bundle, bundle / 'out', nested / 'out'):
            with self.subTest(target=target.name):
                self.refuse('source_output_overlap', self.m._prepare_stage_root,
                            target, (protected,), self.budget)
        self.assertEqual(os.stat(bundle), before)
        self.assertEqual(set(os.listdir(bundle)), {'inner'})

    def test_standalone_workspace_refuses_a_protected_tmp_parent(self):
        # Only read-only directory authority is acquired; no tmp entries are read or changed.
        protected = self.input_owner('/tmp', directory=True)
        with patch.object(os, 'urandom', side_effect=AssertionError('unadmitted entropy')):
            self.refuse('source_output_overlap', self.m._prepare_workspace_root,
                        None, (protected,), self.budget)

    def test_existing_output_file_and_directory_are_never_replaced(self):
        folder = self.directory / 'existing'
        folder.mkdir()
        before = self.input_path.read_bytes()
        for target in (self.input_path, folder):
            self.refuse('output_exists', self.m._prepare_stage_root, target, (), self.budget)
        self.assertEqual(self.input_path.read_bytes(), before)
        self.assertTrue(folder.is_dir())

    def test_symlink_destination_and_parent_refuse(self):
        leaf = self.directory / 'leaf'
        leaf.symlink_to(self.input_path)
        parent = self.directory / 'parent-link'
        parent.symlink_to(self.directory, target_is_directory=True)
        for target in (leaf, parent / 'out'):
            self.refuse('unsafe_path', self.m._prepare_stage_root, target, (), self.budget)

    def test_protected_owner_domain_is_exact_and_finite(self):
        source = self.input_owner()

        class TupleSubclass(tuple):
            def __iter__(self):
                raise AssertionError('subclass iteration')

        with patch.object(os, 'open', side_effect=AssertionError('invalid protected set')):
            for value in ([source], TupleSubclass((source,)), (object(),), (source,) * 9):
                self.refuse('unsafe_path', self.m._prepare_stage_root,
                            self.output_path, value, self.budget)
        owners._close_owner(source)
        self.refuse('unsafe_path', self.m._prepare_stage_root,
                    self.output_path, (source,), self.budget)

    def test_original_parent_identity_survives_intended_parent_metadata_changes(self):
        root = self.stage()
        original_identity = root.parent_identity
        sibling = self.directory / 'owned-sibling'
        sibling.write_bytes(b'ordinary owned sibling')
        self.m._recheck_root_parent(root, self.budget)
        self.assertIs(root.parent_identity, original_identity)

    def test_each_missing_protected_owner_slot_refuses_before_io(self):
        originals = (self.input_owner(), self.input_owner(self.directory, directory=True))
        before = fd_snapshot()
        for owner in originals:
            for missing in owners._Owner.__slots__:
                partial = object.__new__(type(owner))
                for field in owners._Owner.__slots__:
                    if field != missing:
                        object.__setattr__(partial, field, object.__getattribute__(owner, field))
                for factory, argument in ((self.m._prepare_stage_root, self.output_path),
                                          (self.m._prepare_workspace_root, None)):
                    with self.subTest(owner=type(owner).__name__, missing=missing,
                                      factory=factory.__name__):
                        with (patch.object(os, 'open', side_effect=AssertionError('partial open')),
                              patch.object(os, 'dup', side_effect=AssertionError('partial dup')),
                              patch.object(os, 'fstat', side_effect=AssertionError('partial fstat')),
                              patch.object(os, 'urandom', side_effect=AssertionError('partial entropy'))):
                            self.refuse('unsafe_path', factory, argument, (partial,), self.budget)
                del partial
        self.assertEqual(fd_snapshot(), before)
        for owner in originals:
            self.assertFalse(owner.retired)
            os.fstat(owner.fd)
            os.fstat(owner.parent_fd)

    def test_parent_path_replacement_refuses_without_refreshing_original_identity(self):
        parent = self.directory / 'parent'
        parent.mkdir()
        root = self.stage(parent / 'out')
        original_identity = root.parent_identity
        moved = self.directory / 'moved-parent'
        parent.rename(moved)
        parent.mkdir()
        self.refuse('unsafe_path', self.m._recheck_root_parent, root, self.budget)
        self.assertIs(root.parent_identity, original_identity)
        self.assertEqual(os.fstat(root.parent_fd).st_ino, original_identity.inode)

    def test_workspace_does_not_retain_or_borrow_stage_fd_closing_authority(self):
        stage = self.stage()
        work = self.workspace(stage)
        stage_fd, work_fd = stage.parent_fd, work.parent_fd
        self.m._close_generated_root(stage)
        self.assert_closed(stage_fd)
        self.assertEqual(os.fstat(work_fd).st_ino, work.parent_identity.inode)
        self.m._recheck_root_parent(work, self.budget)
        self.refuse('unsafe_path', self.m._prepare_workspace_root, stage, (), self.budget)

    def test_closed_root_refuses_reuse_but_close_is_idempotent_and_fd_only(self):
        root = self.stage()
        descriptor = root.parent_fd
        before = set(os.listdir(self.directory))
        self.m._close_generated_root(root)
        self.assertTrue(root.retired)
        self.assertEqual(root.fd, -1)
        self.assertEqual(root.parent_fd, -1)
        self.assertIsNone(root.original_argument)
        self.assertIsNone(root.path_description)
        self.assertIsNone(root.destination_name)
        self.assertIsNone(root.name)
        self.assertIsNone(root.parent_identity)
        self.assert_closed(descriptor)
        self.m._close_generated_root(root)
        self.refuse('unsafe_path', self.m._recheck_root_parent, root, self.budget)
        self.assertEqual(set(os.listdir(self.directory)), before)

    def test_root_is_closed_immutable_nonreinitializable_and_not_scalar_authority(self):
        root = self.stage()
        self.assertFalse(hasattr(root, '__dict__'))
        for name, value in (('parent_fd', 42), ('committed', True), ('extra', 1)):
            with self.assertRaises(AttributeError):
                setattr(root, name, value)
        self.refuse('unsafe_path', self.m._GeneratedRoot)
        self.refuse('unsafe_path', root.__init__)
        with self.assertRaises(TypeError):
            type('DerivedRoot', (self.m._GeneratedRoot,), {})
        partial = object.__new__(self.m._GeneratedRoot)
        self.refuse('unsafe_path', self.m._close_generated_root, partial)
        self.refuse('unsafe_path', self.m._recheck_root_parent, partial, self.budget)
        self.refuse('unsafe_path', self.m._prepare_workspace_root, object(), (), self.budget)

    def test_fstat_setup_failure_closes_registered_fds_without_touching_inputs(self):
        before = fd_snapshot()
        with patch.object(os, 'fstat', side_effect=OSError(errno.EIO, 'owned fixture failure')):
            error = self.refuse('io_error', self.m._prepare_stage_root,
                                self.output_path, (), self.budget)
        self.assertEqual(error.exit_code, 3)
        self.assertEqual(fd_snapshot(), before)
        self.assertEqual(self.input_path.read_bytes(), b'benign owned input')
        self.assertFalse(self.output_path.exists())

    def test_entropy_failure_after_parent_acquisition_retires_only_owned_fds(self):
        before = fd_snapshot()
        with patch.object(os, 'urandom', side_effect=OSError(errno.EIO, 'owned fixture failure')):
            self.refuse('io_error', self.m._prepare_stage_root,
                        self.output_path, (), self.budget)
        self.assertEqual(fd_snapshot(), before)
        self.assertEqual(set(os.listdir(self.directory)), {'input.bin'})

    def test_workspace_setup_failure_never_closes_the_supplied_stage_parent(self):
        stage = self.stage()
        descriptor = stage.parent_fd
        identity = stage.parent_identity
        before = fd_snapshot()
        with patch.object(os, 'fstat', side_effect=OSError(errno.EIO, 'owned fixture failure')):
            self.refuse('io_error', self.m._prepare_workspace_root, stage, (), self.budget)
        self.assertFalse(stage.retired)
        self.assertEqual(stage.parent_fd, descriptor)
        self.assertEqual(os.fstat(descriptor).st_ino, identity.inode)
        self.assertEqual(fd_snapshot(), before)

    def test_entropy_oserror_always_maps_to_operational_io_error(self):
        stage = self.stage()
        for number in (errno.EIO, errno.ENOENT, errno.ENOTDIR, errno.ELOOP,
                       errno.ENAMETOOLONG, errno.EBADF):
            for factory, argument in ((self.m._prepare_stage_root, self.output_path),
                                      (self.m._prepare_workspace_root, stage)):
                with self.subTest(errno=number, factory=factory.__name__):
                    before = fd_snapshot()
                    with patch.object(os, 'urandom', side_effect=OSError(number, 'owned fixture')):
                        error = self.refuse('io_error', factory, argument, (), self.budget)
                    self.assertEqual(error.exit_code, 3)
                    self.assertEqual(fd_snapshot(), before)
                    self.assertFalse(stage.retired)
                    os.fstat(stage.parent_fd)
        self.assertEqual(self.input_path.read_bytes(), b'benign owned input')
        self.assertFalse(self.output_path.exists())

    def test_close_reentry_and_fd_reuse_never_close_the_replacement_descriptor(self):
        root = self.stage()
        descriptor = root.parent_fd
        real_close = os.close
        replacement = []

        def close_then_reenter(fd):
            real_close(fd)
            if fd == descriptor:
                opened = os.open(self.input_path, os.O_RDONLY)
                if opened != descriptor:
                    os.dup2(opened, descriptor, inheritable=False)
                    real_close(opened)
                replacement.append(descriptor)
                self.m._close_generated_root(root)

        try:
            with patch.object(os, 'close', close_then_reenter):
                self.m._close_generated_root(root)
            self.assertEqual(len(replacement), 1)
            self.assertEqual(os.fstat(replacement[0]).st_ino, os.stat(self.input_path).st_ino)
            self.m._close_generated_root(root)
            os.fstat(replacement[0])
        finally:
            for fd in replacement:
                real_close(fd)

    def test_cleanup_releases_secondary_error_local_on_every_exit(self):
        real_close = os.close
        for mode in ('quiet', 'convert', 'propagate'):
            with self.subTest(mode=mode):
                root = self.stage() if mode != 'quiet' else None
                captured = []
                cleanup_started = [mode != 'quiet']

                def entropy_primary(count):
                    self.assertEqual(count, 16)
                    cleanup_started[0] = True
                    raise RuntimeError('primary fixture')

                def close_then_fail(descriptor):
                    real_close(descriptor)
                    if cleanup_started[0]:
                        error = (RuntimeError('secondary fixture') if mode == 'propagate'
                                 else OSError(errno.EIO, 'secondary fixture'))
                        captured.append(error)
                        raise error

                with patch.object(os, 'close', close_then_fail):
                    if mode == 'quiet':
                        with patch.object(os, 'urandom', entropy_primary):
                            try:
                                self.m._prepare_stage_root(self.output_path, (), self.budget)
                            except RuntimeError as error:
                                self.assertEqual(str(error), 'primary fixture')
                            else:
                                self.fail('Primary failure did not propagate')
                    elif mode == 'convert':
                        try:
                            self.m._close_generated_root(root)
                        except Refusal as error:
                            self.assertEqual(error.code, 'io_error')
                            self.assertEqual(error.exit_code, 3)
                        else:
                            self.fail('Operational failure did not propagate')
                    else:
                        try:
                            self.m._close_generated_root(root)
                        except RuntimeError as error:
                            self.assertIs(error, captured[0])
                        else:
                            self.fail('Secondary failure did not propagate')
                self.assertEqual(len(captured), 1)
                found = False
                secondary = captured[0]
                node = secondary.__traceback__
                while node is not None:
                    frame = node.tb_frame
                    if frame.f_code is self.m._close_cells.__code__:
                        found = True
                        self.assertIsNot(frame.f_locals.get('failure'), secondary)
                    node = node.tb_next
                self.assertTrue(found)
                # Fixture retention permits inspecting a returned frame. Its
                # local must no longer point back to the same secondary error.
                # Plain handlers avoid unittest.assertRaises clearing frames.
                del node, frame, secondary, captured
        self.assertEqual(self.input_path.read_bytes(), b'benign owned input')
        self.assertFalse(self.output_path.exists())

    def test_logical_budget_avoids_clock_and_invalid_budget_precedes_acquisition(self):
        with patch('replicatetable._native_budget_state.monotonic_ns',
                   side_effect=AssertionError('logical route clock')):
            root = self.stage()
            self.m._recheck_root_parent(root, self.budget)
        with patch.object(os, 'open', side_effect=AssertionError('invalid budget open')):
            self.refuse('supervision_unavailable', self.m._prepare_stage_root,
                        self.output_path, (), object())


if __name__ == '__main__':
    unittest.main()
