"""
Baseline tests for CogniacTenant.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestTenant:

    def test_get_tenant(self, cc):
        tenant = cogniac.CogniacTenant.get(cc)
        assert tenant.tenant_id == cc.tenant_id
        assert tenant.name is not None

    def test_tenant_users(self, cc):
        users = cc.tenant.users()
        assert isinstance(users, list)
        assert len(users) > 0
        assert 'email' in users[0]
