# Backend

Implemented Python functionality consists of offline Census 2020 preparation in [data_sources](data_sources/data_sources.md), standalone PEC v0.1 in [exposure](exposure/exposure.md), synthetic candidate generation in [planning](planning/planning.md), replaceable synthetic assumptions in [scenario](scenario/scenario.md), pure Pareto/category processing in [trade_space](trade_space/trade_space.md), and the static machine-side pipeline in [orchestration](orchestration/orchestration.md).

The thin PEC file command under `scripts/` loads inputs and writes exposure results. Static orchestration remains a reusable Python interface plus a deterministic benchmark fixture; it has no API transport, frontend coupling, service framework or database. See the [planning contract](../contracts/candidate-opportunities.md), [static-scenario contract](../contracts/static-scenario-evaluation.md), and [PEC specification](../docs/specifications/pec.md).

The planned [explanations module](explanations/explanations.md) will adapt authoritative PEC results into deterministic facts, without calculation, transport or presentation responsibilities. Its [planning specification](../docs/specifications/pec-explanation-record.md) records unresolved decisions; the feature remains unimplemented.
