"""
Baseline tests for CogniacEdgeFlow.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestEdgeFlowRead:

    def test_get_all_edgeflows(self, cc):
        edgeflows = cc.get_all_edgeflows()
        assert isinstance(edgeflows, list)
        # tenant may or may not have edgeflows
        if len(edgeflows) > 0:
            ef = edgeflows[0]
            assert ef.gateway_id is not None

    def test_get_edgeflow(self, cc):
        edgeflows = cc.get_all_edgeflows()
        if len(edgeflows) == 0:
            pytest.skip("No edgeflows on test tenant")
        ef = edgeflows[0]
        fetched = cogniac.CogniacEdgeFlow.get(cc, ef.gateway_id)
        assert fetched.gateway_id == ef.gateway_id
