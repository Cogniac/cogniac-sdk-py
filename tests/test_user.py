"""
Baseline tests for CogniacUser.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestUser:

    def test_get_current_user(self, cc):
        user = cogniac.CogniacUser.get(cc)
        assert user.email is not None
        assert user.user_id is not None

    def test_user_api_keys(self, cc):
        keys = cc.user.api_keys()
        assert isinstance(keys, list)
