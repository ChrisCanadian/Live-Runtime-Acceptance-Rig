# Contributing

Thank you for helping improve the project.

## Principles

- Keep the framework small and adapter-neutral.
- Require explicit PASS, FAIL, or SKIP results.
- Verify durable effects instead of trusting response text alone.
- Preserve the backup-before-write boundary.
- Never add broad cleanup behavior.
- Keep examples fictional or openly publishable.
- Do not contribute production evidence, private routes, secrets, or user data.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```

Run the passing campaign and the expected demonstration failure:

```bash
python -m live_runtime_rig --config examples/fastapi_sqlite/.env.example --public-safe
python -m live_runtime_rig --config examples/fastapi_sqlite/intentional-failure.env --public-safe
```

The first command must exit `0`. The second must complete the framework, write
evidence, mark the deliberate check `FAIL`, and exit `1`.

## Pull requests

Describe:

- the acceptance or safety problem addressed;
- exact behavior before and after;
- tests added;
- evidence/publication review performed;
- any compatibility impact.

Small, focused changes are preferred.
