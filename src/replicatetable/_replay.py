"""One complete source-bound same-engine replay, never independent proof.

The owning writer/explainer establishes the genuine original A/B/C input
closure. This helper returns a digest only after its replay result and both
borrowed-result stream frames have ended. It preserves runtime/source refusal
and cancellation classification, rather than calling every failure a mismatch.
"""
import hashlib

from .errors import Refusal


def _retire_replay_streams(left, right, has_primary):
    failure = None
    for stream in (left, right):
        if stream is None:
            continue
        try:
            stream.close()
        except BaseException as cleanup:
            # These are only this operation's two owned close attempts.
            # Their failures cannot replace an already established finding.
            BaseException.__traceback__.__set__(cleanup, None)
            BaseException.__context__.__set__(cleanup, None)
            BaseException.__cause__.__set__(cleanup, None)
            if not has_primary and failure is None:
                failure = cleanup
    return failure


def _compare_replay(plan, source, result):
    from .admission import _ACTIVE, _guard
    from .reduce import execute
    from ._result import _result_chunks
    active = _ACTIVE.get()
    if active is None or active.plan is not plan or active.result is not result:
        raise Refusal('invalid_plan_input')
    _guard('materialized')
    replay = left = right = None
    failed = False
    try:
        replay = execute(plan, source)
        left = _result_chunks(result)
        right = _result_chunks(replay)
        digest = hashlib.sha256()
        while True:
            a = next(left, None)
            b = next(right, None)
            if a != b:
                raise Refusal('result_replay_mismatch')
            if a is None:
                return digest.hexdigest()
            digest.update(a)
    except BaseException:
        # Track this operation's own escape. sys.exception() would also see
        # an unrelated caller's active except block during a normal return.
        failed = True
        raise
    finally:
        # Private streams borrow the full result. Explicit closure covers
        # early mismatch/cancellation as well as ordinary exhaustion.
        try:
            failure = _retire_replay_streams(left, right, failed)
        finally:
            replay = left = right = active = None
        if failure is not None:
            raise failure


def _require_exact_replay(plan, source, result):
    from .source import _owned_attempt, _raise_owned
    digest, error = _owned_attempt(_compare_replay, plan, source, result)
    plan = source = result = None
    if error is not None: _raise_owned(error)
    return digest
