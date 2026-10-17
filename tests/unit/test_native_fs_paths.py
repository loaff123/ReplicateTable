"""Finite stock path qualification; no filesystem or native source authority.

The regressions detect pre-copy path/state overflow, user hook invocation,
cache mutation, cache-as-authority, and changed stock POSIX normalization.
"""
import importlib
import pathlib
import sys
import tracemalloc
import unittest
from unittest.mock import patch

from replicatetable.errors import Refusal


SLOTS = ('_raw_paths', '_drv', '_root', '_tail_cached', '_str',
         '_str_normcase_cached', '_parts_normcase_cached')
if sys.version_info[:2] == (3, 12):
    SLOTS += ('_lines_cached',)
SLOTS += ('_hash',)


def stored(path):
    out = {}
    for slot in SLOTS:
        try:
            out[slot] = object.__getattribute__(path, slot)
        except AttributeError:
            pass
    return out


def retained_bytes(path):
    total = sys.getsizeof(path)
    for value in stored(path).values():
        total += sys.getsizeof(value)
        if type(value) is list:
            total += sum(sys.getsizeof(item) for item in value)
    return total


def at_state_limit(extra=0):
    path = pathlib.PosixPath()
    count = (65536 - 2048) // (sys.getsizeof('') + 8)
    path._raw_paths = [''] * count + ['', '/safe']
    padding = 65536 + extra - retained_bytes(path)
    if not 0 <= padding <= 4095:
        raise AssertionError('Boundary fixture no longer matches pinned profile')
    path._raw_paths[-2] = 'a' * padding
    if retained_bytes(path) != 65536 + extra:
        raise AssertionError('Boundary fixture is not exact')
    return path


class NativeFilesystemPathTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('replicatetable._native_fs')
        self.assertTrue(callable(getattr(self.module, '_qualify_path', None)),
                        'The approved private path qualification is missing')
        self.assertTrue(callable(getattr(self.module, '_path_state_bytes', None)),
                        'The approved private retained-state preflight is missing')

    def qualify(self, value):
        return self.module._qualify_path(value)

    def refuse(self, value):
        with self.assertRaises(Refusal) as caught:
            self.qualify(value)
        self.assertEqual(caught.exception.code, 'unsafe_path')
        self.assertLessEqual(len(caught.exception.message.encode('ascii')), 512)
        return caught.exception

    def test_exact_strings_keep_stock_posix_meaning(self):
        cases = {'': '.', '.': '.', './': '.', 'a//./b/': 'a/b',
                 'a/../b': 'a/../b', '../a': '../a', '/': '/',
                 '//': '//', '///': '/', '////a//b': '/a/b',
                 '//a/./b/': '//a/b', '-a': '-a', 'a\\b': 'a\\b',
                 ' a /b\n': ' a /b\n', 'é/🦀': 'é/🦀'}
        for value, expected in cases.items():
            with self.subTest(value=value):
                actual = self.qualify(value)
                self.assertIs(type(actual), str)
                self.assertEqual(actual, expected)

    def test_posixpath_join_normalization_matches_stock(self):
        cases = [(), ('',), ('a', 'b'), ('a/', '', 'b'), ('a', ''),
                 ('a', '/b', 'c'), ('/', 'a'), ('//', 'a'),
                 ('a', '///b'), ('./a', '..', 'b'), ('é', '🦀')]
        for parts in cases:
            with self.subTest(parts=parts):
                expected = str(pathlib.PosixPath(*parts))
                value = pathlib.PosixPath(*parts)
                before = stored(value)
                self.assertEqual(self.qualify(value), expected)
                self.assertEqual(stored(value), before)

    def test_refuses_nonexact_paths_without_calling_hooks(self):
        class PathHook:
            def __fspath__(self):
                raise AssertionError('untrusted fspath invoked')
            def __str__(self):
                raise AssertionError('untrusted str invoked')
            def __eq__(self, other):
                raise AssertionError('untrusted equality invoked')
        class StringSubclass(str):
            def __str__(self):
                raise AssertionError('subclass str invoked')
        class PathSubclass(pathlib.PosixPath):
            def __fspath__(self):
                raise AssertionError('subclass fspath invoked')
        for value in (None, b'a', 1, True, PathHook(), StringSubclass('a'),
                      PathSubclass('a'), pathlib.PurePosixPath('a')):
            self.refuse(value)

    def test_rejects_nul_and_surrogates_before_encoding(self):
        for value in ('a\0b', '\ud800', '\udfff', 'a/\udc80'):
            self.refuse(value)
            self.refuse(pathlib.PosixPath(value))

    def test_raw_utf8_limit_equality_and_plus_one(self):
        for text in ('a' * 4095, 'é' * 2047 + 'a', '🦀' * 1023 + 'abc'):
            self.assertEqual(len(text.encode('utf-8')), 4095)
            self.assertEqual(self.qualify(text), text)
            self.assertEqual(self.qualify(pathlib.PosixPath(text)), text)
            self.refuse(text + 'a')
            self.refuse(pathlib.PosixPath(text + 'a'))

    def test_oversized_character_length_refuses_before_any_text_scan(self):
        # Every codepoint uses at least one UTF-8 byte. This known overflow must
        # be rejected before UTF-8 iteration or searching an arbitrary tail.
        for value in ('a' * 4096, pathlib.PosixPath('a' * 4096)):
            with patch.object(self.module, 'utf8_length',
                              side_effect=AssertionError('oversized text scanned')):
                self.refuse(value)

    def test_joined_utf8_limit_precedes_normalization(self):
        accepted = pathlib.PosixPath('a' * 2047, 'b' * 2047)
        self.assertEqual(len(self.qualify(accepted).encode('utf-8')), 4095)
        self.refuse(pathlib.PosixPath('a' * 2048, 'b' * 2047))
        self.refuse(pathlib.PosixPath('a', './' * 2047))
        self.refuse('a' + '/.' * 2048)

    def test_raw_discarded_prefix_still_qualifies(self):
        self.refuse(pathlib.PosixPath('x' * 4096, '/safe'))
        self.refuse(pathlib.PosixPath('\ud800', '/safe'))
        self.assertEqual(self.qualify(pathlib.PosixPath('x' * 4095, '/safe')),
                         '/safe')

    def test_final_join_respects_absolute_reset_without_extra_narrowing(self):
        value = pathlib.PosixPath('x' * 3000, 'y' * 3000, '/safe')
        self.assertEqual(self.qualify(value), '/safe')

    def test_retained_state_exact_64k_and_plus_one(self):
        accepted = at_state_limit()
        self.assertEqual(self.module._path_state_bytes(accepted), 65536)
        self.assertEqual(self.qualify(accepted), '/safe')
        rejected = at_state_limit(1)
        self.refuse(rejected)
        with self.assertRaises(Refusal) as caught:
            self.module._path_state_bytes(rejected)
        self.assertEqual(caught.exception.code, 'unsafe_path')

    def test_list_capacity_is_part_of_precopy_retained_state(self):
        compact = pathlib.PosixPath()
        compact._raw_paths = [''] * 1220
        self.assertLess(retained_bytes(compact), 65536)
        self.assertEqual(self.qualify(compact), '.')
        spare = [''] * 2440
        del spare[1220:]
        value = pathlib.PosixPath()
        value._raw_paths = spare
        self.assertGreater(sys.getsizeof(spare), sys.getsizeof(compact._raw_paths))
        self.assertGreater(retained_bytes(value), 65536)
        before = sys.getsizeof(spare)
        self.refuse(value)
        self.assertEqual(sys.getsizeof(spare), before)

    def test_all_cached_occurrences_are_counted_without_alias_credit(self):
        value = pathlib.PosixPath('a/b')
        str(value); hash(value); value._parts_normcase
        if sys.version_info[:2] == (3, 12):
            value._lines
        self.assertEqual(self.module._path_state_bytes(value), retained_bytes(value))
        self.assertEqual(self.qualify(value), 'a/b')

    def test_stock_caches_remain_identical_and_unmodified(self):
        value = pathlib.PosixPath('//é/./a\n/b')
        expected = str(value)
        hash(value); value._parts_normcase
        if sys.version_info[:2] == (3, 12):
            value._lines
        before = stored(value)
        self.assertEqual(self.qualify(value), expected)
        after = stored(value)
        self.assertEqual(before, after)
        for slot, item in before.items():
            self.assertIs(after[slot], item)

    def test_uncached_conversion_never_calls_public_path_properties(self):
        value = pathlib.PosixPath('a', '.', 'b')
        before = stored(value)
        with patch.object(pathlib.PosixPath, '__str__', side_effect=AssertionError), \
             patch.object(pathlib.PosixPath, '__fspath__', side_effect=AssertionError), \
             patch.object(pathlib.PosixPath, 'parts', property(lambda self: self.fail())):
            self.assertEqual(self.qualify(value), 'a/b')
        self.assertEqual(stored(value), before)

    def test_present_text_caches_must_match_raw_meaning(self):
        for slot in ('_drv', '_root', '_str', '_str_normcase_cached'):
            value = pathlib.PosixPath('a/b')
            str(value)
            object.__setattr__(value, slot, 'different')
            self.refuse(value)
        if sys.version_info[:2] == (3, 12):
            value = pathlib.PosixPath('a/b')
            value._lines_cached = 'wrong'
            self.refuse(value)

    def test_present_sequence_and_hash_caches_must_match_raw_meaning(self):
        for slot in ('_tail_cached', '_parts_normcase_cached'):
            for content in ([], ['a'], ['a', 'wrong'], ['a', 'b', 'extra']):
                value = pathlib.PosixPath('a/b')
                object.__setattr__(value, slot, content)
                self.refuse(value)
        value = pathlib.PosixPath('a/b')
        value._hash = 0 if hash('a/b') != 0 else 1
        self.refuse(value)

    def test_closed_slot_types_before_any_value_comparison(self):
        class Hook:
            def __eq__(self, other):
                raise AssertionError('cache equality invoked')
            def __sizeof__(self):
                raise AssertionError('cache sizeof invoked')
        for slot in SLOTS:
            value = pathlib.PosixPath('a/b')
            object.__setattr__(value, slot, Hook())
            self.refuse(value)
        for slot in ('_raw_paths', '_tail_cached', '_parts_normcase_cached'):
            value = pathlib.PosixPath('a')
            object.__setattr__(value, slot, [Hook()])
            self.refuse(value)
        for invalid_hash in (True, 1 << 80, -(1 << 80)):
            value = pathlib.PosixPath('a')
            value._hash = invalid_hash
            self.refuse(value)

    def test_uninitialized_exact_path_refuses(self):
        self.refuse(object.__new__(pathlib.PosixPath))
        with self.assertRaises(Refusal):
            self.module._path_state_bytes('a')

    def test_valid_partial_str_cache_is_not_rejected(self):
        value = pathlib.PosixPath('a/./b')
        value._str = 'a/b'
        before = stored(value)
        self.assertEqual(self.qualify(value), 'a/b')
        self.assertEqual(stored(value), before)

    def test_many_components_stay_in_existing_normalization_workspace(self):
        value = 'a/' * 2047 + 'a'
        self.qualify('a')
        tracemalloc.start()
        try:
            actual = self.qualify(value)
            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(actual, value)
        self.assertLess(current, 65536)
        self.assertLess(peak, 65536)
        # This measures one bounded path helper, never whole-call admission/RSS.

    def test_refusal_does_not_mutate_a_bad_existing_cache(self):
        value = pathlib.PosixPath('secret/input')
        value._str = 'different'
        before = stored(value)
        failure = self.refuse(value)
        self.assertEqual(stored(value), before)
        self.assertNotIn('secret', failure.message)
        self.assertNotIn('different', failure.message)
