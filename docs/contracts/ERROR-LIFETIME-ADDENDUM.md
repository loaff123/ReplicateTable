# Owned error lifetime clarification

Status: newly authored reconstruction clarification of the approved source and unit boundary policy. No serialization, numerical rule or resource ceiling changes. Independent implementation review remains required.

## Scope and observable diagnostics

A source or stock-unit operation owns temporary arrays, labels, graph nodes and parser/conversion state created within that operation. On an escaping failure or cancellation, those objects must not remain live solely through the escaping exception's traceback, context or cause links. A narrow operation wrapper may detach these links using the exact qualified BaseException descriptors before reraising the same exception object. The exception type, identity, refusal code and cancellation classification are preserved. The wrapper's newly attached traceback frame must itself contain no buffer-bearing locals or arguments from the owned operation.

This intentionally removes detailed internal traceback and chained-error diagnostics at that boundary. Bounded outward classification and consequential commit/cancellation status remain truthful. The implementation does not walk arbitrary caller frames, traverse the heap, invoke custom exception setters, call global garbage collection or change caller GC settings. It does not strip unrelated exceptions outside the owned operation boundary. A cleanup/restoration fault cannot replace an already escaping primary refusal or cancellation; the private unit state is poisoned when restoration cannot be established, while the primary exception remains primary.

Tests retain escaping exceptions and cancellation objects after the operation, check exact type/identity/code, zero custom setter hooks, and release of newly allocated owned buffers on both public profiles. These tests do not establish a bound on all caller-owned memory or adversarial concurrent mutation.

## Finite initial stock-callable checks

Before the first private Pint registry/parser calls, the implementation checks the finitely named stock constructor, tokenizer aliases, stock preprocessing functions and tree builder using the pinned profile's exact safe type, alias and primitive metadata rules. Ordinary incompatible replacements refuse before they are invoked. Pint UnitRegistry uses the exact named stock RegistryMeta metaclass on the selected profiles; a blanket type(factory) is type check is incorrect. Class metadata must be inspected without invoking replacement factories or user conversion hooks. Only exact built-in strings may participate in metadata comparison.

This bounded named-stock profile is not bytecode attestation, MRO exploration or a hostile in-memory replacement defense. Existing exact runtime binding and trusted quiescent process assumptions remain in force. No caller registries, custom definitions or contexts are admitted.
