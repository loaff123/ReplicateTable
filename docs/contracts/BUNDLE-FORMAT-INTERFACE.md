# Pure bundle formats and report: implementation interface

Status: private implementation handoff for E1; no cap/formula change, native IO,
parser, replay, filesystem transaction or release qualification is introduced.
The five normative documents remain authoritative. This file freezes the first
format/report implementation and is not a new public serialization version.

## Signatures and authority

- `_bundle_formats._iter_table_csv(plan, result)` yields exact bytes
- `_bundle_formats._iter_support_csv(plan, result, column_index, stage_index)` yields exact bytes
- `_bundle_formats._iter_table_schema(plan)` yields exact canonical JSON bytes
- `_bundle_formats._iter_support_schema(plan, column_index, stage_index)` yields exact canonical JSON bytes
- `report._iter_report(plan, result)` yields exact report bytes without a whole-document buffer
- `report.render_report(plan, result)` returns exact bytes
- `_bundle_formats._plan_json_chunks(plan)` is the internal borrowed-field canonical walker, entered only after exact plan/admission validation

Arguments are genuine exact BoundPlan/ComputationResult instances. Positional
indices are exact integers within actual compiled columns/stages; bool refuses.
Each consuming iterator enters `_required_inputs` and `_guard('serialize')`
before first output and retains that closure until exhaustion/close. Matching
plan/result context uses the real admission integration, including distinct
A/B/C backing where applicable. Nothing fabricates a plan or result slot.
Structural checks do not prove source content, runtime or numerical replay.
The renderer freshly requires the expected runtime before fingerprints and at
its success boundary. Its scope text describes what bundle verification means;
it never declares that rendering itself has performed a replay.

## Streaming and component counters

CSV walks the already-owned rows and stage support offsets. It emits field
punctuation and one scalar/Unicode character at a time. String labels are always
quoted, quote characters doubled; numeric repr is exact, null is empty and the
bounded three-reason tuple is canonical JSON quoted as a CSV field only when
required. No record.to_dict, whole-result projection, DataFrame, eager row,
CSV record string, bytes collection or duplicate result forest is created.

Schema JSON emits fixed canonical field order. Only one bounded schema-column
record exists at a time, funded by K; every original logical name/dtype/unit is
preserved. Index-based CSV names remain collision free. Support and schema
member counters use the existing aggregate estimate as a conservative per-file
ceiling. Their eventual writer MUST ALSO sum all stage CSV/schema members under
stage_csv_bytes/schema_json_bytes and enforce the existing bundle ceiling via
its component ledger. Per-file checks cannot replace aggregate accounting.
Every fragment is checked before yielding; hard cap and lower-estimate breaches
retain report_bytes_limit/metadata_bytes_limit/bundle_bytes_limit versus the
operational resource_estimate_mismatch distinction.

## Exact report layout and display

All runtime template bytes/CSS/prose live in report.py. The test-only static
HTML golden freezes those bytes. It is never read by product code. The static
output stays within 32768 and the additional display notice is exactly222.
Report order and IDs follow API-SCHEMAS9. Coordinate headers are original name
plus ` [` plus exact Coordinate.dtype plus `]`. Every label uses ASCII JSON
scalars, explicit quotes for strings and visible literal `\u0020` spaces.
Escaping occurs only in text nodes with html.escape(quote=False), one source
character at a time, at most12 emitted bytes. Actual CSV data remains unchanged.

The grain section gives the complete original row_dims list in declared order.
The declaration `key:NN` always means the dimension at that position, matching
the CSV/schema mapping. Each column's explicit broadcast list uses these short
positional references. Thus even32 columns repeating16 long opaque names do
not multiply full dimension-name text. Table/stage headers retain original
names and exact dtypes. This is an HTML display mapping, not a schema change.
Complete row/support and all three per-column/per-stage reason totals are
computed over the full retained records; preview limits affect display only.
No all-column/stage summary tree is retained: one small counter triple and one
current summary entry are emitted at a time. Stage offsets avoid copied slices.

## Lifetime and dominance against unchanged Formula2

Let B=result_json_bytes and M=result_objects_bytes. The renderer runs inside
fresh Baseline admission, which is at least E_verify=common+3M+6B. Its caller
result occupies one M. No parse, validation-copy or replay result forest is
created. Consequently the exact remaining result serialization envelope is
2M+6B; it is not numerical scratch, a generic decoder discount or an increased
report allowance.

The implementation counts actual complete report length L with a fragment
walk before allocating a whole-document buffer, checks L against the existing
report estimate and8MiB cap, and checks the explicit dominance 2L<=2M+6B.
One exact bytearray(L) followed by one exact bytes(L) is the only whole-report
allocation path. No bytearray growth or Unicode document is used. The mutable
buffer and its iterator frame end before final runtime/source-admission helper
frames begin. At final checks only the returned immutable L bytes survive.
The existing common fixed-byte header pool covers these two byte-storage
headers; it allocates no payload and is not counted again here.

The layout's dominance decomposition is intentionally reviewable: actual
preview scalar text is bounded by one result JSON projection (ASCII coordinate
J, numeric32 and fixed-vocabulary reasons). Key/value/reasons cell and row
wrappers are charged to their existing result-record/map/list/private-instance
P, not hidden as unbounded static text. Each preview table has a real row or
support record because every admitted dimension and scalar product is positive;
that first record's container P pays its header/table wrappers. Complete
summary names/units/reason counters and typed headers use the remaining two
result JSON projections plus result string/container P. Positional broadcast
references are bounded by16 six-character names per column and avoid an
unbounded repeated logical-name term. Source/hash/notice/static prologue bytes
are fixed and must fit the minimum result root/container P slack. Focused
wide-name/wide-broadcast/effective-unit/all-stage tests and independent review
must verify this partition, not merely the equality guard. The guard is an
internal estimate-mismatch detector, not authority for silently shrinking the
admitted contract or raising a resource ceiling.

Other simultaneously live state has explicit owners:

- Canonical plan hashing borrows immutable plan/recipe/source/coordinate fields
  directly in canonical order. It calls neither plan._projection nor any
  plan/recipe serializer that freezes a parallel forest. Explicit A and genuine
  result-plan C may already occupy both Z roles. The one hash helper ends before
  any report buffer; only its four digest strings survive
- Four digest strings, one SHA256 state and one current summary/counter triple
  are within scalar_scratch's existing65536 minimum; no manifest coexists here
- One schema-column dictionary is bounded by K. CSV uses no dictionary/record
  scratch. The current record is borrowed, already counted in caller M
- At most one active format iterator stack exists. Fixed report nesting plus
  canonical plan/record streaming stays below32 frames. The focused physical
  lifetime check must show combined live generator/frame/token/digest/current
  summary storage <=65536, the scalar_scratch minimum, without borrowing the
  separate source/common MODEL_FIXED payload reservations
- CSV/report display tokens are <=32/12 bytes respectively; canonical plan JSON
  emits existing scalar fragments, never a complete Unicode document
- Common's three65536 serial buffers remain unallocated by these pure routines.
  The eventual writer may use only its separately scheduled shared buffer; no
  additional chunk aggregation buffer is allocated by the format iterator

Only byte-return `render_report` independently owns failure/cancellation
cleanup: its `_owned_attempt`/`_raise_owned` thin wrapper releases the owned
report buffers and helper frames before reraising the same exception. No
unrelated caller exception graph or global heap is walked.

The private `_iter_*` streams are ordinary generators, not independent public
operation boundaries. Exhaustion/close retires their admission context; it does
not sanitize an escaping traceback. In particular, a throw before first next,
post-yield emission failure or final-guard failure can retain model-bearing
iterator/helper frames on the exception even after close. The eventual writer
MUST own their complete operation: exhaust/close the iterator and retire its
owned exception traceback/context/cause and helper references at the actual
operation boundary before release, return, rethrow, replay or a new admission
phase. This is narrow owned-operation cleanup, never generic caller-frame or
heap sanitation. Add retained
exception/cancellation tests for pre-first-next throw, post-yield emission and
final-guard failure to that real writer gate. No such writer exists in this
slice. The current close-only tests establish admission-context retirement,
not independent private-generator failure sanitation. Aggregate stage/schema/
bundle counters remain the writer's separate mandatory responsibility.

## Remaining integration and evidence

The public package export is owned by the controller. Bundle file membership,
manifest, cumulative counters, source/replay verification, native transport,
actual atomic installation and browser QA are later gates. These modules expose
no parser or alternate reducer. Exact candidates and executable probes must be
checkpointed before any run/review; both approved profiles use -B and all six
numerical thread settings1. The static report must not be described as browser
QA or numerical proof.

## Route distinction (controller clarification)

The eventual writer calls private `report._iter_report(plan, result)` and streams
fragments directly under E_build. That iterator never allocates whole-report
bytes/bytearray and does not use the convenience envelope. Manifest construction
and replay/parse helpers are sequential with it. Existing record/scalar/serial
terms cover only its named finite iterator/digest/counter storage.

Only module-level `render_report` constructs bytes. It requires the genuine
canonical Baseline=max(E_build,E_verify,E_explain), not an E_build-only guard.
Its caller M remains live and the other result forests are absent, making the
explicit 2M+6B convenience envelope available. Neither route borrows occupied
Z/Dmeta payload terms. The borrowed-field hash helper must finish before whole
report allocation. No plan serialization projection or extra Z role is created.
Both count and fill consume the same frozen digests and raw report fragments,
without calling admission, hashing or public serializers while filling. The
fill iterator and mutable bytearray end before final runtime/admission checks.

The proposed buffer partition above requires independent review before coding;
the runtime inequality does not replace that review or prove the entire domain.

## Sufficient per-field buffer partition for review

The proposed exact implementation imposes a stricter static design target of
2048 literal bytes (within, and not changing, the contractual32768 ceiling).
This is a property of this template, not an input admission limit. Let d<=16,
c<=32. The following partition uses B's conservative numeric32 and the full
three-reason J268 even when actual reasons are empty. No result alias credit is
used. Only actual preview records are emitted, and every table has at least one
underlying result/support record.

1. First B copy: each shown key scalar <=J(scalar), each shown numeric/null
   <=numeric32 and each displayed reason array <=J(reasons). Report reasons
   contain only fixed ASCII words/quotes/punctuation, so text escaping adds
   nothing. All table/support preview scalar bytes inject into distinct
   corresponding result fields. Omitted rows only increase the available B
2. Second B copy: table logical header names inject into the first row's key,
   value and reason map keys. Support coordinate names inject into its first
   record's keys; fixed support header names inject into that record's field
   names. Stage headings use that first record's column/stage scalar strings.
   Name text escapes <=6U and is below the same occurrence's J=6U+2
3. Third B copy: grain row_dims maps to result.row_dims; all full stage summary
   column/stage/reason/count entry is at most171+J(column)+J(stage): its
   five fixed keys have54 characters,10 quote bytes and11 punctuation bytes,
   plus three numeric32 counts96. This fits the first SupportRecord name
   fields plus reason J268 alone, without using its six numeric fields192. Column summary plus column
   reason entry is at most347+2J(name)+J(unit):40 fixed bytes, broadcast<=145,
   and reason-entry fixed/counters<=162. In result the root unit occurrence
   and one row's value/reason entries contribute at least
   3J(name)+J(unit)+303, without assuming separator commas. Even charging
   two output separator commas gives46-J(name)<=38 because legal names have
   J>=8. The conservative residual remains at most41 bytes per column and is paid by the first row's map P below
4. M backing: every key/value/reasons map occurrence provides128 entry bytes,
   apart from all actual scalar/string P. A cell needs at most9 tag bytes.
   The first record additionally pays at most9 header-tag bytes, and for a
   coordinate at most45 dtype/syntax bytes (` [` + exact dtype + `]`, maximum
   dtype length7). Therefore a first coordinate entry pays<=63 of128. A
   first output column's two entries pay<=36 header/cell tag bytes plus the
   <=41 summary deficit, below256. Later displayed cells need<=9 of128
5. Row, table and stage wrappers have at most32 bytes per row and512 per
   table/stage section. Every row has three map bases of512 plus its root
   and private backing. Every support record has its eleven-field root C(11)=1920 and
   key-map base512. These disjoint container bases dominate all such wrappers,
   without spending the128 member bytes used in item4. Fixed support headings
   and per-record tags also fit these container bases
6. The result's non-row/root floor is4480 bytes: root C(5)1152 + root key
   P764 + version128 + row_dims base512 + minimum one-column units900 +
   rows/support base512 each. Static literal<=2048, display notice222,
   source/four-hash text<=1024 and fixed summary punctuation/totals<=1024
   total<=4318. Repeated per-column/stage entry punctuation was already counted
   in item3, and section/table wrappers in item5

Hence L<=3B+M for this specified layout and 2L<=6B+2M for its two exact
buffers. Each inequality is a review/test obligation on actual literal/tag/
field emission; generic growing templates, extra long-name repetitions or
additional summary fields cannot silently inherit the proof. Header dtype
text is charged to P rather than counted as a result JSON field. No new report
field can be justified merely by passing the scalar runtime guard.


The first static golden is tests/golden/report-v2-static.html,1917 bytes, SHA256
4838fe08117aeb717f0d5384069a7f5dfccf1d06298b6b3aa4abdc2fb8a69449.
It contains the concatenated fixed segments with empty dynamic insertion
points. Product code must contain those exact literals; it never opens this
golden. The initial independent design review accepted the disjoint partition
subject to the two corrected support counts and direct borrowed-field hash
remedy above, with actual implementation scratch/lifetime tests still required.
