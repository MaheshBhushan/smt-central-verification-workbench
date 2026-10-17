"""Bounded concurrent localhost acceptance run. Start a trained server first."""

import argparse
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx

from smt_workbench.synthetic import generate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--runtime", type=Path, default=Path("runtime"))
    parser.add_argument("--boards", type=int, default=25)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--run-id", default="http-acceptance")
    parser.add_argument("--output", type=Path, default=Path("runtime/http-report.json"))
    args = parser.parse_args()
    if not 1 <= args.boards <= 1000 or not 1 <= args.concurrency <= 16:
        parser.error("boards must be 1–1000 and concurrency 1–16")
    records = generate(args.runtime / "artifacts", boards=args.boards, seed=91, prefix=args.run_id)["records"]
    requests = []
    latencies = []
    statuses = Counter()
    checks = {}
    with httpx.Client(base_url=args.url, timeout=30) as client:
        assert client.get("/api/health").json()["model_loaded"], "train and restart server first"

        def post(url, payload, expected=200):
            start = time.perf_counter()
            response = client.post(url, json=payload)
            duration = time.perf_counter() - start
            return response, duration, expected

        def record(result):
            response, duration, expected = result
            latencies.append(duration * 1000)
            statuses[response.status_code] += 1
            assert response.status_code == expected, (response.status_code, response.text)
            return response

        def phase(name, jobs):
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                for result in pool.map(lambda job: post(*job), jobs):
                    record(result)
            print(f"HTTP phase {name}: {len(jobs)} requests completed", flush=True)

        for index in range(args.boards):
            rows = records[index * 2 : index * 2 + 2]
            base = {
                "schema_version": "1.0",
                "occurred_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                "run_id": args.run_id,
                "board_id": rows[0]["board_id"],
                "line_id": f"LINE-{index % 3 + 1}",
                "buffer_id": "BUF-HTTP",
                "slot_id": str(index),
                "occupancy_id": f"{args.run_id}-occ-{index}",
            }
            arrival = base | {
                "event_id": f"{args.run_id}-{index}-arrival",
                "event_type": "arrival",
                "payload": {"expected_sites": ["U1", "U2"]},
            }
            evidence = []
            for row in rows:
                for kind, fields in (
                    ("aoi", ("site_id", "image_path", "sha256")),
                    ("measurement", ("site_id", "height_mm", "volume_mm3")),
                ):
                    evidence.append(
                        base
                        | {
                            "event_id": f"{args.run_id}-{index}-{row['site_id']}-{kind}",
                            "event_type": kind,
                            "payload": {k: row[k] for k in fields},
                        }
                    )
            requests.append((base, rows, arrival, evidence))
        started = time.perf_counter()
        early = record(post("/api/events", requests[0][3][0], 202))
        checks["out_of_order_quarantined"] = early.json()["status"] == "quarantined"
        phase("arrivals", [("/api/events", item[2]) for item in requests])
        replay = record(post("/api/replay", {})).json()
        checks["replay_recovered"] = any(r["status"] == "applied" for r in replay["results"])
        phase("evidence", [("/api/events", e) for item in requests for e in item[3]])
        duplicate = record(post("/api/events", requests[0][2])).json()
        checks["duplicate"] = duplicate["status"] == "duplicate"
        record(post("/api/events", requests[0][2] | {"occupancy_id": "changed"}, 409))
        record(post("/api/events", {"event_type": "invalid"}, 422))
        jobs = []
        for base, rows, _, _ in requests:
            jobs.append(
                (
                    f"/api/boards/{args.run_id}/{base['board_id']}/review",
                    {
                        "request_id": str(uuid5(NAMESPACE_URL, base["board_id"])),
                        "reviewer": "HTTP synthetic load agent",
                        "reason": "Automated load exercise; no human review claimed",
                        "decisions": [{"site_id": r["site_id"], "decision": r["label"]} for r in rows],
                    },
                )
            )
        phase("reviews", jobs)
        phase(
            "releases",
            [
                (
                    "/api/events",
                    item[0]
                    | {"event_id": f"{args.run_id}-{i}-release", "event_type": "release", "payload": {}},
                )
                for i, item in enumerate(requests)
            ],
        )
        state = client.get("/api/state", params={"run_id": args.run_id}).json()
        checks["all_released"] = len(state["boards"]) == args.boards and all(
            b["state"] == "RELEASED" for b in state["boards"]
        )
        checks["reviews_retained"] = all(b["review"] for b in state["boards"])
        elapsed = time.perf_counter() - started
    ordered = sorted(latencies)
    percentile = lambda p: ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p))]
    report = {
        "synthetic_only": True,
        "transport": "real localhost HTTP",
        "run_id": args.run_id,
        "boards": args.boards,
        "concurrency": args.concurrency,
        "requests": len(latencies),
        "status_counts": dict(statuses),
        "elapsed_seconds": elapsed,
        "requests_per_second": len(latencies) / elapsed,
        "latency_ms": {"p50": percentile(0.5), "p95": percentile(0.95), "p99": percentile(0.99)},
        "checks": checks,
        "passed": all(checks.values()),
        "method": "Unique slots; phase barriers: arrival/evidence/review/release. Timed POSTs include expected fault requests. Generation and health check excluded.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
