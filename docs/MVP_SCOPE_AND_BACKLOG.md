# Engagement Planning Prototype — MVP Scope and Post-MVP Backlog

## 1. Core research question

The MVP investigates:

> Given a predicted trajectory for a high-speed aerial threat, can a machine rapidly identify feasible future intervention opportunities and show that different intervention locations can produce materially different population exposure while retaining similar supplied mission-success estimates?

The MVP is intended to validate the decision-support concept.

It is not an operational interceptor model and does not claim to predict real interception performance or physical debris behavior.

---

# 2. MVP scope

Machine-side Phases A-G are implemented and covered by deterministic synthetic
tests. Frontend integration and every capability in the post-MVP backlog remain
out of scope.

## Threat

The MVP contains one generic high-speed aerial threat.

The threat has a deterministic predicted 2D trajectory.

Inputs include:

- Initial position.
- Speed.
- Heading.
- Predicted trajectory.
- Maximum time-to-go.

The trajectory does not change during an MVP episode.

---

## Interceptor

The MVP contains:

- One interceptor class.
- One synthetic launch location.
- One initial heading.
- Fixed interceptor speed.
- Configurable maximum turn rate.
- A bounded-curvature 2D kinematic model.

No detailed aircraft dynamics are modelled.

Reachability is determined using a simplified bounded-curvature representation rather than Euclidean distance alone.

---

## Candidate opportunities

The threat trajectory is sampled at 50 future points by default.

Each sampled point represents a potential engagement opportunity.

All future samples are retained as candidates, including those that are unreachable under the simplified kinematic model. Each record preserves the bounded-curvature path length, required travel time, time margin and reachable flag so later stages can inspect exclusion evidence rather than losing it.

The number of candidate samples must remain configurable so it can be increased later.

---

## Mission-success estimate

Each feasible candidate receives an externally supplied success probability.

The MVP does not derive success probability from flight dynamics, seeker performance, guidance, or target type.

The supplied success probability is treated as an exogenous input.

The MVP uses the configurable synthetic profile:

\[
p(t)=\operatorname{clip}(p_0-\alpha t,p_{\min},p_{\max})
\]

with `minimum <= initial <= maximum` and a nonnegative decrease rate. Default
fixture values are `0.97`, `0.004/s`, `0.70`, and `1.00`. These values only
exercise the trade-space and are not calibrated to any real interceptor.

---

## Geographic footprint

Each reachable candidate receives a supplied circular footprint.

For MVP:

- Footprint center equals candidate engagement position.
- One fixed footprint radius is used.
- Footprint radius is a scenario assumption.

The Population Exposure Calculator evaluates the supplied footprint.

The footprint is not claimed to be a prediction of a real debris field.

---

## Population exposure

The existing Population Exposure Calculator returns:

> Estimated people potentially exposed within the supplied footprint.

Population exposure is deterministic under the current model assumptions.

It is not a casualty, injury, or fatality estimate.

---

## Candidate representation

Each reachable evaluated candidate contains:

- Opportunity ID.
- Time from episode start.
- Engagement position.
- Reachability status.
- Required travel time.
- Supplied success probability.
- Footprint ID.
- Footprint radius.
- Population coverage status.
- People potentially exposed.
- Known-area exposure and covered-area fraction.
- Explicit eligibility and ineligibility evidence.
- Dominance and pairwise numerical-equivalence evidence.

All original opportunities, including unreachable records, remain separately
available for traceability.

---

## Pareto filtering

For MVP, candidates are compared on two primary dimensions:

1. Higher supplied success probability is preferable.
2. Lower population exposure is preferable.

Candidate A dominates Candidate B when:

- A has equal or higher supplied success probability; and
- A has equal or lower population exposure; and
- at least one of those comparisons is strict.

Dominated candidates are removed from the decision frontier.

No arbitrary weighted mission-versus-population score is required for MVP.

Probability comparison uses an absolute `1e-12` tolerance. Exposure comparison
uses `max(1e-9 people, 1e-12 * max(abs(a), abs(b)))`. Values equivalent within
both tolerances remain Pareto-efficient; direct equivalent-candidate IDs are
retained for later presentation handling.

---

## Representative recommendations

The backend should not automatically select one universally "best" candidate.

Instead it should return the Pareto-efficient set plus up to three representative alternatives:

1. Earliest viable opportunity.
2. Highest supplied success probability.
3. Lowest population exposure.

Category assignments are retained even when one candidate owns several
categories. A separate representative list contains each assigned candidate ID
once in category order; no extra ranking rule forces three distinct choices.

These are descriptive categories, not automatic engagement decisions.

The human-facing system retains go/no-go authority.

---

## Dynamic behavior

The MVP is static.

It assumes:

- No target-course change.
- No new target.
- No updated detection.
- No interceptor failure.
- No failed engagement requiring replanning.
- No continuous recomputation.

Dynamic replanning is post-MVP.

---

## Performance objective

Target:

> Evaluate approximately 50 candidate opportunities and produce the Pareto frontier and representative recommendations in less than 100 ms on the development machine.

The complete backend pipeline is benchmarked with prepared population outside
timing, one warm-up, seven measured runs and `perf_counter_ns`.

Break down timing for:

- Trajectory sampling and reachability.
- Synthetic-success enrichment.
- Supplied-footprint construction and population exposure assessment.
- Pareto filtering.
- Representative-category extraction.
- Total end-to-end computation.

---

# 3. Calculated values and explicit MVP assumptions

Calculated by the implemented backend:

- Future trajectory samples.
- Free-terminal-heading bounded-curvature reachability.
- Population exposure for supplied footprints.
- Complete-coverage recommendation eligibility.
- Success/exposure Pareto frontier.
- Earliest, highest-success and lowest-exposure category extraction.

The following parameters are deliberately synthetic or externally supplied:

- Threat trajectory.
- Interceptor speed.
- Interceptor maximum turn rate.
- Success probability.
- Footprint radius.
- Maximum engagement time.
- Interceptor launch position.

These values must not be represented as validated operational parameters.

The deterministic end-to-end fixture deliberately uses scaled values including
a 1,000 m/s threat, 10,000 m/s interceptor, 500 m footprint radius and synthetic
population rectangles. Scaling preserves the tested Phase A-C reachability
pattern and exercises a low-to-high-to-lower exposure path. None of these values
is an operational performance estimate.

---

# 4. Post-MVP backlog

The following capabilities are intentionally postponed.

## 4.1 Multiple interceptor classes

Increase from one interceptor type to three.

Each class should eventually have different:

- Speed.
- Normalized cost.
- Accuracy / success characteristics.
- Potentially maneuverability.

The planner should then be able to compare not only different engagement times but different interceptor types.

---

## 4.2 Interceptor resource cost

Introduce explicit resource cost:

\[
C_i
\]

for each interceptor class.

Future trade-space dimensions may therefore include:

- Mission success.
- Population exposure.
- Resource cost.

Resource scarcity and reserve value may also be explored later.

---

## 4.3 Multiple launch sites

Allow more than one synthetic interceptor launch location.

The candidate-opportunity generator should therefore be designed so launch origin is an input rather than a global constant.

---

## 4.4 Refined turn-rate and maneuverability model

The MVP maximum-turn-rate parameter is synthetic.

Post-MVP work should investigate a better-grounded kinematic model.

Potential improvements include:

- Speed-dependent turn-rate constraints.
- Minimum turning radius.
- Acceleration limits.
- Heading-dependent reachability.
- More realistic bounded-curvature trajectory generation.

Do not move directly to full 6-DOF aircraft dynamics unless evidence shows it is necessary for the planning decision.

---

## 4.5 Refined engagement deadline

The MVP uses a supplied maximum engagement time.

Later this should depend on threat state and mission geometry.

Possible inputs include:

- Threat speed.
- Threat trajectory.
- Defended-zone boundary.
- Time until protected-region entry.
- Required remaining response margin.

---

## 4.6 Derived success-probability model

MVP success probabilities are supplied externally.

Later:

\[
p = f(
\text{interceptor type},
\text{target type},
\text{geometry},
\text{timing},
\text{uncertainty}
)
\]

may replace the supplied fixture values.

This model must remain separately validated and inspectable.

The recommendation engine should not need architectural changes when the probability model is replaced.

---

## 4.7 Multiple threat types

The MVP uses one generic high-speed threat.

Later introduce several threat categories.

Threat type may affect:

- Predicted motion.
- Mission consequence.
- Suitable interceptor class.
- Supplied success probabilities.
- Geographic footprint model.

---

## 4.8 Threat-dependent footprint model

MVP uses one fixed circular footprint radius.

Later the supplied footprint should depend on the incoming threat or an external physical-consequence model.

Potential inputs may include:

- Threat type.
- Threat speed.
- Engagement state.
- Other validated physical parameters.

The Population Exposure Calculator must remain separate from this physical model.

PEC evaluates the supplied geometry; it does not predict it.

---

## 4.9 Non-circular footprints

Future footprint representations may include:

- Ellipses.
- Polygons.
- Directional footprints.
- Raster hazard fields.

Population exposure semantics should remain explicit if hazard intensity is introduced.

---

## 4.10 Dynamic trajectory updates

Later versions should handle changes in the observed threat state.

When trajectory changes:

1. Update world state.
2. Regenerate future candidate opportunities.
3. Recompute reachability.
4. Recalculate affected footprints/exposure.
5. Recompute Pareto frontier.
6. Update human-facing recommendations.

---

## 4.11 Event-triggered replanning

Potential future triggers include:

- Threat heading change.
- Threat-speed change.
- Updated tracking estimate.
- New threat detected.
- Interceptor unavailable.
- Failed engagement.
- Population or geographic constraint changes.

Replanning should preferably be event-triggered rather than recomputed unnecessarily every simulation tick.

---

## 4.12 Multiple simultaneous threats

The MVP contains one threat.

Later versions should support multiple incoming threats.

This changes the problem from candidate filtering to a true assignment/resource-allocation problem.

A future decision variable may resemble:

\[
x_{ijk}
\]

where:

- \(i\) = interceptor,
- \(j\) = threat,
- \(k\) = engagement opportunity.

At that stage, mixed-integer optimization or another assignment method may become appropriate.

---

## 4.13 Interceptor allocation and reserve management

With several threats and interceptor classes, later versions should consider:

- Which interceptor handles which target.
- Whether an interceptor should remain unused.
- Whether scarce high-capability interceptors should be reserved.
- Resource conflicts between simultaneous engagements.
- Reallocation after failed attempts.

This is outside MVP.

---

## 4.14 Human-configurable constraints

The MVP does not require human-adjustable planning policy.

Later versions may support:

- Minimum acceptable supplied success probability.
- Maximum population exposure.
- Prohibited geographic areas.
- Resource-use limits.
- Minimum reserve levels.
- Minimum classification confidence.

These constraints should be explicit rather than embedded in opaque weighted scores.

---

## 4.15 Human-supervisory integration

The team is separately developing the human supervisory interface.

Future backend integration should supply structured evidence including:

- Candidate time/location.
- Mission-success estimate.
- Population exposure.
- Geographic footprint.
- Why a candidate appears in a representative category.
- Relevant alternatives.
- Data coverage.
- Assumptions.
- Provenance.
- Replanning events.

The machine should remain auditable and should not require an LLM to invent decision rationales.

---

# 5. Architectural principles to preserve

## Separation of models

Maintain clear boundaries between:

1. Threat-state / trajectory estimation.
2. Interceptor reachability.
3. Mission-success estimation.
4. Physical consequence / footprint generation.
5. Population exposure calculation.
6. Trade-space filtering.
7. Human-facing presentation.

Each module should own one type of claim.

---

## Do not overclaim realism

A sophisticated simulator does not validate its assumptions.

The system should explicitly identify which values are:

- measured;
- externally supplied;
- synthetic;
- calculated;
- derived from validated data.

---

## Prefer replaceable models

MVP approximations should sit behind stable interfaces.

Future validated models should be replaceable without rewriting:

- PEC,
- Pareto logic,
- dashboard contracts.

---

## Maintain human authority

The machine-side prototype should present meaningful alternatives and evidence.

It should not imply that population exposure and mission success can always be collapsed into one universally correct automatic decision.
