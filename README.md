# Cogniac Python SDK

Python SDK for the Cogniac public API. Provides both synchronous and asynchronous (async/await) interfaces.

Requires Python 3.11+

## Installation

```bash
pip install cogniac
```

## Configuration

Authentication is configured via environment variables or constructor arguments:

| Variable | Description |
|----------|-------------|
| `COG_USER` | Cogniac username (usually an email address) |
| `COG_PASS` | Cogniac password |
| `COG_API_KEY` | API key (alternative to username/password) |
| `COG_TENANT` | Tenant ID (required if user belongs to multiple tenants) |
| `COG_URL_PREFIX` | API endpoint (default: `https://api.cogniac.io/`) |

## Synchronous API

```python
import cogniac

cc = cogniac.CogniacConnection()

# Tenants and users
tenant = cc.get_tenant()
print(tenant.name)

# Applications
apps = cc.get_all_applications()
app = cc.get_application(application_id)

# Subjects
subjects = cc.get_all_subjects()
subject = cc.create_subject(name="my-subject", description="example")
subject.description = "updated"  # auto-syncs to API
subject.delete()

# Media
media = cc.create_media("image.jpg", meta_tags=["test"])
fetched = cc.get_media(media.media_id)
image_bytes = fetched.download()          # returns bytes
with open("out.jpg", "wb") as f:          # or write to file
    fetched.download(f)                   # takes open file object, NOT a path string

# Paginated results via generators
for detection in app.detections(limit=100):
    print(detection)

# Score your own predictions (e.g. from a VLM or another model) the way CloudCore
# scores the app's models: against a consensus release, with an evaluation metric
result = app.evaluate([{"media_id": media_id, "subject_uid": subject_uid, "probability": 0.9}],
                      consensus_release_id=None,     # default: the app's latest release
                      evaluation_metric_hash=None,   # default: the app's primary metric
                      allow_unscorable=False,        # True: score what can be scored instead of a 400
                      timeout=None)                  # default 3600 s: scoring time grows with the release
print(result["coverage"], result["summary"])
```

Each prediction is one (media, focus, subject):

- `media_id`, `subject_uid`, and `focus` for apps that label a focus box (copy it from the release label; omit it for whole-image labels);
- plus, by app type: `probability` (detection, classification), `boxes` (`[{x0, y0, x1, y1, probability?}]`, image pixels), `points` (`[{x, y, probability?}]`, image pixels) or `text` (OCR; the app must have exactly one output subject).

For classification, send one prediction per unit, naming the chosen subject; for the other types, a subject with no prediction counts as a negative. The CLI's `--predictions FILE` takes a JSON array or JSON Lines of these.

### Entity Classes

| Class | Description |
|-------|-------------|
| `CogniacConnection` | Authentication and HTTP session management |
| `CogniacApplication` | Vision applications (detection, classification, etc.) |
| `CogniacSubject` | Organizational groupings of media |
| `CogniacMedia` | Image and video files |
| `CogniacTenant` | Tenant (organization) management |
| `CogniacUser` | User accounts and API keys |
| `CogniacEdgeFlow` | Edge computing devices (alias: `CogniacGateway`) |
| `CogniacNetworkCamera` | Network camera configuration |
| `CogniacExternalResult` | External inspection results |
| `CogniacOpsReview` | Operations review queue |
| `CogniacDeployment` | Deployment groups (EdgeFlow/CloudFlow rollouts) |
| `CogniacDeploymentCapacityClass` | Deployment capacity classes |
| `CogniacWorkflow` | Deployment workflows and versions |
| `CogniacBuild` | EdgeFlow/CloudFlow build definitions |

## Async API

The async interface mirrors the sync API. Use `AsyncCogniacConnection.create()` as an async factory:

```python
import asyncio
import cogniac

async def main():
    async with await cogniac.AsyncCogniacConnection.create() as cc:
        # List subjects
        subjects = await cogniac.AsyncCogniacSubject.get_all(cc)
        for s in subjects:
            print(s.name, s.subject_uid)

        # Create and update
        s = await cogniac.AsyncCogniacSubject.create(cc, name="my-subject")
        await s.set(description="updated")  # explicit async setter
        await s.delete()

        # Download media
        media = await cogniac.AsyncCogniacMedia.get(cc, media_id)
        image_bytes = await media.download()      # returns bytes
        with open("out.jpg", "wb") as f:           # or write to file
            await media.download(f)                # takes open file object, NOT a path string

        # Async generators for paginated endpoints
        apps = await cogniac.AsyncCogniacApplication.get_all(cc)
        async for detection in apps[0].detections(limit=10):
            print(detection)

asyncio.run(main())
```

Every sync entity class has an async counterpart prefixed with `Async` (e.g., `AsyncCogniacSubject`, `AsyncCogniacMedia`).

### Key Differences from Sync API

- **Connection**: `await AsyncCogniacConnection.create(...)` instead of `CogniacConnection(...)`
- **Attribute updates**: `await subject.set(name="new")` instead of `subject.name = "new"` (batches multiple fields in one API call)
- **Pagination**: `async for` with generators (`detections`, `media_associations`, `usage`, etc.)
- **Cleanup**: supports `async with` context manager for automatic session cleanup

## CLI Tools

### `cogniac`

Agent-friendly CLI. JSON output by default; `--format table` for humans or `--format jsonl` for one JSON object per line. The command tree is **nested, noun-first / verb-last**; resource ids are `--<resource>-id` flags (the older positional form, e.g. `application get <id>`, still works). `--format` and `--tenant` may be given before or after the command.

```bash
cogniac auth                                       # check credentials (add --tenant <id> to verify a session)
cogniac auth login                                 # browser login; store a per-user API key
cogniac commands                                   # print the whole command tree as JSON (noun -> verbs -> args)

cogniac tenant get                                 # current tenant info
cogniac application list                           # list applications
cogniac application get --application-id <id>      # one application
cogniac subject list
cogniac subject search --prefix test               # search subjects
cogniac subject media --subject-uid <uid> --full-media   # full media records, not just media_id
cogniac media get --media-id <id>                  # media metadata
cogniac media download --media-id <id> -o out.jpg  # download media to file
cogniac edgeflow list                              # list edge devices
cogniac edgeflow status --edgeflow-id <id> --list-subsystems   # discover which subsystems a device reports
cogniac edgeflow health                            # fleet health derived from each device's latest status record
cogniac application create --body @app.json        # --body takes inline JSON, @FILE, or - (stdin)
cogniac application evaluate --application-id <id> --predictions preds.jsonl   # score predictions
                                                   # (JSON array or JSON Lines) against the latest consensus
                                                   # release with the primary metric; --consensus-release-id,
                                                   # --evaluation-metric-hash, --allow-unscorable, --label

cogniac deployment deploy --deployment-group-id <id> --workflow-id <wf>   # DISPATCH a workflow rollout
                                                   # (--now bypasses the group schedule; --timeout raises the
                                                   #  client read timeout — the server blocks until every
                                                   #  EdgeFlow accepts, default 300s)
cogniac deployment deploy-status --deployment-group-id <id>               # rollout convergence status
cogniac deployment target workflow set ...         # records target_workflow_id only — does NOT deploy
```

#### Descriptions under version control

`cogniac descriptions` keeps a tenant's tenant, application and subject descriptions in a `descriptions-<tenant_id>.yaml` file, so description changes can be reviewed and versioned like code:

```bash
cogniac --tenant <tenant_id> descriptions export [--application-id <id> ...]   # write descriptions-<tenant_id>.yaml
cogniac descriptions plan descriptions-<tenant_id>.yaml    # what differs from the live tenant; exit 2 if anything does
cogniac descriptions apply descriptions-<tenant_id>.yaml   # write the descriptions that differ (asks first; --yes to skip)
```

```yaml
tenant:
  tenant_id: <tenant_id>
  name: <tenant name>          # names are for readability only; never applied
  description: <text>
applications:
  <application_id>:
    name: <application name>
    description: |
      <text, may span lines>
subjects:
  <subject_uid>:
    name: <subject name>
    description: <text>
```

- The file names the tenant; `plan` and `apply` refuse a `--tenant` that differs.
- Only descriptions are managed. Anything the file doesn't list is left alone, and a listed tenant only has its description managed if the file gives one.
- A listed application or subject must have a `description` key, and `description: ""` clears that description. Descriptions are limited to 8,000 characters.
- `export` writes the tenant and every application and subject by default. With `--application-id`, it writes only those applications and their input and output subjects. `--refresh --file FILE` updates the entries an existing file lists.
- `apply` works from the file and the live values alone, so running it again is a no-op. Writing the tenant description needs the tenant admin role.

#### Evaluation metrics

Each application scores its models with up to five active evaluation metrics. One is primary: models are ranked and released by it, and `evaluate()` uses it unless given another `evaluation_metric_hash`.

```bash
cogniac application evaluation metrics schema [--name box_F1]                # what each metric scores; its parameters, defaults and ranges
cogniac application evaluation metrics get --application-id <id>             # the app's active metrics, primary first, with hashes
cogniac application evaluation metrics create --application-id <id> --body '{"name": "box_F1", "iou_threshold": 0.5, "active": 1}'
cogniac application evaluation metrics set-primary --application-id <id> --evaluation-metric-hash <hash>
cogniac application evaluation metrics delete --application-id <id> --evaluation-metric-hash <hash>   # not the primary
```

In the SDK: `CogniacApplication.evaluation_metric_schemas(cc, name=None)`, and on an application `evaluation_metrics()`, `create_evaluation_metric(body)`, `set_primary_evaluation_metric(hash)` and `delete_evaluation_metric(hash)`. A metric is identified by its configuration, so the same configuration always has the same hash. `create` adds a non-primary metric; add `"primary": 1` to make it primary in the same call.

Run `cogniac <noun> --help` to explore the tree interactively, or `cogniac commands` for the full machine-readable catalog. An unknown command suggests the closest match.

### `icogniac`

Interactive IPython shell with pre-loaded Cogniac connection:

```bash
icogniac [optional tenant name or ID]
```

### `cogupload`

Parallel media upload (24 threads) to a subject:

```bash
cogupload <subject_uid> <directory>
```

### `cogstats`

EdgeFlow statistics aggregation:

```bash
cogstats -t TENANT_ID [-g GATEWAY_ID] [-s START] [-e END]
```

## Support

Please email support@cogniac.co with feedback.
