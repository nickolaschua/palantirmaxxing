# Frontend–backend HTTP delivery contract, v1

This is the canonical local HTTP delivery and run contract. The standard-library
service is implemented under `backend/api/`, with immutable publications and a
single serial job worker. The canonical [planning payload](planning-result.md)
and independent [simulation payload](simulation-result.md) retain their existing
versions and model settings. Historical `frontend/docs/API-DESIGN.md` is preserved.

## Routes and publication

Result routes are same-origin, read-only GET requests:

| Request | Successful result |
| --- | --- |
| `GET /api/v1/planning-results/latest` | Most recently published completed planning result |
| `GET /api/v1/planning-results/{resultId}` | That immutable planning snapshot |
| `GET /api/v1/simulation-results/latest` | Most recently published completed simulation result |
| `GET /api/v1/simulation-results/{resultId}` | That immutable simulation snapshot |

Only completed, validated results are published. Partial, queued, running, and
failed runs are never successful delivery results. Publication is atomic.
“Latest” orders by publication, not scenario start, episode end, filesystem
modification time, or run start. The publisher must resolve publication ties
deterministically. An ID lookup never changes its payload or publication time;
correction requires a new resultId. Treat resultId as an opaque, nonempty string,
encode it as a URL path segment, and do not derive it from scenarioId or episodeId.
The literal route segment `latest` is reserved and cannot be a lookup identity.

## Success

Every 200 response uses `Content-Type: application/json` and
`Cache-Control: no-store`. Its JSON object is:

```ts
{
  resultId: string,
  publishedAt: string,
  result: object
}
```

resultId is the delivery identity, distinct from planning scenarioId and simulation
episodeId. publishedAt is a valid ISO-8601 UTC timestamp using uppercase T and Z,
seconds, and an optional 1–6 digit fractional second, for example
`2026-09-26T00:00:00.123456Z`. Local times, offsets, impossible dates and empty
identities are rejected. result keeps its existing schemaVersion and is passed
unchanged to the respective frontend parser; the envelope does not rename, enrich,
convert or merge payload fields.

Executable complete success examples use the actual checked-in artifacts:
`frontend/tests/delivery.test.ts` constructs the following object, once with each
artifact, and verifies unchanged identity and acceptance by the existing parser:

```js
({
  resultId: "published-snapshot-1",
  publishedAt: "2026-09-26T00:00:00.123456Z",
  result: JSON.parse(artifactText)
})
```

For planning requests, artifactText is the complete contents of
`data/results/demo-planning-result.json`; for simulation requests it is
`data/results/demo-simulation-result.json`. This construction defines complete
response bodies without duplicating or truncating either payload.

## Failures

All failures below use `Content-Type: application/json` and
`Cache-Control: no-store`, with nonempty string code and message:

| Status | Meaning | Example JSON body |
| --- | --- | --- |
| 404 | No matching published result, including empty latest | `{"error":{"code":"RESULT_NOT_FOUND","message":"No matching published result."}}` |
| 503 | Temporary delivery failure | `{"error":{"code":"DELIVERY_UNAVAILABLE","message":"Result delivery is temporarily unavailable."}}` |
| 500 | Unexpected server failure | `{"error":{"code":"INTERNAL_ERROR","message":"Unexpected server failure."}}` |

The codes above are examples; clients validate nonempty strings and display the
reason safely as text. The HTTP client checks status before selecting
the success or error adapter. Transport and JSON decoding failures also become
Unavailable with a reason. A 200 response with a malformed envelope, wrong result
kind, or unsupported payload schema is invalid and must not draw a result.
The pure adapters in `frontend/src/demo/delivery.ts` validate bodies; they do not
make requests or verify HTTP headers.

## Jobs

`POST /api/v1/runs` accepts exactly `{"kind":"planning"}` or
`{"kind":"simulation","seed":7}`. Simulation seed defaults to 7 and must be an
integer in 0–2147483647. Unknown fields, unsupported kinds, booleans, fractional,
negative, oversized and string seeds return 400. Input cannot specify commands,
paths, policies or configuration. The baseline policy and existing exporters are fixed.

A submission returns 202 with a UUID `runId` and `status: "queued"`.
`GET /api/v1/runs/{runId}` returns a persisted record with `queued`, `running`,
`succeeded` or `failed`. Success adds `resultKind` and `resultId`; failure adds
`error: {code, message}`. Unknown IDs return 404. Responses are JSON/no-store.
One background worker executes one isolated exporter subprocess at a time,
with eight waiting jobs, a 120-second execution timeout, and separate output/logs.
Overflow returns 429. Failed/invalid/timed-out exports do not change latest.
Restart retains terminal records and marks interrupted queued/running jobs failed.

## Client lifecycle and versioning

Both views default to HTTP through Vite's `/api` proxy. Set `?source=fixture`
(or `VITE_RESULT_SOURCE=fixture`) for explicitly labelled fixture mode. Only that
mode imports fixtures or adds illustrative planning consequence values; HTTP
failures never trigger fallback. Delivery metadata stays alongside the payload.

Loading and errors have visible reasons. Explicit Refresh loads latest; publishing
alone never replaces a displayed snapshot. Request generations and abort signals
prevent stale/disposed requests from rendering. Failed fetching, validation, or
render construction preserves the preceding snapshot and identity. Render attempts
own their partial resources; successful replacement disposes old layers/listeners.
Planning history retains its originating result ID and starts fresh per snapshot.
Planning Restart is a presentation action and never submits a backend job.

Each Run control disables duplicate submission, displays job status, and polls at
one-second intervals without overlap. On success it loads the exact result ID,
not latest. Polling stops at terminal state or disposal. A failed job leaves the
preceding view intact and enables another submission. A polling transport failure
offers Retry run status while keeping the existing job active.

Payload versions stay independent. Incompatible payload changes require a new
schemaVersion and compatible parser; incompatible envelope/routes require `/api/v2`.

## Startup and verification

`.venv-rl/bin/python scripts/run_integration_mvp.py` checks prerequisites, starts
backend 127.0.0.1:8000 and Vite 127.0.0.1:5173, verifies direct and proxied readiness,
and prints a plain-basemap URL. It publishes missing default demos before ready;
restarts preserve existing publications. Occupied ports fail explicitly without
stopping their owners. Ctrl-C stops only the launcher's children.

The standalone server remains available via `.venv-rl/bin/python -m backend.api.server`;
add `--bootstrap` for explicit missing-demo generation. GET itself never exports.
Runtime state and evidence are ignored under `outputs/integration-mvp/`.

`.venv-rl/bin/python scripts/verify_integration_mvp.py --all` runs all ten gates;
`--gate B04` independently checks HTTP. Results contain the tested HEAD, tracked
diff/source/input hashes, runtime versions, commands, exit codes and assertions.
Browser gates use real Chromium/Cesium, block external network, retain traces and
screenshots, and observe actual geometry via a read-only `?acceptance=1` hook.
Circle tolerances are 1e-7 degrees for center and 1e-6 metres for radius.
See [readiness](../nickolas/integration-readiness.md) for current evidence.

Successful job status and its result identity commit in the same atomic publication
index replacement. Per-run JSON files mirror that state; a failed mirror write
cannot turn an already committed success into an interrupted job on restart.
