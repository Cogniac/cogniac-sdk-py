# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Python SDK for the Cogniac enterprise AI computer vision platform. Provides a client library (`cogniac` package) and CLI tools (`icogniac`, `cogupload`, `cogstats`) for interacting with the Cogniac API.

Published on PyPI as `cogniac`. Requires Python 3.11+.

## Build and Install

```bash
uv sync                                    # Development install (deps + dev tools)
uv tool install --reinstall -e .           # Install cogniac CLI globally for current user
pip install cogniac                        # From PyPI (end users)
```

## Testing

Integration tests run against a live Cogniac tenant. Requires credentials via env vars.

```bash
COG_TENANT='w26eek85g3o1' pytest tests/ -v
```

No CI/CD pipeline exists in this repo.

## Architecture

### Sync and Async APIs

The SDK provides both synchronous and asynchronous interfaces. The sync API uses `httpx.Client`; the async API uses `httpx.AsyncClient`.

**Sync**: `CogniacConnection` (cogniac.py) is the entry point. Attribute assignment on entities auto-syncs to the API via `__setattr__`.

**Async**: `AsyncCogniacConnection` (async_connection.py) is the async entry point. Created via `await AsyncCogniacConnection.create(...)`. Attribute updates use explicit `await entity.set(key=value)` instead of `__setattr__`.

Environment variables: `COG_USER`, `COG_PASS`, `COG_API_KEY`, `COG_TENANT`, `COG_URL_PREFIX` (default `https://api.cogniac.io/`).

### Entity Classes

Each API resource has a sync class and an async counterpart:

| Sync | Async | File(s) |
|------|-------|---------|
| `CogniacApplication` | `AsyncCogniacApplication` | app.py / async_app.py |
| `CogniacSubject` | `AsyncCogniacSubject` | subject.py / async_subject.py |
| `CogniacMedia` | `AsyncCogniacMedia` | media.py / async_media.py |
| `CogniacTenant` | `AsyncCogniacTenant` | tenant.py / async_tenant.py |
| `CogniacUser` | `AsyncCogniacUser` | user.py / async_user.py |
| `CogniacEdgeFlow` | `AsyncCogniacEdgeFlow` | edgeflow.py / async_edgeflow.py |
| `CogniacNetworkCamera` | `AsyncCogniacNetworkCamera` | network_camera.py / async_network_camera.py |
| `CogniacExternalResult` | `AsyncCogniacExternalResult` | external_results.py / async_external_results.py |
| `CogniacOpsReview` | `AsyncCogniacOpsReview` | ops_review.py / async_ops_review.py |

Common patterns (both sync and async):
- **Factory classmethods**: `get(connection, id)`, `get_all(connection)`, `create(connection, ...)`
- **Mutable/immutable key separation**: each class defines which attributes can be updated
- **Pagination**: sync generators / async generators using `paging.next` from API responses

Sync-only: `__setattr__` override auto-POSTs mutable attribute changes.
Async-only: explicit `await entity.set(key=value)` method (can batch multiple fields in one call).

### Media Download

Both `CogniacMedia.download()` and `AsyncCogniacMedia.download()` accept an optional `filep` argument. This must be an **open file object** (opened in `"wb"` mode), not a file path string. Passing a string will raise `AttributeError: 'str' object has no attribute 'seek'`. If `filep` is omitted, the method returns the media content as bytes.

```python
# Sync
media = cc.get_media(media_id)
with open("out.jpg", "wb") as f:
    media.download(f)

# Async
media = await AsyncCogniacMedia.get(cc, media_id)
with open("out.jpg", "wb") as f:
    await media.download(f)
```

For CLI usage, prefer `cogniac media download <media_id> -o out.jpg`.

### Error Handling and Retry

`common.py` defines three error types mapped to HTTP status codes:
- `CredentialError` (401) — triggers re-authentication (3 attempts)
- `ServerError` (5xx) — exponential backoff retry (500ms multiplier, 8 attempts)
- `ClientError` (4xx) — not retried

The `@retry` decorator from `tenacity` is used on connection and entity methods. It works transparently on both sync and async functions. Connection errors (`httpx.ConnectError`) are treated as retryable (same as server errors).

### API URL Versioning

URLs are version-prefixed (e.g., `/1/tenants`, `/21/users/current`). Connection classes strip and re-prefix versions when constructing request URLs. When adding new endpoints, follow the existing `url_prefix + "/N/" + path` pattern.

### CLI Tools (bin/)

- `icogniac` — IPython shell with pre-loaded cogniac magic commands and auto-authentication
- `cogupload` — Parallel (24-thread) media upload to a subject with infinite retry on server errors
- `cogstats` — EdgeFlow device statistics aggregation

The CLI uses the sync API only.

### Package Exports

`cogniac/__init__.py` re-exports all public classes (sync and async). New entity classes must be added there to be importable as `from cogniac import ClassName`.

## `cogniac` CLI Tool

Agent-friendly CLI. JSON output by default, `--format table` for human-readable. Auth via env vars (`COG_USER`/`COG_PASS` or `COG_API_KEY`, plus `COG_TENANT`). The tenant can also be specified per-invocation with the top-level `--tenant <tenant_id>` flag, which overrides `COG_TENANT`.

Read commands:
```
cogniac auth                    # check credentials and connectivity
cogniac tenant                  # current tenant info
cogniac tenants                 # list all authorized tenants (no COG_TENANT needed)
cogniac apps list               # list all applications
cogniac apps get <id>           # get specific application
cogniac apps leaderboard <id>   # ranked candidate-model snapshot: --set-assignment, --snapshot-type, --eval-metrics, --top, --full
cogniac apps eval-metrics <id>  # active evaluation metrics for an app (table shows weighted vs unweighted)
cogniac subjects list           # list all subjects
cogniac subjects get <uid>      # get specific subject
cogniac subjects search         # search: --prefix, --similar, --name, --ids, --limit
cogniac subjects media <uid>    # list media associations: --limit, --consensus, --probability-lower/upper
cogniac media get <id>          # get specific media metadata
cogniac media download <id>     # download media file to <id>.<ext>; use -o for custom path
cogniac media search            # search: --md5, --filename, --external-media-id, --domain-unit, --limit
cogniac edgeflows list          # list all edgeflows
cogniac edgeflows get <id>      # get specific edgeflow
cogniac edgeflows status <id>   # status events: --subsystem, --limit
cogniac cameras list            # list all cameras
cogniac cameras get <id>        # get specific camera
cogniac version                 # API version info
```

Write commands:
```
cogniac subjects create <name>              # --description, --external-id
cogniac subjects associate <uid> <media_id> # --consensus (True/False/Sidelined/None)
cogniac media upload <filename>             # --subject-uid, --external-media-id, --domain-unit, --meta-tags
```

Implementation is in `cogniac/cli.py`. Entry point registered in `pyproject.toml` via `[project.scripts]`.

## Version

Package version is set in `pyproject.toml` (`[project] version`). Bump it there for releases.
