"""Executable acceptance cases for correlation, audit, replay and synthetic ML."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from smt_workbench.app import create_app
from smt_workbench.db import Database
from smt_workbench.ml import load_predictor, train
from smt_workbench.schemas import Event, Review
from smt_workbench.service import Conflict, Workbench
from smt_workbench.simulator import simulate
from smt_workbench.synthetic import generate


@pytest.fixture
def service(tmp_path):
    artifacts = tmp_path / "artifacts"
    generate(artifacts, boards=2, prefix="fixture")
    return Workbench(
        Database(tmp_path / "db.sqlite"),
        artifacts,
        lambda image, measurement: {"label": "false_call", "confidence": 0.75},
    )


def event(kind="arrival", event_id=None, board="B1", occupancy="O1", **payload):
    return Event(
        event_id=event_id or str(uuid4()),
        event_type=kind,
        run_id="r1",
        board_id=board,
        line_id="L1",
        buffer_id="BUF",
        slot_id="1",
        occupancy_id=occupancy,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        payload=payload,
    )


def complete(service, board="B1", occupancy="O1"):
    service.ingest(event(board=board, occupancy=occupancy))
    for i in (1, 2):
        service.ingest(
            event(
                "aoi", board=board, occupancy=occupancy, site_id=f"U{i}", image_path=f"fixture/00000-U{i}.png"
            )
        )
        service.ingest(
            event(
                "measurement",
                board=board,
                occupancy=occupancy,
                site_id=f"U{i}",
                height_mm=0.5,
                volume_mm3=0.12,
            )
        )


def review(**overrides):
    return Review(
        **(
            {
                "request_id": uuid4(),
                "reviewer": "operator",
                "reason": "Inspected AOI and 3D evidence",
                "decisions": [{"site_id": s, "decision": "false_call"} for s in ("U1", "U2")],
            }
            | overrides
        )
    )


def test_duplicate_and_hash_conflict(service):
    e = event()
    assert service.ingest(e)["status"] == "applied"
    assert service.ingest(e)["status"] == "duplicate"
    with pytest.raises(Conflict):
        service.ingest(e.model_copy(update={"occupancy_id": "OTHER"}))
    assert len(service.snapshot()["boards"]) == 1


def test_quarantine_retry_does_not_count_without_replay(service):
    e = event("measurement", site_id="U1", height_mm=0.4, volume_mm3=0.1)
    assert service.ingest(e)["status"] == "quarantined"
    service.ingest(e)
    assert service.snapshot()["events"][0]["attempts"] == 1
    service.ingest(event())
    assert service.replay()[0]["status"] == "applied"
    saved = next(r for r in service.snapshot()["events"] if r["event_id"] == e.event_id)
    assert saved["attempts"] == 2


def test_review_atomic_and_idempotent(service):
    complete(service)
    with pytest.raises(Conflict):
        service.review("r1", "B1", review(decisions=[{"site_id": "U1", "decision": "false_call"}]))
    assert service.snapshot()["boards"][0]["state"] == "READY_FOR_REVIEW"
    body = review()
    assert service.review("r1", "B1", body)["state"] == "REVIEWED"
    assert service.review("r1", "B1", body)["duplicate"]
    with pytest.raises(Conflict):
        service.review("r1", "B1", body.model_copy(update={"reason": "changed"}))
    with pytest.raises(Conflict):
        service.review("r1", "B1", review())


def test_stale_release_cannot_clear_new_occupant(service):
    complete(service)
    service.review("r1", "B1", review())
    service.ingest(event("release"))
    service.ingest(event(board="B2", occupancy="O2"))
    assert service.ingest(event("release"))["status"] == "quarantined"
    with pytest.raises(Conflict):
        service.ingest(
            event("measurement", board="B2", occupancy="O1", site_id="U1", height_mm=0.5, volume_mm3=0.1)
        )
    with service.db.connect() as c:
        assert c.execute("SELECT board_id,occupancy_id FROM slots").fetchone()["board_id"] == "B2"


def test_concurrent_slot_claim_has_one_winner(service):
    events = [event(board=f"B{i}", occupancy=f"O{i}") for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(service.ingest, events))
    assert sum(r["status"] == "applied" for r in results) == 1
    assert sum(r["status"] == "quarantined" for r in results) == 7


def test_cross_run_identity_does_not_collide(service):
    service.ingest(event())
    service.ingest(event().model_copy(update={"run_id": "r2"}))
    assert len(service.snapshot()["boards"]) == 2


def test_unexpected_site_does_not_mutate(service):
    service.ingest(event())
    with pytest.raises(Conflict):
        service.ingest(event("measurement", site_id="U9", height_mm=0.5, volume_mm3=0.1))
    assert all(s["measurement"] is None for s in service.snapshot()["boards"][0]["sites"])


@pytest.mark.parametrize(
    "payload",
    [{"image_path": "../outside.png"}, {"image_path": "/etc/passwd"}, {"image_path": "missing.png"}],
)
def test_path_traversal_blocked(service, payload):
    with pytest.raises(ValueError):
        service.ingest(event("aoi", site_id="U1", **payload))
    assert service.snapshot()["events"] == []


def test_checksum_and_nonfinite_rejected(service):
    with pytest.raises(ValueError):
        service.ingest(event("aoi", site_id="U1", image_path="fixture/00000-U1.png", sha256="bad"))
    with pytest.raises(ValueError):
        service.ingest(event("measurement", site_id="U1", height_mm=float("nan"), volume_mm3=0.1))


def test_api_semantics_and_static_ui(tmp_path):
    client = TestClient(create_app(tmp_path))
    e = event()
    assert client.post("/api/events", json=e.model_dump(mode="json")).status_code == 200
    assert (
        client.post(
            "/api/events", json=e.model_copy(update={"board_id": "changed"}).model_dump(mode="json")
        ).status_code
        == 409
    )
    assert client.post("/api/events", json={"event_type": "bad"}).status_code == 422
    early = event("release")
    assert client.post("/api/events", json=early.model_dump(mode="json")).status_code == 202
    assert client.post("/api/replay", content="{}", headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.get("/api/health").json()["synthetic_only"]
    assert "One view. Every board." in client.get("/").text


def test_real_training_split_and_load(tmp_path):
    root = tmp_path / "artifacts"
    manifest = generate(root, boards=32, seed=17)
    model_path = tmp_path / "model.joblib"
    report = train(root, manifest, model_path)
    assert not set(report["train_boards"]) & set(report["test_boards"])
    assert report["test_samples"] == 16
    assert not any("label" in name or "board" in name for name in report["feature_names"])
    predictor = load_predictor(model_path)
    result = predictor(root / manifest["records"][0]["image_path"], manifest["records"][0])
    assert result["label"] in ("false_call", "real_defect")
    assert 0 <= result["confidence"] <= 1
    service = Workbench(Database(tmp_path / "db.sqlite"), root, predictor)
    simulation = simulate(service, boards=6, run_id="load-test", seed=73, auto_review=True)
    assert simulation["passed"]
    assert simulation["counts"]["quarantined"] == 2
    assert simulation["counts"]["conflict"] == 1
    with service.db.connect() as c:
        assert c.execute("SELECT count(*) FROM slots").fetchone()[0] == 0
    (tmp_path / "evidence.json").write_text(json.dumps(simulation))


def test_missing_model_preserves_evidence_and_allows_review(service):
    service.predictor = None
    complete(service)
    board = service.snapshot()["boards"][0]
    assert board["state"] == "READY_FOR_REVIEW"
    assert all(s["measurement"] and s["image_path"] for s in board["sites"])
    assert all(s["prediction"]["status"] == "unavailable" for s in board["sites"])
    assert all("confidence" not in s["prediction"] for s in board["sites"])
    service.review("r1", "B1", review())


def test_duplicate_does_not_repeat_audit_and_deleted_image_is_still_duplicate(service):
    arrival = event()
    service.ingest(arrival)
    e = event("aoi", site_id="U1", image_path="fixture/00000-U1.png")
    service.ingest(e)
    before = len(service.snapshot()["audit"])
    (service.artifact_root / e.payload["image_path"]).unlink()
    assert service.ingest(e)["status"] == "duplicate"
    service.ingest(arrival)
    assert len(service.snapshot()["audit"]) == before


def test_naive_time_and_whitespace_review_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Event.model_validate(event().model_dump() | {"occurred_at": "2026-01-01T00:00:00"})
    with pytest.raises(ValidationError):
        review(reason="   ")
