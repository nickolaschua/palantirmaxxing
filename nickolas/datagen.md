# Dataset reproducibility and audit plan

Status: the deterministic pool generator, resumable artifact writer, strict
loader, and integrity verifier are implemented. Both planned releases are
complete and verified. `sg2-pilot-512-v1` has 512 distinct canonical hashes,
512 distinct substantive hashes, and manifest checksum
`sha256:c76f63f056f1dffbba090d720c48f3d2a1953d446e8e55c2f7c183b32d810495`.
`sg2-training-10000-v1` has 10,000 distinct hashes at both layers and manifest
checksum
`sha256:72c0911b584fca06d37952e2a0bedfc8d27b7808ff12d87e318cf55fc26ee31c`.
Verification regenerated one record from every profile in each release.
Scenario mechanics remain defined by the checked Singapore v2 distribution.

The independent canonical distribution audit also completed: 1,000 of 1,000 episodes regenerated deterministically, no generation failures or silent exclusions occurred, and every frozen Goldilocks gate passed. This audit is development evidence about the declared synthetic distribution; it is not an RL performance result.

## Concrete generation sequence

The practical sequence is:

1. Generate and verify a 512-scenario pilot pool. The supported first-pilot range is 512–1,000; this repository uses 512 as the initial release so failures are cheaper to diagnose.
2. Use that pool for the tiny-overfit and 50k generalization experiments only after verification passes.
3. Generate a 10,000-scenario training pool while those experiments run.
4. Expand to 25,000 only if a measured training–validation gap indicates memorization.
5. Add a 5–10% live-generation lane only if validation evidence shows that the fixed pool lacks diversity.

The 512-scenario release uses the same declared mixture as the 1,000-scenario scenario audit: 52 warmup records and 92 records for each of balanced, full-standard, burst-contention, low-slack, and consequence-contrast. The 10,000-scenario release scales that mixture to 1,000 warmup records and 1,800 records for each other profile. OOD profiles stay outside the training pool.

Generate or resume the pilot with:

```bash
.venv-rl/bin/python scripts/generate_scenario_pool.py \
  --release-id sg2-pilot-512-v1 --count 512 --workers 6 --resume
```

Verify every artifact and both checksum layers with:

```bash
.venv-rl/bin/python scripts/generate_scenario_pool.py \
  --release-id sg2-pilot-512-v1 --verify
```

The corresponding large-pool commands are:

```bash
.venv-rl/bin/python scripts/generate_scenario_pool.py \
  --release-id sg2-training-10000-v1 --count 10000 \
  --seed-start 1000100000 --workers 10 --resume
.venv-rl/bin/python scripts/generate_scenario_pool.py \
  --release-id sg2-training-10000-v1 --verify
```

The release lives under `data/scenarios/rl/pools/<release-id>/`. Generation checkpoints each completed episode in `progress.json`; finalization replaces that progress state with an immutable, checksummed `manifest.json`.

The initial release records 2,032 rejected deterministic attempts before its 512 accepted records. Accepted episodes span 2–8 active threats and 3–8 interceptors. All eight ingress sectors are represented. Two cells in the bounding-box-based 4×4 terminal grid have zero accepted detections; that observed gap is retained in the manifest rather than hidden by a balanced marginal claim. The release was generated from a dirty working tree, so its manifest pins SHA-256 checksums for the generator, distribution, provider, scenario serializer, and boundary source in addition to the Git revision.

The 10,000 release records 40,655 rejected deterministic attempts before its
accepted records. Its exact profile counts are 1,000 warmup and 1,800 for each
of the other five core profiles. It spans 2–8 threats, 3–8 interceptors, all
eight ingress sectors, and retains the same two empty bounding-box terminal
cells. Its failure history contains one `KeyboardInterrupt` at record 4,054 from
an operator-requested worker-count change; resumable generation then produced
and verified that record normally. This interruption is preserved as provenance
and is not a rejected scenario or a missing artifact.

## Pre-generated datasets and overfitting

A fixed dataset can make repeated experiments reproducible and avoid regenerating identical inputs. Reusing it does not automatically imply overfitting, and generating inputs online does not automatically prevent overfitting. Generalization depends on coverage, independence of evaluation data, repeated exposure, and how often evaluation results influence development.

Keep the following uses distinct:

| Dataset role | Purpose | Interpretation |
| --- | --- | --- |
| Diagnostic fixtures | Inspect loading, serialization, and reproducibility | Passing these checks establishes infrastructure correctness only |
| Development data | Support iterative development | Results may be influenced by repeated inspection |
| Validation data | Compare development decisions | Repeated use makes this part of model selection |
| Held-out test data | Assess a frozen final candidate | Do not use results to tune that candidate and still call them held out |
| Distribution-shift audit data | Examine explicitly different input distributions | Report separately from ordinary test results |

Dataset size alone is not evidence of diversity. Report the number of distinct content hashes, the number of related input families, and coverage of declared dimensions. A large collection of near-duplicates may provide little additional coverage.

## Versioned release manifest

Each release should have an immutable identifier and a manifest recording:

- Schema and generator versions, source revision, and generation configuration.
- Requested seed and realized seed when retries or substitutions occur.
- Stable record identifier, content hash, split membership, and relative artifact path.
- Generation attempts, rejected records, and reasons for rejection.
- Counts by declared category and a checksum of the complete release manifest.
- Any upstream source versions needed to reproduce the inputs.

Define canonical serialization before calculating content hashes. This implementation records two hashes: the canonical episode identity hash covers the complete serialized record, while the substantive content hash excludes the record ID, seed, release metadata, layout labels, and retry bookkeeping. It retains threat/interceptor states, detection times, candidate count, and operational metadata consumed by the simulator or consequence provider. Changing a filename or provenance field cannot hide duplicate simulator input; changing substantive input changes the content hash.

Publish corrections as a new dataset version. Preserve the old manifest so earlier results remain interpretable. Record any conditioning introduced by acceptance filters; the accepted collection represents that filtered distribution.

## Frozen splits and leakage

Assign split membership before development uses the records. Check content hashes across splits, and group related records together when they share a parent or derivation. Different random seeds alone do not establish independence.

Maintain a registry of training, validation, test, and manually inspected audit records. A record used to guide development should be marked accordingly. If inspection informs a change, do not subsequently describe that record as an untouched test example.

Identifiers, seeds, file paths, and split labels belong in provenance. Avoid treating incidental metadata as model input. Fit any learned preprocessing on the training split and preserve its fitted state with the resulting model artifact.

## Coverage record for reviewers

Maintain one table that makes the intended distribution and its limitations explicit:

| Field | What to record |
| --- | --- |
| Dimension | A plain-language name and definition |
| Support | Permitted categories or ranges, including exclusions |
| Intended coverage | Planned counts or proportions |
| Actual coverage | Measured counts and missing regions |
| Dependencies | Constraints and correlations with other dimensions |
| Rationale | Why the dimension belongs in the evaluation |
| Limitations | What the dataset cannot support claims about |

Report joint coverage where relevant. Balanced marginal counts do not guarantee that combinations are represented. Distinguish intentional difficulty restrictions from accidental gaps.

## Loading a specific record for audit

Use the dataset version plus record identifier to resolve an exact immutable artifact. The frontend should show that identity and content hash alongside the loaded record, and clearly report missing, corrupt, or incompatible artifacts. It should never silently substitute a newly generated record.

Keep audit selection separate from claims about an untouched test set. Record which examples were inspected and whether their inspection informed subsequent development.

## Verifiable data-integrity checks

The release-side checks below are implemented by the generator and verifier.
The frontend exact-loading row remains a separate integration check.

| Check | Procedure | Passing evidence |
| --- | --- | --- |
| Manifest consistency | Recount artifacts and category membership from the release | Counts equal the manifest; all references resolve |
| Round-trip integrity | Load and serialize representative records using the declared schema | Canonical content hashes remain equal |
| Reproduction | Regenerate a declared sample using its recorded versions and configuration | Canonical hashes match, or nondeterminism is explicitly documented |
| Split isolation | Compare content hashes and declared family identifiers across splits | No prohibited overlap; exceptions are explicit and justified |
| Corruption handling | Alter a copy of an artifact and attempt to load it | A checksum failure is reported; no substitute record is returned |
| Exact audit loading | Select known version/identifier pairs through the frontend | Displayed identity and hash match the manifest |
| Retry provenance | Inspect records generated after failed attempts | Requested and realized seeds, attempt counts, and rejection reasons are retained |
| Coverage accounting | Compare planned and observed category counts | Every shortfall is reported; no hidden omission |

Store results with the dataset release identifier and the checking tool's version. A failed check blocks labeling that release as verified; it does not justify rewriting the frozen release in place.

## Interpreting reuse

Track unique records visited and exposure counts as descriptive statistics. Approximate passes equal record visits divided by pool size only when visits are distributed uniformly; report the actual distribution when they are not.

Compare development and validation results using the same metric definitions and report uncertainty. An increasing gap can indicate overfitting, a distribution difference, or an evaluation defect; investigate before attributing a cause. Repeated selection against validation also limits the strength of generalization claims.

The companion [RL_experiments.md](RL_experiments.md) records the post-generation experiment order from the supplied screenshot.
