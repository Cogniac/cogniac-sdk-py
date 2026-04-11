"""
Async integration tests for AsyncCogniacEdgeFlow.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestAsyncEdgeFlowRead:

    @pytest.mark.asyncio
    async def test_get_all_edgeflows(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            edgeflows = await cogniac.AsyncCogniacEdgeFlow.get_all(cc)
            assert isinstance(edgeflows, list)
            if len(edgeflows) > 0:
                ef = edgeflows[0]
                assert ef.gateway_id is not None

    @pytest.mark.asyncio
    async def test_get_edgeflow(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            edgeflows = await cogniac.AsyncCogniacEdgeFlow.get_all(cc)
            if len(edgeflows) == 0:
                pytest.skip("No edgeflows on test tenant")
            ef = edgeflows[0]
            fetched = await cogniac.AsyncCogniacEdgeFlow.get(cc, ef.gateway_id)
            assert fetched.gateway_id == ef.gateway_id

    @pytest.mark.asyncio
    async def test_status_generator(self):
        """Test the async status generator on the first available edgeflow."""
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            edgeflows = await cogniac.AsyncCogniacEdgeFlow.get_all(cc)
            if len(edgeflows) == 0:
                pytest.skip("No edgeflows on test tenant")
            ef = edgeflows[0]
            events = []
            async for event in ef.status(limit=3):
                events.append(event)
            # may be empty if edgeflow has no recent status, but shouldn't error
            assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_edgeflow_setattr_guard_raises(self):
        """Assigning to a server-managed key should raise, directing user to set()."""
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            edgeflows = await cogniac.AsyncCogniacEdgeFlow.get_all(cc)
            if len(edgeflows) == 0:
                pytest.skip("No edgeflows on test tenant")
            ef = edgeflows[0]
            with pytest.raises(AttributeError, match="set"):
                ef.name = "should-not-work"
