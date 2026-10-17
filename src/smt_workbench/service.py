"""Correlation state machine. Never infer board identity from the current slot."""

import hashlib
import json
from pathlib import Path

from .schemas import Event, Review


class Conflict(ValueError):
    pass


class Dependency(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Workbench:
    def __init__(self, db, artifact_root: Path, predictor=None):
        self.db, self.artifact_root, self.predictor = db, artifact_root.resolve(), predictor

    def validate(self, event):
        p = event.payload
        allowed = {
            "arrival": {"expected_sites"},
            "aoi": {"site_id", "image_path", "sha256"},
            "measurement": {"site_id", "height_mm", "volume_mm3", "coplanarity_mm"},
            "release": set(),
        }
        if set(p) - allowed[event.event_type]:
            raise ValueError("unexpected payload fields")
        if event.event_type == "arrival":
            sites = p.get("expected_sites", ["U1", "U2"])
            if (
                not isinstance(sites, list)
                or not 1 <= len(sites) <= 16
                or any(not isinstance(s, str) or not s or len(s) > 80 for s in sites)
                or len(set(sites)) != len(sites)
            ):
                raise ValueError("expected_sites must contain 1–16 unique site IDs")
        if event.event_type in ("aoi", "measurement") and (
            not isinstance(p.get("site_id"), str) or not p["site_id"]
        ):
            raise ValueError("site_id is required")
        if event.event_type == "aoi":
            relative = p.get("image_path")
            if not isinstance(relative, str):
                raise ValueError("image_path is required")
            resolved = (self.artifact_root / relative).resolve()
            if (
                Path(relative).is_absolute()
                or not resolved.is_relative_to(self.artifact_root)
                or not resolved.is_file()
                or resolved.suffix.lower() != ".png"
            ):
                raise ValueError("image must be a PNG inside the artifact directory")
            import cv2

            if cv2.imread(str(resolved)) is None:
                raise ValueError("image cannot be decoded")
            with resolved.open("rb") as image_file:
                if image_file.read(8) != b"\x89PNG\r\n\x1a\n":
                    raise ValueError("image is not a PNG")
            if p.get("sha256") and hashlib.sha256(resolved.read_bytes()).hexdigest() != p["sha256"]:
                raise ValueError("image checksum mismatch")
        if event.event_type == "measurement":
            import math

            for key in ("height_mm", "volume_mm3", *(["coplanarity_mm"] if "coplanarity_mm" in p else [])):
                value = p.get(key)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (float, int))
                    or not math.isfinite(value)
                    or (value < 0 if key == "coplanarity_mm" else value <= 0)
                ):
                    raise ValueError(f"{key} must be a finite positive number")

    def ingest(self, event: Event, *, replay=False):
        body = canonical(event.model_dump(mode="json"))
        digest = hashlib.sha256(body.encode()).hexdigest()
        with self.db.connect() as c:
            old = c.execute("SELECT * FROM events WHERE event_id=?", (event.event_id,)).fetchone()
            if old:
                if old["digest"] != digest:
                    raise Conflict("event_id already has a different payload")
                if old["status"] == "applied":
                    return {"status": "duplicate", "event_id": event.event_id}
                if not replay:
                    return {"status": "quarantined", "reason": old["reason"], "event_id": event.event_id}
                c.execute("UPDATE events SET attempts=attempts+1 WHERE event_id=?", (event.event_id,))
            else:
                self.validate(event)
                c.execute(
                    "INSERT INTO events(event_id,digest,body,status) VALUES(?,?,?,'pending')",
                    (event.event_id, digest, body),
                )
            if replay:
                self.validate(event)
            before = c.execute(
                "SELECT state FROM boards WHERE run_id=? AND board_id=?", (event.run_id, event.board_id)
            ).fetchone()
            # Savepoint preserves the journal while rolling back every failed projection.
            c.execute("SAVEPOINT projection")
            try:
                self._apply(c, event)
            except Dependency as exc:
                c.execute("ROLLBACK TO projection")
                c.execute(
                    "UPDATE events SET status='quarantined',reason=? WHERE event_id=?",
                    (str(exc), event.event_id),
                )
                self._audit(
                    c,
                    event.run_id,
                    event.board_id,
                    "replay_quarantined" if replay else "quarantined",
                    event.event_id,
                    str(exc),
                )
                return {"status": "quarantined", "reason": str(exc), "event_id": event.event_id}
            c.execute("UPDATE events SET status='applied',reason=NULL WHERE event_id=?", (event.event_id,))
            after = c.execute(
                "SELECT state FROM boards WHERE run_id=? AND board_id=?", (event.run_id, event.board_id)
            ).fetchone()
            self._audit(
                c,
                event.run_id,
                event.board_id,
                "replay_applied" if replay else event.event_type,
                event.event_id,
                f"{before['state'] if before else 'NEW'} -> {after['state']}",
            )
        return {"status": "applied", "event_id": event.event_id}

    @staticmethod
    def _audit(c, run_id, board_id, action, reference_id, detail):
        c.execute(
            "INSERT INTO audit_log(run_id,board_id,action,reference_id,detail) VALUES(?,?,?,?,?)",
            (run_id, board_id, action, reference_id, detail),
        )

    def _apply(self, c, e):
        key = (e.run_id, e.board_id)
        b = c.execute("SELECT * FROM boards WHERE run_id=? AND board_id=?", key).fetchone()
        identity = (e.line_id, e.buffer_id, e.slot_id, e.occupancy_id)
        if b and tuple(b[k] for k in ("line_id", "buffer_id", "slot_id", "occupancy_id")) != identity:
            raise Conflict("board identity does not match its original occupancy")
        if e.event_type == "arrival":
            if b:
                raise Conflict("board already arrived under another event_id")
            slot = (e.run_id, e.line_id, e.buffer_id, e.slot_id)
            if c.execute(
                "SELECT 1 FROM slots WHERE run_id=? AND line_id=? AND buffer_id=? AND slot_id=?", slot
            ).fetchone():
                raise Dependency("slot is occupied")
            if c.execute(
                "SELECT 1 FROM boards WHERE run_id=? AND occupancy_id=?", (e.run_id, e.occupancy_id)
            ).fetchone():
                raise Conflict("occupancy_id has already been used")
            expected = e.payload.get("expected_sites", ["U1", "U2"])
            c.execute(
                "INSERT INTO boards VALUES(?,?,?,?,?,?,'COLLECTING',?)",
                (*key, *identity, canonical(expected)),
            )
            c.execute("INSERT INTO slots VALUES(?,?,?,?,?,?)", (*slot, e.board_id, e.occupancy_id))
            c.executemany(
                "INSERT INTO sites(run_id,board_id,site_id) VALUES(?,?,?)", [(*key, s) for s in expected]
            )
            return
        if not b:
            raise Dependency("board has not arrived")
        if e.event_type == "release":
            if b["state"] != "REVIEWED":
                raise Dependency("board must be reviewed before release")
            c.execute("DELETE FROM slots WHERE run_id=? AND occupancy_id=?", (e.run_id, e.occupancy_id))
            c.execute("UPDATE boards SET state='RELEASED' WHERE run_id=? AND board_id=?", key)
            return
        if b["state"] == "RELEASED":
            raise Dependency("stale evidence belongs to a released occupancy")
        if b["state"] != "COLLECTING":
            raise Conflict("inspection is immutable after collection")
        site_key = (*key, e.payload["site_id"])
        s = c.execute("SELECT * FROM sites WHERE run_id=? AND board_id=? AND site_id=?", site_key).fetchone()
        if not s:
            raise Conflict("site is not in the board's expected site list")
        field = "image_path" if e.event_type == "aoi" else "measurement"
        if s[field] is not None:
            raise Conflict("site modality already recorded under another event_id")
        value = (
            e.payload["image_path"]
            if field == "image_path"
            else canonical(
                {k: e.payload[k] for k in ("height_mm", "volume_mm3", "coplanarity_mm") if k in e.payload}
            )
        )
        c.execute(
            f"UPDATE sites SET {field}=? WHERE run_id=? AND board_id=? AND site_id=?", (value, *site_key)
        )
        updated = c.execute(
            "SELECT * FROM sites WHERE run_id=? AND board_id=? AND site_id=?", site_key
        ).fetchone()
        if updated["image_path"] and updated["measurement"]:
            if self.predictor is None:
                prediction = {"label": "unavailable", "status": "unavailable", "reason": "No model loaded"}
            else:
                try:
                    prediction = self.predictor(
                        self.artifact_root / updated["image_path"], json.loads(updated["measurement"])
                    )
                except (ValueError, OSError):
                    prediction = {
                        "label": "unavailable",
                        "status": "error",
                        "reason": "Local inference failed",
                    }
            c.execute(
                "UPDATE sites SET prediction=? WHERE run_id=? AND board_id=? AND site_id=?",
                (canonical(prediction), *site_key),
            )
        missing = c.execute(
            "SELECT count(*) FROM sites WHERE run_id=? AND board_id=? AND prediction IS NULL", key
        ).fetchone()[0]
        if not missing:
            c.execute("UPDATE boards SET state='READY_FOR_REVIEW' WHERE run_id=? AND board_id=?", key)

    def review(self, run_id: str, board_id: str, review: Review):
        with self.db.connect() as c:
            key = (run_id, board_id)
            prior = c.execute(
                "SELECT * FROM reviews WHERE request_id=?", (str(review.request_id),)
            ).fetchone()
            body = canonical(review.model_dump(mode="json"))
            if prior:
                if prior["body"] != body or (prior["run_id"], prior["board_id"]) != key:
                    raise Conflict("request_id already has a different review")
                return {"state": "REVIEWED", "duplicate": True}
            b = c.execute("SELECT * FROM boards WHERE run_id=? AND board_id=?", key).fetchone()
            if not b or b["state"] != "READY_FOR_REVIEW":
                raise Conflict("board is not ready for review")
            expected = set(json.loads(b["expected_sites"]))
            if len(review.decisions) != len(expected) or {d.site_id for d in review.decisions} != expected:
                raise Conflict("review must cover every expected site exactly once")
            c.execute(
                "INSERT INTO reviews(run_id,board_id,operator,note,decisions,request_id,body) VALUES(?,?,?,?,?,?,?)",
                (
                    *key,
                    review.reviewer,
                    review.reason,
                    canonical([d.model_dump() for d in review.decisions]),
                    str(review.request_id),
                    body,
                ),
            )
            c.execute("UPDATE boards SET state='REVIEWED' WHERE run_id=? AND board_id=?", key)
            self._audit(c, run_id, board_id, "review", str(review.request_id), review.reviewer)
        return {"state": "REVIEWED"}

    def replay(self):
        with self.db.connect() as c:
            events = [
                Event.model_validate_json(r[0])
                for r in c.execute(
                    "SELECT body FROM events WHERE status='quarantined' ORDER BY received_at,event_id"
                )
            ]
        results = []
        for event in events:
            try:
                results.append(self.ingest(event, replay=True))
            except Conflict as exc:
                results.append({"event_id": event.event_id, "status": "conflict", "reason": str(exc)})
        return results

    def snapshot(self, run_id=None):
        with self.db.connect() as c:
            clause, args = (" WHERE run_id=?", (run_id,)) if run_id else ("", ())
            boards = [
                dict(r)
                for r in c.execute("SELECT * FROM boards" + clause + " ORDER BY run_id,board_id", args)
            ]
            for b in boards:
                key = (b["run_id"], b["board_id"])
                b["expected_sites"] = json.loads(b["expected_sites"])
                b["sites"] = [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM sites WHERE run_id=? AND board_id=? ORDER BY site_id", key
                    )
                ]
                for s in b["sites"]:
                    for field in ("measurement", "prediction"):
                        s[field] = json.loads(s[field]) if s[field] else None
                review = c.execute("SELECT * FROM reviews WHERE run_id=? AND board_id=?", key).fetchone()
                b["review"] = dict(review) if review else None
            events = [
                dict(r)
                for r in c.execute(
                    "SELECT event_id,status,reason,attempts,received_at FROM events ORDER BY received_at DESC LIMIT 200"
                )
            ]
            audit = [dict(r) for r in c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200")]
        return {"boards": boards, "events": events, "audit": audit}
