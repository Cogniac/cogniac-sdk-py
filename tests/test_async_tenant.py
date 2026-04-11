"""
Async integration tests for AsyncCogniacTenant.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestAsyncTenantRead:

    @pytest.mark.asyncio
    async def test_get_tenant(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            tenant = await cogniac.AsyncCogniacTenant.get(cc)
            assert tenant.tenant_id == cc.tenant_id
            assert tenant.name is not None

    @pytest.mark.asyncio
    async def test_tenant_users(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            tenant = await cogniac.AsyncCogniacTenant.get(cc)
            users = await tenant.users()
            assert isinstance(users, list)
            assert len(users) > 0
            assert 'email' in users[0]

    @pytest.mark.asyncio
    async def test_tenant_immutable_raises(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            tenant = await cogniac.AsyncCogniacTenant.get(cc)
            with pytest.raises(AttributeError):
                tenant.tenant_id = "bad"

    @pytest.mark.asyncio
    async def test_tenant_mutable_guard_raises(self):
        """Assigning to a mutable key should raise, directing user to set()."""
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            tenant = await cogniac.AsyncCogniacTenant.get(cc)
            with pytest.raises(AttributeError, match="set"):
                tenant.name = "should-not-work"
