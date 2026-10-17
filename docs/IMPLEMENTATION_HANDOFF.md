# SMT Central Verification Workbench — implementation handoff

## 1. Product outcome and scope

Build a runnable portfolio prototype for centralized verification of surface-mount technology inspection results. The workbench correlates simulated AOI image evidence, synthetic 3D measurements, and human review decisions across several production lines. The browser shows where each board sits, which evidence has arrived, which inspections need review, and which events require replay.

The prototype must demonstrate engineering depth through executable behavior: board and buffer correlation, slot reuse protection, transactional ingestion, idempotency, an auditable review workflow, deterministic computer-vision fixtures, a trained scikit-learn classifier, fault injection, and measured load runs. A polished dashboard must expose those behaviors without requiring users to read implementation logs.

The implementation must consistently describe its evidence as simulated. The repository, dashboard, dataset report, and benchmark report must state that no real factory, Siemens Industrial Edge device, certified IPC-CFX endpoint, or plant inspection dataset has validated this system. A local Docker deployment provides an edge deployment prototype. It does not establish Siemens compatibility or qualification.

This project provides practical evidence for Python, IoT integration, M2M communication, computer vision, verification workflows, and robustness testing. It cannot establish German language proficiency. A German B1 language gap remains separate from technical project work.

### Required user-visible result

1. Start the service through documented commands.
2. Generate a reproducible synthetic dataset and train a classifier.
3. Seed a multi-line scenario with occupied slots and boards in several workflow states.
4. Open a responsive dashboard with a persistent simulation label.
5. Select a board and inspect each site's AOI crop, 3D values, and model suggestion.
6. Record a whole-board review with one decision per site.
7. Release the reviewed board and reuse its slot for another board.
8. Observe late evidence from the old occupancy enter quarantine without corrupting the new board.
9. Replay a recoverable event after its dependency arrives.
10. Run fault and load checks that produce machine-readable reports with observed results.

### Scope ceiling

Use one Python process, one SQLite database, a local artifact directory, and browser-native HTML/CSS/JavaScript. Avoid a frontend build, message broker, Kubernetes, Redis, ORM, background task framework, hosted model API, or authentication product. Keep HTTP processing synchronous and brief. Run dataset generation, training, and load generation through the CLI.

Keep the app local by default. The prototype has no multi-user security boundary. Document that internet exposure requires authentication, authorization, TLS, retention policies, and an operational review. Do not represent publication of the source repository as deployment of a public application.

## 2. Architecture and implementation ownership

Use Python 3.11 or newer, FastAPI, Uvicorn, Pydantic, NumPy, OpenCV's headless package, and scikit-learn. Use `sqlite3`, `hashlib`, `json`, `uuid`, `datetime`, `pathlib`, `argparse`, and `statistics` from the standard library. Use pytest and HTTPX for verification if the implementation already uses them. No JavaScript dependency is needed.

Prefer a package under `src/smt_workbench`. Install through `uv sync` and provide the `smt-workbench` console entry point. A conventional `python -m smt_workbench.cli` entry point can supplement it. Pin resolved dependencies in a lockfile. Keep user-adjustable paths in environment variables and CLI arguments.

```text
smt-central-verification-workbench/
  pyproject.toml
  uv.lock
  .gitignore
  .dockerignore
  Dockerfile
  compose.yaml
  README.md
  LICENSE
  src/smt_workbench/
    __init__.py
    app.py                 # app factory, HTTP routing, static UI
    db.py                  # schema creation, connections, transactions
    schemas.py             # strict event/review/adapter validation
    service.py             # event application, correlation, review, replay
    synthetic.py           # seeded images, measurements, dataset manifest
    ml.py                  # features, grouped split, fit, evaluation, inference
    simulator.py           # scenario events, fault runs, load reports
    adapters.py            # CFX-inspired and M2M translation
    cli.py                 # small argparse command frontends
    static/
      index.html
      styles.css
      app.js
  tests/
    conftest.py
    test_workflow.py
    test_ingestion.py
    test_replay.py
    test_ml.py
    test_adapters.py
    test_artifacts.py
  docs/
    IMPLEMENTATION_HANDOFF.md
    architecture.md
    api.md
    data-and-model.md
    validation.md
    edge-deployment.md
  .scratch/smt-workbench/plan.md
  .github/workflows/ci.yml
```

The names define responsibility boundaries. The implementation may combine closely related modules when the resulting file remains easy to read. Avoid forwarding-only layers and generic repositories. Domain transitions belong in one service so HTTP ingestion, adapter ingestion, replay, and simulation cannot diverge.

### Runtime configuration

| Setting | Suggested default | Behavior |
| --- | --- | --- |
| `SMT_DATA_DIR` | `./var` | Parent directory for local runtime state |
| `SMT_DB_PATH` | `$SMT_DATA_DIR/workbench.sqlite3` | SQLite database |
| `SMT_ARTIFACT_DIR` | `$SMT_DATA_DIR/artifacts` | Generated PNGs and read-only browser evidence |
| `SMT_MODEL_PATH` | `$SMT_DATA_DIR/model/model.joblib` | Locally trained model bundle |
| Listen address | `127.0.0.1:8000` | Local browser access |

The app factory must accept explicit database/artifact/model paths for tests. Avoid configuration reads that force every test to share global state. Resolve filesystem roots once. Create missing runtime directories through initialization. Do not place generated databases, trained pickle/joblib files, thousands of images, or virtual environments in Git.

SQLite must enable foreign keys and a bounded busy timeout on every connection. WAL mode is appropriate for a local service. A short `BEGIN IMMEDIATE` transaction must cover each event's journal update and every resulting domain mutation. Use database uniqueness constraints as the final concurrency guard. Use parameterized SQL everywhere.

## 3. Identity model and invariants

Use these identities consistently in payloads, SQL, logs, and UI:

| Identity | Meaning | Rule |
| --- | --- | --- |
| `run_id` | One isolated simulation or test run | Required on every event and board |
| `board_id` | Physical-board surrogate within a run | Unique within `run_id`; do not reuse after release |
| `line_id` | Simulated production line | A board belongs to one line in this version |
| `buffer_id` | Simulated buffer within a line | Required even if the demo has one buffer per line |
| `slot_id` | Slot name within a buffer | Unique only with run, line, and buffer |
| `occupancy_id` | One visit to one slot | Fresh UUID or equivalent globally unique token for each arrival |
| `site_id` | One expected inspection site on a board | Declared at arrival; required on AOI and 3D events |
| `event_id` | Producer-assigned event identity | Stable across delivery retries |
| `request_id` | Human-review operation identity | Stable across review submission retries |

The primary board key is `(run_id, board_id)`. The active slot key is `(run_id, line_id, buffer_id, slot_id)`. An event may attach evidence only when its complete board, line, buffer, slot, and occupancy tuple matches the active board visit. Looking up a board by slot alone is forbidden.

All normal events for a board retain the arrival tuple. Event time is evidence metadata. Event timestamps do not replace dependency checks and do not authorize mutation of a released board. A delayed event with an old timestamp still receives the current correlation checks.

### Invariants that must have executable checks

- A slot has at most one active board within its run.
- One board has one declared occupancy in this prototype.
- Occupancy tokens do not move between boards.
- A board cannot receive a site outside its declared `expected_sites`.
- A site's first AOI result and first 3D measurement become immutable evidence.
- An exact event retry produces no extra inspection, review, audit transition, or release.
- A reused event ID with a different canonical payload returns a conflict.
- A second event ID cannot silently replace existing site evidence.
- A board reaches `READY_FOR_REVIEW` only after every expected site has both evidence types.
- Model prediction is advisory; it cannot release a board or create a review.
- Review covers every expected site exactly once.
- Review records become immutable after acceptance.
- Only a reviewed board can release its slot.
- A stale event cannot change any field of a new occupant.
- Replaying a quarantined event uses its stored payload and event ID.
- State updates and journal updates commit together or roll back together.

Scope does not include board transfers between lines, repeated visits by one board, replacement inspection passes, partial reviews, or reopened reviews. Such events must fail explicitly instead of creating an undocumented transition.

## 4. Database design

Create the schema idempotently. A small `schema_version` marker is enough for the first version. No migration framework is needed. Use UTC ISO timestamps or documented UTC epoch values consistently.

### `boards`

| Column | Shape | Constraint/purpose |
| --- | --- | --- |
| `run_id`, `board_id` | text | Composite primary key |
| `line_id`, `buffer_id`, `slot_id` | text | Nonempty validated identifiers |
| `occupancy_id` | text | Unique visit token |
| `expected_sites_json` | JSON text | Ordered unique expected site IDs |
| `state` | text enum | `COLLECTING`, `READY_FOR_REVIEW`, `REVIEWED`, `RELEASED` |
| `arrived_at` | timestamp | Arrival event time |
| `created_at`, `updated_at` | timestamp | Server receipt/update times |
| `reviewed_at`, `released_at` | nullable timestamp | Server transition times |

Enforce active-slot uniqueness with a partial unique index over `(run_id,line_id,buffer_id,slot_id)` where state is not `RELEASED`. A unique `occupancy_id` simplifies stale-visit detection. Index run, line, and state for dashboard filters.

### `inspections`

One row per declared site, created at arrival or lazily on first valid evidence. Its primary key is `(run_id,board_id,site_id)`, with a foreign key to `boards`.

Store AOI event ID, safe relative image path, image SHA-256, and AOI received time. Store measurement event ID, `height_mm`, `volume_mm3`, optional `coplanarity_mm`, and measurement received time. Store nullable model label, class probability, model ID, feature version, and prediction time. An inference failure must be visible as an explicit unavailable/error status; do not invent a probability.

Predictions may be computed after the second evidence type arrives. The app must not run training inside event ingestion. Load a trusted local model once or cache it by path/version. Explicitly define the behavior when no model exists: retain evidence and permit human review, display `Model unavailable`, and document the training command.

### `events`

This table is both the event journal and the source of the quarantine queue. Store:

- `event_id` primary key;
- canonical payload SHA-256 and canonical envelope JSON;
- event type, run ID, board ID, and occupancy ID for filtering;
- state: `applied` or `quarantined`;
- nullable stable `reason_code` and bounded human-readable detail;
- first received time and last processing time;
- processing `attempt_count`, initially one;
- applied time, when successful;
- stable response/result JSON if needed for duplicate responses.

A duplicate delivery does not constitute a new processing attempt. An explicit replay does. A schema-invalid request never enters this table. An event-ID conflict must not overwrite the original row. Quarantine applies to schema-valid envelopes that cannot apply under the current domain state. This definition keeps API failures distinct from replayable records.

### `reviews`

Store a generated review ID, unique request ID, request-body hash, run ID, board ID, reviewer, reason, decisions JSON, and created time. Enforce one accepted review per board. The normalized decisions must include all sites exactly once and use the values `false_call` or `real_defect`.

Keep model suggestions separately from the human decision. A review can disagree with the model. Do not rewrite historical predictions when a person chooses another label.

### `audit_log`

Store ID, timestamp, run/board identities when present, action, actor/source, event or review ID, and JSON details. Record accepted board arrival, readiness transition, review, release, quarantine, and replay result. A duplicate delivery must not create another domain transition. A replay can create an audit entry describing the attempt. Do not store secrets, absolute host paths, or raw exception traces in browser-visible audit details.

An extra artifact or run table is optional. Do not create one unless it removes actual duplicated state. Generated manifests can provide artifact provenance. All SQL reads used by the API must return deterministic ordering.

## 5. Canonical event contract

Use the same envelope for the simulator, direct HTTP clients, adapters, and stored replay. The JSON example is illustrative and uses one arrival:

```json
{
  "schema_version": "1.0",
  "event_id": "c9cc0cf1-8813-46a5-85be-86a37523cfef",
  "event_type": "arrival",
  "run_id": "demo-20261017",
  "board_id": "PCB-0001",
  "line_id": "LINE-A",
  "buffer_id": "BUF-01",
  "slot_id": "S01",
  "occupancy_id": "55ecc34e-7b5e-4cb5-8c31-aa27a2b031ed",
  "occurred_at": "2026-10-17T12:00:00Z",
  "payload": {"expected_sites": ["U1", "R7"]}
}
```

### Payloads

| `event_type` | Required payload | Optional payload | Application effect |
| --- | --- | --- | --- |
| `arrival` | `expected_sites`: 1–16 unique IDs | None required | Create board occupancy and collecting state |
| `aoi` | `site_id`, `image_path` | `sha256` | Attach immutable AOI image evidence |
| `measurement` | `site_id`, `height_mm`, `volume_mm3` | `coplanarity_mm` | Attach immutable numeric 3D evidence |
| `release` | Empty object | None required | Release a reviewed board and free its slot |

`image_path` is a path relative to the artifact root. It must identify a generated PNG. Reject absolute paths, `..` traversal, directories, unregistered external paths, and symlinks that resolve outside the root. Resolve the path and check its containment; string-prefix comparisons are insufficient. Verify the file exists and OpenCV can decode it before accepting AOI evidence. Calculate its SHA-256. Verify a supplied hash. Keep artifact files immutable after generation. The evidence API must expose a browser URL rather than an absolute host path.

### Boundary validation

- Use Pydantic models with unknown fields forbidden at envelope and payload boundaries.
- Require the supported schema version and one of the four event types.
- Validate identifiers as bounded, nonempty strings. A conservative ASCII character set such as letters, numbers, `_`, `-`, and `.` is sufficient.
- Use a maximum length such as 96 characters per identifier and 256 characters for a relative image path.
- Require timezone-aware `occurred_at` and normalize to UTC.
- Enforce a bounded request size. A limit of 64 KiB is sufficient for event/review JSON. No image binary travels in an event.
- Require finite real measurement numbers; reject NaN, positive infinity, and negative infinity.
- Example synthetic bounds: height 0–5 mm, volume 0–20 mm³, coplanarity 0–2 mm. Explain that these are prototype constraints, not universal manufacturing limits.
- Treat booleans as invalid numeric measurements.
- Require a nonempty reviewer and reason with sensible maxima, for example 80 and 1000 characters.
- Reject duplicate site decisions and undeclared sites.

### Canonicalization and duplicate handling

Compute the event hash from normalized model data serialized as UTF-8 JSON with sorted keys and compact separators. Normalize defaults and datetimes before hashing. Preserve all semantic fields, including event identity, correlation tuple, payload, and occurrence time. JSON whitespace and key order must not change the hash.

| Situation | HTTP status | Mutation |
| --- | --- | --- |
| First valid event applies | `201` | Journal and domain commit |
| Exact duplicate of applied event | `200` | None; return `duplicate: true` |
| Schema-valid event lacks dependency or conflicts with domain state | `202` | Journal enters quarantine; domain unchanged |
| Exact duplicate of quarantined event | `202` | None; return existing reason |
| Existing event ID, different canonical hash | `409` | None; original journal row preserved |
| Invalid schema, unsupported version, invalid value | `422` | No domain or journal row |
| Excessive body size | `413` | No mutation |

Return JSON containing `event_id`, `status`, `duplicate`, and optional `reason_code`, `detail`, and resulting board state. Avoid returning raw SQL or stack traces.

Stable quarantine reason codes should include `BOARD_NOT_FOUND`, `SLOT_OCCUPIED`, `OCCUPANCY_MISMATCH`, `BOARD_RELEASED`, `SITE_NOT_EXPECTED`, `EVIDENCE_EXISTS`, `BOARD_NOT_REVIEWED`, and `ARTIFACT_UNAVAILABLE`. Add specific hash/invalid-image codes if those checks occur after schema validation. Document whether each failure can recover through replay.

## 6. State machine and transaction processing

```text
arrival
  │
  ▼
COLLECTING ── every expected site has AOI + 3D ──▶ READY_FOR_REVIEW
                                                       │
                                             complete human review
                                                       │
                                                       ▼
                                                   REVIEWED
                                                       │
                                                release event
                                                       │
                                                       ▼
                                                   RELEASED
```

### Arrival

Start a write transaction. Resolve an existing event ID before any domain work. Validate that the board key and occupancy token are unused. Validate active-slot availability. Insert the board and expected inspection sites. Add the applied event and arrival audit row. Commit together.

Two concurrent arrivals for the same active slot must produce one occupancy and one quarantined event. Catch the expected uniqueness failure and translate it into a stable domain result. Do not leave a transaction partially open.

### Evidence

Resolve event identity, then load the board. Check that the board is active, the entire correlation tuple matches, and the site is expected. Reject attempts to overwrite AOI or 3D evidence under a different event ID. Attach the evidence. If a site now has both sources, compute its advisory prediction when a model is available. If every site is complete, transition to `READY_FOR_REVIEW` once and append one readiness audit row.

Keep inference small enough to finish within the HTTP request. A prediction exception must not create a half-written evidence record. Either persist the evidence with an explicit prediction-error status or roll back and return an explicit server failure. Prefer persisting evidence and exposing model unavailability because the human review workflow can continue.

### Review

Require `READY_FOR_REVIEW`. Check request identity before state validation so a successful request can be retried after the board becomes reviewed. Require exactly one decision per expected site. Store the review, update the board, and append its audit record in one transaction. A new request ID attempting to review the same board again returns `409`.

A mixed board can have both false-call and real-defect site decisions. Label the board outcome as `defect_confirmed` if any site is `real_defect`; otherwise use `false_call_only`. Preserve site decisions as the source of truth. Review completion does not claim a repair or a factory disposition.

### Release

Require a matching occupancy and `REVIEWED` state. Set `RELEASED`, record release time, and append an audit entry. The partial active-slot uniqueness constraint then permits a new board in that slot. A subsequent event for the old board must be quarantined without looking up or mutating the new occupant.

### Replay

Replay only a stored quarantined event. Preserve its payload and hash. Re-run the same service logic inside a transaction; do not send a new HTTP request to the service itself. Increment attempt count and last-attempt time. On success, change the event to `applied` and retain first receipt time. On failure, keep it quarantined and refresh the reason. Replaying an applied event returns a no-op result.

Provide an explicit per-event replay action. An optional bounded replay-all command may process up to a caller-specified limit. Do not implement an unbounded retry loop or background poison-message spinner. Some quarantined events, such as stale evidence or overwrites, can never apply under this version's immutable-evidence rules. Show that fact in the UI and validation document.

## 7. HTTP API

Use `/api` for JSON routes and serve the browser at `/`. Keep an OpenAPI document available through FastAPI. All list endpoints need a documented maximum result count. Filter by `run_id` where relevant to keep load-test state separate from the demo.

| Method and route | Request/filters | Response behavior |
| --- | --- | --- |
| `GET /health` | None | Basic process/database readiness; no sensitive paths |
| `GET /api/summary` | Optional run ID | State counts, active slots, quarantined count, model status |
| `GET /api/boards` | Run, line, state, limit | Stable ordered board summaries and evidence counts |
| `GET /api/boards/{run_id}/{board_id}` | Identity | Board, sites, image URLs, 3D values, predictions, review |
| `GET /api/slots` | Run, optional line | Active occupancies grouped by line/buffer/slot |
| `POST /api/events` | Canonical event | Ingestion result and statuses from Section 5 |
| `POST /api/boards/{run_id}/{board_id}/review` | Review body | `201` accepted; `200` exact retry; `409` conflict |
| `GET /api/events` | Run, status, limit | Event journal; include attempt count and reason |
| `GET /api/quarantine` | Run, limit | Quarantined journal entries |
| `POST /api/quarantine/{event_id}/replay` | No editable payload | Applied/no-op/still-quarantined result |
| `GET /api/audit` | Run, optional board, limit | Ordered immutable transition history |
| `GET /api/model` | None | Model metadata, metrics, evidence limitations; no executable blob |
| `GET /api/metrics` | Optional run | JSON operational counters and persisted workflow totals |
| `POST /api/adapters/cfx` | Documented CFX-inspired envelope | Translate then call normal event service |
| `POST /api/adapters/m2m` | Documented M2M envelope | Translate then call normal event service |
| `GET /artifacts/{relative_path}` | Safe artifact path | Generated PNG only; traversal-resistant resolution |

Equivalent route spellings are acceptable if the implementation chooses them consistently before building the browser and tests. Update `docs/api.md`, README examples, and test clients to the final names. Do not retain aliases that have no consumer.

Suggested review body:

```json
{
  "request_id": "16b7986f-589d-4f8a-bb1d-6c9b69095003",
  "reviewer": "Demo operator",
  "reason": "Glare at U1; missing component confirmed at R7.",
  "decisions": [
    {"site_id": "U1", "decision": "false_call"},
    {"site_id": "R7", "decision": "real_defect"}
  ]
}
```

The browser must retain a review request ID while retrying the same submission. A fresh submission after an error may create a new ID only when the user changes the payload or starts a new operation.

## 8. Protocol adapters and claim boundaries

### CFX-inspired JSON adapter

Use a small envelope with source endpoint, message name, timestamp, message ID, and body. Define a local message vocabulary for arrival, AOI observation, 3D observation, and release. Publish an explicit mapping table to the canonical contract. A message name may use an obviously local prefix such as `Demo.BoardArrived` to avoid implying that an invented payload is an official IPC-CFX message.

The adapter must retain a stable producer message ID as the canonical event ID. Map the full correlation tuple, including the occupancy token. Reject unknown messages and missing identity fields. Route the result through the same validation and service logic as `/api/events`.

Use the phrase **CFX-inspired JSON adapter** in README, UI help, and API documentation. This implementation does not provide AMQP transport, IPC message-schema conformance, endpoint discovery, interoperability qualification, or certification. Do not call it an IPC-CFX-compliant implementation. Adding an arbitrary `CFX` string to JSON does not establish compatibility.

Official references for future integration:

- [IPC-2591 Connected Factory Exchange](https://www.ipc.org/ipc-2591-connected-factory-exchange-cfx)
- [IPC CFX self-validation and qualification system](https://www.ipc.org/cfx-self-validation-and-qualification-system)

A real integration would require the actual applicable message schemas, transport configuration, endpoint semantics, vendor behavior, and qualification evidence. Keep this future work in documentation; do not add a broker solely to make the prototype look industrial.

### M2M simulation adapter

Define a second compact shape with machine ID, event ID, timestamp, event kind, correlation fields, and measurements or image reference. This adapter demonstrates translation between a machine-shaped payload and a central application contract. It does not demonstrate an actual machine connection.

Keep adapter tests focused on preservation of identity and measurements, unsupported message rejection, missing occupancy rejection, and duplicate delivery through different entry points. Translating a direct event and receiving the equivalent adapter event with the same canonical event ID must not apply it twice.

## 9. Synthetic image and measurement generation

Generate original local images with OpenCV. Do not download industrial images or imply third-party dataset rights. Use a seeded NumPy generator passed through the generator functions. Do not use the global unseeded RNG or Python's randomized `hash()` to produce artifacts.

Suggested image size is 160×160 or 192×192 pixels. Draw a dark PCB background, copper pads, rectangular components, solder regions, and controlled noise. Vary translation, rotation, lighting, blur, noise, and component geometry within bounded ranges.

Use two binary truth labels:

| Label | Meaning inside simulation | Example subtype |
| --- | --- | --- |
| `false_call` | AOI flags a site whose generated component is acceptable | Glare, low contrast, benign offset |
| `real_defect` | Generator deliberately introduces a physical-defect surrogate | Missing component, solder bridge, excessive offset |

Store the subtype separately for analysis. Both classes must share nuisance variation so labels cannot be recovered from an accidental image border, file color, background, or deterministic filename pattern. Label information belongs in the manifest, never in the feature vector.

Generate synthetic 3D values from class/subtype-dependent distributions with meaningful overlap and noise. Document their illustrative nature and units. Avoid asserting that generated values match a real SPI/AOI sensor. Keep the measurement values plausible within the application's validation bounds.

### Group structure

Generate several sites per synthetic board, such as two or three. Sites on the same board share a board-level lighting/noise/manufacturing offset. This makes board-level grouping meaningful and prevents a random image split from hiding related-sample leakage.

Use at least 120 boards for the default training demonstration if runtime allows. A 240-board default with two sites each is also reasonable. Keep unit-test datasets small. Each class must appear in both train and test groups. If a tiny seeded dataset violates this requirement, fail with a clear explanation or deterministically regenerate; do not quietly report meaningless metrics.

### Dataset manifest

Emit a CSV or JSONL row per site containing:

- dataset ID and generator version;
- seed and generation configuration;
- board group ID and site ID;
- relative image path and image SHA-256;
- synthetic 3D measurements with units;
- truth label and subtype;
- an explicit `source: synthetic` marker.

Also emit summary metadata with generation command, parameters, row/board/class counts, and an overall manifest hash. Repeating the same seed/configuration must reproduce the same image bytes and measurement values under the same recorded dependency versions. Timestamps may differ in metadata; exclude them from reproducibility comparisons.

Use a distinct seed namespace or dataset ID for the operational demo. Do not silently use the holdout test images as live samples. Do not overwrite the training dataset when running the dashboard scenario.

## 10. Features, model training, and evaluation

Use an understandable feature extractor. Example image features include grayscale mean/std, bright-pixel proportion, edge density, thresholded connected-component statistics, and central-region contrast. Append height and volume, and coplanarity if present in the chosen schema. Freeze feature order under a `feature_version` string.

Feature extraction may use OpenCV, but training and inference must call the same function. Do not feed filenames, board IDs, labels, subtypes, or image hashes to the model. Use a scikit-learn pipeline with `StandardScaler` and `LogisticRegression`, or a small deterministic classifier whose feature handling is equally clear. A simple pipeline is sufficient; no hyperparameter search is required.

### Leakage-conscious split

1. Generate the complete manifest.
2. Split by board group with a fixed random seed and about 25% held-out boards.
3. Assert that train and test board sets are disjoint.
4. Assert that their sample identities are disjoint.
5. Fit preprocessing only on training data through the pipeline.
6. Fit the classifier on training data only.
7. Compute the held-out report once for the chosen fixed model.

Use [scikit-learn GroupShuffleSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupShuffleSplit.html) or an equivalent explicit deterministic group split. Record the exact split membership. A high synthetic score does not establish a real AOI detector's performance.

### Model artifact and report

Save a local trusted model bundle plus a readable JSON report. Include:

- model ID and model/feature/generator versions;
- classifier type and parameters;
- training dataset ID and manifest hash;
- seed, train/test board IDs, and train/test sample counts;
- class counts per partition;
- accuracy, balanced accuracy, precision, recall, F1, and confusion matrix;
- explicit class order for the matrix;
- software versions and the training command;
- probability interpretation and limitations;
- `evidence_type: synthetic_holdout`.

Compute binary metrics with `real_defect` as the positive class. Explain that `real_defect` recall measures missed generated defects within this synthetic holdout only. Handle zero denominators explicitly. Use the classifier's class ordering when selecting probabilities.

Do not require a convenient accuracy threshold to pass the project. Required gates concern correctness, reproducibility, leakage separation, valid metric calculation, and complete reporting. Report the actual measured score. A perfect score should trigger an explanatory check for accidental leakage or an overly separable generator, not a production-quality claim.

Treat model files as executable local artifacts because common Python model serialization formats can execute code. Do not offer arbitrary model uploads or load model blobs from API input. Fail clearly on incompatible feature versions. A changed model must receive a new model ID; stored historical predictions retain their original model ID.

## 11. Simulation, fault replay, and load measurement

Provide CLI operations for database initialization, dataset generation, training, scenario generation, serving, fault replay, and load testing. The final command names must be discoverable with `--help`. Suggested public commands are:

```bash
uv sync
uv run smt-workbench init-db
uv run smt-workbench generate --seed 42 --boards 240
uv run smt-workbench train --seed 42
uv run smt-workbench simulate --scenario demo --seed 2026
uv run smt-workbench serve --host 127.0.0.1 --port 8000
```

If a consolidated `demo` command reduces setup mistakes, add it as a small composition of existing functions. It must print each step and preserve user data. Do not implicitly delete an existing database. Generate a new run ID or require an explicit reset flag for destructive reseeding.

### Default dashboard scenario

Use three lines with four or more visible slots per line. Include at least:

- one collecting board missing an AOI result;
- one collecting board missing a measurement;
- several ready boards with diverse image subtypes;
- one reviewed board;
- one released board and its new slot occupant;
- one quarantined out-of-order event that can recover after its arrival;
- one stale-occupancy event that must remain quarantined.

The simulator may perform seeded simulated reviews to populate history. Mark its reviewer as `Simulation operator` and its source as simulated. Real browser review submissions still use the same review service.

### Fault scenarios and expected observations

| Scenario | Injection | Required observation |
| --- | --- | --- |
| Duplicate delivery | Same event sent twice | One mutation, second response marked duplicate |
| Conflicting event identity | Same event ID, changed measurement | `409`; original value unchanged |
| Evidence before arrival | AOI/3D delivered first | Quarantine; arrival then replay applies once |
| Evidence ordering | 3D before AOI on existing board | Board becomes ready only after both |
| Occupied slot | Two arrivals for same active slot | First owns slot; second quarantines |
| Slot reuse | Release A, arrive B, late event from A | B unchanged; late event quarantines |
| Wrong occupancy | Correct board ID, incorrect token | No evidence attachment |
| Wrong site | Unknown site ID | No extra inspection row |
| Premature review | Review incomplete board | Conflict; no review or state change |
| Premature release | Release unreviewed board | Quarantine; later review permits replay |
| Invalid numeric evidence | Negative/out-of-range/NaN values | Validation failure; no domain mutation |
| Missing artifact | Valid relative path absent | Clear failure/quarantine; no false AOI completion |
| Corrupt artifact | Non-image bytes under `.png` | Clear decode failure; no false AOI completion |
| Path escape | Absolute/traversal/symlink escape | Access rejected; no host file leakage |
| Repeated replay | Replay successful event again | No additional transition |
| Concurrent arrival | Parallel requests for one slot | Exactly one active occupancy |
| Restart | Close and recreate app over same DB | State, reviews, events, and audit remain available |

Tests should directly assert invariants and final database/API state. A status-code-only test does not prove that the new board remained unchanged.

### Load tool

Prefer an async HTTPX client with bounded concurrency, or another small existing client. Send canonical HTTP events to an actual local server for the headline load report. A direct in-process benchmark may supplement it but must be labeled separately.

Pre-generate image assets before timing. Exclude dataset generation and model training from ingestion latency. Use a unique run ID. Either provision enough unique slots for the run or complete board review/release cycles before reusing them. Do not accidentally benchmark a stream of quarantined slot collisions while calling it successful throughput.

Record target URL, timestamp, seed, run ID, workload size, event mix, concurrency, wall time, request counts by status, applied/quarantined/duplicate counts, unexpected errors, throughput, and p50/p95/p99 latencies. Record whether inference was enabled. Include hardware/OS/Python information when available without identifying secrets or private paths.

Use a modest default such as 50–100 boards and concurrency 4–8. Print progress every bounded batch. Write JSON to a requested report path. A finite timeout must apply to every request and the overall job. A failed run must exit nonzero and preserve its report.

Do not set an arbitrary industrial throughput claim or latency service-level objective. Required acceptance is zero unexpected HTTP/server errors, correct expected counts, and preserved invariants. Report actual local measurements and their workload limits. SQLite single-writer throughput and single-process deployment are known prototype ceilings.

## 12. Browser interaction and visual design

Use a restrained industrial dashboard: dark navy or pale neutral canvas, clear typography, strong spacing, and teal/amber/red state accents. A header should show the product name, active run, simulation status, and connection status. Use CSS layout and native controls; no charting library is required.

### Layout

1. Summary cards: active boards, ready for review, reviewed, and quarantined events.
2. Production lines: a responsive grid of line cards with labeled buffer slots and state badges.
3. Review queue: filterable list/table with board, line/slot, evidence completion, model indication, and age.
4. Board inspector: selected-board identity, site image cards, 3D measurement values, prediction, and review controls.
5. Event/quarantine panel: event type, board, reason, attempt count, and replay action.
6. Audit history: concise chronological workflow events.

Keep labels such as `Synthetic evidence`, `Model suggestion`, `Human decision`, and `Quarantined` explicit. Do not use a single “quality score” that conflates model confidence, measurement values, and human review.

Each site card must show units and image alt text. Show model class probability as advisory and avoid implying that it is calibrated. Indicate model unavailability clearly. Use a consistent display for missing AOI or 3D evidence.

### Review flow

Select a ready board, compare each image with its measurement values, select `False call` or `Real defect` per site, enter reviewer and reason, and submit one complete review. Show required-field errors beside the relevant controls. Disable repeated submission while the request is pending. Preserve the user's entries on recoverable HTTP errors. After success, show the saved review and update the queue/slot state.

Allow a separate release action for a reviewed board if a browser release control is included. The control must emit a normal release event with the board's current correlation tuple and a newly generated event ID. Make its effect clear: it frees the simulated slot; it does not claim physical machine actuation.

### Replay flow

Select a quarantine item, inspect its reason, and click replay. Show the result and updated attempt count. Explain permanent stale-occupancy failures without promising that another replay will fix them. No UI editing of historical payloads is allowed.

### Accessibility and reliability

- Use semantic buttons, labels, headings, and tables.
- Support keyboard operation and visible focus.
- Combine color with text badges.
- Keep contrast readable and avoid tiny gray status text.
- Escape all dynamic text through `textContent` or safe DOM construction.
- Never interpolate reviewer text, event details, or identifiers into unsanitized HTML.
- Handle empty data, loading, disconnected, and failed-request states.
- Poll at a modest interval such as 3–5 seconds and avoid overlapping fetch cycles.
- Preserve the selected board and unfinished review form while refreshing summary data.
- Use responsive breakpoints so the inspector and queue remain usable on a narrow screen.

Use the available browser tooling for a real smoke pass. Record which browser actions succeeded. Capture a screenshot for documentation if useful, but do not commit a misleading mock screenshot that the app cannot reproduce.

## 13. Container and Industrial Edge prototype

Build a small Python container that installs locked dependencies, copies the package/static assets, runs as a non-root user, and starts Uvicorn. Bind a volume at a documented data directory. Expose one application port. Include a health check. Do not bake generated runtime databases or secrets into the image.

Use Docker Compose for the local prototype. Document initialization and dataset/model generation inside the mounted data volume. The container must retain boards, reviews, and audit history across a restart.

Document the following distinction:

| Evidence available in this project | Additional evidence needed for a real deployment |
| --- | --- |
| Generic container starts and passes local health/API checks | Target Industrial Edge device/runtime compatibility |
| Volume persistence survives local restart | Device storage limits, backup, restore, and update behavior |
| Local HTTP event processing works | Actual plant network/security and machine integration |
| Synthetic replay/load report exists | Representative site workload and failure qualification |
| CFX-inspired adapter mapping works | IPC schema/transport interoperability and qualification |

Siemens integration references describe the real packaging workflow and runtime requirements:

- [Industrial Edge application Docker Compose overview](https://docs.industrial-operations-x.siemens.cloud/r/en-us/industrial-edge-platform-operation-develop-an-application/developer-guide/handson-exercise/description-of-the-hands-on-application/overview-of-the-docker-compose-file)
- [Industrial Edge standalone applications: Docker and Docker Compose](https://docs.industrial-operations-x.siemens.cloud/r/en-us/v26.01/industrial-edge-platform-operation-apis-references/industrial-edge-control-iectl/tutorials/create-application/standalone-apps/docker-and-docker-compose?contentId=CaUTO5CDnhDNVve2cAbq_g)

The current reference describes App Publisher packaging and Compose constraints. Verify the target device/runtime documentation before a future integration. Do not claim that this repository's generic Compose file has been imported, published, signed, or run on a Siemens device.

If the local Docker daemon is unavailable, still validate the Docker/Compose configuration where tools permit. State the exact unperformed runtime check. Do not fabricate a successful container run.

## 14. Verification gates and runnable acceptance

The repository must provide one short documented sequence that a fresh reader can execute. Final command spellings must match the implemented CLI. The illustrative sequence below establishes the intended gates:

```bash
uv sync --locked
uv run pytest -q
uv run smt-workbench init-db
uv run smt-workbench generate --seed 42 --boards 240
uv run smt-workbench train --seed 42
uv run smt-workbench simulate --scenario demo --seed 2026
uv run smt-workbench serve --host 127.0.0.1 --port 8000
```

Run the service as a tracked background job. Use separate commands for the HTTP smoke test and load run. Do not block the foreground on an unbounded readiness loop.

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/api/summary
uv run smt-workbench load-test --url http://127.0.0.1:8000 --boards 60 --concurrency 4 --report var/reports/load.json
docker compose config
```

### Gate A: packaging and persistence

Installation succeeds from the lockfile. CLI help lists actual commands. A temporary database initializes twice without destructive changes. Restarting the app preserves existing board, review, and event state.

### Gate B: domain behavior

Tests exercise complete board lifecycle, missing-evidence readiness, review atomicity, event/review idempotency, event-ID conflict, occupied slot, occupancy mismatch, stale slot reuse, and concurrent arrivals. Every test uses isolated state. At least one test proves rollback behavior or atomic rejection by comparing state before and after failure.

### Gate C: adapters and artifacts

Adapters preserve the full identity tuple and feed the same ingestion service. Invalid message types and missing required fields fail clearly. Image serving rejects traversal and escaping symlinks. A valid PNG is served with its expected content type. Corrupt/missing images cannot count as complete AOI evidence.

### Gate D: model evidence

Repeated seeded generation reproduces stable image hashes and numeric values. Train/test board sets are disjoint. The report contains actual held-out metrics, class ordering, model identity, dataset hash, and split membership. A saved model produces the same predictions after reload. Feature extraction never consumes truth labels or identifiers. Runtime images use the same feature implementation.

### Gate E: replay and load

Recoverable out-of-order evidence applies after its arrival and one replay. Stale evidence remains quarantined and leaves the new occupant unchanged. Load reports contain expected counts, observed latency percentiles, throughput, and explicit unexpected-error counts. Reports never translate local synthetic throughput into a factory-capacity claim.

### Gate F: browser and docs

A browser can load the seeded dashboard, filter/select boards, view images, submit a valid review, observe its persistence, and replay a recoverable event. Verify empty/error states where practical. Documentation describes real commands, protocol limitations, synthetic evidence, model metrics, test evidence, and unverified plant/edge work.

Run project-appropriate static analysis if installed. Address findings that reveal defects. Do not refactor working code solely to satisfy a generic complexity preference. CI should run the scoped test suite on a supported Python version; avoid heavyweight generated datasets and load tests in every CI run.

## 15. Documentation content and evidence ledger

The README should lead with the concrete board-review problem and the running solution. Include a screenshot if captured from the real app, short feature list, setup commands, demo commands, test commands, and a visible limitation paragraph. Avoid invented customers, deployment history, savings, accuracy guarantees, or certification badges.

`docs/architecture.md` should explain identity, occupancy safety, transactions, state transitions, and module responsibilities. `docs/api.md` should show canonical and adapter examples, routes, statuses, and replay semantics. `docs/data-and-model.md` should cover generator rules, feature definitions, units, grouping, provenance, actual metrics, and simulation limitations. `docs/edge-deployment.md` should cover local container use and the uncompleted real-device integration steps.

`docs/validation.md` must distinguish evidence categories:

| Category | What to record |
| --- | --- |
| Automated correctness | Exact command, actual pass count/result, tested invariants |
| Synthetic ML evaluation | Dataset/model IDs, split counts, actual metrics |
| Local workload | Date, environment, workload, measured latencies and throughput |
| Browser smoke test | Actual interactions completed and visible result |
| Container verification | Build/run/config result and persistence check if executed |
| Plant validation | Explicitly unperformed; list needed real evidence |

Store compact reports or selected JSON examples under a documented evidence directory if they are useful for reviewers. Strip absolute private paths and transient machine identifiers. Generated evidence must be labeled with the command and configuration that produced it. Do not commit every generated PNG or a database snapshot solely to create an impression of activity.

## 16. Meaningful commit sequence

Publish at least six meaningful implementation commits. The following eight commits provide reviewable milestones. Each commit should contain coherent behavior and applicable tests/docs. Do not pad history with formatting-only commits or empty milestones.

1. **`chore: scaffold Python workbench and implementation plan`** — package metadata, lockfile, CLI/app skeleton, configuration, ignore rules, initial docs, and schema initialization.
2. **`feat: correlate board evidence with safe slot occupancies`** — database constraints, canonical schemas, arrival/evidence state machine, complete correlation checks, and core domain tests.
3. **`feat: add immutable reviews and replayable event quarantine`** — review idempotency, release, event journal, replay, audit, stale-slot/duplicate/concurrency tests.
4. **`feat: generate synthetic AOI evidence and train grouped classifier`** — deterministic OpenCV fixtures, manifests, features, board-group split, model/report persistence, inference, and ML tests.
5. **`feat: add simulated machine adapters and fault scenarios`** — CFX-inspired/M2M translations, seeded multi-line demo, fault replay cases, and adapter tests.
6. **`feat: build central verification dashboard`** — responsive UI, evidence inspector, review submission, line/slot view, quarantine replay, accessibility/error states, and browser smoke evidence.
7. **`test: add measured load validation and edge container prototype`** — load CLI/report, robustness coverage, container/Compose files, CI, and local deployment checks.
8. **`docs: publish reproducible validation and integration limits`** — actual test/model/load/browser results, architecture/API/runbook completion, screenshot if available, and precise claim boundaries.

The implementation may adjust commit boundaries to preserve coherent changes. Keep at least six substantive commits and avoid attribution trailers. Before publication, inspect staged files, check repository status, verify ignored runtime artifacts, run the required checks, and scan committed content for credentials or private environment paths. Use the authenticated user's requested public repository and confirm the remote branch contains the commit sequence.

## 17. Completion checklist

- [ ] Fresh checkout installs and starts using documented commands.
- [ ] Multi-line demo contains visible evidence, review, release, and quarantine states.
- [ ] Full correlation tuple and occupancy token guard every evidence/release mutation.
- [ ] Event and review retries are idempotent; conflicting identities cannot overwrite data.
- [ ] Site evidence and accepted reviews remain immutable.
- [ ] Readiness depends on every declared site receiving both evidence sources.
- [ ] Quarantined events preserve their original payload and can be replayed safely.
- [ ] Synthetic OpenCV images and numeric measurements have reproducible provenance.
- [ ] scikit-learn evaluation uses disjoint board groups and records actual metrics.
- [ ] Dashboard presents model suggestions separately from human decisions.
- [ ] Adapter documentation states the CFX-inspired and simulated M2M boundaries.
- [ ] Load/fault reports contain measured results and checked invariants.
- [ ] Container documentation separates local evidence from Siemens/plant validation.
- [ ] Browser smoke test covers the main review and replay flows.
- [ ] Public GitHub repository contains at least six meaningful commits and no secrets.
- [ ] Final report links the repository and states actual checks plus remaining validation limits.
