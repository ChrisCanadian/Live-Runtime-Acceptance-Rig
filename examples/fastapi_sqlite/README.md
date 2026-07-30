# FastAPI and SQLite work-order example

This example is a small local work-order service. It has no external network
dependency and uses FastAPI's in-process test client.

Run the passing campaign from the repository root:

```bash
python -m live_runtime_rig --config examples/fastapi_sqlite/.env.example --public-safe
```

**EXPECTED DEMONSTRATION FAILURE — EXITS WITH STATUS 1 BY DESIGN**

```bash
python -m live_runtime_rig --config examples/fastapi_sqlite/intentional-failure.env --public-safe
```

The database adapter creates the local toy fixture if it does not exist. It then
uses SQLite's native backup API and verifies the backup before the application
cases perform writes.

The lifecycle case creates one marked work order, reads it back, updates it,
archives it, verifies event and audit rows, and records each created resource in
the cleanup manifest. No cleanup runs automatically.
