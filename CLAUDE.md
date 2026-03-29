# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Python SDK for the Cogniac enterprise AI computer vision platform. Provides a client library (`cogniac` package) and CLI tools (`icogniac`, `cogupload`, `cogstats`) for interacting with the Cogniac API.

Published on PyPI as `cogniac`. Supports Python 2.7 and 3.x (uses `six` for compatibility).

## Build and Install

```bash
pip install -e .          # Development install
python setup.py install   # Standard install
pip install cogniac       # From PyPI
```

No test suite, linter configuration, or CI/CD pipeline exists in this repo.

## Architecture

### Connection and Authentication

`CogniacConnection` (cogniac.py) is the entry point for all API interaction. It manages authentication (username/password or API key), bearer token lifecycle, MFA/OTP handling, and HTTP session with automatic retry. All entity classes hold a `_cc` reference to the connection.

Environment variables: `COG_USER`, `COG_PASS`, `COG_API_KEY`, `COG_TENANT`, `COG_URL_PREFIX` (default `https://api.cogniac.io/`).

### Entity Classes

Each API resource is a class with the same patterns:

- **Factory classmethods** for construction: `get(connection, id)`, `get_all(connection)`, `create(connection, ...)`
- **Mutable/immutable key separation**: each class defines `mutable_keys` and `immutable_keys` lists
- **Auto-sync on set**: `__setattr__` is overridden so setting a mutable attribute immediately POSTs to the API
- **Pagination**: generator patterns using `paging.next` from API responses

Entity classes: `CogniacApplication` (app.py), `CogniacSubject` (subject.py), `CogniacMedia` (media.py), `CogniacTenant` (tenant.py), `CogniacUser` (user.py), `CogniacEdgeFlow` (edgeflow.py), `CogniacNetworkCamera` (network_camera.py), `CogniacExternalResult` (external_results.py), `CogniacOpsReview` (ops_review.py).

### Error Handling and Retry

`common.py` defines three error types mapped to HTTP status codes:
- `CredentialError` (401) — triggers re-authentication (3 attempts)
- `ServerError` (5xx) — exponential backoff retry (500ms multiplier, 8 attempts)
- `ClientError` (4xx) — not retried

The `@retry` decorator from the `retrying` library is used on connection methods. Connection errors are treated as retryable (same as server errors).

### API URL Versioning

URLs are version-prefixed (e.g., `/1/tenants`, `/21/users/current`). `CogniacConnection` strips and re-prefixes versions when constructing request URLs. When adding new endpoints, follow the existing `url_prefix + "/N/" + path` pattern.

### CLI Tools (bin/)

- `icogniac` — IPython shell with pre-loaded cogniac magic commands and auto-authentication
- `cogupload` — Parallel (24-thread) media upload to a subject with infinite retry on server errors
- `cogstats` — EdgeFlow device statistics aggregation

### Package Exports

`cogniac/__init__.py` re-exports all public classes. New entity classes must be added there to be importable as `from cogniac import ClassName`.

## Version

Package version is set in `setup.py` (line 6, `version` variable). Bump it there for releases.
