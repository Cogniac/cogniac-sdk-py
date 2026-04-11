"""
Shared fixtures for cogniac SDK integration tests.

Requires live Cogniac credentials via environment variables:
  COG_USER/COG_PASS or COG_API_KEY, plus COG_TENANT
"""

import os
import pytest
import cogniac


requires_live = pytest.mark.skipif(
    not os.environ.get('COG_API_KEY') and not os.environ.get('COG_USER'),
    reason="No Cogniac credentials configured"
)


@pytest.fixture(scope="session")
def cc():
    """Session-scoped authenticated CogniacConnection."""
    return cogniac.CogniacConnection()
