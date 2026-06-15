"""
Regression tests for request-body support on _get / _head.

cogniac 3.x migrated the HTTP client from requests to httpx. httpx's
Client.get()/head() convenience methods do not accept a request body, but the
SDK must still support GET/HEAD-with-body (the requests-era behavior) because
callers such as cogtrain issue GET-with-body requests (e.g. OptunaStorage).
_get/_head therefore route through session.request(), matching _delete.
"""

import pytest
from tests.conftest import requires_live


@requires_live
class TestRequestBodySupport:

    def test_get_accepts_request_body(self, cc):
        # Pre-fix this raised
        # "TypeError: Client.get() got an unexpected keyword argument 'data'".
        resp = cc._get("/1/users/current", data={"data": "{}"})
        assert resp.status_code == 200

    def test_head_accepts_request_body(self, cc):
        # _head has the same httpx limitation; it must not reject a body kwarg.
        try:
            cc._head("/1/users/current", data={"data": "{}"})
        except TypeError as exc:
            pytest.fail(f"_head must accept a request body: {exc}")
        except Exception:
            # A non-2xx status (e.g. 405) is acceptable here; only the
            # TypeError on the body kwarg is the regression we guard against.
            pass
