# Test-first reconstruction and qualification plan

Status: execution plan candidate, 2026-10-06, with accepted native design closures integrated 2026-10-07. This artifact is a design and verification plan; it is not a release-qualification claim. Contract/API/resource approval and a fresh isolated implementation checkpoint precede implementation. This plan implements only ReplicateTable under CONTRACT, API-SCHEMAS, RESOURCES and NATIVE-LIFECYCLE.

## 1. Delivery and review gates

Initial native filesystem qualification is the experimental Linux6.18.44 x86_64/tmpfs-only profile in NATIVE-FILESYSTEM-PROFILE. Unsupported kernel/filesystem/per-directory feature observations must retain their explicit refusal boundary. PublicCI on another profile may verify refusal and name skipped native-success cases; it cannot silently widen the profile. Overlay's ordinary FUSE backing counterexample remains a withdrawn-admission finding. Qualify the existing /tmp journeys first; any practical direct filesystem addition needs independent source/feature/actual-runtime evidence. The eager-memory workflow and native limitations must be presented separately at release.

The design is architectural: missing model/source/resource/serialization/transaction code is newly implemented. Recovered units/runtime/explanation/reducer texts are references, not a product baseline. No historical source commit, test count, approval, timing or RSS result carries forward. Exact fixture/oracle bytes remain read-only.

Execution method: one controlled implementation effort with small dependency-ordered increments. Parallelize only genuinely independent tests/reviews/artifact acquisition after frozen interfaces; do not have two writers edit the same model/source/resource module. Each implementation increment is bound to the exact approved document hashes and only the assigned outcome/files. Independent reviewer gets final files/diffs and normative contract, not the implementer's private reasoning.

Every implementation increment follows:

1. Write narrowly scoped behavioral tests against the frozen interface; state the production defect each test would detect
2. Preserve first intended failing command output and exit receipt before implementing the missing behavior; a syntax/import accident is not the intended red unless a missing export is the feature under test
3. Implement the smallest cohesive behavior, run focused tests, then the complete available project suite; record all failures, including unrelated failures
4. Review exact public types, refusal precedence, fresh admission, immutable backing/lifetime, byte counters and semantic behavior together; no code-only review that ignores allocation effects
5. Resolve critical/important findings, rerun focused/full tests, freeze changed source with a complete sorted manifest and source hashes
6. Preserve complete changed source/tests/docs with a sorted hash/mode manifest and a durable checkpoint BEFORE candidate review or execution; each later changed slice needs a new immutable export. Review that exact checkpoint before long profile/qualification runs. Publication and dependency distribution require their separate authorization
7. Run longer checks only on that frozen source, with import origins and hashes proving the tested bytes. Later edits invalidate affected evidence; do not repair a candidate while its final cells are running

Review can reject a reconstructed choice; no cap increase or silent accepted-domain contraction is an implementation convenience. A design amendment receives fresh hashes and affected tests before continuing. An expected wrapper/layout mismatch is a blocked preflight, not permission for generic reflection/callbacks.

## 2. Product file map (NEW module boundaries)

- pyproject.toml, MANIFEST.in, LICENSE, README.md: exact pins, package/console metadata, MIT2026, reproducible user flows, limits and no unsupported claims
- src/replicatetable/__init__.py: only documented API/model exports
- model.py: exact scalar/name/dtype/primitive validation; immutable Recipe/Coordinate/SourceSnapshot/BoundPlan models; no native IO or unit engine
- codec.py: strict UTF-8 JSON lexical preflight/duplicate detection/canonical scalar/field streaming; bounded J/P projections; no arbitrary object serialization
- resources.py: all caps, formula2, cardinality/work bounds, output component projections and actual counters
- source.py: safe eager-source qualification, exact source phases, owner/descriptor prepass, identity framing, selected preparation/materialization/rechecks
- admission.py: call-local required Dataset closure, exact cache profile, fresh scalar-only admission/guard; no arbitrary heap walk
- runtime.py: reviewed recovered runtime binding integration with only necessary model/helper adapters
- units.py: reviewed recovered stock-Pint qualification and normalization integration
- plan.py: strict recipe topology, compile/recompile, semantic/resource binding separation and persisted reanchor behavior
- reduce.py: reviewed/new reducer integration; sequential columns, exact direct integers, support records, structurally bounded result model and serialization
- _native.py: trusted root NetCDF4/HDF5 metadata/data adapter, fixed scalar/string/native bounds; no public unsupervised entry
- supervision.py: one worker, shared contexts, absolute deadline, sampled PID RSS, exclusive wait/reap, signals and lifecycle
- _wire.py: exact bounded control and typed primitive/raw API return framing; no pickle/generic object deserialization
- _filesystem.py: anchored safe descriptors, original witnesses, stage ownership, no-replace commit and cleanup
- report.py: exact golden report-v2 renderer, scalar text-node escaping/visible labels/typed dtype headers
- bundle.py: streaming seven-root/stage outputs, exact manifest, typed parse checks, replay verification, worker/parent commit receipts
- explain.py: reviewed reconstruction of immutable trace model, one replay and selected trace, global byte stop, three mandatory constructor fixes
- cli.py: exact grammar/main deadline, dispatch to one worker, protected nonblocking stdout/stderr streaming after reap
- tests/: unit/integration/refusal/real OS/lifetime/packaging tests separated by subject, no product-only test seams except specifically labeled scalar arithmetic/private metadata seams
- docs/: approved contract/API/resources and focused truthful guides; examples/: public benign fixtures/recipes/readme flows; qualification/: compact public-safe methodology/result summaries only

Private acquisition archives, absolute paths, raw inventories, logs, owned-runtime installs, calibration probes, publication receipts and reviewer working notes stay outside source/distributions. No dependency/interpreter redistribution.

## 3. Stage A: freeze inputs and acquire fresh profiles

### A1. Recovered-byte/provenance audit

Create private manifest of all13 original artifacts, exact baseline.py, exact units.py/test_units.py, runtime.py/contracts/tests, recovered earlier reducer, exact recovered explanation v1 with known pending fixes and pending fixes. Confirm all original freeze hashes and independently record exact current bytes. Inventory absent source/test/schema bodies as absent; do not infer source from old85-file manifest. Preserve original fixture bytes. Freeze explicit test-only weight_unit:null adapter as new test code; it may only add that required field on freshly allocated historical unitless weighted stages, with input/output diff assertions.

Tests first: artifact manifest verification fails on a one-byte temporary copy mutation; adapter refuses to change any other key/value/order or original file. No candidate engine imports for this stage. Check all fourteen original refusal controls by their exact frozen code, with no code translation; the only allowed original-recipe migration remains the already documented test-only weight_unit:null insertion. Exit gate: original hashes verified; original fixture dimensional/variable/column/modeled-work limits individually below the new maxima. Combined formula qualification waits for the new estimator.

### A2. Public interpreter/wheel acquisition

Reacquire from verified official public provider links; do not invent missing historical URLs. Verify before extraction/run:

- public312: CPython3.12.14, python-build-standalone release20260924; archive SHA256269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41; observed archive34270188 bytes; executable SHA256edffa803e5c4d73a1357f7f2c6c9fd38e9693712b2c06793e6a5e5cc1090d03a
- public313: CPython3.13.5, python-build-standalone release20250723; archive SHA256f7ac16748be2674ec14df532a3e48d0c6f215017b537f14ca3feb837dbe86292; observed archive35452245 bytes; executable SHA2560eba26d5f04a3673ee264ca406ef286d5025da098c1a24987a8118c23d69153c

Derive new exact selected-wheel filename/hash locks for the recovered20 qualification pins. Runtime15 pins stay exact. Missing historical wheel archive hashes remain missing; newly acquired hashes are new evidence. Record official resolved URLs, byte lengths/digests, extraction method, actual Python executable/build/compiler/ABI, stdlib root, import origins, dependency payload/metadata membership versus wheel RECORD and absence of external symlinks/editable/shadow paths. Never reuse unsupported historical local313; local312 remains historical only if unavailable. Two profiles are the approved final scope; there is no automatic substitution or downgrade.

Tests: wrong archive hash refuses before extraction; each runtime scan succeeds on actual untouched supported install; deliberate isolated fixture runtime drift/shadow/extra resource/restored-mtime cases refuse under fresh process witnesses. Product has not yet earned final qualification. Preserve an immutable source checkpoint before long acquisition-validation runs.

## 4. Stage B: strict model/codec/resource foundation

### B1. Lexical parser and immutable primitives

Tests: duplicate/unknown/missing fields, all exact types including bool-as-int and malicious equality objects, integer endpoints beyond2**53, overflow tokens, signed zero, empty strings, invalid UTF-8/surrogates, depth32/+1, numeric token32/+1, exact ASCII counts, metadata tagged sentinel collision controls. Frozen constructors must not retain mutable backing. Namespace collisions n_valid/stage/value/key:00 and row/column same-name case.

Implement codec/model primitives and exact Recipe/SourceIdentity/Coordinate constructors only after intended reds. No native/Pint imports to parse a recipe. Canonical byte goldens include LF and every typed key.

### B2. Formula2 and symbolic projections

Tests first: every cap equality/+1; finite multiplication overflow guards; zero-dimension scalar product; R/H/source/weight unions; W formula; all estimate keys; J/P primitives and map/list punctuation; strings with control escapes/non-BMP; schema/result/report/explanation/manifest component bounds; original fixtures pass individual and then combined admission where genuinely projected. Assert no row/coordinate Cartesian forest created by estimator. Plan estimation excludes estimates block from its own recursion.

Before metadata decode prove lexical-prepass primitive counters upper-bound actual safe parser/model allocations on adversarial-small strings/nesting. Verify parent965*N exact equality/domain cutoff and distinct simultaneous decode reservation. No code path can serialize first to decide whether it was allowed.

Exit gate: resource reviewer checks all coefficients/lifetime terms and report/explanation amendments; freeze the reviewed source checkpoint. No numeric-engine validation until supplemental oracle freeze is recorded separately.

## 5. Stage C: source, owner, cache and runtime

### C1. Exact stock layout preflight

Read pinned xarray/pandas/NumPy source read-only and write tests that construct ordinary datasets/IndexVariable/PandasIndex wrappers, inspect exact storage classes/field paths and prove no lazy callback/data realization. Qualify the eleven stock engine/table families and actual safe native size routines on both profiles; inspect pre/post `_cache` state to prove measurement creates/clears nothing. Unknown keys/types/engines/masks refuse. Pin the v6 named additions: BlockValuesRefs list/counter/header/weakref capacity charge without ref() or callbacks; RangeIndex already-present _data owned int64 array; Index already-present _isnan bool/uint8 owner chain. Prove missing entries are not created, source identity/P_input/plan are unchanged, and shallow-copy reference-list/cache growth raises only the measured call-local charge. Reject nonnull weakref callbacks, extra instance fields, populated inherited NamedArray shadow slots and Masked*/extension engines; the exact storage route must preserve indexed Unicode width without public property access. Pin root Dataset._encoding None/exact empty acceptance and nonempty refusal before data reads/no mutation; ordinary direct native files do not inherit this refusal from temporary backend bookkeeping. Bounded profile table is reviewed before production adapter code uses it. Do not broaden into arbitrary reflection if a profile differs.

### C1a. Adopted finite source bridge and lifetime seams (v9)

Implement only the newly reconstructed approved source table/metadata bridge in API-SCHEMAS §17, with no historical recovery claim. First reds pin raw descriptor/frame |O versus selected Umax, proved indexed U<N>, fixed S<N>→U<N>, object sentinels without invented width, same selected labels with distinct raw source identities, and no constructor as source authority.

Pin MetadataValue owned-tag adoption and the two typed child maps: exact types before comparisons, atomic construction/reinitialization refusal, no mutable aliases, no model objects inserted into primitive OwnedMap, one descriptor/tag tree, shallow borrowed Inspection view, exact phase sets and plan Coordinate instance identity without broad backreferences. RangeIndex gets zero retained owner/header and logical8*length with actual scalar/wrapper charges; caches never supply its semantic values.

Metadata tests cover only the finite exact Python/NumPy classes and rank1 bridge: raw owner/view/header precharge, source-cap before conversion, exact np.str_ base methods/optional-storage reserve, no item/dtype/buffer/NumPy str/repr, actual UTF-8 equality/excess/surrogates and preserved NUL. Rank1 numeric/bool/Unicode metadata preserves container type. Wide U4097/U16384 short content and nonempty U0 must not acquire a coordinate-width cap; empty vectors avoid casts, invalid UTF32 fails before construction, and no padded scalar/character-list/vector forest is retained.

Global late-fault tests must prove every owner/raw metadata/codeunit and aggregate tagged bound finishes before any normalized prefix. Pass2 one-scalar checks do not replace this complete-source gate. None/empty slot normalization preserves semantic identity while actual represented capacity determines binding. Dataset cache absent/fresh-empty/overcapacity-empty contributes0/Hsmall/Hlarge in C with no cache mutation or P_input change; unsupported nonempty cache still refuses.

Use the corrected C-R01–C-R06 behaviors as intended reds, with wide/U0 metadata and active-plan preallocation rules superseding earlier narrower drafts. Existing plan Baseline+X+C must reject before poisoned selected-coordinate/array allocation even if a standalone local bound would pass. No-plan compile reserves every preliminary allocation and exposes no plan after later full-baseline rejection. Test route-specific declaration/runtime/admission joint faults, actual supplied B, stale-source versus held-identity codes, exact A binding credit, and original outer A/B/C closure. No universal fault-priority assertion is permitted.

Source control arithmetic and declared3Q/2A slots are necessary design bounds, not actual lifetime qualification. Implementations must show one current scan/owner tuple, one owned tagged tree, real helper/iterator/exception release, no recursive guard or fourth handle, and source cursor release before B2.

### C2. Source phase and retained ownership

Intended reds: legal descriptor/prepared/materialized/scalar phases; exact-set supersets/partials; changed-selection descriptor reuse; held identity mismatch before phase; invalid phase before data/hash; prepared accepted paths freshly recheck source; plan arrays empty and Coordinate instance sharing/weakrefs; actual supplied B materialized, not hidden A.

Owner regressions: immediate C, legal singleton zero/negative stride, readonly, terminal C/F/bytes; one-cell view into8 MiB array/bytes owner charged entirely; two variables same owner conservatively doubled; memmap/mmap/subclass/unsupported exporter before reads; object-coordinate owned/type/full-label charge including unselected labels; chain32/depth33/cycle via clearly labeled metadata seam only. Substantial-owner incremental metadata regression before encoding/hash reproduces source_bytes_limit priority. No unsafe pointer construction.

Under the adopted v11 native whole-route/control-overlap contract, the early implementation gate is a genuine small native file inspect → prepare → compile → materialize → reconstructed-model round-trip with exactly one worker per public invocation, proven parent frame/copy release and all returned bytes/coordinates equal. Corrupt submitted input after parent digest capture and alter a returned plan/context to prove expected hashes/witnesses bind actual inputs and caller models.

Native tests: first pin v8 raw declaration gates in both attrs/encoding: packing/_Unsigned presence, only scalar NaN missing declarations on float storage, all finite/inf/null/string/vector cases, conflicts, role/reason/code order, malformed metadata precedence, unselected status and no source mutation. Verify native raw housekeeping is not synthesized into a semantic declaration, no CF conversion occurs, and known scalar/container types are preserved. Allowed NaN declarations never waive actual weight/coordinate validity. Reproject all status-bearing descriptor/API forms with the seven-reason coordinate and five-reason data/weight bounds before implementation. Then memory/native scalar/auxiliary/multidimensional coordinate refusals before payload access; unchanged source bytes/metadata; exact root/variable `coordinates` declaration tokenization/name/duplicate/missing-reference cases; undeclared scalar/multidimensional/bounds data remain admitted; tab-delimited reference-time units reach unsupported_coordinate_encoding. Then bounded root-only file, selected/nonselected coords, fixed/variable strings, raw bytes before UTF-8 decode, all selected reduced coordinate failures, exact CF regex declarations and inspectable unselected status, no coordinate Dataset.__getitem__ during native inspection, protected ordinary source path and symlink/hardlink/overlap refusals. Public file routes invoke one supervisor for every native call.

### C3. Call-local admission

Tests A/A, A/B and A/B/C Dataset slots with equal semantic content/distinct ownership; anchor P_input credit once only after exact full fresh resource_binding equality. Pin unchanged-anchor success, owner growth and shrinkage, non-cache container-capacity changes, and redistribution among recorded owner charges with unchanged aggregate total; mismatch gives source_resource_binding_mismatch and fixed replan guidance before credit/downstream allocation. Keep source_bytes_limit/unsupported-layout precedence and prove that same-footprint unused-A content is not semantically hashed while ordinary named cache growth changes C_cache only; result backing never dropped; result without plan refuses; unknown cache state; native-table/body/bucket/mask charging; cache growth before next operation; identity/P_input/plan/result unchanged by a normal4096-entry lookup. Cache measurements never materialize/clear lookup or call user hooks. Tests unused A same-footprint mutation is not mistaken for proof until A is consumed; actual B changes fail source replay. Equality/+1 total512 MiB and beyond bounded cache domain retain truthful diagnostics.

### C4. Runtime integration

Reuse exact runtime.py only after interface review of model helper contracts, scanner boundedness, import assumptions and exception mapping. Test all nine runtime refusal codes, process-witness latch including actual scanner failure, wrong caller expectation no latch, restored mtime, resource membership, stdlib/package exclusions, six.moves/typing exact exceptions, mapped-core duplicate/alias rules, streaming metadata headers, hardlink occurrences and no private paths. Source/plan runtime checks occur before Pint and final success under supervision.

The v11 native foundation and corrected complete caller/control design are adopted. Their equations and exact protocol now govern implementation; source-only control evidence still cannot establish real native/decoder behavior. Preserve intended reds and independently review actual process/native/lifetime code before claiming any route qualified.

Exit gate: independent source/admission/runtime review of frozen code and real bounded memory/file journeys on both profiles; no historical242/270/etc counts appear as current results. Checkpoint before lengthy profile runs.

## 6. Stage D: planning, units and computation

### D1. Compiler and binding

Tests zero-to-two stages, weighted-first, explicit broadcast, no row-dim reduction, complete dimensional union including weights/reduced axes, names collision, source exact unit assertion, typed plan grain ordering, persisted plan resource-binding mismatch versus execute(plan_A,B) extra-source charge. Canonical plans identical across legal phases on same anchor; equivalent B can't silently alter saved footprint. Parser/runtime/source error priority tests precede expensive work. Pin all six v5 specific original refusal boundaries and joint faults: missing stage missing policy versus generic malformed fields; later weighted stage before weighted-only requirements; residual dimensions before well-formed broadcast mismatch; row duplicate versus reduced-axis duplicate; null missing unit assertion versus nonnull mismatch. Original R01–R14 compare exact frozen codes unchanged.

### D2. Units and reducer

Review exact recovered units.py with new foundational seams. Run recovered unit tests then fresh cases for identity unknown units, positive affine composition, incompatible/nonlinear/offset compound units, stock graph closure/order/caps, null retained label, percent normalization and exact weight assertions. Stage reduction scratch/lifetime follows W; do not promote earlier recovered reduce.py as final.

The NEW v10 stock-unit interface is independently reviewed design, not production qualification. Implement it test-first with a separately sealed source/review gate. Cover:

- Every unchanged original/supplemental unit label and the prose-only original R07 not_a_known_unit/R08 kg controls; preserve R09 missing_unit_assertion and R13 source_unit_mismatch without fixture edits or expectation translation
- Poison evaluation while constructing/validating stock token/tree structures; refuse arithmetic-expression powers before evaluation. Qualify ordinary aliases, multiplication/implicit multiplication/division/grouping, literal 1, finite signed fractional powers and pinned caret/superscript spellings. Check raw 512-byte, transformed 16×/8192-byte, meaningful-token 128, numeric-token 32-byte/domain, parenthesis-depth 32, node 255 and tree-depth 32 boundaries and just-over cases with benign inputs; no hostile huge-power evaluation
- Exact original-text normalization/parse schedule and audited plain tokenizer; count/charge two terminators, current token, in-flight preprocessing/tokenizer buffers, actual headers, builder frames and all scratch within 512 KiB of the existing runtime allowance. Prove guard frame release before stock work
- Canceled unknown/logarithmic/offset leaves and aliases; offset neutral factors, quotient/cancellation and nested powers; only the single-name/single-literal-power-equal-to-1 shape qualifies. Test pre-cancellation aggregate 128 distinct canonical definitions/512 terms and just-over cases across source plus target, counting aliases/repeated raw roots; one transient closure at a time and final reachable-only graph
- One nonblocking owner-thread context; overlap/reentry/reuse/inactive/wrong-thread refusal and 64/65 attempts including failed and weight attempts. Permit unrelated memory-route threads. Inject initialization/partial-entry/BaseException/exit/restoration failures; one construction attempt and poisoned-state refusals; exact baseline map-list/map/cache identities and contents restored, operation weakrefs released, no caller GC/settings/cache changes
- Retain public Refusal and traceback frames with GC disabled after malformed parse, unknown unit, graph rejection, cross-check failure and exceptional exit. Prove the private dependency helper returned before fresh public Refusal; no private registry/cache/Unit/Quantity/parser frame retention, recursive error-chain walk or raw dependency diagnostic leak
- Atomic UnitOperation model initialization/reinitialization and exact owned primitive graph invariants; fresh seven-field stock comparison at runtime/source/compiler boundaries remains separate. NormalizedWeights requires the qualified ArrayBuffer/operation and the existing released-mask/cast/immutable-byte schedule, never a bare ndarray source shortcut

After sealing the implementation, independently review all stock-helper changes and run the full available suite plus focused grammar/resource/equal-plus-one/context/thread/failure/lifetime tests on both public profiles. Interface probe counts and historical passes do not qualify production or complete caller/runtime memory. No pending native/API overlap amendment is adopted by this unit gate.

Test direct int64/uint64 values/keys, float32 direct, conversion once including no-stage nonidentity, NaN missing/inf refusal, zero-weight finite count, weight validity even on missing data, named broadcast alignment, skip/propagate/min_count reason order, failed intermediates, all-null rows, overflow products/sums/division and support/final linkage. Legal independently rounded sums are structural model admission, not imposed accumulation order. Coherent forged result/adjacent stage cases must survive local constructor where appropriate and fail later replay.

After independent supplemental freeze, run original scalar Fraction oracle and exact competent xarray/Pint/pandas baseline without importing candidate computation into either. Compare numeric abs/rel1e−12, exact keys/counts/reasons/units; separately compare same-engine exact canonical bytes. Metamorphic coordinates/permutation/unit/sensible scaling invariants retain explicitly defined limitations. Stage output/native source/runtime gates require focused/full green and independent numeric/lifetime review.

## 7. Stage E: files, bundle, report and commit

### E1. Streaming format

First freeze exact report-v2 static template golden within32768 literal budget. Product template/CSS/literals remain in runtime-bound .py modules; the golden HTML is a test artifact, never a runtime-unbound output source. Test all seven root files/stage pairs, collision-free positional headers, typed CSV null/empty/quoted Unicode/int64/uint64, exact schemas, canonical LF JSON, manifest no self-cycle, per-component/aggregate counters. Strings ` `, leading/trailing/multiple spaces, tabs/newlines where labels permit, `<>&\"`, non-BMP characters and exact coordinate dtype widths exercise report ASCII scalar display/text-node escaping/12-byte fragment bound and222-byte notice. Data/CSV remain unchanged. Full totals/reasons are checked against all rows/support, not just previews.

### E2. Independent verification layers and liveness

Intended corruption cases: unknown/duplicate JSON, extra/missing path, changed hash/typed CSV, schema dtype/key coercion, plausible coherent result tamper, locally coherent impossible adjacent-stage lineage, wrong source/runtime binding, altered report. Assert each check's completed/unattempted status and unchanged runtime-specific findings. Writer refuses coherent forge before install. Weakref/frame probes prove parsed/validated helper forests released before replay, no fourth result forest and outer Dataset closure retained. Streaming instrumentation rejects whole-result to_dict/freeze/thaw/DataFrame/all-chunks paths in writer.

### E3. Real Linux transaction/supervision

Use actual anchored renameat2 RENAME_NOREPLACE under qualified filesystem; unsupported/no-op shim must fail closed. Test output race/no overwrite, inherited stdout/stderr hardlink/source/bundle aliases, symlink parent/entry substitution, original witness held before read and never refreshed, stage cleanup only same owned inode, acquired FD setup/fstat failure closes/removes safely. Final worker full replay/runtime/source scan → exit/reap → parent anchored bounded receipt/manifest checks → final source stat → actual rename order is observed.

Real SIGINT/SIGTERM before the final checkpoint, during bounded commit/state capture, around ContextVar retirement and at each prior-handler restoration must preserve observed truth. Test actual main-Python-thread/no-other-Python-thread/default-SIGCHLD/exclusive-wait preconditions; do not add an all-OS-thread gate. Restore qualified touched sigaction/Python handler/mask/stream state and test previous-policy exceptions after per-signal handoff without relabeling them controlled cancellation. No reused token or installed-output cleanup. Partial stdout after commit remains committed; delayed native-helper callbacks/caller policy may prevent delivery. Preserve residual final-stat/check-to-return races and SIGKILL/power-loss limits.

V11 implementation tests must cover the following reviewed finite closures before the exit gate:

- Exact original parent-root/trusted worker-child identity through creation, seal and first post-reap opens; 135 files+support=136 witnesses and +1 refusal; no refreshed authority, support substitution at every phase, killed-before-seal empty/proven/unproven residue branches; only the validated 54-byte generated basename and exact 163-byte local hint, preserving primary finding/receipt
- Real plan-file and bundle-directory renameat2 no-replace, unsupported/no-op primitive refusal, same-parent anchors, acquired-FD/fstat/setup failures, safe source-reference sharing/finalization, retire-before-close, actual stage/manifest/receipt order and no postcommit destination removal
- Fresh exec and exact inherited FD set above 2; launch-only Popen transfer/destructor retirement, traps on every forbidden lifecycle convenience method, real successful/nonzero status, ECHILD→LOST with unchanged classification and no reaped token or later kill, timeout after result-0 probe, exit-before-kill, returned-object transfer failure and the explicitly limited unadopted-constructor outcome on both profiles
- Main-thread/background-Python-thread/nondefault SIGCHLD/external-reaper refusal; qualify actual idle native-helper observation where available without treating Python Thread simulation as evidence; native access requires active private worker context and nested helpers launch no second worker
- CLI plan/build completion requires PreparedReceipt+StageWitness, payload=null and the required empty private ordinary payload FD; wrong nonnull payload/nonempty FD refuses. api_write_bundle preserves its framed PreparedReceipt return; only actual parent rename creates a public committed receipt
- First api_inspect requires source=null and original parent FD/entry/stat authority. Trap parent initial content hashing in API and relevant CLI routes, retain the first supervised worker source hash, and mutate before final worker hashing to reject a self-comparison shortcut. Later established SourceIdentity is also checked; parent final source gate is stat only, and recipe/plan/result/key independent parent digests remain unchanged
- Full touched INT/TERM action flags/mask/restorer and Python-handler restoration, unknown getsignal(None) before mutation, observed entry/precheckpoint/postcheckpoint/cleanup/handoff cancellations, retained readonly Refusal envelope coherence, semantic api_verify reports versus transport exceptions; no process-wide signal-drain claim
- Capture both stdout/stderr origins before unrelated opens; deliberately closed fd1/fd2 reused by files remain unavailable, shared-description flags captured before either mutation, nontruncating alias protection, real short/EINTR/EAGAIN/backpressure and tiny-error deadline, no diagnostic fallback
- Shared strict lexer/primitive decoder preserves all B1 regressions, including escaped-string P_scan≤P_model+4N and equality/+1; exact Inspection/result P and key guard precede allocation; no second parser, public permit, fabricated baseline, sender-counter authority or fourth result forest
- Combined caller+W_parent+965*N and non-result wire guards, actual response→manifest→scientific frame release including tracebacks/generators, 12664 scanner bytes within control, 40200/57923 distinct fixed pools, exact-preallocated buffer headers and at most four retired-before-next-variable readonly views
- Exact nine original+normalized path mapping in NATIVE-LIFECYCLE: three source references, active lease, four inputs and destination-or-workspace-parent; only workspace/stage roots, output co-location under destination parent and non-output qualified fixed `/tmp`. Test 4095/+1 raw/join/normalized UTF-8, 64 KiB/+1 PosixPath and pre-copy argv state with list capacity/huge discarded prefixes/caches; bounded one-component normalization and full target-to-parent construction retirement, no retained ancestor vector/second path representation/caller cache mutation
- Prepare/compile caller Recipe remains additive and future worker estimates grant no capacity. Saved plans padded to the unchanged 16 MiB raw cap retain L, full D+R until actual helper return, then P_saved+R outside later maxima; fresh canonical total+L+P_saved+R equality/+1. CallAdmission still diagnoses only its own declared inputs
- api_verify original anchored plan-only strict bootstrap: identity-before-phase for descriptor/prepared/materialized exact sets, R+2*79640 charge, real prelaunch forest release, exactly one worker on legal input, parent native/manifest/result/Pint traps, original plan replacement before launch/worker read/return including coherent plan+manifest change, mismatched verified plan_sha256 rejection and no null-digest equality pass
- Fixed verification metadata 7345/+1 and zero raw trailer, semantic report/check/finding preservation, complete worker source/runtime/replay gates, memory LogicalOnlyBudget parity with no native clock/RSS/reap claim, and Deadline-only native dispatch

These are mandatory intended-red/green, exact-source review and liveness gates, not performed implementation evidence. The approved resource arithmetic and benign ABI/header observations do not qualify actual native files, RSS/time, maximum capacity or final distribution cells.

### E3a. Accepted constructor/topology/state closures: all execution pending

NATIVE-LIFECYCLE supplies the accepted NEW named159-of160 allocation target, generated-owner topology, conditional integrity premises and finite failed-start outcome matrix. It is not a recovered historical schedule or native implementation pass. All live-worker, native-adapter, stage/seal and final-commit tests below are pending. No custom launcher, audit bypass, exhaustive CPython allocator proof or expanded runtime/locale profile belongs to this gate.

Before the affected implementation is used, qualify exact root/input headers and backing against23544≤50960 and15552≤29760 with no reused surplus; borrowed descriptions and target-to-parent path-scratch overlap; read-write-to-read-only reopen/replacement with immediate registration/original-identity checks; 28 persistent, eight protocol and four transient FD cells plus six stock descriptor lifetimes. Observe iterator-owned FDs, sequential membership→digest helper retirement, root/child lifetimes and original parent identities. Neither generated scalar constructors nor a descriptor number grant authority.

Map concrete lifecycle/ABI/observation/stream/retirement records, stock wrapper18 and constructor-helper24 to the named pool. Observe helper/traceback/context/cause release, actual S0/S1 buffer retirement before the73477-byte constructor payload, retained18628-byte argv through REAPED/LOST, and sequential completion→manifest→scientific parsing. Qualify the bounded supported stock `_cleanup()`/`_active`/callback and libc/locale behavior inside existing reservations; unresolved fit refuses. Keep31 estimate keys, all coefficients/caps/wire fields, W_parent, CONTROL and worker-ledger accounting unchanged.

The seven ordinary qualification cases are:

| Case | Required observation; pending on both pinned profiles |
|---|---|
| Absent interpreter path and owned ordinary nonexecutable interpreter candidate | Sanitized constructor error, no invented launch/reap/success, unchanged source/output and retired parent resources |
| Controlled ordinary error-pipe read error after actual child creation | Termination unconfirmed, no inferred/adopted handle, commit unreachable, stage/workspace retained; fixture tears down only its own exact child |
| Returned wrapper with failure before/during adoption | Finally repeats idempotent adoption, exactly one owner, exact-PID wait/signaling and no later signal after REAPED/LOST |
| Residual worker completes temporary output after constructor failure | Final output absent/unchanged, later completion cannot revive invocation, residue remains conservative |
| Earlier finding and temporal INT/TERM cases | Earlier finding means Popen is never called; pending prelaunch cancellation means no launch; failed-start latch observation selects130/143 or failed/3; late latch is retained without replacing selected first outcome |
| Existing final file/directory and independent source/output hardlink aliases | No replacement or mutation; original alias-boundary refusals remain in force |
| Normal successful launch/terminal reap and normal worker exit failure | Authoritative adopted wait/validation/commit route only when premises hold; unchanged source/input bytes |

Use benign owned fixtures, preserve before/after source/output witnesses and bytes, and keep fixture-only exact child identity outside product outcome authority. The error-pipe injection is test-only at the fixed supported stock boundary; if that boundary changes, stop and adapt the frozen test design before execution. No arbitrary PID probing or foreign-child waits/signals.

Test preflight supervision_unavailable/refused/2 separately from attempted unadopted supervision_unavailable/failed/3, without reclassifying LOST. Pin fresh-outcome/no-earlier-finding launch entry, one failed-start latch-selection observation, both cancellation exits and later-latch retention, readonly exception/envelope coherence, all four72/87/236/251-byte messages, unchanged163-byte stage hint and validated54-byte basename, five-check progress, LF and≤521-byte ErrorEnvelope, safe/unsafe stream behavior and unchanged fallback. Preserve adopted-worker, prior-policy handoff and postcommit cancellation/receipt tests separately.

The conditional final-output claim requires its own integration evidence: originally anchored read-only sources/inputs, qualified inherited read-only native adapter, worker writes only declared temporary roles, parent-only installer, adopted exact-PID terminal reap followed by bounded completion/seals/receipt/source-input rechecks/final checkpoint and real no-replace rename. Unadopted failure closes only registered parent FDs and leaves all possibly worker-accessible entries. No residual-worker exit/cleanup or pre-adoption60s/1GiB guarantee may be asserted from these tests.

Exit gate: independent bundle/OS review on exact freeze, receipt/witness/frame evidence and real end-to-end file journey. Add parity tests between file-backed and pure materialized-memory bundle content, all refusal/corruption/overwrite/cancellation controls on each route, and explicit assertions that the memory route makes no worker/reap/RSS/wall claim. No UI/browser claim from static HTML checks alone.

## 8. Stage F: explanation

Tests first against recovered v1 known defects: exact primitive types before equality; raw/direct integer nonnull; source/key/support stored Unicode width; otherwise-valid over-width query returns row_key_not_found; shown policy-derived reasons/implicit weight counts/sums; shown final record/value linkage. No constructor second reducer. Explain replay rejects coherent forged result.

Test exact dict/limit1..1000, query type without int↔float coercion, stored signed zero, linear lookup with untouched caches, raw/converted/source physical indices/labels, actual raw/normalized weights/exclusions, direct/scalar/broadcast/two-stage paths, complete offsets/selectors for omitted source/predecessors, O(rank) odometer. Mandatory skeleton refusal, limit omissions, first global byte overflow then no later display, correct omission counts and exact bytes at equality/+1. Private byte counters included in P; no full Unicode/to_dict/freeze/thaw/chunks list. At most32 walker frames, one current record/token scratch and pointer-copy finalization.

Weakrefs/references and allocation probes prove replay/helper/iterator release before second materialization, caller+new selection maximum and immutable returned model with no source/result/plan handles. Full suite and independent trace/resource review. Capture static report pixels with MuPDF only if useful, label them static; obtain real browser QA only through an actually working authorized browser.

## 9. Stage G: CLI and final distribution matrix

### G1. Exact grammar and shared supervisor

Test both console and python -m forms; every forbidden syntax, unknown/repeated/abbreviation/= option, stdin/inline/default limit, N formatting, --help static route, cheap grammar before worker. One absolute deadline starts in main before grammar; fake-clock/labeled seams plus real time/backpressure tests cover setup, native/runtime scans, worker/reap, frame/manifest validation, stdout/stderr and cleanup. No per-phase resets. No nested workers. CLI parent only streams payload; Python API model-return reconstruction uses framed bounded primitive/raw path without native parser/pickle, charged before allocation.

Inherited-stream alias tests use already-open nontruncating FDs; explicitly document that shell redirection may truncate a source before cli.main and cannot be undone by later checks. Test real pipe/socket short/EINTR/EAGAIN, unread pipe timeout, shared open-description flags captured before either change, restoration, unsafe output suppression and no fallback. Whole worker errors4096/+1 including receipt; parent965*N precharge for every control/error/manifest decode and parse-frame release before manifest reread; safe fallback retains code/checks/committed receipt. Observed committed status must survive postcommit diagnostics failure/cancellation.

### G2. Packaging and eight fresh cells

Freeze final source archive/manifest only after all reviews. Build source distribution and wheel with pinned tools, without dependency/interpreter vendoring. Inspect filenames/member safety/license/readme/test data inclusion; require clean reproducible source inputs and pristine import origins. Each of the two reacquired public profiles has four cells:

1. source checkout from exact final frozen source
2. wheel installed into fresh environment, launched outside source checkout
3. installed sdist via real build/install flow into fresh environment, launched outside checkout
4. pristine extracted sdist, build/test from extraction with intended import origin verified

For every cell record interpreter/dependency/product/runtime hashes and actual module origins. Run complete current suite, original frozen artifact/hash+oracle/baseline gates, newly frozen supplemental gates, refusal/corruption/metamorphic suite, real README CLI/report/explain/verify flow, and practical admitted resource journeys. A source-path import in an installed cell invalidates that cell. Build artifact existence alone is not installed behavior evidence. Same-engine replay bundles stay inside their exact binding; cross-cell/profile different-binding refusal is expected and tested.

The dense non-scalar fully reduced unweighted float64 family at64 MiB is already analytically refused by the606419042-byte logical lower bound in RESOURCES; treat64 MiB as a rejection ceiling and qualify smaller practical cases without changing coefficients/caps. Do not turn an indeterminate lower-bound check into an admission claim.

Measure honest benign practical maxima constrained by all caps: large source-owner/small selection, widest selected union that passes complete envelope, many-row/many-support admitted workloads, long-label/report/trace bytes, runtime/import/registry memory, cold/warm scans where available, caller+worker liveness and backpressure. Report actual sizes/work/conditional admission/refusal, not an unsupported simultaneous cap claim. Full-scan source/manifests must remain unchanged before/after each final cell.

### G3. Final review and publication boundary

Independent final reviewer receives exact freeze, all raw receipts, qualification matrix and remaining gaps. All material blockers fixed/retested; no historical count used as substitute. Public report states passed/failed/not-run per cell, numerical tolerance versus exact replay, native trust/race limits, browser QA status, public acquisition hashes and new-version compatibility boundary. Publication is a separate authorized release step; maintain the immutable source checkpoint and do not include dependency/interpreter bytes.

Stopping condition: approved exact frozen implementation plus all eight fresh required cells and real user-flow/resource evidence, or a specific unresolved required authorization/environment/profile/design blocker. A running test/qualification operation remains active work until its terminal result is collected; do not stop at an intermediate green subset.


## Eager-memory installation clarification

For the implemented eager-memory transaction, a cooperative cancellation observed before the final checkpoint prevents rename. A later observation may accompany installed output. Atomic no-replace installation does not imply Python-bytecode-atomic receipt capture or delivery against arbitrary asynchronous caller exceptions or forced termination. Preserve caller signal policy. For a catchable caller interruption after an installation attempt, the interruption is re-raised as the same exception object with its existing notes and exception-chain details while original-inode reconciliation is attempted. Earlier source or replay validation may shorten traceback and chaining details to release temporary state; it preserves the exception object and notes, but does not promise cause/context preservation. Reconciliation remains best effort under repeated interruption. Cleanup never removes the requested destination. See MEMORY-COMMIT-INTERRUPTION.md. Supervised file-native launch/handler promises remain separately gated.
