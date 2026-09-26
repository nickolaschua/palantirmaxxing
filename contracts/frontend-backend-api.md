# Frontend–backend HTTP delivery contract, v1

This is the canonical contract for future result delivery. **The backend has no
HTTP service yet.** No endpoint is implemented or verified by this frontend work.
This document supersedes the backend-delivery guidance in the historical
[frontend/docs/API-DESIGN.md](../frontend/docs/API-DESIGN.md), which is retained
unchanged. The canonical planning payload is [planning-result.md](planning-result.md);
the independent simulation payload is [simulation-result.md](simulation-result.md).

## Routes and publication

All routes are same-origin, read-only GET requests:

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
reason safely as text. A future HTTP client must check status before selecting
the success or error adapter. Transport and JSON decoding failures also become
Unavailable with a reason. A 200 response with a malformed envelope, wrong result
kind, or unsupported payload schema is invalid and must not draw a result.
The pure adapters in `frontend/src/demo/delivery.ts` validate bodies; they do not
make requests or verify HTTP headers.

## Client lifecycle and versioning

Both views remain fixture-backed through injectable async loaders. Loading is
visible before validation; failures show Unavailable, a reason, and Retry.
Validation precedes drawing. Superseded or disposed requests cannot update the UI.
Retry replaces a mounted snapshot only after validation succeeds, disposing its
previous layers. Failed retries preserve an already validated snapshot.

V1 has no authentication, run submission, polling, push updates or automatic
replacement of displayed results. An eventual explicit refresh requests latest
again and changes the displayed snapshot only after validation succeeds. The
current Retry action reruns the injected fixture loader; it performs no HTTP call.

`planning-result/1` and `simulation-result/1` are independent payload versions.
Incompatible payload changes require a new schemaVersion and a compatible parser.
Changes to the HTTP envelope or route semantics require `/api/v2`; changing a
payload version alone does not change delivery identity or route semantics.
Unknown additive fields may be ignored. No simulation payload is accepted by the
planning adapter or vice versa.

## Verification boundary

`npm test` checks actual-artifact envelopes, wrong kind, absent/empty identity,
invalid publication times, unsupported schema and the three failure examples.
`npm run test:ui` exercises both actual view mounts in jsdom with mocked canvas
layers, including retry and lifecycle races. These tests prove frontend behavior,
not backend HTTP conformance, real Cesium rendering, route implementation,
publication ordering, headers or server immutability. Those require integration
tests against a future service.
