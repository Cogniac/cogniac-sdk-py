"""
Async integration tests for AsyncCogniacConnection.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestAsyncConnection:

    @pytest.mark.asyncio
    async def test_async_connection_authenticates(self):
        cc = await cogniac.AsyncCogniacConnection.create()
        try:
            assert cc.session is not None
            assert cc.tenant_id is not None
        finally:
            await cc.close()

    @pytest.mark.asyncio
    async def test_async_connection_context_manager(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            assert cc.session is not None
            assert cc.tenant_id is not None

    @pytest.mark.asyncio
    async def test_async_get_version(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            version = await cc.get_version()
            assert version is not None
