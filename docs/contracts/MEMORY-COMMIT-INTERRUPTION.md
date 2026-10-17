# Eager-memory atomic installation and interruption

Status: current eager-memory installation and interruption behavior.
No native-worker guarantees, accepted datatype, cap, public field or CLI grammar
are changed. Existing in-memory calls remain valid in ordinary background
threads; they do not acquire native launch's quiescence restrictions.

The filesystem operation remains a genuine anchored Linux renameat2 with
RENAME_NOREPLACE. It cannot overwrite an existing destination. The owning route
must finish actual source/runtime/replay/stage checks, then the shared logical
budget's final cooperative cancellation checkpoint before attempting rename.
Cancellation observed by that checkpoint prevents the attempt. Cancellation
observed afterward may accompany committed output. No checkpoint is inserted
between the successful syscall return and recording the prepared committed
receipt and installed ownership state.

Python bytecodes and a foreign-function syscall return are not an atomic region
against arbitrary asynchronous exceptions. Such a caller exception, forced
termination, or failed delivery can prevent receipt capture or return after the
kernel has committed the rename. No rollback or guaranteed receipt delivery is
promised for that case. The product never deletes the requested destination as
cleanup, whether or not in-memory capture completed.

On a catchable exception after an install attempt, bounded best-effort
reconciliation uses the already-held destination-parent and stage descriptors,
the actual original created directory identity, and no-follow observations of
the destination and old temporary name. A matching original destination inode
and absent old temporary entry establish the actual installed state; a prepared
scalar receipt alone never does. If reconciliation cannot finish, propagate the
same caller exception object with its existing notes and exception-chain details,
and retain residue/state conservatively. Its traceback may be shortened. Earlier
source/replay validation separately sanitizes traceback and chaining links to
release temporary state; cause/context preservation is not promised throughout
the whole transaction. The exception object and notes are preserved. The user
must inspect the destination before retrying after interruption. A later
output_exists refusal never implies that the existing output is valid.

Ordinary success requires confirmed installation and returns its committed
receipt. This clarification is specifically the eager-memory path; the managed
native-worker policy, adopted exact-PID reap, and CLI remain separately gated.
