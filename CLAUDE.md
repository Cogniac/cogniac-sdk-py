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

The coverage suite (`tests/test_coverage_smoke.py` / `tests/test_coverage_live.py`) keeps a few conventions:
- **Smoke (no creds)** walks the built parser and asserts every command resolves to a handler, and that every `args.<x>` a handler reads is a dest its command actually defines — a mechanical check that catches handler/parser attribute mismatches. Pagination generators are exercised against a mocked transport (empty/`null` response, bare list, paging envelope, client-side limit); pure existence checks miss those.
- **Live (`@requires_live`, read-only)** does one round-trip per resource group. Skip on 403 (and on a documented 404/405 only where "not configured / not allowed on this backend" is legitimate), but let an unexpected 404 **fail** — a stray 404 usually means a wrong path and must not masquerade as "not permitted." Don't burn API calls before an unconditional skip — mark the whole test `@pytest.mark.skip`. Destructive operations (create/delete, EdgeFlow device-control events) are not invoked live.

## Architecture

### Sync and Async APIs

The SDK provides both synchronous and asynchronous interfaces. The sync API uses `httpx.Client`; the async API uses `httpx.AsyncClient`.

**Sync**: `CogniacConnection` (cogniac.py) is the entry point. Attribute assignment on entities auto-syncs to the API via `__setattr__`.

**Async**: `AsyncCogniacConnection` (async_connection.py) is the async entry point. Created via `await AsyncCogniacConnection.create(...)`. Attribute updates use explicit `await entity.set(key=value)` instead of `__setattr__`.

Environment variables: `COG_USER`, `COG_PASS`, `COG_API_KEY`, `COG_TENANT`, `COG_URL_PREFIX` (default `https://api.cogniac.io/`).

### Credential sources and precedence

Both connection classes resolve a credential in this order (first match wins):
1. explicit `api_key` constructor argument
2. explicit `username`+`password` constructor arguments
3. `COG_API_KEY` env var
4. `COG_USER`+`COG_PASS` env vars
5. stored login at `~/.config/cogniac/credentials` (written by `cogniac auth login`)

The stored credential is a tenant-less, per-user API key consumed exactly like `COG_API_KEY` (the SDK trades it for per-tenant tokens and re-mints on 401). When it is the active source, its recorded `url_prefix` is also adopted (unless `url_prefix`/`COG_URL_PREFIX` is set explicitly). `credentials.py` is the store (XDG-aware, 0600); `auth_login.py` implements the RFC 8252 browser-loopback flow (`cogniac auth login`/`auth logout` in the CLI). See CloudCore-Product#1026 — this is the Phase 1 CLI/SDK side (`state` CSRF guard, key-in-query, no backend changes; Phase 2 adds PKCE + a one-time-code exchange).

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
- **Factory classmethods**: `get(connection, <id>)` (one), `get_all(connection, ...)` (the tenant's collection), `create(connection, ...)` with required fields as explicit keyword args. Additional explicit lookups are named `get_by_<key>` (e.g. `get_by_id`).
- **Instance lifecycle**: `update(self, body)` POSTs the body to `/N/<resource>/<id>`, refreshes the instance's attributes from the response, and returns the response JSON; `delete(self)` removes the resource.
- **Mutable/immutable key separation**: each class declares which attributes can be updated.
- **Pagination**: multi-item reads are generators that drain the API's pagination (`paging.next`, or a cursor such as a DynamoDB `last_key`) and honor `limit`/`reverse`/filter args; async counterparts are async generators. Single object/count/status reads return the value directly.
- **Method naming**: snake_case; verb-first for actions (`download_model`, `create_api_key`, `disassociate_media`), noun for reads that return a thing (`api_keys`, `events`).

Sync-only: `__setattr__` override auto-POSTs mutable attribute changes.
Async-only: explicit `await entity.set(key=value)` method (can batch multiple fields in one call); assigning a mutable attribute directly raises with a hint to use `set()`.

**Sync/async symmetry is required**: every method on a sync class has an async counterpart with the same name and signature (an async generator where the sync one is a generator). Both are re-exported from `cogniac/__init__.py` (see Package Exports). The smoke tests assert this pairing — a sync-only method is a bug.

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
- `ClientError` (4xx) — not retried, **except 429** (rate-limited): the shared `server_error` retry predicate treats a `ClientError` with `status_code == 429` as transient, so it backs off and retries like a 5xx. `raise_errors` records the server's `Retry-After` (when sent) on the exception as `retry_after`.

The `@retry` decorator from `tenacity` is used on connection and entity methods. It works transparently on both sync and async functions. Connection errors (`httpx.ConnectError`) are treated as retryable (same as server errors).

`common.py` also exposes `parse_json_str(value)`: some API fields (`app_data`, `custom_data`) are occasionally returned as serialized JSON strings, so it is applied at every yield/return point that surfaces them — `media_associations()` (sync + async), `CogniacMedia.detections()`, and `CogniacMedia.subjects()` — so callers always see dicts/lists.

### API URL Versioning

URLs are version-prefixed (e.g., `/1/tenants`, `/21/users/current`). Connection classes strip and re-prefix versions when constructing request URLs. When adding new endpoints, follow the existing `url_prefix + "/N/" + path` pattern.

Go through the connection wrappers `_get` / `_post` / `_put` / `_delete` — they version-prefix the URL, apply the default timeout, and re-authenticate on 401. Don't hit the raw httpx session from an entity method. `_get` retries only on 401; a method that should tolerate transient 5xx adds the `@retry(... server_error, 8 attempts)` decorator itself. **Body-bearing GETs** are routed through `session.request("GET", ...)` because httpx's `.get()` rejects a request body — so pass `json=`/`params=` to `_get` as needed rather than constructing requests by hand.

### CLI Tools (bin/)

- `icogniac` — IPython shell with pre-loaded cogniac magic commands and auto-authentication
- `cogupload` — Parallel (24-thread) media upload to a subject with infinite retry on server errors
- `cogstats` — EdgeFlow device statistics aggregation

The CLI uses the sync API only.

### Package Exports

`cogniac/__init__.py` re-exports all public classes (sync and async). New entity classes must be added there to be importable as `from cogniac import ClassName`.

## `cogniac` CLI Tool

Agent-friendly CLI. JSON output by default, `--format table` for human-readable. Auth via env vars (`COG_USER`/`COG_PASS` or `COG_API_KEY`, plus `COG_TENANT`) **or** a stored login from `cogniac auth login`. The tenant can also be specified per-invocation with the top-level `--tenant <tenant_id>` flag, which overrides `COG_TENANT`.

### Command structure & conventions

The command surface is **nested, noun-first / verb-last**: `cogniac <noun> [<sub-noun> ...] <verb>` (max depth ~3–4). Read verb is `get` (one) / `list` (collection); CRUD verbs are `create`/`get`/`list`/`update`/`delete`. Mutually-exclusive operations are sibling verbs under one sub-noun (e.g. `application replay status|start|stop`). Compound names split into separate nested tokens (`application consensus release items`), never hyphenated together; hyphens survive only inside an atomic terminal verb / model name (`new-random`, `label-mask-decoder-model`).

- **Resource ids are `--<resource>-id` flags** (`--application-id`, `--subject-uid`, …) — the canonical, documented form. Build them with the `_id(dest, help)` helper: the dest keeps the resource name, so handlers read `args.application_id` unchanged. Secondary ids use the same full naming (`--source-application-id`, `--workflow-id`). For backward compatibility `_id` also registers a **deprecated optional positional mirror** (`<dest>__posid`) so the older `application get <id>` spelling keeps working; `_resolve_positional_ids` (called in `main()`) folds the positional into the canonical dest after parsing (flag wins when both are given) and enforces required ids in either form (usage error, exit 2). Pass `pos=False` on the few verbs that already take another positional (`classify <image-file>`, `workflow version get <version>`) — there a positional id would be ambiguous, so the flag is required outright. Genuine file-path inputs stay positional (e.g. `media upload <filename>`).
- **Aliases, two layers, both routing to the same handler:** (1) token synonyms / plurals / abbreviations via `_SYNONYM_GROUPS` + `resource_aliases()`, accepted in every position including compounds (`app`/`apps`/`application`, `edgeflow`/`gateway`, `cert`/`certificate`, `detection`/`assertion`) — so `gateway event reboot` resolves exactly like `edgeflow event reboot`; (2) every prior flat / hyphenated spelling stays as a **hidden, deprecated** alias. To hide a deprecated parser/verb, **omit the `help` kwarg** — never `help=argparse.SUPPRESS` (an aliased subparser with `SUPPRESS` renders a literal `==SUPPRESS==` line in `--help`).
- **Register with the helpers**, not raw `add_parser` chains: `_add_resource` (top-level noun + aliases), `_add_verb(sub, name, handler, arg_specs, help, aliases, hidden)` where `arg_specs` is a list of `(names_tuple, add_argument_kwargs)`, and `_flat_alias` (a hidden flat compound whose verbs come from the same registrar function as the nested sub-noun, so both bind one handler set).
- **Pagination is automatic**: list commands `list(...)` the SDK generator and emit one JSON array. Keep `--limit` / `--cursor` / sort / filter flags; `--limit` caps the total. Most reads return the complete set by default, but the **expensive reads keep a default cap** (`edgeflow status --limit 10`, `subject media --limit 100`) so they don't walk an entire device/subject history unbidden; pass a larger `--limit` to widen.
- **Usage stays terse for agents**: the parser is a `_CogniacParser` and every `add_subparsers()` gets `metavar='<command>'` (set by a tree-walk at the end of `build_parser`) so usage strings don't dump the ~140 alias spellings; an invalid command prints a concise `difflib` close-match suggestion ("did you mean: …?") instead of the full choice list. The full tree is still in `--help`.
- **Agent ergonomics**: `cogniac commands` emits the whole surface as JSON (`_command_catalog` walks the tree → canonical noun/verbs/args with name, positional?, required?, type, choices, help — dual-form ids report `required: true` via the `_reqid_` marker). Global `--format`/`--tenant` come from a shared `_global_parent()` (suppressed defaults) added to every verb, so they parse **before or after** the command without clobbering. `--format` adds `jsonl` (one JSON object per line for lists). `--body` uses the `_body_arg` type (`@FILE` / `-` stdin / inline). `--start`/`--end` use the `_timestamp` type (epoch **or** ISO 8601). `output()` writes a `{"truncated": true, …}` notice to **stderr** when a list is capped by `--limit` (stdout stays clean).
- **Errors are a structured envelope**: `error_exit` emits `{"error": {"type", "status", "message", "hint"}}` — `type` is `auth`/`client`/`server`/`connection`/`rate_limit`/`error`; the server's JSON body is un-nested into `message`; `hint` self-heals (e.g. `cogniac auth login`). Handlers still call `error_exit("ClientError", str(e))`; the envelope is derived centrally.
- **`update` takes per-field flags and/or `--body`**: per-field flags for the resource's mutable fields (driven by the `_UPDATE_FIELDS` table; bool flags default to `None` so an unset flag is omitted) merged over a whole-object `--body JSON`, flags winning on overlap. A resource with dynamic fields stays `--body`-only.
- **Handlers** are `cmd_*` functions: call `get_connection(args)`, do the work inside `try/except ClientError → error_exit(...)`, then `output(result, args, table_type)` (JSON by default, table when a table type is given). For a fire-and-forget action whose SDK method returns `None`, print a synthesized status dict. Every command must resolve to a callable handler (`set_defaults(func=...)`); the smoke tests parse every command and alias and assert it.

The examples below use the historical flat spellings, which remain valid as hidden aliases; the canonical forms are nested (e.g. `cogniac application list`, `cogniac subject create <name>`).

Auth commands:
```
cogniac auth                    # check credentials; with --tenant/COG_TENANT, also verifies a session can be minted
cogniac auth login              # browser-loopback login; stores a per-user API key at ~/.config/cogniac/credentials (0600). --no-browser prints the URL instead of opening it
cogniac auth logout             # remove the stored login credential
```

Read commands:
```
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
cogniac edgeflows status <id>   # status events: --subsystem, --limit; --list-subsystems (+ --scan-limit) for distinct-subsystem discovery
cogniac cameras list            # list all cameras
cogniac cameras get <id>        # get specific camera
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
