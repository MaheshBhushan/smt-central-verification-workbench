# SMT workbench execution gates

Detailed contract: [Implementation handoff](../../docs/IMPLEMENTATION_HANDOFF.md).

The package is a local Python/FastAPI/SQLite service with a native browser dashboard. All inspection and machine evidence is synthetic. CFX-inspired JSON and generic containers do not establish protocol qualification or Siemens deployment validation.

## Ordered work

1. **Scaffold and persistence.** Installable package, configuration, idempotent schema, CLI help. Gate: fresh installation and database reopening work.
2. **Correlation and workflow.** Board/run key, complete line/buffer/slot tuple, unique occupancy token, immutable AOI/3D evidence, readiness. Gate: duplicates, slot collision, unknown site, and stale occupancy cannot corrupt state.
3. **Review and quarantine.** Atomic whole-board review, review idempotency, release, event journal, audit, replay. Gate: out-of-order recovery applies once; stale evidence remains quarantined; concurrent arrivals preserve one occupant.
4. **Synthetic data and ML.** Seeded OpenCV images, noisy 3D values, manifest hashes, board-group split, classifier, persisted provenance/report. Gate: reproducibility, disjoint groups, valid actual metrics, and stable reload predictions.
5. **Adapters and simulator.** CFX-inspired and M2M translations, multi-line seeded scenario, fault scenarios. Gate: adapters preserve complete identity and use the same domain service.
6. **Browser workflow.** Line/slot grid, evidence inspector, review controls, quarantine replay, accessible responsive states. Gate: real browser completes review and recoverable replay.
7. **Load and edge prototype.** Bounded HTTP load generator, JSON report, container/Compose, CI. Gate: expected counts, zero unexpected errors, measured percentiles, documented container result.
8. **Evidence and publication.** Complete README/API/architecture/model/validation/edge docs. Gate: actual checks recorded; no production/certification claim; public remote contains at least six meaningful implementation commits.

## Execution rules

- Preserve unrelated work and keep implementation aligned with the handoff's identity invariants.
- Run long builds, tests, training, and load jobs through tracked background execution.
- Give jobs progress output and inspect their native status within the first minute.
- Do not commit runtime databases, model blobs, large generated datasets, credentials, or private paths.
- Do not reset existing runtime data implicitly; create a fresh run ID.
- Record actual metrics and failed or unperformed checks honestly.
- Keep Git commits coherent. The handoff proposes eight substantive milestones.

## Completion evidence

Record the final test command/result, model report path and metrics, load command/report and counts, browser actions, container check result, public repository URL, and committed milestone count in `docs/validation.md` or the final delivery report.
