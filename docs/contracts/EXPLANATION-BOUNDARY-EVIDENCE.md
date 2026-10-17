# Supplemental explanation byte-boundary design

Status: frozen design and tests pending checkpointed execution. This adds no product behavior, schema, resource formula or ceiling. The candidate08 product is unchanged. The approved API-SCHEMAS section 8, RESOURCES sections 1, 2 and 7, and PLAN stage F govern.

## Evidence scopes

The existing actual admitted-source journey reaches 8,386,002 bytes and observes the first global stop with complete section counts. It establishes practical near-cap behavior. The B2 prefix arithmetic case is scalar arithmetic only. Neither is an exact 8 MiB equality/+1 product test.

The supplemental tests distinguish two scopes. The mandatory-skeleton result below is an analytical upper bound over every valid schema shape. The byte-boundary journey uses genuine eager datasets, SourceSnapshot, BoundPlan, ComputationResult, real A/B/C admission, stock Pint qualification and exact same-engine replay. Its later constructor checks concern valid standalone explanation structures and do not claim independent numerical or source verification.

## Finite mandatory-skeleton upper bound

A valid mandatory metadata-only skeleton cannot reach 8 MiB under the accepted finite domain. A conservative componentwise J upper bound is 5,081,142 bytes, including final LF, leaving 3,307,466 bytes below the unchanged 8,388,608-byte ceiling.

Use exactly RESOURCES section 2: J(string)=6U+2, J(number)=32, J(bool)=5, list punctuation=2+max(k-1,0), map punctuation=2+max(k-1,0), and each map entry adds J(key)+1+J(value). Bound names by 128 UTF-8 bytes, units by 512, stored labels by 4096, canonical measurement dtype spelling by 7 bytes, coordinate dtype by 6, and each digest by 64. Both fixed assurance and notice are shorter than the conservatively assigned 512 bytes. All count/index/value/scale/offset scalars receive numeric32; null alternatives cannot be larger.

Independently maximize every dimension list and map to 16 entries, columns to 32, and stages to 2 per column. This deliberately includes incompatible maxima, such as 16 final dimensions alongside 16 reduced dimensions; it is a safe upper envelope rather than a constructed valid plan. Give every column complete weight metadata and all three reasons. Every source/stage record list is empty. Hidden model byte counters are not serialized.

| Component | J upper bound in bytes |
| --- | ---: |
| Name | 770 |
| Unit | 3,074 |
| Name list of 16 | 12,337 |
| Index selector of 16 | 529 |
| SourceIdentity | 589 |
| Coordinate descriptor | 145 |
| Coordinates map of 16 | 14,673 |
| Stored key map of 16 | 405,601 |
| Source section, empty cells | 1,041 |
| Conversion metadata | 9,589 |
| Weight metadata | 16,644 |
| Stage section, empty records | 38,959 |
| Two-stage list | 77,921 |
| Column | 144,979 |
| Column list of 32 | 4,639,361 |
| Root with final LF | 5,081,142 |

The scalar test reconstructs these charges by the exact schema field names and asserts every component. This does not claim that an oversized valid skeleton was executed. The earlier invalid oversized-notice constructor fixture remains a malformed-input test, not mandatory-skeleton overflow evidence. The defensive product check remains intact for future schema/domain changes.

## Genuine exact byte-boundary journey

Use two distinct float64 measurement variables, v and vv, both physical shape (500,2), containing 1.0, with integer r coordinates 0..499 and two s labels of 4096 UTF-8 bytes each. Two mean columns reduce r and s to one row. Each variable has explicit raw unit metadata and exact recipe source/target assertions. Start with the stock unit spelling meter for both.

An initial real explanation with limit1000 measures its exact output size. Its displayed sections must be source1000/stage1/source984/stage0. The first column contributes four raw unit spelling occurrences: three conversion fields and its displayed support unit. The second contributes three conversion fields. Find bounded leading-space counts a,b, each0..507, such that 4a+3b fills the measured byte gap. Leading ASCII space is valid unit text; the already-qualified stock unit route receives it, and the original raw spelling remains bound. No parser, budget, estimate or runtime identity is patched.

A new genuine source/plan/result with those raw unit spellings must produce exactly 8,388,608 bytes, retaining the same source/stage counts. Check that SourceIdentity.size_bytes keeps the same decimal width. Each changing identity is a fixed-width 64-character hash. After the operation helper returns and releases its source/model frames, parse the output in test code and require the public standalone RowExplanation constructor to accept the exact same boundary and stream exactly that many bytes.

A third genuine journey changes only the second measurement name from vv to vvv. That adds one explanation metadata byte, while source/recipe/plan hashes remain fixed-width and the source-size decimal width is checked. The producer must omit precisely the last previously displayed source cell, yielding source1000/stage1/source983/stage0, with exact byte omissions. A plain observation wrapper counts source-cell construction and verifies only one prospective rejected cell is created, followed by the global stop.

After this helper returns, use the new explanation's own metadata/hashes and restore its actual next physical source cell at ordinal983: indices[491,1], labels[491,second s label], raw/converted1.0, raw_weight null, normalized_weight1.0, no exclusion. Adjust shown and byte_omitted together. This is a locally coherent standalone prefix exactly 8,388,609 bytes. An independent test-only stdlib JSON scalar stream counts UTF-8 bytes with final LF, without building a whole Unicode document. The public constructor must refuse explanation_bytes_limit before its first owned-tree adoption.

Each full actual journey ends before the next. Only scalar observations cross the first helper boundary; output bytes cross the second and third. Dataset/source/plan/result handles are not retained for the standalone checks. Those test-only JSON trees are not product admission authority. Candidate source/tests/manifests and modes must be durably checkpointed before executing the stock unittest command on both actual public interpreter profiles.
