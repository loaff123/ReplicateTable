# Portable public-workflow qualification

This is an explicit, limited qualification lane for ordinary Linux x86_64
CPython. It runs the actual public eager-memory example from source and from an
installed wheel. It does not claim the complete regression suite, native bundle
success, CLI support, or a file-native source route.

## Exact public runtimes

| Profile | CPython | Executable SHA-256 |
| --- | --- | --- |
| public312 | 3.12.14 | edffa803e5c4d73a1357f7f2c6c9fd38e9693712b2c06793e6a5e5cc1090d03a |
| public313 | 3.13.5 | 0eba26d5f04a3673ee264ca406ef286d5025da098c1a24987a8118c23d69153c |

`runtime-inputs/` is an unchanged text-only subset of the pinned public runtime
preparation. `RUNTIME-INPUTS-MANIFEST.json` hashes every copied input. It includes
the exact official release asset URLs, archive sizes and hashes, executable
hashes, exact PyPI wheel URLs, hashes, RECORD/license observations, and six
dependency/installer lock files. There are no interpreters, wheels, downloaded
archives, credentials, or absolute local-origin reports in these inputs.
Consult `runtime-inputs/PUBLIC-REPRODUCTION.md` and `QUALIFICATION-LIMITS.md` for
the original preparation scope. Runtime preparation is separate from product
qualification. No moving Python selector or dependency resolver is used.

## Reproduce from a fresh checkout

Prerequisites: ordinary Ubuntu 24.04 x86_64, trusted bootstrap Python >=3.12,
bash, curl, HTTPS access to the official GitHub/PyPI URLs, and sufficient disk.
The output parent must be an ordinary non-tmpfs filesystem so the experimental
bundle restriction can be tested. Do not run with `python -O`.

Run from the repository root. `$HOME/replicatetable-qualification` must be new
and outside the checkout; these commands deliberately refuse existing output.

```sh
WORK="$HOME/replicatetable-qualification"
mkdir "$WORK"
for PROFILE in public312 public313; do
  bash qualification/prepare_profile.sh "$PROFILE" "$WORK/runtime-$PROFILE"
  python3 -I -S -B qualification/run_cell.py \
    --runtime "$WORK/runtime-$PROFILE" --profile "$PROFILE" \
    --lane source --output "$WORK/$PROFILE-source"
  python3 -I -S -B qualification/run_cell.py \
    --runtime "$WORK/runtime-$PROFILE" --profile "$PROFILE" \
    --lane wheel --output "$WORK/$PROFILE-wheel"
done
```

To use an already prepared exact runtime, omit acquisition and pass its root
(the directory containing `profiles/` and `downloads/`) to `run_cell.py`.
Every cell freshly verifies both interpreter executables, all 21 locked wheel
artifacts, the selected stdlib files, the 15 runtime dependency inventories,
distribution versions and actual dependency origins before running product code.

The cell runs with `-I -B`, no `PYTHONPATH`/`PYTHONHOME`, and all six native thread
limits set to 1. It never alters a runtime/profile gate. The source lane adds
only its explicit `src` directory. The wheel lane builds an sdist and then a
wheel from that sdist using the locked build tools without build isolation or
network dependency resolution. It installs into a new copied-interpreter venv
using the exact offline wheel closure, then runs `pip check`. Its product probe
receives no source-package argument, never adds source or tests to `sys.path`,
and verifies every product payload file and loaded module against the candidate
manifest and the selected site-packages location. The example is copied outside
the checkout. There is no wheel-to-source fallback.

An already completed build/install can be reused with `--reuse-wheel-cell
/absolute/path/to/prior-wheel-cell`. The frozen supervisor verifies the archived
wheel hash, source payload equality, exact interpreter, every pinned dependency
inventory and live import origin in that venv again before a fresh product
probe. The prior build/install receipt hash is retained; an earlier successful
probe is never substituted for the new one.

## What each zero-skip cell proves

- The public example runs snapshot, recipe parsing, compilation, execution,
  saved plan/result reload and same-engine replay, HTML report, and row explanation.
- Hand-derived results are 15/20 and 115/120 for pooled/equal-replicate means,
  with ordinary xarray controls. Changed source content raises `source_changed`.
- Exactly five loose export files are written; these are not an atomic bundle.
- The actual unmodified native bundle path refuses the ordinary output parent
  with `unsafe_path`, no commit receipt, and no new output/staging entries.
- On an unsupported kernel the receipt identifies the kernel-profile boundary.
  If the exact Linux 6.18.44 profile appears, it identifies the filesystem
  boundary instead. The local Linux 6.18.44 overlay check cannot establish
  behavior on a different hosted kernel.
- A file path is refused by `snapshot_dataset` with `invalid_source`;
  there is no package `__main__` or installed console-script entry point.
- Source/installed-wheel product origins and byte identity remain explicit.

The checks are direct assertions, with no skip facility. No instrumented unit
test, synthetic runtime, or profile monkeypatch is counted as real hosted
execution. Native bundle success is a separate experimental qualification on
the exact supported tmpfs profile; a successful native write in this lane is
reported as an unexpected profile and fails this negative cell.

## Receipts, liveness, and failure semantics

Each cell has `cell.json` plus `probe/receipt.json`, the product file manifest,
runtime preflight, five example exports, and bounded command logs. A running
cell first snapshots its entire qualification directory and public example,
hashes every input, and re-executes the frozen supervisor. Its recorded runner,
probe, exact acquisition/lock recipes and example bytes cannot be blurred by
later checkout edits. The snapshot is checked again at completion. A running
command emits and saves liveness every 120 seconds. The default whole-cell
timeout is 1,200 seconds; `--timeout-seconds` changes that explicit budget.
Ordinary child exceptions/nonzero exits become a terminal failed receipt.
If the supervisor itself is killed, a missing terminal receipt or `running`
state means incomplete, never pass. Preserve that attempt and use a new output
directory for a retry. Local receipts contain absolute execution paths and must
not be presented as a publication whitelist.

## Hosted workflow and status

`.github/workflows/portable-qualification.yml` targets `ubuntu-24.04`, with a
matrix of the two exact public runtimes. It preserves receipts for source and
installed-wheel cells even if another cell fails. Its external actions are
pinned to official release commits:

- [checkout v5.0.0](https://github.com/actions/checkout/releases/tag/v5.0.0),
  `08c6903cd8c0fde910a37f88322edcfb5dd907a8`, Node 24; runner >=2.327.1.
- [upload-artifact v4.6.2](https://github.com/actions/upload-artifact/releases/tag/v4.6.2),
  `ea165f8d65b6e75b540449e92b4886f43607fa02`.

Adding this workflow is not evidence that GitHub Actions ran it. Hosted
qualification remains pending until the exact candidate is published with
authorization, the workflow runs, and all four terminal receipts are inspected
for that commit. Local results are local only; separately retained local
receipts cannot substitute for a hosted run.

## Proposed later regression schedule

After these four portable cells pass, run existing regression modules in
separate moderate-duration source/installed-wheel groups with one durable
receipt per group. Keep instrumentation/schema tests labelled as such and keep
exact-kernel/tmpfs success tests in their own experimental lane. Inventory each
collected test ID and every skip/failure; never relabel unsupported native
success tests as portable passes. Do not launch the historical monolithic full
suite without this separation: absence of a terminal receipt proves nothing.
