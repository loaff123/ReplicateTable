"""Bounded eager-memory bundle orchestration over genuine native owners.

Temporary preparation is not installation. The original stage writer and its
first seal remain the native transaction's authority; only actual no-replace
installation may return a public committed receipt. File-native routes are not
implemented by substituting an eager source or a fabricated worker.
"""
import hashlib

from .errors import Refusal
from . import resources as r


def _detach(error):
    # Retire the escaping operation traceback using the base descriptor. Caller
    # cancellation/custom exceptions retain their unrelated cause/context/notes;
    # no custom attribute hook or caller frame/heap walk is invoked.
    BaseException.__traceback__.__set__(error, None)
    if isinstance(error, (Refusal, OSError)):
        BaseException.__context__.__set__(error, None)
        BaseException.__cause__.__set__(error, None)


def _owned_attempt(operation, *arguments):
    try:
        return operation(*arguments), None
    except BaseException as error:
        _detach(error)
        return None, error


def _raise_owned(error):
    if isinstance(error, (Refusal, OSError)):
        raise error from None
    raise error


def _close_stream(stream, primary):
    if stream is not None:
        try:
            stream.close()
        except BaseException as error:
            _detach(error)
            if not primary:
                raise


def _partial_bytes(backing, used):
    # No bytearray prefix copy: both borrowed views retire before append.
    whole = prefix = None
    try:
        whole = memoryview(backing)
        prefix = whole[:used]
        return bytes(prefix)
    finally:
        if prefix is not None: prefix.release()
        if whole is not None: whole.release()
        prefix = whole = backing = None


def _batch_chunks(writer, producer, ledger, budget):
    from . import _native_stage as native
    backing = bytearray(r.SERIAL_BUFFER_BYTES)
    used = 0
    fragment = chunk = None
    try:
        for fragment in producer:
            if type(fragment) is not bytes or len(fragment) > r.SERIAL_BUFFER_BYTES:
                raise Refusal('invalid_bundle')
            for byte in fragment:
                backing[used] = byte
                used += 1
                if used == r.SERIAL_BUFFER_BYTES:
                    chunk = bytes(backing)
                    ledger.feed(chunk)
                    native._append_stage_member(writer, chunk, budget)
                    chunk = None
                    used = 0
            fragment = None
        if used:
            chunk = _partial_bytes(backing, used)
            ledger.feed(chunk)
            native._append_stage_member(writer, chunk, budget)
            chunk = None
    finally:
        backing = fragment = chunk = producer = None


def _emit_member_inner(plan, result, writer, ledger, path, manifest, budget):
    from ._bundle_payload import _MemberStream
    from ._bundle_manifest import _manifest_chunks
    producer = None
    failed = False
    try:
        if path == 'manifest.json':
            ledger.begin_manifest()
            producer = _manifest_chunks(plan, manifest)
        else:
            ledger.begin(path)
            producer = _MemberStream(plan, result, path)
        _batch_chunks(writer, producer, ledger, budget)
        return None if path == 'manifest.json' else producer.counter
    except BaseException:
        failed = True
        raise
    finally:
        _close_stream(producer, failed)
        producer = None


def _emit_member(plan, result, writer, ledger, path, manifest, budget):
    counter, error = _owned_attempt(_emit_member_inner,
        plan, result, writer, ledger, path, manifest, budget)
    plan = result = writer = ledger = path = manifest = budget = None
    if error is not None: _raise_owned(error)
    return counter


def _same_counter(actual, expected):
    if (actual['size_bytes'] != expected['size_bytes'] or
            actual['sha256'] != expected['sha256']):
        raise Refusal('bundle_digest_mismatch')


def _write_member(plan, result, writer, ledger, path, manifest, budget):
    from . import _native_stage as native
    from ._bundle_payload import _member_budget
    from ._bundle_manifest import _manifest_budget
    bound = _manifest_budget(plan) if path == 'manifest.json' else _member_budget(plan, path)
    native._open_stage_member(writer, path, bound.estimated_bytes, budget)
    expected = _emit_member(plan, result, writer, ledger, path, manifest, budget)
    # All emission backing, partial views, producer/generator and formatter
    # helper frames have returned before native finish/close can be accepted.
    witness = native._finish_stage_member(writer, budget)
    completed = ledger.end()
    if witness.size != completed['size_bytes']:
        raise Refusal('bundle_digest_mismatch')
    if expected is not None: _same_counter(completed, expected)
    return completed


def _read_payload_inner(plan, result, writer, path, expected, budget):
    from . import _native_stage as native
    from ._bundle_payload import _MemberMatcher
    matcher = fragment = None
    failed = False
    try:
        native._open_stage_read(writer, path, budget)
        matcher = _MemberMatcher(plan, result, path)
        while True:
            fragment = native._read_stage_chunk(writer, r.SERIAL_BUFFER_BYTES, budget)
            if not fragment: break
            matcher.feed(fragment)
            fragment = None
        _same_counter(matcher.finish(), expected)
    except BaseException:
        failed = True
        raise
    finally:
        fragment = None
        try:
            _close_stream(matcher, failed)
        except BaseException:
            failed = True
            raise
        finally:
            matcher = None
            try:
                native._close_stage_member(writer)
            except BaseException as error:
                _detach(error)
                if not failed: raise


def _read_payload(plan, result, writer, path, expected, budget):
    _, error = _owned_attempt(_read_payload_inner, plan, result, writer, path, expected, budget)
    plan = result = writer = path = expected = budget = None
    if error is not None: _raise_owned(error)


def _next_nonempty(producer):
    for fragment in producer:
        if type(fragment) is not bytes or len(fragment) > r.SERIAL_BUFFER_BYTES:
            raise Refusal('invalid_bundle')
        if fragment: return fragment
    return None


def _read_manifest_inner(plan, writer, manifest, expected, budget):
    from . import _native_stage as native
    from ._bundle_manifest import _manifest_chunks
    producer = actual = pending = None
    failed = False
    offset = size = 0
    digest = hashlib.sha256()
    try:
        native._open_stage_read(writer, 'manifest.json', budget)
        producer = _manifest_chunks(plan, manifest)
        while True:
            actual = native._read_stage_chunk(writer, r.SERIAL_BUFFER_BYTES, budget)
            if not actual: break
            digest.update(actual)
            size += len(actual)
            for byte in actual:
                if pending is None:
                    pending = _next_nonempty(producer)
                    offset = 0
                if pending is None or byte != pending[offset]:
                    raise Refusal('invalid_bundle')
                offset += 1
                if offset == len(pending): pending = None
            actual = None
        if pending is not None or _next_nonempty(producer) is not None:
            raise Refusal('invalid_bundle')
        if size != expected['size_bytes'] or digest.hexdigest() != expected['sha256']:
            raise Refusal('bundle_digest_mismatch')
    except BaseException:
        failed = True
        raise
    finally:
        actual = pending = digest = None
        try:
            _close_stream(producer, failed)
        except BaseException:
            failed = True
            raise
        finally:
            producer = None
            try:
                native._close_stage_member(writer)
            except BaseException as error:
                _detach(error)
                if not failed: raise


def _read_manifest(plan, writer, manifest, expected, budget):
    _, error = _owned_attempt(_read_manifest_inner, plan, writer, manifest, expected, budget)
    plan = writer = manifest = expected = budget = None
    if error is not None: _raise_owned(error)


def _emit_validate_inner(plan, result, writer, budget, outcome):
    from . import _native_stage as native
    from ._bundle_payload import _PayloadLedger, _payload_paths
    from ._bundle_manifest import _make_manifest
    from ._bundle_models import PreparedReceipt
    ledger = paths = manifest = files = complete = None
    phase = 'structure'
    try:
        ledger = _PayloadLedger(plan)
        paths = _payload_paths(plan)
        for path in paths:
            _write_member(plan, result, writer, ledger, path, None, budget)
        paths.close()
        paths = None
        files = ledger.payload_files()
        manifest = _make_manifest(plan, result, files)
        manifest_counter = _write_member(plan, result, writer, ledger, 'manifest.json', manifest, budget)
        complete = ledger.finish()
        output_bytes = complete['bundle_bytes']
        # The complete-counter projection is temporary, not a retained copy.
        complete = ledger = None
        native._seal_stage(writer, budget)
        paths = _payload_paths(plan)
        for path in paths:
            if path != 'report.html':
                _read_payload(plan, result, writer, path, files[path], budget)
        paths.close()
        paths = None
        _read_manifest(plan, writer, manifest, manifest_counter, budget)
        _mark_check(outcome, 'structure', 'passed')
        phase = 'report'
        # Regenerated report is its own semantic check, after structure.
        _read_payload(plan, result, writer, 'report.html', files['report.html'], budget)
        _mark_check(outcome, 'report', 'passed')
        return PreparedReceipt(version=2, kind='bundle', source=plan.source,
            recipe_sha256=manifest['recipe_sha256'], plan_sha256=manifest['plan_sha256'],
            result_sha256=manifest['result_sha256'], runtime_sha256=manifest['runtime_sha256'],
            manifest_sha256=manifest_counter['sha256'], output_bytes=output_bytes)
    except BaseException as error:
        _failed_check(outcome, phase, error)
        raise
    finally:
        if paths is not None: paths.close()
        ledger = paths = manifest = files = complete = None


def _emit_validate(plan, result, writer, budget, outcome):
    prepared, error = _owned_attempt(_emit_validate_inner, plan, result, writer, budget, outcome)
    plan = result = writer = budget = outcome = None
    if error is not None: _raise_owned(error)
    return prepared


def _prepare_memory_inner(plan, result, root, budget, outcome):
    from . import _native_stage as native
    from .admission import _required_inputs, _guard
    from .plan import _plan_exact, _plan_selected
    from .source import _selection_snapshot, recheck_source
    from .runtime import require_runtime
    from ._native_budget_state import LogicalOnlyBudget, _checkpoint
    from ._replay import _require_exact_replay
    _plan_exact(plan)
    source = plan._source
    _selection_snapshot(source, _plan_selected(plan), expected=plan.source)
    if type(budget) is not LogicalOnlyBudget: raise Refusal('supervision_unavailable')
    writer = None
    with _required_inputs(plan=plan, snapshot=source, result=result):
        _guard('materialized')
        try:
            require_runtime(plan.runtime)
        except BaseException as error:
            _failed_check(outcome, 'runtime_binding', error)
            raise
        _mark_check(outcome, 'runtime_binding', 'passed')
        try:
            recheck_source(source)
        except BaseException as error:
            _failed_check(outcome, 'source_binding', error)
            raise
        _mark_check(outcome, 'source_binding', 'passed')
        _checkpoint(budget)
        try:
            writer = native._begin_stage_writer(root, 'bundle', budget)
            prepared = _emit_validate(plan, result, writer, budget, outcome)
            # The ledger, manifest, emission/matcher and read helpers returned.
            # This is the exact supplied plan source, with caller A/B/C live.
            try:
                digest = _require_exact_replay(plan, source, result)
                if digest != prepared.result_sha256:
                    raise Refusal('result_replay_mismatch')
            except BaseException as error:
                _failed_check(outcome, 'replay', error)
                raise
            _mark_check(outcome, 'replay', 'passed')
            recheck_source(source)
            require_runtime(plan.runtime)
            _guard('serialize')
            _checkpoint(budget)
            return writer, prepared
        except BaseException:
            if writer is not None:
                try:
                    native._close_stage_writer(writer, quiet=True)
                except BaseException as cleanup:
                    _detach(cleanup)
            raise


def _prepare_memory_bundle(plan, result, root, budget, outcome=None):
    """Return genuine validated temporary writer and compact prepared receipt."""
    value, error = _owned_attempt(_prepare_memory_inner, plan, result, root, budget, outcome)
    plan = result = root = budget = outcome = None
    if error is not None: _raise_owned(error)
    return value


def _mark_check(outcome, name, status):
    if outcome is not None:
        from ._native_supervisor import _record_check
        _record_check(outcome, name, status)


def _failed_check(outcome, phase, error):
    if outcome is None or not isinstance(error, Refusal): return
    code = error.code
    if code == 'invalid_runtime' or code.startswith('runtime_'):
        phase = 'runtime_binding'
    elif code in ('source_changed', 'source_fingerprint_mismatch',
                  'source_resource_binding_mismatch', 'invalid_source',
                  'invalid_source_phase', 'unsupported_source_storage'):
        phase = 'source_binding'
    elif code == 'report_mismatch':
        phase = 'report'
    elif code == 'result_replay_mismatch':
        phase = 'replay'
    if phase is not None: _mark_check(outcome, phase, 'failed')


def _close_transaction(writer, root, primary):
    from . import _native_stage as native
    from . import _native_workspace as workspace
    from . import _native_fs_generated as roots
    failure = None
    if writer is not None:
        try:
            native._close_stage_writer(writer, quiet=primary)
        except BaseException as error:
            _detach(error)
            if not primary: failure = error
    if root is not None:
        try:
            workspace._cleanup_empty_root(root)
        except BaseException as error:
            _detach(error)
            if not primary and failure is None: failure = error
        try:
            roots._close_generated_root(root)
        except BaseException as error:
            _detach(error)
            if not primary and failure is None: failure = error
    if failure is not None: raise failure


def _write_memory_attempt(plan, result, destination, outcome):
    from .admission import _required_inputs, _guard
    from .plan import _plan_exact, _plan_selected
    from .source import _selection_snapshot, recheck_source
    from .runtime import require_runtime
    from ._native_budget_state import LogicalOnlyBudget
    from . import _native_fs_generated as roots
    from . import _native_workspace as workspace
    from ._native_commit import _install_memory_bundle
    _plan_exact(plan)
    source = plan._source
    _selection_snapshot(source, _plan_selected(plan), expected=plan.source)
    with _required_inputs(plan=plan, snapshot=source, result=result):
        # A genuine complete eager-memory closure qualifies this route before
        # a logical-only IO budget can exist. No worker policy is entered.
        _guard('materialized')
        try:
            require_runtime(plan.runtime)
        except BaseException as error:
            _failed_check(outcome, 'runtime_binding', error)
            raise
        _mark_check(outcome, 'runtime_binding', 'passed')
        try:
            recheck_source(source)
        except BaseException as error:
            _failed_check(outcome, 'source_binding', error)
            raise
        _mark_check(outcome, 'source_binding', 'passed')
        budget = LogicalOnlyBudget(outcome.cancellation)
        root = writer = None
        failed = False
        try:
            root = roots._prepare_stage_root(destination, (), budget)
            workspace._create_generated_root(root, budget)
            writer, prepared = _prepare_memory_bundle(plan, result, root, budget, outcome)
            # The final native installer rechecks the original sealed stage and
            # its parent, observes cancellation, and alone obtains commit authority.
            return _install_memory_bundle(writer, prepared, outcome, budget)
        except BaseException as error:
            failed = True
            _failed_check(outcome, None, error)
            raise
        finally:
            _close_transaction(writer, root, failed)
            writer = root = None


def write_bundle(plan, result, destination):
    """Install an exact-source-replayed eager-memory bundle without overwrite.

    This path uses cooperative logical cancellation and no native worker, RSS
    sampling, or preemptive clock. Arbitrary asynchronous Python interruption
    may prevent delivery after kernel commit; the destination is never deleted.
    """
    from ._native_budget_state import _CancellationState
    from ._native_supervisor import _Outcome, _record_failure, _error_from_outcome
    from .errors import ComputationError
    outcome = _Outcome(_CancellationState())
    receipt, error = _owned_attempt(_write_memory_attempt, plan, result, destination, outcome)
    plan = result = destination = None
    if error is not None:
        if isinstance(error, OSError):
            error = ComputationError('io_error')
        if isinstance(error, Refusal):
            _record_failure(outcome, error.code, error.message, error.exit_code)
            error = _error_from_outcome(outcome)
        outcome = None
        _raise_owned(error)
    return receipt


def _member_size(reader, path):
    for entry in reader.entries:
        if entry.path == path: return entry.witness.size
    raise Refusal('invalid_bundle')


def _read_external_raw(reader, path, maximum, budget, source=None, ledger=None):
    from . import _native_bundle_reader as native
    from .admission import _guard, _active_plan
    from .plan import _load_source_base
    from ._resource_bounds import _checked_add
    size = _member_size(reader, path)
    if size > maximum: raise Refusal('bundle_bytes_limit' if path == 'result.json' else 'metadata_bytes_limit')
    if _active_plan() is None:
        # The original source and fixed reader reserve are freshly measured
        # before both raw-buffer occupants. Strict plan parsing follows with
        # its own fresh complete 5N+3P guard and the same live reader reserve.
        _checked_add(_load_source_base(source), 2*size, limit=r.LOGICAL_JOURNEY_LIMIT)
    else:
        # The complete canonical model budget contains the bounded raw input /
        # decode serial phase. The actual member size is limited by that plan.
        _guard('serialize')
    backing = fragment = None
    failed = False
    try:
        native._open_bundle_member(reader, path, budget)
        backing = bytearray(size)
        offset = 0
        while True:
            fragment = native._read_bundle_chunk(reader, r.SERIAL_BUFFER_BYTES, budget)
            if not fragment: break
            if ledger is not None: ledger.feed(fragment)
            for byte in fragment:
                if offset >= size: raise Refusal('bundle_changed')
                backing[offset] = byte
                offset += 1
            fragment = None
        if offset != size: raise Refusal('bundle_changed')
        return bytes(backing)
    except BaseException:
        failed = True
        raise
    finally:
        backing = fragment = None
        try:
            native._close_bundle_member(reader)
        except BaseException as error:
            _detach(error)
            if not failed: raise


def _load_external_plan_inner(reader, source, budget):
    from .plan import load_plan
    raw = _read_external_raw(reader, 'plan.json', r.METADATA_BYTES_LIMIT, budget, source)
    digest = hashlib.sha256(raw).hexdigest()
    return load_plan(raw, source), digest


def _load_external_plan(reader, source, budget):
    value, error = _owned_attempt(_load_external_plan_inner, reader, source, budget)
    reader = source = budget = None
    if error is not None: _raise_owned(error)
    return value


def _load_external_result_inner(reader, plan, budget):
    from .reduce import load_result
    raw = _read_external_raw(reader, 'result.json', plan.estimates['result_json_bytes'], budget)
    digest = hashlib.sha256(raw).hexdigest()
    return load_result(raw, plan), digest


def _load_external_result(reader, plan, budget):
    value, error = _owned_attempt(_load_external_result_inner, reader, plan, budget)
    reader = plan = budget = None
    if error is not None: _raise_owned(error)
    return value


def _require_external_members(reader, plan):
    from ._bundle_payload import _payload_paths
    count = 1  # manifest, deliberately absent from the payload map.
    paths = _payload_paths(plan)
    try:
        for path in paths:
            _member_size(reader, path)
            count += 1
    finally:
        paths.close()
    if count > 7:
        _member_size(reader, 'support')
        count += 1
    if len(reader.entries) != count: raise Refusal('invalid_bundle')


def _read_external_payload_inner(reader, plan, result, path, expected, budget):
    from . import _native_bundle_reader as native
    from ._bundle_payload import _MemberMatcher
    matcher = fragment = None
    failed = False
    try:
        native._open_bundle_member(reader, path, budget)
        matcher = _MemberMatcher(plan, result, path)
        while True:
            fragment = native._read_bundle_chunk(reader, r.SERIAL_BUFFER_BYTES, budget)
            if not fragment: break
            matcher.feed(fragment)
            fragment = None
        _same_counter(matcher.finish(), expected)
    except BaseException:
        failed = True
        raise
    finally:
        fragment = None
        try:
            _close_stream(matcher, failed)
        except BaseException:
            failed = True
            raise
        finally:
            matcher = None
            try:
                native._close_bundle_member(reader)
            except BaseException as error:
                _detach(error)
                if not failed: raise


def _read_external_payload(reader, plan, result, path, expected, budget):
    _, error = _owned_attempt(_read_external_payload_inner, reader, plan, result, path, expected, budget)
    reader = plan = result = path = expected = budget = None
    if error is not None: _raise_owned(error)


def _hash_external_member(reader, ledger, path, budget):
    from . import _native_bundle_reader as native
    fragment = None
    failed = False
    try:
        ledger.begin(path)
        native._open_bundle_member(reader, path, budget)
        while True:
            fragment = native._read_bundle_chunk(reader, r.SERIAL_BUFFER_BYTES, budget)
            if not fragment: break
            ledger.feed(fragment)
            fragment = None
        ledger.end()
    except BaseException:
        failed = True
        raise
    finally:
        fragment = None
        try:
            native._close_bundle_member(reader)
        except BaseException as error:
            _detach(error)
            if not failed: raise


def _load_external_manifest_inner(reader, plan, result, ledger, files, budget):
    from ._bundle_manifest import _load_manifest
    ledger.begin_manifest()
    raw = _read_external_raw(reader, 'manifest.json', plan.estimates['manifest_json_bytes'], budget, ledger=ledger)
    counter = ledger.end()
    return _load_manifest(raw, plan, result, files), counter['sha256']


def _load_external_manifest(reader, plan, result, ledger, files, budget):
    value, error = _owned_attempt(_load_external_manifest_inner, reader, plan, result, ledger, files, budget)
    reader = plan = result = ledger = files = budget = None
    if error is not None: _raise_owned(error)
    return value


def _verify_structure_inner(reader, plan, result, budget, outcome, bindings):
    from . import _native_bundle_reader as native
    from ._bundle_payload import _PayloadLedger, _payload_paths
    ledger = files = manifest = paths = complete = None
    phase = 'structure'
    try:
        _require_external_members(reader, plan)
        ledger = _PayloadLedger(plan)
        paths = _payload_paths(plan)
        for path in paths: _hash_external_member(reader, ledger, path, budget)
        paths.close()
        paths = None
        files = ledger.payload_files()
        manifest, manifest_digest = _load_external_manifest(reader, plan, result, ledger, files, budget)
        bindings[3] = manifest_digest
        complete = ledger.finish()
        if complete['bundle_bytes'] != reader.total_bytes:
            raise Refusal('bundle_digest_mismatch')
        complete = ledger = None
        if manifest['plan_sha256'] != bindings[1] or manifest['result_sha256'] != bindings[2]:
            raise Refusal('bundle_digest_mismatch')
        paths = _payload_paths(plan)
        for path in paths:
            if path != 'report.html':
                _read_external_payload(reader, plan, result, path, files[path], budget)
        paths.close()
        paths = None
        native._recheck_bundle_reader(reader, budget)
        _mark_check(outcome, 'structure', 'passed')
        phase = 'report'
        _read_external_payload(reader, plan, result, 'report.html', files['report.html'], budget)
        _mark_check(outcome, 'report', 'passed')
    except BaseException as error:
        _failed_check(outcome, phase, error)
        raise
    finally:
        if paths is not None: paths.close()
        ledger = files = manifest = paths = complete = None


def _verify_structure(reader, plan, result, budget, outcome, bindings):
    _, error = _owned_attempt(_verify_structure_inner, reader, plan, result, budget, outcome, bindings)
    reader = plan = result = budget = outcome = bindings = None
    if error is not None: _raise_owned(error)


def _verify_memory_attempt(source, directory, outcome, bindings):
    from . import _native_bundle_reader as native
    from .admission import _BundleReaderScope, _required_inputs, _guard
    from .source import recheck_source
    from .runtime import require_runtime
    from ._replay import _require_exact_replay
    from ._native_budget_state import LogicalOnlyBudget, _checkpoint
    reader = plan = result = None
    failed = False
    phase = 'source_binding'
    with _BundleReaderScope(source) as scope:
        try:
            recheck_source(source)
            budget = LogicalOnlyBudget(outcome.cancellation)
            phase = 'structure'
            reader = native._open_bundle_reader(directory, budget)
            scope.adopt(reader)
            plan, bindings[1] = _load_external_plan(reader, source, budget)
            bindings[0] = plan.source
            _mark_check(outcome, 'source_binding', 'passed')
            _mark_check(outcome, 'runtime_binding', 'passed')
            _require_external_members(reader, plan)
            with _required_inputs(plan=plan, snapshot=source):
                _guard('serialize')
                result, bindings[2] = _load_external_result(reader, plan, budget)
                with _required_inputs(plan=plan, snapshot=source, result=result):
                    _guard('materialized')
                    _verify_structure(reader, plan, result, budget, outcome, bindings)
                    phase = 'replay'
                    digest = _require_exact_replay(plan, source, result)
                    if digest != bindings[2]: raise Refusal('result_replay_mismatch')
                    _mark_check(outcome, 'replay', 'passed')
                    phase = 'source_binding'
                    recheck_source(source)
                    require_runtime(plan.runtime)
                    _guard('serialize')
                    phase = 'structure'
                    native._recheck_bundle_reader(reader, budget)
                    _checkpoint(budget)
        except BaseException as error:
            failed = True
            _failed_check(outcome, phase, error)
            raise
        finally:
            plan = result = None
            if reader is not None:
                try:
                    native._close_bundle_reader(reader, quiet=failed)
                except BaseException as error:
                    _detach(error)
                    if not failed: raise
            reader = None


def verify_bundle(source, directory):
    """Read and verify an ordinary bundle against the exact eager source.

    Every file is acquired through original anchored witnesses, then strict
    shape/digests/typed duplication, regenerated report and exact same-engine
    source replay are checked independently. This is not independent numerical
    proof and does not introduce the unsupported native file-source route.
    """
    from ._native_budget_state import _CancellationState
    from ._native_supervisor import _Outcome, _record_failure
    from ._bundle_models import BundleVerification
    from .errors import ComputationError
    outcome = _Outcome(_CancellationState())
    bindings = [None, None, None, None]
    _, error = _owned_attempt(_verify_memory_attempt, source, directory, outcome, bindings)
    source = directory = None
    if error is not None:
        if isinstance(error, OSError): error = ComputationError('io_error')
        if not isinstance(error, Refusal):
            outcome = bindings = None
            _raise_owned(error)
        _record_failure(outcome, error.code, error.message, error.exit_code)
    return BundleVerification(version=2, status='verified' if error is None else outcome.status,
        checks=outcome.checks, source=bindings[0], plan_sha256=bindings[1],
        result_sha256=bindings[2], manifest_sha256=bindings[3], finding=outcome.finding,
        committed=False)
