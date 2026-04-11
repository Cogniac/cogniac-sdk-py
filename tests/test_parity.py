"""
Parity tests: verify sync and async APIs produce equivalent results.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestParity:

    @pytest.mark.asyncio
    async def test_get_all_subjects_parity(self, cc):
        """Sync and async get_all_subjects return the same subject UIDs."""
        sync_uids = {s.subject_uid for s in cc.get_all_subjects()}

        async with await cogniac.AsyncCogniacConnection.create() as acc:
            async_subjects = await cogniac.AsyncCogniacSubject.get_all(acc)
            async_uids = {s.subject_uid for s in async_subjects}

        assert sync_uids == async_uids

    @pytest.mark.asyncio
    async def test_get_all_applications_parity(self, cc):
        """Sync and async get_all_applications return the same app IDs."""
        sync_ids = {a.application_id for a in cc.get_all_applications()}

        async with await cogniac.AsyncCogniacConnection.create() as acc:
            async_apps = await cogniac.AsyncCogniacApplication.get_all(acc)
            async_ids = {a.application_id for a in async_apps}

        assert sync_ids == async_ids

    @pytest.mark.asyncio
    async def test_get_version_parity(self, cc):
        """Sync and async get_version return the same data."""
        sync_version = cc.get_version()

        async with await cogniac.AsyncCogniacConnection.create() as acc:
            async_version = await acc.get_version()

        assert sync_version == async_version

    @pytest.mark.asyncio
    async def test_get_tenant_parity(self, cc):
        """Sync and async get tenant return the same tenant_id and name."""
        sync_tenant = cc.get_tenant()

        async with await cogniac.AsyncCogniacConnection.create() as acc:
            async_tenant = await cogniac.AsyncCogniacTenant.get(acc)

        assert sync_tenant.tenant_id == async_tenant.tenant_id
        assert sync_tenant.name == async_tenant.name

    @pytest.mark.asyncio
    async def test_get_edgeflows_parity(self, cc):
        """Sync and async get_all_edgeflows return the same gateway IDs."""
        sync_ids = {ef.gateway_id for ef in cc.get_all_edgeflows()}

        async with await cogniac.AsyncCogniacConnection.create() as acc:
            async_efs = await cogniac.AsyncCogniacEdgeFlow.get_all(acc)
            async_ids = {ef.gateway_id for ef in async_efs}

        assert sync_ids == async_ids
