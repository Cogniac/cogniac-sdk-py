"""
Async integration tests for AsyncCogniacOpsReview.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestAsyncOpsReviewRead:

    @pytest.mark.asyncio
    async def test_get_pending(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            pending = await cogniac.AsyncCogniacOpsReview.get_pending(cc)
            assert isinstance(pending, int)
            assert pending >= 0

    @pytest.mark.asyncio
    async def test_search_generator(self):
        """Search ops review results — may return empty but shouldn't error."""
        from time import time
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            end = time()
            start = end - 86400
            results = []
            async for r in cogniac.AsyncCogniacOpsReview.search(
                cc, start=start, end=end, limit=5
            ):
                results.append(r)
            assert isinstance(results, list)
