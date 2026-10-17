"""Deterministic multi-line traffic and fault injection through production services."""
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5
from .schemas import Event, Review
from .synthetic import generate
from .service import Conflict


def simulate(service, *, run_id="demo", boards=12, seed=73, faults=True, auto_review=False):
    if not 1 <= boards <= 1000:
        raise ValueError("boards must be between 1 and 1000")
    manifest = generate(service.artifact_root, boards=boards, seed=seed, prefix=run_id)
    counts = {"applied": 0, "quarantined": 0, "duplicate": 0, "conflict": 0}
    started = __import__("time").perf_counter()
    all_events = []
    for i in range(boards):
        rows = manifest["records"][i * 2:i * 2 + 2]
        base = dict(run_id=run_id, board_id=rows[0]["board_id"], line_id=f"LINE-{i % 3 + 1}",
                    buffer_id="BUF-1", slot_id=str(i // 3 + 1), occupancy_id=f"OCC-{run_id}-{i}",
                    occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        arrival = Event(**base, event_id=f"{run_id}-{i}-arrival", event_type="arrival", payload={"expected_sites": ["U1", "U2"]})
        inspections = []
        for row in rows:
            inspections += [Event(**base, event_id=f"{run_id}-{i}-{row['site_id']}-aoi", event_type="aoi",
                                 payload={k: row[k] for k in ("site_id", "image_path", "sha256")}),
                            Event(**base, event_id=f"{run_id}-{i}-{row['site_id']}-3d", event_type="measurement",
                                  payload={k: row[k] for k in ("site_id", "height_mm", "volume_mm3")})]
        events = [inspections[0], arrival, *inspections[1:]] if faults and i % 3 == 0 else [arrival, *inspections]
        for event in events:
            result = service.ingest(event)
            counts[result["status"]] += 1
            all_events.append(event)
        if faults:
            counts[service.ingest(arrival)["status"]] += 1
        for result in service.replay():
            counts[result["status"]] += 1
        if auto_review:
            service.review(run_id, base["board_id"], Review(
                request_id=uuid5(NAMESPACE_URL, base["board_id"]), reviewer="synthetic-load-agent",
                reason="Automated synthetic load exercise; no human decision claimed",
                decisions=[{"site_id": r["site_id"], "decision": r["label"]} for r in rows]))
            release = Event(**base, event_id=f"{run_id}-{i}-release", event_type="release")
            counts[service.ingest(release)["status"]] += 1
        if (i + 1) % 25 == 0:
            print(f"simulated {i + 1}/{boards} boards", flush=True)
    if faults:
        bad = all_events[0].model_copy(update={"occupancy_id": "STALE-OCCUPANCY"})
        try:
            service.ingest(bad)
        except Conflict:
            counts["conflict"] += 1
    elapsed = __import__("time").perf_counter() - started
    snapshot = service.snapshot(run_id)
    expected_state = "RELEASED" if auto_review else "READY_FOR_REVIEW"
    ready = sum(b["state"] == expected_state for b in snapshot["boards"])
    report = {"run_id": run_id, "boards": boards, "seed": seed, "faults": faults,
              "auto_review": auto_review, "expected_state": expected_state, "matching_boards": ready,
              "counts": counts, "elapsed_seconds": elapsed, "events_per_second": len(all_events) / elapsed,
              "passed": ready == boards, "synthetic_only": True}
    return report
