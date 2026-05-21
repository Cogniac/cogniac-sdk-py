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
```

### Entity Classes

| Class | Description |
|-------|-------------|
| `CogniacConnection` | Authentication and HTTP session management |
| `CogniacApplication` | Vision applications (detection, classification, etc.) |
| `CogniacSubject` | Organizational groupings of media |
| `CogniacMedia` | Image and video files |
| `CogniacTenant` | Tenant (organization) management |
| `CogniacUser` | User accounts and API keys |
| `CogniacEdgeFlow` | Edge computing devices |
| `CogniacNetworkCamera` | Network camera configuration |
| `CogniacExternalResult` | External inspection results |
| `CogniacOpsReview` | Operations review queue |

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

Agent-friendly CLI with JSON output (default) or `--format table`.

```bash
cogniac auth                            # check credentials (add --tenant <id> to verify a session)
cogniac tenant                          # current tenant info
cogniac apps list                       # list applications
cogniac apps leaderboard <id>           # ranked candidate-model snapshot
cogniac apps eval-metrics <id>          # active evaluation metrics
cogniac subjects list                   # list subjects
cogniac subjects search --prefix test   # search subjects
cogniac media get <media_id>            # get media metadata
cogniac media download <media_id> -o f  # download media to file
cogniac edgeflows list                  # list edge devices
```

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
