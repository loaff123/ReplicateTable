"""Finite private path qualification for the approved v11 stock profiles.

The original argument remains caller-owned. This helper returns only one exact
normalized string: no Path conversion/cache, absolute-path copy, component
vector or filesystem authority. A single <=4095-byte bytearray and one current
encoded raw component fit the existing 64KiB path-normalization workspace,
including the final Unicode string and scalar traversal state. Anchored IO,
budgets, witnesses, stage seals and real no-replace installation are separate
increments. Trusted quiescent caller state is required; this is not protection
against hostile concurrent mutation or a claim of source/runtime validation.
"""
import pathlib
import sys

from .codec import utf8_length
from .errors import Refusal


_PATH_LIMIT = 4095
_STATE_LIMIT = 65536
_MISSING = object()
_PATH_SLOTS = ('_raw_paths', '_drv', '_root', '_tail_cached', '_str',
               '_str_normcase_cached', '_parts_normcase_cached')
if sys.version_info[:2] == (3, 12):
    _PATH_SLOTS += ('_lines_cached',)
_PATH_SLOTS += ('_hash',)
_LIST_SLOTS = ('_raw_paths', '_tail_cached', '_parts_normcase_cached')
_EMPTY_TEXT_SIZE = str.__sizeof__('')


def _slot(path, name):
    try:
        return object.__getattribute__(path, name)
    except AttributeError:
        return _MISSING


def _state_add(total, amount):
    if amount > _STATE_LIMIT - total:
        raise Refusal('unsafe_path')
    return total + amount


def _path_state_bytes(value):
    """Measure the closed stored-state inventory before any path conversion.

    Exact list capacity (including spare slots) and every string occurrence are
    counted before walking/copying text. No sharing credit, referent walk or
    instance __sizeof__ hook is used. The two qualified GC headers are 16 bytes.
    """
    if (type(value) is not pathlib.PosixPath or
            sys.version_info[:2] not in ((3, 12), (3, 13)) or
            pathlib.PurePath.__slots__ != _PATH_SLOTS):
        raise Refusal('unsafe_path')
    total = _state_add(0, object.__sizeof__(value) + 16)
    for name in _PATH_SLOTS:
        item = _slot(value, name)
        if item is _MISSING:
            if name == '_raw_paths':
                raise Refusal('unsafe_path')
            continue
        if name in _LIST_SLOTS:
            if type(item) is not list:
                raise Refusal('unsafe_path')
            # Precharge capacity and a minimum text occurrence BEFORE walking.
            total = _state_add(total, list.__sizeof__(item) + 16)
            total = _state_add(total, len(item) * _EMPTY_TEXT_SIZE)
            for text in item:
                if type(text) is not str:
                    raise Refusal('unsafe_path')
                total = _state_add(total, str.__sizeof__(text) - _EMPTY_TEXT_SIZE)
        elif name == '_hash':
            if (type(item) is not int or
                    not -sys.maxsize - 1 <= item <= sys.maxsize):
                raise Refusal('unsafe_path')
            total = _state_add(total, int.__sizeof__(item))
        else:
            if type(item) is not str:
                raise Refusal('unsafe_path')
            total = _state_add(total, str.__sizeof__(item))
    return total


def _raw_bytes(text):
    if type(text) is not str or len(text) > _PATH_LIMIT:
        raise Refusal('unsafe_path')
    if '\0' in text:
        raise Refusal('unsafe_path')
    return utf8_length(text, 'unsafe_path', maximum=_PATH_LIMIT)


def _joined_shape(raw):
    """Return scalar effective start/length without making a joined string."""
    start = 0
    length = 0
    ends_slash = False
    for index in range(len(raw)):
        text = raw[index]
        size = _raw_bytes(text)  # Includes raw prefixes discarded by absolutes.
        if text.startswith('/'):
            start = index
            length = size
            ends_slash = text.endswith('/')
        elif not length or ends_slash:
            length += size
            if size:
                ends_slash = text.endswith('/')
        else:
            length += 1 + size
            ends_slash = not size or text.endswith('/')
    # The final stock join is the admitted joined text. Intermediate prefixes
    # may be discarded by a later absolute component, but raw state was bounded.
    if length > _PATH_LIMIT:
        raise Refusal('unsafe_path')
    return start, length


def _normalize(raw, start, joined_bytes):
    """Construct and normalize one bounded byte workspace in place."""
    workspace = bytearray(max(1, joined_bytes))
    used = 0
    for index in range(start, len(raw)):
        text = raw[index]
        if used and workspace[used - 1] != 47:
            workspace[used] = 47
            used += 1
        encoded = text.encode('utf-8')
        size = len(encoded)
        workspace[used:used + size] = encoded
        used += size
        del encoded
    return _normalize_workspace(workspace, used)


def _normalize_workspace(workspace, used):
    """Normalize one admitted owned byte workspace; retain no components."""
    if (type(workspace) is not bytearray or type(used) is not int or
            not 0 <= used <= len(workspace) <= _PATH_LIMIT or not workspace):
        raise Refusal('unsafe_path')
    lead = 0
    while lead < used and workspace[lead] == 47:
        lead += 1
    root = 2 if lead == 2 else 1 if lead else 0
    read = lead
    written = root
    while read < used:
        end = read
        while end < used and workspace[end] != 47:
            end += 1
        if end > read and not (end == read + 1 and workspace[read] == 46):
            if written > root:
                workspace[written] = 47
                written += 1
            while read < end:
                workspace[written] = workspace[read]
                written += 1
                read += 1
        read = end + 1
    if not written:
        workspace[0] = 46
        written = 1
    del workspace[written:]
    return workspace.decode('utf-8')


def _check_parts(parts, normalized, *, tail):
    index = 0
    if tail:
        if normalized == '.':
            if parts:
                raise Refusal('unsafe_path')
            return
        while index < len(normalized) and normalized[index] == '/':
            index += 1
        if index == len(normalized):
            if parts:
                raise Refusal('unsafe_path')
            return
    count = 0
    while True:
        end = normalized.find('/', index)
        if end < 0:
            end = len(normalized)
        if (count >= len(parts) or len(parts[count]) != end - index or
                not normalized.startswith(parts[count], index, end)):
            raise Refusal('unsafe_path')
        count += 1
        if end == len(normalized):
            break
        index = end + 1
    if count != len(parts):
        raise Refusal('unsafe_path')


def _check_caches(value, normalized):
    """Every present cache is a checked consequence, never path authority."""
    root = '//' if normalized.startswith('//') else '/' if normalized.startswith('/') else ''
    for name in _PATH_SLOTS:
        if name == '_raw_paths':
            continue
        item = _slot(value, name)
        if item is _MISSING:
            continue
        if name == '_drv':
            expected = ''
        elif name == '_root':
            expected = root
        elif name in ('_str', '_str_normcase_cached'):
            expected = normalized
        elif name == '_hash':
            expected = hash(normalized)
        elif name in ('_tail_cached', '_parts_normcase_cached'):
            _check_parts(item, normalized, tail=name == '_tail_cached')
            continue
        else:  # The sole additional 3.12 slot: separators/newlines swapped.
            if normalized == '.':
                if item != '':
                    raise Refusal('unsafe_path')
            else:
                if len(item) != len(normalized):
                    raise Refusal('unsafe_path')
                for index in range(len(normalized)):
                    character = normalized[index]
                    expected = '\n' if character == '/' else '/' if character == '\n' else character
                    if item[index] != expected:
                        raise Refusal('unsafe_path')
            continue
        if item != expected:
            raise Refusal('unsafe_path')


def _qualify_path(value):
    """Return exact stock POSIX normalization after finite raw/state admission."""
    if type(value) is str:
        size = _raw_bytes(value)
        return _normalize((value,), 0, size)
    if type(value) is not pathlib.PosixPath:
        raise Refusal('unsafe_path')
    _path_state_bytes(value)
    raw = _slot(value, '_raw_paths')
    start, size = _joined_shape(raw)
    normalized = _normalize(raw, start, size)
    _check_caches(value, normalized)
    return normalized
