# Specifications

The implemented [population preparation specification](population-data.md) documents source acquisition, eligibility and provenance. The implemented [PEC v0.1 specification](pec.md) documents standalone exposure mathematics, validation, numerical settings, execution and limitations. [Benchmark findings](pec-benchmark.md) record measured runtime and approximation sensitivity.

Payload formats belong in `contracts/`; system boundaries belong in `docs/architecture/`. Existing frontend scenario notes do not define PEC calculation behavior. Frontend connection, APIs and application orchestration remain future work.

The [PEC coverage investigation](pec-coverage-investigation.md) and adjacent JSON/PNG/SVG snapshots document the reproduced boundary-sensitive status change. These are diagnostic report artifacts, not new production output contracts.

The [PEC frontend handoff](pec-frontend-handoff.md) gives the Singapore Canvas owner current file integration points, metric and geometry semantics, suggested experience and outstanding verification questions. It does not prescribe visual design or claim frontend PEC integration is implemented.

The [PEC explanation-record plan](pec-explanation-record.md) records the future deterministic adapter boundary, existing output capabilities, missing geometry/information, pending product decisions and implementation acceptance criteria. It defines no final payload schema and implements no feature.

The [static machine-side MVP benchmark](static-mvp-benchmark.md) records the
scaled synthetic Phase A-G fixture, full candidate table, category evidence and
seven-run stage timing. Its values are test inputs, not operational estimates.
