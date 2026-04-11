"""
Async integration tests for AsyncCogniacUser.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestAsyncUserRead:

    @pytest.mark.asyncio
    async def test_get_current_user(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            user = await cogniac.AsyncCogniacUser.get(cc)
            assert user.email is not None
            assert user.user_id is not None

    @pytest.mark.asyncio
    async def test_user_api_keys(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            user = await cogniac.AsyncCogniacUser.get(cc)
            keys = await user.api_keys()
            assert isinstance(keys, list)

    @pytest.mark.asyncio
    async def test_user_mutable_guard_raises(self):
        """Assigning to a mutable key should raise, directing user to set()."""
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            user = await cogniac.AsyncCogniacUser.get(cc)
            with pytest.raises(AttributeError, match="set"):
                user.given_name = "should-not-work"
