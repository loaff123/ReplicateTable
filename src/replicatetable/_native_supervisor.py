"""Private exact-PID ownership for an already returned stock child.

This increment supplies adopted-child transfer, sampled RSS, wait, stop,
managed signal policy and retirement. It does not launch a worker or establish
protocol/source ownership, completed transport or installation authority.
The eventual closed launch route must establish those separate gates before
using this lifecycle. Tests may own benign fixture children independently.

One preallocated _ChildOwner occupies the named lifecycle child-owner cell.
Its stock wrapper and argv stay separately funded until actual REAPED/LOST.
Wait observations occupy the named child-observation lane; failure retirement
uses the existing sanitization lane. There is no PID registry, global reaper,
stock lifecycle call, caller callback or destructor-based wait authority.
"""
import _signal as _raw_signal
import _thread
import ctypes
import errno
import os
import signal
import subprocess
import threading
import time

from .errors import Refusal, ComputationError
from ._native_budget_state import _checkpoint, _require_deadline
from ._native_fs_owners import _FDCell
from ._native_abi import _syscall_binding


_STATES = ('PRELAUNCH', 'TRANSFERRING', 'OWNED', 'REAPED', 'LOST')
_MISSING = object()
_RSS_LIMIT = 1073741824
_RSS_KIB_MAX = ((1 << 63) - 1) // 1024
_ACTIVE_POLICY = None
_SIGNAL_POISONED = False
_RESTORATION_MESSAGE = 'Signal restoration is incomplete; restart this process before native work.'
_KERNEL_ACTION = ctypes.c_ubyte * 32
_MANAGED_SIGNALS = (2, 15)


def _signal_metadata():
    binding = _syscall_binding()
    return None if binding is None else (binding[0], binding[1], _KERNEL_ACTION)


# Fixed binding/type metadata is established at import, never during an
# operation. The shared module owns its one acquisition and unavailable state.
_SIGNAL_API = _signal_metadata()


def _signal_api():
    if _SIGNAL_API is None:
        raise Refusal('supervision_unavailable')
    return _SIGNAL_API


def _query_action(signum):
    native = _signal_api()
    storage = native[2]()
    result = native[1](13, ctypes.c_int(signum), None,
                       ctypes.byref(storage), ctypes.c_size_t(8))
    observed_errno = ctypes.get_errno()
    if result != 0:
        raise Refusal('supervision_unavailable')
    raw = bytes(storage)
    # The saved libc-shaped field is four bytes. Never truncate meaningful
    # high kernel flags. All 64 mask bits survive independently of Python's
    # valid_signals set. Only proven unused saved ranges are canonicalized.
    if raw[12:16] != b'\0\0\0\0':
        raise Refusal('supervision_unavailable')
    return (raw[:8] + raw[24:32] + bytes(120) + raw[8:12] +
            bytes(4) + raw[16:24])


def _restore_action(signum, original):
    native = _signal_api()
    if type(original) is not bytes or len(original) != 152:
        raise Refusal('supervision_unavailable', _RESTORATION_MESSAGE)
    raw = (original[:8] + original[136:140] + bytes(4) +
           original[144:152] + original[8:16])
    storage = native[2].from_buffer_copy(raw)
    result = native[1](13, ctypes.c_int(signum), ctypes.byref(storage),
                       None, ctypes.c_size_t(8))
    observed_errno = ctypes.get_errno()
    if result != 0:
        raise Refusal('supervision_unavailable', _RESTORATION_MESSAGE)


def _handler_supported(handler):
    # Borrow caller policy without inspecting its closure or invoking it.
    return (handler is signal.SIG_DFL or handler is signal.SIG_IGN or
            handler is not None and handler is not _managed_signal and callable(handler))


def _preflight_native(deadline):
    """Observable stock checks under caller-established Python quiescence.

    Registry and raw stock counts cannot prove absence of pending starts,
    foreign C-created Python states, other interpreters or operation-time
    starts. Idle native helpers remain allowed; there is no OS-thread gate.
    """
    _require_deadline(deadline)
    _checkpoint(deadline)
    if _SIGNAL_POISONED:
        raise Refusal('supervision_unavailable', _RESTORATION_MESSAGE)
    if (threading.current_thread() is not threading.main_thread() or
            threading.active_count() != 1 or _thread._count() != 0 or
            _ACTIVE_POLICY is not None):
        raise Refusal('supervision_unavailable')
    if type(subprocess._active) is not list or len(subprocess._active):
        raise Refusal('supervision_unavailable')
    if signal.getsignal(signal.SIGCHLD) is not signal.SIG_DFL:
        raise Refusal('supervision_unavailable')
    child_action = _query_action(signal.SIGCHLD)
    if (int.from_bytes(child_action[:8], 'little') != 0 or
            int.from_bytes(child_action[136:140], 'little') & 2):
        raise Refusal('supervision_unavailable')
    if (not _handler_supported(signal.getsignal(signal.SIGINT)) or
            not _handler_supported(signal.getsignal(signal.SIGTERM))):
        raise Refusal('supervision_unavailable')


class _SignalPolicy:
    """Captured originals; terminal failure retains real strong ownership."""
    __slots__ = ('_deadline', '_int_handler', '_term_handler', '_int_action',
                 '_term_action', '_mask', '_touched', '_active', '_retired')

    def __init__(self):
        raise Refusal('supervision_unavailable')

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private signal policy is final')

    def __setattr__(self, name, value):
        raise AttributeError('Private signal policy is readonly')

    def __delattr__(self, name):
        raise AttributeError('Private signal policy is readonly')

    @property
    def active(self):
        return self._active

    @property
    def deadline(self):
        return self._deadline

    @property
    def restoration_message(self):
        if _SIGNAL_POISONED and self is _ACTIVE_POLICY and self._active:
            return _RESTORATION_MESSAGE
        return None


def _managed_signal(signum, frame):
    # Asynchronous work is only the first-signal latch. No prior handler,
    # public callback, IO, model construction or cleanup is invoked here.
    policy = _ACTIVE_POLICY
    if policy is not None:
        policy._deadline._cancellation._latch(signum)


def _observe_pending(policy):
    pending = _raw_signal.sigpending()
    if 2 in pending:
        policy._deadline._cancellation._latch(2)
    if 15 in pending:
        policy._deadline._cancellation._latch(15)


def _enter_signal_attempt(deadline):
    global _ACTIVE_POLICY
    policy = None
    try:
        _preflight_native(deadline)
        int_handler = signal.getsignal(signal.SIGINT)
        term_handler = signal.getsignal(signal.SIGTERM)
        if not _handler_supported(int_handler) or not _handler_supported(term_handler):
            raise Refusal('supervision_unavailable')
        int_action = _query_action(signal.SIGINT)
        term_action = _query_action(signal.SIGTERM)
        original_mask = _raw_signal.pthread_sigmask(signal.SIG_BLOCK, ())
        # The fixed libc pthread wrapper cannot restore its reserved bits.
        # Refuse this original main mask before changing any caller policy;
        # kernel action-mask bits32/33 are separately preserved without loss.
        if 32 in original_mask or 33 in original_mask:
            raise Refusal('supervision_unavailable')
        policy = object.__new__(_SignalPolicy)
        for field, value in (('_deadline', deadline), ('_int_handler', int_handler),
                ('_term_handler', term_handler), ('_int_action', int_action),
                ('_term_action', term_action), ('_mask', original_mask),
                ('_touched', 0), ('_active', True), ('_retired', False)):
            object.__setattr__(policy, field, value)
        del int_handler, term_handler, int_action, term_action, original_mask
        _ACTIVE_POLICY = policy
        before_block = _raw_signal.pthread_sigmask(signal.SIG_BLOCK, _MANAGED_SIGNALS)
        object.__setattr__(policy, '_mask', before_block)
        del before_block
        object.__setattr__(policy, '_touched', 1)
        signal.signal(signal.SIGINT, _managed_signal)
        object.__setattr__(policy, '_touched', 3)
        signal.signal(signal.SIGTERM, _managed_signal)
        _observe_pending(policy)
        # Only those two bits changed at the blocking boundary. UNBLOCK avoids
        # a separate full-mask difference allocation alongside the old mask.
        _raw_signal.pthread_sigmask(signal.SIG_UNBLOCK, _MANAGED_SIGNALS)
        return policy, None
    except BaseException as error:
        if policy is not None and policy is _ACTIVE_POLICY:
            try:
                _leave_signal_policy(policy)
            except BaseException as cleanup_error:
                _drop_owned_links(cleanup_error)
        _drop_owned_links(error)
        return None, error


def _enter_signal_policy(deadline):
    policy, error = _enter_signal_attempt(deadline)
    deadline = None
    if error is not None:
        raise error from None
    return policy


def _first_signal_error(primary, error):
    _drop_owned_links(error)
    return error if primary is None else primary


def _restore_one_signal(policy, signum, bit):
    global _SIGNAL_POISONED
    handler = policy._int_handler if bit == 1 else policy._term_handler
    original = policy._int_action if bit == 1 else policy._term_action
    primary = None
    completed_setter = False
    try:
        current = signal.getsignal(signum)
        if current is _managed_signal:
            try:
                signal.signal(signum, handler)
                completed_setter = True
            except BaseException as error:
                completed_setter = False
                primary = _first_signal_error(primary, error)
                # CPython can dispatch a previous-policy callback BEFORE the
                # setter changes the table. Exactly one retry is allowed, and
                # only while this operation still owns that actual mapping.
                if signal.getsignal(signum) is _managed_signal:
                    try:
                        signal.signal(signum, handler)
                        completed_setter = True
                    except BaseException as retry_error:
                        completed_setter = False
                        primary = _first_signal_error(primary, retry_error)
            current = signal.getsignal(signum)
        if current is handler:
            if completed_setter:
                _restore_action(signum, original)
            elif _query_action(signum) != original:
                # A callback can reinstall this SAME callable with a new
                # action. Identity alone cannot authorize an overwrite after
                # a raising setter or before our setter began. Preserve that
                # observed state and require restart with ownership retained.
                raise Refusal('supervision_unavailable', _RESTORATION_MESSAGE)
            if _query_action(signum) != original:
                raise Refusal('supervision_unavailable', _RESTORATION_MESSAGE)
        elif _handler_supported(current):
            # A legitimate callback replacement owns BOTH its Python mapping
            # and the kernel action it installed. Never overwrite either one.
            replacement_action = _query_action(signum)
            if _query_action(signum) != replacement_action:
                raise Refusal('supervision_unavailable', _RESTORATION_MESSAGE)
        else:
            raise Refusal('supervision_unavailable', _RESTORATION_MESSAGE)
        if signal.getsignal(signum) is not current:
            raise Refusal('supervision_unavailable', _RESTORATION_MESSAGE)
        object.__setattr__(policy, '_touched', policy._touched & ~bit)
    except BaseException as error:
        _SIGNAL_POISONED = True
        primary = _first_signal_error(primary, error)
    return primary


def _leave_signal_attempt(policy):
    global _ACTIVE_POLICY, _SIGNAL_POISONED
    primary = None
    try:
        _raw_signal.pthread_sigmask(signal.SIG_BLOCK, _MANAGED_SIGNALS)
        _observe_pending(policy)
    except BaseException as error:
        primary = _first_signal_error(primary, error)
    for signum, bit in ((signal.SIGINT, 1), (signal.SIGTERM, 2)):
        if policy._touched & bit:
            try:
                error = _restore_one_signal(policy, signum, bit)
            except BaseException as error:
                _SIGNAL_POISONED = True
                primary = _first_signal_error(primary, error)
            else:
                if error is not None:
                    primary = _first_signal_error(primary, error)
    if policy._touched:
        # Further real failure is terminal: keep strong policy/touched/mask
        # ownership and permanently refuse native entry. No notes/callbacks,
        # fallback handlers, force-exit or repeated restoration attempts.
        _SIGNAL_POISONED = True
        if primary is None:
            primary = Refusal('supervision_unavailable', _RESTORATION_MESSAGE)
        return primary
    try:
        _raw_signal.pthread_sigmask(signal.SIG_SETMASK, policy._mask)
    except BaseException as error:
        primary = _first_signal_error(primary, error)
    try:
        restored = _raw_signal.pthread_sigmask(signal.SIG_BLOCK, ()) == policy._mask
    except BaseException as error:
        primary = _first_signal_error(primary, error)
        restored = False
    if not restored:
        _SIGNAL_POISONED = True
        if primary is None:
            primary = Refusal('supervision_unavailable', _RESTORATION_MESSAGE)
        return primary
    # Python mappings, meaningful kernel actions and original main mask were
    # actually validated. A caller exception remains primary and untouched
    # apart from retiring this operation's traceback/context/cause links.
    try:
        object.__setattr__(policy, '_active', False)
        object.__setattr__(policy, '_retired', True)
    except BaseException as error:
        primary = _first_signal_error(primary, error)
    finally:
        _ACTIVE_POLICY = None
        object.__setattr__(policy, '_active', False)
        object.__setattr__(policy, '_retired', True)
    return primary


def _leave_signal_policy(policy):
    if type(policy) is not _SignalPolicy:
        raise Refusal('supervision_unavailable')
    if _stored(policy, '_retired') is True:
        return
    if (policy is not _ACTIVE_POLICY or _stored(policy, '_active') is not True or
            threading.current_thread() is not threading.main_thread()):
        raise Refusal('supervision_unavailable')
    if _SIGNAL_POISONED:
        raise Refusal('supervision_unavailable', _RESTORATION_MESSAGE)
    error = _leave_signal_attempt(policy)
    policy = None
    if error is not None:
        _drop_owned_links(error)
        raise error from None


def _stored(value, name):
    try:
        return object.__getattribute__(value, name)
    except AttributeError:
        return _MISSING


class _ChildOwner:
    """Empty construction is state only; adoption requires a returned wrapper."""
    __slots__ = ('_state', '_pid', '_wrapper', '_wait_status')

    def __init__(self):
        if type(self) is not _ChildOwner:
            raise Refusal('supervision_unavailable')
        for name in _ChildOwner.__slots__:
            if _stored(self, name) is not _MISSING:
                raise Refusal('supervision_unavailable')
        object.__setattr__(self, '_state', 'PRELAUNCH')
        object.__setattr__(self, '_pid', None)
        object.__setattr__(self, '_wrapper', None)
        object.__setattr__(self, '_wait_status', None)

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private child owner is final')

    def __setattr__(self, name, value):
        raise AttributeError('Private child ownership is readonly')

    def __delattr__(self, name):
        raise AttributeError('Private child ownership is readonly')

    @property
    def state(self):
        return self._state

    @property
    def pid(self):
        return self._pid

    @property
    def wrapper(self):
        return self._wrapper

    @property
    def wait_status(self):
        return self._wait_status


def _owner_state(owner):
    if type(owner) is not _ChildOwner:
        raise Refusal('supervision_unavailable')
    state = _stored(owner, '_state')
    pid = _stored(owner, '_pid')
    wrapper = _stored(owner, '_wrapper')
    status = _stored(owner, '_wait_status')
    if type(state) is not str or state not in _STATES:
        raise Refusal('supervision_unavailable')
    if state == 'PRELAUNCH':
        if pid is not None or wrapper is not None or status is not None:
            raise Refusal('supervision_unavailable')
    elif state != 'TRANSFERRING':
        if type(pid) is not int or not 1 <= pid <= (1 << 31) - 1:
            raise Refusal('supervision_unavailable')
        if wrapper is None:
            if state not in ('REAPED', 'LOST'):
                raise Refusal('supervision_unavailable')
        elif type(wrapper) is not subprocess.Popen:
            raise Refusal('supervision_unavailable')
        if state == 'REAPED':
            if (type(status) is not int or not 0 <= status <= 65535 or
                    not (os.WIFEXITED(status) or os.WIFSIGNALED(status))):
                raise Refusal('supervision_unavailable')
        elif status is not None:
            raise Refusal('supervision_unavailable')
    return state


def _adopt_returned(owner, wrapper):
    """Idempotent transfer of a stock constructor's exact returned object.

    The closed caller retains its returned local and repeats this in finally
    before error cleanup. No semantic work or allocating owner construction
    belongs between successful constructor return and this transfer.
    """
    if type(owner) is not _ChildOwner or type(wrapper) is not subprocess.Popen:
        raise Refusal('supervision_unavailable')
    state = _stored(owner, '_state')
    if type(state) is not str or state not in _STATES:
        raise Refusal('supervision_unavailable')
    if state in ('OWNED', 'REAPED', 'LOST'):
        _owner_state(owner)
        if owner._wrapper is not wrapper:
            raise Refusal('supervision_unavailable')
        return
    previous = _stored(owner, '_wrapper')
    if ((previous is not None and previous is not wrapper) or
            (state == 'TRANSFERRING' and previous is not wrapper) or
            _stored(owner, '_wait_status') is not None):
        raise Refusal('supervision_unavailable')
    pid = wrapper.pid
    if (type(pid) is not int or not 1 <= pid <= (1 << 31) - 1 or
            wrapper.returncode is not None or
            (state == 'PRELAUNCH' and wrapper._child_created is not True)):
        raise Refusal('supervision_unavailable')
    object.__setattr__(owner, '_wrapper', wrapper)
    object.__setattr__(owner, '_state', 'TRANSFERRING')
    object.__setattr__(owner, '_pid', pid)
    wrapper._child_created = False
    object.__setattr__(owner, '_state', 'OWNED')


def _wait_observation(pid, flags):
    """Return primitive OS observations after the dependency error frame ends."""
    while True:
        try:
            observed_pid, status = os.waitpid(pid, flags)
            return observed_pid, status, 0
        except OSError as error:
            number = error.errno
            # No exception text, traceback, or constructor state escapes.
            if number == errno.EINTR:
                continue
            return None, None, number


def _observe_child(owner, flags):
    if _owner_state(owner) != 'OWNED':
        raise Refusal('supervision_unavailable')
    observed_pid, status, error = _wait_observation(owner._pid, flags)
    if error == errno.ECHILD:
        object.__setattr__(owner, '_state', 'LOST')
        raise Refusal('supervision_unavailable')
    if error:
        raise ComputationError('io_error')
    if (type(observed_pid) is not int or type(status) is not int or
            not 0 <= status <= 65535):
        object.__setattr__(owner, '_state', 'LOST')
        raise Refusal('supervision_unavailable')
    if observed_pid == 0 and flags == os.WNOHANG and status == 0:
        return False
    if (observed_pid != owner._pid or
            not (os.WIFEXITED(status) or os.WIFSIGNALED(status))):
        # This cannot be a successful exact-PID terminal observation. Never
        # synthesize a reaped token or risk signaling after lost wait authority.
        object.__setattr__(owner, '_state', 'LOST')
        raise Refusal('supervision_unavailable')
    object.__setattr__(owner, '_wait_status', status)
    object.__setattr__(owner, '_state', 'REAPED')
    return True


def _probe_child(owner):
    return _observe_child(owner, os.WNOHANG)


def _kill_observation(pid):
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError as error:
        return error.errno
    return 0


def _stop_child(owner):
    """Probe first; only an owned result-zero child may receive SIGKILL."""
    state = _owner_state(owner)
    if state in ('PRELAUNCH', 'REAPED', 'LOST'):
        return
    if state != 'OWNED':
        raise Refusal('supervision_unavailable')
    if _probe_child(owner):
        return
    error = _kill_observation(owner._pid)
    if error and error != errno.ESRCH:
        raise ComputationError('io_error')
    # ESRCH can mean exit between the owned result-zero probe and signal.
    # Only the actual subsequent wait establishes REAPED (or reports LOST).
    _observe_child(owner, 0)


def _drop_owned_links(error):
    BaseException.__traceback__.__set__(error, None)
    BaseException.__context__.__set__(error, None)
    BaseException.__cause__.__set__(error, None)


def _rss_stream(cell, budget):
    """One chunk plus scalar parser state; never retain an irrelevant line."""
    prefix = b'VmRSS:'
    position = 0
    mode = 0  # prefix, leading space, digits, space, k, B, tail; -1 skips a line
    value = 0
    while True:
        _checkpoint(budget)
        try:
            raw = os.read(cell._fd, 65536)
        except OSError as error:
            if error.errno == errno.EINTR:
                continue
            raise ComputationError('io_error') from None
        if not raw:
            if mode not in (-1, 0):
                raise Refusal('supervision_unavailable')
            return None
        for byte in raw:
            if mode == -1:
                if byte == 10:
                    mode = position = 0
                continue
            if mode == 0:
                if byte == prefix[position]:
                    position += 1
                    if position == len(prefix):
                        mode = 1
                elif byte == 10:
                    position = 0
                else:
                    mode = -1
                continue
            if mode == 1:
                if byte in (9, 32):
                    continue
                if 48 <= byte <= 57:
                    value = byte - 48
                    mode = 2
                    continue
            elif mode == 2:
                if 48 <= byte <= 57:
                    digit = byte - 48
                    if value > (_RSS_KIB_MAX - digit) // 10:
                        raise Refusal('supervision_unavailable')
                    value = value * 10 + digit
                    continue
                if byte in (9, 32):
                    mode = 3
                    continue
            elif mode == 3:
                if byte in (9, 32):
                    continue
                if byte == 107:  # exact kernel unit kB
                    mode = 5
                    continue
            elif mode == 5:
                if byte == 66:
                    mode = 6
                    continue
            elif mode == 6:
                if byte in (9, 32):
                    continue
                if byte == 10:
                    return value * 1024
            raise Refusal('supervision_unavailable')
        del raw  # S1's previous payload retires before the next read allocates.


def _rss_work(owner, budget, cell):
    _checkpoint(budget)
    try:
        object.__setattr__(cell, '_fd', os.open('/proc/' + str(owner._pid) + '/status',
                           os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW))
    except OSError as error:
        if error.errno in (errno.ENOENT, errno.ESRCH):
            return None
        raise ComputationError('io_error') from None
    return _rss_stream(cell, budget)


def _rss_attempt(owner, budget):
    cell = _FDCell()
    try:
        result = _rss_work(owner, budget, cell)
    except BaseException as error:
        try:
            cell._close()
        except BaseException as cleanup_error:
            _drop_owned_links(cleanup_error)
        _drop_owned_links(error)
        return None, error
    try:
        cell._close()
    except BaseException as error:
        _drop_owned_links(error)
        if isinstance(error, OSError):
            return None, ComputationError('io_error')
        return None, error
    return result, None


def _read_child_rss(owner, deadline):
    """Read only an adopted PID; None is no sample, never zero/reap proof."""
    _require_deadline(deadline)
    if _owner_state(owner) != 'OWNED':
        raise Refusal('supervision_unavailable')
    result, error = _rss_attempt(owner, deadline)
    owner = None
    deadline = None
    if error is not None:
        raise error from None
    return result


def _wait_attempt(owner, budget):
    absent_since = None
    try:
        while True:
            if _probe_child(owner):
                return owner._wait_status, None
            _checkpoint(budget)
            rss = _read_child_rss(owner, budget)
            _checkpoint(budget)
            if rss is None:
                if _probe_child(owner):
                    return owner._wait_status, None
                now = time.monotonic_ns()
                if absent_since is None:
                    absent_since = now
                elif now - absent_since >= 10000000:
                    raise Refusal('supervision_unavailable')
            else:
                absent_since = None
                if rss > _RSS_LIMIT:
                    raise ComputationError('worker_memory_limit')
            # A missing sample has one target interval, never a fresh interval
            # on repeated misses. The original deadline/cancellation remains
            # primary. A real terminal wait resolves without invented RSS.
            wake_at = min(time.monotonic_ns() + 10000000, budget._deadline_ns)
            if absent_since is not None:
                wake_at = min(wake_at, absent_since + 10000000)
            time.sleep(max(0, wake_at - time.monotonic_ns()) / 1000000000)
    except BaseException as error:
        # Expiry/cancellation does not waive reaping of an adopted child.
        # A cleanup failure cannot replace the already established primary.
        try:
            _stop_child(owner)
        except BaseException as cleanup_error:
            _drop_owned_links(cleanup_error)
        _drop_owned_links(error)
        return None, error


def _wait_child(owner, deadline):
    """Return actual terminal status; it is not a completed-operation token."""
    _require_deadline(deadline)
    _owner_state(owner)
    status, error = _wait_attempt(owner, deadline)
    owner = None
    deadline = None
    if error is not None:
        raise error from None
    return status


def _release_child(owner):
    if _owner_state(owner) not in ('REAPED', 'LOST'):
        raise Refusal('supervision_unavailable')
    # _child_created was retired at adoption, so dropping the stock wrapper
    # cannot poll/wait, mutate _active, or resurrect numeric signal authority.
    object.__setattr__(owner, '_wrapper', None)


class _Outcome:
    """Bounded first-finding state; construction proves no native operation."""
    __slots__ = ('_cancellation', '_finding', '_checks', '_exit_code',
                 '_committed', '_receipt', '_prepared', '_startup_failed')

    def __init__(self, cancellation):
        from .source import _owned_attempt, _raise_owned
        _, error = _owned_attempt(_initialize_outcome, self, cancellation)
        self = cancellation = None
        if error is not None:
            _raise_owned(error)

    def __init_subclass__(cls, **keywords):
        raise TypeError('Private outcome is final')

    def __setattr__(self, name, value):
        raise AttributeError('Private outcome is readonly')

    def __delattr__(self, name):
        raise AttributeError('Private outcome is readonly')

    @property
    def cancellation(self): return self._cancellation
    @property
    def finding(self): return self._finding
    @property
    def checks(self): return self._checks
    @property
    def exit_code(self): return self._exit_code
    @property
    def committed(self): return self._committed
    @property
    def receipt(self): return self._receipt
    @property
    def prepared(self): return self._prepared
    @property
    def startup_failed(self): return self._startup_failed
    @property
    def status(self):
        return None if self._finding is None else _status_for_exit(self._exit_code)


def _initialize_outcome(outcome, cancellation):
    from ._native_budget_state import _signal_value
    from ._bundle_models import _own_checks
    if type(outcome) is not _Outcome:
        raise Refusal('supervision_unavailable')
    for name in _Outcome.__slots__:
        if _stored(outcome, name) is not _MISSING:
            raise Refusal('supervision_unavailable')
    _signal_value(cancellation)
    checks = _own_checks({'structure':'not_attempted', 'source_binding':'not_attempted',
                          'runtime_binding':'not_attempted', 'replay':'not_attempted',
                          'report':'not_attempted'})
    for name, value in (('_cancellation',cancellation), ('_finding',None),
                        ('_checks',checks), ('_exit_code',0), ('_committed',False),
                        ('_receipt',None), ('_prepared',None), ('_startup_failed',False)):
        object.__setattr__(outcome, name, value)


def _outcome_state(outcome):
    from ._native_budget_state import _signal_value
    from ._bundle_models import _own_checks, _own_finding
    if type(outcome) is not _Outcome:
        raise Refusal('supervision_unavailable')
    for name in _Outcome.__slots__:
        if _stored(outcome, name) is _MISSING:
            raise Refusal('supervision_unavailable')
    _signal_value(outcome._cancellation)
    _own_checks(outcome._checks)
    _own_finding(outcome._finding)
    if type(outcome._committed) is not bool or type(outcome._startup_failed) is not bool:
        raise Refusal('supervision_unavailable')
    if type(outcome._exit_code) is not int:
        raise Refusal('supervision_unavailable')
    if outcome._finding is None:
        if outcome._exit_code != 0:
            raise Refusal('supervision_unavailable')
    elif outcome._exit_code != outcome._finding['exit_code']:
        raise Refusal('supervision_unavailable')


def _status_for_exit(exit_code):
    if type(exit_code) is not int:
        raise Refusal('supervision_unavailable')
    if exit_code == 2: return 'refused'
    if exit_code == 3: return 'failed'
    if exit_code in (130, 143): return 'cancelled'
    raise Refusal('supervision_unavailable')


def _record_check_inner(outcome, name, status):
    from ._bundle_models import _own_checks
    _outcome_state(outcome)
    if type(name) is not str or type(status) is not str or name not in outcome._checks:
        raise Refusal('supervision_unavailable')
    checks = _own_checks({key:status if key == name else value
                          for key, value in outcome._checks.items()})
    object.__setattr__(outcome, '_checks', checks)


def _record_check(outcome, name, status):
    from .source import _owned_attempt, _raise_owned
    _, error = _owned_attempt(_record_check_inner, outcome, name, status)
    outcome = name = status = None
    if error is not None:
        _raise_owned(error)


def _record_failure_inner(outcome, code, message, exit_code):
    from ._bundle_models import _own_finding
    _outcome_state(outcome)
    if outcome._finding is not None:
        return
    finding = _own_finding({'code':code, 'message':message, 'exit_code':exit_code})
    object.__setattr__(outcome, '_exit_code', exit_code)
    object.__setattr__(outcome, '_finding', finding)


def _record_failure(outcome, code, message, exit_code):
    from .source import _owned_attempt, _raise_owned
    _, error = _owned_attempt(_record_failure_inner, outcome, code, message, exit_code)
    outcome = code = message = exit_code = None
    if error is not None:
        _raise_owned(error)


def _select_failed_start_inner(outcome, stage_basename):
    from ._native_budget_state import _signal_value
    _outcome_state(outcome)
    if (outcome._finding is not None or outcome._committed or outcome._startup_failed or
            outcome._receipt is not None or outcome._prepared is not None):
        raise Refusal('supervision_unavailable')
    if stage_basename is not None:
        if (type(stage_basename) is not str or len(stage_basename) != 54 or
                not stage_basename.startswith('.replicatetable-stage-') or
                any(char not in '0123456789abcdef' for char in stage_basename[22:])):
            raise Refusal('supervision_unavailable')
    # This is the single managed latch observation at failed-start selection.
    # The owning launch route, never this scalar helper, proves the attempt.
    signum = _signal_value(outcome._cancellation)
    if signum:
        code, exit_code = 'interrupted', 128 + signum
        message = 'Operation interrupted during worker startup; worker termination could not be confirmed.'
    else:
        code, exit_code = 'supervision_unavailable', 3
        message = 'Native worker startup failed; worker termination could not be confirmed.'
    if stage_basename is not None:
        message += (' Operation did not complete; an unverified temporary stage may remain: ' +
                    stage_basename + ' (in the requested destination parent).')
    _record_failure_inner(outcome, code, message, exit_code)
    object.__setattr__(outcome, '_startup_failed', True)


def _select_failed_start(outcome, stage_basename):
    from .source import _owned_attempt, _raise_owned
    _, error = _owned_attempt(_select_failed_start_inner, outcome, stage_basename)
    outcome = stage_basename = None
    if error is not None:
        _raise_owned(error)


class _OperationFailure(Refusal):
    """Readonly value carrier; explicit contextual exit, no inferred authority."""
    __slots__ = ('_envelope', '_exit_code')

    def __init__(self, envelope, exit_code):
        from .source import _owned_attempt, _raise_owned
        _, error = _owned_attempt(_initialize_operation_failure, self, envelope, exit_code)
        self = envelope = exit_code = None
        if error is not None:
            _raise_owned(error)

    def __init_subclass__(cls, **keywords):
        raise TypeError('Private operation failure is final')

    def __setattr__(self, name, value):
        if type(name) is not str or name in ('_envelope','_exit_code','envelope','code','message','exit_code'):
            raise AttributeError('Operation classification is readonly')
        super().__setattr__(name, value)

    def __delattr__(self, name):
        if type(name) is not str or name in ('_envelope','_exit_code','envelope','code','message','exit_code'):
            raise AttributeError('Operation classification is readonly')
        super().__delattr__(name)

    @property
    def envelope(self): return self._envelope
    @property
    def code(self): return self._envelope.code
    @property
    def message(self): return self._envelope.message
    @property
    def exit_code(self): return self._exit_code


def _initialize_operation_failure(error, envelope, exit_code):
    from ._bundle_models import ErrorEnvelope, _read_model
    if (type(error) is not _OperationFailure or
            _stored(error, '_envelope') is not _MISSING or
            _stored(error, '_exit_code') is not _MISSING or
            type(envelope) is not ErrorEnvelope):
        raise Refusal('supervision_unavailable')
    _read_model(envelope)
    if _status_for_exit(exit_code) != envelope.status:
        raise Refusal('supervision_unavailable')
    object.__setattr__(error, '_envelope', envelope)
    object.__setattr__(error, '_exit_code', exit_code)
    ValueError.__init__(error, envelope.message)


def _error_from_outcome_inner(outcome):
    from ._bundle_models import ErrorEnvelope
    _outcome_state(outcome)
    if outcome._finding is None:
        raise Refusal('supervision_unavailable')
    envelope = ErrorEnvelope(version=2, status=outcome.status,
        code=outcome._finding['code'], message=outcome._finding['message'],
        checks=outcome._checks, committed=outcome._committed, receipt=outcome._receipt)
    return _OperationFailure(envelope, outcome._exit_code)


def _error_from_outcome(outcome):
    from .source import _owned_attempt, _raise_owned
    value, error = _owned_attempt(_error_from_outcome_inner, outcome)
    outcome = None
    if error is not None:
        _raise_owned(error)
    return value
