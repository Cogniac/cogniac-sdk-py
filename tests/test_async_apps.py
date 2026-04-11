"""
Async integration tests for AsyncCogniacApplication.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestAsyncAppRead:

    @pytest.mark.asyncio
    async def test_get_all_applications(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            apps = await cogniac.AsyncCogniacApplication.get_all(cc)
            assert isinstance(apps, list)
            assert len(apps) > 0
            app = apps[0]
            assert app.application_id is not None
            assert app.name is not None

    @pytest.mark.asyncio
    async def test_get_application(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            apps = await cogniac.AsyncCogniacApplication.get_all(cc)
            first = apps[0]
            fetched = await cogniac.AsyncCogniacApplication.get(cc, first.application_id)
            assert fetched.application_id == first.application_id

    @pytest.mark.asyncio
    async def test_pending_feedback(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            apps = await cogniac.AsyncCogniacApplication.get_all(cc)
            app = apps[0]
            pending = await app.pending_feedback()
            assert isinstance(pending, int)

    @pytest.mark.asyncio
    async def test_app_immutable_raises(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            apps = await cogniac.AsyncCogniacApplication.get_all(cc)
            app = apps[0]
            with pytest.raises(AttributeError):
                app.application_id = "bad"

    @pytest.mark.asyncio
    async def test_app_mutable_guard_raises(self):
        """Assigning to a mutable key should raise, directing user to set()."""
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            apps = await cogniac.AsyncCogniacApplication.get_all(cc)
            app = apps[0]
            with pytest.raises(AttributeError, match="set"):
                app.name = "should-not-work"

    @pytest.mark.asyncio
    async def test_detections_generator(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            apps = await cogniac.AsyncCogniacApplication.get_all(cc)
            for app in apps:
                dets = []
                async for d in app.detections(limit=3):
                    dets.append(d)
                if len(dets) > 0:
                    return
            pytest.skip("No apps with detections found")
