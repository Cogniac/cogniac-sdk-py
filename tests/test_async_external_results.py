"""
Async integration tests for AsyncCogniacExternalResult.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestAsyncExternalResultRead:

    @pytest.mark.asyncio
    async def test_search_by_time(self):
        """Search external results by time range — may return empty but shouldn't error."""
        from time import time
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            end = time()
            start = end - 86400  # last 24 hours
            results = await cogniac.AsyncCogniacExternalResult.search(
                cc, time_start=start, time_end=end, limit=5
            )
            assert isinstance(results, list)
