# Native lifecycle, generated owners and startup limits

Status: accepted NEW design amendment and written closures, 2026-10-07. This document is normative with CONTRACT, API-SCHEMAS and RESOURCES. It replaces the stronger stock-constructor cleanup assumption, names the existing two-root/path roles and introduces a named allocation target inside the unchanged160×512-byte parent state pool. It does not qualify an implementation. Physical representations, actual lifetimes, all seven live-worker cases, native access, signals, stage/seal/commit and whole-route/distribution tests remain pending.

All public models, seven ErrorEnvelope fields, wire schemas,31 estimate keys, P/J coefficients, existing byte/field caps and worker/caller resource terms stay unchanged. This is a bounded trusted-stock-runtime design, not a custom launcher, malicious-worker sandbox, exhaustive CPython allocation proof, audit bypass or expanded interpreter/locale profile. Earlier finding, LOST, adopted-worker and postcommit policies remain governed by their existing clauses except for the precise failed-start extension below.

## 1. Unadopted stock-constructor failure

### 1.1 Ownership and reachable outcomes

Enter stock Popen only from a fresh uncommitted outcome with no established finding, after the ordinary prelaunch cancellation/deadline checkpoint. An earlier finding prevents Popen; observed pending cancellation uses the existing no-launch130/143 route. Neither may report an invented worker. During the supported closed constructor call no other product semantic work runs; only the first observed INT/TERM latch may asynchronously change product outcome state.

Stock Popen performs its ordinary constructor setup and exec-failure cleanup. It does not guarantee synchronous termination for every post-creation exception before it returns a reliably adoptable wrapper/PID. For example, an error-pipe read can fail after child creation; native PID-to-integer conversion can fail before the wrapper stores a PID. An exception traceback/text, copied FD number, guessed PID, destructor or stock `_active` observation is not product ownership/reap evidence.

If construction raises without a returned, reliably adopted wrapper/PID, this invocation permanently loses all successful completion, verification-success, reconstruction and commit paths. It has no successful-launch/reaped evidence. Partial or later completion/payload bytes cannot revive it. Never infer or signal an unowned numeric PID, call waitpid(-1), recover unknown children through stock `_active`, or retry launch automatically in the same invocation. Stock `_cleanup()` scope must still be qualified before launch is enabled; waiting for unrelated children is not authorized by this design.

After that failure, make one managed observation of the first INT/TERM latch before selecting the first outcome. Observed2/15 selects interrupted/cancelled/130 or143; otherwise select supervision_unavailable/failed/3. This observation is the selection boundary, not an atomic OS signal-arrival boundary. Later cleanup findings do not replace that first finding/code/status/exit. A first late INT/TERM remains recorded through cleanup but cannot replace an already selected startup failure. Further signals preserve the first2/15. Previous-policy exceptions or forced death may prevent return/delivery under existing restoration/handoff rules.

Preflight unavailable supervision stays supervision_unavailable/refused/2. Attempted unadopted stock-constructor failure is the contextual supervision_unavailable/failed/3 extension required by RESOURCES §11. The readonly operation exception must expose this exact code/status/exit; Refusal-family ancestry cannot choose the exit implicitly. Existing LOST and other supervision branches are not reclassified. Any returned-wrapper failure belongs to the existing preallocated owner/idempotent adoption/finally/exact-PID wait route, never this unadopted table.

| Condition | Launch and selected public outcome | Diagnostic |
|---|---|---|
| Finding established before constructor entry | No launch; preserve earlier code/message/checks/exit | Existing finding; no claim that a worker may have been created |
| Pending INT/TERM observed by prelaunch checkpoint | No launch; existing interrupted130/143 | Existing cancellation diagnostic |
| Constructor raises; no latch at failed-start selection | No adoption/reap/success/commit; supervision_unavailable/failed/3 | A, with H when applicable |
| Constructor raises; first latch2 observed at selection | No adoption/reap/success/commit; interrupted/cancelled/130 | B, with H when applicable |
| Constructor raises; first latch15 observed at selection | No adoption/reap/success/commit; interrupted/cancelled/143 | B, with H when applicable |
| First INT/TERM observed after startup failure was selected | Preserve startup finding; retain latch through cleanup | A remains |
| Additional signal after selected interrupted outcome | Preserve first2/15 and130/143 | B remains |
| Unsafe stderr, exhausted output deadline, serialization failure or prior-policy/forced-death interruption | Suppress/fail delivery under existing rules; no fallback destination | No delivery guarantee or fabricated success |

### 1.2 Four finite message forms

A is the fixed72-byte ASCII literal:

    Native worker startup failed; worker termination could not be confirmed.

B is the fixed87-byte ASCII literal:

    Operation interrupted during worker startup; worker termination could not be confirmed.

H is the unchanged163-byte local-stage hint using the validated operation-generated54-byte basename:

    Operation did not complete; an unverified temporary stage may remain: {generated_basename} (in the requested destination parent).

The basename is exactly `.replicatetable-stage-` plus32 lowercase hexadecimal digits, never worker/exception/user text. The only failed-start forms are A, B, A+one ASCII space+H, or B+one ASCII space+H: lengths72,87,236,251. If an unverified stage from this invocation remains and the safe complete message can be sent, include H. H may be absent when no stage hint applies or safe diagnostics cannot be delivered. Workspace-only residue uses A/B with no additional local-path hint. No arbitrary concatenation, raw exception text, truncation, alternate basename or user/source/absolute-path interpolation is admitted.

Every reachable failed-start envelope has committed=false and receipt=null, with the existing five-check map and actual observed progress. That map's maximum canonical JSON length is146: key lengths50+key quotes10+colons5+five quoted13-byte values75+commas4+braces2. Seven envelope keys total46 bytes; their quotes/colons/commas/braces add29, for outer structural cost75. Values cost at most version1+quoted status11+quoted code25+quoted message253+checks146+false5+null4=445. Including LF, the componentwise bound is75+445+1=521 bytes. It conservatively combines maxima even if not simultaneously reachable; all message characters, including the generated hexadecimal basename, require no JSON escaping.

Thus message≤251≤512 and whole envelope≤521≤4096. The unchanged generic fallback literal and rules remain in force, but valid failed-start size alone cannot invoke fallback or hide termination uncertainty. Schema/emitter tests must still establish all four forms, progress combinations, exact LF, prefix/basename validation, both cancellation exits and safe/unsafe stream behavior before CLI use.

### 1.3 Cleanup and operational limits

Retire independently registered parent FD cells before closing them. This closes only parent ownership; inherited worker FDs may remain open and worker work may continue. Stock constructor descriptors remain stock cleanup's responsibility. Never close numbers copied from private constructor state or `_devnull`.

When worker access may remain, leave its temporary workspace/stage entries. Do not traverse/unlink children or attempt root removal while a residual worker may use them. The generated-stage hint preserves the selected primary outcome and makes no cleanup guarantee. Temporary contents can change after return; a caller may have to inspect/remove residue after independently establishing quiescence. There is no eventual automatic cleanup/destructor guarantee.

Sample only the successfully adopted worker PID. Worker-side deadline/CPU guards help only after initialization; they do not establish preinitialization cleanup, residual-worker lifetime or pre-adoption RSS enforcement. There is no promise that an unadopted worker exits by60 seconds or remains below1 GiB. Startup/kernel blockage can overshoot the original deadline; cleanup starts no new deadline. Adopted operations retain their same absolute deadline, sampled RSS, exact-PID terminal reap and ordered validation rules, including required reap after an expired deadline. No hard allocator/process-tree containment is claimed.

## 2. Generated roots, paths and descriptor authority

### 2.1 Exactly two persistent root roles

NATIVE-FILESYSTEM-PROFILE narrows initial temporary/output parents to the experimental exact-kernel tmpfs profile with successful anchored filesystem/type and per-directory lookup-feature observations. Overlay and unqualified profiles refuse; a type label or finite name sample is insufficient. Original parent identity checks remain independent, and compatibility is rechecked before actual creation and final installation. Neither generated stage nor output workspace basename may equal the requested final leaf; refuse before returning the prepared root and before mkdir, with no retry or extra retained path. The shared native binding and fixed ctypes types initialize before operation; operation buffers/addresses/scalars remain in their existing explicit lanes.

The two roots are workspace root and stage root, each with at most its own directory FD and one immediate-parent FD. Stage's parent FD is also destination-parent anchor for eventual no-replace installation; no third destination-directory owner exists. Before stage creation its record may contain the acquired parent FD with an unacquired root FD. That is acquisition state, not evidence that a stage exists.

Exactly nine full original/normalized path allowances remain: three source references, one active lease, four input roles, one destination-or-workspace-parent role. On output routes the ninth normalized description is the absolute destination parent; original output argument and destination_name retain their separate charges. Retire full normalized target construction before persistent parent-text retention; the construction overlap must fit existing path scratch. Never retain a second full target/parent string, ancestor vector or additional generated-object full path.

Create output workspace and stage under that same qualified destination parent. Workspace owns a duplicate parent FD and independently charged original parent identity. Only stage/destination retains the ninth description; workspace has no second persistent path reference/text. Its anchored basename/held FD/identity helper may temporarily borrow that description for a full rewalk, then release its frame before reuse.

Non-output operations have no stage or destination owner. Use fixed Linux `/tmp`, qualified through the same anchored no-follow ordinary-directory route. Its original literal and sole normalized description use the otherwise unused ninth allowance. Workspace owns its parent and root FD. No TMPDIR, extra caller path or retained cwd FD; unavailable/unqualified `/tmp` refuses under existing path/IO rules.

Workspace basename is `.replicatetable-work-` plus32 lowercase hexadecimal digits,53 ASCII bytes. Stage basename is `.replicatetable-stage-` plus32 such digits,54 bytes. Both are generated by the operation and fit the existing≤54 allowance; only the stage basename may enter the residue diagnostic. Generated objects need anchored-name records, not additional path-backed file/directory owners.

### 2.2 Persistent owner/descriptor map

| Role | Maximum persistent cells | Access and authority | Retirement |
|---|---:|---|---|
| Three source references | 6: source+immediate-parent FD each | Read-only source; original FD/entry witnesses and parent identity; original argument/description | Last sharing model releases reference |
| Active source lease | 2 owned duplicates | Established original authority independently charged; no backend/model clone | After final required original-source rechecks |
| Four input roles | 8: input+immediate-parent FD each | External ordinary files read-only with original FD/entry/digest. Bundle uses one otherwise unused role. Generated serialization uses basename, created identity, sealed witnesses and read-only worker access | Final required input validation/recheck and worker use complete |
| Four workspace files | 8: file+duplicate workspace-root FD each | `request.json`, `completion.json`, `control.json`, `payload.bin`, all≤32. Original creation identity observed before writes; request/control sealed read-only; completion/payload temporary worker outputs | Exact worker terminal outcome and final use; on unadopted failure close parent FDs and leave worker-accessible entries |
| Workspace root | 2: root+parent FD | Generated53-byte basename, original root creation and parent identity, final full witness after intended membership writes | Children retire and conservative cleanup is justified |
| Stage root | 2: root+destination-parent FD | Generated54-byte basename, original root creation and parent identity, worker stable seal matching original root | Validation, no-replace commit/immediate receipt and permitted cleanup; never remove installed output |
| **Total** | **28** | Eight path-based source/lease/input pairs, two generated roots and four generated workspace-file pairs; not14 full path-backed owners | |

Saved-plan bootstrap's current plan child uses an available input role, not a fifth role. Its parsed objects retain the separate R+2*Smax reservation and retire before launch. Source/lease aliases receive no accounting credit. A new owner role beyond this table requires design review before acquisition.

For generated serialized input, retire the parent write FD before exposing the stable read-only role. Acquire/register a replacement read-only FD immediately and match original creation identity plus stable sealed entry/FD witness; reopening never refreshes expectations. The transition's extra FD uses one of the four transient cells. Duplicating a read-write descriptor cannot downgrade access. Sealed request/control have the same actual read-only obligation.

Workspace children compare their held parent FDs against the retained workspace original creation identity. No new persistent per-child parent witness copy is hidden. Each file's created_identity/witness covers its original inode and stable phase witness. Retain the root record until children finish. Both roots have explicit parent_identity; parent directory revalidation compares identity only, never refreshed size/mtime after controlled creation. Root creation identities, stable seals and transition witnesses remain distinct. Scalar constructors, bare FD numbers and caller-supplied identities never prove acquisition.

At most eight owned protocol duplicates above fd2 map to input, payload, control, at most three operation-required optional roles, and request/completion bootstrap. Integer tuples are not additional descriptors or closing authority. No root/file parent FD passes to the worker. Required stage FD is temporary output authority, never destination-parent FD/name authority. Source/request/control/input descriptors are read-only; completion/payload/stage are temporary outputs. Parent protocol duplicates retire after last required parent use, at latest before post-reap decoding; original file owners remain available.

### 2.3 Transient and stock descriptors

At most four transient cells cover two current anchored rewalk/acquisition FDs while original authority stays live, plus one support-directory and one current-child FD during sequential validation/cleanup. RSS observation uses a transient role only while its helper is active; that descriptor retires before the role is reused.

Support has no persistent path/owner record; its original witness is in the worker-origin ledger. Membership enumeration finishes and closes its iterator/releases entry/helper state before current-file hashing/recheck. Any iterator-owned descriptor consumes a transient role, never an uncounted fifth FD. Retain only a bounded membership mask/cursor, not another names/witness forest. Actual iterator/control behavior remains to qualify.

At most six stock Popen descriptor lifetimes are reserved: one shared DEVNULL, one error-pipe pair and three conservative low-writer relocations. These are stock-owned, not product FD cells. The conservative simultaneous ceiling is28+8+4+6=46 owned/stock parent descriptor lifetimes. Original stdout/stderr are two borrowed inherited descriptors, not new owned cells. Unrelated caller/runtime descriptors are outside this count and grant no cleanup authority. This does not bound RLIMIT_NOFILE or every process descriptor.

Stage children are sequentially opened, never all held.135 regular files plus support yield136 witnessed entries; two directories refers to the stage and support, not136 retained child FD owners. Their two complete funded ledgers remain additive.

## 3. Unchanged projection dominates generated records

Use frozen C(n)=512+128*n, P(UTF-8 string length n)=128+4*n and scalar/reference slot128. Current identity P=1724. This is scalar projection dominance, not observed physical fit or reusable capacity.

| Generated-root term | P bytes |
|---|---:|
| Existing root record | 25096 |
| Replace4095-byte name allowance by generated≤54 | −4×(4095−54)=−16164 |
| Remaining original fields | 8932 |
| New parent_identity: member128+key188+identity1724 | 2040 |
| New path_ref: member128+key160+reference128 | 416 |
| Generated-root maximum | 11388 |
| Both roots: C(2)+2×11388 | **23544≤50960** |

path_ref is null or a reference to the separately funded ninth normalized description. It does not clone text or add a second persistent workspace path reference on output routes. Keep the full50960 reserve; no freed amount funds other state. Two transition root witnesses remain separately charged, not repurposed as parent identities. Concrete root header/control fields must fit the original header/container allowance.

For generated input basename≤32,29760−4×(4095−32)=13508. New created_identity costs member128+key192+identity1724=2044, yielding**15552≤29760**. Original input FD/entry/parent/digest fields stay charged. An external input uses its full original name projection, with no generated-name credit; any mixture of four remains within C(4)+4×29760=120064.

All nine path values, destination name, original/transition root witnesses, two full child ledgers, request/error/receipt models, FD cells and phase/helper slots remain additive. All original reservations stay intact; no surplus is reassigned. Concrete record headers/backing, actual reference counts and construction lifetimes remain pending.

## 4. NEW named parent FD/state allocation target

The prior contract supplied a160×512=81920-byte pool outside CONTROL but no historical named phase schedule. This is the accepted new allocation target. Slots are accounting labels, not a public array or authority token. Every concrete occupant must map to a live role or an independently funded P/buffer term. Exceeding a group stops work for reviewed correction; the unused slot is not permission to grow. Neither arithmetic nor narrow prior owner observations demonstrates full-route fit.

Existing W_parent projections already pay path/basename text, owner fields/witnesses/identities/digests, request/API/CLI bindings, both ledgers, prepared/committed receipts, finding/checks/ErrorEnvelope, signal/stream originals, scientific references and argv. These cells pay registered descriptors and extra implementation/control state, not those payloads twice. A reference does not pay a model/path/forest/buffer clone. Two saved152-byte sigactions remain in signal_originals; ABI cells fund transient wrappers/control.

| Slots | Group | Cells | Intended occupants and pending fit |
|---|---|---:|---|
| 1–28 | Persistent descriptors | 28 | §2 owner cells; whole-route count/liveness pending |
| 29–30 | Closed budget state | 2 | One exact Deadline or qualified LogicalOnlyBudget and exact cancellation state, each≤512; native requires Deadline |
| 31–38 | Route lifecycle | 8 | Child owner, independent outcome, active context, cleanup cursor, active/reentry guard, ContextVar token, commit-capture and signal-handoff cursor; projected values borrowed |
| 39–56 | Retained stock wrapper | 18 | Source-derived8732-byte wrapper/lock/dict/key/reference projection rounded to9216; argv separately charged; pinned physical fit pending |
| 57–64 | Protocol duplicates | 8 | Acquired FD registered before setup, retired before close; exact interface/implementation pending |
| 65–68 | Transient descriptors | 4 | Rewalk/acquisition pair plus support/current-child, iterator or sequential observation roles |
| 69–105 | Stock constructor fixed subtotal | 37 | Finite containers/control and stock descriptor lifetimes below; live through constructor/unwind |
| 106–129 | Current phase helper lane | 24 | Either owner stat16+walk/state8, or stock launch helpers/control24; actual helper return/release required before reuse |
| 130–137 | Native ABI control | 8 | Current syscall/ctypes scalar/address/result wrappers and signal/rename control; payloads separately funded |
| 138–145 | Child observation | 8 | Exact-PID wait status plus current bounded RSS parser/cursor; read payload separately funded |
| 146–153 | Streaming/digest | 8 | Current read/write/poll cursors and one current digest state; no per-file context forest |
| 154–159 | Sanitization/retirement | 6 | Bounded primary/secondary failure references, retirement cursor, sanitized-return control; earlier frames stay charged until return |
| 160 | Unassigned | 1 | Any assignment requires explicit review |
| **Conservatively simultaneous assigned total** | | **159=81408 bytes** | **Allocation target; whole-route fit remains pending** |

The constructor fixed subtotal is the55-cell source-audit subtotal minus the separately retained18-cell wrapper:

| Constructor occupants | Cells |
|---|---:|
| Exact pass-FD tuple,≤8 entries | 5 |
| Keep set,≤9 entries | 6 |
| Sorted FD list and native-call FD tuple | 8 |
| Map/set iterators | 2 |
| Argv clone and converted-argv tuple | 6 |
| One-candidate executable tuple | 2 |
| Low-FD list | 2 |
| Stock descriptor lifetimes | 6 |
| **Subtotal** | **37** |

The24-cell/12288-byte launch helper lane covers stock constructor/helper frames, call-argument references, ExitStack/deque/callback machinery, `_on_error_fd_closer` generator/context manager and current error/unwind control. It is a new design budget, not a measured or source-proven upper bound. Qualification must fit both pinned builds; ordinary behavior exceeding it fails this design target, without silently enlarging the pool or hiding state in runtime allowance.

During owner work the same lane is16 cells/8192 bytes for one exact stat_result/helper observation plus8 cells/4096 bytes for current transient owner shell, bounded identity records, walk cursor and helper control. Prior narrow stat observations do not prove the eight new cells or whole-route coexistence. Path components/cwd/normalized construction remain in the existing64 KiB path scratch, not this lane.

### 4.1 Phase ceilings and mandatory release

P=28 persistent cells and B=2 budget cells are conservatively held throughout; ceilings below are sums, not measured peaks. The159-cell all-groups sum is stronger arithmetic, but every representation and release boundary still requires observation.

| Phase | Groups beyond P+B | Cell ceiling | Transition requirement |
|---|---|---:|---|
| A: acquisition/binding/serialization | lifecycle8+protocol8+transient4+helper24+ABI8+stream8+retirement6 | 96 | Bootstrap/serialization helpers return; required raw/Recipe/selection/parse forests retire; retain funded owners/models/digests/files |
| B: constructor/adoption | lifecycle8+wrapper18+protocol8+transient4+constructor37+helper24+ABI8+retirement6 | 143 | Idempotently adopt returned wrapper/PID before semantic work; retire constructor helpers/vectors/error-pipe payload; retain wrapper through REAPED/LOST |
| C: owned wait/RSS/cancellation | lifecycle8+wrapper18+protocol8+transient4+helper24+ABI8+observation8+retirement6 | 114 | Actual terminal exact-PID reap or LOST; LOST cannot succeed; release wrapper/argv/launch references before decode |
| D: completion/manifest/scientific reconstruction | lifecycle8+transient4+helper24+ABI8+stream8+retirement6 | 88 | Completion helper returns before manifest helper, which returns before reconstruction; owners/receipts/ledgers remain additive |
| E: stage/source/input validation and checkpoint | lifecycle8+transient4+helper24+ABI8+stream8+retirement6 | 88 | One child/digest at a time; original expectations retained; no earlier forest hidden by exception/generator/frame |
| F: no-replace install/receipt capture | lifecycle8+transient4+helper24+ABI8+retirement6 | 80 | Actual syscall return immediately captures preallocated committed state/receipt; installed output is never rolled back |
| G: output/cleanup/signal handoff | lifecycle8+transient4+helper24+ABI8+stream8+retirement6 | 88 | Retire before close; preserve primary/commit/receipt; restore stream flags before prior-handler handoff; no installed-output cleanup |

Unadopted failed startup does not enter successful C–F. Its possibly retained stock state and residual worker follow §1, with no complete teardown/end-to-end resource guarantee. Still-live constructor/helper state stays charged throughout supported ordinary unwind. A retained traceback cannot make the success schedule appear smaller.

### 4.2 Existing serial buffers and worker/caller boundaries

Three common SERIAL_BUFFER_BYTES reservations stay3×65536. Separate path_normalization_scratch stays65536 and cannot be borrowed while an earlier path helper lives. Launch accounting assumes the bounded six-string argv, strict UTF-8 absolute interpreter path≤4095, decimal FD roles3..2**31−1, pass_fds≤8, cwd=None, env=None and the fixed Popen flags. Exact private launch signatures remain to freeze and qualify.

The source-derived retained argv P is18628. Known constructor payload peak is73477, including stock os.read(...,50000), encoded executable and trusted short error payload; container/control cells are separate. Native arrays request8355, conservatively charged9635 with ten block allowances, retire before error-pipe reading and are already inside those constructor alternatives.

Before B, actual bytes/bytearray allocations occupying S0/S1 must retire. Their131072 combined capacity then funds the known73477-byte payload; an allocated idle buffer does not free capacity. S2 remains only for a separately justified simultaneous need, with no hidden duplicate64 KiB allocation. After successful return, wrapper.args retains18628 in S0 through actual REAPED/LOST and release; no argv-retirement optimization is assumed. C may use S1 for bounded RSS/read, never completion/scientific parsing. Protocol duplicates retire by D, retaining original file owners.

Before D, release wrapper/argv, helpers, vectors and exceptions. S0/S1/S2 resume their existing streaming/serialization roles. W_parent and965*N response/manifest/scientific decode reservations remain fully additive and follow actual sequential helper-return barriers; no state/serial-buffer substitution pays them.

Known launch byte bounds exclude unresolved libc/locale error-text construction. Qualify ordinary supported error construction/overlap within existing reservations. No extra capacity is granted for arbitrary audit/profile/trace callbacks or unrelated `_active` cleanup. Settle the bounded supported runtime scope explicitly without disabling audit/security behavior or claiming that main-thread status proves it.

Worker CONTROL stays separate: creation ledger430272+StageWitness656672+completion shell36168+existing overlay/native145324+three extra buffers196608=1465044≤2097152. Completion borrows the seal; validation stream-regenerates the charged manifest. Worker exit retires worker state; parent models/ledgers/receipts retain their own charges. No combined RSS cap follows. Pure-memory LogicalOnlyBudget is allowed only after actual route qualification, with no native RSS/60-second/reap claim or authority from caller-created scalar records.

## 5. Conditional final-output integrity

This is a design argument with pending integration premises, not a report that the routes passed.

| Premise to implement and qualify | Failed-start consequence |
|---|---|
| Originally anchored ordinary source/input FDs are read-only; trusted native adapter uses inherited read-only authority; original witness/alias/overlap guards hold | Supported source/input content is not written by worker or parent failure cleanup |
| Trusted worker writes only declared owned temporary workspace/stage roles and receives no final destination parent/name authority | Residual work may change temporary files but has no supported final-install operation |
| Only parent installer renames into final destination | Worker completion alone cannot expose final output |
| Installer requires adopted ownership, terminal exact-PID reap, bounded completion/seals/receipt, original source/input rechecks and final cancellation/deadline checkpoint | Every unadopted constructor-failure invocation is rejected before install, regardless of later bytes |
| Qualified native renameat2(RENAME_NOREPLACE) preserves existing output | No replacement/partial installation is added |

With these premises, previously absent final output stays absent and existing final output stays byte-for-byte unchanged. Temporary contents may continue changing. Trusted workers and quiescent qualified filesystems remain assumptions; withholding a name/FD is not a sandbox against malicious code. Ordinary source hardlinks retain original witness/alias protection; stage/bundle regular files retain their single-link rule. Lexical normalization alone grants no authority. Final-stat/check-to-return races, forced death and whole-process-tree containment remain outside the guarantee.

Adopted success keeps the full sequence: worker replay/source/runtime/stage validation→exit→actual exact-PID reap→bounded completion helper return→anchored parent seal/manifest/receipt validation→original source/input rechecks→final checkpoint→qualified no-replace rename→immediate committed receipt. Failed-start cleanup/resource enforcement is the narrowed guarantee; no later residual output revives success.

## 6. Pending qualification before native use

The seven ordinary cases are all unrun at this design integration. Use benign owned temporary inputs/outputs/workers, preserve source/output bytes and witnesses before each and inspect independently afterward. A fixture may retain its own exact child identity only for its own teardown; it cannot lend that authority to product outcomes. No arbitrary PID probe or foreign-child wait/signal is permitted.

| Case | Required observation on both pinned profiles |
|---|---|
| Absent interpreter and owned ordinary nonexecutable candidate | Sanitized constructor failure, no invented reap/success, unchanged source/output, registered parent resources retired |
| Controlled ordinary error-pipe read failure after real child creation | Unconfirmed termination, no adopted handle, unreachable commit, retained stage/workspace, fixture reaps only its own child |
| Returned wrapper with failure before/during adoption | Idempotent finally adoption, one owner, authoritative exact-PID wait/signaling; no signal after REAPED/LOST |
| Residual worker successfully finishes temporary output after constructor failure | Final output absent/unchanged; later completion cannot revive failed invocation; conservative residue |
| Earlier finding and temporal INT/TERM | Earlier finding forbids Popen; prelaunch cancellation forbids launch; first selection observation pins130/143 versus failed/3; late latch retained without replacing selected outcome |
| Existing final file/directory and independent source/output hardlink aliases | No replacement/mutation; original alias boundaries still refuse |
| Normal successful launch/terminal reap and normal worker failure | Existing adopted wait/validation/commit route only with its premises; unchanged source/input bytes |

Controlled error-pipe injection is test-only at the fixed stock boundary, never an admitted callback. If a pinned implementation no longer exposes that boundary, stop and adapt the frozen design before execution. Exhaustive allocator injection, hostile native parsing, signal-policy implementation and custom spawning are outside this slice.

Before each candidate review/execution, freeze the complete changed source/tests/docs with hash/mode manifest and a durable checkpoint. Qualification uses only the exact two pinned public profiles, with origin evidence and source/output-integrity/FD observations. Preserve previous sealed evidence. Design acceptance supplies no test pass.

Remaining separate gates are concrete generated root/input headers/backing; path construction overlap/borrowed reference release; actual read-only transitions; maximum persistent/protocol/transient/iterator coexistence; wrapper18/helper24 and all named lifecycle/ABI/observation/stream/retirement fits; stock runtime/_active/callback/libc/locale scope; exception/context/cause/traceback release and actual serial-buffer reuse; exact four-message/schema/emitter behavior; the seven live-worker cases; qualified read-only adapter; adopted exact-PID supervisor and signal/stream restoration; stage creation/seal/parent validation; original source/input rechecks; and real no-replace install/receipt ordering. All live-worker/native/stage/commit and whole-route/public-operation/distribution claims remain pending their evidence. If any target fails, stop for a reviewed correction within unchanged caps rather than silently enlarging the budget or scope.


## Eager-memory installation clarification

For the implemented eager-memory transaction, a cooperative cancellation observed before the final checkpoint prevents rename. A later observation may accompany installed output. Atomic no-replace installation does not imply Python-bytecode-atomic receipt capture or delivery against arbitrary asynchronous caller exceptions or forced termination. Preserve caller signal policy. For a catchable caller interruption after an installation attempt, the interruption is re-raised as the same exception object with its existing notes and exception-chain details while original-inode reconciliation is attempted. Earlier source or replay validation may shorten traceback and chaining details to release temporary state; it preserves the exception object and notes, but does not promise cause/context preservation. Reconciliation remains best effort under repeated interruption. Cleanup never removes the requested destination. See MEMORY-COMMIT-INTERRUPTION.md. Supervised file-native launch/handler promises remain separately gated.
