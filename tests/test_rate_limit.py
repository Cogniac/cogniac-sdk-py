"""
Unit tests for HTTP 429 rate-limit retry behavior (issue #158).

No live credentials required.
"""

import pytest
from unittest.mock import MagicMock

from cogniac.common import raise_errors, ServerError


class TestRaiseErrors429:

    def _mock_resp(self, status_code, text="rate limited"):
        r = MagicMock()
        r.status_code = status_code
        r.text = text
        return r

    def test_429_raises_server_error(self):
        """429 must raise ServerError so the tenacity retry path picks it up."""
        with pytest.raises(ServerError) as exc_info:
            raise_errors(self._mock_resp(429))
        assert "429" in str(exc_info.value) or "RateLimited" in str(exc_info.value)

    def test_500_raises_server_error(self):
        with pytest.raises(ServerError):
            raise_errors(self._mock_resp(500))

    def test_400_not_server_error(self):
        from cogniac.common import ClientError
        with pytest.raises(ClientError):
            raise_errors(self._mock_resp(400))

    def test_200_no_error(self):
        raise_errors(self._mock_resp(200))  # should not raise
