# FastAPI and SQLite work-order example

This example is a small local work-order service. It has no external network
dependency and uses FastAPI's in-process test client.

Seed the fictional toy database explicitly before the first campaign:

~~~bash
python -m live_runtime_rig_examples.fastapi_sqlite.seed --database var/work_orders.db
~~~

Run the passing campaign from the repository root:

~~~bash
python -m live_runtime_rig --config examples/fastapi_sqlite/.env.example --public-safe
~~~

**EXPECTED DEMONSTRATION FAILURE — EXITS WITH STATUS 1 BY DESIGN**

~~~bash
python -m live_runtime_rig --config examples/fastapi_sqlite/intentional-failure.env --public-safe
~~~

The database and runtime adapters do not initialize or migrate the durable
store. Explicit setup ensures the campaign's verified pre-write backup captures
the true starting state. The SQLite adapter uses the native backup API and
returns a structured file proof that the runner independently verifies against
the exact destination bytes and an integrity check.

The lifecycle case creates one marked work order, reads it back, updates it,
archives it, verifies event and audit rows, and registers each discovered
resource in the cleanup manifest immediately after its successful mutation.
No cleanup runs automatically.