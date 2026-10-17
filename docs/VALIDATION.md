# Validation record

## Local checks

The Python 3.12 environment comes from `uv.lock`. `uv run pytest -q` passes 16 focused cases. The suite exercises event identity, grouped model training, quarantine/replay, immutable evidence, cross-run isolation, concurrent claims, path traversal, checksums, stale occupancy protection, review transactions, review retry identity, model unavailability, and static/API routes. Starlette emits a deprecation notice for its HTTPX test client. The localhost HTTP acceptance run separately verifies the real Uvicorn stack.

`uv run ruff check src tests scripts` passes. Code-health fast and deep checks against the initial packaging commit report zero findings. The available analyzers were Ruff and oxlint. The [saved reports](evidence/code-health-deep.json) describe their scope. These checks do not constitute a security audit or a Python type proof.

## Measured runs

- [Fault simulation](evidence/fault-demo.json): 12 boards, 60 applied events including replay, four initial quarantines, 12 duplicate deliveries, one deliberate identity conflict. Every board completed inspection.
- [Service load](evidence/service-load.json): 100 boards, 600 applied events including release/replay, 34 initial quarantines, 100 duplicates, one deliberate identity conflict. All 100 ended RELEASED. The 27.46-second duration includes local synthesis and direct service traffic. Its event rate counts the five original inspection/arrival events per board and excludes duplicate/review/release/replay calls from the numerator.
- [HTTP load](evidence/http-load.json): 25 boards, concurrency four, 180 POSTs; 177 returned 200, one expected out-of-order request returned 202, one event hash conflict returned 409, and one malformed request returned 422. All 25 boards ended RELEASED with retained reviews. The run took 22.29 seconds and measured 8.08 POSTs/s. p50/p95/p99 were 378/792/3362 ms. The script records every timed POST, including intentional fault requests. Generation, health checks, and final state retrieval do not contribute request samples. Overall elapsed time includes the final state read.
- [Model evaluation](evidence/model-evaluation.json): 120 generated training boards, two sites each, seed 17; 90 training boards/180 samples and 30 held-out boards/60 samples. The grouped split uses seed 41. All 60 held-out synthetic samples were classified correctly. Independent operational seeds are 73 for service simulation and 91 for HTTP load.

The host stores SQLite on a mounted workspace. Fsync, inference, concurrent local jobs, and filesystem behavior influence these latency values. No remote network, sustained soak, multiple API worker, or production-capacity test was performed.

## Browser check

Playwright opened the real localhost service, confirmed the connected classifier state, loaded both AOI crops, selected both decisions, submitted a named review with a reason, released the board, observed the retained review, and clicked quarantine replay. The [screenshot](workbench.png) records the running dashboard before that review. The replay recovery itself is verified by the HTTP report and unit suite.

## Container check

Container build and runtime verification are recorded below after the local build completes. The Docker CLI uses its legacy builder on this host. The default bridge could not resolve Python package download hosts; a host-network build was attempted. This environment behavior does not imply an application failure or Siemens platform compatibility.

## Implementation choices against the planning specification

The [handoff](IMPLEMENTATION_HANDOFF.md) records the intended engineering design. The executable package uses the following bounded choices:

- One runtime root (`SMT_RUNTIME` or `--runtime`) configures the database, artifacts, and model. Paths are isolated by an app factory argument.
- An explicit `slots` table enforces active-slot uniqueness. Board occupancy tokens are unique within a run. Every event retains its complete identity tuple.
- Journal status strings use lowercase `applied` and `quarantined`. Domain states use uppercase names. The journal stores canonical envelope JSON with all producer metadata. The audit log records transitions and accepted review actors. Dedicated per-site timestamp columns and a separate SQL migration framework were omitted.
- Strict identity or immutable-evidence conflicts return 409 without a new journal row. Dependency failures and late evidence for a released occupancy enter quarantine. Replay cannot change stored payloads. Exact duplicate deliveries do not increment attempts or create audit records.
- Synthetic measurement validation requires positive finite height and volume. It does not impose plant-specific upper limits. Optional coplanarity is accepted as producer metadata in the event journal; the current classifier and site projection use height and volume.
- A missing or failed local model produces an explicit unavailable prediction with no probability. Complete evidence still reaches human review readiness. Predictions do not authorize review or release.
- Reviews use transactional state guards and UUID request IDs. They do not use a separate revision field. SQLite serializes competing writers.
- The initial demo provides ready, reviewed, and released states through labelled synthetic fixtures. The simulator can leave valid dependency failures in quarantine, and tests construct collection and stale-reuse scenarios.
- The adapter normalizes a local CFX-inspired JSON wrapper. It does not translate official vendor messages or connect to a broker.
- JSON POST bodies are limited to 64 KiB before JSON parsing. The local prototype reads the body before checking that limit. It has no hostile internet ingress boundary.
- The dashboard renders the complete board list and the most recent 200 event/audit rows. It provides a line filter and manual refresh. Pagination and continuous streaming are future work.

All records and imagery originate from the synthetic generator. Automated fixture/load reviewers identify themselves in saved records. No performance or classification result establishes factory readiness.
