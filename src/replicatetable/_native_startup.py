"""Bounded failed-start scalar diagnostics, without lifecycle authority.

The outer route owns the failure observation, latch selection and outcome.
These helpers neither observe nor establish a worker, stage or source fact.
"""
from .errors import Refusal


_FAILED = 'Native worker startup failed; worker termination could not be confirmed.'
_INTERRUPTED = ('Operation interrupted during worker startup; '
                'worker termination could not be confirmed.')
_STAGE_PREFIX = '.replicatetable-stage-'
_HINT_PREFIX = 'Operation did not complete; an unverified temporary stage may remain: '
_HINT_SUFFIX = ' (in the requested destination parent).'


def _signal_domain(signum):
    if type(signum) is not int or signum not in (0, 2, 15):
        raise Refusal('supervision_unavailable')


def _startup_classification(signum):
    """Return primitive classification; a scalar grants no outcome ownership."""
    _signal_domain(signum)
    if signum == 0:
        return ('supervision_unavailable', 'failed', 3)
    return ('interrupted', 'cancelled', 128 + signum)


def _startup_message(signum, stage_basename):
    """Format one approved ASCII form; name syntax is not creation evidence."""
    _signal_domain(signum)
    message = _FAILED if signum == 0 else _INTERRUPTED
    if stage_basename is None:
        return message
    if type(stage_basename) is not str or len(stage_basename) != 54:
        raise Refusal('unsafe_path')
    if not stage_basename.startswith(_STAGE_PREFIX):
        raise Refusal('unsafe_path')
    for index in range(22, 54):
        if stage_basename[index] not in '0123456789abcdef':
            raise Refusal('unsafe_path')
    return message + ' ' + _HINT_PREFIX + stage_basename + _HINT_SUFFIX
