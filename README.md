# ReplicateTable

Make the row grain and reduction order of an eager `xarray.Dataset` explicit, then preserve a source-bound plan, typed results, intermediate support counts, an HTML report and a row explanation.

**Experimental release candidate. Ordinary hosted-runner and final distribution qualification are pending.** The primary workflow is the Python eager-memory compute/report/explain API. It does not require the bundle backend's exact Linux kernel. Atomic bundle IO is a separate, optional, compatibility-limited experiment. Native NetCDF/HDF5 file APIs and the file-command CLI are not implemented.

## A concrete choice: pooled samples or equal replicates?

One replicate has observations `[10, 10, 10]`; another has `[30, missing, missing]`.

- Mean of all four observed samples: **15**
- Mean within each replicate, then equally across the two replicate means: **20**

Both are valid calculations. Which question you intend to answer is a scientific choice. ReplicateTable records that choice in an explicit recipe instead of inferring independence from dimensions or repetition.

Ordinary xarray can compute either answer in a line. ReplicateTable adds a bounded, reusable contract around the calculation: source and runtime binding, explicit missing-value/unit policies, exact typed serialization, per-stage support records, reload checks and a bounded row trace. It is useful when someone needs to inspect how a saved table was produced. If you only need a quick group mean, direct xarray or pandas is simpler.

Replay establishes same-engine consistency. It is not independent numerical proof, authenticity, or whole-operating-system attestation.

## Run the primary example

Use stock Linux x86_64 CPython 3.12/3.13 with the dependency versions pinned in `pyproject.toml`. The validated acquisition recipes select public CPython 3.12.14 and 3.13.5; a matching version string alone does not imply an identical bound runtime.

From a checkout, install and run:

```sh
python -m pip install .
python examples/eager_memory.py new-example-output
```

The example uses ordinary public Dataset construction and public ReplicateTable APIs. It checks the hand-derived 15/20 answers against explicit xarray controls, reloads saved plan/result JSON, repeats the computation, renders HTML, explains one row and rejects a later source mutation. It writes five loose exports to the new directory:

- `recipe.json`, `plan.json` and `result.json`
- `report.html` and `explanation.json`

The output directory must not already exist. These are ordinary example exports, not an atomic or verified bundle. No exact-kernel bundle API is called.

The public sequence is `snapshot_dataset` → `parse_recipe` → `compile_plan` → `execute`, with `load_plan`, `load_result`, `render_report` and `explain_row`. Loading a result is structural validation; explicit re-execution or the separately qualified bundle verifier is needed for replay.

## Supported data and limits

- A small, exact eager `xarray.Dataset`, with same-named one-dimensional dimension coordinates and supported ordinary numeric backing. Auxiliary coordinates, lazy arrays and unsupported storage are refused without being rewritten.
- Zero to two ordered reductions per output column, declared broadcasting and unit policies, and explicit missing-value handling.
- Exact dependency versions, fresh source/runtime checks, fixed byte/work ceilings and call-local logical memory admission. Large hidden array owners or unsupported caches may be refused even if a selected view is small.
- Caller-process execution. There is no worker RSS limit or preemptive 60-second wall-clock guarantee for the eager-memory route.
- Stable inputs during a call. Binding checks are not a hostile-mutation snapshot or a security boundary against the caller's own process.

CSV strings are data, not formulas to execute. HTML is escaped; rendering alone does not perform source replay.

## Optional experimental bundle IO

`write_bundle` and `verify_bundle` add genuine fixed-member filesystem acquisition, typed/digest/report checks, source replay and atomic no-overwrite installation. They currently require **Linux 6.18.44 x86_64**, qualified CPython profiles and a positively checked **tmpfs** directory with case folding disabled. `/tmp` is checked rather than assumed compatible. Other kernels, overlayfs and other filesystems refuse. This limitation does not apply to the primary eager-memory compute/report/explain example.

On the supported experimental profile only:

```sh
python examples/experimental_bundle.py
```

A bundle contains seven fixed root files and positional CSV/schema pairs for each reduction stage. Logical names never become file paths. The example creates a temporary real bundle, reloads it and performs all five verifier checks; its temporary directory is removed afterward.

Atomic no-replace protects existing destinations. An asynchronous caller exception or termination may still occur after kernel installation and before receipt delivery. Check the destination before retrying. Reconciliation is bounded and best effort, and cleanup never removes the requested destination. See [memory interruption semantics](docs/contracts/MEMORY-COMMIT-INTERRUPTION.md).

## Verification status

The unchanged synthetic corpora include independently derived scalar expectations and refusal controls. Component tests and local examples are evidence for their exact sources and environments, not a hosted release claim. Ordinary hosted CI is intended to exercise the primary public workflow and source/installed-wheel cells, and explicitly confirm unsupported native refusal. Experimental native-success cases are kept separate; skipped native cases are never counted as passes.

No ordinary hosted-runner pass or final release qualification is claimed yet. See the qualification receipts accompanying a future release, [public schemas](docs/contracts/API-SCHEMAS.md) and [resource contract](docs/contracts/RESOURCES.md).

MIT licensed. Interpreter and dependency binaries are not redistributed.
