"""Closed private v11 budget states; arithmetic is not semantic authority.

Future outer routes must establish actual source/plan qualification and full
current-live admission before passing these private states to IO. No public
API accepts them. One <=512-byte budget record and one <=512-byte shared
cancellation record consume TWO OF the existing 160 FD/state slots; no new
slot or allowance is introduced. A future outcome owner shares cancellation
state and must preserve checks/status/committed receipt before handling a
Refusal. This module performs no launch, signal manipulation, RSS monitoring,
source/model measurement or public operation; logical-only work has no clock.
"""
from time import monotonic_ns

from ._resource_bounds import _checked_add, _count
from .errors import Refusal, ComputationError
from .resources import COUNT_MAX, LOGICAL_JOURNEY_LIMIT


_WINDOW_NS = 60000000000
_MISSING = object()
_MESSAGE = 'Operation was interrupted.'


def _stored(value, name):
    try:
        return object.__getattribute__(value, name)
    except AttributeError:
        return _MISSING


def _uninitialized(value, kind, names):
    if type(value) is not kind:
        raise Refusal('supervision_unavailable')
    for name in names:
        if _stored(value, name) is not _MISSING:
            raise Refusal('supervision_unavailable')


class _ClosedState:
    __slots__ = ()

    def __setattr__(self, name, value):
        raise AttributeError('Private budget state is readonly')

    def __delattr__(self, name):
        raise AttributeError('Private budget state is readonly')


class _CancellationState(_ClosedState):
    __slots__ = ('_signum',)

    def __init__(self):
        _uninitialized(self, _CancellationState, ('_signum',))
        object.__setattr__(self, '_signum', 0)

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private cancellation state is final')

    @property
    def signum(self):
        return _signal_value(self)

    def _latch(self, signum):
        """First observed INT/TERM only; future handlers call this latch."""
        previous = _signal_value(self)
        if type(signum) is not int or signum not in (2, 15):
            raise Refusal('supervision_unavailable')
        if not previous:
            object.__setattr__(self, '_signum', signum)


def _signal_value(value):
    if type(value) is not _CancellationState:
        raise Refusal('supervision_unavailable')
    signum = _stored(value, '_signum')
    if type(signum) is not int or signum not in (0, 2, 15):
        raise Refusal('supervision_unavailable')
    return signum


class Deadline(_ClosedState):
    __slots__ = ('_deadline_ns', '_cancellation')

    def __init__(self, deadline_ns, cancellation):
        _uninitialized(self, Deadline, ('_deadline_ns', '_cancellation'))
        _count(deadline_ns, 'supervision_unavailable')
        _signal_value(cancellation)
        object.__setattr__(self, '_deadline_ns', deadline_ns)
        object.__setattr__(self, '_cancellation', cancellation)

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private deadline state is final')

    @property
    def deadline_ns(self):
        _validate_budget(self)
        return self._deadline_ns


class LogicalOnlyBudget(_ClosedState):
    __slots__ = ('_cancellation',)

    def __init__(self, cancellation):
        _uninitialized(self, LogicalOnlyBudget, ('_cancellation',))
        _signal_value(cancellation)
        object.__setattr__(self, '_cancellation', cancellation)

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private logical-only budget is final')


def _validate_budget(budget):
    kind = type(budget)
    if kind is not Deadline and kind is not LogicalOnlyBudget:
        raise Refusal('supervision_unavailable')
    cancellation = _stored(budget, '_cancellation')
    _signal_value(cancellation)
    if kind is Deadline:
        _count(_stored(budget, '_deadline_ns'), 'supervision_unavailable')
    return cancellation


def _now():
    value = monotonic_ns()
    _count(value, 'supervision_unavailable')
    return value


def _start_deadline(cancellation):
    """One fresh outer-entry timestamp; never a per-phase reset."""
    _signal_value(cancellation)
    deadline_ns = _checked_add(_now(), _WINDOW_NS, limit=COUNT_MAX,
                               code='supervision_unavailable')
    return Deadline(deadline_ns, cancellation)


def _inherited_deadline(deadline_ns, cancellation):
    """Preserve the original parent timestamp, including an expired one."""
    return Deadline(deadline_ns, cancellation)


class _Cancellation(Refusal):
    """Small readonly classification; the outer owner retains commit outcome."""
    __slots__ = ('_signum',)

    def __init__(self, signum):
        _uninitialized(self, _Cancellation, ('_signum',))
        if type(signum) is not int or signum not in (2, 15):
            raise Refusal('supervision_unavailable')
        object.__setattr__(self, '_signum', signum)
        ValueError.__init__(self, _MESSAGE)

    def __init_subclass__(cls, **kwargs):
        raise TypeError('Private cancellation classification is final')

    def __setattr__(self, name, value):
        if name == '_signum':
            raise AttributeError('Cancellation classification is readonly')
        super().__setattr__(name, value)

    def __delattr__(self, name):
        if name == '_signum':
            raise AttributeError('Cancellation classification is readonly')
        super().__delattr__(name)

    @property
    def signum(self):
        return self._signum

    @property
    def code(self):
        return 'interrupted'

    @property
    def message(self):
        return _MESSAGE

    @property
    def exit_code(self):
        return 128 + self._signum


def _checkpoint(budget):
    """Validate closed state, then cancellation, then the original deadline."""
    cancellation = _validate_budget(budget)
    signum = _signal_value(cancellation)
    if signum:
        raise _Cancellation(signum)
    if type(budget) is Deadline and _now() >= budget._deadline_ns:
        raise ComputationError('operation_timeout')


def _require_deadline(budget):
    """Exact native-state gate only; callers still checkpoint before work."""
    if type(budget) is not Deadline:
        raise Refusal('supervision_unavailable')
    _validate_budget(budget)
    return budget


def _admit(budget, current_live_bytes, additional_bytes):
    """Scalar accounting only; inputs never confer source/plan authority.

    Owning routes must derive their current-live quantities from actual safely
    measured state. This addition does not measure or grant model/native trust.
    Exact scalar domains precede cancellation; cancellation precedes the total.
    """
    _count(current_live_bytes)
    _count(additional_bytes)
    _checkpoint(budget)
    return _checked_add(current_live_bytes, additional_bytes,
                        limit=LOGICAL_JOURNEY_LIMIT)
