# Formula 2: finite resource and lifetime contract

Status: NEW conservative rederivation for design review, 2026-10-06. Formula 1's missing common/schema coefficients are not reconstructed facts. Known primitive costs, W and E equations and all requested ceilings are preserved. This document defines every new coefficient and ancillary bound before coding. It is a logical allocation/work contract for admitted trusted stock objects, not a hard RSS/security theorem. Implementation, fresh measurements and independent review must demonstrate that the described lifetimes actually hold.

## 1. Fixed ceilings

Binary units: KiB=1024, MiB=1048576. All arithmetic is checked exact integer arithmetic; refuse before multiplying/appending/allocating beyond the applicable finite domain.

Preserved limits:

- SOURCE_FILE_BYTES_LIMIT=128 MiB; source file byte length is checked before native open/hash
- SOURCE_MEMORY_BASE_LIMIT=128 MiB (**NEW explicit reconstruction of source-owner/metadata admission boundary**, not an old recovered constant)
- SELECTED_NUMERIC_BYTES_LIMIT=64 MiB, union of distinct selected measurement/weight arrays, never sum per column
- COORDINATE_RAW_BYTES_LIMIT=8 MiB, COORDINATE_CANONICAL_BYTES_LIMIT=8 MiB, COORDINATE_LABEL_UTF8_BYTES_LIMIT=8 MiB, separately enforced for complete selected coordinate union
- LABEL_UTF8_BYTES_LIMIT=4096 per label
- OUTPUT_ROWS_LIMIT=100000; SUPPORT_RECORDS_LIMIT=1000000
- RECIPE_BYTES_LIMIT=1 MiB; KEY_BYTES_LIMIT=1 MiB
- METADATA_BYTES_LIMIT=16 MiB for each bounded descriptor/plan/schema/manifest model; RUNTIME_JSON_BYTES_LIMIT=1 MiB
- REPORT_BYTES_LIMIT=8 MiB; EXPLANATION_BYTES_LIMIT=8 MiB; BUNDLE_BYTES_LIMIT=128 MiB
- LOGICAL_JOURNEY_LIMIT=512 MiB; RUNTIME_ALLOWANCE=128 MiB
- EXPLANATION_CELL_LIMIT=1000 per source/stage section; REPORT_PREVIEW_LIMIT=100 rows/records per table/stage
- sampled adopted-native-worker PID RSS budget=1 GiB; one absolute wall budget=60 seconds, with documented startup/sampling/syscall overshoot and no pre-adoption enforcement/termination guarantee after unadopted constructor failure (NATIVE-LIFECYCLE §1), not process-tree/hard allocation guarantees
- CLI worker error whole encoded bytes≤4096; parent control/error envelopes≤16 MiB, further narrowed by decoder admission

**NEW ancillary bounds** (old exact values unavailable):

- source dimensions≤16; variable rank≤16; source data variables≤64; output columns 1..32; stages≤2 per column; total stage blocks≤64
- each dimension length 1..67108864, each variable shape product≤67108864; scalar has product1
- source name≤128 UTF-8, unit/calendar text≤512 UTF-8, metadata scalar string≤4096 UTF-8
- metadata depth≤8; per map≤64 entries; per sequence≤1024 entries; total metadata scalar/key occurrences≤65536; total containers≤8192, including attrs and encoding across source
- public JSON depth≤32; JSON numeric token≤32 ASCII bytes; generic counts≤2**63−1; input integers −2**63..2**64−1
- owner chain≤32 exact ndarray nodes; no cycle; runtime/input dictionaries use explicit bounded shapes
- bundle payload entries≤134 (six root payloads + 128 support files), total regular files≤135 including manifest, total directories≤2 including root; witnessed child entries≤136 including support; relative bundle path≤128 UTF-8
- source/plan/result explicit Dataset slots≤3; distinct Datasets≤3; input index objects≤16 per Dataset
- `WORK_CELL_LIMIT=268435456` (2**28 modeled scalar visits), `CONTROL_STATE_BYTES=2097152`, `SERIAL_BUFFER_BYTES=65536`, and `MODEL_FIXED_BYTES=65536`
- names/index/caches/owners are bounded before any generic walk. Any unavailable/unknown stock layout refuses; absence of historical exact layout tables is not permission for an unchecked fallback

Caps are conditional, not promises that all maxima fit together. A 64 MiB selection, 100000 rows or 1000000 support records can fail journey admission. Never enlarge a cap because a formula or implementation exceeds it. Boundary tests use genuine benign instances when practical; scalar-only seams test arithmetic equality/+1 without pretending that a synthetic seam proves native maximum capacity.

### Proven dense-family capacity limit (v7 clarification)

For the defined family of non-scalar, fully reduced, unweighted float64 selections with row_dims=[], at most32 output columns, exactly64 MiB in the distinct selected numeric union, and the mandatory1000-per-section compilation trace bound, Formula2 has a proven combined logical-admission lower bound of606419042 bytes. This exceeds536870912 bytes (512 MiB) by69548130 bytes before many positive source/model terms are counted. It is an analytical admission result, not measured RSS or a claim about all possible selection families.

The64 MiB selected-union number is therefore a rejection ceiling, not a promise that this family can be admitted at that size. Keep all existing coefficients/caps and qualify smaller practical instances with the complete estimator and actual source/runtime gates; a lower bound below512 MiB alone does not establish admission. No dtype-tight integer or other out-of-family exact-number claim is made here. Public-safe scalar evidence is `stage-b2-design/supplement-v2/DENSE-SANITY-AND-ANCHOR-GUARD.md` and `dense-sanity.json`, relative to the qualification evidence root; this note uses only their independently verified float64 subfamily.

## 2. Primitive JSON and object bounds

For exact primitive s, let U(s) be its strict UTF-8 byte length, measured incrementally without first allocating an unbounded UTF-8 copy.

- J(null)=4; J(bool)=5; J(int or finite float)=32; J(str)=6*U+2
- P(null/bool/int/finite float)=128; P(str)=128+4*U
- container P base with k entries is C(k)=512+128*k
- J(list[k])=2+max(k−1,0)+ΣJ(value)
- P(list[k])=C(k)+ΣP(value)
- J(map[k])=2+max(k−1,0)+Σ(J(key)+1+J(value))
- P(map[k])=C(k)+Σ(P(key)+P(value))

The final LF adds1 to each whole JSON document. Maps/tuples/frozen records use these same conservative container costs, without string/record alias credit. Dictionary keys are charged as occurrences. Metadata tags, dtype strings, field names, selectors, wrappers, list entries and hidden scalar byte counters are real costs, not free. Numeric32 is valid only because the lexical/dtype domain excludes arbitrary integers/decimal strings; string6U+2 covers JSON escaping/non-BMP surrogate display bounds. New exact-byte counters use actual serialization, but admission uses these conservative bounds.

Schema projections avoid building output records to estimate them. A scalar placeholder carries fixed J/P bound. For coordinate d, let Ld=length, maxJd=max J(label), maxPd=max P(label), obtained during bounded coordinate qualification. `KeyBound(K)` is the exact map formula over dimension field-name strings and maxJd/maxPd for each d in K. For repeated structures, sum the formula with multiplicity in integers; do not materialize an example forest. Empty maps/lists have their actual base charges. All formulas below mean these recursively defined symbolic J/P, not Python object construction.

## 3. Input, coordinates and plan footprint

Selected numeric union S is distinct source/weight variable names. A=Σ over S of itemsize*shape_product, ≤64 MiB. Same variable used in several columns is charged once here, but its per-column work remains separate.

For every retained source variable/coordinate, owner charge O(v)=whole terminal payload allocation + Σ safely measured retained ndarray headers along its chain. Conservative header charge per node is max(512+128*rank, measured exact-ndarray header bytes). Terminal ndarray payload is nbytes including unused capacity; bytes owner charge is exact len(bytes)+128. Owned object coordinates additionally charge P of every exact stored str/null/nonfinite-float object per occurrence, including unselected coordinates; pointer slots alone are insufficient. String byte/width/type scans occur in the safe prepass before hashes/copies. Shared terminal allocations and object occurrences are deliberately charged again per variable. Descriptor/metadata prepasses keep these full charges live during every incremental check.

Memory base P_input is ΣO(v) for all source variables/coordinates + P(bounded descriptor metadata) + stock container/index-header charges + MODEL_FIXED_BYTES. Stock Dataset/Variable/Index container headers and the finite raw metadata backing in the v9 closure below are charged using a frozen safe exact-type layout with at least C(member_count) and 512 bytes per Variable/Index; storage arrays are already in O(v), cache payload is excluded for separate C_cache. No hidden general referent traversal. P_input≤128 MiB before payload hashes. File base P_input=file size + P(descriptor metadata)+MODEL_FIXED_BYTES, a conservative read/native-container reserve despite streamed reads. The 128 MiB file cap applies to actual file size, and the full file base also enters journey admission.

Selected coordinate boundaries:

- Q_raw: Σ numeric/Unicode ndarray logical nbytes; owned object coordinates add pointer slots plus UTF-8 label/sentinel token payload lengths. For native VLEN, count pointer storage plus actual returned raw UTF-8 bytes, one returned scalar/chunk at a time before decoding
- Q_json: Σ J of physical label arrays including typed sentinel tokens before selection; then selected Coordinate serialization including dtype/values/sorted_indices. Both admission passes must fit 8 MiB; a canonical representation cannot quietly drop failed labels
- Q_utf8: sum actual UTF-8 label bytes, per occurrence across D, ≤8 MiB, each≤4096
- Q=P of the selected coordinate map containing dtype/physical scalar tuple/sorted-index tuple, with no sharing credit. This includes worst scalar/P/header overhead, not just raw bytes

For fixed-width native coordinates, dtype/shape preflight Q_raw and worst possible serialized/label storage before reading the array. For VLEN strings, supervise native scalar/chunk reads, inspect returned raw byte lengths before UTF-8 decode, and increment Q_raw/Q_json/Q_utf8 before retaining each admitted label. Native allocation before that returned-length check is the explicitly disclosed trusted-library caveat. Do not claim the precheck controls HDF5's internal VLEN allocation. Never request the full VLEN array merely to discover it is oversized.

Let Dmeta=P of the full descriptor metadata retained by a bound snapshot (excluding data owners and selected Coordinate forest); Jmeta is its canonical JSON bound. Let Plan0 be plan schema excluding estimates but including coordinate/model/resource-binding/runtime fields. Z=P(Plan0), Zj=J(Plan0)+1. This is a scalar projection; no full plan copy is created. Estimate block bound T is the map over the exact estimate-key list in §9 with numeric32/P128 fields. Plan_bytes_bound=Zj+J(T)+1 (one extra byte is conservative map-merge punctuation), plan_objects_bound=Z+P(T)+512. All actual canonical plans must fit both their estimate and 16 MiB cap. Recipe and runtime have their own independent J/P bounds.

Plan semantic identity does not contain pandas cache bytes. Bound resource_binding records the actual canonical base P_input/owners at compilation. Later distinct equivalent input X is separately measured, never silently substituted into this binding. The exact-match rule in API-SCHEMAS §5 applies both to persisted-plan reanchoring and to the live anchor before its saved non-cache credit is granted. Recompute the existing full kind/base_bytes/owners/descriptor_bytes record from actual bounded source state; compare every field/owner entry exactly, including shrinkage and changed charge distribution. This introduces no additional layout inventory or semantic fingerprint field. It cannot distinguish different physical arrangements that leave every existing binding field and the supported exact stock layout unchanged, and makes no such claim.

### Finite source/metadata accounting closure (NEW v9)

Apply the exact source bridge and global two-pass schedule in API-SCHEMAS §17. The raw source remains retained throughout: charge actual raw attrs/encoding container H, each bounded primitive occurrence, every metadata ndarray’s complete owner/header chain, and separately the final tagged descriptor P. No second normalized metadata forest is permitted. Metadata-array owners are in stock_headers/raw metadata backing, not new named scientific OwnerCharge entries. Repeat occurrences conservatively; no alias credit is inferred. Maintain the full scientific-owner subtotal during every metadata increment and refuse source_bytes_limit before normalized allocation.

Exact np.str_ raw backing replaces its generic raw primitive alternative with max(512,str.__sizeof__(value)+object.__sizeof__(value)+16)+128+4*(L+1), L from exact base str.__len__ after exact-class qualification. Its final tagged string P is still charged separately. Exact base character scanning determines actual UTF-8/context limits before base-string conversion; no dtype/item/buffer/NumPy str/repr path is used. Numeric/bool NumPy scalar raw occurrences remain covered by128 before their approved one-scalar conversion. No new global coefficient is introduced.

Native rank1 metadata Unicode has no coordinate-width cap: fully charge padded terminal capacity and headers, then scan bounded raw UTF32 codeunits. Empty vectors/U0 need no zero-sized buffer cast. Complete-source pass1 folds every owner/type/object/codeunit and aggregate tagged bound before any normalized string/tag/list prefix. Pass2 uses one exact UTF-8 bytearray≤4096, exact str P≤128+4*4096, a tiny token and at most two view headers in the unchanged65536 scalar-scratch minimum. Invalid scalar range/surrogates or actual UTF-8 excess fail before chr/decode/normalization; per-scalar reservation does not replace the whole-source pass. No padded scalar extraction, character list or normalized-vector shadow tree is allowed.

None and empty raw metadata slots share the same semantic empty-map tag; their actually retained allocations still follow the finite inventory. Derive resource_binding effects rather than assuming representation change alone must alter it. Explicit null declaration values remain present. Dataset._cache absent contributes0; present exact empty dict contributes H=max(512,dict.__sizeof__(cache)+16) once to C for each distinct Dataset, while the Dataset/slot header remains base. Nonempty/nonexact refuses; no mutation/compaction. Absent/fresh-empty/overcapacity-empty changes no semantic fingerprint or canonical P_input.

The scalar-backed RangeIndex factory produces the existing coordinate OwnerCharge with terminal_bytes=header_bytes=0 and logical_bytes=8*length. Its real bounded scalar/index/wrapper/container state is in stock_headers; there is no conceptual ndarray allocation. Semantic framing streams int64 from _range; cached _data is C only. Selected raw-coordinate precharge uses logical8*length, while raw byte facts for other routes come from actual qualified storage, not selected dtype.

The closed source control inventory permits exactly these new co-live shallow charges alongside the already-approved B2/control state: binding wrapper1936, one fresh80-owner tuple264512, Inspection wrapper2432, scan result1808, selection1388, SourceIdentity wrapper1488. Sum273564; plus existing1653500 gives1927064≤CONTROL_STATE_BYTES2097152, leaving170088. These numbers name this source-only schedule, not extra allowances. Source-only cursor/chain/metadata traversal/scratch occupancy is587936 under its reviewed phase-disjoint use. No MODEL_FIXED_BYTES is reused for these transients. Actual immutable-model/view headers still require implementation verification against their own existing reserves.

Only one fresh owner tuple, current scan and active owner/metadata walk exists. Fold/release A/B/C one at a time; release source cursor/walk/sort state before B2. Footprint mode folds descriptor J/P without a descriptor forest; existing-source consume compares/reuses immutable children; initial consume constructs only one tree. Active-plan nests preserve the complete outer baseline and declared3Q/2A slots; standalone memory adds actual observed C to its full source/model reservation. No duplicate baseline, hidden fourth Dataset, recursive scan→guard or claimed overlap subtraction.

This source subtotal alone is not whole-route admission. The v11 closure in §12 separately funds retained scientific callers, persistent parent state, control/scientific decode overlap, native shallow state and scanner counters. Those reviewed design requirements are now adopted; actual implementation/liveness and native journeys remain qualification gates.

### Finite declaration-status projection (v8)

SelectionStatus retains its three fields; its finite code enum now distinguishes unsupported_coordinate_encoding from unsupported_source_encoding, and its ordered reason enum is API-SCHEMAS §16. Coordinate worst status uses all seven reasons; data/weight worst status uses the last five. With the unchanged primitive rules, J/P for the status object (excluding its enclosing field and document LF) are respectively coordinate J1203/P4616 and data-or-weight J951/P3940. The old two-reason coordinate object was J600/P2944; data status can no longer be projected only as null. These are derived schema costs, not changed coefficients.

Charge status container/keys/code/reason strings/list entries before retaining them. Raw attrs and encoding declarations already contribute their complete tagged metadata costs separately; do not replace them with the derived status or count a disallowed declaration as a free omission. Update Dmeta, Plan0 when it contains descriptors, full I/Pp/Mp/Lp/native/API metadata projections and any inspection/control/report schema that actually carries this status. A projection without descriptor status does not gain a synthetic field. The existing source/coordinate/metadata/transport/journey ceilings, formula2 constants and phase lifetimes remain unchanged. Metadata preflight and the fixed reason enum bound derivation before payload work; no extra unbounded decoder/classifier tree is allowed.

## 4. Cardinality, work and numerical scratch

R=Π Ld for row_dims (empty product1). For column c: n(c,0)=source shape product. nw(c)=weight shape product if weighted first, else0. After stage i, n(c,i)=product of remaining lengths. Support total H=ΣcΣi n(c,i), in canonical complete blocks. Require R≤100000 and H≤1000000 before arrays/records.

Preserved numerical scratch:

Wc=32*n(c,0)+16*nw(c)+Σi[64*n(c,i−1)+128*n(c,i)].
W=max_c Wc (columns execute sequentially).

This allowance requires one float64 conversion buffer with in-place multiply/add, at most cast+immutable normalized-weight storage (16*nw), view-only weight alignment, bounded finite/positive masks and product/reduced arrays, release product before division, release weights after first stage, and no completed-column ndarray or expanded covariate forest. ArrayBuffer bytes/view headers are charged in common/model costs. A recovered implementation is only a candidate until tests prove these lifetimes.

NEW modeled work bound:

V=Σd[Ld*(1+ceil(log2(max(2,Ld))))] + Σc[4*n(c,0)+3*nw(c)+Σi(12*n(c,i−1)+8*n(c,i))] + 4*R*number_of_columns + 8*H.

Require V≤2**28 before engine execution. Sorting term covers typed coordinate ordering/permutation validation. Data terms conservatively cover conversion/masks/products/group passes; record terms cover creation and local validation. This is an operation-domain bound, not a time prediction. Full replay doubles engine visits within verification, explanation adds one selected trace materialization, and all controlled journey phases use the same absolute supervisor deadline regardless of visit estimate, subject to the startup/adoption and syscall-overshoot limits in API-SCHEMAS §19.2. Runtime scan bytes/occurrences obey independent finite caps. No CLI deadline resets between these components.

## 5. Exact projected result and output components

Row shape Qrow: keys=KeyBound(row_dims); values map of all output column names to numeric32/P128 or null bound; reasons map of every column name to the full three-reason sequence (safe for direct/unweighted). This projection uses widest allowable field content, not a sample row.

Support shape Qsupport(c,i): exact SupportRecord fields; keys=KeyBound(stage.support_dims); column/stage/unit use exact known strings; all numeric/count/value fields use numeric32/P128; reasons use full vocabulary. Retain field-name/object cost exactly. This treats separately rounded sums independently.

B=J({version:1,row_dims,units,rows:repeat(R,Qrow),support:concat repeat(n(c,i),Qsupport(c,i))})+1.
M=P of that same root, plus 128 bytes per row and support record for private immutable-model instance backing and one list-finalization pointer copy of 8*(R+H). No tuple sharing credit. Null may be cheaper but never increases the bound. Result.actual_bytes≤B; B≤128 MiB and overall bundle bound must pass before computation.

CSV field bound F(s) for exact string bytes is 2+2*U(s) (quotes plus worst quote doubling). Numeric F=32, null F=0; JSON reasons CSV F=2+2*J(reasons). Key strings always quote; numerics do not. One CSV record with k fields: ΣF + max(k−1,0)+1 for commas/LF. For key fields use max UTF-8 label length of its dimension; no records/Cartesian keys are built. Headers use exact known positional strings. Table_csv_bound=header_bound+R*row_csv_bound. Support_csv_bound=Σ block(header_bound+n(c,i)*support_csv_record_bound). Schema_json_bound sums exact J(table schema) and every J(support schema), plus each LF. Actual file counters are distinct, not only aggregate.

Recipe_json_bound=J(recipe)+1. Plan_json_bound defined in §3. Result_json_bound=B. Manifest projection contains every exact payload path, digest placeholders. A digest is a 64-character string, therefore J/P use string rule, never numeric32; actual size fields use numeric32. The manifest runtime is charged in full. Manifest_json_bound=J(exact manifest projection)+1. It is finite from at most134 entries; no file contents copied. Manifest excludes itself from files and contains only rows/support_records/payload_bytes totals, so there is no self-length recursion. Receipt bundle_bytes is actual final sum including manifest.

Report bound is rederived in §6. Bundle_bytes_bound=recipe_json_bound+plan_json_bound+B+table_csv_bound+schema_json_bound+support_csv_bound+report_bytes_bound+manifest_json_bound. schema_json_bound includes all stage schemas once, not both there and support_csv_bound. Require every metadata component≤16 MiB, report≤8 MiB, and aggregate≤128 MiB before stage allocation. If a conservative report bound exceeds8 MiB, refuse rather than silently reduce preview counts. Actual byte counters are enforced again before every write and checked at completion.

## 6. Report bound (NEW, including recovered display amendment)

Static literal template output≤32768 bytes, measured from constants. Add the exact222-byte display notice. Dynamic rendering is scalar/fragment streamed; no full Unicode document is kept alongside output bytes.

For text node str s, E(s)=6*U(s); for numeric token E=32; for a displayed string coordinate label, D(s)=6*U(s)+2 (two literal JSON quotes). This is a conservative ASCII-JSON-plus-text-escape bound: quotes remain text; `<`, `>`, `&` expansions are covered; a literal space becomes six-character backslash-u0020. A single Unicode character produces≤12 bytes through this route. Each coordinate header contributes E(name)+3+6*U(exact dtype). Non-coordinate headers use E(logical name) plus literal markup. Do not use HTML attribute escaping as a substitute.

Each emitted HTML dynamic scalar/cell reserves 32 additional literal bytes for its fixed tags/wrappers. Each table reserves512 literal bytes; each row reserves32. These are NEW template structural maxima, verified against actual golden template output. Static32768 covers page headings/CSS/fixed section prose; repeated wrappers are charged separately and cannot hide in the static bound.

Report_bytes_bound=32768+222 + J(identity/grain/units/repetition/complete totals-and-reason-summary display projection)*6 + Σpreview_tables [512 + Σheaders(32+header_display_bound) + n_preview*(32+Σcells(32+cell_display_bound))].

Identity/grain/etc display projection uses the exact known schema of source identity, four hashes, row_dims, columns' effective unit/broadcast, complete R/H counts, and three reason counts per column and per stage. It contains no source data values. n_preview=min(100,R) for table and min(100,n(c,i)) for each stage. Cell sets match CSV schema; reasons have their complete JSON vocabulary bound. Headers/cells are scalar projected from actual dtypes and maximum admitted label lengths. The multiplier6 conservatively bounds transforming the compact metadata summary into text, including labels/tags whose repeated wrappers remain explicitly charged. This choice is deliberately conservative and NEW, not a recovered historical coefficient.

## 7. Explanation bound and lifetime

Construct mandatory metadata-only Skeleton with all root/column/conversion/weight/coordinate fields, every source/stage section, total/omission counters, empty records, source selectors and full support offsets. At compilation use the exact schema, worst valid stored-key projection KeyBound(row_dims), and actual known names/dtypes/units/counts; no caller key exists yet. At execution the same bound covers the actual matched stored key. Valid over-width or malformed query temporaries are separately reserved before lookup under KEY_BYTES_LIMIT and actual P(key), and never retained in a successful explanation. Sbytes=J(Skeleton)+1 and Sobjects=P(Skeleton)+512+4*128 for two hidden name/value byte counters. If Sbytes>8 MiB, refuse before tracing, even if limit1.

For source-section c, T(c,source)=product of original dimensions not fixed by row key. CellMax(c) includes complete physical indices, typed labels, raw/converted values, raw/normalized weights and exclusion reason. Integer labels/values use exact numeric domain; strings use dimension maxima. For stage section c,i, T(c,i)=product of remaining dims not fixed by row key. RecordMax(c,i) includes support_index, complete SupportRecord and physical membership selector. Add the actual array-entry comma allowance. Each section contributes min(limit,T)*its respective maximal J/P; omission counters are already skeleton fields. Let Nshowmax=Σsections min(limit,T).

Trace candidate JSON bound = Sbytes + Σsections min(limit,T)*(J(display_record)+1).
trace_bytes=min(8 MiB,trace candidate JSON bound).

Trace object bound = Sobjects + Σsections min(limit,T)*P(display_record) + C(Nshowmax) + 8*Nshowmax + P(worst display record) + max widened-token bytes + traversal + key charge.

- C(Nshowmax) conservatively charges record-list backing even if records are in separate lists; each actual section's empty list is already skeleton-charged
- 8*Nshowmax is the one permitted list-to-immutable-finalization pointer copy
- one worst-record P scratch is charged even when the next record does not fit
- max widened-token bytes=4*max_scalar_J+max_scalar_J+256, for the single current Unicode token and encoded bytes; no full document Unicode exists
- traversal=32*(512+4*128) for at most32 four-slot traversal frames
- key charge=max(P(KeyBound(row_dims))+J(KeyBound(row_dims))+1, C(16)+16*((128+4*128)+128+4*4096)+5*KEY_BYTES_LIMIT) (compile-time worst stored-key model plus conservative raw query-validation envelope; caller argument survives, no hidden copied whole row)

The conservative object bound may charge more records than fit the byte ceiling; this is intentional and can conditionally reject high-width/many-column combinations. Do not assume byte truncation makes object scratch free. Actual produced record/object/byte counters are checked before retaining records. Mandatory skeleton is sized with worst applicable counters, so updating omission counts cannot exceed the reserved skeleton.

Before trace materialization, exact shared replay must be finished and replay/helper/iterator frames released. The caller result remains retained/charged; the replay result does not. At most the caller-selected union plus one new selected union coexist. No rebound BoundPlan Coordinate forest exists. RowExplanation owns only immutable output backing; weakrefs and real object-liveness probes must prove source/result/plan handles are released after return.

## 8. Common, E equations and admission

Define schema_objects=P(table schema)+ΣP(stage schema)+P(manifest projection without runtime)+P(verification/receipt shapes). Let K be max P of one row/support/CSV schema record. Let scalar_scratch=max(65536,largest admitted string/token JSON bound*5+256). Let fixed=CONTROL_STATE_BYTES+MODEL_FIXED_BYTES+3*SERIAL_BUFFER_BYTES. No runtime scanner scratch is added again: it is inside the unchanged128 MiB runtime allowance.

**NEW transport reserve:** Define full API metadata projections, each including the exact {version,kind,model,arrays} wrapper: I has Inspection model and empty arrays; Pp has {inspection:Inspection,coordinates:D} model and empty arrays; Mp has that prepared model plus at most64 typed array-frame descriptor entries in arrays; Lp has Plan0 plus estimate-block bound as model and empty arrays. Let Nj=J(projection)+1 and Pj=P(projection) for each.

For each non-result full metadata projection above, and explanation using its exact wrapper plus trace bounds, let T_wire=A+max_j(17*Nj+3*Pj). For explanation specifically, Nj=trace_bytes+explanation_wrapper_json_bound and Pj=trace_objects+explanation_wrapper_object_bound, with the exact version/kind/model/empty-arrays wrapper and the model represented only by its already-counted trace costs. The unchanged generic decoder uses 5*N+3*P_scan; its lexical string bound satisfies P_scan≤P_model+4*N, yielding the 17 coefficient without changing primitive costs. Let N_control be the locally projected maximum whole JSON bytes of the exact request, API/CLI sidecars, completion (including all plan-derived child witnesses), 4096-byte worker error, parent ErrorEnvelope and runtime-bearing manifest. Use componentwise maxima for finite null/status alternatives; sender estimates/counters are never authority. Let W_parent be the persistent parent inventory in §12, including original/normalized paths, original/transition witnesses, receipts and header/state slots.

transport_reserve_bytes = W_parent + max(T_wire,965*N_control).

Persistent W_parent survives both branches. Real response→manifest→scientific helper-frame barriers justify the maximum; additional retained inputs remain explicitly additive. This replaces the earlier wire-only reserve. Only transport_reserve_bytes, common_bytes, build_bytes, verify_bytes, explain_bytes and estimated_memory_bytes change, each by the same nonnegative transport delta; all 31 keys and all other formulas/caps remain unchanged. Near-limit narrowing and fresh rederivation of saved plans are required, not silent old-estimate credit. The fixed estimate-block projection prevents circularity. Result reconstruction instead uses the exact shared-decoder CALLER/PARSE/FINAL schedule under 3M+6B and the combined fixed-header pool in §12. Standalone/pre-plan routes use §12's explicit guards rather than future plan authority.

**NEW rederived common:**

common=128 MiB + P_input + 2*A + 3*Q + 2*Dmeta + 2*Z + P(T) + W + schema_objects + 2*K + scalar_scratch + fixed + transport_reserve_bytes.

Every term has an allocation purpose: runtime/import/scanner allowance; live original source base; at most two selected numeric unions; selected prepared/materialized/validation coordinate backing (conservative); descriptor and validation metadata; live plan plus bounded plan validation copy; estimates; numerical scratch; output schemas/manifest state; current record plus validator scratch; one token/encoding buffer; and controlled infrastructure. Some shared immutable objects are double-charged; this is safe and explicit. Implementers may not replace it with optimistic sharing credit without a reviewed formula change. Q/Z may both count coordinates conservatively. The common includes all live non-result/non-explanation structures described by the implementation architecture; new retained structures must be charged before introduction.

Preserved equations:

E_build=common+M+3*B.
E_verify=common+3*M+6*B.
E_explain=E_verify+trace_objects+3*trace_bytes.
Baseline=max(E_build,E_verify,E_explain).
Call total=Baseline+X+C_cache≤512 MiB.

The 3M/6B envelope covers caller result if present, bounded parse/validate result forests and replay with helper release. It never authorizes a fourth simultaneous result forest. The 3trace_bytes covers exact bytearray, final immutable bytes and a bounded serialization/validation allowance; widened scalar Unicode is separately charged. Writer streams and may use less than this envelope; convenience full-load paths may not exceed it.

Before any Baseline credit depending on live anchor A, run the complete safe non-cache footprint recheck against the saved resource_binding. A source-cap or unsupported-layout failure retains its existing earlier code; otherwise any unequal binding refuses source_resource_binding_mismatch with the fixed replan guidance in API-SCHEMAS. Never accept shrinkage by a ≤ comparison, replace the saved binding, drop A, add an anchor-delta to X, or reinterpret C_cache as excess non-cache storage. Full equality compares the existing finite record, not only P_input totals; same-footprint unused content is still not hashed/proved.

X sums complete freshly validated P_input for distinct required Dataset handles other than the plan anchor A, each only once by Dataset identity. Equivalent content is not identity deduplication. File handles add no hidden Dataset slot; loaded selected buffers are charged in A/Q. C_cache measures existing known stock cache allocations across all distinct known Dataset handles, with no credit for cross-Dataset aliasing. A's existing caches are included; baseline has no cache credit.

A complete total just above512 MiB produces CallAdmission admitted=false when safe bounded measurement completes. If cache/domain accumulation itself exceeds512 MiB, stop with estimated_memory_limit and state that complete admission was not evaluated; do not fabricate complete partial counters. Other limit failures use their precise early code. Recheck before copying/serializing/staging, at materialization boundaries, before replay and before final success/commit. Retained-but-unused A is validated for safe storage/descriptors/base/cache, not unconditionally hashed for semantics; consumed B must be rebound from its actual buffers.

At compilation, trace formulas always use limit=1000, the worst permitted public limit. A smaller later request cannot change the canonical plan or its max(E_build,E_verify,E_explain) baseline; it merely produces less actual trace work.

### NEW stock cache measurement contract

Source variable containers are exact xarray Variable or exact IndexVariable (ordinary dimension coordinates), with a frozen audited storage-field path to exact ndarray or exact xarray PandasIndexingAdapter/PandasIndex/PandasMultiIndex-free wrapper around admitted Index. Do not call generic `.data`/`.values` on an unqualified wrapper. Exact type/layout names and field paths must be checked from the pinned xarray source in the first preflight test increment; a path discrepancy blocks implementation until a reviewed correction. This explicit gate supplies unavailable implementation layout facts without pretending an uninspected slot name is historical.

The supported pandas2.2.3 Index is exact `Index` or exact `RangeIndex` held by the admitted exact xarray PandasIndex wrapper, with numeric ndarray or owned object-string backing. MultiIndex, extension indexes, subclasses/custom engines and unknown cache entries refuse. Frozen index-engine family is Int8/16/32/64Engine, UInt8/16/32/64Engine, Float32/64Engine and ObjectEngine with matching stock HashTable when allocated. Eleven numeric/object families must receive actual fresh per-profile table/layout qualification before adoption. RangeIndex has its own exact scalar state; no arbitrary range materialization is permitted to measure it.

Only already-present cache keys from the finite stock set `_engine`, `dtype`, `inferred_type`, `is_unique`, `is_monotonic_increasing`, `is_monotonic_decreasing`, `_is_multi`, `_na_value`, `hasnans`, `_can_hold_na`, `_should_fallback_to_positional` are eligible, together with only the two exact array-valued additions `_data` on RangeIndex and `_isnan` on Index defined below; each has an exact approved value type. dtype is an exact admitted numpy dtype; other semantic flags are exact bool/str/null or exact built-in finite/nonfinite scalar sentinel, not arbitrary object. Version-specific evidence must establish that inspecting these actual stored fields does not populate a cache; no property access that triggers a lookup is allowed. Additional stock keys require an explicit reviewed amendment, not silent trust.

Charge C(cache-entry-count)+ΣP(key)+P(value) for primitive entries; the engine entry adds512-byte object reserve, measured native mapping.sizeof() if a mapping already exists, safe measured engine/table headers, and whole terminal allocations/headers of any already-present exact bool-view masks. Native table body and bucket allocation are both counted; no deep=True object callback scan. The engine's compiled size routine and storage-field accesses must be audited against the pinned stock source and tested for nonallocation/nonmutation before use. Unknown mask/engine/table state refuses. A cache larger than its valid measurable bound is not zero. This is a new deliberately explicit cache profile; precise known compiled layout/header calls are a stop-gated implementation preflight, not guessed historical code.

### Finite stock-profile closure (v6 amendment)

This is a named exact-state addition to the call-local C_cache profile, not a new generic object traversal. No existing cache/reference list is created, cleared, compacted or dereferenced by measurement. Canonical P_input, source fingerprint and plan serialization remain unchanged by these retained derived states. Unknown types/fields continue to refuse unsupported_source_storage. C_cache is rechecked under the same512 MiB domain/admission rules and has no cross-Index/cross-Dataset alias credit.

The fixed eager field path is Dataset._variables[name] → exact Variable/IndexVariable._data → exact ndarray, or exact PandasIndexingAdapter.array → exact Index.__dict__['_data']; exact RangeIndex instead uses its bounded stored built-in `_range` scalar state for semantic labels. For an adapter-backed coordinate, any already-present Dataset._indexes[name] entry must be exact PandasIndex whose index is the same adapter index, dim agrees and coord_dtype equals the adapter’s exact `_dtype`. Direct unindexed ndarray coordinates remain admitted with no such entry; inspection never requires or creates an index entry for that route. Wrapper instance dicts are empty. Dataset uses only exact `_variables`/`_dims`/`_indexes` dicts and `_coord_names` set, bounded `_attrs`, `_encoding`, `_close=None`, and `_cache` absent or exact empty. Variable/IndexVariable uses its exact `_dims`, `_attrs`, `_encoding`, `_data` slots and has no instance dict. The three inherited NamedArray member slots `_attrs`/`_data`/`_dims` shadowed by Variable must be uninitialized; populated shadow slots refuse rather than hiding retained state. Exact Index instance keys are `_data`,`_name`,`_cache`,`_id`,`_references`; RangeIndex replaces `_data` with `_range`. Name is None/bounded str, `_id` is exact object, and all extra state refuses. These are finite prequalified storage-field routes, not property/duck-array access. Original indexed Unicode width is preserved in adapter._dtype/PandasIndex.coord_dtype despite owned object-string backing; those widths must agree and qualify every stored label.

For an already-present exact built-in container with k entries, charge H_container=max(512+128*k, exact_type.__sizeof__(container)+16). The second term includes retained backing capacity without invoking subclass methods; it is not a recursive traversal. Primitive entries retain the existing P charges. Incremental domain checks occur before walking any potentially large list.

1. **Index reference bookkeeping.** Inspect only the already-present Index.__dict__['_references'] slot. An exact Index requires exact pandas._libs.internals.BlockValuesRefs. An exact RangeIndex requires _references is None; a nonnull value on RangeIndex refuses, even if it is BlockValuesRefs. The following bookkeeping charge applies only to exact Index. Its referenced_blocks is an exact list; clear_counter is an exact nonnegative bounded int; every element is exact weakref.ReferenceType with its readonly __callback__ exactly None. Never call ref(), inspect a referent, traverse callback data, or call BlockValuesRefs methods that clear/compact the list. Charge C_refs=512+H_container(referenced_blocks)+sum(max(128,object.__sizeof__(ref)+16))+128. The512 reserves the BlockValuesRefs header and128 the scalar counter; weakref objects/list capacity are charged per occurrence even if shared. This whole charge belongs to call-local C_cache, not the canonical source base. A nonnull callback or unsupported reference state refuses before data reads/callbacks.

2. **Already materialized RangeIndex cache.** Inspect only exact RangeIndex.__dict__['_cache'].get('_data') when the key is already present; never access the RangeIndex._data property to obtain it. Its value must be exact ndarray, native int64, rank1, C-contiguous, immediate owned storage with base=None, length exactly len(the stored exact built-in range). Charge nbytes+max(640,np.ndarray.__sizeof__(array)−nbytes), in addition to the existing cache dict/key charge. An absent key contributes no array and is not filled in. Stored scalar range identity/semantics remain authoritative; this cache is not a source-payload redefinition.

3. **Already materialized missingness cache.** Inspect only an already-present exact Index.__dict__['_cache']['_isnan']. It is an exact rank1 C-contiguous bool ndarray whose shape equals the admitted stored index ndarray. Follow only exact ndarray owner nodes with dtype bool or uint8; at most32 nodes with the existing cycle guard. The terminal must be an exact owning C/F ndarray, not bytes/mmap/another exporter. Charge whole terminal nbytes plus sum over every node of max(512+128*rank,np.ndarray.__sizeof__(node)−(node.nbytes if the node owns else0)), plus existing cache dict/key charge. This admits ordinary bool views over owning uint8 storage without charging only the view. It does not authorize an extension-array mask or masked engine.

Engine inspection remains read-only through already-present stock values/mapping/mask fields. The eleven qualified numeric/object engine families require mask=None in this profile; Masked* and extension-backed engines remain excluded. `_isnan` is the explicitly admitted stock cache mask, not a reason to generalize engine mask support. For an already-present engine, charge512+object.__sizeof__(engine)+16; if its mapping is present, add object.__sizeof__(mapping)+16+ExactHashTable.sizeof(mapping,deep=False), with the exact corresponding table family. Engine.values must be the already-charged Index backing or RangeIndex cached _data by identity; a different array refuses rather than adding hidden storage. Do not call engine.__sizeof__, Index.memory_usage, Index.nbytes, Index._engine, BlockValuesRefs.has_reference or arbitrary instance sizing/property helpers: these can omit headers or mutate state. The selected exact native table size method includes body/flags/key-value buckets and never creates a mapping. Cached RangeIndex _data is accounting-only; bounded semantic enumeration uses stored _range, never cached payload as source truth.

In-memory root layout closure: exact Dataset._encoding must be None or an exact empty dict, checked before payload reads. Nonempty/other root encoding refuses unsupported_source_storage without mutation because Inspection has no root encoding field to bind it. Variable/coordinate encoding continues to follow its existing bounded schema. The direct native file adapter reads actual file attributes/storage metadata and need not instantiate an xarray Dataset; its temporary backend housekeeping is not user-declared semantic root encoding and does not reject ordinary files. No descriptor field or selected-source scope is added.

## 9. Exact estimate keys and actual output counters

Estimate JSON map has exactly these numeric count keys, all values nonnegative exact int≤2**63−1:

formula_version,source_base_bytes,selected_numeric_bytes,coordinate_raw_bytes,coordinate_canonical_bytes,coordinate_label_utf8_bytes,coordinate_objects_bytes,descriptor_objects_bytes,plan_objects_bytes,recipe_json_bytes,plan_json_bytes,result_json_bytes,result_objects_bytes,table_csv_bytes,stage_csv_bytes,schema_json_bytes,report_bytes,manifest_json_bytes,bundle_bytes,output_rows,support_records,work_cell_visits,numerical_scratch_bytes,trace_objects_bytes,trace_bytes,transport_reserve_bytes,common_bytes,build_bytes,verify_bytes,explain_bytes,estimated_memory_bytes.

formula_version=2. *_json_bytes and other serialized output values are conservative upper bounds, not claims of actual lengths; names in documentation/UI must call them estimates. Actual output counters are separate immutable map path -> {size_bytes,sha256} plus payload_bytes,manifest_bytes,bundle_bytes,rows,support_records; report/explanation maintain their own exact byte/count fields. Writer/report/explanation enforce both upper estimate and hard cap before each emitted fragment. A violated estimate is `resource_estimate_mismatch` exit3, not permission to expand a limit or silently succeed.

## 10. Runtime and parent transport finite accounting

Recovered runtime scanner caps: per inventory selected files≤2048, visited dirs≤512, relative names≤128 UTF-8, retained/queued name bytes≤128 KiB; whole binding occurrences≤8192, directory visits≤4096, file≤128 MiB, total hashed bytes≤256 MiB. One64 KiB readinto buffer, one inventory at a time. Core libraries≤16, product/Pint maps≤256 entries each. Stable metadata header processed bytes≤128 KiB, raw line≤4 KiB. Evidence full inventory≤16 MiB streamed outside production model. Scanner scratch≤1524736=1180160 retained-name/container bound+262144 sort/bookkeeping+65536 buffer+16384 entry/stat state+512. It is included in runtime allowance, not added as free extra memory.

Every control/error/manifest decode still precharges N+4*N+3*320*N=965*N before retaining raw bytes or decoding. The 320 coefficient is a coarse control-forest bound, not semantic P. Its complete current-live guard now includes actual caller scientific state and W_parent through §§8,12; two separately passing reservations never authorize their overlap. Nominal 16 MiB remains only a rejection ceiling. No numeric-scratch borrowing or fabricated caller-baseline subtraction is permitted.

Original parent state includes up to 136 child entries per ledger, all original path/FD/stream/signal/witness/receipt state, and a separately charged ledger-transition alternative. Response parse frames die before manifest reread and that frame dies before scientific reconstruction. Distinct co-live envelopes would require their summed charge and a reviewed schedule rather than the sequential maximum. CLI payloads stream after reap with a 64 KiB buffer; Python reconstruction uses the corrected route guards. Fallback remains independently ≤4096 bytes preserving code/progress/committed receipt; no new deadline for tiny error backpressure.

### 10.1 Bounded stock-unit scratch within the existing allowance (NEW v10)

The API-SCHEMAS §18 guard reserves 512 KiB (524288 bytes) BEFORE preprocessing, inside the unchanged 128 MiB runtime allowance. This is not a new estimate key or added allowance. Its finite components are:

- At most two transformed strings, each bounded by 16 times raw UTF-8 bytes and at most 8192 bytes: 2*(128+4*8192)=65792 bytes
- At most 128 meaningful tokens plus two final empty terminators, including token-list/container backing, current exact TokenInfo, spans/strings/fields/pointers and shared line text charged once: at most 196608 bytes
- At most 255 exact tree nodes, at most 128 token-bounded recursive builder frames, the bounded iterative validation walker and numeric-literal scratch: at most 196608 bytes

Total 459008 leaves 65280 bytes within that reservation. Parenthesis and final tree depth are each at most 32; numeric token spelling is at most 32 ASCII bytes with the existing integer/finite-float domain. Focused implementation/profile checks must include in-flight preprocessing/tokenizer buffers, current token, actual headers and build-frame peaks, not merely the final retained objects. Guards precede the allocations/evaluation they protect; no parse-first retrospective admission.

Guard strings/token/tree/walker frames die before raw-leaf work. Each raw leaf has one current closed definition graph under the existing 128-node/512-term/65536-conservative-JSON limits. Across source and target, at most 128 distinct canonical definitions and 512 aggregate terms (unique-definition references once plus every raw NAME occurrence) are retained only as bounded primitive summaries. Discard each transient closure before the next and discard leaf tuples/summaries before the final reachable graph. No second graph forest is permitted. Final UnitOperation objects remain in existing plan Z; transient graph/cache work remains in the runtime/compiler allowance. The one private process registry, at most 64 qualification attempts per locked semantic pass including failures, restored operation overlay/cache, and unchanged shared stock LRU128 have the lifetime obligations in §18. A failed initialization cannot cause a second construction attempt; failed restoration poisons the state.

The 512 KiB reservation is not the entire registry budget or a whole-caller-heap bound. Imports, runtime scanner, fixed registry, private operation cache/overlay, guard and graph scratch must fit together within the existing runtime allowance in integrated qualification. Do not change caller GC settings, collect globally or clear caller/shared stock caches to make a measurement pass. Complete runtime/source/admission/compiler proof remains separate. All 31 estimate fields, P/J primitives, W/common/E equations, caps, X/C and transport/native reservations are unchanged. In particular the existing normalized-weight 16*nweights scratch relies on released sequential masks, cast-plus-immutable-bytes overlap, then cast release before final constructor masks; the original input remains in A.

## 11. Stable early refusals and evidence

Before reads/copies: invalid_recipe/key/plan/source type; source_fingerprint_mismatch (when expected identity already held); invalid_source_phase; unsupported_source_storage; source_bytes_limit; metadata_bytes_limit; coordinate_bytes_limit; label_bytes_limit; unsupported_coordinate_encoding; missing_row_key/missing_coordinate; duplicate_row_key/duplicate_coordinate/nonfinite_coordinate; selected_numeric_bytes_limit; output_rows_limit; support_records_limit; work_cell_limit; estimated_memory_limit. Error ordering within a single unrelated set is fixed by API validation order tests, never hash/serialize first to manufacture a later error.

On actual emission: report_bytes_limit,explanation_bytes_limit,bundle_bytes_limit,resource_estimate_mismatch. On numerical finite overflow: numeric_overflow. Runtime family is API-SCHEMAS §11. Native budget/time/IO/worker failures remain operational exit3 except explicit cancellation. In particular, attempted stock-constructor failure without an adopted returned wrapper/PID selects supervision_unavailable/failed/3 unless the first INT/TERM latch is observed at its one managed selection boundary, in which case interrupted/cancelled/130 or143 applies. Preflight supervision_unavailable stays refused/2; existing LOST and other branches are unchanged. No launch is allowed with an earlier finding. Later cleanup findings/latches preserve the selected failed-start outcome and progress as specified in NATIVE-LIFECYCLE §1. Unknown cache/storage layouts are unsupported_source_storage, not guessed byte counts.

Before final qualification, measure real admitted small/medium/practical-maximum file and memory journeys on both fresh profiles, including import/registry/scanner RSS, selected-owner retention, explanation overlap/release, output serialization, parent decoder/witness state, worker/caller paired RSS samples, time/backpressure, and untouched-cache controls. Report measured size/workload and margins. A tiny scalar seam cannot establish native maxima. The combination of logical bound and sampled operational supervision still does not certify arbitrary native allocator behavior, cold storage timing, concurrent mutation or total process-tree memory.


## 12. Complete native/API route accounting (NEW v11)

This finite correction is adopted design, with implementation and actual lifetime/OS/source journeys still to qualify. All existing 31 estimate keys, source/metadata/array/output caps, 512 MiB ceiling, P/J costs, X/cache/resource-binding meanings and unit §10.1 are unchanged. The corrected source-kind rule is final: file base is actual file size + exact Inspection P + source MODEL_FIXED; only actual file bytes face the 128 MiB file cap, while the full base enters admission. Memory base retains its separate cap.

### 12.1 One strict decoder, lexical and semantic counters

Let P_scan use the unchanged B1 lexical string cost 128+4*L for raw UTF-8 token-interior length L, and P_model use 128+4*U for decoded UTF-8 length U. Every admitted escape/UTF-8 spelling has U≤L; string token interiors are disjoint and sum to at most N. Thus P_scan−P_model=4*Σ(L−U)≤4*N. Other primitive/container/member costs are identical. Invalid UTF-8, overlong spelling, lone/bad surrogate pairs, escapes, duplicates, depth and numeric violations still refuse. D(N,P_scan)=5*N+3*P_scan remains the generic strict-loader reservation; valid projected non-result shapes are conservatively covered by 17*N+3*P_model. Observed scanner peak/key allocation guards still precede every allocation, including malformed extra structure.

A narrow forest-free observer in the SAME bounded lexer additionally measures exact decoded-width model P for the fixed Inspection/result wrapper; the SAME strict primitive-decoding implementation follows it. No new parser, public permit, caller-supplied trusted counter, lexical bypass, parse-to-measure forest or generic-baseline subtraction. Initial exact Inspection P excludes the wrapper and is rechecked from admitted fields before binding. The observer's eight scalar fields are exact_objects, model_start, model_objects, decoded_utf8, model_depth, root_field, model_seen, source_checked. Their bounded record is 3960 bytes; two 128-byte scalar slots on each of at most 32 lexical frames plus a 512-byte wrapper state yield 12664 bytes. Add this named state to the prior B2+C+native 1942940, giving 1955604≤CONTROL_STATE_BYTES 2097152. It is not another MODEL_FIXED occupant or permission for unnamed state.

### 12.2 Persistent W_parent, original paths and control projection

Let child paths be the exact six root payloads plus manifest.json and each compiled stage CSV/schema path; add support iff stage files exist. Zero-child standalone uses an empty set. Witnessed children≤136, regular files≤135, total directories≤2. Generated stage paths have their exact positional spelling (maximum 27 bytes). Each original/transition ledger costs C(n)+ΣP({path:<exact path>,witness:<FileWitness numeric placeholders>,sha256:<64-byte digest>}); both complete ledgers are charged without alias credit.

W_parent is the following finite accounting map P plus 160*512 FD/state bytes. These private projection labels are not wire/model fields. All listed values include their own nested primitive/container costs; outer map/key costs are separate. Numeric/bool/digest and nullable alternatives use the existing worst-case P, and original scientific models are borrowed by charged reference slots rather than cloned.

| Accounting field | P bytes |
|---|---:|
| api_bindings | 8572 |
| api_header_reservation | 23160 |
| caller_path_arguments | 591488 |
| checks | 2892 |
| children_original | ledger P above (512 when empty) |
| children_transition | ledger P above (512 when empty) |
| cli_bindings | 6952 |
| committed_receipt | 8048 |
| destination_name | 16508 |
| error_envelope | 16664 |
| finding | 4304 |
| inputs | 120064 |
| normalized_path_texts | 150236 |
| original_argv_state | 65536 |
| path_normalization_scratch | 65536 |
| prepared_receipt | 7548 |
| request | 6552 |
| root_owners | 50960 |
| root_witnesses | 7488 |
| scientific_reference_slots | 2560 |
| signal_originals | 21460 |
| source_lease | 30184 |
| source_references | 91448 |
| stream_originals | 11488 |
| workspace_files | 32832 |
| workspace_name | 344 |

Outer map/container/key P=8764 and FD/state slots=81920. Consequently W0=1434532 and W136=2913396 for the maximum exact child-path set. Nine normalized descriptions add 150576 to the earlier inventory: their value P=150236, plus 128 outer member bytes and 212 field-key bytes. Every canonical case gains that same increment on top of the earlier reviewed control-overlap correction.

The nine original path occurrences map to three required-context source FileReferences, one active source lease, four input roles and one destination-or-workspace-parent role. Bundle occupies an otherwise unused input role; no operation needs bundle plus all four recipe/plan/result/key roles. Source lease/reference sharing receives no credit. On output routes the ninth normalized text is the destination parent: the original output argument and destination_name keep their existing separate charges, and full normalized target construction retires before persistent parent-text retention. Workspace and stage share that qualified parent; workspace borrows its description only during a helper call. Non-output workspace uses qualified fixed `/tmp` in the otherwise unused ninth allowance, no TMPDIR or extra cwd/path role. Original argv is separately charged. Each exact original str/PosixPath retained state is at most 64 KiB; nine simultaneous normalized strict-UTF8 descriptions each at most 4095 bytes are separately funded. Generated roots/children use anchored basenames rather than extra full path owners. Owner name pays its basename. One 64 KiB normalization workspace holds offsets/current component and target-to-parent construction overlap; no persistent ancestor vector/second full string/cache. Path input qualification in API-SCHEMAS §19 precedes formatting/normalization. Source-reference retirement releases original argument/description/FD ownership together, without refreshing identity authority.

The owner map covers three source references and one lease with original FD/entry/parent/source witnesses; four input owners with independent digests; four workspace-file owners; two root owners and two transition root witnesses; two full child ledgers; prepared/committed receipts, ErrorEnvelope/checks/finding, exact request/API/CLI bindings; two stream snapshots, signal/mask/two 152-byte actions, eight scientific-reference slots; original arguments/argv/workspace; and 965*24 for the binary API header outside the phase maximum. W_parent is OUTSIDE CONTROL, not a second spend of its 2 MiB pool. Its uniform path allowances keep canonical estimates independent of actual private path text.

The two roots are workspace and stage; stage's immediate-parent FD is also destination-parent authority, including pre-stage acquisition state. NATIVE-LIFECYCLE §§2–4 normatively specify the descriptor/record map and NEW named state target: 28 persistent FD cells, at most eight protocol duplicates, four transients and six stock-owned constructor descriptor lifetimes (46 simultaneous owned/stock lifetimes, excluding borrowed stdout/stderr). The 160×512 pool stays81920;159 assigned cells total81408 and slot160 remains unassigned. No historical per-phase allocation or demonstrated whole-route fit is claimed.

Generated-root/input dominance uses the same C/P coefficients and identity P=1724: root25096−4×(4095−54)+2040 parent_identity+416 path_ref=11388, so both roots C(2)+2×11388=23544≤50960. Generated input29760−4×(4095−32)+2044 created_identity=15552≤29760; any mixture of four external/generated inputs stays within C(4)+4×29760=120064. Full existing reserves remain charged; no shorter-name surplus is reassigned. Root-transition witnesses, nine path values, destination name, two ledgers, model/receipt state and all FD/helper cells remain additive. Physical headers/backing, borrowed path references, access modes, maximum coexistence and actual retirement remain pending qualification.

NATIVE-LIFECYCLE §4's named phase ceilings and serial-buffer schedule are allocation targets within these unchanged totals. In particular, wrapper18 and constructor-helper24 need physical qualification; two actually retired common64 KiB buffers fund the known73477-byte constructor payload, retained argv18628 stays funded until REAPED/LOST, and response→manifest→scientific decode frames remain sequential and separately charged. Ordinary stock `_active`/callback scope, libc/locale error construction and exception release remain unresolved implementation gates, not extra runtime allowance. No interpreter/profile/locale expansion or cap/key/wire change follows from this design.

N_control is max of J+LF for the exact request, API bindings, CLI bindings, full operation completion, parent ErrorEnvelope and plan-derived full-runtime manifest, and 4096 for the whole worker error. Use actual compiled child names/counts and componentwise maxima for all finite alternatives. Completion's StageWitness includes support. No returned counter, estimate value or missing-null shortcut determines the bound. Runtime/common/control/three buffers and all caller models remain funded during 965*N decoding. Complete control/error frames are sequential with manifest and scientific parse frames; W_parent and original/compact receipt state remain additive across them. If a helper/exception/generator retains an earlier forest, the maximum proof fails.

Worker creation/seal/completion has its separate post-B2 schedule: release estimator/source traversal temporaries before constructing the creation ledger. At maximum, creation ledger 430272 + sealed StageWitness 656672 + completion shell 36168 + existing overlay/native 145324 + conservative three extra 64 KiB buffers 196608 =1465044 inside CONTROL. Completion borrows the seal and writer validation stream-regenerates from its retained charged manifest; no clone/second manifest forest. This does not subtract the existing common buffer terms. Worker exit releases this entire worker ledger; parent summary/control/model state remains funded separately. No combined parent/worker RSS cap is claimed.

### 12.3 Separate source and common fixed-header pools

The initial tmpfs-only filesystem compatibility gate introduces no path, FD, persistent owner/token, cap or state slot. Sequential fstatfs120-byte and GETFLAGS8-byte storage plus per-call scalar/address/result/errno wrappers occupy the existing ABI8 lane; original parent stat observations use stat16 after each native helper returns, with current caller/helper control in walk8. The one shared import-time libc/syscall binding and fixed consumer types receive imported-runtime treatment only after their actual initialization/first-call/retained graph and co-live operation qualification. Lazy initialization cannot be reclassified as baseline. Cwd4096-byte storage remains in the already-funded path workspace. Every original W_parent term and all simultaneously live FD/budget cells remain additive; slot160 stays unused.

Source MODEL_FIXED and common MODEL_FIXED are distinct 65536-byte reserves. Against ONE source fixed reserve, conservatively count all three possible source views: three snapshot/MetadataValue/two-map-wrapper sets at 216, three 64-buffer sets at 56/header, three 16-Coordinate sets at 56/header, three SourceIdentity headers at 512 and 192 byte-storage headers at 128. Total=40200 (margin 25336), even if handles are deduplicated. Tuple/pair/primitive backing stays in source/A/Q/Dmeta; headers never pay payloads.

The common fixed pool simultaneously counts: result wrapper/key/context 16379; three returned snapshot/wrapper sets 648; two returned 64-ArrayBuffer header sets 7168; 128 immutable/staging byte-storage headers 16384; three 16-Coordinate sets 2688; six each of SourceIdentity/BoundPlan/Recipe/result-root headers at 512 totaling 12288; four rank≤16 readonly NumPy views each 352+112 base totaling 1856; four extra raw/frame byte-storage headers at 128 totaling 512. Total=57923≤65536 (margin 7613). Future exact root headers must fit 512 and these finite live counts. No per-row/stage extra wrapper forest. Four views permit measurement and optional weight base+reshape pairs only; retire prior views before the next variable. Exact-preallocated bytes/bytearray storage uses the 128 header/trailing-byte allowance; uncharged growth capacity is not covered. Result M retains its own original private backing costs. External arbitrary caller views are not discovered by heap traversal. Scanner state stays solely in CONTROL. Standalone routes pay BOTH fixed reserves; canonical transition pays common fixed once, never again.

### 12.4 Result decode: exactly CALLER/PARSE/FINAL

An internal result-decode context comes only from actual required source/plan/result arguments, freshly amended admission, verified payload FD/context/hash and this exact raw frame. The shared forest-free observer incrementally enforces exact semantic model P≤M before full parsing. Every result object key is an existing fixed field or ≤128-byte logical name: enforce decoded key UTF-8≤128 before slice/decode, raw token≤6*128+2=770, key scratch=(128+770)+(128+4*770)=4106. Other metadata/generic key rules are unchanged. Malformed structure remains subject to observed scanner guards.

Scan holds caller M + raw N + P_scan≤2M+5N plus bounded key/wrapper/context. Strict full decode holds caller M + parse M +5N. Final adoption holds caller M + parse M + final M +N, with one-record in-place validation and widened text released before final construction. No separate full validator, from_dict/freeze/thaw forest or fourth result. Real parser/wrapper/iterator/exception frame release is required before a fresh same-engine replay occupies a freed slot; caller and exact approved plan remain charged.

N≤B+221; result wrapper P=2416. Wrapper/key/header=12507 and shallow result context=3872, together 16379 within the COMMON pool above. Thus existing 3M+6B and already-charged record/fixed terms cover this branch without generic 3P_scan added atop caller M. No public budget permit or numerical-scratch borrowing. Actual shared-decoder integration/liveness tests are required before treating this arithmetic as executable proof.

### 12.5 Standalone and pre-plan route guards

Let H=source_base+2*A_held+Q_held from safely measured actual held file SourceSnapshot state, with its complete retained numeric union and Coordinate forest; before a future selection exists do not substitute imagined plan state. Initial inspect has no caller A/Q/Inspection; before retained raw acquisition fund actual file bytes+source MODEL_FIXED and all known state, including mutable/final raw overlap if used. Each lexical/key allocation has its current-live guard; exact forest-free model P then supplies Inspection/source_base before full decode and is checked again after adoption.

Let K_route(W)=RUNTIME+H+CONTROL+3*SERIAL_BUFFER+MODEL_FIXED+W. This route-local K is distinct from §8's one-record K. Let R_recipe be the projected exact retained caller/extracted Recipe (written R below), P_saved the safely observed saved primitive/model tree (including recipe), L the explicit caller raw saved-plan length, and D(N,P_scan)=5N+3P_scan. W0=1434532; N0=8375; 965*N0=8081875. All complete totals are ≤536870912 before the allocations they authorize. Raw read staging is admitted independently; release mutable raw staging before widened decode.

Initial inspect uses K_route(W0)+max(965*N0,D(return_metadata)) once exact prospective Inspection P is available. Prepare/compile use K_route(W0)+R+max(965*N0,D(return_metadata)); R is outside the maximum even if a returned plan can borrow it. Validate current input owners/Recipe, capture original digests, run one worker, receive bounded control and return from its helper, then inspect the 24-byte API header/kind/raw length/local metadata projection and existing cap before retaining raw bytes. Lexical guards precede full D admission. No future unit graph, returned estimate or unconstructed plan is a permit. After closed plan reconstruction, freshly rederive canonical semantics/resources and also require complete canonical call total+R before final adoption.

File load_plan initially requires K_route(W0)+L+D(L,P_scan,saved). R extraction additionally requires full D+R until the adoption helper actually returns; merely deleting a local is insufficient. Thereafter its single api_compile bootstrap requires K_route(W0)+L+P_saved+R+max(965*N0,D(return_metadata)). At every later canonical transition require fresh complete canonical call total+L+P_saved+R. L includes accepted whitespace up to the unchanged 16 MiB raw cap and remains charged through return. Remove P_saved/R only after exact saved/returned semantic/resource-binding/derived-estimate comparison and actual reference/frame release; retaining all charges until return is valid. Saved estimates never fund recomputation.

Public CallAdmission remains exactly baseline+X+C for its own declared plan/source/result arguments. It has no raw saved-plan or Recipe parameter. A route may correctly refuse because its named extra live arguments exceed the combined budget even when that separate diagnostic reports admitted. No forged partial CallAdmission exists before a plan, and no extra temporary guard may replace/subtract a canonical term.

### 12.6 Corrected source-only api_verify bootstrap

Use K_route(W136), W136=2913396, with actual H and all original bundle/path/child state. The fixed BundleVerification model has J/P=7087/13928; its exact metadata wrapper gives N≤7345 (including LF), P≤16368, arrays empty/raw length zero. Hence 17*N+3*P=173969, below 965*N0=8081875. Enforce this local bound before raw allocation; invalid schema/context is invalid_worker_response, never fabricated check success.

Python verify first performs API-SCHEMAS §19's ordinary plan.json-only bootstrap to validate caller identity/phase. Let Np/P_scan,p be actual bounded plan raw/lexical counts. Before Recipe/selection reconstruction require:

K_route(W136)+D(Np,P_scan,p)+R+2*Smax≤512 MiB.

Smax=79640 projects {source:SourceIdentity,variables:[name*64],dimensions:[name*16],row_dims:[name*16],plan_sha256:digest}, name≤128 UTF-8. P(source)=2024, P64names=49664, each P16names=12800, digest=384, root container=1152 and root keys=816. Sum=79640. Two occurrences explicitly pay construction/validation and final summary plus smaller bounded S/D builders/header scratch; no alias credit or descriptor clone. R remains additive during full D. This projection is private accounting, not a new wire schema.

The complete sequential guard is:

K_route(W136)+max(D(Np,P_scan,p)+R+2*Smax,965*N0,D(verification_metadata))≤512 MiB.

Every phase admits its own raw/key/scan allocations before use. Unlike load_plan, there is no explicit caller raw-plan argument: these controlled read bytes may release at the actual helper-frame boundary. Before worker launch, release raw/plan/Recipe/selection/builders/summary/copied fields/iterators/error frames; only original plan digest survives inside its funded child ledger. Any extra retained state must stay outside the maximum or refuse. Recheck original FD/entry before launch and after completion; verified worker plan_sha256 must equal the original. No new expected-plan wire field, refreshed hash authority, parent native/manifest/result parse, filesystem lock or atomic snapshot claim. Bootstrap marks no semantic verification check passed. Worker-side source/runtime/plan/replay has its own fresh complete budget, not a hypothetical second parent allowance.
