# Violation analysis and next experiment

Date: 2026-09-26

## What a violation means

Every validation violation in this campaign has termination reason
`constraint_violation:unhandled_threat`.

This is not an invalid discrete action. The environment's action mask ensured
that each selected assignment, cancellation, or advance action was legal in the
current state. The violation occurs later, when the event queue reaches a
threat's expiry time and that threat is still active rather than successfully
intercepted. The consequence provider evaluates the unhandled threat, records a
hard constraint violation, and immediately terminates the episode.

At the policy level, the failure means the sequence of individually legal
actions was globally unsafe. The learned policy either advanced while a visible
threat still needed coverage, selected or retained an assignment that consumed
a resource needed elsewhere, or reached a state where the remaining threats
could no longer be matched to the remaining interceptors. The aggregate
evaluation report does not retain action-by-action traces, so the exact branch
must be established by replaying each failed episode with the rollout recorder.

The online naive comparator completed all 64 validation episodes without a
violation. Therefore these failures are attributable to learned action
selection rather than infeasible validation scenarios.

## Validation breakdown

| Candidate | Violations | Profiles containing violations |
| --- | ---: | --- |
| Behavior cloning | 7/64 | balanced 1, consequence-contrast 2, full-standard 4 |
| DAgger 1 | 12/64 | balanced 5, burst-contention 1, consequence-contrast 2, full-standard 4 |
| DAgger 2 | 17/64 | balanced 2, burst-contention 1, consequence-contrast 1, full-standard 9, low-slack 4 |
| DAgger 3 | 6/64 | balanced 2, consequence-contrast 1, full-standard 3 |

DAgger round 3 failed on:

- `singapore-v2-balanced-0000010003`
- `singapore-v2-balanced-0000010007`
- `singapore-v2-consequence-contrast-0000010062`
- `singapore-v2-full-standard-0000010019`
- `singapore-v2-full-standard-0000010024`
- `singapore-v2-full-standard-0000010025`

`singapore-v2-balanced-0000010003` failed under behavior cloning and every
DAgger round. Round 3 fixed four of the original BC failures, retained three,
and introduced three different failures. This shows that aggregation moved the
error surface rather than enforcing safety.

## Why DAgger became unstable

The residual expert can label a student-visited state only while an exact
completion still exists for every unresolved threat and remaining interceptor.
The campaign recorded the following states after the student had already made
the episode impossible to complete exactly:

| Collection round | Student-visited states | States with no exact residual completion | Training-pool violating rollouts |
| --- | ---: | ---: | ---: |
| DAgger 1 | 13,050 | 390 | 41/512 |
| DAgger 2 | 14,804 | 830 | 91/512 |
| DAgger 3 | 18,915 | 1,559 | 150/512 |

Those irrecoverable states receive no corrective label. As the student visits
more of them, ordinary DAgger aggregation cannot teach the decision that should
have been made earlier to avoid the dead end. This is consistent with rounds 1
and 2 becoming less safe even as the supervised datasets grew.

## What to do now

Do not open the 256-case held-out suite, expand the scenario pool, or add more
flat PPO/DAgger compute. Freeze this campaign as `experimental-not-promoted` and
keep `naive-launch-on-detection/1` as the operational policy.

The next experiment should be `structured-imitation-safety-shield-v1`:

1. Replay the six DAgger-3 violations and the corresponding naive-policy runs
   with full action traces. Record the first action where they diverge and
   classify it as unsafe advance, resource-stealing assignment, unsafe retained
   tentative assignment, or another observed cause.
2. Add an observation-time safety shield before executing the learned action.
   It must use only currently detected threats, current masks, candidate
   eligibility, assignment status, deadlines, and remaining interceptors.
3. Reject `ADVANCE_ACTION` whenever a visible unassigned threat has a valid
   assignment available.
4. Reject assignments and cancellations that leave the currently visible
   unresolved threats without a one-to-one feasible matching to remaining
   interceptors. Use a deterministic bipartite feasibility check, not a learned
   estimate.
5. When the learned choice is rejected or no shield-approved learned choice
   exists, choose the same earliest-valid online action used by
   `naive-launch-on-detection/1` and record the fallback reason.
6. First require all six previously failing episodes to terminate normally.
   Then evaluate all 64 frozen validation episodes against both unshielded
   DAgger 3 and the online naive comparator.

The shielded candidate advances only if it has 64/64 normal completions, zero
constraint violations, at least 60% wins, at least 5% mean improvement, a
favorable 95% bootstrap interval excluding zero, and decision-path p95 below
100 ms. If any gate fails, keep the naive policy and leave held-out sealed.

## Decision

The learning result is promising but unsafe. The immediate engineering target
is deterministic safety around the learned cost-sensitive scorer. The next
research target is preventing irrecoverable states before they occur, rather
than asking the residual expert to repair them afterward.
