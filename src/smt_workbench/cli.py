"""Reproducible commands with generated data confined to an ignored runtime."""
import argparse
import json
from pathlib import Path
from .db import Database
from .ml import load_predictor, train
from .service import Workbench
from .synthetic import generate
from .simulator import simulate


def main():
    parser = argparse.ArgumentParser(description="Synthetic SMT verification prototype")
    parser.add_argument("--runtime", type=Path, default=Path("runtime"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db")
    for name in ("generate", "train", "simulate", "load-test", "demo"):
        sub = commands.add_parser(name)
        sub.add_argument("--boards", type=int, default=120 if name in ("generate", "train") else 12)
        sub.add_argument("--seed", type=int, default=17 if name in ("generate", "train") else 73)
        sub.add_argument("--run-id", default="demo" if name != "load-test" else "load")
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    root = args.runtime.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.command == "serve":
        import uvicorn
        from .app import create_app
        uvicorn.run(create_app(root), host=args.host, port=args.port)
        return
    db = Database(root / "workbench.db")
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    model_path = root / "model.joblib"
    if args.command == "init-db":
        result = {"database": str(db.path)}
    elif args.command in ("generate", "train", "demo"):
        if not 8 <= args.boards <= 1000:
            parser.error("training requires 8–1000 boards")
        manifest = generate(artifacts, boards=args.boards, seed=17 if args.command == "demo" else args.seed)
        result = {"boards": manifest["boards"], "samples": len(manifest["records"])}
        if args.command != "generate":
            result = train(artifacts, manifest, model_path)
        if args.command == "demo":
            result = simulate(Workbench(db, artifacts, load_predictor(model_path)), run_id=args.run_id,
                              boards=12, seed=args.seed)
    else:
        if not model_path.exists():
            parser.error("run train or demo first")
        result = simulate(Workbench(db, artifacts, load_predictor(model_path)), run_id=args.run_id,
                          boards=args.boards, seed=args.seed, auto_review=args.command == "load-test")
    (root / f"{args.command}-report.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)
    if result.get("passed") is False:
        raise SystemExit(1)
