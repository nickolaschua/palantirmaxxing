# Explanations

**Planned module; no feature implementation exists.** This folder reserves a boundary for turning authoritative PEC results into structured, deterministic explanations. The [explanation-record planning specification](../../docs/specifications/pec-explanation-record.md) records responsibilities, available evidence, unresolved decisions and the future implementation sequence. It is not a final payload contract.

The future module may package recorded zone contributions, associate facts with episode/event/zone IDs, distinguish known-area subtotals from complete totals, explain overlapping-event metrics, and attach matching provenance, assumptions and calculation settings. If the frontend needs text, it may produce deterministic factual text from recorded results.

It must preserve PEC values, statuses and null semantics, keep unrounded values authoritative, and remain independent of presentation layout. It must not independently recalculate exposure, alter results, invent causal claims, or use an LLM to invent explanations. It cannot claim casualties, building occupancy or real-world hazard validity.

## Boundaries

- [Exposure](../exposure/exposure.md) owns validation, geometry algorithms and calculation. Additional calculated information requires an explicitly agreed extension there; explanations consume authoritative outputs.
- [Data sources](../data_sources/data_sources.md) owns acquisition, eligibility and source provenance. Matching reference artifacts may enrich facts; they must not replace eligible calculation data.
- [Orchestration](../orchestration/orchestration.md) owns loading, execution and result packaging/persistence; [API](../api/api.md) owns future transport. This folder does not duplicate those responsibilities.
- [Contracts](../../contracts/contracts.md) owns final versioned interfaces. The planning specification defines no final explanation schema.
- The [frontend](../../frontend/frontend.md) owns layout, interaction and display formatting. Its [PEC handoff](../../docs/specifications/pec-frontend-handoff.md) contains suggestions, not settled product requirements.

No adapter, classes, endpoints, storage mechanism, geometry exports or frontend components are introduced here.
