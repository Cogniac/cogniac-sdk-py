"""
Baseline tests for CogniacConnection.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestConnection:

    def test_connection_authenticates(self, cc):
        assert cc.session is not None
        assert cc.tenant_id is not None

    def test_tenant_property(self, cc):
        tenant = cc.tenant
        assert tenant is not None
        assert tenant.tenant_id == cc.tenant_id
        assert tenant.name is not None

    def test_user_property(self, cc):
        user = cc.user
        assert user is not None
        assert user.email is not None

    def test_get_version(self, cc):
        version = cc.get_version()
        assert version is not None

    def test_get_all_authorized_tenants(self):
        tenants = cogniac.CogniacConnection.get_all_authorized_tenants()
        assert 'tenants' in tenants
        assert len(tenants['tenants']) > 0
