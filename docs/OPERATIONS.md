# Running the workbench

Use Python 3.12 and uv. `uv sync --locked --extra dev` installs the recorded environment. The default runtime directory contains the SQLite database, model, JSON reports, and synthetic images. Git ignores this directory.

```sh
uv run smt-workbench demo --boards 120
uv run smt-workbench serve
```

Open http://127.0.0.1:8080. Select a board, inspect both sites, select each decision, enter a reviewer and reason, and submit. The release control emits a simulated release event after review. A release clears the active occupancy and retains inspection and review history.

`demo` trains on seed 17 and creates operational images with seed 73. Run IDs identify separate simulations. Repeating the exact same run produces duplicate event results. Use a new `--run-id` for new traffic. Do not regenerate images beneath a live workbench while an inspection process reads them.

## Separate pipeline commands

```sh
uv run smt-workbench init-db
uv run smt-workbench generate --boards 120 --seed 17
uv run smt-workbench train --boards 120 --seed 17
uv run smt-workbench simulate --run-id shift-02 --boards 12 --seed 73
uv run smt-workbench load-test --run-id load-02 --boards 100 --seed 73
```

`train` regenerates the requested training corpus before fitting. Restart the server after training because a process loads its model at startup. `load-test` uses explicitly labelled automated reviews with synthetic ground truth to exercise persistence and release. These records do not claim human verification. Training features contain image statistics and numeric measurements. They exclude board IDs, site IDs, filenames, and labels.

Use `--runtime /absolute/path` before the subcommand to isolate a run. The JSON model uses a held-out board-group split. It records train/test board IDs, confusion matrix, classification report, and feature importance. Synthetic images contain simplified cracks or highlights. Their separability limits the meaning of the resulting score.

## Event API

The interactive `/docs` page documents endpoints. `POST /api/events` accepts normalized JSON or `{"adapter":"cfx-inspired","body":EVENT}`. The adapter provides a local concept mapping. It does not implement an IPC-CFX broker, official schemas, message delivery guarantees, or a vendor machine protocol.

```json
{
  "schema_version": "1.0",
  "occurred_at": "2026-01-01T00:00:00Z",
  "event_id": "shift-02-board-01-arrival",
  "event_type": "arrival",
  "run_id": "shift-02",
  "board_id": "board-01",
  "line_id": "LINE-1",
  "buffer_id": "BUF-1",
  "slot_id": "1",
  "occupancy_id": "occ-unique-01",
  "payload": {"expected_sites": ["U1", "U2"]}
}
```

AOI payload: `site_id`, relative `image_path`, optional `sha256`. Measurement payload: `site_id`, positive finite `height_mm` and `volume_mm3`, optional `coplanarity_mm`. Release payload: `{}`. Board identity includes the run ID. The slot key includes run, line, buffer, and slot. The occupancy ID prevents stale evidence from following slot reuse. Timestamps provide source context; prerequisites determine application order.

Successful ingestion returns 200. An exact duplicate preserves the journal and returns its existing outcome. Conflicting event identity returns 409. Malformed input returns 422 without persistence. Valid events with unavailable prerequisites return 202 and enter quarantine. `POST /api/replay` retries quarantined payloads without editing their identities and increments processing attempts. Applied events remain immutable. Inspection modality replacement requires a new run or an explicit future rework design.

`POST /api/boards/{run_id}/{board_id}/review` requires a UUID `request_id`, nonempty `reviewer` and `reason`, and a `decisions` array with every site exactly once. Each decision is `false_call` or `real_defect`. The transaction checks the current board state before saving every decision and moving to REVIEWED. A same-body request ID retry returns the saved result; changed content returns 409. A review does not release the board.

## Container prototype

```sh
docker compose build
docker compose run --rm workbench demo --boards 120
docker compose up -d
```

The service runs as UID 10001, stores state in a named volume, and binds its published port to localhost. This generic Linux container illustrates an Industrial Edge deployment unit. It has no Siemens app manifest, Edge platform integration, shop-floor connectivity, certification, authentication, or TLS. Use a controlled local demo environment. Only load model artifacts produced locally: joblib model deserialization executes Python code.

## Boundaries and next checks

SQLite serializes writers with `BEGIN IMMEDIATE`. This simplifies competing slot claims and atomic review. The prototype performs local inference inside that transaction. A production throughput study would determine whether inference and persistence need separate stages. The UI loads all boards and the latest 200 journal entries. Large installations need pagination, retention, identity management, access control, and a real message transport.

The prototype never sends machine-control commands. Plant trials need real machine adapters, calibrated measurement data, external operator identities, safety and cybersecurity review, site-specific validation, model monitoring, and labelled production evaluation.
