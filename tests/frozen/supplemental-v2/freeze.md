# ReplicateTable supplemental numerical corpus: v2 code-only amendment

Status: FROZEN v2 CODE-ONLY AMENDMENT. The independent finite-amendment and projection review passed before this final manifest freeze and before candidate validation.

This is the public projection of `replicatetable-clean-rebuild-supplement-v1`, newly authored and frozen on 2026-10-06 before candidate-engine validation. It is supplemental evidence, not recovered historical bytes, product implementation, historical test qualification, or numerical proof for arbitrary inputs.

## V2 code-only amendment

This separately labeled projection applies the approved contract v5 correction to the unchanged v1 fixtures. Exactly one expected field changes: R15_weighted_second_stage.code is unsupported_later_stage_weights instead of invalid_recipe. The oracle and reproducible authoring source each change that one independent code mapping. All source fixture bytes, derivations, successful numerical values, exact rationals, 20 result rows, 72 support records and other refusal fields remain unchanged. Both original v1 projections and their manifests remain intact.

The approved API contract SHA-256 is 60c6a54084b679e680d021878e267d2138463e51bd054981210310bd84761371. Its later-stage rule applies to a valid common stage shape with a present valid missing policy, before requiring weighted-only fields or resolving weights. V5 also retains residual_dimension, duplicate_row_key, unapproved_broadcast, missing_unit_assertion and missing_stage_policy; none changes another existing supplemental case. In particular, reduced-coordinate duplicates stay duplicate_coordinate, and an incorrect nonnull unit assertion stays source_unit_mismatch. Missing-stage-policy and other precedence behavior is not newly tested by this finite amendment.

The fixture schema version, original corpus ID, descriptive phase labels and case IDs stay unchanged for byte preservation; the projection manifest identifies the v2 amendment. This remains a finite oracle rather than a general recipe parser. No candidate implementation was read/imported and no new numerical expectations were derived from an engine.

## Included files and verification

This standalone projection contains exactly seven files:

- `fixtures.json`: 35 explicit numerical, refusal and structural-model cases
- `expected.json`: complete expected results and exact rational companions
- `derivations.json`: case-by-case calculations and refusal rationales
- `author_cases.py`: reproducible hand-authored fixture/expectation source
- `oracle.py`: independently written scalar/Fraction verifier
- `freeze.md`: this public description
- `freeze_sha256.json`: the clearly labeled public-projection manifest

The five JSON/Python source artifacts are byte-identical to the newly frozen corpus. The documentation and manifest are specific to this projection. The manifest hashes exactly the six payload files, lists the full seven-file allowlist, and records the original corpus manifest's digest; a manifest cannot include its own digest without circularity. The public-projection manifest's digest is supplied separately with the export.

Run `python oracle.py --verify` in this directory. The verifier checks all 35 cases and every payload hash in the projection manifest. It requires only the Python standard library. There are 20 complete result rows and 72 support records. Running the verifier is a corpus self-check, not a candidate-engine or baseline pass.

## Independence

Expected per-group values, counts and reasons were hand-worked before candidate validation. `author_cases.py` does not import or call `oracle.py`; the oracle separately evaluates finite fixture semantics using `Fraction`, Python scalar binary64 arithmetic and `math`, with standard-library JSON/path/CLI/hash I/O. Neither imports NumPy, xarray, Pint, a candidate implementation, or runtime code. Candidate units, reducer and explanation implementations were not read or imported during corpus preparation. An independent corpus-only review found no remaining substantive issue before the freeze.

The corpus does not replace or modify the original feasibility corpus. Its S/R/M cases are newly authored and must not be described as recovered missing historical cases. Engine adapters and their validation results are separate evidence.

## Coverage

S01–S02 preserve exact int64/uint64 extreme values and row keys beyond 2**53, direct binary32 values, and signed zeros. S03 aligns percent weights by named dimensions despite differing physical orders. S04–S05 freeze one- and two-stage failure policies, valid versus positive-weight counts, complete reason ordering, and independent final-stage reasons. S06–S07 apply positive affine conversion before means/extrema and to direct output. S08 distinguishes direct NaN missingness. S09 checks opaque names and collision-free physical CSV headers.

R01–R22 cover absent/missing/duplicate reduced coordinates, invalid weights even at missing measurements, infinity, finite intermediate overflow, invalid stage/count/order, duplicate output names, exact unit assertions and incompatible weight dimensions. M01–M02 reject null direct integer outputs. M03 accepts a legitimate separately rounded support triple; M04 rejects an outside-envelope sum.

## Fixture encoding and adapter rules

An execute case contains a complete version-1 recipe and explicit data. `data.dimensions` gives dimension lengths, including deliberately absent coordinates. Coordinates contain `dtype` and physical-order `values`. Variables contain `dims`, exact `dtype`, raw `units`, and C-order flat `values`; derive their shape from dimensions, retaining scalar shape for empty `dims`.

Construct explicitly typed arrays. Keep all integer keys and values as exact integers; never infer them through float or coerce mixed output columns through pandas. In float arrays, JSON null represents a source NaN. The explicit `float_special` object with value `+inf` represents a deliberately refused infinity. In descriptor-only object coordinates, null is the missing coordinate element. Preserve signed zeros and absent coordinates. Fixture dtype aliases are construction requests; product schemas use canonical stored dtype representations.

A `result_mutation` case starts from the successful `base_case` result, applies the exact listed replacement paths, then tests public structural construction. Both value and reasons are altered to isolate direct integer nullability. A `support_model` case tests its exact record under the supplied stage policy in an otherwise legitimate one-stage weighted model. It does not prescribe source arrays, accumulation order, or a source-replay proof.

Refusal `phase` identifies the semantic boundary, not a private function name. The expected public `code` and `exit_code` are exact; arbitrary exceptions do not satisfy them. Header/model self-checks establish fixture consistency until an engine adapter exercises its actual serializer or constructor.

## Numerical semantics

Keys, scalar types, units, dtypes, counts, reasons, ordering, headers and direct integer values compare exactly. Direct signed zeros have explicit sign assertions. Exact companions are reduced rational strings. Computed float values and weight sums use absolute and relative tolerance 1e-12; tolerance cannot excuse an invalid type, missing result or changed integer/key.

Conversion is applied once to each finite source value before reduction. Percent weights normalize by 1/100 and align by dimension name. Finite zero-weight values count toward `n_valid`; positive-weight counts are separate. Failed intermediates are missing to the next stage, whose own policy determines final reasons. Applicable reasons remain in order: missing_values, insufficient_count, zero_weight.

Arithmetic uses unscaled float64 affine multiply/add, normalized weights, weighted products, sums and subsequent division. Every performed nonfinite intermediate from finite operands fails with numeric_overflow, even if a rescaled mathematical mean could be finite. The overflow controls distinguish converted-result overflow from product, numerator-sum, denominator-sum and second-stage intermediate overflow. The corpus does not prescribe deterministic accumulation grouping or promise an overflow-avoiding algorithm.

M03 retains the exact binary64 literals weight_total=10000000000000000.0, weight_valid=10000000000000002.0 and value=0.9999999999999998, with input=4, valid=3, positive-valid=3 and no reasons. It satisfies V≤T or `math.isclose(V,T,rel_tol=(n_input-1)*2**-52,abs_tol=0)`. M04's valid sum 10000000000000032.0 exceeds that envelope. Do not clamp, replace, or impose an exact subset identity on independently rounded sums. These are structural-admission cases, not mandated output triples for every reducer.

## Freeze identity and limits

Original newly frozen corpus manifest SHA-256:
`b5a26c0a9f518c3c7455504f6194d058b7ae7693fc8397b3a7236667d5848228`

Unchanged fixture SHA-256:
`53d4180f65c13c043139c4845a43396ea84e5706b78de36398a904688564626f`

Amended expected-result SHA-256:
`94911607947340172e6ed4656fd6f0d939e32aa5e7fa416bc5657f89b552e3e2`

Amended oracle SHA-256:
`ff41ba50b346da09d80214704a4bb6840eab6f1b977f7d8e97273a5c371ebdd7`

Any later payload change requires a labeled amendment and new hashes before renewed affected validation. This finite corpus claims no broad fuzzing, performance, runtime-binding, source-lifetime, persistence, explanation, browser, release, or arbitrary-input qualification.
