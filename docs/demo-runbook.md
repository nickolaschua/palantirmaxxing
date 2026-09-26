# Deterministic policy demo runbook

This is the short, rehearsed fallback demo for the policy pipeline. It exercises
the real browser, Vite proxy, backend job queue, simulation exporter and result
publication path. It does not depend on a new reinforcement-learning training
run.

## Start and preflight

From the repository root:

```sh
.venv-rl/bin/python scripts/run_integration_mvp.py
```

Open the printed `?basemap=plain` URL. Wait for **Rehearsed policy demo** to show
`sg2:validation:000000`. This immutable validation scenario is the golden demo
case: profile `balanced`, seed `10000`, six threats.

Before presenting, keep the launcher running and execute the browser rehearsal:

```sh
npm --prefix frontend run test:demo -- 'http://127.0.0.1:5173/?basemap=plain'
```

The command must finish with `"status": "passed"`. It runs the same three
numbered buttons through the real HTTP job pipeline. This is an intentionally
headless preflight check; it is not the presentation itself.

## The 60-second presentation

In the visible frontend, use the numbered buttons in order. Each button pins the
golden scenario, selects the policy, submits the backend job and automatically
starts a 12× map replay with moving threats and labelled intercept points.

| Step | Button | Expected live result | What to say |
|---|---|---:|---|
| 1 | **1 · Naive** | cost **2.464**, 6 intercepted, 0 unhandled | “This is the deterministic online fallback: launch on detection.” |
| 2 | **2 · Exact** | cost **0.447**, 6 intercepted, 0 unhandled | “This is a clairvoyant offline reference, not a deployable policy.” |
| 3 | **3 · Imitation** | cost **0.447**, 6 intercepted, 0 unhandled | “The observation-only imitation checkpoint matches the reference on this pinned case and beats naive by about 81.9%.” |

The green **LIVE BACKEND POLICY RUN** strip and scenario/policy identities are
the authoritative output of each click. The right-hand outcome panel is labelled
**BUNDLED RETROSPECTIVE · NOT THE LIVE RUN** and should be described only as a
separate narrative visualisation.

Typical local completion is roughly 4 seconds for Naive/Exact and 5–6 seconds
for Imitation. Wait for `succeeded` before moving to the next step.

## Claims and boundaries

- Lower ordinal cost is better.
- The Exact result has full-episode information and is only a benchmark.
- The Imitation checkpoint is experimental and unpromoted. This golden case is
  a deterministic demonstration, not evidence that it is universally optimal.
- The validation aggregate remains the honest broader claim: the checkpoint can
  beat naive often, but recorded validation still contains constraint violations.
- Supplied 100 m areas are synthetic scenario inputs, not validated blast radii.

## Recovery during the demo

- If a run-status request fails, use **Retry run status**; do not resubmit first.
- If the UI is stale, reload the `?basemap=plain` URL and restart at **1 · Naive**.
- If Imitation fails, finish on Naive and say it is the guaranteed deterministic
  fallback. Do not substitute the offline Exact policy as though it were online.
- If the launcher exits, restart the single launcher command. Its persistent
  local result store preserves the last published result.

The safest demo conclusion is: “The end-to-end product path works today with a
deterministic baseline; structured imitation is the stronger demo policy on this
fixed case; RL remains the improvement track rather than a demo dependency.”
